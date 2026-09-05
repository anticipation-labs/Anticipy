"""One decision may spend 150 s and 32 calls, and not a second or a call more.

Until 2026-09-05 the only bound anywhere beneath the transcript loop was one
attempt's 60 s inactivity timeout in brain/llm.py — per call, per attempt.
One heard line walks twelve to sixteen sequential model calls (extraction,
up to five triage asks, party, world, settled, sufficiency, one memory fill
PER GAP, calendar, voice), and every single-question caller swallows its own
transport error and walks on to the next. So a provider that hung after
triage answered cost 3 x 60 s at EACH remaining question — half an hour for
one line — and a provider answering slowly-but-successfully at 50 s a call
never tripped the timeout at all. The worker is one thread and its poll turn
is strictly serial, so behind that one line sat every later line in the
batch, then handle_inbound (the ONLY path that reads his yes/no to a question
she already asked), the digests, research, stuck-job asks and finished-job
reports. Nothing in the tree could say "this line has had enough".

Omi port 06 (the corrected mechanism): one wall-clock deadline and one call
ceiling per decision, opened around hear() and clock_tick(), reserved BEFORE
each request leaves; the retry stops when the deadline is spent; and one poll
turn stops taking new lines after TURN_HEARING_SECONDS. The split is by TYPE,
never by reading a message: DeadlineExceeded is a TimeoutError so the worker
holds the line for the ten-minute sweep; CallCeilingExceeded is a
RuntimeError so it gets the tombstone. After triage has answered neither
reaches the worker at all — each single-question caller falls to the
no-verdict state it was already built to return.

Every leg drives the REAL brain.llm.LLM through the REAL Brain and Anticipy,
with llm._post_json replaced by a scripted provider that routes on the system
prompt the client actually built, and llm._clock replaced by a clock the
provider advances per request — so a slow provider costs time without
anybody sleeping. Nothing here reads a byte of transcript or model output to
decide anything; the fakes only answer the question they were asked.
"""
from __future__ import annotations

import contextlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import brain.anticipy_core as core  # noqa: E402
import brain.llm as llm  # noqa: E402
import brain.worker as W  # noqa: E402
from brain.memory import EXTRACT_SYSTEM, Memory  # noqa: E402
from brain.orchestrator import (Brain, CALENDAR_PLAN_SYSTEM,  # noqa: E402
                                MEMORY_FILL_SYSTEM, PARTY_SYSTEM,
                                READ_ALOUD_SYSTEM, SETTLED_SYSTEM,
                                SUFFICIENCY_SYSTEM, TRIAGE_SYSTEM,
                                WORLD_SYSTEM)
from llm_fakes import licence_reply  # noqa: E402

LINE = "book us dinner at Cactus Club Thursday"
GOAL = "book dinner at Cactus Club on Thursday"
TRIAGE_ACT = {"decision": "act", "goal": GOAL, "reason": "he asked for it",
              "missing": [], "assumption": None, "addressee": "person",
              "owes": "owner", "touches": "world"}


# ------------------------------------------------------------ the provider

def _system_of(payload: dict) -> str:
    """The system prompt as the REAL client sent it: a plain string, or the
    cache-block list _openrouter builds for a long prompt."""
    content = payload["messages"][0]["content"]
    if isinstance(content, list):
        return "".join(str(b.get("text") or "") for b in content
                       if isinstance(b, dict))
    return str(content)


def _reply(text: str) -> dict:
    return {"choices": [{"message": {"content": text},
                         "finish_reason": "stop"}],
            "usage": {}}


_PROMPTS = (
    ("triage", TRIAGE_SYSTEM), ("extract", EXTRACT_SYSTEM),
    ("fill", MEMORY_FILL_SYSTEM), ("party", PARTY_SYSTEM),
    ("world", WORLD_SYSTEM), ("settled", SETTLED_SYSTEM),
    ("sufficiency", SUFFICIENCY_SYSTEM), ("calendar", CALENDAR_PLAN_SYSTEM),
    ("read_aloud", READ_ALOUD_SYSTEM), ("second_look", Brain.SECOND_LOOK),
    ("voice", core.VOICE_SYSTEM),
)


