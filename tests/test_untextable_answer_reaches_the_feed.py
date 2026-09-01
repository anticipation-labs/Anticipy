"""Real work finished, and nobody was ever told.

Live, 2026-08-22. An owner_profile row with a timezone on it and nothing else
— no first_name, no email, no phone — got a job, and the job REALLY RAN: the
browser drafted the invoice email to Devon in the owner's own Gmail. Then the
brain composed "the invoice email to Devon is waiting in your gmail drafts",
notify_owner refused it for want of a number, the job was deliberately left
out of REPORTED so a failed send could retry, and two seconds later the whole
thing happened again. For hours. One paid model call per sweep.

The first fix stopped the burn by deciding deliverability BEFORE composing
(can_reach_owner -> Anticipy.can_notify_owner) and treating "no phone" as
handled rather than as a failure to retry. That killed the loop and the wasted
calls, and it must stay killed. But it fixed the cheaper half: the ANSWER was
still thrown away, so a person whose errand was genuinely done still learned
nothing, through any channel, ever.

There is a channel. anticipy_says events are the app feed; the phone renders
them; a feed write needs no phone number and no Twilio. The research lane in
this same function has always delivered that way on purpose ("never an SMS").
So an owner with no number is not unreachable, only untextable: compose once,
put the answer on the feed, record it as said — because this time it was.

What is on test here is that it lands EXACTLY ONCE across many sweeps, and at
the cost of EXACTLY ONE model call, because "record nothing on failure" is the
whole reason the loop existed in the first place.
"""
import threading
import types
from concurrent.futures import ThreadPoolExecutor

import pytest

import brain.worker as W
from brain.anticipy_core import Anticipy
from brain.memory import Memory


@pytest.fixture(autouse=True)
def clean_process_state():
    W.REPORTED.clear()
    W._SENT_RECENTLY.clear()
    W._last_blocker.clear()
    yield
    W.REPORTED.clear()
    W._SENT_RECENTLY.clear()
    W._last_blocker.clear()


class CountingLLM:
    """Every .chat is a sentence someone paid for."""

    def __init__(self):
        self.calls = 0

    def chat(self, system, user, **kw):
        self.calls += 1
        return types.SimpleNamespace(
            text="the invoice email to Devon is waiting in your gmail drafts")


class Twilio:
    """A configured transport. `fails` is the 5xx / dropped-connection case."""

    def __init__(self, fails=False):
        self.fails = fails
        self.sent = []
        self.attempts = 0

    def text(self, to, message):
        self.attempts += 1
        if self.fails:
            raise RuntimeError("Twilio 503")
        self.sent.append((to, message))
        return {"sid": "SM1"}

    def call(self, to, message):
        return self.text(to, message)


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


def brain(monkeypatch, phone="", fails=False):
    llm = CountingLLM()
    voice = Twilio(fails=fails)
    a = Anticipy(memory=Memory(":memory:"), llm=llm, backend_url="http://pb",
                 voice=voice, owner_phone=phone, owner_id="own1", owner_ref="")
    return a, llm, voice


def backend(monkeypatch, jobs):
    """Reads return these jobs and no events; writes succeed and are captured.

    The feed is what this file is about, so every POST to the events
    collection is kept: those rows are what the app renders.
    """
    feed = []

    def fake_get(url, **kw):
        if "/collections/events/" in url:
            return Resp({"items": []})
        return Resp({"items": [dict(j) for j in jobs]})

    def fake_post(url, **kw):
        if "/collections/events/" in url:
            feed.append(dict(kw.get("json") or {}))
        return Resp()

    monkeypatch.setattr(W.pb, "get", fake_get)
    monkeypatch.setattr(W.pb, "post", fake_post)
    monkeypatch.setattr(W.pb, "patch", lambda *a, **k: Resp())
    return feed


def says(feed):
    return [e for e in feed if e.get("kind") == "anticipy_says"]


def notification_states(feed):
    return [e.get("decision") for e in feed
            if e.get("kind") == "notification_status"]


# The real row, from the real account, on the day this happened.
FINISHED = {"id": "dxrx1q9y0tcx8ld", "goal": "email Devon the invoice",
            "result": "the invoice email to Devon is drafted",
            "status": "done", "lane": "", "params": "{}", "owner": "own1"}

STUCK = {"id": "stuck1", "goal": "book the table",
         "result": "the form needs your phone number to hold it",
         "status": "needs_user", "lane": "", "params": "{}", "owner": "own1"}


def daytime(monkeypatch):
    monkeypatch.setattr(W, "CLOCK_QUIET_START", 25)
    monkeypatch.setattr(W, "CLOCK_QUIET_END", 0)


def stamped(job):
    from datetime import datetime, timezone
    return dict(job, updated=datetime.now(timezone.utc)
                .strftime("%Y-%m-%d %H:%M:%S"))


