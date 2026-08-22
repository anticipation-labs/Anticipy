"""A prompt that says nothing about place is not neutral — it is an invitation.

Live 2026-08-22, on an account whose owner_profile carries
`timezone: America/Los_Angeles`, the owner said:

    "I keep meaning to find out how late the post office on Main is open on
     Saturdays"

and the delivered text began:

    "the main street post office in philly is open saturday until noon, but
     i'm not finding any main street post of..."

Philadelphia, for someone on Pacific time. where_line() returned "" whenever
it could not derive a city from the IANA zone, so the grounding said nothing
at all about where the owner was, and the model filled the hole confidently
before hedging in the same sentence.

These tests pin all three halves of the fix: the derivable city still gets
named, the underivable one is stated as unknown out loud, and the static
system prompt still leads the message so the prompt cache (measured 5x) keeps
hitting.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.llm import LLM, where_line  # noqa: E402


# Long enough to clear LLM.CACHE_MIN_CHARS, so chat() takes the cached
# multipart shape — the only shape where prefix order is load-bearing.
BIG_PROMPT = "Return JSON. " + ("x" * (LLM.CACHE_MIN_CHARS + 100))


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": '{"decision":"ignore"}'}}],
                "usage": {}}


class _Client:
    request = None

    def __init__(self, timeout):
        assert timeout == 60

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def post(self, url, headers, json):
        type(self).request = (url, headers, json)
        return _Response()


def _system_blocks(monkeypatch, zone):
    """Whatever the transport actually receives as the system message."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-secret")
    monkeypatch.setattr("brain.llm.httpx.Client", _Client)
    LLM(owner_zone=zone).chat(BIG_PROMPT, "hello")
    _url, _headers, payload = _Client.request
    return payload["messages"][0]["content"]


def test_a_derivable_zone_still_names_the_city():
    """The behaviour that already worked, pinned so the fix cannot bleach it."""
    line = where_line("America/Los_Angeles")
    assert "Los Angeles" in line
    assert "unless they say otherwise" in line


def test_an_unknown_zone_forbids_inventing_a_city():
    """The Philadelphia bug: silence became a guess, so silence is over."""
    for zone in (None, "", "   ", "UTC", "not-a-zone"):
        line = where_line(zone)
        assert line.strip(), f"{zone!r} still grounds the model in nothing"
        low = line.lower()
        assert "never assume a city" in low, line
        # And it must say what to do instead, or the model hedges its way
        # into a guess anyway — "philly ... but i'm not finding any".
        assert "ask" in low and "depends" in low, line


def test_the_unknown_line_is_one_short_sentence():
    """This rides on EVERY call, including the 278-token extraction ones."""
    line = where_line(None)
    assert len(line) < 200, f"{len(line)} chars of boilerplate per call"
    assert line.count(".") == 1, line


def test_the_unknown_place_sentence_reaches_the_model(monkeypatch):
    blocks = _system_blocks(monkeypatch, None)
    grounding = blocks[-1]["text"]
    assert "never assume a city" in grounding.lower(), grounding
    # The clock did not get displaced by the place sentence.
    assert "Right now it is" in grounding


def test_a_known_place_reaches_the_model(monkeypatch):
    blocks = _system_blocks(monkeypatch, "America/Los_Angeles")
    grounding = blocks[-1]["text"]
    assert "They are in Los Angeles" in grounding, grounding
    assert "never assume a city" not in grounding.lower(), grounding


def test_the_static_prompt_is_still_the_cached_prefix(monkeypatch):
    """A prompt cache is keyed on an exact PREFIX. If the place sentence ever
    drifts to the front, every call is a permanent miss — measured 0.001041 a
    call against 0.000206 cached."""
    for zone in (None, "America/Los_Angeles"):
        blocks = _system_blocks(monkeypatch, zone)
        assert isinstance(blocks, list) and len(blocks) == 2, blocks
        assert blocks[0]["text"] == BIG_PROMPT, "the static prefix moved"
        assert blocks[0]["cache_control"] == {"type": "ephemeral"}
        assert "cache_control" not in blocks[1], "the clock must never cache"
