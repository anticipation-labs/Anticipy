"""The decoder adapter has to say what is missing, not guess around it.

The experiment's whole inference — "a strong decoder loses the same words, so
the microphone is starved" — collapses if the decoder that produced the number
was weak, or if it quietly went to the network for weights while somebody
believed the run was offline. These drive the pure half: no whisper is invoked,
no subprocess is spawned, and the suite passes identically on a machine with no
decoder installed at all.
"""
import email.message
import io
import json
import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proof.reference_decode import (  # noqa: E402
    BACKEND_HOSTED,
    BACKEND_LOCAL,
    ENV_LOCAL,
    GROQ_KEY_NAME,
    GROQ_TRANSCRIBE_URL,
    HOSTED_DEFAULT_MODEL,
    HOSTED_USER_AGENT,
    MIN_DECODE_WORDS,
    REFERENCE_GRADE,
    afconvert_command,
    auto_backend,
    availability,
    cached_models,
    convert_for_upload,
    decode,
    default_model,
    engine_name,
    find_converter,
    find_interpreter,
    grade_caveat,
    groq_api_key,
    guard_decode_text,
    hosted_availability,
    hosted_transcribe,
    multipart_body,
    provenance_line,
    read_env_file,
    resolve_backend,
    wav_digest,
    whisper_command,
)


def test_no_decoder_anywhere_is_a_named_gap_not_a_crash():
    """The brief calls this a legitimate outcome. It has to arrive as a
    sentence somebody can act on, not as an ImportError three frames deep."""
    plan = availability(None, [], "large-v3")
    assert plan["available"] is False
    assert "whisper" in plan["why_not"]
    assert "$ANTICIPY_WHISPER_PYTHON" in plan["why_not"]
    assert "does not care what wrote it" in plan["why_not"], (
        "the gap is pluggable, and the message has to say so")


def test_uncached_weights_are_refused_rather_than_fetched():
    # whisper reaches for the network on a cache miss. On a machine with no
    # network that is a long opaque hang; on one with network it silently makes
    # an offline experiment online. Either way the operator should have said so.
    plan = availability("/usr/bin/python3", ["base"], "large-v3")
    assert plan["available"] is False
    assert "not cached" in plan["why_not"]
    assert "base" in plan["why_not"], "and it should say what IS on disk"
    assert "--allow-download" in plan["why_not"]


def test_saying_allow_download_out_loud_unblocks_it():
    plan = availability("/usr/bin/python3", ["base"], "large-v3",
                        allow_download=True)
    assert plan["available"] is True


def test_a_small_model_runs_but_carries_the_caveat_that_it_is_not_the_one_asked_for():
    """This is the honest half. base.pt is what is cached on this machine and
    it is 74M parameters against large-v3's 1550M. It may still clear the
    control arm; it may not. What it must never do is get reported as "a strong
    reference decoder" because it was the one that happened to be installed."""
    plan = availability("/usr/bin/python3", ["base"], "base")
    assert plan["available"] is True
    assert "large-v3" in plan["caveat"]
    assert "control arm" in plan["caveat"]
    assert "CANNOT DECIDE" in plan["caveat"]


def test_the_decoder_the_experiment_was_designed_around_carries_no_caveat():
    plan = availability("/usr/bin/python3", ["large-v3"], "large-v3")
    assert plan["available"] is True
    assert plan["caveat"] == ""
    assert "large-v3" in REFERENCE_GRADE


def test_cached_models_reads_the_disk_and_survives_there_being_no_disk():
    assert cached_models("/nonexistent/whisper/cache") == []


def test_cached_models_names_the_weights_it_finds(tmp_path):
    (tmp_path / "base.pt").write_text("")
    (tmp_path / "large-v3.pt").write_text("")
    (tmp_path / "README.md").write_text("not weights")
    assert cached_models(str(tmp_path)) == ["base", "large-v3"]


def test_the_command_is_deterministic_and_says_so_in_its_flags():
    """A measuring stick that returns a different number on the second run is
    not a measuring stick. Temperature zero is not an optimisation here."""
    cmd = whisper_command("/usr/bin/python3", "a.wav", "/out", "base")
    assert cmd[cmd.index("--temperature") + 1] == "0"