class Transport:
    """A scripted provider standing in for llm._post_json.

    Routes on the system prompt the real client built, so every answer is to
    the question actually asked, and steps a fake clock per request so a slow
    or hung provider costs time without anybody sleeping.
    """

    def __init__(self, clock: dict, advance: float = 0.0, first=None,
                 triage: dict | None = None, after_triage=None):
        self.clock = clock
        self.advance = advance          # seconds each request costs
        self.first = first              # what the FIRST request costs, if different
        self.triage = triage or TRIAGE_ACT
        self.after_triage = after_triage  # run once triage has answered
        self.asked: list[str] = []

    @staticmethod
    def name(system: str) -> str:
        # Containment, not a prefix: for short prompts _openrouter PREPENDS
        # the grounding sentence, for long ones it splits into cache blocks.
        for label, prompt in _PROMPTS:
            if prompt[:60] in system:
                return label
        if "Two task descriptions from the SAME conversation" in system:
            return "same_plan"
        if licence_reply(system) is not None:
            return "licence"
        return "other"

    def answer(self, name: str, system: str) -> str:
        if name == "triage":
            out = json.dumps(self.triage)
            if self.after_triage:
                self.after_triage()
            return out
        return {
            "extract": "{}",
            "fill": json.dumps({"answer": "the usual window table"}),
            "party": json.dumps({"owner_is_party": True}),
            "world": json.dumps({"ends_in_the_world": True}),
            "settled": json.dumps({"settled": True}),
            "sufficiency": json.dumps({"can_start": True}),
            "calendar": json.dumps({"calendar_write": False}),
            "read_aloud": json.dumps({"speech": True}),
            "second_look": json.dumps({"owner_committed": True}),
            "same_plan": json.dumps({"same": True}),
            "voice": "want me to go ahead?",
            "licence": licence_reply(system) or "{}",
        }.get(name, "{}")

    def __call__(self, url, headers, payload):
        system = _system_of(payload)
        name = self.name(system)
        self.asked.append(name)
        step = (self.first if (self.first is not None and len(self.asked) == 1)
                else self.advance)
        self.clock["t"] += step
        return _reply(self.answer(name, system))


def _refuse(*_a, **_k):
    raise ConnectionError("no backend in this test")


