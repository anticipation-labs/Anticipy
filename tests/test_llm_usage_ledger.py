"""Provider-reported usage survives Gemini's native transport, offline.

The fixture follows Google's GenerateContentResponse UsageMetadata contract:
https://ai.google.dev/api/generate-content#UsageMetadata
No provider requests, estimated token counts, or estimated prices are used.
"""
import json

import pytest

import brain.llm as L


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "calls.jsonl"
    monkeypatch.setattr(L, "_LEDGER", str(path))
    return path


def gemini(monkeypatch, data):
    monkeypatch.setattr(L, "_post_json", lambda *_args, **_kwargs: data)
    client = L.LLM(api_key="fixture-unused")
    client.gemini_api_key = "fixture-unused"
    return client._gemini("private system fixture", "private user fixture", 0,
                          model="fixture-gemini")


def lines(ledger):
    return [json.loads(line) for line in ledger.read_text().splitlines()]


def response(usage):
    return {"candidates": [{"content": {"parts": [{"text": "fixture answer"}]},
                            "finishReason": "STOP"}], "usageMetadata": usage}


def test_native_gemini_counts_are_recorded_without_inventing_price(ledger, monkeypatch):
    usage = {"promptTokenCount": 120, "candidatesTokenCount": 14,
             "cachedContentTokenCount": 90, "thoughtsTokenCount": 7,
             "toolUsePromptTokenCount": 3, "totalTokenCount": 144}
    result = gemini(monkeypatch, response(usage))

    assert result.text == "fixture answer"
    [row] = lines(ledger)
    assert row["prompt_tokens"] == 120, "cached tokens are already included"
    assert row["completion_tokens"] == 14, "preserve reported response-candidate count"
    assert row["cached_tokens"] == 90
    assert row["reasoning_tokens"] == 7
    assert row["tool_prompt_tokens"] == 3
    assert row["total_tokens"] == 144, "the provider aggregate is authoritative"
    assert row["cost"] is None, "Gemini's response reports tokens, not a dollar price"
    assert row["mode"] == "gemini" and row["model"] == "fixture-gemini"
    raw = ledger.read_text()
    assert "private system fixture" not in raw and "private user fixture" not in raw
    assert "fixture-unused" not in raw and "fixture answer" not in raw


@pytest.mark.parametrize("data", [
    {"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}},
    {"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]},
])
def test_empty_or_refused_replies_still_record_provider_usage(ledger, monkeypatch, data):
    data["usageMetadata"] = {"promptTokenCount": 18, "thoughtsTokenCount": 2,
                             "totalTokenCount": 20}
    with pytest.raises(ValueError, match="Gemini returned no text"):
        gemini(monkeypatch, data)

    [row] = lines(ledger)
    assert row["prompt_tokens"] == 18 and row["reasoning_tokens"] == 2
    assert row["total_tokens"] == 20
    assert row["completion_tokens"] is None, "absence is not a reported zero"


@pytest.mark.parametrize("usage", [None, {}, "malformed", [], {
    "promptTokenCount": True, "candidatesTokenCount": -1,
    "cachedContentTokenCount": "90", "thoughtsTokenCount": 1.5,
    "toolUsePromptTokenCount": {}, "totalTokenCount": False,
}])
def test_missing_or_malformed_usage_is_unknown_without_breaking_the_answer(ledger, monkeypatch, usage):
    assert gemini(monkeypatch, response(usage)).text == "fixture answer"
    [row] = lines(ledger)
    for key in ("prompt_tokens", "completion_tokens", "cached_tokens",
                "reasoning_tokens", "tool_prompt_tokens", "total_tokens", "cost"):
        assert row[key] is None


def test_explicit_zero_counts_are_not_lost(ledger, monkeypatch):
    gemini(monkeypatch, response({name: 0 for name in (
        "promptTokenCount", "candidatesTokenCount", "cachedContentTokenCount",
        "thoughtsTokenCount", "toolUsePromptTokenCount", "totalTokenCount")}))
    [row] = lines(ledger)
    for key in ("prompt_tokens", "completion_tokens", "cached_tokens",
                "reasoning_tokens", "tool_prompt_tokens", "total_tokens"):
        assert row[key] == 0
    assert row["cost"] is None


def test_openrouter_usage_keeps_its_existing_meaning(ledger, monkeypatch):
    monkeypatch.setattr(L, "_post_json", lambda *_args, **_kwargs: {
        "choices": [{"message": {"content": "fixture answer"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 9, "total_tokens": 20,
                  "prompt_tokens_details": {"cached_tokens": 5},
                  "completion_tokens_details": {"reasoning_tokens": 4}, "cost": 0.0012},
    })
    L.LLM(api_key="fixture-unused")._openrouter("system", "user")
    [row] = lines(ledger)
    assert row["prompt_tokens"] == 11 and row["completion_tokens"] == 9
    assert row["cached_tokens"] == 5 and row["reasoning_tokens"] == 4
    assert row["total_tokens"] == 20 and row["cost"] == 0.0012
    assert row["mode"] == "openrouter"


def test_a_fallback_keeps_both_providers_reported_usage(ledger, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fixture-unused")
    monkeypatch.setenv("ANTICIPY_LLM_ORDER", "gemini,openrouter")
    asked = []

    def provider(url, *_args, **_kwargs):
        asked.append(url)
        if url == L.OPENROUTER_URL:
            return {"choices": [{"message": {"content": "fallback answer"}}],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 5,
                              "total_tokens": 25, "cost": 0.002}}
        return {"candidates": [], "usageMetadata": {
            "promptTokenCount": 10, "thoughtsTokenCount": 2, "totalTokenCount": 12}}

    monkeypatch.setattr(L, "_post_json", provider)
    result = L.LLM(api_key="fixture-unused").chat("fixture system", "fixture user")

    assert result.text == "fallback answer" and result.fell_through_from == "gemini"
    assert len(asked) == 2
    rows = lines(ledger)
    assert [(r["mode"], r["total_tokens"]) for r in rows] == [("gemini", 12), ("openrouter", 25)]
    assert rows[0]["cost"] is None and rows[1]["cost"] == 0.002


def test_ledger_write_failure_cannot_change_a_valid_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "_LEDGER", str(tmp_path))  # directory, not writable as a file
    assert gemini(monkeypatch, response({"promptTokenCount": 12})).text == "fixture answer"