def test_the_command_turns_off_the_setting_that_makes_whisper_loop_on_silence():
    # This experiment is specifically about audio with long silences in it, and
    # a looping decoder posts an insertion rate that reads as a finding.
    cmd = whisper_command("/usr/bin/python3", "a.wav", "/out", "base")
    assert cmd[cmd.index("--condition_on_previous_text") + 1] == "False"


def test_the_interpreter_search_prefers_the_one_the_operator_named(monkeypatch):
    monkeypatch.setenv("ANTICIPY_WHISPER_PYTHON", "/opt/mine/python3")
    seen = []

    def probe(path):
        seen.append(path)
        return True

    assert find_interpreter(("/usr/bin/python3",), probe) == "/opt/mine/python3"
    assert seen == ["/opt/mine/python3"], (
        "an operator who named an interpreter should not be silently overridden "
        "by one that happens to sort earlier")


def test_the_interpreter_search_walks_past_pythons_without_whisper(monkeypatch):
    monkeypatch.delenv("ANTICIPY_WHISPER_PYTHON", raising=False)
    assert find_interpreter(("/a", "/b", "/c"), lambda p: p == "/c") == "/c"


def test_no_interpreter_at_all_returns_none_rather_than_a_hopeful_guess(monkeypatch):
    monkeypatch.delenv("ANTICIPY_WHISPER_PYTHON", raising=False)
    assert find_interpreter(("/a", "/b"), lambda p: False) is None


# ===========================================================================
# THE SECOND BACKEND (2026-09-06)
#
# The first one never ran: no python on this Mac imports whisper, there is no
# Homebrew and torch is not installed, so `--check` printed available: False
# and the 1,400-line scorer behind it had scored nothing. These drive the
# hosted path, and they drive it WITHOUT A SOCKET — the seam is `opener`,
# which stands exactly where urllib.request.urlopen stands. Everything below
# that seam is the real code: the real multipart body, the real headers, the
# real refusals. A suite that mocked `hosted_transcribe` would be testing that
# the test can return a string.
# ===========================================================================


class _FakeResponse:
    """What urlopen hands back: a context manager with .status and .read()."""

    def __init__(self, body, status=200):
        self._body, self.status = body, status

    def read(self):
        return self._body

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _opener(body=b'{"text": "hello there"}', status=200, seen=None):
    def opener(request, timeout=None):
        if seen is not None:
            seen.append(request)
        return _FakeResponse(body, status)
    return opener


def _http_error(code, body=b"", headers=None):
    hdrs = email.message.Message()
    for key, value in (headers or {}).items():
        hdrs[key] = value

    def opener(request, timeout=None):
        raise urllib.error.HTTPError(
            GROQ_TRANSCRIBE_URL, code, "nope", hdrs, io.BytesIO(body))
    return opener


class _Ran:
    """A stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode=0, stderr=b""):
        self.returncode, self.stderr, self.stdout = returncode, stderr, b""


# --- which decoder spoke ---------------------------------------------------


def test_the_hosted_backend_is_never_reached_for_by_accident(monkeypatch):
    """Requirement one, pinned. `availability` with no backend named answers
    about the LOCAL decoder, even on a machine whose key is sitting right
    there. A fallback that selects itself is not a fallback."""
    monkeypatch.setenv(GROQ_KEY_NAME, "sk-not-a-real-key")
    plan = availability(None, [], "base")
    assert plan["backend"] == BACKEND_LOCAL
    assert plan["available"] is False
    assert "whisper" in plan["why_not"]


def test_the_local_refusal_now_names_the_backend_that_could_have_run():
    """The failure being fixed: four days of `available: False` with a working
    decoder one flag away and nothing saying so."""
    plan = availability(None, [], "base")
    assert BACKEND_HOSTED in plan["why_not"]


def test_every_plan_says_which_backend_answered_it():
    """A run where nobody can tell whisper-local from whisper-hosted is a run
    whose reference is unknown, and R1/R2 subtract the reference from the app."""
    assert availability(None, [], "base")["backend"] == BACKEND_LOCAL
    assert availability("/usr/bin/python3", ["base"], "base")["backend"] == BACKEND_LOCAL
    assert hosted_availability(have_key=True)["backend"] == BACKEND_HOSTED


def test_an_unknown_backend_is_refused_by_name_rather_than_defaulted():
    # A typo that silently picks a backend picks the reference decoder for the
    # whole experiment.
    with pytest.raises(ValueError) as caught:
        availability(None, [], "base", backend="whisper-ish")
    assert "whisper-ish" in str(caught.value)
    with pytest.raises(ValueError):
        resolve_backend("wisper-hosted")


def test_the_operator_may_type_the_short_names():
    assert resolve_backend("local") == BACKEND_LOCAL
    assert resolve_backend("hosted") == BACKEND_HOSTED
    assert resolve_backend("groq") == BACKEND_HOSTED
    assert resolve_backend(" HOSTED ") == BACKEND_HOSTED


def test_each_backend_defaults_to_the_model_that_backend_actually_has():
    assert default_model(BACKEND_LOCAL) == "base"
    assert default_model(BACKEND_HOSTED) == HOSTED_DEFAULT_MODEL


def test_auto_asks_the_offline_decoder_first_every_time():
    """Offline beats online for a reference decode: the weights are a file with
    a sha256 on this disk rather than a version string on someone's server."""
    up = {"available": True}
    down = {"available": False}
    assert auto_backend(up, up) == BACKEND_LOCAL
    assert auto_backend(down, up) == BACKEND_HOSTED
    assert auto_backend(up, down) == BACKEND_LOCAL


