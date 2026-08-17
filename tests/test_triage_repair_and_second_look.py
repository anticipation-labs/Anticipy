"""Two triage failures that cost real actions.

1. The unparseable-output retry re-sent the IDENTICAL prompt at temperature
   0.0 while llm.py pins seed=11 — a deterministic replay of the reply that
   had just failed. It could never succeed; it only doubled cost and latency
   on the already-failing path.

2. SECOND_LOOK was handed the fully decorated transcript line (memory notes,
   earlier-conversation block, voice check) but, unlike TRIAGE_SYSTEM, its
   prompt never said that decoration is context rather than commitment. A
   remembered fact could satisfy "the owner plainly commits" and flip an
   honest "ignore" into an action he never asked for.
"""
import inspect
from brain import orchestrator


def test_the_retry_is_a_different_ask():
    src = inspect.getsource(orchestrator.Brain.triage)
    # The repair sentence is split across source lines, so normalise before
    # matching — an assertion that depends on line wrapping is a false alarm
    # waiting to happen.
    flat = " ".join(src.split())
    assert 'could not be " "parsed as JSON' in flat or "could not be parsed as JSON" in flat, \
        "the retry must tell the model what went wrong"
    assert "temperature=0.2" in src, \
        "a pinned seed at temperature 0 makes the retry a bit-for-bit replay"


def test_second_look_refuses_to_read_context_as_commitment():
    p = orchestrator.Brain.SECOND_LOOK
    for marker in ("Related memory", "Earlier in this conversation", "Voice check"):
        assert marker in p, f"SECOND_LOOK must name the {marker!r} decoration"
    assert "NOT HIM COMMITTING" in p
    assert "ONLY the current line" in p


def test_triage_system_still_carries_its_own_guard():
    assert "never themselves a reason to act" in orchestrator.TRIAGE_SYSTEM
