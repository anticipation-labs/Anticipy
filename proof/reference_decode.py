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
"""
from __future__ import annotations

import os as _os
import sys as _sys

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))

import argparse
import hashlib
import os
import subprocess
import sys

# The scorer strips this line before scoring and checks what it says against
# the cell it was filed under. Imported rather than restated so the two files
# cannot drift into two different contracts.
from proof.engine_or_audio import PROVENANCE_PREFIX  # noqa: E402

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


def availability(interpreter, cached, model="base", allow_download=False) -> dict:
    """Can this machine produce a reference transcript, and with what caveat.

    Returns `available`, `why_not` when it is not, and `caveat` when it is but
    the decoder is below the grade §11 named. The caveat is not a warning to be
    dismissed: it is the reason the control arm exists.
    """
    if interpreter is None:
        return {
            "available": False, "interpreter": None, "model": model,
            "cached": list(cached), "caveat": "",
            "why_not": (
                "no python on this machine imports `whisper`. Install "
                "openai-whisper into any interpreter and point "
                "$ANTICIPY_WHISPER_PYTHON at it, or plug a different decoder "
                "in here — the scorer takes a transcript file and does not "
                "care what wrote it"),
        }
    if model not in cached and not allow_download:
        return {
            "available": False, "interpreter": interpreter, "model": model,
            "cached": list(cached), "caveat": "",
            "why_not": (
                f"the weights for {model!r} are not cached (present: "
                f"{', '.join(cached) or 'none'}). whisper would fetch them from "
                "the network, which turns an offline experiment into an online "
                "one without anybody saying so. Pass --allow-download if that "
                "is what you meant"),
        }
    caveat = ""
    if model not in REFERENCE_GRADE:
        caveat = (
            f"{model!r} is not the reference decoder §11 asked for (large-v3 or "
            "Parakeet-TDT-v3). Whether it is strong enough is not settled by "
            "argument: the control arm decides it, and the run reports CANNOT "
            "DECIDE if it fails there")
    return {"available": True, "interpreter": interpreter, "model": model,
            "cached": list(cached), "caveat": caveat, "why_not": ""}


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


def provenance_line(wav: str, arm: str, decoder: str = "reference") -> str:
    """The line proof/engine_or_audio.py's output contract asks for.

    The scratch recorder that has to write this for the on-device cells does
    not exist yet. This side of the contract does, so it honours it today —
    and a run where the reference cells carry provenance and the phone's cells
    do not is a run where the harness can still tell arm A's WAV from arm C's.
    """
    return (f"{PROVENANCE_PREFIX} arm={arm} decoder={decoder} "
            f"wav={os.path.basename(wav)} sha256={wav_digest(wav)}\n")


def arm_of(out_path: str) -> str:
    """Which arm this transcript is being written for, from the path the
    protocol tells the operator to write to (`<run>/arm_a/reference.txt`).
    Guessing is not good enough here: a wrong guess would stamp a provenance
    line that itself lies, so an unrecognised path gets no line at all."""
    parent = os.path.basename(os.path.dirname(os.path.abspath(out_path)))
    if parent.startswith("arm_") and len(parent) == 5:
        return parent[4].upper()
    return ""


def decode(wav: str, out_path: str, model="base", allow_download=False) -> str:
    plan = availability(find_interpreter(), cached_models(), model, allow_download)
    if not plan["available"]:
        raise RuntimeError(plan["why_not"])
    out_dir = os.path.dirname(os.path.abspath(out_path)) or "."
    os.makedirs(out_dir, exist_ok=True)
    cmd = whisper_command(plan["interpreter"], wav, out_dir, model)
    subprocess.run(cmd, check=True)
    produced = os.path.join(
        out_dir, os.path.splitext(os.path.basename(wav))[0] + ".txt")
    if produced != os.path.abspath(out_path):
        os.replace(produced, out_path)
    with open(out_path, encoding="utf-8") as fh:
        text = fh.read()
    arm = arm_of(out_path)
    if arm:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(provenance_line(wav, arm) + text)
    return text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="report what this machine can decode with, and exit")
    ap.add_argument("--wav")
    ap.add_argument("--out")
    ap.add_argument("--model", default="base")
    ap.add_argument("--allow-download", action="store_true",
                    help="permit whisper to fetch weights over the network")
    args = ap.parse_args(argv)

    plan = availability(find_interpreter(), cached_models(), args.model,
                        args.allow_download)
    print(f"interpreter : {plan['interpreter'] or '-- none found --'}")
    print(f"model       : {plan['model']}")
    print(f"cached      : {', '.join(plan['cached']) or 'none'}")
    print(f"available   : {plan['available']}")
    if plan["why_not"]:
        print(f"why not     : {plan['why_not']}")
    if plan["caveat"]:
        print(f"CAVEAT      : {plan['caveat']}")

    if args.check or not args.wav:
        return 0 if plan["available"] else 1
    if not args.out:
        ap.error("--wav needs --out")
    print(decode(args.wav, args.out, args.model, args.allow_download))
    return 0


if __name__ == "__main__":
    sys.exit(main())
