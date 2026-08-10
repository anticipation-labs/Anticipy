"""A card she was not allowed to talk about does not get to exist.

2026-08-07, live, and the worst failure of the day. He told Priya, out loud,
"I'll send it to your email." Anticipy built the job and HELD it for his
approval — correct so far. Then the anti-nag guard refused the text:

    quiet: already put this to him twice with no answer
        -> 'Draft email to Priya with deck attached'
    heard: "...we really love your deck for sure let's do the deck
            I'll send it to your email" -> act (Draft email to Priya with deck attached)

The card stayed on his desk. He approved something nobody had ever told him
about, and it opened Gmail.

THE STRUCTURAL FAULT, and it is the same one behind half the incidents in this
repo: the job is queued BEFORE the speech is decided, and every guard here
silences her MOUTH — never her HANDS. That makes the worst possible outcome the
default one: she does something real and says nothing about it.

So silence and stillness are now the same thing. A held card she may not raise
is cancelled, not parked.

THE EXCEPTION THAT MUST SURVIVE: when he TEXTS her, conversation.py passes a
deliberately muted guard (may_say=quiet, explicit=True) because it delivers her
words itself, in-thread. Cancelling there would break the SMS lane outright.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import pb  # noqa: E402
from brain.anticipy_core import Anticipy, is_consequential  # noqa: E402
from brain.memory import Memory  # noqa: E402
from brain.orchestrator import Decision  # noqa: E402

GOAL = "Draft email to Priya with deck attached"
LINE = "we really love your deck for sure let's do the deck I'll send it to your email"

SAY_NOTHING = lambda *a, **k: False      # noqa: E731  the anti-nag guard, refusing
SAY_IT = lambda *a, **k: True            # noqa: E731


class _Reply:
    def __init__(self, payload):
        self._p, self.ok = payload, True

    def json(self):
        return self._p

    def raise_for_status(self):
        return None


class Fake:
    """An in-memory jobs table. Never the shared backend."""

    def __init__(self):
        self.jobs = []

    def get(self, url, params=None, timeout=None, **k):
        want = [s for s in ("awaiting_confirm", "queued")
                if s in (params or {}).get("filter", "")]
        return _Reply({"items": [j for j in self.jobs if j.get("status") in want]})

    def post(self, url, json=None, timeout=None, **k):
        rec = dict(json or {})
        rec["id"] = f"j{len(self.jobs) + 1}"
        self.jobs.append(rec)
        return _Reply(rec)

    def patch(self, url, json=None, timeout=None, **k):
        jid = url.rstrip("/").rsplit("/", 1)[-1]
        for j in self.jobs:
            if j.get("id") == jid:
                j.update(json or {})
        return _Reply({})

    # what the app would actually show him
    def cards(self):
        return [j for j in self.jobs
                if j.get("status") in ("awaiting_confirm", "needs_user")]


class DeadMemory(Memory):
    def __init__(self):
        pass

    def ingest(self, *a, **k):
        return {}

    def recall(self, *a, **k):
        return []


def _anticipy(monkeypatch, decision):
    fake = Fake()
    monkeypatch.setattr(pb, "get", fake.get)
    monkeypatch.setattr(pb, "post", fake.post)
    monkeypatch.setattr(pb, "patch", fake.patch)
    a = Anticipy(memory=DeadMemory(), owner_id="silence")
    monkeypatch.setattr(a, "_decide", lambda *args, **kw: decision)
    monkeypatch.setattr(a, "_voice", lambda *a_, **k_: "i'm on it, ok to send?")
    sent = []
    a.notify_owner = lambda m, channel="sms": (sent.append(m), True)[1]
    return a, fake, sent


def _act(goal=GOAL):
    return Decision(decision="act", goal=goal, reason="he committed to it",
                    addressee="person")


# ------------------------------------------------------------ the failure

def test_a_card_he_was_never_told_about_does_not_survive(monkeypatch):
    """THE PRIYA FAILURE. Held, silenced, and left approvable."""
    assert is_consequential(GOAL), "this test is meaningless if the job is not held"
    a, fake, sent = _anticipy(monkeypatch, _act())
    a.hear(LINE, may_say=SAY_NOTHING)
    assert sent == [], "the guard was supposed to keep her quiet"
    assert fake.cards() == [], \
        f"a card he was never told about is still on his desk: {fake.cards()}"
    assert fake.jobs and fake.jobs[0]["status"] == "cancelled"


def test_the_cancelled_row_says_why(monkeypatch):
    """Cancelled, never deleted — the record must still explain itself."""
    a, fake, _ = _anticipy(monkeypatch, _act())
    a.hear(LINE, may_say=SAY_NOTHING)
    assert (fake.jobs[0].get("result") or "").strip(), "no reason on the cancellation"


# --------------------------------------------------- what must NOT change

def test_when_she_is_allowed_to_speak_the_card_stays(monkeypatch):
    a, fake, sent = _anticipy(monkeypatch, _act())
    a.hear(LINE, may_say=SAY_IT)
    assert len(sent) == 1, sent
    assert len(fake.cards()) == 1, "the card he WAS told about vanished"
    assert fake.jobs[0]["status"] == "awaiting_confirm"


def test_a_text_he_sent_her_is_never_cancelled(monkeypatch):
    """THE SMS LANE. conversation.py mutes the guard on purpose
    (may_say=quiet, explicit=True) because it delivers her words in-thread
    itself. Cancelling on that silence would break texting entirely.

    Asserted on the job, not on cards: an explicit request is not "held for
    approval" at all — he just asked for it — so it is queued to run and was
    never a card. What matters is only that it SURVIVES.
    """
    a, fake, sent = _anticipy(monkeypatch, _act())
    a.hear(LINE, may_say=SAY_NOTHING, explicit=True)
    assert fake.jobs, "the SMS lane produced no job at all"
    assert all(j.get("status") != "cancelled" for j in fake.jobs), \
        f"an SMS-lane job was cancelled — this kills the whole texting lane: {fake.jobs}"


def test_a_repeat_of_a_card_he_already_knows_about_is_left_alone(monkeypatch):
    """Second mention of the same plan merges into the existing card. He was
    told the first time, so there is nothing silent about it — cancelling
    would delete a card he is actively waiting on."""
    a, fake, sent = _anticipy(monkeypatch, _act())
    a.hear(LINE, may_say=SAY_IT)                 # told about it
    assert len(fake.cards()) == 1 and len(sent) == 1
    a.hear(LINE, may_say=SAY_NOTHING)            # mentioned again, stays quiet
    assert len(fake.cards()) == 1, \
        "the merge path cancelled a card he already knows about"
    assert fake.jobs[0]["status"] == "awaiting_confirm"


def test_quiet_research_is_untouched(monkeypatch):
    """Unheld work is free, silent and additive by design — it was never
    waiting on him, so there is nothing to cancel."""
    goal = "Research the best noise cancelling headphones under 400 dollars"
    assert not is_consequential(goal)
    a, fake, sent = _anticipy(monkeypatch, _act(goal))
    a.hear("i should look at headphones", may_say=SAY_NOTHING)
    assert all(j.get("status") != "cancelled" for j in fake.jobs), fake.jobs


def test_an_explicit_request_that_IS_held_still_survives(monkeypatch):
    """The SMS test above never exercised the risk: an explicit ask is not
    held, so `elif held` could not fire either way and a mutation that
    cancelled explicit jobs sailed through it.

    This forces the combination that actually matters — he texted her AND the
    plan needs his confirmation — and proves the muted SMS guard still cannot
    destroy it."""
    d = Decision(decision="act", goal=GOAL, reason="he asked",
                 addressee="assistant", needs_confirmation=True)
    a, fake, sent = _anticipy(monkeypatch, d)
    a.hear(LINE, may_say=SAY_NOTHING, explicit=True)
    assert fake.jobs, "no job at all"
    assert all(j.get("status") != "cancelled" for j in fake.jobs), \
        f"a HELD job he asked for over SMS was cancelled: {fake.jobs}"


def test_the_plain_act_lane_also_cancels_a_silent_card(monkeypatch):
    """Not everything goes through the ambient lane. Thinking aloud
    (addressee="self") lands in the plain act branch, and a silenced held card
    there is the same failure — proved by behaviour, not by grepping."""
    d = Decision(decision="act", goal=GOAL, reason="he committed to it",
                 addressee="self", needs_confirmation=True)
    a, fake, sent = _anticipy(monkeypatch, d)
    # The line must NAME Priya. GOAL does, and when the heard line does not,
    # the invented-name guard turns this act into an ask before the act branch
    # is ever reached — which is why the first version of this test passed
    # even with the cancel removed.
    a.hear("i'll send Priya the deck to her email", may_say=SAY_NOTHING)
    assert sent == []
    assert fake.cards() == [], \
        f"the plain act lane left a card he was never told about: {fake.cards()}"


def test_a_failed_send_keeps_the_card(monkeypatch):
    """NOT ALLOWED TO SPEAK and TRIED AND FAILED TO SPEAK are different.

    The first version of this fix collapsed them into one branch, so a Twilio
    failure destroyed the card. It took both live proof families down at once
    (dinner 0/3, earls 0/3): their harness returns None from notify_owner, the
    `and` short-circuited, and every real booking was cancelled.

    A refused guard means he will never hear about it, so the card must go. A
    failed send means the card is real and merely undelivered — it has to
    survive for the retry.
    """
    a, fake, sent = _anticipy(monkeypatch, _act())
    a.notify_owner = lambda m, channel="sms": False      # allowed, but it failed
    out = a.hear(LINE, may_say=SAY_IT)
    assert fake.jobs, "no job at all"
    assert all(j.get("status") != "cancelled" for j in fake.jobs), \
        f"a real booking was destroyed by a failed text: {fake.jobs}"
    assert len(fake.cards()) == 1, "the card must stand so a retry can reach him"
    assert not out.get("anticipy_says"), \
        "nothing was delivered, so nothing may be recorded as said"


# ------------------------------------------------------------- the wall

def test_a_failing_cancel_never_takes_hearing_down(monkeypatch):
    a, fake, _ = _anticipy(monkeypatch, _act())

    def boom(*a_, **k_):
        raise RuntimeError("backend down")
    monkeypatch.setattr(pb, "patch", boom)
    out = a.hear(LINE, may_say=SAY_NOTHING)          # must not raise
    assert out and "decision" in out


def test_cancel_is_safe_on_junk():
    a = Anticipy(memory=DeadMemory(), owner_id="x")
    for jid in (None, "", 0, False):
        assert a._cancel_job(jid, "why") is False


def test_the_exception_is_keyed_on_explicit_not_on_the_guard(monkeypatch):
    """If this ever keys on may_say instead of explicit, the SMS lane and the
    anti-nag guard become indistinguishable and one of them breaks."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    # The ambient lane is where the Priya card was built, and it is keyed on
    # `fresh` — a plan firming up merges into its existing card and never
    # reaches the cancel.
    amb = src.index('"ambient_act")')
    block = src[amb:amb + 3400]
    assert "_cancel_job" in block, "the ambient lane still leaves silent cards"
    assert "if fresh:" in src[:amb], "the cancel must sit behind the fresh check"
    # And the plain act lane, which handles self-talk and direct asks.
    i = src.index("elif held and not explicit:")
    assert "_cancel_job" in src[i:i + 2600]
    assert src.index("elif held and repeat:") < i, \
        "the repeat case must be handled before the cancel case"


def test_quiet_hours_defer_keeps_the_card_and_sends_nothing(monkeypatch):
    """NOT NOW is not NEVER. A plan made at midnight gets a card that waits
    for morning; before "defer" existed, the quiet-hours refusal read as a
    dedupe refusal and the cancel branch destroyed every late-night plan."""
    a, fake, sent = _anticipy(monkeypatch, _act())
    a.hear(LINE, may_say=lambda *a_, **k_: "defer")
    assert sent == [], "quiet hours must send nothing"
    assert len(fake.cards()) == 1, "the midnight plan's card must survive"
    assert fake.jobs[0]["status"] == "awaiting_confirm"
