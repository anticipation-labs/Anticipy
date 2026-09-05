"""One reserved slot per uninvited text — Omi port 10b.

Omi's second proactivity ordering: the budget is RESERVED before the side
effect, never checked after it. Until 2026-09-05 the brain counted
anticipy_says rows after the fact, on one door of four (the parked ask),
fail-OPEN to zero on any read error — so a flaky PocketBase removed the cap,
two workers for one owner both read the same count and both sent, and the
clock, the overheard-plan receipt and the meeting digest never touched the
count at all: up to 4 clock nudges plus every receipt plus a digest plus 3
asks a day, none summed against the "3". The owner's words about the result:
"why is it also randomly messaging me after the fact... 90% of the time it's
bad".

Now every uninvited text takes ONE slot row first — kind="uninvited_slot",
external_event_id="uninvited:{owner}:{day}:{n}" — and the partial unique index
on external_event_id is the compare-and-set. Only the process whose CREATE got
an unambiguous 2xx may touch Twilio. Nothing is ever released: the transport
cannot prove a non-send, so a slot is burned or reused, never given back.

Every test here drives the REAL worker code (SPEAK_ONCE, maybe_ask_parked,
deliver_pending_digest, clock_should_run, reserve_uninvited_text) and, where
the door is inside the core, the real Anticipy.hear() / clock_tick(), through
the brain.pb seam with a fake store that enforces the unique index. The
transport is a lambda that logs. Twilio is never touched.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import types
from datetime import datetime, timezone

import pytest
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.pb as pb  # noqa: E402
import brain.worker as W  # noqa: E402
from brain.anticipy_core import Anticipy, is_consequential  # noqa: E402
from brain.memory import Memory  # noqa: E402
from brain.orchestrator import Decision  # noqa: E402

OWNER = "owner-10b"
CAP = W.UNINVITED_TEXTS_PER_DAY


# ------------------------------------------------------------ the fake store

class _Resp:
    def __init__(self, payload=None, ok=True, status=200):
        self.ok, self.status_code = ok, status
        self._p = payload if payload is not None else {}

    def json(self):
        return self._p

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


_CLAUSE = re.compile(r'^\s*(\w+)\s*(>=|<=|!=|=|>|<)\s*"([^"]*)"\s*$')


def _split_top(s: str, sep: str) -> list[str]:
    out, depth, cur, i = [], 0, "", 0
    while i < len(s):
        ch = s[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth == 0 and s.startswith(sep, i):
            out.append(cur)
            cur, i = "", i + len(sep)
            continue
        cur += ch
        i += 1
    out.append(cur)
    return out


def _strip_parens(s: str) -> str:
    s = s.strip()
    while s.startswith("(") and s.endswith(")"):
        inner, depth = s[1:-1], 0
        for ch in inner:
            depth += (ch == "(") - (ch == ")")
            if depth < 0:
                return s
        s = inner.strip()
    return s


def matches(row: dict, filt: str) -> bool:
    """A PocketBase filter, honoured: =, !=, >=, <=, &&, || and parens."""
    filt = _strip_parens(filt)
    if not filt.strip():
        return True
    ands = _split_top(filt, "&&")
    if len(ands) > 1:
        return all(matches(row, p) for p in ands)
    ors = _split_top(filt, "||")
    if len(ors) > 1:
        return any(matches(row, p) for p in ors)
    m = _CLAUSE.match(filt)
    if not m:
        return True
    field, op, val = m.groups()
    have = str(row.get(field) or "")
    return {"=": have == val, "!=": have != val, ">=": have >= val,
            "<=": have <= val, ">": have > val, "<": have < val}[op]


class FakeBackend:
    """PocketBase's events collection with the partial unique index on
    external_event_id (WHERE external_event_id != ''), plus a jobs table for
    the core-driven cases. Scriptable: a lost CREATE response (insert, then
    raise), an unreadable store, a hook that runs inside a GET."""

    def __init__(self):
        self.events: list[dict] = []
        self.jobs: list[dict] = []
        self.patches: list[tuple[str, dict]] = []
        self.gets = self.posts = 0
        self.lose_next_post = False
        self.gets_raise = self.gets_not_ok = self.posts_raise = False
        self.on_slot_get = None
        self._n = 0

    # -- pb seam
    def get(self, url, params=None, timeout=None, **k):
        self.gets += 1
        if self.gets_raise:
            raise requests.ConnectionError("pb down")
        if self.gets_not_ok:
            return _Resp({}, ok=False, status=502)
        filt = str((params or {}).get("filter") or "")
        table = self.jobs if "/collections/jobs/" in url else self.events
        items = [dict(r) for r in table if matches(r, filt)]
        if self.on_slot_get and 'kind="uninvited_slot"' in filt:
            hook, self.on_slot_get = self.on_slot_get, None
            hook()                      # the snapshot above is already taken
        return _Resp({"items": items})

    def post(self, url, json=None, timeout=None, **k):
        self.posts += 1
        if self.posts_raise:
            raise requests.ConnectionError("pb down")
        row = dict(json or {})
        self._n += 1
        row["id"] = f"r{self._n}"
        row["created"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S.000Z")
        if "/collections/jobs/" in url:
            self.jobs.append(row)
            return _Resp(row)
        ext = str(row.get("external_event_id") or "")
        if ext and any(e.get("external_event_id") == ext for e in self.events):
            return _Resp({"code": 400}, ok=False, status=400)
        self.events.append(row)
        if self.lose_next_post:
            self.lose_next_post = False
            raise requests.Timeout("response lost after the row committed")
        return _Resp({"id": row["id"]})

    def patch(self, url, json=None, timeout=None, **k):
        self.patches.append((url, dict(json or {})))
        jid = url.rstrip("/").rsplit("/", 1)[-1]
        for j in self.jobs:
            if j.get("id") == jid:
                j.update(json or {})
        return _Resp({})

    # -- what the tests read
    def slots(self) -> list[dict]:
        return [e for e in self.events if e.get("kind") == "uninvited_slot"]

    def slot_ns(self) -> list[int]:
        return sorted(int(e["external_event_id"].rsplit(":", 1)[1])
                      for e in self.slots())

    def said(self) -> list[dict]:
        return [e for e in self.events if e.get("kind") == "anticipy_says"]

    def seed_slots(self, n: int, owner=OWNER) -> None:
        day = W._uninvited_day()
        for i in range(1, n + 1):
            self.post("http://x/api/collections/events/records", json={
                "kind": "uninvited_slot", "decision": "seed", "owner_ref": owner,
                "external_event_id": W.uninvited_slot_id(owner, day, i)})

    def cards(self) -> list[dict]:
        return [j for j in self.jobs
                if j.get("status") in ("awaiting_confirm", "needs_user")]


@pytest.fixture
def fake(monkeypatch):
    f = FakeBackend()
    monkeypatch.setattr(pb, "get", f.get)
    monkeypatch.setattr(pb, "post", f.post)
    monkeypatch.setattr(pb, "patch", f.patch)
    monkeypatch.setattr(W, "ACTIVE_OWNER_REF", OWNER)
    monkeypatch.setattr(W, "ACTIVE_OWNER_ID", "")
    monkeypatch.setattr(W, "UNINVITED_SPENT_UNTIL", 0.0)
    monkeypatch.setattr(W, "UNINVITED_HELD_SLOT", "")
    monkeypatch.setattr(W, "MEETING_ARMED", False)
    monkeypatch.setattr(W, "LAST_HEARD_AT", 0.0)
    # Daylight, whatever the wall clock says.
    monkeypatch.setattr(W, "CLOCK_QUIET_START", 25)
    monkeypatch.setattr(W, "CLOCK_QUIET_END", 0)
    W._SENT_RECENTLY.clear()
    W.DIGEST_PENDING = None
    yield f
    W.DIGEST_PENDING = None


# ------------------------------------------------------------ the four doors

def _owner(sends: list, ok=True):
    """The minimum an Anticipy needs to be for the worker-side doors."""
    def notify_owner(text, channel="sms"):
        if ok is None:
            return None
        sends.append(text)
        return {"sid": f"SM{len(sends)}"} if ok else None
    return types.SimpleNamespace(owner_ref=OWNER, _pending_ask=None,
                                 _meeting_held=[], cleared=[],
                                 notify_owner=notify_owner,
                                 clear_meeting_held=lambda e: None)


def _park(a, text="which garage do you use?", now=None):
    a._pending_ask = (text, (now or time.time()) - 30, 0.0, "")


def _digest(text="While you were talking I got this ready: the venue.",
            now=None):
    W.DIGEST_PENDING = (text, (now or time.time()) - 60, 0.0,
                        [("j1", "book the venue")], "")


def open_door(door: str, fake: FakeBackend, sends: list) -> bool:
    """Try to send one uninvited text through `door`; did one leave?"""
    if door == "clock":
        ok = W.SPEAK_ONCE("Bins go out tonight.", "bins out", "clock")
        if ok is True:
            assert W.take_held_slot().startswith(f"uninvited:{OWNER}:")
        return ok is True
    if door == "ambient_act":
        ok = W.SPEAK_ONCE("caught your plan — want me to book?",
                          "book dinner", "ambient_act")
        if ok is True:
            assert W.take_held_slot().startswith(f"uninvited:{OWNER}:")
        return ok is True
    before = len(sends)
    a = _owner(sends)
    if door == "ask":
        _park(a, text=f"quick one — the {door} question {len(sends)}?")
        W.maybe_ask_parked(a)
        assert a._pending_ask is None, "a parked ask leaves or is dropped"
    elif door == "digest":
        _digest(text=f"digest {len(sends)}: one thing is ready.")
        W.deliver_pending_digest(a)
    return len(sends) == before + 1


DOORS = ("clock", "ambient_act", "ask", "digest")
# The slot row records the DOOR it was taken at — the `kind` SPEAK_ONCE
# received. The digest shares the overheard-plan door (kind "ambient_act");
# its said row is what carries decision "digest".
SLOT_DECISION = {"clock": "clock", "ambient_act": "ambient_act",
                 "ask": "ask", "digest": "ambient_act"}


@pytest.mark.parametrize("fourth", DOORS)
def test_four_doors_share_three_slots_and_the_fourth_is_refused(fake, fourth):
    """Whichever door the fourth text comes from, it is refused; exactly
    three slot rows exist, and the refusal cancels nothing."""
    sends: list[str] = []
    first_three = [d for d in DOORS if d != fourth]
    for door in first_three:
        assert open_door(door, fake, sends) is True, door
    assert fake.slot_ns() == [1, 2, 3]
    assert sorted(s["decision"] for s in fake.slots()) == \
        sorted(SLOT_DECISION[d] for d in first_three)

    assert open_door(fourth, fake, sends) is False, fourth
    assert fake.slot_ns() == [1, 2, 3], "a fourth slot row must be impossible"
    assert len(fake.slots()) == CAP
    if fourth == "digest":
        assert W.DIGEST_PENDING is not None, "a refused digest stays parked"
    # Every said row that was written is linked to the slot it was sent on.
    for row in fake.said():
        assert row["external_event_id"].startswith(f"uninvited:{OWNER}:")
        assert row["external_event_id"].endswith(":said")
    assert fake.patches == [], "nothing is ever released"


def test_an_ambient_refusal_is_defer_never_false(fake):
    """The core cancels the card on False (SILENCE MUST MEAN STILLNESS); a
    plan he made is real whether or not there is room to text about it."""
    fake.seed_slots(CAP)
    assert W.SPEAK_ONCE("caught your plan", "book dinner", "ambient_act") == "defer"
    assert W.SPEAK_ONCE("Bins tonight.", "bins", "clock") is False
    assert W.take_held_slot() == ""


# ------------------------------------------------------ the named mutation

def test_two_workers_cannot_send_a_fourth(fake):
    """Two slots taken. Two workers for one owner each hold a parked ask, and
    both read the slot count BEFORE either CREATE lands (worker B runs to
    completion inside worker A's count GET, after A's snapshot is taken).
    The unique index lets exactly one of them own slot 3.

    THE MUTATION: move reserve_uninvited_text after notify_owner in
    maybe_ask_parked (record-after-send, the shape this file had until
    2026-09-05) and both send — sends == 2, RED."""
    fake.seed_slots(2)
    sends: list[str] = []
    a, b = _owner(sends), _owner(sends)
    _park(a, "worker A: which garage?")
    _park(b, "worker B: which garage?")
    fake.on_slot_get = lambda: W.maybe_ask_parked(b)

    W.maybe_ask_parked(a)

    assert len(sends) == 1, f"a fourth text left: {sends}"
    assert fake.slot_ns() == [1, 2, 3]
    assert a._pending_ask is None and b._pending_ask is None, \
        "the loser's ask is dropped, the winner's is sent"
    assert [r["external_event_id"] for r in fake.said()] == [
        W.uninvited_slot_id(OWNER, W._uninvited_day(), 3) + ":said"]
    assert fake.patches == []


# ------------------------------------------------------------- the polarity

def test_an_unreadable_backend_sends_nothing_and_drops_nothing(fake):
    """Today's counter returned 0 — "nothing sent yet" — on exactly these
    errors, so the cap vanished when the server was flaky. Unknown is now
    NOT NOW: the ask stays parked, the clock stamps nothing, the card is
    deferred. The dedupe guards keep their own fail-open; the budget does
    not share it."""
    sends: list[str] = []
    for mode in ("gets_raise", "gets_not_ok"):
        setattr(fake, mode, True)
        a = _owner(sends)
        _park(a)
        W.maybe_ask_parked(a)
        assert sends == [] and a._pending_ask is not None, mode
        assert W.SPEAK_ONCE("Bins tonight.", "bins", "clock") is False, mode
        assert W.SPEAK_ONCE("caught your plan", "book dinner",
                            "ambient_act") == "defer", mode
        assert W.reserve_uninvited_text(OWNER, "ask") is None, mode
        setattr(fake, mode, False)
    assert fake.posts == 0, "nothing may be written on an unreadable day"
    assert W.uninvited_budget_spent(OWNER) is False


def test_every_pb_call_raising_never_grants_and_never_raises(fake):
    """_may_say's fail-open ("a broken guard must never silence a genuine
    message") returns True on an exception. The reservation must therefore
    never raise — a raise here would turn a dead store into a GRANT."""
    fake.gets_raise = fake.posts_raise = True
    assert W.reserve_uninvited_text(OWNER, "clock") is None
    assert W.SPEAK_ONCE("Bins tonight.", "bins", "clock") is False
    assert W.SPEAK_ONCE("caught your plan", "g", "ambient_act") == "defer"
    assert W.uninvited_budget_spent(OWNER) is None
    assert W.take_held_slot() == ""


def test_a_lost_create_response_never_sends_on_that_slot(fake):
    """The CREATE for slot 1 commits but its response is lost. This process
    cannot prove it owns slot 1, so it never sends on it: the read-back finds
    the row, slot 1 is burned for the day, and the text goes on slot 2. At
    worst one fewer text — never a fourth."""
    fake.lose_next_post = True
    assert W.SPEAK_ONCE("Bins tonight.", "bins", "clock") is True
    assert W.take_held_slot().endswith(":2")
    assert fake.slot_ns() == [1, 2]
    # The burned slot still counts: one more text, then the day is spent.
    assert W.SPEAK_ONCE("Call mum.", "call mum", "clock") is True
    assert W.take_held_slot().endswith(":3")
    assert W.SPEAK_ONCE("The dentist.", "dentist", "clock") is False
    assert fake.slot_ns() == [1, 2, 3]


def test_an_ambiguous_send_never_gives_the_slot_back(fake):
    """notify_owner returns None while the handset may already have the
    message (a socket timeout after Twilio committed is one None among a
    Twilio 4xx, a rig refusal, a missing phone and a revocation). Releasing
    on None is how three "failed" sends plus three real ones become six
    texts. Three such attempts leave three slot rows; the fourth ask is
    dropped; pb.patch is never called.

    A PATCH release reintroduced on None turns this RED."""
    attempts: list[str] = []

    def transport_logged_but_returned_none(text, channel="sms"):
        attempts.append(text)
        return None

    for i in range(CAP):
        a = _owner([])
        a.notify_owner = transport_logged_but_returned_none
        _park(a, f"question {i}?")
        W.maybe_ask_parked(a)
        assert a._pending_ask is not None and a._pending_ask[3].endswith(f":{i + 1}")
    assert len(attempts) == CAP
    assert fake.slot_ns() == [1, 2, 3]
    fourth = _owner(attempts)
    _park(fourth, "a fourth question?")
    W.maybe_ask_parked(fourth)
    assert fourth._pending_ask is None and len(attempts) == CAP
    assert fake.patches == [], "a slot is burned or reused, never released"
    assert not any(s.get("decision") == "released" for s in fake.slots())


def test_a_retried_parked_ask_reuses_its_slot(fake):
    """A blip does not spend the day: the slot follows the question. None,
    then success -> one slot row, one send, one :said link."""
    sends: list[str] = []
    a = _owner(sends, ok=None)               # the transport refused outright
    t0 = time.time()
    _park(a, now=t0)
    W.maybe_ask_parked(a, now=t0)
    assert sends == [] and a._pending_ask is not None
    slot = a._pending_ask[3]
    assert slot.endswith(":1")
    a.notify_owner = lambda text, channel="sms": sends.append(text) or {"sid": "SM1"}
    W.maybe_ask_parked(a, now=t0 + W.ASK_RETRY_S + 1)
    assert len(sends) == 1 and a._pending_ask is None
    assert fake.slot_ns() == [1]
    assert [r["external_event_id"] for r in fake.said()] == [slot + ":said"]


def test_a_legacy_three_tuple_ask_still_sends(fake):
    """A core older than the port parks (text, stamped, last_try); the sweep
    must read it as "no slot yet" rather than crash."""
    sends: list[str] = []
    a = _owner(sends)
    a._pending_ask = ("which garage?", time.time() - 30, 0.0)
    W.maybe_ask_parked(a)
    assert len(sends) == 1 and fake.slot_ns() == [1]


# ----------------------------------------------------------------- the cost

def test_a_refusal_before_the_budget_costs_no_row(fake, monkeypatch):
    """The reservation is the LAST gate. Quiet hours, the nag limit and the
    dedupe all refuse before it, so a silent day pays no read and no write."""
    sends: list[str] = []
    # Quiet hours: the ambient door defers, the parked ask stays parked.
    monkeypatch.setattr(W, "CLOCK_QUIET_START", 0)
    monkeypatch.setattr(W, "CLOCK_QUIET_END", 24)
    assert W.SPEAK_ONCE("caught your plan", "g", "ambient_act") == "defer"
    a = _owner(sends)
    _park(a)
    W.maybe_ask_parked(a)
    assert a._pending_ask is not None
    monkeypatch.setattr(W, "CLOCK_QUIET_START", 25)
    monkeypatch.setattr(W, "CLOCK_QUIET_END", 0)
    # The nag limit refuses the clock before the budget is consulted.
    monkeypatch.setattr(W, "raised_and_ignored", lambda *a_, **k: True)
    assert W.SPEAK_ONCE("Just confirming?", "the dinner", "clock") is False
    # A question she already asked is dropped without a slot ever existing.
    monkeypatch.setattr(W, "already_said", lambda *a_, **k: True)
    W.maybe_ask_parked(a)
    assert a._pending_ask is None
    assert fake.posts == 0 and fake.slots() == []
    assert sends == []


def test_invited_answers_are_never_muted_by_a_spent_budget(fake):
    """The tag is the DOOR. A direct ask, a sufficiency question with a goal,
    a done text, a compute answer, a stall notice: none of them reserve, so a
    spent day cannot mute one and none of them writes a row. Counting these
    once let three invited clarifications mute every FYI."""
    fake.seed_slots(CAP)
    assert W.uninvited_budget_spent(OWNER) is True
    posts_before = fake.posts
    for kind in ("ask", "act", "needs_user", "compute_answer", "done", ""):
        assert W.SPEAK_ONCE("Quick question — which Priya?",
                            "Email Priya the invoice", kind) is True, kind
    assert fake.posts == posts_before
    assert W.UNINVITED_KINDS == ("clock", "ambient_act")


# ------------------------------------------------- the doors inside the core

class _DeadMemory(Memory):
    def __init__(self):
        pass

    def ingest(self, *a, **k):
        return {}

    def recall(self, *a, **k):
        return []


PRIYA_GOAL = "Draft email to Priya with deck attached"
PRIYA_LINE = ("we really love your deck for sure let's do the deck I'll send "
              "it to your email")


def _core(monkeypatch, decision):
    # owes="owner" on purpose: since Omi port 10a a decision with NO verdict
    # on whose errand this is takes the governed lane and never reaches the
    # overheard-plan arm, so the door under test is only reachable when the
    # model positively said the plan is his.
    a = Anticipy(memory=_DeadMemory(), owner_id="silence")
    monkeypatch.setattr(a, "_decide", lambda *args, **kw: decision)
    monkeypatch.setattr(a, "_voice", lambda *a_, **k_: "i'm on it, ok to send?")
    sent, cancelled = [], []
    a.notify_owner = lambda m, channel="sms": (sent.append(m), {"sid": "SM1"})[1]
    real_cancel = a._cancel_job
    a._cancel_job = lambda jid, why: (cancelled.append(jid), real_cancel(jid, why))[1]
    return a, sent, cancelled


def test_a_spent_budget_keeps_the_ambient_card(fake, monkeypatch):
    """The overheard-plan door, through the real hear(). With the day spent
    the receipt is deferred, NOT refused: the card stands, awaiting his OK,
    and nothing is cancelled — a wrong polarity here is the 2026-08-07
    failure (he approved something nobody told him about) in reverse."""
    assert is_consequential(PRIYA_GOAL)
    fake.seed_slots(CAP)
    a, sent, cancelled = _core(monkeypatch, Decision(
        decision="act", goal=PRIYA_GOAL, reason="he committed to it",
        addressee="person", owes="owner"))
    out = a.hear(PRIYA_LINE, may_say=W.SPEAK_ONCE)
    assert sent == [] and cancelled == []
    assert out["decision"].decision == "act"
    assert out["decision"].needs_confirmation is True
    assert "raised when there is room" in out["decision"].reason
    assert len(fake.cards()) == 1 and fake.cards()[0]["status"] == "awaiting_confirm"
    assert not out.get("anticipy_says")
    assert W.take_held_slot() == ""
    assert len(fake.slots()) == CAP


def test_the_ambient_door_reserves_through_the_real_core(fake, monkeypatch):
    """The mirror: with room, the receipt goes out on a slot the worker then
    attaches to the said row."""
    a, sent, cancelled = _core(monkeypatch, Decision(
        decision="act", goal=PRIYA_GOAL, reason="he committed to it",
        addressee="person", owes="owner"))
    out = a.hear(PRIYA_LINE, may_say=W.SPEAK_ONCE)
    assert sent == ["i'm on it, ok to send?"] and cancelled == []
    assert out.get("anticipy_says")
    assert fake.slot_ns() == [1] and fake.slots()[0]["decision"] == "ambient_act"
    assert W.take_held_slot().endswith(":1")
    assert W.take_held_slot() == "", "a slot is handed over once"


class _WantsToReachOut:
    def __init__(self):
        self.calls = 0

    def chat(self, system, user, **kw):
        self.calls += 1
        return types.SimpleNamespace(text=json.dumps({
            "initiate": True, "say": "Did you ever get that dinner booked?",
            "goal": None, "loop_ids": []}))


def _clock_brain():
    mem = Memory(":memory:")
    cur = mem.db.execute(
        "INSERT INTO episodes(ts, text) VALUES (1000, 'I need to book dinner')")
    eid = cur.lastrowid
    mem.db.execute(
        "INSERT INTO nodes (type, name, created_ts, last_seen_ts, status, attrs) "
        "VALUES ('commitment', 'book dinner', 1000, 1000, 'open', ?)",
        (json.dumps({"source_episode": eid}),))
    mem.db.commit()
    llm = _WantsToReachOut()
    return Anticipy(memory=mem, llm=llm, owner_id="t"), llm


def _noon_today() -> float:
    return datetime.now(W.CLOCK_TZ).replace(hour=12, minute=0, second=0,
                                            microsecond=0).timestamp()


def test_a_spent_day_runs_zero_clock_model_calls(fake):
    """clock_should_run is where the spent check lives — BEFORE initiative
    and work_is_licensed. A refused clock stamps nothing, so without this a
    day spent by 10:00 would run the model every 30 minutes until 22:00 and
    be refused each time. Moving the check behind the model turns this RED:
    llm.calls becomes 1 while the text is still refused."""
    fake.seed_slots(CAP)
    a, llm = _clock_brain()
    sent = []
    a.notify_owner = lambda m, channel="sms": sent.append(m) or {"sid": "SM1"}
    state = {"last_outreach_ts": 0, "reached_loop_ids": []}
    now = _noon_today()
    assert W.clock_should_run(now, state) is False
    if W.clock_should_run(now, state):          # the worker loop's shape
        a.clock_tick(now, may_say=W.SPEAK_ONCE)
    assert llm.calls == 0 and sent == []
    # Memoised: a spent day costs one read per process, not one per tick.
    reads = fake.gets
    assert W.clock_should_run(now + 1800, state) is False
    assert fake.gets == reads


def test_an_unspent_or_unreadable_day_runs_the_clock_as_before(fake):
    """The check can only ever skip work. False and None both run the clock;
    the grant is still decided by the slot row at the door."""
    state = {"last_outreach_ts": 0, "reached_loop_ids": []}
    now = _noon_today()
    fake.seed_slots(CAP - 1)
    assert W.clock_should_run(now, state) is True
    fake.gets_raise = True
    assert W.clock_should_run(now, state) is True
    fake.gets_raise = False
    assert W.clock_should_run(now, {"last_outreach_ts": now - 60}) is False, \
        "the 4h spacing still applies"


def test_the_clock_door_reserves_through_the_real_core(fake):
    """With room, clock_tick speaks on a slot; with the day spent, the same
    tick returns None, touches no transport, and stamps nothing."""
    a, llm = _clock_brain()
    sent = []
    a.notify_owner = lambda m, channel="sms": sent.append(m) or {"sid": "SM1"}
    out = a.clock_tick(now=2000, may_say=W.SPEAK_ONCE)
    assert out and sent == ["Did you ever get that dinner booked?"]
    assert W.take_held_slot().endswith(":1")
    fake.seed_slots(CAP)          # slot 1 already exists (400); 2 and 3 land
    assert len(fake.slots()) == CAP
    assert a.clock_tick(now=2000, may_say=W.SPEAK_ONCE) is None
    assert len(sent) == 1 and W.take_held_slot() == ""


# --------------------------------------------------------------- the digest

def test_the_digest_posts_its_said_row_linked_to_its_slot(fake):
    """This door wrote no durable row until the port: already_said, the feed
    and the live leg could not see that a digest went out."""
    sends: list[str] = []
    a = _owner(sends)
    cleared = []
    a.clear_meeting_held = lambda e: cleared.append(list(e))
    _digest()
    W.deliver_pending_digest(a)
    assert len(sends) == 1 and W.DIGEST_PENDING is None
    assert cleared == [[("j1", "book the venue")]]
    said = fake.said()
    assert len(said) == 1 and said[0]["decision"] == "digest"
    assert said[0]["external_event_id"] == W.uninvited_slot_id(
        OWNER, W._uninvited_day(), 1) + ":said"
    assert fake.slots()[0]["decision"] == "ambient_act"


def test_a_digest_that_could_not_send_keeps_its_slot_for_the_retry(fake):
    sends: list[str] = []
    a = _owner(sends, ok=None)
    t0 = time.time()
    _digest(now=t0)
    W.deliver_pending_digest(a, now=t0)
    assert sends == [] and W.DIGEST_PENDING is not None
    assert W.DIGEST_PENDING[4].endswith(":1")
    a.notify_owner = lambda text, channel="sms": sends.append(text) or {"sid": "SM1"}
    W.deliver_pending_digest(a, now=t0 + W.ASK_RETRY_S + 1)
    assert len(sends) == 1 and W.DIGEST_PENDING is None
    assert fake.slot_ns() == [1] and len(fake.said()) == 1


def test_a_legacy_four_tuple_digest_still_sends(fake):
    sends: list[str] = []
    a = _owner(sends)
    W.DIGEST_PENDING = ("One thing is ready.", time.time() - 60, 0.0,
                        [("j1", "the venue")])
    W.deliver_pending_digest(a)
    assert len(sends) == 1 and fake.slot_ns() == [1]


# -------------------------------------------------------------- the primitive

def test_the_slot_id_is_the_owner_local_day(fake):
    day = W._uninvited_day()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", day)
    assert W.uninvited_slot_id(OWNER, day, 2) == f"uninvited:{OWNER}:{day}:2"
    slot = W.reserve_uninvited_text(OWNER, "clock")
    assert slot == W.uninvited_slot_id(OWNER, day, 1)
    row = fake.slots()[0]
    assert row["kind"] == "uninvited_slot" and row["decision"] == "clock"
    assert row["owner_ref"] == OWNER and row["text"] == f"slot 1/{CAP}"
    assert row["created"] >= W._uninvited_since_utc()


def test_a_conflict_on_slot_n_moves_to_n_plus_one_and_the_cap_holds(fake):
    """Another process holds slot 1 (a stale count saw zero rows). The
    CREATE for 1 is a 400 from the index; 2 is taken instead. The cap is the
    loop bound, not the count."""
    fake.seed_slots(1)
    monkeypatch_count_zero = fake.get

    def stale_get(url, params=None, timeout=None, **k):
        r = monkeypatch_count_zero(url, params=params, timeout=timeout, **k)
        if 'kind="uninvited_slot"' in str((params or {}).get("filter") or ""):
            return _Resp({"items": []})       # a stale snapshot
        return r
    pb.get = stale_get
    assert W.reserve_uninvited_text(OWNER, "ask").endswith(":2")
    assert W.reserve_uninvited_text(OWNER, "ask").endswith(":3")
    assert W.reserve_uninvited_text(OWNER, "ask") is False
    assert fake.slot_ns() == [1, 2, 3]
