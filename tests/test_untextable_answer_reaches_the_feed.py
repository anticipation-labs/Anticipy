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
import types

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

    def text(self, to, message):
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
                 "goal": FINISHED["goal"], "text": "already on his feed"}
    monkeypatch.setattr(W.pb, "get", lambda url, **kw: Resp(
        {"items": [delivered] if "/collections/events/" in url
         else [stamped(FINISHED)]}))
    posted = []
    monkeypatch.setattr(W.pb, "post", lambda url, **kw: (
        posted.append(url), Resp())[1])
    monkeypatch.setattr(W.pb, "patch", lambda *a, **k: Resp())

    W.report_finished_jobs(a)

    assert posted == [], "already delivered is already delivered"
    assert llm.calls == 0


# ------------------------------------------------------ nothing else may move

def test_a_reachable_owner_still_gets_the_text_and_one_feed_row(monkeypatch):
    """The existing behaviour, unchanged: the text is the delivery and the
    feed row is the record. Exactly one of each, however many sweeps run."""
    daytime(monkeypatch)
    a, llm, voice = brain(monkeypatch, phone="+15145550101")
    feed = backend(monkeypatch, [stamped(FINISHED)])

    for _ in range(4):
        W.report_finished_jobs(a)

    assert len(voice.sent) == 1, "he is textable; the text is the delivery"
    assert len(says(feed)) == 1
    assert llm.calls == 1


def test_a_transient_send_failure_still_retries_and_writes_nothing(monkeypatch):
    """The reason REPORTED was only ever set after a successful send. A Twilio
    5xx must not be mistaken for an untextable account: no feed row, not
    marked reported, and the answer goes out when the transport returns."""
    daytime(monkeypatch)
    a, llm, voice = brain(monkeypatch, phone="+15145550101", fails=True)
    feed = backend(monkeypatch, [stamped(FINISHED)])

    for _ in range(3):
        W.report_finished_jobs(a)

    assert says(feed) == [], (
        "a feed row is a record that she spoke — she did not, and writing one "
        "would make already_delivered swallow the answer for 24 hours")
    assert FINISHED["id"] not in W.REPORTED, "a 5xx is not a delivery"
    assert llm.calls == 3

    voice.fails = False
    W.report_finished_jobs(a)
    assert len(voice.sent) == 1, "the recovered send must deliver"
    assert len(says(feed)) == 1
    assert FINISHED["id"] in W.REPORTED, "delivered once, never twice"


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