def _rig(monkeypatch, transport: Transport, queue: bool = True):
    """The real client, brain, memory and core, with only the wire faked."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTICIPY_STRONG_MODEL", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.setattr(llm, "AUX_MODEL", "")
    monkeypatch.setattr(llm, "_post_json", transport)
    monkeypatch.setattr(llm, "_clock", lambda: transport.clock["t"])
    monkeypatch.setattr(llm, "_LAST_SPENT", None)
    monkeypatch.setattr(core.pb, "get", _refuse)
    monkeypatch.setattr(core.pb, "post", _refuse)
    monkeypatch.setattr(core.pb, "patch", _refuse)
    model = llm.LLM(api_key="test-key")
    assert model.live and not model.gemini_api_key, \
        "the leg must run LLM.chat -> _openrouter -> _post_json for real"
    a = core.Anticipy(memory=Memory(":memory:", llm=model), llm=model,
                      owner_id="t", owner_phone=None)
    assert a.brain is not None and a.brain.strong is None
    a._running_jobs = lambda: []
    a._pending_jobs = lambda: []
    a._backed_by_a_card = lambda *_a, **_k: True
    a.notify_owner = lambda *_a, **_k: {"ok": True}
    queued: list[dict] = []
    if queue:
        def _queue(goal, params, hold=False, **kw):
            queued.append({"goal": goal, "params": params, "hold": hold, **kw})
            return "job-1"
        a._queue_job = _queue
    return a, model, queued


# ----------------------------------------------------- leg 1: the deadline

def test_a_slow_provider_is_cut_at_the_deadline_not_at_the_chain(monkeypatch):
    """50 s a call, under the 60 s inactivity timeout that used to be the
    only bound: today's code walks the whole chain — ten minutes for one
    line. Bounded, the line completes after ceil(150/50) requests, degraded
    on the side each check already chose, and the held card still lands."""
    slow = Transport({"t": 1000.0}, advance=50.0)
    a, _, queued = _rig(monkeypatch, slow)
    out = a.hear(LINE)
    assert out["decision"].decision == "act", out["decision"]
    assert len(slow.asked) <= 3, slow.asked
    assert queued and queued[0]["hold"] is True, queued
    # The same line, answered instantly, walks well past three: the bound is
    # what cut it, not the chain running out.
    instant = Transport({"t": 0.0})
    b, _, _ = _rig(monkeypatch, instant)
    b.hear(LINE)
    assert len(instant.asked) > 3, instant.asked


# --------------------------------------- leg 2 + 8: a hang before triage

def test_a_hang_before_triage_holds_the_line_and_clears_the_budget(monkeypatch):
    """The deadline spent before triage has answered is the one case that
    must ESCAPE hear(): triage's chat is the un-tried call, so the worker
    sees a TimeoutError, stamps nothing, and the ten-minute sweep hands the
    line back. Then THE LEAK, the worst outcome on the table: after the
    escape the ContextVar must be clear, or every later call in the process
    raises instantly and she is mute until redeploy."""
    hung = Transport({"t": 1000.0}, first=200.0)
    a, model, queued = _rig(monkeypatch, hung)
    with pytest.raises(llm.DeadlineExceeded) as caught:
        a.hear(LINE)
    assert len(hung.asked) == 1, hung.asked
    assert queued == [], "nothing may be minted from a line that was not judged"
    # the worker's split, decided by type exactly as _UNREACHABLE already is
    assert W.unreachable_model(caught.value) is True
    marked: list[tuple[str, str]] = []
    monkeypatch.setattr(W, "mark_processed",
                        lambda event_id, decision, **k:
                        marked.append((event_id, decision)) or True)
    monkeypatch.setattr(W, "DEAF_STREAK", 0)
    assert W.record_failure("ev1", LINE, caught.value) == "held"
    assert marked == [], "a PATCH here resets the stranded clock"
    assert W.DEAF_STREAK == 1
    # leg 8 — the leak
    assert llm._BUDGET.get() is None, \
        "the spent budget stayed installed: every later chat would raise"
    before = len(hung.asked)
    model.chat("s", "u")
    assert len(hung.asked) == before + 1, \
        "a bare chat outside any budget must reach the provider"


# ------------------------------------------------------- leg 3: the ceiling

def _sixty_gaps():
    return [f"detail number {n}" for n in range(60)]


def _always_knows(*_a, **_k):
    return [{"fact": "he always books the window table", "source": "owner"}]


def test_the_ceiling_stops_a_model_controlled_fan_out(monkeypatch):
    """fill_gaps_from_memory makes one call PER GAP, and the gap list is the
    model's own `missing` — uncapped. Sixty gaps with a fact for each is
    sixty calls today. The ceiling cuts it, hear() still returns, and what
    the ceiling left unfilled is still ASKED rather than dropped."""
    t = Transport({"t": 0.0}, triage=dict(TRIAGE_ACT, missing=_sixty_gaps()))
    a, _, queued = _rig(monkeypatch, t)
    a.memory.recall = _always_knows
    out = a.hear(LINE)
    assert len(t.asked) <= llm.DECISION_CALL_CEILING, len(t.asked)
    assert "fill" in t.asked, "the fan-out never started, so nothing was cut"
    assert out["decision"].decision == "act", out["decision"]
    # The unfilled gaps ride on the held card he approves, where the one
    # text names them — that is where "she asks" lives on the ambient lane.
    assert queued and queued[0]["hold"] is True, queued
    left = queued[0]["params"].get("missing") or []
    assert left, "gaps the ceiling left unfilled must remain his to answer"
    assert len(left) < 60, "not one gap was filled before the ceiling"
    # control: with the budget switched off the same line fans out past it
    t2 = Transport({"t": 0.0}, triage=dict(TRIAGE_ACT, missing=_sixty_gaps()))
    b, _, _ = _rig(monkeypatch, t2)
    b.memory.recall = _always_knows
    monkeypatch.setattr(core, "decision_budget", contextlib.nullcontext)
    b.hear(LINE)
    assert len(t2.asked) > llm.DECISION_CALL_CEILING, len(t2.asked)


# ------------------------------------------------ leg 4: the split by type

def test_the_split_between_held_and_tombstoned_is_by_type(monkeypatch):
    assert W.unreachable_model(llm.DeadlineExceeded("spent")) is True
    assert W.unreachable_model(llm.CallCeilingExceeded("spent")) is False
    marked: list[tuple[str, str]] = []
    monkeypatch.setattr(W, "mark_processed",
                        lambda event_id, decision, **k:
                        marked.append((event_id, decision)) or True)
    monkeypatch.setattr(W, "DEAF_STREAK", 0)
    assert W.record_failure("ev2", LINE, llm.CallCeilingExceeded("spent")) == "error"
    assert marked == [("ev2", "error")], \
        "the same words through the same code hit the same count forever"
    assert W.DEAF_STREAK == 0


# ------------------------------------------- leg 5: an ordinary line pays 0

def test_an_ordinary_line_pays_nothing(monkeypatch):
    """Same requests, same order, with the budget and without it."""
    bounded = Transport({"t": 0.0})
    a, _, _ = _rig(monkeypatch, bounded)
    a.hear(LINE)
    assert llm.budget_spent_last() == len(bounded.asked)
    assert 0 < len(bounded.asked) < llm.DECISION_CALL_CEILING // 2, \
        "the ordinary chain sits within a quarter of the ceiling"
    free = Transport({"t": 0.0})
    b, _, _ = _rig(monkeypatch, free)
    monkeypatch.setattr(core, "decision_budget", contextlib.nullcontext)
    b.hear(LINE)
    assert bounded.asked == free.asked


def test_no_budget_active_is_a_no_op(monkeypatch):
    """A caller outside hear/clock_tick — research, briefings, the nightly
    consolidation — is bounded by nothing, exactly as before."""
    t = Transport({"t": 0.0})
    _, model, _ = _rig(monkeypatch, t)
    assert llm._BUDGET.get() is None
    for _ in range(llm.DECISION_CALL_CEILING + 5):
        model.chat("s", "u")
    assert len(t.asked) == llm.DECISION_CALL_CEILING + 5


def test_nesting_never_widens(monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(llm, "_clock", lambda: clock["t"])
    with llm.decision_budget() as outer:
        outer.calls_left = 1
        with llm.decision_budget() as inner:
            assert inner is outer
            llm._spend()
            with pytest.raises(llm.CallCeilingExceeded):
                llm._spend()
        assert llm._BUDGET.get() is outer
    assert llm._BUDGET.get() is None
    assert llm.budget_spent_last() == 1


# ------------------------------------ leg 6: the retry stops at the deadline

class _Resp:
    def __init__(self, code):
        self.status_code = code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {"ok": True}


def _client_that(counter, clock, step, outcome):
    """An httpx.Client double whose every attempt costs `step` seconds and
    ends in `outcome` — a status, or an exception to raise."""
    class _C:
        def __init__(self, *a, **k):
            counter.setdefault("timeouts", []).append(k.get("timeout"))

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def post(self, *_a, **_k):
            counter["n"] += 1
            clock["t"] += step
            if isinstance(outcome, Exception):
                raise outcome
            return _Resp(outcome)
    return _C


@pytest.mark.parametrize("outcome", [503, llm.httpx.TimeoutException("slow")])
def test_a_retry_is_refused_once_the_deadline_is_spent(monkeypatch, outcome):
    """Both retry paths — a retryable status and a transport error. One
    attempt that ate the whole budget is not followed by a sleep into a
    retry that cannot finish; and with no budget the same double is retried
    to the ceiling exactly as before."""
    monkeypatch.setattr(llm, "_RETRY_BASE_SECONDS", 0.001)
    clock = {"t": 0.0}
    monkeypatch.setattr(llm, "_clock", lambda: clock["t"])
    counter = {"n": 0}
    monkeypatch.setattr(llm.httpx, "Client",
                        _client_that(counter, clock,
                                     llm.DECISION_DEADLINE_SECONDS + 1, outcome))
    with llm.decision_budget():
        with pytest.raises(llm.DeadlineExceeded):
            llm._post_json("http://x", {}, {})
    assert counter["n"] == 1, "a retry was attempted with no time left"
    counter["n"] = 0
    with pytest.raises((RuntimeError, llm.httpx.TimeoutException)):
        llm._post_json("http://x", {}, {})
    assert counter["n"] == llm._RETRY_ATTEMPTS


def test_each_attempt_is_clamped_to_what_is_left(monkeypatch):
    """The 60 s figure is an inactivity timeout per attempt; a decision with
    ten seconds left may not open an attempt that can wait sixty."""
    clock = {"t": 0.0}
    monkeypatch.setattr(llm, "_clock", lambda: clock["t"])
    assert llm._attempt_timeout() == 60.0
    counter = {"n": 0}
    monkeypatch.setattr(llm.httpx, "Client",
                        _client_that(counter, clock, 0.0, 200))
    with llm.decision_budget():
        assert llm._attempt_timeout() == 60.0
        clock["t"] = llm.DECISION_DEADLINE_SECONDS - 10
        assert llm._attempt_timeout() == pytest.approx(10.0)
        llm._post_json("http://x", {}, {})
    assert counter["timeouts"] == [pytest.approx(10.0)]


# ------------------------- the gateway (Omi port 09b) and the deadline

def _two_wires(monkeypatch, clock, primary_costs: float):
    """Both credentials, the real _post_json and both real parsers, through
    an httpx.Client double that routes by host — the shape
    tests/test_gateway_fallthrough.py uses. The primary's one attempt costs
    `primary_costs` seconds of the fake clock and answers 503; the fallback
    answers at once."""
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-secret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "not-a-real-secret-either")
    monkeypatch.setattr(llm, "_TRANSPORT_ORDER", ("gemini", "openrouter"))
    monkeypatch.setattr(llm, "_RETRY_BASE_SECONDS", 0.001)
    monkeypatch.setattr(llm, "_clock", lambda: clock["t"])
    posts = {"gemini": 0, "openrouter": 0}

    class _Answer:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "{}"},
                                 "finish_reason": "stop"}]}

    class _Unavailable:
        """What httpx really raises on the last 503 — a transport-typed
        HTTPStatusError, which is what 09b's cooldown keys on."""
        status_code = 503

        def raise_for_status(self):
            raise llm.httpx.HTTPStatusError("503", request=None, response=None)

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def post(self, url, **_k):
            if "generativelanguage" in url:
                posts["gemini"] += 1
                clock["t"] += primary_costs
                return _Unavailable()
            posts["openrouter"] += 1
            return _Answer()

    monkeypatch.setattr(llm.httpx, "Client", _Client)
    model = llm.LLM()
    assert model.transport_names() == ["gemini", "openrouter"]
    return model, posts


