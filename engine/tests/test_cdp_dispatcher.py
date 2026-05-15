"""Unit tests for the CDP dispatcher humanlike motion + parsing.

Phase fara-3 gate (unit half). Integration test against real Chrome
lives at engine/tests/integration/test_dispatcher_real_chrome.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.action_engine.humanlike import (
    bezier_path,
    gaussian_delay,
    typing_inter_char_delays,
)


def test_bezier_deterministic_with_seed():
    rng = np.random.default_rng(42)
    p1 = bezier_path(0, 0, 100, 100, n_points=10, rng=rng)
    rng = np.random.default_rng(42)
    p2 = bezier_path(0, 0, 100, 100, n_points=10, rng=rng)
    assert len(p1) == 11
    for a, b in zip(p1, p2):
        assert a.x == pytest.approx(b.x)
        assert a.y == pytest.approx(b.y)
        assert a.delay_ms == pytest.approx(b.delay_ms)


def test_bezier_endpoint_close_to_target():
    rng = np.random.default_rng(0)
    p = bezier_path(0, 0, 1000, 500, n_points=30, rng=rng)
    last = p[-1]
    # Last point can be slightly off due to jitter; should be within 5px
    assert abs(last.x - 1000) < 5
    assert abs(last.y - 500) < 5


def test_bezier_delays_in_clamp_range():
    rng = np.random.default_rng(1)
    p = bezier_path(0, 0, 200, 200, n_points=50, rng=rng)
    for pt in p:
        assert 5.0 <= pt.delay_ms <= 50.0


def test_gaussian_delay_clamps():
    rng = np.random.default_rng(7)
    samples = [gaussian_delay(100, 50, 30, 200, rng=rng) for _ in range(200)]
    assert min(samples) >= 30.0
    assert max(samples) <= 200.0
    # Mean should be near 100
    mean = sum(samples) / len(samples)
    assert 90 < mean < 110, f"mean {mean} outside 90..110"


def test_typing_delays_length_and_clamp():
    rng = np.random.default_rng(3)
    text = "Hello world this is a test typing string"
    delays = typing_inter_char_delays(text, rng=rng)
    assert len(delays) == len(text)
    for d in delays:
        assert d >= 30.0
        # Pause cap is 1500ms
        assert d <= 1500.0


# ─── Refusal parsing ──────────────────────────────────────────────────


def test_fara_parser_extracts_left_click():
    from app.fara.server import _parse_fara_output
    raw = '<think>I see Compose. I click it.</think>{"name": "computer_use", "arguments": {"action": "left_click", "coordinate": [105, 178]}}'
    out = _parse_fara_output(raw)
    assert out["action"] == "left_click"
    assert out["coordinate"] == [105, 178]
    assert "Compose" in (out.get("chain_of_thought") or "")
    assert out["refusal"] is False


def test_fara_parser_detects_refusal():
    from app.fara.server import _parse_fara_output
    raw = "I cannot complete this task because it requires user consent at a critical point."
    out = _parse_fara_output(raw)
    assert out["refusal"] is True
    assert out.get("action") is None


def test_fara_parser_handles_type_with_text():
    from app.fara.server import _parse_fara_output
    raw = '{"name":"computer_use","arguments":{"action":"type","text":"hello world"}}'
    out = _parse_fara_output(raw)
    assert out["action"] == "type"
    assert out["text"] == "hello world"
