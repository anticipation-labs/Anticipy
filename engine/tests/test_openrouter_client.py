"""Phase V4-2 unit tests for OpenRouterClient.

Network calls are mocked. Two of the tests can optionally hit the
real OpenRouter endpoint when RUN_REAL_OPENROUTER=1 is set; by
default they run mocked so the suite is fast and offline-safe.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.action_engine.openrouter_client import (  # noqa: E402
    OpenRouterClient,
    ORResponse,
    screenshot_to_image_block,
    TEXT_MODEL,
    VISION_MODEL,
    MIN_TOKENS,
)


def _mock_resp(status=200, content="READY", reasoning="", finish="stop",
               p_tok=10, c_tok=2):
    m = MagicMock()
    m.status_code = status
    m.text = json.dumps({"error": "x"}) if status != 200 else ""
    m.json.return_value = {
        "model": TEXT_MODEL,
        "choices": [{
            "message": {"role": "assistant", "content": content,
                        "reasoning": reasoning},
            "finish_reason": finish,
        }],
        "usage": {"prompt_tokens": p_tok, "completion_tokens": c_tok},
    }
    return m


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-key")
    return OpenRouterClient()


def test_text_chat_returns_content(client):
    with patch("requests.post", return_value=_mock_resp(content="READY")):
        r = client.chat([{"role": "user", "content": "say READY"}])
    assert r.ok
    assert r.content == "READY"
    assert r.prompt_tokens == 10
    assert r.cost_usd > 0


def test_min_tokens_floor_enforced(client):
    captured = {}

    def _cap(*a, **kw):
        captured["max_tokens"] = kw["json"]["max_tokens"]
        return _mock_resp()

    with patch("requests.post", side_effect=_cap):
        client.chat([{"role": "user", "content": "hi"}], max_tokens=8)
    assert captured["max_tokens"] >= MIN_TOKENS


def test_vision_block_attached(client):
    captured = {}

    def _cap(*a, **kw):
        captured["payload"] = kw["json"]
        return _mock_resp(content="a login page")

    with patch("requests.post", side_effect=_cap):
        r = client.chat(
            [{"role": "user", "content": "what is this"}],
            model=VISION_MODEL, image_b64="ZmFrZQ==",
        )
    assert r.ok
    last = captured["payload"]["messages"][-1]
    assert isinstance(last["content"], list)
    assert any(b.get("type") == "image_url" for b in last["content"])


def test_screenshot_to_image_block():
    blk = screenshot_to_image_block(b"\x89PNG fake bytes")
    assert blk["type"] == "image_url"
    assert blk["image_url"]["url"].startswith("data:image/png;base64,")


def test_fallback_fires_on_primary_error(client):
    calls = []

    def _seq(*a, **kw):
        calls.append(kw["json"]["model"])
        if kw["json"]["model"] == TEXT_MODEL:
            return _mock_resp(status=500)
        return _mock_resp(content="from fallback")

    with patch("requests.post", side_effect=_seq):
        r = client.chat_with_fallback(
            [{"role": "user", "content": "hi"}],
            primary=TEXT_MODEL, fallback=VISION_MODEL,
        )
    assert r.content == "from fallback"
    assert TEXT_MODEL in calls and VISION_MODEL in calls


def test_fallback_on_unparseable_json(client):
    def _seq(*a, **kw):
        if kw["json"]["model"] == TEXT_MODEL:
            return _mock_resp(content="not json at all")
        return _mock_resp(content='{"action":"done"}')

    with patch("requests.post", side_effect=_seq):
        r = client.chat_with_fallback(
            [{"role": "user", "content": "hi"}],
            primary=TEXT_MODEL, fallback=VISION_MODEL,
            response_format={"type": "json_object"},
        )
    assert json.loads(r.content)["action"] == "done"


def test_retry_on_429_then_success(client):
    seq = [_mock_resp(status=429), _mock_resp(status=429), _mock_resp(content="ok now")]

    with patch("requests.post", side_effect=seq), patch("time.sleep"):
        r = client.chat([{"role": "user", "content": "hi"}])
    assert r.ok
    assert r.content == "ok now"


def test_reasoning_starve_retries_with_double_budget(client):
    # First: starved (content empty, reasoning present, finish=length).
    # Second: succeeds. Confirm budget doubled on the retry.
    budgets = []

    def _seq(*a, **kw):
        budgets.append(kw["json"]["max_tokens"])
        if len(budgets) == 1:
            return _mock_resp(content="", reasoning="thinking hard", finish="length")
        return _mock_resp(content="finally")

    with patch("requests.post", side_effect=_seq):
        r = client.chat([{"role": "user", "content": "hi"}], max_tokens=256)
    assert r.content == "finally"
    assert budgets[1] == budgets[0] * 2


def test_bad_key_raises(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-prefix")
    with pytest.raises(RuntimeError):
        OpenRouterClient()


@pytest.mark.skipif(os.environ.get("RUN_REAL_OPENROUTER") != "1",
                    reason="set RUN_REAL_OPENROUTER=1 to hit the live API")
def test_real_text_smoke():
    from dotenv import load_dotenv
    load_dotenv(os.path.expanduser("~/.anticipy/.env"))
    c = OpenRouterClient()
    r = c.chat([{"role": "user", "content": "Reply with the single word READY."}],
               model=TEXT_MODEL, max_tokens=256)
    assert r.ok and "READY" in r.content.upper()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