def test_a_spent_deadline_is_not_a_dead_primary(monkeypatch):
    """DeadlineExceeded is a TimeoutError, and port 09b's _fall_through
    remembers a transport-typed primary failure as 'the primary is down' for
    a minute and tries the fallback. One decision running out of time must
    not move the next minute of every other line onto the fallback, nor be
    counted as both wires dead: it propagates, and the worker holds the
    line as for any TimeoutError."""
    clock = {"t": 0.0}
    model, posts = _two_wires(monkeypatch, clock,
                              primary_costs=llm.DECISION_DEADLINE_SECONDS + 1)
    with llm.decision_budget():
        with pytest.raises(llm.DeadlineExceeded):
            model.chat("s", "u")
    assert posts == {"gemini": 1, "openrouter": 0}, posts
    assert model._primary_down_until == 0.0, \
        "one decision's clock put the primary into cooldown for every line"
    assert not any(model.gateway_tally.values()), model.gateway_tally
    assert llm._BUDGET.get() is None
    # Control: the same 503 with time left is a real fault — remembered, and
    # rescued by the second credential exactly as port 09b built it.
    clock = {"t": 0.0}
    model, posts = _two_wires(monkeypatch, clock, primary_costs=1.0)
    with llm.decision_budget():
        res = model.chat("s", "u")
    assert res.mode == "openrouter" and res.fell_through_from == "gemini"
    assert posts["gemini"] == llm._RETRY_ATTEMPTS and posts["openrouter"] == 1
    assert model._primary_down_until > 0.0
    assert model.gateway_tally["rescued"] == 1