def test_auto_with_neither_backend_nominates_nothing():
    # Naming a backend that cannot run would print one refusal and hide the
    # other, which is how the first backend's absence went unnoticed.
    assert auto_backend({"available": False}, {"available": False}) is None


# --- grading, across both backends -----------------------------------------


def test_the_hosted_large_v3_is_the_decoder_section_eleven_asked_for():
    """Groq's model id carries a `whisper-` prefix the cached filenames do not.
    A grader that missed that would stamp the CANNOT DECIDE caveat on the exact
    decoder the experiment was designed around."""
    assert grade_caveat("whisper-large-v3") == ""
    assert grade_caveat("large-v3") == ""
    assert "CANNOT DECIDE" in grade_caveat("base")
    assert "CANNOT DECIDE" in grade_caveat("whisper-tiny")


def test_the_hosted_plan_says_out_loud_that_the_run_is_no_longer_offline():
    plan = hosted_availability(have_key=True, converter="/usr/bin/afconvert")
    assert plan["available"] is True
    assert "over the network" in plan["caveat"]
    assert "engine=" in plan["caveat"], (
        "the caveat should name the field a reader uses to tell the two "
        "decoders apart")
    assert "CANNOT DECIDE" not in plan["caveat"]


# --- the credential --------------------------------------------------------


def test_no_key_is_a_refusal_that_names_the_variable_and_the_file():
    plan = hosted_availability(have_key=False)
    assert plan["available"] is False
    assert GROQ_KEY_NAME in plan["why_not"]
    assert ENV_LOCAL in plan["why_not"]


def test_the_key_never_travels_in_the_plan_dict(monkeypatch):
    """A plan gets printed, logged and put in tracebacks. The only reliable
    defence for a secret is for it never to be in there at all — which is why
    availability carries `have_key` as a bool."""
    secret = "gsk-THE-ACTUAL-SECRET-0123456789"
    monkeypatch.setenv(GROQ_KEY_NAME, secret)
    plan = hosted_availability()
    assert plan["have_key"] is True
    assert secret not in json.dumps(plan, default=str)


def test_the_environment_beats_the_dotenv_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env.local"
    env_file.write_text(f"{GROQ_KEY_NAME}=from-the-file\n")
    monkeypatch.setenv(GROQ_KEY_NAME, "from-the-environment")
    assert groq_api_key(env_file=str(env_file)) == "from-the-environment"


def test_the_dotenv_file_is_read_when_the_environment_is_empty(tmp_path, monkeypatch):
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "# a comment\n"
        "OTHER=value\n"
        f'export {GROQ_KEY_NAME}="from-the-file"\n')
    monkeypatch.delenv(GROQ_KEY_NAME, raising=False)
    assert groq_api_key(env_file=str(env_file)) == "from-the-file"


def test_a_missing_dotenv_file_is_none_and_not_a_crash(monkeypatch):
    monkeypatch.delenv(GROQ_KEY_NAME, raising=False)
    assert groq_api_key(env_file="/nonexistent/.env.local") is None
    assert read_env_file("/nonexistent/.env.local", GROQ_KEY_NAME) is None


