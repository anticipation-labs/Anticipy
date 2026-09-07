"""Missing model credentials must not turn speech into rules-engine actions."""
import pytest

from brain.llm import LLM


@pytest.mark.parametrize("utterance", [
    "Please send the deck to my colleague.",
    "Maybe we should book dinner.",
    "That weather was lovely.",
    "Delete the old backup after I confirm.",
])
def test_keyless_call_reports_unavailability_for_every_kind_of_speech(monkeypatch, utterance):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ConnectionError, match="No model transport is configured"):
        LLM().chat("Decide what this means.", utterance)
