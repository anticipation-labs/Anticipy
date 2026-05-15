"""Phase V4-3 unit tests for VisionVerifier. OpenRouter mocked."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.action_engine.vision_verifier import VisionVerifier, _parse_verdict  # noqa: E402
from app.action_engine.openrouter_client import ORResponse  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n fake bytes"


def _client_returning(*contents):
    """Mock client whose .chat returns the given contents in sequence."""
    c = MagicMock()
    seq = [ORResponse(content=ct, model="moonshotai/kimi-k2.6", latency_s=0.1)
           for ct in contents]
    c.chat.side_effect = seq
    return c


def test_parse_verdict_certified():
    v = _parse_verdict('{"status":"CERTIFIED","evidence":"page changed","confidence":0.9}')
    assert v.status == "CERTIFIED" and v.confidence == 0.9


def test_parse_verdict_embedded_json():
    v = _parse_verdict('here is my answer {"status":"DIVERGED","evidence":"no change","confidence":0.8} done')
    assert v.status == "DIVERGED"


def test_parse_verdict_garbage_returns_none():
    assert _parse_verdict("not json, no verdict") is None


def test_certified_high_confidence_no_fallback():
    c = _client_returning('{"status":"CERTIFIED","evidence":"nav happened","confidence":0.95}')
    v = VisionVerifier(client=c)
    out = v.verify({"action": "click"}, PNG, PNG, "open the menu")
    assert out.status == "CERTIFIED"
    assert out.confidence == 0.95
    assert not out.fellback
    assert c.chat.call_count == 1


def test_diverged_high_confidence_no_fallback():
    c = _client_returning('{"status":"DIVERGED","evidence":"nothing moved","confidence":0.88}')
    v = VisionVerifier(client=c)
    out = v.verify({"action": "click"}, PNG, PNG, "open the menu")
    assert out.status == "DIVERGED"
    assert c.chat.call_count == 1


def test_low_confidence_triggers_second_opinion_agree():
    c = _client_returning(
        '{"status":"CERTIFIED","evidence":"maybe","confidence":0.4}',
        '{"status":"CERTIFIED","evidence":"yes clearly","confidence":0.9}',
    )
    v = VisionVerifier(client=c)
    out = v.verify({"action": "click"}, PNG, PNG, "submit form")
    assert out.status == "CERTIFIED"
    assert out.fellback
    assert c.chat.call_count == 2


def test_low_confidence_mixed_resolves_diverged():
    c = _client_returning(
        '{"status":"CERTIFIED","evidence":"looks ok","confidence":0.5}',
        '{"status":"DIVERGED","evidence":"actually no","confidence":0.7}',
    )
    v = VisionVerifier(client=c)
    out = v.verify({"action": "click"}, PNG, PNG, "submit form")
    assert out.status == "DIVERGED"
    assert "mixed" in out.evidence.lower()
    assert out.fellback


def test_unparseable_primary_falls_to_strict():
    c = _client_returning(
        "I cannot output JSON sorry",
        '{"status":"DIVERGED","evidence":"strict says no","confidence":0.8}',
    )
    v = VisionVerifier(client=c)
    out = v.verify({"action": "type"}, PNG, PNG, "fill the box")
    assert out.status == "DIVERGED"
    assert out.fellback


def test_total_failure_is_conservative_diverged():
    c = _client_returning("garbage one", "garbage two")
    v = VisionVerifier(client=c)
    out = v.verify({"action": "type"}, PNG, PNG, "fill the box")
    assert out.status == "DIVERGED"
    assert out.confidence == 0.0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