# ------------------------------- the answer reaches him with no phone involved

def test_an_untextable_answer_still_lands_on_the_feed(monkeypatch):
    """THE BUG. Devon's invoice email was really drafted and the owner was
    never told by anything. He opens the app and the answer is there."""
    daytime(monkeypatch)
    a, llm, voice = brain(monkeypatch)
    feed = backend(monkeypatch, [stamped(FINISHED)])

    W.report_finished_jobs(a)

    assert voice.sent == [], "there is no number — nothing may be texted"
    assert len(says(feed)) == 1, (
        "finished work with nobody to text it to was discarded outright: "
        "no text, no feed event, no way for him to ever learn it happened")
    event = says(feed)[0]
    assert event["decision"] == "done"
    assert event["goal"] == FINISHED["goal"]
    assert "Devon" in event["text"], (
        "the feed row has to CARRY the answer, not merely note that one "
        f"existed: {event['text']!r}")


def test_it_lands_once_across_many_sweeps_for_one_compose(monkeypatch):
    """Doing it once is the whole point: nothing being recorded on failure is
    what made the original loop possible. The reporter runs every two seconds,
    so 'once' means once across all of them, at one model call."""
    daytime(monkeypatch)
    a, llm, voice = brain(monkeypatch)
    feed = backend(monkeypatch, [stamped(FINISHED)])

    for _ in range(6):
        W.report_finished_jobs(a)

    assert len(says(feed)) == 1, (
        f"{len(says(feed))} copies of the same answer on the feed")
    assert llm.calls == 1, (
        f"paid for {llm.calls} sentences — one per sweep is the 2026-08-22 "
        "token burn wearing a new hat")
    assert FINISHED["id"] in W.REPORTED
    assert voice.sent == []


def test_the_log_says_the_feed_not_the_text(monkeypatch, capsys):
    """Production has to be able to tell the two deliveries apart, and this
    line is the only place the difference is visible."""
    daytime(monkeypatch)
    a, _, _ = brain(monkeypatch)
    backend(monkeypatch, [stamped(FINISHED)])

    for _ in range(6):
        W.report_finished_jobs(a)

    log = capsys.readouterr().out
    assert log.count("went to the feed") == 1, (
        "one delivery, one line — and it must say which channel carried it")


def test_a_second_process_does_not_repeat_it(monkeypatch):
    """REPORTED is RAM. The durable guard is the feed row itself, which is now
    a real record of a real delivery — so a restart re-reading the same
    finished job must find the answer already delivered and stay quiet."""
    daytime(monkeypatch)
    a, llm, _ = brain(monkeypatch)
    delivered = {"kind": "anticipy_says", "decision": "done",
                 "goal": FINISHED["goal"], "text": "already on his feed",
                 "external_event_id": f"job-result:{FINISHED['id']}"}
    skipped = {"kind": "notification_status", "decision": "sms_skipped",
               "goal": FINISHED["id"],
               "external_event_id": f"job-sms:{FINISHED['id']}:sms_skipped"}

    def fake_get(url, **kw):
        if "/collections/events/" not in url:
            return Resp({"items": [stamped(FINISHED)]})
        filt = str((kw.get("params") or {}).get("filter") or "")
        rows = [row for row in (delivered, skipped)
                if row["external_event_id"] in filt]
        return Resp({"items": rows})

    monkeypatch.setattr(W.pb, "get", fake_get)
    posted = []
    monkeypatch.setattr(W.pb, "post", lambda url, **kw: (
        posted.append(url), Resp())[1])
    monkeypatch.setattr(W.pb, "patch", lambda *a, **k: Resp())

    W.report_finished_jobs(a)

    assert posted == [], "already delivered is already delivered"
    assert llm.calls == 0


# ------------------------------------------------------ nothing else may move

def test_a_reachable_owner_still_gets_the_text_and_one_feed_row(monkeypatch):
    """A reachable owner gets the primary app result and one optional text.
    Exactly one of each, however many sweeps run."""
    daytime(monkeypatch)
    a, llm, voice = brain(monkeypatch, phone="+15145550101")
    feed = backend(monkeypatch, [stamped(FINISHED)])

    for _ in range(4):
        W.report_finished_jobs(a)

    assert len(voice.sent) == 1, "he is textable; one optional copy is sent"
    assert len(says(feed)) == 1
    assert llm.calls == 1


