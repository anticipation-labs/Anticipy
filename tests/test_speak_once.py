"""One plan, one voice — the guards that keep her from texting twice.

On 2026-08-05 the held dinner text went out, and then the clock — checking
only its own dedupe class, with exact goal-string equality — texted "just
confirming for tomorrow night, what time and where…" about the very same
dinner. Two texts, one plan, the exact spam Omar fears most.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.worker as W  # noqa: E402
from brain.anticipy_core import _BROWSER_TARGET_RE, job_lane  # noqa: E402


class _R:
    def __init__(self, items):
        self._items, self.ok = items, True

    def json(self):
        return {"items": self._items}


def _events(monkeypatch, items):
    captured = {}

    def fake_get(url, params=None, timeout=None, **kw):
        captured["filter"] = (params or {}).get("filter", "")
        return _R(items)

    monkeypatch.setattr(W.pb, "get", fake_get)
    return captured


NOW = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def test_clock_sees_the_held_plan_text(monkeypatch):
    """A plan raised by an act text immunizes the clock — cross-class."""
    captured = _events(monkeypatch, [{
        "kind": "anticipy_says", "decision": "act", "created": NOW,
        "goal": "book dinner reservation for 2 at Cactus Club park location "
                "for 7 PM tomorrow"}])
    raised = W.already_raised(
        "confirm the Cactus Club dinner plan for tomorrow at 7 PM",
        decision="clock")
    assert raised, "the clock re-raised a plan the act text already raised"
    assert 'decision="act"' in captured["filter"], captured["filter"]


def test_rephrasing_does_not_slip_the_guard(monkeypatch):
    """Model-phrased goals never match exactly; word overlap must catch them."""
    _events(monkeypatch, [{
        "kind": "anticipy_says", "decision": "act", "created": NOW,
        "goal": "Make a dinner reservation for 2 people at Cactus Club "
                "Park Royal for tomorrow at 7 PM"}])
    assert W.already_raised(
        "book dinner for two at Cactus Club Park Royal tomorrow 7 PM",
        decision="act")


def test_a_different_errand_still_gets_its_text(monkeypatch):
    _events(monkeypatch, [{
        "kind": "anticipy_says", "decision": "act", "created": NOW,
        "goal": "book dinner at Cactus Club tomorrow at 7 PM"}])
    assert not W.already_raised(
        "cancel the gym membership this week", decision="act")


def test_overheard_texts_obey_quiet_hours(monkeypatch):
    class FakeDT:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 8, 5, 23, 30, tzinfo=tz)

    monkeypatch.setattr(W, "datetime", FakeDT)
    # "defer", never False: quiet hours are NOT NOW, and a plain False reads
    # as a dedupe refusal downstream — the core would cancel the card and a
    # plan made at midnight would silently vanish.
    assert W.SPEAK_ONCE("caught your plan", "book dinner", "ambient_act") == "defer"


def test_direct_asks_text_at_any_hour(monkeypatch):
    class FakeDT:
        @staticmethod
        def now(tz=None):
            return datetime(2026, 8, 5, 23, 30, tzinfo=tz)

    monkeypatch.setattr(W, "datetime", FakeDT)
    _events(monkeypatch, [])
    assert W.SPEAK_ONCE("on it", "book dinner", "act") is True


# ---- browser is a TARGET, not a topic -----------------------------------

def test_browser_as_target_routes_to_chrome():
    for line in ("open Wikipedia in my browser",
                 "pull up the menu in a new tab",
                 "open Chrome and go to the dashboard"):
        assert _BROWSER_TARGET_RE.search(line), line


def test_browser_as_topic_stays_on_the_server():
    for line in ("research the best Chrome extensions for note taking",
                 "look up why my browser keeps crashing",
                 "compare Safari and Firefox market share"):
        assert not _BROWSER_TARGET_RE.search(line), line
    os.environ["BRAVE_API_KEY"] = "x"
    try:
        assert job_lane("research the best Chrome extensions") == "research"
    finally:
        del os.environ["BRAVE_API_KEY"]
