"""An account with nobody to text spent hours paying for sentences.

Live, 2026-08-22, on a real account with no phone number on it, this pair of
lines repeated in the log every single sweep for hours:

    NO OWNER PHONE on this account — composed but NOT sent: 'the invoice
    email to Devon is drafted and waiting in your gmail drafts.'
    result for dxrx1q9y0tcx8ld: send failed, not recording it as said

Both notification sites composed FIRST, with a live model call, and only then
asked the transport to deliver. notify_owner refuses a message when a
transport is configured and the person's number is missing. The old caller
treated that exactly like a transient Twilio failure and deliberately recorded
nothing, so the identical sentence was recomposed at model prices every two
seconds.

Now the app result is primary and independent of SMS. The transport gets at
most one best-effort attempt, with its attempted/sent/failed/skipped outcome
recorded separately; an uncertain external effect is never blindly repeated.
The assertions here pin both the model cost and the one-attempt boundary.
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
        return types.SimpleNamespace(text="that's done, the invoice is drafted")


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
    """Reads return these jobs and no events; writes succeed."""
    monkeypatch.setattr(W.pb, "get", lambda url, **kw: Resp(
        {"items": [] if "/collections/events/" in url else [dict(j)
                                                            for j in jobs]}))
    monkeypatch.setattr(W.pb, "post", lambda *a, **k: Resp())
    monkeypatch.setattr(W.pb, "patch", lambda *a, **k: Resp())


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


# ------------------------------------------- an account nobody can be reached on

def test_an_unreachable_owner_costs_at_most_one_compose(monkeypatch, capsys):
    """The exact production loop. Six sweeps of the same finished job on an
    account with no number: before this guard that was six model calls, and
    in production it ran for hours."""
    daytime(monkeypatch)
    a, llm, voice = brain(monkeypatch)
    backend(monkeypatch, [stamped(FINISHED)])
    for _ in range(6):
        W.report_finished_jobs(a)
    assert llm.calls <= 1, (
        f"paid for {llm.calls} sentences that could never be delivered")
    assert voice.sent == [], "there is no number to send to"


def test_an_unreachable_owner_is_never_composed_for_again(monkeypatch):
    """(b) of the same failure: whatever the first sweep decides to do, later
    sweeps must not go back to the model about it."""
    daytime(monkeypatch)
    a, llm, voice = brain(monkeypatch)
    backend(monkeypatch, [stamped(FINISHED)])
    W.report_finished_jobs(a)
    after_first = llm.calls
    for _ in range(5):
        W.report_finished_jobs(a)
    assert llm.calls == after_first, (
        "the account cannot change between sweeps — this is the hours-long "
        "token burn of 2026-08-22")
    assert FINISHED["id"] in W.REPORTED, (
        "undeliverable is handled, not retried forever")


def test_the_unreachable_account_is_reported_once_not_every_cycle(
        monkeypatch, capsys):
    daytime(monkeypatch)
    a, _, _ = brain(monkeypatch)
    backend(monkeypatch, [stamped(FINISHED)])
    for _ in range(6):
        W.report_finished_jobs(a)
    log = capsys.readouterr().out
    assert log.count("nowhere to go") == 1, (
        "the hours of repeating log lines were the visible half of this bug")


# ------------------------------ an optional text failure stays honest and safe

def test_a_transient_send_failure_keeps_the_app_result_and_does_not_repeat(monkeypatch):
    """A number is configured and Twilio throws. The result is still delivered
    in app, and an uncertain external effect is never repeated blindly."""
    daytime(monkeypatch)
    a, llm, voice = brain(monkeypatch, phone="+15145550101", fails=True)
    backend(monkeypatch, [stamped(FINISHED)])
    for _ in range(3):
        W.report_finished_jobs(a)
    assert llm.calls == 1
    assert voice.attempts == 1
    assert FINISHED["id"] in W.REPORTED

    # Recovery changes future work, not this already-attempted external effect.
    voice.fails = False
    W.report_finished_jobs(a)
    assert voice.sent == []
    assert voice.attempts == 1


def test_a_reachable_owner_is_still_told(monkeypatch):
    """The guard must not become a mute: a normal account still gets its
    answer, and only one copy of it."""
    daytime(monkeypatch)
    a, llm, voice = brain(monkeypatch, phone="+15145550101")
    backend(monkeypatch, [stamped(FINISHED)])
    for _ in range(4):
        W.report_finished_jobs(a)
    assert len(voice.sent) == 1
    assert llm.calls == 1


def test_a_rig_with_no_transport_at_all_is_untouched(monkeypatch):
    """notify_owner treats a Twilio-less dev rig as a truthy no-op, on purpose,
    so her voice survives there. That must not be mistaken for an unreachable
    owner and silenced."""
    daytime(monkeypatch)
    llm = CountingLLM()
    a = Anticipy(memory=Memory(":memory:"), llm=llm, backend_url="http://pb",
                 voice=None, owner_phone="", owner_id="own1", owner_ref="")
    backend(monkeypatch, [stamped(FINISHED)])
    W.report_finished_jobs(a)
    assert llm.calls == 1, "a dev rig still composes and still 'delivers'"
    assert FINISHED["id"] in W.REPORTED


# --------------------------------------------- the same shape on the stuck path

def test_a_stuck_job_ask_is_not_recomposed_for_an_unreachable_owner(
        monkeypatch, capsys):
    """worker.py's second copy of the loop: 'stuck job ...: send failed, not
    recording it as said', every sweep, each one paying for a paraphrase."""
    a, llm, voice = brain(monkeypatch)
    backend(monkeypatch, [stamped(STUCK)])
    for _ in range(6):
        W.ask_about_stuck_jobs(a, convo=None)
    assert llm.calls == 0, (
        f"paid for {llm.calls} asks with nowhere to send them")
    assert voice.sent == []
    assert capsys.readouterr().out.count("nowhere to send this") == 1


def test_a_stuck_job_ask_still_retries_a_transient_failure(monkeypatch):
    a, llm, voice = brain(monkeypatch, phone="+15145550101", fails=True)
    backend(monkeypatch, [stamped(STUCK)])
    W.ask_about_stuck_jobs(a, convo=None)
    assert llm.calls >= 1
    voice.fails = False
    W.ask_about_stuck_jobs(a, convo=None)
    assert voice.sent, "the ask must go out once the transport is back"


def test_a_number_arriving_mid_window_unblocks_the_stuck_ask(monkeypatch):
    """The undeliverable note is held under its own key, never under the key
    the real send uses — so adding a phone to the account speaks at once
    instead of waiting out a 45-minute suppression it never earned."""
    a, llm, voice = brain(monkeypatch)
    backend(monkeypatch, [stamped(STUCK)])
    W.ask_about_stuck_jobs(a, convo=None)
    assert voice.sent == [] and llm.calls == 0
    a.owner_phone = "+15145550101"
    W.ask_about_stuck_jobs(a, convo=None)
    assert len(voice.sent) == 1, "a reachable owner waits for nothing"
