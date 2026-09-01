"""Answers that were computed and then thrown away, and texts that repeated.

Five separate ways the brain destroyed work it had already done, all found in
one sweep and all pinned here:

  1. report_finished_jobs read ONE page of the ten newest finished rows. A
     finished job's `updated` never moves again, so after a burst of more
     than ten (the 38-job backlog replay) jobs 11..N were never fetched at
     all and aged out of the 12h window unannounced.
  2. Delivery was deduped with already_raised(), whose overlap is measured
     over the SHORTER goal — so "weather in Montreal this Sunday" scored
     0.67 against yesterday's "look up weather in Montreal" and the answer
     was destroyed, not deferred.
  3. A research job the worker claimed and never finished sat at `running`
     forever: the pass polls only `queued`, and the stall report skips this
     lane on purpose because it never needs his Chrome.
  4. It was claimed under a 120s lease that was never heartbeated, while the
     run itself routinely passes two minutes — so the backend refused the
     `done` write and the answer was discarded.
  5. Every notification site sent the text and wrote the durable dedupe
     record second, and every guard reads only that record. A PocketBase
     write outage therefore turned one notification into one text every two
     seconds.
"""
import json
import types
from datetime import datetime, timedelta, timezone

import pytest

import brain.worker as W
from brain.workflow import (Consequence, from_params, new_plan, put_in_params)


@pytest.fixture(autouse=True)
def clean_process_state():
    W.REPORTED.clear()
    W._SENT_RECENTLY.clear()
    W._last_blocker.clear()
    yield
    W.REPORTED.clear()
    W._SENT_RECENTLY.clear()
    W._last_blocker.clear()


class Resp:
    def __init__(self, payload=None, ok=True):
        self.ok = ok
        self.status_code = 200 if ok else 409
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("write refused")


def anticipy(notified):
    return types.SimpleNamespace(
        owner_id="own1", owner_ref="", backend_url="http://pb", llm=None,
        _voice=lambda ctx: None,
        notify_owner=lambda msg, channel="sms": (notified.append(msg),
                                                 {"ok": 1})[1])


def daytime(monkeypatch):
    """Take the wall clock out of it: quiet hours are not what is on test."""
    monkeypatch.setattr(W, "CLOCK_QUIET_START", 25)
    monkeypatch.setattr(W, "CLOCK_QUIET_END", 0)


# ---------------------------------------------------------------- 1. the page