# -------------------------------------------------- leg 7: the turn bound

def test_the_turn_bound_both_ways():
    assert W.turn_has_time(0.0, W.TURN_HEARING_SECONDS - 0.1) is True
    assert W.turn_has_time(0.0, W.TURN_HEARING_SECONDS) is False
    assert W.turn_has_time(100.0, 100.0 + W.TURN_HEARING_SECONDS + 1) is False


def test_the_loop_checks_the_turn_before_claiming():
    """A tested predicate that main() does not consult is a comment. And it
    must run BEFORE claim(), so no claimed row is ever abandoned mid-turn."""
    source = open(W.__file__, encoding="utf-8").read()
    head = "for ev in fetch_unprocessed(owner_ref=anticipy.owner_ref):"
    assert source.count(head) == 1
    assert "turn_started = time.monotonic()" in source[:source.index(head)]
    loop = source[source.index(head):]
    before_claim = loop[:loop.index('if not claim(ev["id"]):')]
    assert "if not turn_has_time(turn_started, time.monotonic()):" in before_claim
    assert "break" in before_claim


# ------------------------------------------ the measurement on the row

def test_the_row_carries_the_measurement_only_when_measured(monkeypatch):
    """Absent, never 0: an unmeasured row must not read like a decision that
    took no time. One PATCH, as today, with the two numbers riding on it.
    And the loop stamps what the budget counted."""
    bodies: list[dict] = []

    class _Ok:
        ok = True
        status_code = 200

    monkeypatch.setattr(W, "_HEARD_COLUMNS_ACCEPTED", True)
    monkeypatch.setattr(W.pb, "patch",
                        lambda url, **kw: bodies.append(kw["json"]) or _Ok())
    assert W.mark_processed("ev", "act", goal=GOAL, heard_ms=1234, heard_calls=9)
    assert len(bodies) == 1, "an accepted stamp is ONE round trip, as today"
    assert bodies[-1]["heard_ms"] == 1234 and bodies[-1]["heard_calls"] == 9
    assert W.mark_processed("ev", "ignore")
    assert "heard_ms" not in bodies[-1] and "heard_calls" not in bodies[-1]
    assert W._HEARD_COLUMNS_ACCEPTED is True
    source = open(W.__file__, encoding="utf-8").read()
    after_hear = source[source.index("note_heard(True)"):]
    assert "heard_calls = budget_spent_last()" in after_hear[:1200]
    assert "heard_ms=heard_ms, heard_calls=heard_calls)" in after_hear
    # the deploy proof: the bounds print beside the fingerprint
    assert "budget={DECISION_DEADLINE_SECONDS}s/{DECISION_CALL_CEILING}calls" in source


