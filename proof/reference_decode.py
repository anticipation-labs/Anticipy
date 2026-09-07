#!/usr/bin/env python3
"""The reference decoder — pluggable, and honest about what is actually here.

§11 of research/2026-08-24-engine-options.md asks for "a strong reference —
whisper large-v3 or Parakeet-TDT-v3 on the Mac", and the whole experiment hangs
off it: if a good decoder loses the same third of the words off the same file,
the recognizer is exonerated and the fault is upstream in the capture path.

WHAT IS ACTUALLY INSTALLED ON THIS MACHINE, checked rather than assumed:
openai-whisper 20250625 under /opt/anaconda3/bin/python3, with exactly one set
of weights cached — `base.pt`. `base` is NOT the decoder §11 asked for. It is a
74M-parameter model; large-v3 is 1550M. Running it and calling the result "a
strong reference decoder" would be the flattering-instrument failure this repo
has already been burned by twice.

So this file does two things instead of pretending:

1. It never argues about model strength. `proof/engine_or_audio.py` settles it
   empirically — the control arm is the same script read close to the mic, and
   the pre-registered validity gate requires the reference decoder to capture
   >= 0.85 there before R1 or R2 are available at all. A `base` model that
   clears the control is strong enough for the inference being drawn from it. A
   `base` model that does not is reported as CANNOT DECIDE, naming itself.

2. It refuses to download weights unless told to. whisper fetches missing
   weights from the network on first use; with no network that fails after a
   long opaque hang, and with network it silently turns an offline experiment
   into an online one. Either way the operator should have said so out loud.

    python3 proof/reference_decode.py --check
    python3 proof/reference_decode.py --wav arm_a.wav --out arm_a/reference.txt

NOTHING IN THIS FILE IS A DEPENDENCY OF THE REPO. whisper is discovered on the
machine and driven as a subprocess; the scorer and its tests import none of it
and run with the standard library alone. If this machine had no whisper, every
test would still pass and `--check` would print what is missing — which is the
designed outcome, not a failure.

SECOND BACKEND, added 2026-09-06 because the first one was never going to run
here. The paragraph above was written when `base.pt` was cached under
/opt/anaconda3; it is not any more, no python on this Mac imports `whisper`,
there is no Homebrew and torch is not installed. `--check` printed
`available: False` and the 1,400-line scorer behind it had therefore never
scored anything. A gate that cannot run is not a gate.

So there are now two named backends and the run says which one spoke:

  whisper-local   the original subprocess path. PREFERRED whenever it is
                  available: it is offline, it is free, and nothing about it
                  depends on a third party being up.
  whisper-hosted  Groq's OpenAI-compatible transcription endpoint, driven with
                  urllib and a multipart body. large-v3 weights someone else
                  pays to hold in memory. It is a FALLBACK — chosen explicitly
                  (`--backend hosted`) or by `--backend auto` after local has
                  been asked first and said no.

What the second backend costs, said out loud rather than discovered later:
the audio leaves this machine, the run is by definition online, and the
decoder is a version string on somebody else's server rather than a file with
a sha256 on this disk. That is why `engine=` is stamped into every provenance
line it writes. A reference decode whose reader cannot tell whisper-local from
whisper-hosted is a reference of unknown provenance, and R1/R2 are drawn by
SUBTRACTING the reference from the app — so an unknown reference makes the
whole subtraction unknown.

    python3 proof/reference_decode.py --backend hosted \\
        --wav arm_a.wav --out arm_a/reference.txt
"""
from __future__ import annotations

import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid

# The scorer strips this line before scoring and checks what it says against
# the cell it was filed under. Imported rather than restated so the two files
# cannot drift into two different contracts. `tokens` is imported for the same
# reason: "one word" has to mean the same thing on both sides of the handover,
# or a transcript this file waves through is a transcript the scorer refuses.
from proof.engine_or_audio import (  # noqa: E402
    MIN_TRANSCRIPT_WORDS,
    PROVENANCE_PREFIX,
    tokens,
)

REPO_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))

#: The models §11 named. Anything else still runs — the control arm decides
#: whether it was good enough — but the report says plainly that it is not the
#: decoder the experiment was designed around.
REFERENCE_GRADE = {"large", "large-v1", "large-v2", "large-v3", "large-v3-turbo"}

#: Searched in order, after $ANTICIPY_WHISPER_PYTHON. The system python3 on this
#: machine does not carry whisper and the anaconda one does, so "python3" alone
#: would report the tool missing while it sits on disk.
INTERPRETER_CANDIDATES = (
    "/opt/anaconda3/bin/python3",
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
    "python3",
)

DEFAULT_CACHE = os.path.expanduser("~/.cache/whisper")

# ---------------------------------------------------------------------------
# BACKENDS. Two names, and every report and every provenance line carries one
# of them. They are strings rather than a bool because `hosted=False` reads as
# "the normal one" and there is no normal one — there is the offline one and
# the online one, and which spoke is the first thing a reader of a reference
# transcript needs to know.
# ---------------------------------------------------------------------------
BACKEND_LOCAL = "whisper-local"
BACKEND_HOSTED = "whisper-hosted"
BACKENDS = (BACKEND_LOCAL, BACKEND_HOSTED)

