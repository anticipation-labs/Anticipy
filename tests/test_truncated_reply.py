"""A reply that ran out of room must never be spoken as if it were finished.

Both providers report it and this client discarded the answer: Gemini in
`candidates[0].finishReason`, OpenRouter in `choices[0].finish_reason`. A JSON
judgment cut at the ceiling mostly self-corrects, because the parse fails and
triage re-asks. Prose does not — `_voice` composes the words that go to the
owner's phone, and a composition truncated mid-word was sent as-is. Omi's own
ranked improvement list calls this small to fix and expensive to ship; it costs
more here, because the destination is a text message rather than a chat bubble.

The polarity is the point and is tested in both directions: a POSITIVE
truncation signal discards the composition, and an absent or unrecognised one
does NOT. A guard that fired when it could not see would silence her the first
time a provider renamed a field.
"""

from brain.llm import LLMResult


class _Stub:
    """Enough of an LLM to answer one composition."""

    live = True

    def __init__(self, result):
        self._result = result

    def chat(self, *_args, **_kwargs):
        return self._result


def _voice_with(result):
    from brain.anticipy_core import Anticipy
    brain = Anticipy.__new__(Anticipy)
    brain.llm = _Stub(result)
    return brain._voice({"goal": "email Priya the invoice"})


def test_truncated_composition_is_discarded():
    out = _voice_with(LLMResult(text="I'll email Priya the inv",
                                used_model="m", mode="gemini", truncated=True))
    assert out is None, "a half-sentence must not reach the owner"


def test_complete_composition_is_spoken():
    out = _voice_with(LLMResult(text="I'll email Priya the invoice.",
                                used_model="m", mode="gemini",
                                truncated=False))
    assert out == "I'll email Priya the invoice."


def test_absent_signal_is_not_a_verdict():
    """An LLMResult built without the field must still speak.

    Absence is not a verdict. If this inverted, a provider that stopped
    sending a finish reason would mute her entirely rather than degrade.
    """
    out = _voice_with(LLMResult(text="On it.", used_model="m", mode="gemini"))
    assert out == "On it."


def _gemini_answering(reason):
    """Run the REAL _gemini parse against a canned provider payload.

    Asserting the rule by restating it would test the restatement. This drives
    the actual code path with the JSON shape Gemini returns, so a change to
    where the field is read — a renamed key, a moved candidate — turns it red.
    """
    import brain.llm as llm_mod

    payload = {
        "candidates": [{
            "content": {"parts": [{"text": "I'll email Priya the inv"}]},
            "finishReason": reason,
        }],
        "usageMetadata": {},
    }

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def post(self, *_a, **_k):
            return _Resp()

    original = llm_mod.httpx.Client
    llm_mod.httpx.Client = lambda *a, **k: _Client()
    try:
        brain_llm = llm_mod.LLM.__new__(llm_mod.LLM)
        brain_llm.gemini_model = "gemini-2.5-flash"
        brain_llm.gemini_api_key = "test-key"
        return brain_llm._gemini("sys", "user", 0.0)
    finally:
        llm_mod.httpx.Client = original


def test_gemini_max_tokens_is_read_as_truncated():
    assert _gemini_answering("MAX_TOKENS").truncated is True


def test_gemini_stop_is_not_truncated():
    assert _gemini_answering("STOP").truncated is False


def test_gemini_refusals_are_not_relabelled_as_truncation():
    """SAFETY and RECITATION are refusals, not truncations.

    Calling them truncation would route a refusal into the "template speaks
    instead" branch and hide it, when the caller's own emptiness handling is
    what should see it.
    """
    for reason in ("SAFETY", "RECITATION", "OTHER"):
        assert _gemini_answering(reason).truncated is False


def test_gemini_absent_reason_is_not_a_verdict():
    assert _gemini_answering("").truncated is False


def test_default_is_false():
    assert LLMResult(text="t", used_model="m", mode="heuristic").truncated is False