def test_an_empty_value_in_the_file_counts_as_absent(tmp_path, monkeypatch):
    env_file = tmp_path / ".env.local"
    env_file.write_text(f"{GROQ_KEY_NAME}=\n")
    monkeypatch.delenv(GROQ_KEY_NAME, raising=False)
    assert groq_api_key(env_file=str(env_file)) is None


def test_a_model_this_endpoint_does_not_serve_is_refused_before_the_upload():
    plan = hosted_availability("base", have_key=True)
    assert plan["available"] is False
    assert "whisper-large-v3" in plan["why_not"]
    assert "--backend local" in plan["why_not"]


# --- conversion ------------------------------------------------------------


def test_the_conversion_targets_sixteen_kilohertz_mono_sixteen_bit():
    """Three minutes at 48 kHz mono float32 is 34.5 MB and over the free-tier
    limit before a word is said; the same three minutes at 16 kHz mono int16 is
    5.8 MB, and 16 kHz mono is what the model downsamples to anyway."""
    cmd = afconvert_command("/usr/bin/afconvert", "in.wav", "out.wav")
    assert cmd[cmd.index("-d") + 1] == "LEI16@16000"
    assert cmd[cmd.index("-c") + 1] == "1"
    assert cmd[cmd.index("-f") + 1] == "WAVE"
    assert cmd[cmd.index("--src-quality") + 1] == "127"
    assert cmd[-2:] == ["in.wav", "out.wav"]


def test_a_failed_conversion_refuses_instead_of_uploading_the_original(tmp_path):
    def runner(cmd, capture_output=False):
        return _Ran(returncode=1, stderr=b"afconvert: unsupported format")

    with pytest.raises(RuntimeError) as caught:
        convert_for_upload("a.wav", str(tmp_path / "out.wav"),
                           "/usr/bin/afconvert", runner)
    message = str(caught.value)
    assert "unsupported format" in message
    assert "NOT uploaded" in message, (
        "a decode of a file nobody could convert is a decode of an unknown file")


def test_a_conversion_that_exits_zero_and_writes_nothing_is_still_a_refusal(tmp_path):
    with pytest.raises(RuntimeError) as caught:
        convert_for_upload("a.wav", str(tmp_path / "out.wav"),
                           "/usr/bin/afconvert",
                           lambda cmd, capture_output=False: _Ran(0))
    assert "wrote nothing" in str(caught.value)


def test_a_missing_converter_is_a_caveat_and_not_a_refusal():
    # A WAV already small enough can go up as it is; refusing would be a
    # machine telling the operator it cannot do a thing it can do.
    plan = hosted_availability(have_key=True, converter=None)
    assert plan["available"] is True
    assert "afconvert" in plan["caveat"]
    assert find_converter("/nonexistent/afconvert") is None


# --- the digest names the RECORDING, not the transport artefact -------------


def test_the_digest_is_of_the_original_recording_not_the_converted_upload(
        tmp_path, monkeypatch):
    """Requirement three, and it is the one that would rot quietly. The digest
    is what proof/engine_or_audio.py compares to decide two cells named the
    same recording. Hash the converted file and the reference cell and the
    app's cell stop agreeing about which WAV they are talking about — the exact
    arm-swap the provenance line exists to catch, introduced by the fix for it.
    """
    monkeypatch.setenv(GROQ_KEY_NAME, "sk-not-a-real-key")
    original = tmp_path / "arm_a.wav"
    original.write_bytes(b"RIFF" + b"\x01" * 4096)
    original_sha = wav_digest(str(original))

    converted_bytes = []

    def runner(cmd, capture_output=False):
        # afconvert's real behaviour: a DIFFERENT file with different bytes.
        with open(cmd[-1], "wb") as fh:
            fh.write(b"RIFF" + b"\x02" * 512)
        converted_bytes.append(cmd[-1])
        return _Ran(0)

    out = tmp_path / "arm_a" / "reference.txt"
    plan = hosted_availability(have_key=True, converter="/usr/bin/afconvert")
    decode(str(original), str(out), backend=BACKEND_HOSTED, plan=plan,
           runner=runner,
           opener=_opener(json.dumps(
               {"text": " " + " ".join(["word"] * 40)}).encode()))

    assert converted_bytes, "the converter should have been used at all"
    header = out.read_text(encoding="utf-8").splitlines()[0]
    assert f"sha256={original_sha}" in header
    assert original_sha != "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934c" \
                           "a495991b7852b855", "empty-file hash, not a real one"