#: What the operator may type. `auto` is not a backend — it is a rule for
#: picking one, and it resolves to a named backend before anything decodes.
BACKEND_ALIASES = {
    "local": BACKEND_LOCAL, "whisper-local": BACKEND_LOCAL,
    "hosted": BACKEND_HOSTED, "whisper-hosted": BACKEND_HOSTED,
    "groq": BACKEND_HOSTED,
}

#: Verified against Groq's speech-to-text documentation on 2026-09-06 rather
#: than taken from the brief that asked for this. The endpoint is
#: OpenAI-compatible; the models are Groq's own ids, and `whisper-large-v3` is
#: the 1550M-parameter decoder §11 asked for by name.
GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
HOSTED_MODELS = {
    "whisper-large-v3": "large-v3, 1550M — the decoder §11 asked for",
    "whisper-large-v3-turbo": "large-v3-turbo — faster, pruned decoder",
}
HOSTED_DEFAULT_MODEL = "whisper-large-v3"

#: Groq's documented ceiling on the free tier (the dev tier is 100 MB). The
#: refusal names both, because "too big" with no number is a dead end for
#: whoever reads it at eleven at night.
HOSTED_MAX_BYTES = 25 * 1024 * 1024
HOSTED_MAX_BYTES_DEV = 100 * 1024 * 1024

#: Documented container list, checked the same day. Only consulted when the
#: converter is missing and the original file has to go up as it is.
HOSTED_FORMATS = ("flac", "mp3", "mp4", "mpeg", "mpga", "m4a", "ogg", "wav",
                  "webm")

HOSTED_TIMEOUT_S = 600

#: Load-bearing, and found the hard way on 2026-09-06: the endpoint sits behind
#: Cloudflare, and urllib's default `Python-urllib/3.9` User-Agent is refused
#: at the edge with `HTTP 403 ... error code: 1010` — a browser-signature ban,
#: not an auth failure. The same key over curl returned 200 on the same file in
#: the same minute. Anything that reads as a real client passes; this one names
#: itself so a log on the other end can see who it was.
HOSTED_USER_AGENT = "anticipy-reference-decode/1.0 (+proof/reference_decode.py)"

GROQ_KEY_NAME = "GROQ_API_KEY"

#: Read at runtime, never committed: .gitignore line 22 covers `.env.*`. The
#: value is never returned in a plan dict, never printed, and never put in an
#: exception message — availability carries `have_key` as a bool for exactly
#: that reason.
ENV_LOCAL = os.path.join(REPO_ROOT, ".env.local")

# ---------------------------------------------------------------------------
# CONVERSION. The phone writes 32-bit float at the microphone's native rate:
# three minutes at 48 kHz mono float32 is 34.5 MB, which is over the free-tier
# limit before a word has been said. The same three minutes at 16 kHz mono
# int16 is 5.8 MB, and 16 kHz mono is what the hosted model downsamples to
# anyway — so the conversion throws away nothing the decoder was going to use.
#
# afconvert ships with macOS. `--src-quality 127` is its best sample-rate
# converter; the default is not, and a reference decoder should not be handed
# a cheaper resample than the machine can do.
# ---------------------------------------------------------------------------
AFCONVERT = "/usr/bin/afconvert"

#: Zero tokens and one token are the same failure, and the scorer's own comment
#: block (proof/engine_or_audio.py:169-191) is where that was settled: "you"
#: and "Thank you." are whisper's canonical output on silence or a failed
#: decode, and "you" alone once scored capture 0.0027 with script share 1.00
#: and fired R1 off a dead file. `if not text:` catches the first and waves the
#: second through.
#:
#: Note what this is NOT. It is not a word list and it does not read the words:
#: it counts them. "Thank you." is refused here because it is two tokens under
#: MIN_TRANSCRIPT_WORDS and gets the warning below, and if it were the whole
#: truthful transcript of a two-second clip it would still be written out —
#: what is refused is only the degenerate case where there is no transcript to
#: speak of at all. Deciding what a transcript MEANS is the scorer's job and
#: nobody's regex (HARNESS-LAWS.md, Law 1).
MIN_DECODE_WORDS = 2

#: Sentinel: "I was not told, go and look". Distinct from None, which means
#: "I was told there is none", and the difference is the whole point — a test
#: that wants to simulate a machine with no key must be able to say so.
_LOOK_IT_UP = object()


def cached_models(cache_dir: str = DEFAULT_CACHE) -> list[str]:
    """Which weights are already on disk, so nothing has to reach the network
    to find out that it must reach the network."""
    try:
        names = sorted(os.listdir(cache_dir))
    except OSError:
        return []
    return [n[:-3] for n in names if n.endswith(".pt")]


