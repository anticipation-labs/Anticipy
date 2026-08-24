"""The ask valve: the middle answer must be reachable — and GOVERNED.

The recorded day: 2026-08-23, 137 decisions, 131 ignore, 6 act, ZERO ask.
A goalless ambient ask fell to "stays ambient" and died with its question.
Now the core PARKS one question and the worker SENDS it — into real quiet
only, daylight only, counted against the daily uninvited cap, deduped
against what she actually sent, durably recorded, backed off on failure.
Every one of those adverbs is a reviewed finding from the Law-6 pass that
refused to ship the first version of this valve.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.pb as pb
import brain.worker as worker
from brain.anticipy_core import Anticipy, Decision
from brain.asking import question_line


class _Resp:
    ok = True
    status_code = 200
    def __init__(self, payload=None): self._p = payload or {"items": [], "id": "j1"}
    def json(self): return self._p
    def raise_for_status(self): return None


class _ScriptedBrain:
    def __init__(self, decision): self._d = decision
    def triage(self, line, candidates=0, explicit=False): return self._d


def _anticipy(monkeypatch, decision, sent):
    monkeypatch.setattr(pb, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(pb, "post", lambda *a, **k: _Resp({"id": "j1"}))
    monkeypatch.setattr(pb, "patch", lambda *a, **k: _Resp())
    a = Anticipy(backend_url="http://dead", owner_ref="test-owner")
    a.brain = _ScriptedBrain(decision)
    monkeypatch.setattr(a, "notify_owner",
                        lambda text, channel="sms": sent.append(text) or {"ok": 1})
    return a


def _quiet_worker(monkeypatch, recorded, uninvited=0, said=False):
    """Worker conditions where a parked ask is ALLOWED out."""
    monkeypatch.setattr(worker, "MEETING_ARMED", False)
    monkeypatch.setattr(worker, "LAST_HEARD_AT",
                        time.time() - worker.ASK_QUIET_S - 5)
    # Push quiet hours out of reach so wall-clock never decides a test.
    monkeypatch.setattr(worker, "CLOCK_QUIET_START", 25)
    monkeypatch.setattr(worker, "CLOCK_QUIET_END", 0)
    monkeypatch.setattr(worker, "uninvited_sent_today",
                        lambda owner_ref="": uninvited)
    monkeypatch.setattr(worker, "already_said",
                        lambda text, within_hours=24.0, owner_ref="": said)
    monkeypatch.setattr(worker, "post_event",
                        lambda *a, **k: recorded.append((a, k)))


def _ask(missing, addressee="person", owes="owner"):
    return Decision(decision="ask", goal=None, reason="one unknown blocks",
                    addressee=addressee, owes=owes, missing=missing)


def _park(monkeypatch, sent, missing=None, **kw):
    a = _anticipy(monkeypatch, _ask(missing or ["which garage do you use"],
                                    **kw), sent)
    a.hear("I keep meaning to get the brakes looked at",
           may_say=lambda *ar, **kws: True)
    return a


def test_goalless_ambient_ask_parks_and_says_nothing_inline(monkeypatch):
    sent = []
    a = _park(monkeypatch, sent)
    assert a._pending_ask is not None
    assert "garage" in a._pending_ask[0]
    assert sent == []


def test_worker_sends_once_records_it_and_clears(monkeypatch):
    sent, recorded = [], []
    a = _park(monkeypatch, sent)
    _quiet_worker(monkeypatch, recorded)
    worker.maybe_ask_parked(a)
    assert len(sent) == 1 and "garage" in sent[0]
    assert a._pending_ask is None
    # The durable record: kind anticipy_says, decision ask — what the feed
    # renders, the dedupe reads, and the uninvited counter counts.
    assert recorded and recorded[0][0][0] == "anticipy_says"
    assert recorded[0][1].get("decision") == "ask" or recorded[0][0][2] == "ask"
    worker.maybe_ask_parked(a)
    assert len(sent) == 1


def test_recent_speech_keeps_it_parked(monkeypatch):
    sent, recorded = [], []
    a = _park(monkeypatch, sent)
    _quiet_worker(monkeypatch, recorded)
    monkeypatch.setattr(worker, "LAST_HEARD_AT", time.time() - 20)
    worker.maybe_ask_parked(a)
    assert sent == [] and a._pending_ask is not None


def test_quiet_hours_keep_it_parked(monkeypatch):
    sent, recorded = [], []
    a = _park(monkeypatch, sent)
    _quiet_worker(monkeypatch, recorded)
    monkeypatch.setattr(worker, "CLOCK_QUIET_START", 0)
    monkeypatch.setattr(worker, "CLOCK_QUIET_END", 24)
    worker.maybe_ask_parked(a)
    assert sent == [] and a._pending_ask is not None


def test_daily_cap_drops_it(monkeypatch):
    sent, recorded = [], []
    a = _park(monkeypatch, sent)
    _quiet_worker(monkeypatch, recorded, uninvited=worker.UNINVITED_TEXTS_PER_DAY)
    worker.maybe_ask_parked(a)
    assert sent == [] and a._pending_ask is None


def test_already_said_drops_it(monkeypatch):
    sent, recorded = [], []
    a = _park(monkeypatch, sent)
    _quiet_worker(monkeypatch, recorded, said=True)
    worker.maybe_ask_parked(a)
    assert sent == [] and a._pending_ask is None


def test_failed_send_backs_off_then_retries(monkeypatch):
    sent, recorded = [], []
    a = _park(monkeypatch, sent)
    _quiet_worker(monkeypatch, recorded)
    monkeypatch.setattr(a, "notify_owner", lambda text, channel="sms": None)
    worker.maybe_ask_parked(a)
    assert a._pending_ask is not None
    # Immediately again: inside the retry backoff, nothing happens.
    calls = []
    monkeypatch.setattr(a, "notify_owner",
                        lambda text, channel="sms": calls.append(text) or {"ok": 1})
    worker.maybe_ask_parked(a)
    assert calls == []
    # Past the backoff: it sends.
    text, stamped, _ = a._pending_ask
    a._pending_ask = (text, stamped, time.time() - worker.ASK_RETRY_S - 1)
    worker.maybe_ask_parked(a)
    assert len(calls) == 1 and a._pending_ask is None


def test_no_transport_clears_without_claiming_asked(monkeypatch):
    sent, recorded = [], []
    a = _park(monkeypatch, sent)
    _quiet_worker(monkeypatch, recorded)
    monkeypatch.setattr(a, "notify_owner",
                        lambda text, channel="sms": {"skipped": "no transport"})
    worker.maybe_ask_parked(a)
    assert a._pending_ask is None
    assert recorded == [], "a question no phone received must not be recorded as asked"


def test_stale_questions_expire_unasked(monkeypatch):
    sent, recorded = [], []
    a = _park(monkeypatch, sent)
    _quiet_worker(monkeypatch, recorded)
    text, _, _ = a._pending_ask
    a._pending_ask = (text, time.time() - 601, 0.0)
    worker.maybe_ask_parked(a)
    assert a._pending_ask is None and sent == []


def test_meeting_arming_cancels_the_parked_question(monkeypatch):
    sent = []
    a = _park(monkeypatch, sent)
    assert a._pending_ask is not None
    a.hear("yeah so as I was saying about the quarterly numbers",
           may_say=lambda *ar, **kw: True, in_meeting=True)
    assert a._pending_ask is None


def test_a_held_card_supersedes_the_question(monkeypatch):
    sent = []
    a = _park(monkeypatch, sent)
    assert a._pending_ask is not None
    a._queue_job("dinner at Earls Thursday 7pm",
                 {"source": "x", "lane": "desk"}, hold=True)
    assert a._pending_ask is None


def test_first_parked_wins(monkeypatch):
    sent = []
    a = _park(monkeypatch, sent)
    first = a._pending_ask[0]
    a.brain = _ScriptedBrain(_ask(["what colour was it"]))
    a.hear("hmm the thing from earlier", may_say=lambda *ar, **kw: True)
    assert a._pending_ask[0] == first


def test_owes_other_never_parks(monkeypatch):
    sent = []
    a = _park(monkeypatch, sent, owes="other")
    assert a._pending_ask is None


def test_dictation_asks_still_die(monkeypatch):
    sent = []
    a = _park(monkeypatch, sent, addressee="dictation")
    assert a._pending_ask is None


def test_question_quality_filters():
    # Junk is dropped, not rendered; third-person subjects are dropped, not
    # texted to the owner about himself; nothing left means silence.
    assert question_line([None, 42, {"gap": "t"}, "what night works"]) \
        == "quick one — what night works?"
    assert question_line(["which garage he uses"]) == ""
    assert question_line(["which", "the", ""]) == ""


def test_unspeakable_missing_stays_silent(monkeypatch):
    sent = []
    a = _park(monkeypatch, sent, missing=["which"])
    assert a._pending_ask is None


def test_third_person_passes_through_when_composer_is_live():
    # Triage narrates from outside; with a live composer between this text
    # and his phone, the item survives and the composer speaks properly.
    assert "he uses" in question_line(["which garage he uses"],
                                      third_person_ok=True)
    # Degraded path (no composer): silence beats third person to his face.
    assert question_line(["which garage he uses"]) == ""


def test_parked_digest_waits_for_a_dead_room(monkeypatch):
    """An overnight-parked digest must not fire into his 8 AM call."""
    sent = []
    a = _anticipy(monkeypatch, _ask(["x"]), sent)
    a._meeting_held = [("j1", "book the venue")]
    monkeypatch.setattr(worker, "CLOCK_QUIET_START", 25)
    monkeypatch.setattr(worker, "CLOCK_QUIET_END", 0)
    monkeypatch.setattr(worker, "SPEAK_ONCE", lambda *a_, **k: True)
    worker.DIGEST_PENDING = ("While you were talking...", time.time() - 60,
                             0.0, [("j1", "book the venue")])
    # Room is live: armed, or someone spoke seconds ago -> nothing sends.
    monkeypatch.setattr(worker, "MEETING_ARMED", True)
    worker.deliver_pending_digest(a)
    assert sent == [] and worker.DIGEST_PENDING is not None
    monkeypatch.setattr(worker, "MEETING_ARMED", False)
    monkeypatch.setattr(worker, "LAST_HEARD_AT", time.time() - 5)
    worker.deliver_pending_digest(a)
    assert sent == [] and worker.DIGEST_PENDING is not None
    # Dead room: it sends and clears ONLY its own snapshot.
    monkeypatch.setattr(worker, "LAST_HEARD_AT",
                        time.time() - worker.ASK_QUIET_S - 5)
    a._meeting_held.append(("j2", "the NEW meeting's card"))
    worker.deliver_pending_digest(a)
    assert len(sent) == 1
    assert worker.DIGEST_PENDING is None
    assert a._meeting_held == [("j2", "the NEW meeting's card")], (
        "an older digest's delivery wiped a newer meeting's held cards")
    worker.DIGEST_PENDING = None


def test_invited_questions_do_not_burn_the_uninvited_cap(monkeypatch):
    """A direct-lane sufficiency question (carries the job's goal) is the
    OPPOSITE of uninvited; only goal-less parked asks count."""
    rows = [
        {"decision": "ask", "goal": "", "params": ""},          # parked: counts
        {"decision": "ask", "goal": "book Cactus Club", "params": ""},  # invited
        {"decision": "done", "goal": "g", "params": "uninvited fyi"},   # counts
        {"decision": "done", "goal": "g", "params": ""},        # plain FYI: no
    ]
    class R:
        ok = True
        def json(self): return {"items": rows}
    monkeypatch.setattr(worker.pb, "get", lambda *a, **k: R())
    assert worker.uninvited_sent_today("o") == 2