def test_the_provenance_line_names_the_engine_that_actually_decoded(
        tmp_path, monkeypatch):
    monkeypatch.setenv(GROQ_KEY_NAME, "sk-not-a-real-key")
    original = tmp_path / "arm_c.wav"
    original.write_bytes(b"RIFF" + b"\x01" * 128)
    out = tmp_path / "arm_c" / "reference.txt"
    decode(str(original), str(out), backend=BACKEND_HOSTED,
           plan=hosted_availability(have_key=True, converter=None),
           opener=_opener(json.dumps(
               {"text": " " + " ".join(["word"] * 40)}).encode()))
    header = out.read_text(encoding="utf-8").splitlines()[0]
    assert "engine=whisper-hosted:whisper-large-v3" in header
    assert "arm=C" in header
    assert "decoder=reference" in header, (
        "decoder= is the CELL's name and the scorer refuses the cell when it "
        "disagrees with the manifest; engine= is the new field")


def test_the_scorer_reads_the_new_line_without_choking_on_the_new_field():
    """A cross-file contract test. `engine` is deliberately not one of the
    scorer's PROVENANCE_KEYS, so parse_provenance must drop it and
    strip_provenance must take the whole line off — otherwise the engine name
    is tokenised and charged to the decoder as words it hallucinated."""
    from proof.engine_or_audio import (
        _provenance_mismatch, parse_provenance, strip_provenance, tokens)

    line = provenance_line(__file__, "C", engine=engine_name(
        BACKEND_HOSTED, HOSTED_DEFAULT_MODEL))
    raw = line + "the quick brown fox"
    parsed = parse_provenance(raw)
    assert parsed["arm"] == "C"
    assert parsed["decoder"] == "reference"
    assert "engine" not in parsed
    assert _provenance_mismatch(parsed, "C", "reference") is None
    assert strip_provenance(raw) == "the quick brown fox"
    assert "whisper-hosted" not in tokens(strip_provenance(raw))


def test_engine_name_is_one_token_because_the_line_is_whitespace_split():
    name = engine_name(BACKEND_HOSTED, HOSTED_DEFAULT_MODEL)
    assert " " not in name
    assert name == "whisper-hosted:whisper-large-v3"


# --- the multipart body ----------------------------------------------------


def test_the_body_carries_the_model_the_filename_and_the_audio_bytes():
    body, content_type = multipart_body(
        {"model": "whisper-large-v3", "temperature": "0"},
        "arm_a.wav", b"\x00AUDIOBYTES\x01")
    assert b'name="model"' in body
    assert b"whisper-large-v3" in body
    assert b'filename="arm_a.wav"' in body
    assert b"\x00AUDIOBYTES\x01" in body
    boundary = content_type.split("boundary=", 1)[1]
    assert body.startswith(("--" + boundary).encode())
    assert body.endswith(("--" + boundary + "--\r\n").encode())


def test_a_boundary_that_occurs_inside_the_audio_is_refused_not_uploaded():
    # It would split the upload in the wrong place and the server would decode
    # whatever fell before it — quiet truncation, which is the failure mode
    # this whole module exists to refuse.
    with pytest.raises(RuntimeError) as caught:
        multipart_body({}, "a.wav", b"xx--fixedxx", boundary="fixed")
    assert "truncated" in str(caught.value)


# --- the HTTP layer, every branch, no socket --------------------------------


def test_a_two_hundred_returns_the_transcript_exactly_as_it_came_back():
    """Law 1. This module's job ends at "here is what the decoder returned,
    verbatim" — the leading space, the casing and the digits are the scorer's
    to normalise, and a cleanup here would silently change the measurement."""
    text = hosted_transcribe(
        b"audio", "a.wav", "whisper-large-v3", "sk-x",
        opener=_opener(b'{"text": " The 7.15 train, Tejas said."}'))
    assert text == " The 7.15 train, Tejas said."


def test_the_request_carries_the_credential_and_the_user_agent():
    """HOSTED_USER_AGENT is a regression pin, not decoration: on 2026-09-06 the
    endpoint's Cloudflare edge answered urllib's default `Python-urllib/3.9`
    with `HTTP 403 ... error code: 1010` — a browser-signature ban that reads
    exactly like a bad key. The same key over curl returned 200 in the same
    minute."""
    seen = []
    hosted_transcribe(b"audio", "a.wav", "whisper-large-v3", "sk-x",
                      opener=_opener(seen=seen))
    request = seen[0]
    assert request.get_header("Authorization") == "Bearer sk-x"
    assert request.get_header("User-agent") == HOSTED_USER_AGENT
    assert request.get_method() == "POST"