def test_a_failed_text_never_hides_or_repeats_the_in_app_result(monkeypatch):
    """The app is the primary result channel. A Twilio 5xx is recorded as an
    attempted/failed optional copy; it cannot erase the app result or trigger
    an unsafe duplicate attempt every two seconds."""
    daytime(monkeypatch)
    a, llm, voice = brain(monkeypatch, phone="+15145550101", fails=True)
    feed = backend(monkeypatch, [stamped(FINISHED)])

    for _ in range(3):
        W.report_finished_jobs(a)

    assert len(says(feed)) == 1, "Twilio must not gate the app result"
    assert notification_states(feed) == ["sms_attempted", "sms_failed"]
    assert voice.attempts == 1, "an uncertain external effect is at-most-once"
    assert FINISHED["id"] in W.REPORTED
    assert llm.calls == 1

    voice.fails = False
    W.report_finished_jobs(a)
    assert voice.sent == [], (
        "a later sweep must not blindly repeat an SMS whose provider outcome "
        "could have been lost; the result is already available in the app")


def test_a_restart_reads_the_attempt_fence_while_retrying_the_app_feed(monkeypatch):
    """REPORTED is process memory. If the first app-feed write fails but the
    pre-SMS fence persists, a fresh worker must retry only the app result and
    must never repeat the external effect."""
    daytime(monkeypatch)
    a, llm, voice = brain(monkeypatch, phone="+15145550101", fails=True)
    stored_events = []
    app_write_fails = {"value": True}

    def fake_get(url, **kw):
        if "/collections/events/" in url:
            filt = str((kw.get("params") or {}).get("filter") or "")
            rows = [e for e in stored_events
                    if e.get("external_event_id")
                    and str(e["external_event_id"]) in filt]
            return Resp({"items": rows})
        return Resp({"items": [stamped(FINISHED)]})

    def fake_post(url, **kw):
        row = dict(kw.get("json") or {})
        if row.get("kind") == "anticipy_says" and app_write_fails["value"]:
            return Resp(ok=False)
        if "/collections/events/" in url:
            stored_events.append(row)
        return Resp()

    monkeypatch.setattr(W.pb, "get", fake_get)
    monkeypatch.setattr(W.pb, "post", fake_post)
    monkeypatch.setattr(W.pb, "patch", lambda *args, **kwargs: Resp())

    W.report_finished_jobs(a)
    assert voice.attempts == 1
    assert not says(stored_events)
    assert notification_states(stored_events) == ["sms_attempted", "sms_failed"]
    assert FINISHED["id"] not in W.REPORTED, "the missing app result must retry"

    # New process, recovered app store, recovered SMS provider. The old
    # attempted fence is the only fact preventing a duplicate text.
    W.REPORTED.clear()
    app_write_fails["value"] = False
    voice.fails = False
    W.report_finished_jobs(a)

    assert len(says(stored_events)) == 1
    assert voice.attempts == 1
    assert voice.sent == []
    assert FINISHED["id"] in W.REPORTED
    assert llm.calls == 2, "the app retry may re-compose; the SMS may not repeat"


def test_app_result_saved_before_restart_still_gets_one_optional_text(monkeypatch):
    """A crash can land after the app event and before the SMS fence. A new
    process must reuse that exact sentence, finish the optional text once, and
    never pay the model to compose a second version."""
    daytime(monkeypatch)
    a, llm, voice = brain(monkeypatch, phone="+15145550101")
    stored_events = [{
        "kind": "anticipy_says",
        "decision": "done",
        "goal": FINISHED["goal"],
        "text": "the exact sentence already visible in the app",
        "external_event_id": f"job-result:{FINISHED['id']}",
    }]

    def fake_get(url, **kw):
        if "/collections/events/" not in url:
            return Resp({"items": [stamped(FINISHED)]})
        filt = str((kw.get("params") or {}).get("filter") or "")
        return Resp({"items": [row for row in stored_events
                               if row.get("external_event_id")
                               and str(row["external_event_id"]) in filt]})

    def fake_post(url, **kw):
        stored_events.append(dict(kw.get("json") or {}))
        return Resp()

    monkeypatch.setattr(W.pb, "get", fake_get)
    monkeypatch.setattr(W.pb, "post", fake_post)
    monkeypatch.setattr(W.pb, "patch", lambda *args, **kwargs: Resp())

    W.report_finished_jobs(a)
    assert llm.calls == 0
    assert voice.sent == [(
        "+15145550101", "the exact sentence already visible in the app")]
    assert notification_states(stored_events) == ["sms_attempted", "sms_sent"]

    W.REPORTED.clear()
    W.report_finished_jobs(a)
    assert llm.calls == 0
    assert len(voice.sent) == 1