def has_whisper(interpreter: str) -> bool:
    try:
        r = subprocess.run([interpreter, "-c", "import whisper"],
                           capture_output=True, timeout=60)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def find_interpreter(candidates=INTERPRETER_CANDIDATES, probe=has_whisper):
    env = os.environ.get("ANTICIPY_WHISPER_PYTHON")
    for candidate in ((env,) if env else ()) + tuple(candidates):
        if probe(candidate):
            return candidate
    return None


def read_env_file(path: str, name: str):
    """One value out of a dotenv file, or None. No dependency, no export.

    Deliberately dumb: it does not expand, interpolate, or export. It answers
    one question — is the operator's key on this disk — and the answer never
    leaves this module except as a bool.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].lstrip()
                key, sep, value = line.partition("=")
                if not sep or key.strip() != name:
                    continue
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                return value or None
    except OSError:
        return None
    return None


def groq_api_key(environ=None, env_file: str = ENV_LOCAL):
    """The key, from the environment first and `.env.local` second, or None.

    Environment first so an operator can run one decode against a different
    account without editing a file. The return value is a secret: it goes into
    an Authorization header and nowhere else. Nothing in this module prints it,
    stores it, or puts it in an exception message.
    """
    env = os.environ if environ is None else environ
    value = (env.get(GROQ_KEY_NAME) or "").strip()
    if value:
        return value
    return read_env_file(env_file, GROQ_KEY_NAME)


def find_converter(path: str = AFCONVERT):
    """afconvert, or None. Absence is a caveat and not a refusal: a WAV that
    is already small enough can go up as it is."""
    return path if os.path.isfile(path) and os.access(path, os.X_OK) else None


def grade_caveat(model: str) -> str:
    """The one sentence about decoder strength, written once.

    Both backends ask it and both must get the same answer, so `base` and
    `whisper-large-v3` cannot end up graded by two different paragraphs. The
    hosted ids carry a `whisper-` prefix that the cached filenames do not; the
    prefix is a naming convention, not a different model.
    """
    name = model[len("whisper-"):] if model.startswith("whisper-") else model
    if name in REFERENCE_GRADE:
        return ""
    return (
        f"{model!r} is not the reference decoder §11 asked for (large-v3 or "
        "Parakeet-TDT-v3). Whether it is strong enough is not settled by "
        "argument: the control arm decides it, and the run reports CANNOT "
        "DECIDE if it fails there")


def _plan(backend, available, why_not="", caveat="", **extra) -> dict:
    """Every plan has the same keys whichever backend answered, so a caller
    can print one report and a test can compare two backends without knowing
    which shape it got."""
    plan = {
        "backend": backend, "available": available, "why_not": why_not,
        "caveat": caveat, "interpreter": None, "model": None, "cached": [],
        "endpoint": None, "converter": None, "have_key": None,
    }
    plan.update(extra)
    return plan


def hosted_availability(model=HOSTED_DEFAULT_MODEL, have_key=_LOOK_IT_UP,
                        converter=_LOOK_IT_UP, endpoint=GROQ_TRANSCRIBE_URL) -> dict:
    """Can the hosted decoder be reached, and with what caveat.

    `have_key` is a BOOL, never the key. A plan dict gets printed, logged, and
    put in tracebacks; a secret that travels in one will eventually be read by
    somebody it was not meant for, and the only reliable defence is for it
    never to be in there in the first place.

    Not answered here: whether the network is up, whether the account has
    credit, and whether the endpoint returns 200. Those are facts about the
    world at the moment of the call, they cannot be established without making
    it, and a `--check` that quietly spends a request to answer them is a
    `--check` nobody can run twice. They surface as honest refusals at decode
    time instead.
    """
    if have_key is _LOOK_IT_UP:
        have_key = groq_api_key() is not None
    have_key = bool(have_key)
    if converter is _LOOK_IT_UP:
        converter = find_converter()
    base = {"model": model, "endpoint": endpoint, "converter": converter,
            "have_key": have_key}
    if model not in HOSTED_MODELS:
        return _plan(BACKEND_HOSTED, False, why_not=(
            f"{model!r} is not a model this endpoint serves (it serves: "
            f"{', '.join(sorted(HOSTED_MODELS))}). Pass --model with one of "
            "those, or --backend local if you meant the whisper on this "
            "machine — the cached weights there are named without the "
            "`whisper-` prefix"), **base)
    if not have_key:
        return _plan(BACKEND_HOSTED, False, why_not=(
            f"no {GROQ_KEY_NAME} in the environment and none in "
            f"{ENV_LOCAL} (that file is gitignored and is where it belongs). "
            "Without a credential the hosted decoder cannot be asked "
            "anything, and a run that reports a reference transcript it never "
            "obtained is worse than a run that reports nothing"), **base)
    caveat = grade_caveat(model)
    online = (
        "this decode goes over the network: the WAV is uploaded to "
        f"{endpoint} and the transcript comes back from a model version "
        "nobody here can pin to a sha256. The provenance line stamps "
        f"engine={BACKEND_HOSTED}:{model} so the reader can tell it from an "
        "offline decode, which is the whole reason that field exists")
    if converter is None:
        online += (
            f". {AFCONVERT} is missing, so the WAV goes up as it was "
            f"recorded — 32-bit float at 48 kHz is {HOSTED_MAX_BYTES // (1 << 20)} MB "
            "in about two minutes and the upload will be refused on size "
            "rather than converted")
    return _plan(BACKEND_HOSTED, True,
                 caveat=(caveat + ". " + online) if caveat else online, **base)


def availability(interpreter, cached, model="base", allow_download=False,
                 backend=BACKEND_LOCAL, have_key=_LOOK_IT_UP,
                 converter=_LOOK_IT_UP) -> dict:
    """Can this machine produce a reference transcript, and with what caveat.

    Returns `available`, `why_not` when it is not, and `caveat` when it is but
    the decoder is below the grade §11 named. The caveat is not a warning to be
    dismissed: it is the reason the control arm exists.

    `backend` defaults to the local one so that every existing caller keeps the
    answer it always got. The hosted decoder is never reached for by accident:
    somebody has to name it, here or on the command line.
    """
    if backend == BACKEND_HOSTED:
        return hosted_availability(model, have_key, converter)
    if backend != BACKEND_LOCAL:
        raise ValueError(f"unknown backend {backend!r}; known: {list(BACKENDS)}")
    if interpreter is None:
        return {
            "backend": BACKEND_LOCAL, "endpoint": None, "converter": None,
            "have_key": None,
            "available": False, "interpreter": None, "model": model,
            "cached": list(cached), "caveat": "",
            "why_not": (
                "no python on this machine imports `whisper`. Install "
                "openai-whisper into any interpreter and point "
                "$ANTICIPY_WHISPER_PYTHON at it, or plug a different decoder "
                "in here — the scorer takes a transcript file and does not "
                f"care what wrote it. `--backend {BACKEND_HOSTED}` is the one "
                "already plugged in: large-v3 over the network, at the cost of "
                "the run no longer being offline"),
        }
    if model not in cached and not allow_download:
        return {
            "backend": BACKEND_LOCAL, "endpoint": None, "converter": None,
            "have_key": None,
            "available": False, "interpreter": interpreter, "model": model,
            "cached": list(cached), "caveat": "",
            "why_not": (
                f"the weights for {model!r} are not cached (present: "
                f"{', '.join(cached) or 'none'}). whisper would fetch them from "
                "the network, which turns an offline experiment into an online "
                "one without anybody saying so. Pass --allow-download if that "
                "is what you meant"),
        }
    return {"backend": BACKEND_LOCAL, "endpoint": None, "converter": None,
            "have_key": None,
            "available": True, "interpreter": interpreter, "model": model,
            "cached": list(cached), "caveat": grade_caveat(model),
            "why_not": ""}


def whisper_command(interpreter, wav, out_dir, model="base") -> list[str]:
    """The exact argv, built in one place so the run is reproducible.

    `--temperature 0` because a measuring stick that returns a different number
    on the second run is not a measuring stick.

    `--condition_on_previous_text False` because whisper's decoder, conditioned
    on what it just emitted, loops on long silences and emits the same phrase
    over and over. This experiment is specifically about audio with a lot of
    silence in it, and a looping reference decoder would post a huge insertion
    rate that reads as noise rather than as the artefact it is.
    """
    return [
        interpreter, "-m", "whisper", wav,
        "--model", model,
        "--language", "en",
        "--task", "transcribe",
        "--temperature", "0",
        "--condition_on_previous_text", "False",
        "--fp16", "False",
        "--output_format", "txt",
        "--output_dir", out_dir,
        "--verbose", "False",
    ]


def afconvert_command(converter, src, dest) -> list[str]:
    """16 kHz mono signed 16-bit little-endian PCM WAV, best resampler.

    In one place, like whisper_command and for the same reason: the exact argv
    is part of what "this transcript came from this recording" means, and an
    argv assembled at the call site is an argv nobody can check.
    """
    return [converter, "-f", "WAVE", "-d", "LEI16@16000", "-c", "1",
            "--src-quality", "127", src, dest]


def convert_for_upload(wav: str, dest: str, converter: str,
                       runner=None) -> str:
    """Downconvert, or refuse and say what afconvert said.

    The digest is NOT taken here and must never be. `wav_digest` names the
    RECORDING; this file is a transport artefact that exists for the length of
    one upload, and hashing it would make two cells that decoded the same
    recording disagree about which recording it was.
    """
    # Resolved at CALL time, never bound at def time: a default of
    # `subprocess.run` captures the original function object, and a test that
    # monkeypatches reference_decode.subprocess.run then silently drives the
    # real one. tests/test_engine_or_audio.py does exactly that.
    runner = runner or subprocess.run
    result = runner(afconvert_command(converter, wav, dest),
                    capture_output=True)
    if result.returncode != 0:
        detail = (getattr(result, "stderr", b"") or b"")
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace")
        raise RuntimeError(
            f"{converter} could not convert {os.path.basename(wav)} to 16 kHz "
            f"mono 16-bit WAV (exit {result.returncode}): "
            f"{detail.strip() or 'no output'}. The original was NOT uploaded: "
            "a decode of a file nobody could convert is a decode of an unknown "
            "file")
    if not os.path.isfile(dest) or os.path.getsize(dest) == 0:
        raise RuntimeError(
            f"{converter} exited 0 but wrote nothing to {dest}. Refusing to "
            "upload rather than guessing which file it meant")
    return dest


def multipart_body(fields: dict, filename: str, payload: bytes,
                   boundary=None, field_name="file"):
    """A multipart/form-data body, built with the standard library.

    `requests` would be four lines shorter and one dependency heavier, and the
    scorer's contract is standard library only — the whole point of this half
    of the tree is that a machine with nothing installed can still run it.

    Returns (body, content_type). A boundary that occurs inside the payload
    would split the upload in the wrong place and the server would decode
    whatever fell before it, which is exactly the kind of quiet truncation this
    module exists to refuse; a uuid4 hex makes that ~0, and it is checked
    anyway because ~0 is not 0.
    """
    boundary = boundary or ("anticipy" + uuid.uuid4().hex)
    marker = ("--" + boundary).encode("ascii")
    if marker in payload:
        raise RuntimeError(
            "the multipart boundary occurs inside the audio payload; the "
            "upload would be truncated at that byte. Retry — the boundary is "
            "random")
    out = bytearray()
    for key, value in fields.items():
        out += marker + b"\r\n"
        out += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
        out += str(value).encode("utf-8") + b"\r\n"
    out += marker + b"\r\n"
    out += (f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{filename}"\r\n').encode()
    out += b"Content-Type: audio/wav\r\n\r\n"
    out += payload + b"\r\n"
    out += marker + b"--\r\n"
    return bytes(out), "multipart/form-data; boundary=" + boundary


def hosted_transcribe(payload: bytes, filename: str, model: str, api_key: str,
                      endpoint: str = GROQ_TRANSCRIBE_URL,
                      opener=None, timeout: int = HOSTED_TIMEOUT_S) -> str:
    """One upload, one transcript, or one sentence saying why not.

    `temperature=0` for the same reason whisper_command sets it: a measuring
    stick that returns a different number on the second run is not a measuring
    stick. `language=en` because the script is English and letting the model
    decide invites a transcript in another alphabet scoring 0% capture.

    `response_format=json` — the plain `text` format returns a bare body, and a
    bare body cannot be told apart from an error page that happened to arrive
    with a 200. JSON either has a `text` key or it does not.

    `opener` is injectable so the tests can drive every branch of this without
    a socket. It is NOT a mock of the module's own logic: it stands exactly
    where urlopen stands, and everything below the seam is the real code.
    """
    opener = opener or urllib.request.urlopen
    fields = {"model": model, "language": "en", "temperature": "0",
              "response_format": "json"}
    body, content_type = multipart_body(fields, filename, payload)
    request = urllib.request.Request(endpoint, data=body, method="POST")
    request.add_header("Content-Type", content_type)
    request.add_header("Content-Length", str(len(body)))
    request.add_header("Accept", "application/json")
    # See HOSTED_USER_AGENT. Without this the edge answers 403 before Groq
    # ever sees the request, and the 403 reads exactly like a bad key.
    request.add_header("User-Agent", HOSTED_USER_AGENT)
    # The only place the key is used. It is not logged, not echoed into an
    # exception, and not put in the plan dict.
    request.add_header("Authorization", "Bearer " + api_key)
    try:
        with opener(request, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = (exc.read() or b"").decode("utf-8", "replace")[:600]
        except Exception:  # noqa: BLE001 - a body we cannot read is not fatal
            detail = ""
        if exc.code == 429:
            retry = ""
            try:
                after = exc.headers.get("retry-after")
                retry = f" (retry-after: {after})" if after else ""
            except Exception:  # noqa: BLE001
                retry = ""
            raise RuntimeError(
                f"{endpoint} rate-limited this decode (HTTP 429){retry}. "
                "Nothing was transcribed. Wait and run it again — a reference "
                f"transcript is not something to half-obtain: {detail}") from exc
        if exc.code in (401, 403):
            raise RuntimeError(
                f"{endpoint} refused this request (HTTP {exc.code}) and "
                "nothing was transcribed. Two different causes look identical "
                f"here: (a) the {GROQ_KEY_NAME} in the environment or "
                f"{ENV_LOCAL} is absent, expired, or not entitled to "
                f"{model!r}; (b) the Cloudflare edge in front of the endpoint "
                "rejected the client before Groq saw it — a body naming "
                "`error code: 1010` is that one, and it means HOSTED_USER_AGENT "
                f"is not being sent. Body: {detail}") from exc
        raise RuntimeError(
            f"{endpoint} returned HTTP {exc.code} and no transcript: "
            f"{detail or 'no body'}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"{endpoint} could not be reached ({exc.reason}). The hosted "
            "decoder needs the network by definition; if this machine is "
            "offline, that is not a decode that can be retried into "
            "existence") from exc
    if status is not None and int(status) != 200:
        raise RuntimeError(
            f"{endpoint} answered {status} rather than 200 and no transcript "
            "was written")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError(
            f"{endpoint} answered 200 with a body that is not JSON, so there "
            "is no way to tell a transcript from an error page: "
            f"{raw[:300]!r}") from exc
    if not isinstance(parsed, dict) or "text" not in parsed:
        raise RuntimeError(
            f"{endpoint} answered 200 with JSON that has no `text` key "
            f"({sorted(parsed) if isinstance(parsed, dict) else type(parsed).__name__}). "
            "An absent transcript is reported as absent, never as an empty one")
    text = parsed["text"]
    if not isinstance(text, str):
        raise RuntimeError(
            f"{endpoint} answered 200 with a `text` that is a "
            f"{type(text).__name__}, not a string")
    return text


def guard_decode_text(text: str, wav: str, engine: str, warn=None) -> str:
    """Refuse a transcript that is the SHAPE of a failed decode.

    proof/engine_or_audio.py:169-191 settled this: "you" and "Thank you." are
    whisper's canonical output on silence or a failed decode, and a one-word
    transcript scored capture 0.0027 with script share 1.00 and fired R1 off a
    dead file. Zero tokens and one token are the same event, and `if not text:`
    catches only the first.

    It counts tokens; it does not read them. There is no word list here and
    there must never be one — a transcript that genuinely says two words is
    written out verbatim, and what a transcript MEANS is the scorer's question
    (HARNESS-LAWS.md, Law 1).

    Below MIN_TRANSCRIPT_WORDS the scorer will refuse the cell anyway. That is
    a WARNING, not a refusal, because the scorer's floor is about a 370-word
    script and this function is also used on short probes.
    """
    warn = warn or (lambda message: print(message, file=sys.stderr))
    words = tokens(text)
    if len(words) < MIN_DECODE_WORDS:
        raise RuntimeError(
            f"{engine} returned {len(words)} word(s) for "
            f"{os.path.basename(wav)} ({text.strip()!r}). That is the shape of "
            "a failed decode, not a decode: see the comment block at "
            "proof/engine_or_audio.py:169-191, where a one-word transcript "
            "scored script share 1.00 and fired a conclusion off a dead file. "
            "Nothing was written. Check that the WAV actually contains speech")
    if len(words) < MIN_TRANSCRIPT_WORDS:
        warn(f"WARNING     : {engine} returned {len(words)} words, below the "
             f"scorer's MIN_TRANSCRIPT_WORDS ({MIN_TRANSCRIPT_WORDS}). The "
             "transcript is written verbatim, and proof/engine_or_audio.py "
             "will refuse to score it — a proportion over that few words is "
             "noise with a decimal point")
    return text


def wav_digest(wav: str) -> str:
    """sha256 of the WAV, so two cells cannot silently name one recording.

    A filename is exactly the thing a tired human gets wrong at eleven at
    night, and arm A's transcript filed under arm B reverses the answer about
    the audio session line. The hash is what proof/engine_or_audio.py checks.
    """
    h = hashlib.sha256()
    with open(wav, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def engine_name(backend: str, model: str) -> str:
    """`whisper-hosted:whisper-large-v3` — what actually decoded this file.

    One token, no spaces, because the provenance line is whitespace-split.
    """
    return f"{backend}:{model}"


def provenance_line(wav: str, arm: str, decoder: str = "reference",
                    engine: str = "") -> str:
    """The line proof/engine_or_audio.py's output contract asks for.

    The scratch recorder that has to write this for the on-device cells does
    not exist yet. This side of the contract does, so it honours it today —
    and a run where the reference cells carry provenance and the phone's cells
    do not is a run where the harness can still tell arm A's WAV from arm C's.

    `decoder=` stays the CELL's name — `reference`, one of the four keys in
    proof/engine_or_audio.py's DECODERS — because the scorer compares it
    against the manifest and refuses the cell when they differ. `engine=` is
    the new field and it names the backend that actually spoke. The two are not
    the same question: `reference` says which column of the experiment this is,
    `engine` says whether the column was filled offline by a 74M model on this
    disk or online by large-v3 on somebody's GPU. R1 and R2 subtract this cell
    from the app's, so a reader who cannot tell those apart cannot read the
    result.

    `engine` is deliberately NOT in the scorer's PROVENANCE_KEYS: parse_provenance
    keeps the four keys it knows and drops the rest, and strip_provenance takes
    the whole line off before tokenising. So this field is carried for the human
    and for `git diff`, and it cannot be charged to the decoder as a
    hallucinated word.
    """
    tail = f" engine={engine}" if engine else ""
    return (f"{PROVENANCE_PREFIX} arm={arm} decoder={decoder} "
            f"wav={os.path.basename(wav)} sha256={wav_digest(wav)}{tail}\n")


def arm_of(out_path: str) -> str:
    """Which arm this transcript is being written for, from the path the
    protocol tells the operator to write to (`<run>/arm_a/reference.txt`).
    Guessing is not good enough here: a wrong guess would stamp a provenance
    line that itself lies, so an unrecognised path gets no line at all."""
    parent = os.path.basename(os.path.dirname(os.path.abspath(out_path)))
    if parent.startswith("arm_") and len(parent) == 5:
        return parent[4].upper()
    return ""


def resolve_backend(name: str) -> str:
    """`local`, `hosted`, `groq` and the full names all land on one of two
    strings. Anything else is refused by name rather than defaulted, because a
    typo that silently picks a backend picks the reference decoder for the
    whole experiment."""
    try:
        return BACKEND_ALIASES[str(name).strip().lower()]
    except KeyError:
        raise ValueError(
            f"unknown backend {name!r}; known: {sorted(set(BACKEND_ALIASES))}"
        ) from None


def default_model(backend: str) -> str:
    """`base` locally — it is what the cache holds — and large-v3 hosted, which
    is what §11 asked for and what the endpoint serves."""
    return HOSTED_DEFAULT_MODEL if backend == BACKEND_HOSTED else "base"


def auto_backend(local_plan: dict, hosted_plan: dict):
    """Local first, always. Hosted is the fallback, never the preference.

    Offline beats online for a reference decode on three counts that are not
    close: the weights are a file with a sha256 on this disk rather than a
    version string on someone's server, the run stays offline as the protocol
    assumes, and nothing about it can be rate-limited halfway through a night's
    recordings. `auto` exists so a machine that has neither gets ONE report
    naming both gaps instead of a single misleading refusal — it returns None
    in that case rather than nominating a backend that cannot run.
    """
    if local_plan.get("available"):
        return BACKEND_LOCAL
    if hosted_plan.get("available"):
        return BACKEND_HOSTED
    return None


def _decode_local(wav, out_path, model, plan, runner=None):
    """Run whisper and read back what it wrote. Returns (text, produced_path).

    `runner` is injectable only so the file handling around it can be pinned on
    a machine that has no whisper to run — which is every machine this repo is
    currently on.

    It no longer moves whisper's output onto `out_path`, and that is the whole
    point of the change: the guard runs on the shared tail, and a path that had
    already renamed the file would leave a one-word transcript sitting at
    `reference.txt` for a later reader to score. So whisper's file stays under
    its own name until the transcript has been accepted; on the failing path it
    stays put as the evidence of what came back, and out_path is never created.

    The one collision — a WAV named `reference.wav` beside a `reference.txt`,
    where whisper writes straight onto the target — is stepped aside rather
    than special-cased downstream.
    """
    runner = runner or subprocess.run  # see convert_for_upload
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    cmd = whisper_command(plan["interpreter"], wav, out_dir, model)
    runner(cmd, check=True)
    produced = os.path.join(
        out_dir, os.path.splitext(os.path.basename(wav))[0] + ".txt")
    if os.path.abspath(produced) == os.path.abspath(out_path):
        produced += ".whisper-raw"
        os.replace(out_path, produced)
    with open(produced, encoding="utf-8") as fh:
        return fh.read(), produced


def _decode_hosted(wav, model, plan, opener=None, api_key=None,
                   runner=None) -> str:
    """Convert if we can, refuse if it is too big, upload, return the text."""
    api_key = api_key or groq_api_key()
    if not api_key:
        raise RuntimeError(
            f"no {GROQ_KEY_NAME} available at decode time. Nothing was "
            "uploaded and nothing was written")
    converter = plan.get("converter")
    endpoint = plan.get("endpoint") or GROQ_TRANSCRIBE_URL
    scratch = None
    try:
        if converter:
            scratch = tempfile.mkdtemp(prefix="anticipy-ref-")
            upload_path = convert_for_upload(
                wav, os.path.join(scratch, "upload.wav"), converter, runner)
            filename = os.path.splitext(os.path.basename(wav))[0] + ".wav"
        else:
            upload_path = wav
            filename = os.path.basename(wav)
            extension = os.path.splitext(filename)[1].lstrip(".").lower()
            if extension not in HOSTED_FORMATS:
                raise RuntimeError(
                    f"{filename} is a .{extension or '(no extension)'} and the "
                    f"endpoint accepts {', '.join(HOSTED_FORMATS)}. "
                    f"{AFCONVERT} is missing, so it cannot be converted here")
        size = os.path.getsize(upload_path)
        if size > HOSTED_MAX_BYTES:
            raise RuntimeError(
                f"{os.path.basename(upload_path)} is "
                f"{size / (1 << 20):.1f} MB after conversion and the free tier "
                f"accepts {HOSTED_MAX_BYTES // (1 << 20)} MB (dev tier: "
                f"{HOSTED_MAX_BYTES_DEV // (1 << 20)} MB). Split the recording "
                "at a sentence boundary and decode the halves, or upgrade the "
                "account — do NOT truncate it, because a reference transcript "
                "of the first half of a page scores the second half as words "
                "the microphone lost")
        with open(upload_path, "rb") as fh:
            payload = fh.read()
        return hosted_transcribe(payload, filename, model, api_key, endpoint,
                                 opener=opener)
    finally:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)


def decode(wav: str, out_path: str, model=None, allow_download=False,
           backend=BACKEND_LOCAL, opener=None, plan=None, warn=None,
           runner=None) -> str:
    """Decode one WAV into one transcript, through the named backend.

    `backend` defaults to the local decoder, so every caller that predates the
    hosted one keeps the behaviour it had. Whichever runs, the transcript is
    guarded against the failed-decode shape before it is written, and the
    provenance line names the engine that produced it.
    """
    backend = resolve_backend(backend)
    model = model or default_model(backend)
    if plan is None:
        plan = availability(
            find_interpreter() if backend == BACKEND_LOCAL else None,
            cached_models() if backend == BACKEND_LOCAL else [],
            model, allow_download, backend=backend)
    if not plan["available"]:
        raise RuntimeError(plan["why_not"])
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    os.makedirs(out_dir, exist_ok=True)
    produced = None
    if backend == BACKEND_HOSTED:
        text = _decode_hosted(wav, model, plan, opener=opener, runner=runner)
    else:
        text, produced = _decode_local(wav, out_path, model, plan, runner=runner)
    engine = engine_name(backend, model)
    # Guarded BEFORE the write, so a failed decode leaves NO file at out_path
    # that a later reader could mistake for a result. On the local path
    # whisper's own output survives under its own name, so the evidence of what
    # came back is not deleted either — see _decode_local.
    guard_decode_text(text, wav, engine, warn=warn)
    arm = arm_of(out_path)
    header = provenance_line(wav, arm, engine=engine) if arm else ""
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(header + text)
    if produced and os.path.abspath(produced) != os.path.abspath(out_path):
        # Only once the transcript is accepted and written. A stray
        # `arm_a.txt` beside `reference.txt` is a second file naming the same
        # cell, which is the manifest ambiguity the provenance line exists to
        # remove.
        os.remove(produced)
    return text


def report(plan: dict, out=None) -> None:
    """One backend's answer, printed the same way whichever backend it is."""
    out = out or sys.stdout
    def line(label, value):
        print(f"  {label:<11} : {value}", file=out)
    print(f"[{plan['backend']}]", file=out)
    if plan["backend"] == BACKEND_LOCAL:
        line("interpreter", plan["interpreter"] or "-- none found --")
        line("cached", ", ".join(plan["cached"]) or "none")
    else:
        line("endpoint", plan["endpoint"])
        line("converter", plan["converter"] or "-- missing --")
        # The presence of the key, never the key.
        line("api key", f"{GROQ_KEY_NAME} "
                        f"{'present' if plan['have_key'] else 'absent'}")
    line("model", plan["model"])
    line("available", plan["available"])
    if plan["why_not"]:
        line("why not", plan["why_not"])
    if plan["caveat"]:
        line("CAVEAT", plan["caveat"])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="report what this machine can decode with, and exit")
    ap.add_argument("--wav")
    ap.add_argument("--out")
    ap.add_argument("--model", default=None,
                    help="whisper weights (local) or a Groq model id (hosted); "
                         "defaults per backend")
    ap.add_argument("--backend", default="auto",
                    help="local | hosted | auto (default: auto — local is "
                         "asked first and hosted is the fallback)")
    ap.add_argument("--allow-download", action="store_true",
                    help="permit whisper to fetch weights over the network")
    args = ap.parse_args(argv)

    wanted = str(args.backend).strip().lower()
    if wanted != "auto":
        try:
            chosen = resolve_backend(wanted)
        except ValueError as exc:
            ap.error(str(exc))
        plans = {chosen: availability(
            find_interpreter() if chosen == BACKEND_LOCAL else None,
            cached_models() if chosen == BACKEND_LOCAL else [],
            args.model or default_model(chosen), args.allow_download,
            backend=chosen)}
    else:
        # BOTH reports, always. The failure this replaces is a machine that
        # printed `available: False` for four days while a decoder it could
        # have used sat one flag away, unmentioned.
        plans = {
            BACKEND_LOCAL: availability(
                find_interpreter(), cached_models(),
                args.model or "base", args.allow_download),
            BACKEND_HOSTED: availability(
                None, [], args.model or HOSTED_DEFAULT_MODEL,
                backend=BACKEND_HOSTED),
        }
        chosen = auto_backend(plans[BACKEND_LOCAL], plans[BACKEND_HOSTED])

    for plan in plans.values():
        report(plan)
    if chosen is None:
        print("chosen      : -- none: neither backend can decode, see above --")
        return 1
    print(f"chosen      : {chosen} "
          f"({'named' if wanted != 'auto' else 'auto: local asked first'})")
    plan = plans[chosen]
    if not plan["available"]:
        return 1

    if args.check or not args.wav:
        return 0
    if not args.out:
        ap.error("--wav needs --out")
    print(decode(args.wav, args.out, plan["model"], args.allow_download,
                 backend=chosen, plan=plan))
    return 0


if __name__ == "__main__":
    sys.exit(main())
