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


def _system_sent(monkeypatch, **env):
    """Drive one direct-Gemini call and hand back what it sent."""
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-secret")
    monkeypatch.setattr("brain.llm.httpx.Client", _Client)
    for name, value in env.items():
        monkeypatch.setattr(f"brain.llm.{name}", value)
    return LLM(owner_zone="America/Vancouver", owner_name="Omar")


def test_the_clock_never_leads_the_prompt(monkeypatch):
    """A cache is keyed on an exact PREFIX, so the sentence carrying the
    current minute may never sit in front of the instruction. It did on this
    path until 2026-08-24, behind a comment claiming an explicit
    CachedContent mechanism that has never existed in brain/."""
    llm = _system_sent(monkeypatch)

    llm.chat("Return JSON.", "hello", temperature=0)

    system = _Client.request[2]["systemInstruction"]["parts"][0]["text"]
    assert system.startswith("Return JSON."), system[:120]
    # The grounding still travels — it just travels last.
    assert "Vancouver" in system


def test_a_mechanical_call_reaches_the_aux_model(monkeypatch):
    """ANTICIPY_AUX_MODEL was unreachable whenever GEMINI_API_KEY was set:
    this branch returned before the aux-aware one, so extraction and
    same-fact comparison quietly paid the judgement model's rate."""
    llm = _system_sent(monkeypatch, AUX_MODEL="google/gemini-2.5-flash-lite")

    result = llm.chat("Extract facts.", "hello", temperature=0, aux=True)

    assert result.used_model == "gemini-2.5-flash-lite"
    assert _Client.request[0].endswith("/gemini-2.5-flash-lite:generateContent")


def test_judgement_stays_on_the_good_model(monkeypatch):
    """An aux model being configured must not move a call that decides
    whether to act, what is consequential, or what the owner reads."""
    llm = _system_sent(monkeypatch, AUX_MODEL="google/gemini-2.5-flash-lite")

    result = llm.chat("Decide.", "hello", temperature=0)

    assert result.used_model == "gemini-2.5-flash"


def test_a_foreign_aux_slug_is_refused_not_forwarded(monkeypatch):
    """The direct endpoint serves Google models only. Stripping the vendor
    off another provider's slug would send a name that 404s a real decision,
    so the main model answers instead."""
    llm = _system_sent(monkeypatch, AUX_MODEL="deepseek/deepseek-v3.2")

    result = llm.chat("Extract facts.", "hello", temperature=0, aux=True)

    assert result.used_model == "gemini-2.5-flash"