def test_two_workers_racing_the_attempt_fence_send_exactly_one_text(monkeypatch):
    """The unique event id is a claim, not merely idempotent bookkeeping.

    Both workers are forced to observe no app result and no SMS fence before
    either may create. One wins each unique insert; the loser reads the
    winner's app sentence but never inherits permission to send from the
    winner's attempt row.
    """
    daytime(monkeypatch)
    job = stamped(FINISHED)
    stored_events = []
    sent = []
    lock = threading.Lock()
    result_barrier = threading.Barrier(2)
    attempt_barrier = threading.Barrier(2)
    exact_reads = {}

    def fake_get(url, **kw):
        if "/collections/events/" not in url:
            return Resp({"items": [dict(job)], "totalPages": 1})
        filt = str((kw.get("params") or {}).get("filter") or "")
        durable_id = next((value for value in (
            f"job-result:{job['id']}",
            f"job-sms:{job['id']}:sms_attempted",
            f"job-sms:{job['id']}:sms_sent",
        ) if value in filt), "")
        with lock:
            snapshot = [dict(row) for row in stored_events
                        if durable_id and row.get("external_event_id") == durable_id]
            exact_reads[durable_id] = exact_reads.get(durable_id, 0) + 1
            read_number = exact_reads[durable_id]
        if durable_id == f"job-result:{job['id']}" and read_number <= 2:
            result_barrier.wait(timeout=5)
        if durable_id == f"job-sms:{job['id']}:sms_attempted" and read_number <= 2:
            attempt_barrier.wait(timeout=5)
        return Resp({"items": snapshot})

    def fake_post(url, **kw):
        row = dict(kw.get("json") or {})
        durable_id = row.get("external_event_id")
        with lock:
            if durable_id and any(
                    existing.get("external_event_id") == durable_id
                    for existing in stored_events):
                return Resp(ok=False)
            stored_events.append(row)
        return Resp()

    monkeypatch.setattr(W.pb, "get", fake_get)
    monkeypatch.setattr(W.pb, "post", fake_post)
    monkeypatch.setattr(W.pb, "patch", lambda *args, **kwargs: Resp())
    monkeypatch.setattr(W, "picture_for_done_text", lambda *args: [])

    def participant(draft):
        return types.SimpleNamespace(
            owner_id="own1", owner_ref="", backend_url="http://pb",
            _voice=lambda _context: draft,
            can_notify_owner=lambda: True,
            notify_owner=lambda message: (sent.append(message), {"ok": True})[1],
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(W.report_finished_jobs, participant("draft one")),
                   pool.submit(W.report_finished_jobs, participant("draft two"))]
        for future in futures:
            future.result(timeout=10)

    app_rows = [row for row in stored_events
                if row.get("external_event_id") == f"job-result:{job['id']}"]
    attempts = [row for row in stored_events
                if row.get("external_event_id") ==
                f"job-sms:{job['id']}:sms_attempted"]
    assert len(app_rows) == 1
    assert len(attempts) == 1
    assert sent == [app_rows[0]["text"]], (
        "only the attempt-claim winner may text, using the sentence that won "
        "the app-result race")


def test_an_unverified_cached_number_is_paused_and_the_app_result_still_lands(
        monkeypatch):
    """A profile read can fail after the number was removed elsewhere. The old
    cached route must not receive another task result while canonical state is
    unknown; availability falls back to the app."""
    daytime(monkeypatch)
    a, llm, voice = brain(monkeypatch, phone="+15145550101")
    monkeypatch.setattr(W, "fetch_owner_phone", lambda owner_ref="": None)

    assert W.refresh_owner_phone(a) is False
    assert a.owner_phone == ""

    feed = backend(monkeypatch, [stamped(FINISHED)])
    W.report_finished_jobs(a)

    assert voice.attempts == 0
    assert len(says(feed)) == 1
    assert notification_states(feed) == ["sms_skipped"]
    assert llm.calls == 1


def test_a_stuck_question_is_deliberately_not_pushed_to_the_feed(monkeypatch):
    """The judgement call, pinned so it is not quietly reversed.

    A parked job already shows its blocker in the app — popup.js renders the
    job's own `result` as "I stopped and I need you: ...". An anticipy_says
    copy would repeat that card, and worse: these rows ARE the durable dedup
    that need_already_asked and asks_for_goal read as proof she asked. Writing
    one while nothing was sent buys 3 hours of "already asked", so a number
    added to the account mid-window is met with silence, and a few parked
    sweeps spend the whole STUCK_ASKS_CEILING budget on questions he never
    saw. An answer has somewhere to go; a question needs a channel that can
    carry the reply back.
    """
    a, llm, voice = brain(monkeypatch)
    feed = backend(monkeypatch, [stamped(STUCK)])

    for _ in range(6):
        W.ask_about_stuck_jobs(a, convo=None)

    assert says(feed) == [], (
        "a question recorded as asked but never asked is how a parked job "
        "goes permanently quiet")
    assert llm.calls == 0
    assert voice.sent == []

    # ...and because nothing was recorded, a number arriving later still asks.
    a.owner_phone = "+15145550101"
    W.ask_about_stuck_jobs(a, convo=None)
    assert len(voice.sent) == 1, "a reachable owner waits for nothing"
    assert len(says(feed)) == 1, "now she really did ask, so now it is recorded"
