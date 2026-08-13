from brain.llm import LLM


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": '{"decision":"ignore"}'}]}}]}


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


def test_gemini_is_preferred_and_bounded(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-secret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-used")
    monkeypatch.setattr("brain.llm.httpx.Client", _Client)

    result = LLM().chat("Return JSON.", "hello", temperature=0)

    assert result.text == '{"decision":"ignore"}'
    assert result.used_model == "gemini-2.5-flash"
    assert result.mode == "gemini"
    url, headers, payload = _Client.request
    assert url.endswith("/gemini-2.5-flash:generateContent")
    assert headers["x-goog-api-key"] == "not-a-real-secret"
    assert payload["generationConfig"]["maxOutputTokens"] == 2048
    assert payload["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
    assert payload["contents"] == [{"role": "user", "parts": [{"text": "hello"}]}]
    assert "Return JSON." in payload["systemInstruction"]["parts"][0]["text"]
