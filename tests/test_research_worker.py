"""Brief 01, the worker side: the research pass claims lane="research" jobs
the way the extension claims its own (stamp, read back, walk away if the
stamp did not survive), runs the executor, and the result is a DESK
delivery — an event in the feed, never an SMS, unless the ask itself came
in over SMS."""
import inspect
import json
import types

import pytest

import brain.worker as W


@pytest.fixture(autouse=True)
def clean_reported():
    W.REPORTED.clear()
    yield
    W.REPORTED.clear()


class Resp:
    def __init__(self, payload=None, ok=True):
        self.ok = ok
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def make_anticipy(notified):
    return types.SimpleNamespace(
        owner_id="own1", backend_url="http://pb", llm=None,
        _voice=lambda ctx: None,
        notify_owner=lambda msg, channel="sms": (notified.append(msg), {"ok": 1})[1])


def wire(monkeypatch, job, patches, posts, key="test-key", stamp_survives=True):
    """Point brain.pb at an in-memory job row; record every write."""
    if key is None:
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    else:
        monkeypatch.setenv("BRAVE_API_KEY", key)
    state = dict(job)

    def fake_get(url, **kw):
        if "/collections/events/" in url:
            return Resp({"items": []})
        if url.endswith("/records"):
            fake_get.filters.append((kw.get("params") or {}).get("filter", ""))
            return Resp({"items": [dict(state)]})
        return Resp(dict(state))
    fake_get.filters = []

    def fake_patch(url, **kw):
        body = kw.get("json") or {}
        patches.append(body)
        if stamp_survives:
            state.update(body)
        return Resp()

    def fake_post(url, **kw):
        posts.append(kw.get("json") or {})
        return Resp()

    monkeypatch.setattr(W.pb, "get", fake_get)
    monkeypatch.setattr(W.pb, "patch", fake_patch)
    monkeypatch.setattr(W.pb, "post", fake_post)
    return fake_get


QUEUED = {"id": "r1", "goal": "research: opening hours of the aquarium",
          "params": json.dumps({"source": "test", "now": "now"}),
          "status": "queued", "lane": "research", "claimed_by": "",
          "owner": "own1"}


def test_claims_like_the_extension_then_writes_the_answer(monkeypatch):
    patches, posts, ran = [], [], []
    fake_get = wire(monkeypatch, QUEUED, patches, posts)

    def runner(goal, params, llm=None, api_key=None):
        ran.append((goal, api_key))
        return {"ok": True, "result": "Open 9:30-5:30 [1]\n\nSources:\n[1] x"}

    W.run_research_jobs(make_anticipy([]), runner=runner)
    # Owner-scoped, lane-scoped poll — identical scoping to every other job.
    assert 'lane="research"' in fake_get.filters[0]
    assert 'owner="own1"' in fake_get.filters[0]
    # Stamp, then the answer on the job row.
    assert patches[0]["status"] == "running"
    assert patches[0]["claimed_by"] == W.RESEARCH_CLAIMANT
    assert patches[1]["status"] == "done"
    assert "Sources:" in patches[1]["result"]
    assert ran and ran[0][1] == "test-key"


def test_a_lost_claim_race_means_walking_away(monkeypatch):
    patches, posts, ran = [], [], []
    # The stamp never lands (someone else's survived the read-back).
    wire(monkeypatch, dict(QUEUED, claimed_by="ext-abc"), patches, posts,
         stamp_survives=False)
    W.run_research_jobs(make_anticipy([]),
                        runner=lambda *a, **k: ran.append(1) or {"ok": True, "result": "x"})
    assert not ran                       # never ran a job it does not own
    assert len(patches) == 1             # only the claim attempt


def test_no_key_hands_the_job_to_the_browser_lane(monkeypatch):
    patches, posts, ran = [], [], []
    wire(monkeypatch, QUEUED, patches, posts, key=None)
    W.run_research_jobs(make_anticipy([]),
                        runner=lambda *a, **k: ran.append(1) or {"ok": True, "result": "x"})
    assert not ran                       # graceful fallback, not a crash
    assert patches == [{"lane": ""}]     # the extension will pick it up


def test_a_failed_run_is_written_as_failed(monkeypatch):
    patches, posts = [], []
    wire(monkeypatch, QUEUED, patches, posts)
    W.run_research_jobs(make_anticipy([]),
                        runner=lambda *a, **k: {"ok": False, "result": "Found nothing."})
    assert patches[1]["status"] == "failed"
    assert patches[1]["result"] == "Found nothing."


DONE = {"id": "r1", "goal": "research: opening hours of the aquarium",
        "params": json.dumps({"source": "test", "now": "now"}),
        "status": "done", "lane": "research",
        "result": "Open 9:30-5:30 daily [1].\n\nSources:\n[1] Hours — https://x",
        "claimed_by": "worker-research", "owner": "own1"}


def test_research_results_land_on_the_desk_not_his_phone(monkeypatch):
    patches, posts, notified = [], [], []
    wire(monkeypatch, DONE, patches, posts)
    W.report_finished_jobs(make_anticipy(notified))
    assert notified == []                       # desk delivery: no SMS
    assert posts, "no conversation entry was written"
    assert posts[0]["kind"] == "anticipy_says"
    assert posts[0]["decision"] == "done"
    assert "Sources:" in posts[0]["text"]       # the feed card IS the answer
    assert "r1" in W.REPORTED                   # and it is never re-delivered


def test_an_sms_ask_is_answered_in_thread(monkeypatch):
    patches, posts, notified = [], [], []
    sms_job = dict(DONE, params=json.dumps(
        {"source": "what time does the aquarium close", "channel": "sms"}))
    wire(monkeypatch, sms_job, patches, posts)
    W.report_finished_jobs(make_anticipy(notified))
    assert len(notified) == 1                   # he asked by text; answer by text
    assert "Sources:" in notified[0]


def test_a_failed_research_job_still_reaches_the_desk(monkeypatch):
    patches, posts, notified = [], [], []
    failed = dict(DONE, status="failed", result="")
    wire(monkeypatch, failed, patches, posts)
    W.report_finished_jobs(make_anticipy(notified))
    assert notified == []
    assert posts and "Couldn't get there" in posts[0]["text"]


def test_browser_lane_results_still_get_texted(monkeypatch):
    """The existing behavior is untouched: a done browser job is reported to
    the owner exactly as before the research lane existed."""
    patches, posts, notified = [], [], []
    browser_done = dict(DONE, lane="", result="Booked for 7:30.")
    wire(monkeypatch, browser_done, patches, posts)
    W.report_finished_jobs(make_anticipy(notified))
    assert len(notified) == 1
    assert "Booked" in notified[0]


def test_stalled_work_never_flags_the_research_lane(monkeypatch):
    """'I just need your Chrome open' about a research job would be a false
    alarm — this same process runs that lane."""
    monkeypatch.setattr(W, "browser_reachable", lambda: False)
    # Disable quiet hours so the test does not depend on the wall clock.
    monkeypatch.setattr(W, "CLOCK_QUIET_START", 25)
    monkeypatch.setattr(W, "CLOCK_QUIET_END", 0)
    seen = {}

    def fake_get(url, **kw):
        seen["filter"] = (kw.get("params") or {}).get("filter", "")
        return Resp({"items": []})

    monkeypatch.setattr(W.pb, "get", fake_get)
    W.report_stalled_work(make_anticipy([]))
    assert 'lane!="research"' in seen["filter"]


def test_the_worker_loop_actually_runs_the_research_pass():
    src = inspect.getsource(W.main)
    assert "run_research_jobs(anticipy)" in src