def test_the_request_asks_for_a_deterministic_english_json_decode():
    seen = []
    hosted_transcribe(b"audio", "a.wav", "whisper-large-v3", "sk-x",
                      opener=_opener(seen=seen))
    body = seen[0].data
    assert b'name="temperature"\r\n\r\n0\r\n' in body, (
        "a measuring stick that returns a different number on the second run "
        "is not a measuring stick")
    assert b'name="language"\r\n\r\nen\r\n' in body
    assert b'name="response_format"\r\n\r\njson\r\n' in body, (
        "a bare text body cannot be told apart from an error page that "
        "arrived with a 200")


def test_a_rate_limit_is_reported_as_a_rate_limit_not_as_an_empty_transcript():
    with pytest.raises(RuntimeError) as caught:
        hosted_transcribe(b"audio", "a.wav", "whisper-large-v3", "sk-x",
                          opener=_http_error(429, b"slow down",
                                             {"retry-after": "17"}))
    message = str(caught.value)
    assert "429" in message
    assert "17" in message, "the operator should be told how long"
    assert "Nothing was transcribed" in message


def test_a_refused_credential_names_both_causes_that_look_identical():
    with pytest.raises(RuntimeError) as caught:
        hosted_transcribe(b"audio", "a.wav", "whisper-large-v3", "sk-x",
                          opener=_http_error(403, b"error code: 1010"))
    message = str(caught.value)
    assert GROQ_KEY_NAME in message
    assert "1010" in message and "HOSTED_USER_AGENT" in message, (
        "an edge ban and an expired key are the same HTTP code; a message "
        "that names only one of them costs an afternoon")


def test_any_other_non_two_hundred_is_a_refusal_carrying_the_body():
    with pytest.raises(RuntimeError) as caught:
        hosted_transcribe(b"audio", "a.wav", "whisper-large-v3", "sk-x",
                          opener=_http_error(500, b"upstream exploded"))
    assert "500" in str(caught.value)
    assert "upstream exploded" in str(caught.value)


def test_no_network_at_all_says_so_rather_than_hanging_or_returning_nothing():
    def opener(request, timeout=None):
        raise urllib.error.URLError("nodename nor servname provided")

    with pytest.raises(RuntimeError) as caught:
        hosted_transcribe(b"audio", "a.wav", "whisper-large-v3", "sk-x",
                          opener=opener)
    assert "could not be reached" in str(caught.value)
    assert "nodename" in str(caught.value)


def test_a_two_hundred_that_is_not_json_is_refused_rather_than_scored():
    with pytest.raises(RuntimeError) as caught:
        hosted_transcribe(b"audio", "a.wav", "whisper-large-v3", "sk-x",
                          opener=_opener(b"<html>Attention Required!</html>"))
    assert "not JSON" in str(caught.value)


def test_json_with_no_text_key_is_an_absent_transcript_not_an_empty_one():
    with pytest.raises(RuntimeError) as caught:
        hosted_transcribe(b"audio", "a.wav", "whisper-large-v3", "sk-x",
                          opener=_opener(b'{"error": {"message": "no"}}'))
    message = str(caught.value)
    assert "no `text` key" in message
    assert "never as an empty one" in message


def test_a_status_that_is_not_two_hundred_without_an_exception_is_refused():
    # A redirect or a 204 arrives here as a response object, not an HTTPError.
    with pytest.raises(RuntimeError) as caught:
        hosted_transcribe(b"audio", "a.wav", "whisper-large-v3", "sk-x",
                          opener=_opener(b'{"text": "hello there"}', status=204))
    assert "204" in str(caught.value)


# --- the failed-decode shape ------------------------------------------------


def test_an_empty_transcript_is_refused_rather_than_written():
    with pytest.raises(RuntimeError) as caught:
        guard_decode_text("   \n", "arm_a.wav", "whisper-hosted:x")
    assert "0 word" in str(caught.value)
    assert "Nothing was written" in str(caught.value)