def test_a_backend_that_throws_on_the_columns_still_lands_the_decision(monkeypatch):
    """THE SHAPE MEASURED LIVE ON 2026-09-05. The Worker's column map knew
    heard_ms/heard_calls; the D1 table did not; the UPDATE threw and the
    Worker answered a 500 (Cloudflare 1101), not the 400 the leg above
    pins. The stamp then never retried, every decided line stayed at
    "processing", and release_stranded_claims re-heard the errand line every
    ten minutes — six duplicate browser jobs from one line in an hour. So ANY
    failed measured stamp retries once without the measurement; only a 400
    switches the measurement off, a 500 may be transient and is offered
    again on the next line."""
    bodies: list[dict] = []

    class _Reply:
        def __init__(self, code):
            self.status_code = code
            self.ok = code < 400

    def patch(url, **kw):
        bodies.append(kw["json"])
        measured = "heard_ms" in kw["json"] or "heard_calls" in kw["json"]
        return _Reply(500 if measured else 200)

    monkeypatch.setattr(W, "_HEARD_COLUMNS_ACCEPTED", True)
    monkeypatch.setattr(W.pb, "patch", patch)
    assert W.mark_processed("ev1", "act", goal=GOAL, heard_ms=1234, heard_calls=9) is True
    assert len(bodies) == 2, "one retry, at once, without the measurement"
    assert "heard_ms" in bodies[0] and bodies[0]["decision"] == "act"
    assert bodies[1] == {"decision": "act", "goal": GOAL}, bodies[1]
    # a 500 is not the definitive "no columns": the measurement is offered again
    assert W._HEARD_COLUMNS_ACCEPTED is True
    bodies.clear()
    assert W.mark_processed("ev2", "act", goal=GOAL, heard_ms=2000, heard_calls=5) is True
    assert len(bodies) == 2 and "heard_ms" in bodies[0] and "heard_ms" not in bodies[1]


