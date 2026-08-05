"""Brief 01, lane routing: read-only goals -> the research lane (worker);
anything consequential -> the browser lane, held behind the confirmation
gate. No Brave key -> everything stays in the browser lane."""
import json

import brain.anticipy_core as core
from brain.anticipy_core import Anticipy, job_lane


def test_read_only_goals_get_the_research_lane():
    for goal in ("research: opening hours of the Vancouver aquarium",
                 "look up the ferry schedule to Nanaimo",
                 "check pricing on flights to Montreal",
                 "compare hotel prices in Tofino",
                 "find a well-rated ramen place near the office"):
        assert job_lane(goal) == "research", goal


def test_consequential_goals_keep_the_browser_lane():
    for goal in ("book a table at Cactus Club for 7:30",
                 "send the pitch deck to Marcus",
                 "buy more coffee beans",
                 "sign up for the newsletter",
                 "draft_and_send_document"):
        assert job_lane(goal) == "", goal


def test_a_goal_that_reads_both_ways_is_browser():
    # "find … and book …" leaves his world; the consequential reading wins.
    assert job_lane("find a flight to Montreal and book the cheapest") == ""
    assert job_lane("research restaurants and reserve one for Friday") == ""


def test_explicit_browser_navigation_uses_the_browser_arm():
    for goal in ("open Wikipedia in my browser",
                 "go to the dashboard in Chrome",
                 "show the article in a new tab"):
        assert job_lane(goal) == "", goal
    assert job_lane("open Wikipedia") == "research"
    assert job_lane("open Wikipedia", {"source": "open it in my browser"}) == ""


def _queue(monkeypatch, goal, key="test-key"):
    """Drive _queue_job with pb mocked; returns the record it would create."""
    if key is None:
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    else:
        monkeypatch.setenv("BRAVE_API_KEY", key)
    posted = {}

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "j1"}

    def fake_post(url, **kw):
        posted.update(kw.get("json") or {})
        return R()

    monkeypatch.setattr(core.pb, "post", fake_post)
    a = Anticipy(owner_id="own1")
    monkeypatch.setattr(a, "_same_pending", lambda goal: None)
    a._queue_job(goal, {"source": "test", "now": "now"})
    return posted


def test_queue_stamps_explicit_browser_navigation_on_browser_lane(monkeypatch):
    posted = _queue(monkeypatch, "open Wikipedia in my browser")
    assert posted["lane"] == ""
    assert posted["status"] == "queued"


def test_queue_stamps_the_research_lane(monkeypatch):
    posted = _queue(monkeypatch,
                    "research: opening hours of the Vancouver aquarium")
    assert posted["lane"] == "research"
    assert posted["status"] == "queued"      # read-only is never held
    assert posted["owner"] == "own1"         # scoping identical to every job


def test_queue_holds_consequential_goals_in_the_browser_lane(monkeypatch):
    posted = _queue(monkeypatch, "book a table at Cactus Club")
    assert posted["lane"] == ""
    assert posted["status"] == "awaiting_confirm"


def test_no_brave_key_falls_back_to_the_browser_lane(monkeypatch):
    posted = _queue(monkeypatch,
                    "research: opening hours of the Vancouver aquarium",
                    key=None)
    assert posted["lane"] == ""              # graceful: extension runs it
    assert posted["status"] == "queued"


def test_an_sms_ask_is_marked_on_the_job(monkeypatch):
    """channel rides in params so the finished answer can go back in-thread
    instead of landing silently on the desk."""
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")
    posted = {}

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "j1"}

    monkeypatch.setattr(core.pb, "post",
                        lambda url, **kw: (posted.update(kw.get("json") or {}),
                                           R())[1])
    a = Anticipy(owner_id="own1")
    monkeypatch.setattr(a, "_same_pending", lambda goal: None)
    # No LLM: the deterministic path acts on a fresh commitment.
    out = a.hear("I'll send you the pitch deck after this call.",
                 channel="sms")
    assert out["decision"].decision == "act"
    assert json.loads(posted["params"])["channel"] == "sms"


def test_a_pendant_line_carries_no_channel(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")
    posted = {}

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "j1"}

    monkeypatch.setattr(core.pb, "post",
                        lambda url, **kw: (posted.update(kw.get("json") or {}),
                                           R())[1])
    a = Anticipy(owner_id="own1")
    monkeypatch.setattr(a, "_same_pending", lambda goal: None)
    a.hear("I'll send you the pitch deck after this call.")
    assert "channel" not in json.loads(posted["params"])