def test_one_word_is_refused_for_the_same_reason_zero_is():
    """proof/engine_or_audio.py:169-191: "you" and "Thank you." are whisper's
    canonical output on silence or a failed decode, and "you" alone scored
    capture 0.0027 with script share 1.00 and fired R1 off a dead file. The
    line was drawn at the one point where the confusion cannot occur rather
    than at the point where it stops."""
    with pytest.raises(RuntimeError) as caught:
        guard_decode_text("you", "arm_a.wav", "whisper-hosted:x")
    message = str(caught.value)
    assert "'you'" in message, "and it should say what came back"
    assert "engine_or_audio.py:169-191" in message
    assert MIN_DECODE_WORDS == 2


def test_the_guard_counts_words_and_does_not_read_them():
    """Law 1: no word list may decide what words mean. Two real words are a
    real transcript and get written verbatim, warned about but not censored —
    the guard's whole competence is arithmetic over a length."""
    warnings = []
    assert guard_decode_text("Thank you.", "a.wav", "e", warnings.append) == "Thank you."
    assert guard_decode_text("banana banana", "a.wav", "e", warnings.append) == "banana banana"
    assert len(warnings) == 2, "both are short, and both are written"


def test_a_transcript_the_scorer_will_refuse_gets_said_out_loud_first():
    warnings = []
    guard_decode_text(" ".join(["word"] * 5), "a.wav", "e", warnings.append)
    assert warnings and "MIN_TRANSCRIPT_WORDS" in warnings[0]
    warnings.clear()
    guard_decode_text(" ".join(["word"] * 40), "a.wav", "e", warnings.append)
    assert warnings == [], "a full-length transcript is not warned about"


def test_a_degenerate_decode_writes_no_file_at_all(tmp_path, monkeypatch):
    """The failure mode in one line: a file on disk that a later reader takes
    for a result. There must not be one."""
    monkeypatch.setenv(GROQ_KEY_NAME, "sk-not-a-real-key")
    wav = tmp_path / "arm_a.wav"
    wav.write_bytes(b"RIFF" + b"\x01" * 64)
    out = tmp_path / "arm_a" / "reference.txt"
    with pytest.raises(RuntimeError) as caught:
        decode(str(wav), str(out), backend=BACKEND_HOSTED,
               plan=hosted_availability(have_key=True, converter=None),
               opener=_opener(b'{"text": " you"}'))
    assert "failed decode" in str(caught.value)
    assert not out.exists()


def test_the_transcript_is_written_verbatim_with_nothing_stripped(
        tmp_path, monkeypatch):
    """Law 1 again, at the write. No filler-word stripping, no normalisation,
    no case folding: the scorer does its own, and a cleanup here would change
    the measurement without appearing in the number."""
    monkeypatch.setenv(GROQ_KEY_NAME, "sk-not-a-real-key")
    spoken = ("  Um, the 7.15 train -- Tejas said, uh, ANTICIPY. "
              + " ".join(["padding"] * 30))
    wav = tmp_path / "arm_a.wav"
    wav.write_bytes(b"RIFF" + b"\x01" * 64)
    out = tmp_path / "arm_a" / "reference.txt"
    decode(str(wav), str(out), backend=BACKEND_HOSTED,
           plan=hosted_availability(have_key=True, converter=None),
           opener=_opener(json.dumps({"text": spoken}).encode()))
    body = out.read_text(encoding="utf-8").split("\n", 1)[1]
    assert body == spoken


# --- refusals before the wire ----------------------------------------------


def test_a_file_too_big_for_the_tier_is_refused_with_both_numbers(
        tmp_path, monkeypatch):
    monkeypatch.setenv(GROQ_KEY_NAME, "sk-not-a-real-key")
    monkeypatch.setattr("proof.reference_decode.HOSTED_MAX_BYTES", 100)
    wav = tmp_path / "arm_a.wav"
    wav.write_bytes(b"RIFF" + b"\x01" * 4096)
    with pytest.raises(RuntimeError) as caught:
        decode(str(wav), str(tmp_path / "arm_a" / "reference.txt"),
               backend=BACKEND_HOSTED,
               plan=hosted_availability(have_key=True, converter=None),
               opener=_opener())
    message = str(caught.value)
    assert "do NOT truncate" in message, (
        "a reference transcript of the first half of a page scores the second "
        "half as words the microphone lost")