def test_a_backend_without_the_columns_still_lands_the_decision(monkeypatch):
    """THE LIVE BACKEND IS NOT POCKETBASE. The Cloudflare Worker
    (migration/workers/src/pb/records.ts) answers 400 `unknown_field` on a
    PATCH carrying a column its schema lacks, where PocketBase drops the key
    silently. Until migration/d1/schema.sql carries heard_ms/heard_calls a
    stamp that insisted on them would leave every decision unlanded: the row
    at "processing", handed back by the stranded sweep, heard again every
    ten minutes with a duplicate job and text each time. The decision is
    what must land: one immediate retry without the measurement, keyed on
    the HTTP status alone, and the process stops offering it."""
    bodies: list[dict] = []

    class _Reply:
        def __init__(self, code):
            self.status_code = code
            self.ok = code < 400

    def patch(url, **kw):
        bodies.append(kw["json"])
        unknown = "heard_ms" in kw["json"] or "heard_calls" in kw["json"]
        return _Reply(400 if unknown else 200)

    monkeypatch.setattr(W, "_HEARD_COLUMNS_ACCEPTED", True)
    monkeypatch.setattr(W.pb, "patch", patch)
    assert W.mark_processed("ev1", "act", goal=GOAL, heard_ms=1234, heard_calls=9) is True
    assert len(bodies) == 2, "one retry, at once, without the measurement"
    assert "heard_ms" in bodies[0] and bodies[0]["decision"] == "act"
    assert bodies[1] == {"decision": "act", "goal": GOAL}, bodies[1]
    assert W._HEARD_COLUMNS_ACCEPTED is False
    # every later line is today's single PATCH — never a second round trip
    assert W.mark_processed("ev2", "act", goal=GOAL, heard_ms=2000, heard_calls=5) is True
    assert len(bodies) == 3 and "heard_ms" not in bodies[-1]


