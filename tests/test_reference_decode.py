"""The decoder adapter has to say what is missing, not guess around it.

The experiment's whole inference — "a strong decoder loses the same words, so
the microphone is starved" — collapses if the decoder that produced the number
was weak, or if it quietly went to the network for weights while somebody
believed the run was offline. These drive the pure half: no whisper is invoked,
no subprocess is spawned, and the suite passes identically on a machine with no
decoder installed at all.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from proof.reference_decode import (  # noqa: E402
    REFERENCE_GRADE,
    availability,
    cached_models,
    find_interpreter,
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