def test_a_container_the_endpoint_cannot_read_is_refused_before_the_upload(
        tmp_path, monkeypatch):
    monkeypatch.setenv(GROQ_KEY_NAME, "sk-not-a-real-key")
    aiff = tmp_path / "arm_a.aiff"
    aiff.write_bytes(b"FORM" + b"\x01" * 64)
    with pytest.raises(RuntimeError) as caught:
        decode(str(aiff), str(tmp_path / "arm_a" / "reference.txt"),
               backend=BACKEND_HOSTED,
               plan=hosted_availability(have_key=True, converter=None),
               opener=_opener())
    assert ".aiff" in str(caught.value)
    assert "afconvert" in str(caught.value)


def test_an_unavailable_backend_refuses_before_anything_is_uploaded(tmp_path):
    def opener(request, timeout=None):
        raise AssertionError("nothing should have been uploaded")

    with pytest.raises(RuntimeError) as caught:
        decode("a.wav", str(tmp_path / "arm_a" / "reference.txt"),
               backend=BACKEND_HOSTED,
               plan=hosted_availability(have_key=False), opener=opener)
    assert GROQ_KEY_NAME in str(caught.value)


# --- the first backend, still working --------------------------------------


def _fake_whisper(text):
    """whisper names its output after the WAV and drops it in --output_dir; the
    adapter then moves it to --out. That handoff is the fiddly part, and no
    machine in this repo currently has a whisper to prove it with."""
    def runner(cmd, check=False):
        wav = cmd[cmd.index("-m") + 2]
        out_dir = cmd[cmd.index("--output_dir") + 1]
        produced = os.path.join(
            out_dir, os.path.splitext(os.path.basename(wav))[0] + ".txt")
        with open(produced, "w", encoding="utf-8") as fh:
            fh.write(text)
        return _Ran(0)
    return runner


def test_the_local_backend_still_moves_whispers_output_and_stamps_the_arm(tmp_path):
    wav = tmp_path / "arm_b.wav"
    wav.write_bytes(b"RIFF" + b"\x01" * 64)
    out = tmp_path / "arm_b" / "reference.txt"
    out.parent.mkdir()
    spoken = " ".join(["word"] * 30)
    text = decode(str(wav), str(out), model="base", backend=BACKEND_LOCAL,
                  plan=availability("/usr/bin/python3", ["base"], "base"),
                  runner=_fake_whisper(spoken))
    assert text == spoken
    header, body = out.read_text(encoding="utf-8").split("\n", 1)
    assert body == spoken
    assert "arm=B" in header
    assert "engine=whisper-local:base" in header, (
        "the local decode must be as identifiable as the hosted one, or the "
        "engine field only tells you when the answer came from the network")
    assert not (tmp_path / "arm_b" / "arm_b.txt").exists(), (
        "whisper's own output file should have been moved, not left beside "
        "the transcript for somebody to score twice")


def test_the_local_backend_is_guarded_against_the_same_dead_decode(tmp_path):
    """The guard is on the shared tail, so `you` off the local decoder is
    refused for the same reason it is off the hosted one."""
    wav = tmp_path / "arm_b.wav"
    wav.write_bytes(b"RIFF" + b"\x01" * 64)
    out = tmp_path / "arm_b" / "reference.txt"
    out.parent.mkdir()
    with pytest.raises(RuntimeError) as caught:
        decode(str(wav), str(out), model="base", backend=BACKEND_LOCAL,
               plan=availability("/usr/bin/python3", ["base"], "base"),
               runner=_fake_whisper("you"))
    assert "failed decode" in str(caught.value)
    assert not out.exists(), (
        "a one-word file at reference.txt is exactly what a later reader "
        "scores by mistake")
    assert (tmp_path / "arm_b" / "arm_b.txt").read_text() == "you", (
        "and what the decoder actually returned is kept, under its own name, "
        "because refusing is not the same as destroying the evidence")


def test_a_transcript_written_outside_an_arm_directory_gets_no_provenance(tmp_path):
    """arm_of guesses nothing: an unrecognised path would otherwise stamp a
    line that itself lies about which arm the recording came from."""
    wav = tmp_path / "scratch.wav"
    wav.write_bytes(b"RIFF" + b"\x01" * 64)
    out = tmp_path / "somewhere" / "reference.txt"
    spoken = " ".join(["word"] * 30)
    decode(str(wav), str(out), model="base", backend=BACKEND_LOCAL,
           plan=availability("/usr/bin/python3", ["base"], "base"),
           runner=_fake_whisper(spoken))
    assert out.read_text(encoding="utf-8") == spoken