def test_a_transient_failure_of_the_stamp_is_not_read_as_missing_columns(monkeypatch):
    """A 503 is the backend being absent, not the schema lacking a column:
    the verdict is False exactly as today and the process keeps offering the
    measurement. CORRECTED 2026-09-05: this leg first said "nothing is
    retried (it would land nothing either)". Live on Cloudflare the measured
    stamp answered 500 while an unmeasured one answered 200 — the column map
    was ahead of the table — and "not retried" meant the decision never
    landed and the line was re-heard every ten minutes with a duplicate job
    each time. So one retry without the measurement always follows a failed
    measured stamp; a backend that is truly down fails that too, which is
    what this leg now pins."""
    bodies: list[dict] = []

    class _Down:
        ok = False
        status_code = 503

    monkeypatch.setattr(W, "_HEARD_COLUMNS_ACCEPTED", True)
    monkeypatch.setattr(W.pb, "patch",
                        lambda url, **kw: bodies.append(kw["json"]) or _Down())
    assert W.mark_processed("ev", "act", goal=GOAL, heard_ms=1234, heard_calls=9) is False
    assert len(bodies) == 2, "one retry without the measurement, and it fails too: the backend is down"
    assert "heard_ms" in bodies[0] and "heard_ms" not in bodies[1]
    assert W._HEARD_COLUMNS_ACCEPTED is True


# ------------------------------- leg 9: the residual, recorded not fixed

def _real_mint_rig(monkeypatch, transport: Transport):
    """The REAL _queue_job with one job already running, so the dedupe over
    _running_jobs() at the top of the mint path actually runs."""
    a, _, _ = _rig(monkeypatch, transport, queue=False)
    posted: list[dict] = []

    class _Created:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": f"job-{len(posted)}", "status": "awaiting_confirm"}

    monkeypatch.setattr(core.pb, "post",
                        lambda url, **kw: posted.append(kw.get("json") or {})
                        or _Created())
    a._running_jobs = lambda: [{"id": "running-1", "status": "running",
                                "goal": "cancel the gym membership"}]
    a._same_pending = lambda *_a, **_k: None
    a._refines_pending = lambda *_a, **_k: None
    return a, posted


def test_the_ceiling_reopens_the_duplicate_card_residual(monkeypatch):
    """RESIDUAL, written down rather than fixed here. `_same_plan` asks the
    model only when the words cannot tell (overlap < 0.5), and its
    no-verdict state is False — "different". So a ceiling spent after triage
    makes every running-job comparison answer "different", and a re-mention
    of a plan already in motion mints a SECOND held card: the recorded
    five-copies failure, reachable by structure. This leg pins what the code
    does TODAY, both ways, so it goes red the day the residual is fixed — or
    regressed — and research/2026-09-05-port-06-reasoning-bounds.md names it.
    """
    def spend_it():
        llm._BUDGET.get().calls_left = 0

    t = Transport({"t": 0.0}, after_triage=spend_it)
    a, posted = _real_mint_rig(monkeypatch, t)
    a.hear(LINE)
    assert "same_plan" not in t.asked, "the ceiling let the question through"
    assert [p for p in posted if p.get("goal")], \
        "the residual moved: a spent ceiling no longer mints a second card"
    # control: with the ceiling intact the question is asked, the model says
    # "same", and the running job absorbs the re-mention — no second card.
    t2 = Transport({"t": 0.0})
    b, posted2 = _real_mint_rig(monkeypatch, t2)
    b.hear(LINE)
    assert "same_plan" in t2.asked
    assert [p for p in posted2 if p.get("goal")] == []