def paged_jobs(monkeypatch, jobs, per_page=None, events=()):
    """A jobs collection that pages exactly like PocketBase does."""
    size = per_page or W.FINISHED_PER_PAGE
    asked = []

    def fake_get(url, **kw):
        params = kw.get("params") or {}
        if "/collections/events/" in url:
            return Resp({"items": list(events)})
        page = int(params.get("page") or 1)
        rows = sorted(jobs, key=lambda j: j["updated"])
        if str(params.get("sort") or "").startswith("-"):
            rows = list(reversed(rows))
        start = (page - 1) * size
        asked.append(page)
        return Resp({
            "items": rows[start:start + size],
            "page": page,
            "perPage": size,
            "totalItems": len(rows),
            "totalPages": max(1, -(-len(rows) // size)),
        })

    monkeypatch.setattr(W.pb, "get", fake_get)
    monkeypatch.setattr(W.pb, "post", lambda *a, **k: Resp())
    return asked


def a_backlog(count):
    base = datetime.now(timezone.utc) - timedelta(hours=6)
    return [{"id": f"j{n:02d}", "goal": f"look up thing number {n}",
             "result": f"answer number {n}", "status": "done", "lane": "",
             "params": "{}", "owner": "own1",
             "updated": (base + timedelta(minutes=n)).strftime("%Y-%m-%d %H:%M:%S")}
            for n in range(25)]


def test_a_backlog_bigger_than_one_page_is_fully_announced(monkeypatch):
    """The 38-job replay. With a single newest-first page of ten, jobs 11..N
    were never even fetched — they aged out of the window with no text, no
    feed event and no log line."""
    daytime(monkeypatch)
    notified = []
    paged_jobs(monkeypatch, a_backlog(25), per_page=10)
    W.report_finished_jobs(anticipy(notified))
    assert len(notified) == 25, "the backlog must drain, not re-read its edge"
    assert len(W.REPORTED) == 25


def test_the_oldest_finished_work_is_announced_first(monkeypatch):
    """Answers arrive in the order they finished. Newest-first paging read
    the edge of the burst and left the oldest — the ones closest to falling
    out of the window — for a page nobody ever asked for."""
    daytime(monkeypatch)
    notified = []
    paged_jobs(monkeypatch, a_backlog(25), per_page=10)
    W.report_finished_jobs(anticipy(notified))
    assert notified[0] == "answer number 0"
    assert notified[-1] == "answer number 24"


# ------------------------------------------------- 2. a resembling question

YESTERDAY = [{"kind": "anticipy_says", "decision": "done",
              "goal": "look up weather in Montreal",
              "text": "18 and clear", "created": "2026-08-16 19:00:00"}]


def test_a_new_question_is_not_silenced_by_a_similar_old_answer(monkeypatch):
    """He asked "weather in Montreal" on Monday evening and "weather in
    Montreal this Sunday" on Tuesday morning. Token overlap over the shorter
    goal scores 0.67, so the second answer was added to REPORTED and dropped:
    no text, no feed event, nothing. That is the three-silent-weather-
    questions failure this whole function exists to end."""
    daytime(monkeypatch)
    notified = []
    job = {"id": "j1", "goal": "weather in Montreal this Sunday",
           "result": "Sunday: 22 and sunny", "status": "done", "lane": "",
           "params": "{}", "owner": "own1",
           "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}
    paged_jobs(monkeypatch, [job], events=YESTERDAY)
    W.report_finished_jobs(anticipy(notified))
    assert notified == ["Sunday: 22 and sunny"]


def test_the_same_answer_is_still_never_delivered_twice(monkeypatch):
    """The guard still has to hold across a restart, where REPORTED is gone:
    the SAME job re-read carries a byte-identical goal."""
    daytime(monkeypatch)
    notified = []
    job = {"id": "j1", "goal": "look up weather in Montreal",
           "result": "18 and clear", "status": "done", "lane": "",
           "params": "{}", "owner": "own1",
           "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}
    delivered = {
        "kind": "anticipy_says", "decision": "done",
        "goal": job["goal"], "text": job["result"],
        "external_event_id": "job-result:j1",
    }
    attempted = {
        "kind": "notification_status", "decision": "sms_attempted",
        "goal": "j1", "external_event_id": "job-sms:j1:sms_attempted",
    }
    paged_jobs(monkeypatch, [job], events=[delivered, attempted])
    W.report_finished_jobs(anticipy(notified))
    assert notified == []
    assert "j1" in W.REPORTED


def test_two_jobs_with_identical_goals_each_deliver_once(monkeypatch):
    """Human wording is not an idempotency key. Two separately created jobs
    can legitimately ask the same thing and both outcomes must survive."""
    daytime(monkeypatch)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    jobs = [
        {"id": "same-a", "goal": "send the team sync note",
         "result": "first note sent", "status": "done", "lane": "",
         "params": "{}", "owner": "own1", "updated": now},
        {"id": "same-b", "goal": "send the team sync note",
         "result": "second note sent", "status": "done", "lane": "",
         "params": "{}", "owner": "own1", "updated": now},
    ]
    events = []
    notified = []

    def fake_get(url, **kw):
        if "/collections/events/" in url:
            filt = str((kw.get("params") or {}).get("filter") or "")
            return Resp({"items": [row for row in events
                                   if row.get("external_event_id")
                                   and str(row["external_event_id"]) in filt]})
        return Resp({"items": [dict(row) for row in jobs], "totalPages": 1})

    def fake_post(url, **kw):
        events.append(dict(kw.get("json") or {}))
        return Resp()

    monkeypatch.setattr(W.pb, "get", fake_get)
    monkeypatch.setattr(W.pb, "post", fake_post)

    W.report_finished_jobs(anticipy(notified))
    assert notified == ["first note sent", "second note sent"]
    assert [row.get("external_event_id") for row in events
            if row.get("kind") == "anticipy_says"] == [
                "job-result:same-a", "job-result:same-b"]

    W.REPORTED.clear()
    W.report_finished_jobs(anticipy(notified))
    assert notified == ["first note sent", "second note sent"]


# ------------------------------------------- 3. + 4. the stranded research job

STRANDED = {"id": "r9", "goal": "research: aquarium hours",
            "status": "running", "lane": "research",
            "claimed_by": W.RESEARCH_CLAIMANT, "params": "{}",
            "owner": "own1", "lease_token": ""}


def test_a_research_job_a_dead_worker_left_running_is_handed_back(monkeypatch):
    """A redeploy is a SIGTERM. Nothing anywhere recovered the row: the pass
    polls status="queued" only, report_stalled_work skips this lane because
    it never needs his Chrome, and the extension's sweep needs Chrome open —
    the one thing this lane exists not to need."""
    patches = []
    monkeypatch.setattr(W.pb, "get",
                        lambda *a, **k: Resp({"items": [dict(STRANDED)]}))

    def fake_patch(url, **kw):
        patches.append(kw.get("json") or {})
        return Resp()
    monkeypatch.setattr(W.pb, "patch", fake_patch)

    assert W.release_stranded_research(anticipy([])) == 1
    assert patches[0]["status"] == "queued"
    assert patches[0]["claimed_by"] == ""


def test_the_sweep_only_takes_back_claims_this_worker_abandoned(monkeypatch):
    """A live run, and a browser-lane job, must both be left alone."""
    seen = {}

    def fake_get(url, **kw):
        seen["filter"] = (kw.get("params") or {}).get("filter", "")
        return Resp({"items": []})
    monkeypatch.setattr(W.pb, "get", fake_get)
    W.release_stranded_research(anticipy([]))
    assert f'claimed_by="{W.RESEARCH_CLAIMANT}"' in seen["filter"]
    assert 'lane="research"' in seen["filter"]
    assert "updated<=" in seen["filter"], "a live run must never be swept"


def test_a_stranded_workflow_plan_is_recovered_not_just_restatused(monkeypatch):
    """The row and its embedded plan are checked against each other by the
    backend, so a bare status flip is rejected — and the job stays stuck."""
    plan = new_plan(owner_ref="owner-a", lineage_key="c1",
                    goal="research: aquarium hours",
                    consequence=Consequence.READ_ONLY, source_event_id="e1")
    claimed = W.claim_plan(plan, expected_version=plan.version,
                           actor_id=W.RESEARCH_CLAIMANT, lease_seconds=5,
                           now=datetime.now(timezone.utc) - timedelta(hours=1))
    row = dict(STRANDED, params=json.dumps(put_in_params({}, claimed)),
               lease_token=claimed.lease.token)
    patches, headers = [], []
    monkeypatch.setattr(W.pb, "get", lambda *a, **k: Resp({"items": [row]}))

    def fake_patch(url, **kw):
        patches.append(kw.get("json") or {})
        headers.append(kw.get("headers") or {})
        return Resp()
    monkeypatch.setattr(W.pb, "patch", fake_patch)

    assert W.release_stranded_research(anticipy([])) == 1
    recovered = from_params(json.loads(patches[0]["params"]))
    assert recovered.state.value == "queued"
    assert recovered.lease is None
    assert patches[0]["lease_token"] == ""
    assert headers[0]["X-Anticipy-Lease"] == claimed.lease.token


def test_the_research_lease_outlives_a_real_research_run(monkeypatch):
    """Brave (15s) + three page fetches (12s each) + an LLM summarize (60s,
    with a fallback client) passes 120s routinely, and nothing heartbeats.
    Past the lease the backend refuses the `done` write outright: the answer
    was computed, refused, and thrown away."""
    plan = new_plan(owner_ref="owner-a", lineage_key="c1",
                    goal="research: aquarium hours",
                    consequence=Consequence.READ_ONLY, source_event_id="e1")
    row = {"id": "r1", "goal": plan.goal, "status": "queued",
           "lane": "research", "claimed_by": "", "owner": "own1",
           "params": json.dumps(put_in_params({}, plan))}
    state = dict(row)
    patches = []
    monkeypatch.setenv("BRAVE_API_KEY", "k")

    def fake_get(url, **kw):
        filt = (kw.get("params") or {}).get("filter", "")
        if "/collections/events/" in url:
            return Resp({"items": []})
        if url.endswith("/records"):
            if 'status="running"' in filt:
                return Resp({"items": []})
            return Resp({"items": [dict(state)]})
        return Resp(dict(state))

    def fake_patch(url, **kw):
        body = kw.get("json") or {}
        patches.append(body)
        state.update(body)
        return Resp()

    monkeypatch.setattr(W.pb, "get", fake_get)
    monkeypatch.setattr(W.pb, "patch", fake_patch)
    monkeypatch.setattr(W.pb, "post", lambda *a, **k: Resp())
    W.run_research_jobs(
        anticipy([]),
        runner=lambda *a, **k: {"ok": True,
                                "result": "Open daily. https://example.test/h"})

    running = from_params(json.loads(patches[0]["params"]))
    held = (running.lease.expires_at - running.lease.acquired_at).total_seconds()
    assert held >= 300, f"a {held:.0f}s lease cannot cover a real research run"


# ------------------------------------------------- 5. the write-outage storm

STUCK = {"id": "s1", "goal": "Book lunch at Earls for tomorrow at noon",
         "result": "I need your birthday to finish the reservation.",
         "status": "needs_user", "params": "{}", "owner": "own1"}


def blind_backend(monkeypatch, jobs, writes_fail=True):
    """Reads keep working, writes do not — a PB restart, or the nightly
    backup holding the write lock. Exactly the shape that made one
    notification into one text every two seconds."""
    monkeypatch.setattr(W.pb, "get", lambda url, **kw: Resp(
        {"items": [] if "/collections/events/" in url else list(jobs)}))
    monkeypatch.setattr(W.pb, "post",
                        lambda *a, **k: Resp(ok=not writes_fail))
    monkeypatch.setattr(W.pb, "patch", lambda *a, **k: Resp())


def test_a_write_outage_cannot_turn_one_question_into_a_text_storm(monkeypatch):
    """Anticipy texts "I need your birthday"; post_event raises; nothing is
    recorded. Two seconds later every durable guard says "never asked" and
    the identical text goes out again, and again, for the whole outage."""
    notified = []
    blind_backend(monkeypatch, [STUCK])
    for _ in range(8):
        W.ask_about_stuck_jobs(anticipy(notified), convo=None)
    assert len(notified) == 1, f"sent it {len(notified)} times in one outage"


def test_a_write_outage_cannot_repeat_a_finished_answer(monkeypatch):
    """With no durable store, do not create an un-fenceable SMS effect. The
    terminal job remains visible in Done and delivery resumes once writes do."""
    daytime(monkeypatch)
    notified = []
    job = {"id": "j1", "goal": "book the table", "result": "Booked for 7:30.",
           "status": "done", "lane": "", "params": "{}", "owner": "own1",
           "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}
    blind_backend(monkeypatch, [job])
    for _ in range(8):
        W.report_finished_jobs(anticipy(notified))
    assert notified == []
    assert "j1" not in W.REPORTED

    blind_backend(monkeypatch, [job], writes_fail=False)
    W.report_finished_jobs(anticipy(notified))
    assert notified == ["Booked for 7:30."]
    assert "j1" in W.REPORTED


@pytest.mark.parametrize("job", [
    {"id": "ambient-1", "goal": "look up the team sync venue",
     "result": "The venue closes at ten.", "status": "done", "lane": "",
     "params": json.dumps({"lane": "ambient"}), "owner": "own1"},
    {"id": "research-1", "goal": "research the team sync venue",
     "result": "The venue closes at ten.", "status": "done",
     "lane": "research", "params": "{}", "owner": "own1"},
])
def test_app_only_lanes_retry_the_feed_without_ever_texting(monkeypatch, job):
    """Ambient and non-SMS research are quiet by contract. A feed outage
    keeps the exact result retryable; it never turns the retry into a text or
    marks a result delivered before storage accepts it."""
    daytime(monkeypatch)
    job = dict(job, updated=datetime.now(timezone.utc)
               .strftime("%Y-%m-%d %H:%M:%S"))
    feed = []
    writes_fail = {"value": True}
    notified = []

    def fake_get(url, **kw):
        if "/collections/events/" in url:
            filt = str((kw.get("params") or {}).get("filter") or "")
            return Resp({"items": [row for row in feed
                                   if row.get("external_event_id")
                                   and str(row["external_event_id"]) in filt]})
        return Resp({"items": [dict(job)], "totalPages": 1})

    def fake_post(url, **kw):
        if writes_fail["value"]:
            return Resp(ok=False)
        feed.append(dict(kw.get("json") or {}))
        return Resp()

    monkeypatch.setattr(W.pb, "get", fake_get)
    monkeypatch.setattr(W.pb, "post", fake_post)

    for _ in range(3):
        W.report_finished_jobs(anticipy(notified))
    assert notified == []
    assert job["id"] not in W.REPORTED
    assert feed == []

    writes_fail["value"] = False
    W.report_finished_jobs(anticipy(notified))
    assert notified == []
    assert job["id"] in W.REPORTED
    assert [row.get("external_event_id") for row in feed] == [
        f"job-result:{job['id']}"]

    W.REPORTED.clear()
    W.report_finished_jobs(anticipy(notified))
    assert len(feed) == 1
    assert notified == []


def test_a_write_outage_cannot_repeat_a_stall_notice(monkeypatch):
    """The app notice is primary: a failed feed write permits no SMS effect.

    Once storage recovers the notice lands first and the optional copy may go
    out once.  This is stronger than the old send-first suppression, which
    still left the app silent and could not prove delivery across a restart.
    """
    daytime(monkeypatch)
    notified = []
    job = {"id": "j1", "goal": "book the table", "status": "queued",
           "params": "{}", "owner": "own1"}
    blind_backend(monkeypatch, [job])
    monkeypatch.setattr(W, "browser_reachable", lambda *a, **k: False)
    for _ in range(8):
        W.report_stalled_work(anticipy(notified))
    assert notified == []

    blind_backend(monkeypatch, [job], writes_fail=False)
    W.report_stalled_work(anticipy(notified))
    assert len(notified) == 1


def test_a_genuinely_new_requirement_still_speaks_at_once(monkeypatch):
    """The guard fires on what was actually said, not on the job — the most
    important message this path sends is a NEW blocker on a job she has
    already asked about, and a job-keyed suppression would eat it."""
    notified = []
    blind_backend(monkeypatch, [STUCK])
    W.ask_about_stuck_jobs(anticipy(notified), convo=None)
    moved_on = dict(STUCK, result="the form needs a phone number to hold it")
    blind_backend(monkeypatch, [moved_on])
    W.ask_about_stuck_jobs(anticipy(notified), convo=None)
    assert len(notified) == 2


def test_the_local_suppression_expires(monkeypatch):
    """It must not become the permanent mute. A still-parked job gets its
    three-hour second chance, so this window has to be shorter than that."""
    assert W.SEND_SUPPRESS_SECONDS < 3 * 3600
    W.mark_sent("k", now=1000.0)
    assert W.sent_moments_ago("k", now=1000.0 + W.SEND_SUPPRESS_SECONDS - 1)
    assert not W.sent_moments_ago("k", now=1000.0 + W.SEND_SUPPRESS_SECONDS + 1)
