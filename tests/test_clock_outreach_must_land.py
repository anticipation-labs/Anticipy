"""A clock reminder that did not arrive is not a reminder.

clock_tick called notify_owner(say) and threw the answer away, then returned
its dict regardless. The caller (worker.py) treats any truthy return as
delivered: it stamps last_outreach_ts, writes the loop ids into
reached_loop_ids permanently, and posts an anticipy_says event with
decision="clock" — which is the durable record already_raised reads, so the
goal is immunised against every future SPEAK_ONCE.

One transient Twilio 500 at the clock moment and that reminder is dead
forever: he never received it, it can never fire again, and the four-hour
outreach budget was spent on nothing. Every other send path in worker.py
guards on this return; the clock lane was the last one recording blind.
"""
import json

from brain.anticipy_core import Anticipy
from brain.memory import Memory


class WantsToReachOut:
    def chat(self, system, user, **kw):
        class R:
            text = json.dumps({
                "initiate": True,
                "say": "Did you ever get that dinner booked?",
                "goal": None,
                "loop_ids": [],
            })
        return R()


def _brain():
    mem = Memory(":memory:")
    cur = mem.db.execute(
        "INSERT INTO episodes(ts, text) VALUES (1000, 'I need to book dinner')")
    eid = cur.lastrowid
    mem.db.execute(
        "INSERT INTO nodes (type, name, created_ts, last_seen_ts, status, attrs) "
        "VALUES ('commitment', 'book dinner', 1000, 1000, 'open', ?)",
        (json.dumps({"source_episode": eid}),))
    mem.db.commit()
    return Anticipy(memory=mem, llm=WantsToReachOut(), owner_id="t")


def test_a_failed_send_is_not_reported_as_outreach():
    a = _brain()
    a.notify_owner = lambda message, channel="sms": None   # Twilio 500
    assert a.clock_tick(now=2000) is None, \
        "nothing may be stamped as reached for a text he never got"


def test_a_delivered_send_still_reports_normally():
    a = _brain()
    sent = []
    a.notify_owner = lambda message, channel="sms": sent.append(message) or {
        "sid": "SM1"}
    out = a.clock_tick(now=2000)
    assert out and out["say"] == "Did you ever get that dinner booked?"
    assert sent == ["Did you ever get that dinner booked?"]


def test_a_rig_with_no_transport_is_not_a_failed_send():
    """notify_owner returns {"skipped": "no transport"} on dev and test rigs,
    and her feed voice has to survive there — only an ATTEMPTED send that
    errored returns None."""
    a = _brain()
    a.notify_owner = lambda message, channel="sms": {"skipped": "no transport"}
    assert a.clock_tick(now=2000) is not None


def test_no_reachable_phone_means_no_hidden_clock_card(monkeypatch):
    """A configured SMS lane with no destination cannot silently fill the app
    with work that was supposed to be introduced by a text."""
    a = _brain()
    a.conversation = object()       # a real transport exists
    a.owner_phone = ""              # but there is nowhere to send
    monkeypatch.setattr(
        a, "_queue_job",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("unreachable outreach must not queue work")))
    assert a.clock_tick(now=2000) is None
