"""No verdict is below the floor (Omi port 10a, 2026-09-05).

Wherever the brain reads a model-produced label to decide whether to ACT —
text him, ask him, prepare work — an ABSENT, malformed or unanswered label
must fall on the do-nothing / governed side, never the texting side. Omi does
it with a number (a missing confidence defaults to 0.5, below the 0.80
floor). Anticipy has no numeric confidence on the act path (grep it:
`confiden` hits only brain/memory.py's fact ranking), so the analog is the
four-state verdict and the POLARITY is the port.

The recorded failure this pins: 2026-08-23, 137 decisions, 6 acts, 5 wrong,
0 asks — with speaker/attribution absent on every line. The six acts carried
positive labels (self x5, person x1), so this port does not fix THEM; it
closes the routes an absent label took that day and takes again on any day a
model drops a field:

  VOICE FLOOR   addressee absent/unreadable (None) on a non-explicit act/ask
                -> the ambient lane (held card with lane=desk, one text through
                kind "ambient_act", or the parked-ask valve), never the direct
                lane's immediate `_may_say(..., "act")` text or "Quick question".
  HANDS FLOOR   owes absent (None) on a line NOT positively aimed at her
                -> the nobody treatment: quiet lookup at most, nothing
                prepared, nothing texted, reason begins "no verdict" and never
                says "nobody"; plan_is_settled is the one positive tiebreaker,
                and a None addressee reaches it too. A line the model
                positively labelled addressee="assistant" keeps her voice —
                each floor refuses only what it authorizes.
  CLOCK FLOOR   `initiate` not a JSON true, or `say` not a non-empty string
                -> nothing raised this tick.
  STRONG FLOOR  a configured, live strong second opinion that raises or
                returns no readable decision -> a non-explicit cheap act/ask/
                quiet-goal is demoted to plain ignore; explicit lines keep the
                cheap verdict; unset (prod today) changes nothing.

Every leg drives the REAL code: Anticipy.hear() with `_decide` stubbed and pb
monkeypatched (jobs really post), the real clock_tick with a prompt-routed
model double, the real Brain.triage with a fake strong model. Nothing here
reads a word; the doubles are routed on the system prompt they are handed.

Each floor names its mutation in the leg's docstring. They were all run.
"""
from __future__ import annotations

import json
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.anticipy_core as core  # noqa: E402
from brain import pb  # noqa: E402
from brain.anticipy_core import Anticipy, CLOCK_SYSTEM  # noqa: E402
from brain.memory import Memory  # noqa: E402
from brain.orchestrator import (  # noqa: E402
    AMBIENT_ADDRESSEES, Brain, DIRECT_ADDRESSEES, Decision, LICENCE_SYSTEM,
    SETTLED_SYSTEM, SUFFICIENCY_SYSTEM, TRIAGE_SYSTEM, WORLD_SYSTEM)

# Eleven words: clear of the shard floor, which only judges lines of four or
# fewer. Every number the goal carries is spoken here ("seven" -> 7), so the
# invented-detail guards have nothing to object to.
LINE = "yeah let's do Earls tomorrow at seven, I'll sort the table for us"
BOOK = "book a table at Earls tomorrow at 7"          # deny-list: consequential
LOOK = "research dinner spots near Earls"             # read-only wording


class _Reply:
    def __init__(self, payload):
        self._p, self.ok = payload, True

    def json(self):
        return self._p

    def raise_for_status(self):
        return None


class _Fake:
    """An in-memory jobs table, so the real _queue_job really posts."""

    def __init__(self):
        self.rows: list[dict] = []

    def get(self, url, params=None, timeout=None, **k):
        want = [s for s in ("awaiting_confirm", "queued")
                if s in (params or {}).get("filter", "")]
        return _Reply({"items": [r for r in self.rows if r.get("status") in want]})

    def post(self, url, json=None, timeout=None, **k):
        rec = dict(json or {})
        rec["id"] = f"j{len(self.rows) + 1}"
        rec["_url"] = url
        self.rows.append(rec)
        return _Reply(rec)

    def patch(self, url, json=None, timeout=None, **k):
        jid = url.rstrip("/").rsplit("/", 1)[-1]
        for r in self.rows:
            if r.get("id") == jid:
                r.update(json or {})
        return _Reply({})

    def jobs(self) -> list[dict]:
        return [r for r in self.rows if "/jobs/" in r.get("_url", "")]


class _DeadMemory(Memory):
    def __init__(self):
        pass

    def ingest(self, *a, **k):
        return {}

    def recall(self, *a, **k):
        return []

    def open_loops(self):
        return []

    def close_from_speech(self, *a, **k):
        return []


class _LLM:
    """Routed on the system prompt, so a double cannot answer a question it
    was never asked. Records every prompt it saw."""
    live = True
    model = "fake"

    def __init__(self, settled=False, world=False):
        self.settled, self.world = settled, world
        self.asked: list[str] = []

    def chat(self, system, user, **kw):
        self.asked.append(system)
        if system == SETTLED_SYSTEM:
            return types.SimpleNamespace(text=json.dumps({"settled": self.settled}))
        if system == WORLD_SYSTEM:
            return types.SimpleNamespace(
                text=json.dumps({"ends_in_the_world": self.world}))
        if system == SUFFICIENCY_SYSTEM:
            return types.SimpleNamespace(
                text=json.dumps({"can_start": True, "needed": []}))
        return types.SimpleNamespace(text="{}")


def _anticipy(monkeypatch, decision: Decision, llm=None):
    fake = _Fake()
    monkeypatch.setattr(pb, "get", fake.get)
    monkeypatch.setattr(pb, "post", fake.post)
    monkeypatch.setattr(pb, "patch", fake.patch)
    a = Anticipy(memory=_DeadMemory(), llm=llm, owner_id="floor")
    monkeypatch.setattr(a, "_decide", lambda *args, **kw: decision)
    monkeypatch.setattr(a, "_voice", lambda *a_, **k_: None)   # template wording
    monkeypatch.setattr(core, "fill_gaps_from_memory",
                        lambda llm_, mem, goal, gaps: ({}, list(gaps)))
    sent: list[str] = []
    a.notify_owner = lambda m, channel="sms": (sent.append(m), True)[1]
    return a, fake, sent


def _recorder():
    """A may_say that allows everything and remembers which KIND asked."""
    kinds: list[str] = []

    def may_say(text, goal, kind):
        kinds.append(kind)
        return True
    return kinds, may_say


def _params(job: dict) -> dict:
    return json.loads(job["params"])


# ------------------------------------------------------------ the sets


def test_the_direct_set_is_the_one_positive_addressee():
    """The gate compares against what AUTHORIZES an interruption. None is in
    neither set, which is the whole point: it used to skip the ambient gate
    and land in the direct lane."""
    assert DIRECT_ADDRESSEES == ("assistant",)
    assert not set(DIRECT_ADDRESSEES) & set(AMBIENT_ADDRESSEES)
    assert None not in DIRECT_ADDRESSEES and None not in AMBIENT_ADDRESSEES


# ------------------------------------------------------------ voice floor


def test_an_unattributed_consequential_act_takes_the_governed_lane(monkeypatch):
    """(a) act, consequential, addressee=None, owes="owner", not explicit.

    MUTATION: revert the lane gate to `addressee in AMBIENT_ADDRESSEES` ->
    None skips the ambient lane, the direct lane calls _may_say(..., "act")
    and queues params with no "lane": red on three assertions."""
    d = Decision(decision="act", goal=BOOK, reason="a plan he made",
                 addressee=None, owes="owner")
    a, fake, sent = _anticipy(monkeypatch, d)
    kinds, may_say = _recorder()
    out = a.hear(LINE, may_say=may_say)
    assert "act" not in kinds, f"the direct lane spoke: {kinds}"
    assert kinds == ["ambient_act"], kinds
    jobs = fake.jobs()
    assert len(jobs) == 1, jobs
    assert _params(jobs[0]).get("lane") == "desk"
    assert jobs[0]["status"] == "awaiting_confirm"
    assert len(sent) == 1
    assert out["decision"].decision == "act"
    assert out["decision"].addressee is None, "the record must not invent a label"
    assert out["decision"].reason.startswith("unattributed-directed")


def test_an_unattributed_goalless_ask_parks_in_the_valve(monkeypatch):
    """(b) ask, goal None, missing=[...], addressee=None -> nothing sent
    inline, the question is parked for the worker's quiet moment.

    MUTATION: same revert -> the direct ask branch texts "Quick question"
    through kind "ask" immediately: red."""
    d = Decision(decision="ask", goal=None, reason="one unknown blocks",
                 addressee=None, owes="owner", missing=["which garage do you use"])
    a, fake, sent = _anticipy(monkeypatch, d)
    kinds, may_say = _recorder()
    out = a.hear("I keep meaning to get the brakes looked at before the weekend",
                 may_say=may_say)
    assert sent == [], f"an unattributed question was texted at once: {sent}"
    assert kinds == [], kinds
    assert a._pending_ask is not None and "garage" in a._pending_ask[0]
    assert out["decision"].decision == "ask" and out["decision"].goal == ""
    assert out["decision"].addressee is None
    assert fake.jobs() == []


def test_a_person_directed_ask_still_parks_exactly_as_before(monkeypatch):
    """The lane gate's rewrite must not move the lines that were already on
    the governed side: "person" parks today and parks still."""
    d = Decision(decision="ask", goal=None, reason="one unknown blocks",
                 addressee="person", owes="owner", missing=["which garage do you use"])
    a, fake, sent = _anticipy(monkeypatch, d)
    kinds, may_say = _recorder()
    a.hear("I keep meaning to get the brakes looked at before the weekend",
           may_say=may_say)
    assert sent == [] and kinds == [] and a._pending_ask is not None


def test_an_unattributed_read_only_act_is_quiet_research(monkeypatch):
    """The other half of the governed lane: read-only work runs unheld with
    lane=ambient and says nothing — the same treatment "person" gets."""
    d = Decision(decision="act", goal=LOOK, reason="soft plan",
                 addressee=None, owes="owner", touches="read")
    a, fake, sent = _anticipy(monkeypatch, d)
    kinds, may_say = _recorder()
    out = a.hear(LINE, may_say=may_say)
    jobs = fake.jobs()
    assert len(jobs) == 1 and _params(jobs[0]).get("lane") == "ambient"
    assert jobs[0]["status"] == "queued"
    assert sent == [] and kinds == []
    assert out["decision"].decision == "ignore" and out["decision"].goal == LOOK


# ------------------------------------------------------------ hands floor


def test_an_absent_owes_on_an_overheard_plan_withholds_her_hands(monkeypatch):
    """(c) act, consequential, addressee="person", owes=None, plan_is_settled
    False -> nothing queued, nothing sent, reason begins "no verdict" and
    never says "nobody", owes stays None on the record.

    MUTATION: revert the fence to `decision.owes in NOT_HIS` -> None passes it
    and the ambient lane prepares a desk card and spends a text: red."""
    llm = _LLM(settled=False)
    d = Decision(decision="act", goal=BOOK, reason="a plan", addressee="person",
                 owes=None)
    a, fake, sent = _anticipy(monkeypatch, d, llm=llm)
    kinds, may_say = _recorder()
    out = a.hear(LINE, may_say=may_say)
    assert fake.jobs() == [], fake.jobs()
    assert sent == [] and kinds == []
    assert out["decision"].decision == "ignore" and out["decision"].goal == ""
    assert out["decision"].reason.startswith("no verdict"), out["decision"].reason
    assert "nobody" not in out["decision"].reason
    assert out["decision"].owes is None
    assert SETTLED_SYSTEM in llm.asked, "the one positive tiebreaker was not consulted"


def test_an_absent_owes_still_allows_a_quiet_lookup(monkeypatch):
    """The nobody treatment's generous half survives: read-only work may
    still be looked up quietly, unheld, lane=ambient, saying nothing — and
    the record still says "no verdict", with owes None, not "nobody"."""
    d = Decision(decision="act", goal=LOOK, reason="soft plan",
                 addressee="person", owes=None)
    a, fake, sent = _anticipy(monkeypatch, d)
    kinds, may_say = _recorder()
    out = a.hear(LINE, may_say=may_say)
    jobs = fake.jobs()
    assert len(jobs) == 1 and _params(jobs[0]).get("lane") == "ambient"
    assert jobs[0]["status"] == "queued"
    assert sent == [] and kinds == []
    assert out["decision"].decision == "ignore" and out["decision"].goal == LOOK
    assert out["decision"].owes is None
    assert out["decision"].reason.startswith("no verdict")


def test_a_settled_plan_with_both_fields_blank_reaches_the_held_card(monkeypatch):
    """(d) act, consequential, addressee=None AND owes=None, plan_is_settled
    True -> the widened tiebreaker lifts it into the ambient held card: one
    desk card, one ambient_act text.

    MUTATION: restore `addressee in AMBIENT_ADDRESSEES` inside `settled` ->
    None fails it, the tiebreaker is unreachable, the plan dies unasked: red."""
    llm = _LLM(settled=True)
    d = Decision(decision="act", goal=BOOK, reason="a plan", addressee=None,
                 owes=None)
    a, fake, sent = _anticipy(monkeypatch, d, llm=llm)
    kinds, may_say = _recorder()
    out = a.hear(LINE, may_say=may_say)
    assert SETTLED_SYSTEM in llm.asked
    jobs = fake.jobs()
    assert len(jobs) == 1, "a settled plan must reach the held card"
    assert jobs[0]["status"] == "awaiting_confirm"
    assert _params(jobs[0]).get("lane") == "desk"
    assert kinds == ["ambient_act"] and len(sent) == 1
    assert out["decision"].decision == "act"
    assert out["decision"].addressee is None and out["decision"].owes is None


def test_voice_survives_an_absent_hands_verdict_when_aimed_at_her(monkeypatch):
    """(e) ask, addressee="assistant", owes=None, not explicit -> ONE text
    through kind "ask" and the asked-about plan held on the direct lane. The
    addressee verdict authorizes her voice; a blank owes must not mute an
    invited answer (the wall the first design built).

    MUTATION: drop `and addressee not in DIRECT_ADDRESSEES` from `no_owes` ->
    the line takes the nobody treatment and nothing is asked: red."""
    d = Decision(decision="ask", goal=BOOK, reason="need the time",
                 addressee="assistant", owes=None, missing=["what time?"])
    a, fake, sent = _anticipy(monkeypatch, d)
    kinds, may_say = _recorder()
    out = a.hear(LINE, may_say=may_say)
    assert kinds == ["ask"], kinds
    assert len(sent) == 1
    assert a._pending_ask is None
    jobs = fake.jobs()
    assert len(jobs) == 1 and jobs[0]["status"] == "awaiting_confirm"
    assert "lane" not in _params(jobs[0]), "the direct lane, as before"
    assert out["decision"].decision == "ask"


def test_a_consequential_act_aimed_at_her_with_no_owes_is_held_not_dropped(monkeypatch):
    """The act twin of (e): addressee="assistant", owes=None, consequential ->
    the direct lane's held card plus one "act" text. His tap is the hand."""
    d = Decision(decision="act", goal=BOOK, reason="he asked",
                 addressee="assistant", owes=None)
    a, fake, sent = _anticipy(monkeypatch, d)
    kinds, may_say = _recorder()
    a.hear(LINE, may_say=may_say)
    assert kinds == ["act"] and len(sent) == 1
    jobs = fake.jobs()
    assert len(jobs) == 1 and jobs[0]["status"] == "awaiting_confirm"
    assert "lane" not in _params(jobs[0])


def test_an_explicit_line_with_both_fields_blank_is_unchanged(monkeypatch):
    """(f) explicit=True with addressee=None and owes=None -> the channel is
    transport evidence, not a model label: held card + one "act" text,
    exactly as today, and the record shows the forced "assistant"."""
    d = Decision(decision="act", goal=BOOK, reason="he typed it",
                 addressee=None, owes=None, needs_confirmation=True)
    a, fake, sent = _anticipy(monkeypatch, d)
    kinds, may_say = _recorder()
    out = a.hear(LINE, may_say=may_say, explicit=True)
    assert kinds == ["act"] and len(sent) == 1
    jobs = fake.jobs()
    assert len(jobs) == 1 and jobs[0]["status"] == "awaiting_confirm"
    assert "lane" not in _params(jobs[0])
    assert out["decision"].addressee == "assistant"


def test_machine_silence_stays_positive_only(monkeypatch):
    """An absent owes is the nobody treatment, never the machine one: the
    reason must not claim he was voice-typing, and a read-only goal may
    still be looked up (machine allows nothing at all)."""
    d = Decision(decision="act", goal=LOOK, reason="soft plan",
                 addressee="dictation", owes=None)
    a, fake, sent = _anticipy(monkeypatch, d)
    out = a.hear(LINE)
    assert "machine" not in out["decision"].reason
    assert len(fake.jobs()) == 1 and sent == []


# ------------------------------------------------------------ cost on an ordinary day


def test_a_clean_verdict_pays_nothing_new(monkeypatch):
    """The common path: both labels present. No tiebreaker is consulted, no
    extra model call is made, and the lane is the one it always was."""
    llm = _LLM(settled=True, world=True)
    d = Decision(decision="act", goal=BOOK, reason="a plan", addressee="person",
                 owes="owner")
    a, fake, sent = _anticipy(monkeypatch, d, llm=llm)
    kinds, may_say = _recorder()
    a.hear(LINE, may_say=may_say)
    assert SETTLED_SYSTEM not in llm.asked
    assert WORLD_SYSTEM not in llm.asked
    assert kinds == ["ambient_act"] and len(sent) == 1
    llm2 = _LLM(settled=True, world=True)
    d2 = Decision(decision="act", goal=BOOK, reason="he asked",
                  addressee="assistant", owes="owner")
    a2, fake2, sent2 = _anticipy(monkeypatch, d2, llm=llm2)
    kinds2, may_say2 = _recorder()
    a2.hear(LINE, may_say=may_say2)
    assert SETTLED_SYSTEM not in llm2.asked and WORLD_SYSTEM not in llm2.asked
    assert kinds2 == ["act"] and len(sent2) == 1


# ------------------------------------------------------------ clock floor


def _mem_with_loop() -> Memory:
    mem = Memory(":memory:")
    cur = mem.db.execute(
        "INSERT INTO episodes(ts, text) VALUES "
        "(1001, 'I will send Priya the pitch deck by Friday')")
    eid = cur.lastrowid
    mem.db.execute(
        "INSERT INTO nodes (type, name, created_ts, last_seen_ts, status, attrs) "
        "VALUES ('commitment', 'send Priya the pitch deck', 1001, 1001, 'open', ?)",
        (json.dumps({"source_episode": eid}),))
    mem.db.commit()
    return mem


def _clock(monkeypatch, reply: str):
    class ClockLLM:
        live = True

        def __init__(self):
            self.asked: list[str] = []

        def chat(self, system, user, **kw):
            self.asked.append(system)
            if system == CLOCK_SYSTEM:
                return types.SimpleNamespace(text=reply)
            if system == LICENCE_SYSTEM:
                return types.SimpleNamespace(
                    text=json.dumps({"licenses_work": True}))
            return types.SimpleNamespace(text="{}")

    llm = ClockLLM()
    a = Anticipy(memory=_mem_with_loop(), llm=llm, owner_id="t")
    monkeypatch.setattr(a, "can_notify_owner", lambda: True)
    sent: list[str] = []
    a.notify_owner = lambda m, channel="sms": (sent.append(m), True)[1]
    queued: list = []
    monkeypatch.setattr(a, "_queue_job",
                        lambda goal, params, hold=False, **k:
                        (queued.append((goal, params, hold)) or "job1"))
    return a, llm, sent, queued


@pytest.mark.parametrize("initiate", ["false", "no", "true", "yes", 1, 0, "", None])
def test_a_non_boolean_initiate_raises_nothing(monkeypatch, initiate):
    """(g) The STRING "false" is truthy and used to pass `if not
    raw.get("initiate")`; so did "true", 1, and "no". Only a JSON true is a
    verdict. (None here means the key absent.)

    MUTATION: revert to the truthiness read -> "false"/"no"/"true"/"yes"/1
    all speak: red."""
    reply = {"say": "Did you ever send Priya the deck?", "loop_ids": [1]}
    if initiate is not None:
        reply["initiate"] = initiate
    a, llm, sent, queued = _clock(monkeypatch, json.dumps(reply))
    kinds, may_say = _recorder()
    assert a.clock_tick(now=2000, may_say=may_say) is None
    assert sent == [] and queued == [] and kinds == []
    assert CLOCK_SYSTEM in llm.asked, "the model was consulted; its reply was unreadable"


@pytest.mark.parametrize("say", ["", "   ", 7, None, ["x"], {"text": "x"}])
def test_a_missing_or_non_string_say_raises_nothing(monkeypatch, say):
    reply = {"initiate": True, "loop_ids": [1]}
    if say is not None:
        reply["say"] = say
    a, llm, sent, queued = _clock(monkeypatch, json.dumps(reply))
    kinds, may_say = _recorder()
    assert a.clock_tick(now=2000, may_say=may_say) is None
    assert sent == [] and queued == [] and kinds == []


def test_an_honest_true_with_words_still_speaks(monkeypatch):
    """The floor must not become a wall: a readable verdict goes out."""
    reply = {"initiate": True, "say": "Did you ever send Priya the deck?",
             "loop_ids": [1]}
    a, llm, sent, queued = _clock(monkeypatch, json.dumps(reply))
    kinds, may_say = _recorder()
    out = a.clock_tick(now=2000, may_say=may_say)
    assert out and out["say"] == "Did you ever send Priya the deck?"
    assert kinds == ["clock"] and len(sent) == 1


def test_an_honest_false_is_quiet_without_complaint(monkeypatch, capsys):
    """A JSON false is a readable "not now": silent, and not logged as an
    unreadable reply — the log must separate "said no" from "said nothing"."""
    reply = {"initiate": False, "say": "a reminder", "loop_ids": [1]}
    a, llm, sent, queued = _clock(monkeypatch, json.dumps(reply))
    assert a.clock_tick(now=2000) is None
    assert sent == [] and queued == []
    assert "no readable initiate" not in capsys.readouterr().out


def test_an_unreadable_clock_reply_is_logged(monkeypatch, capsys):
    """Silence must not be silent: party_verdict prints when its question
    goes unanswered, and so does this."""
    reply = {"initiate": "false", "say": "a reminder", "loop_ids": [1]}
    a, llm, sent, queued = _clock(monkeypatch, json.dumps(reply))
    assert a.clock_tick(now=2000) is None
    assert "no readable initiate/say" in capsys.readouterr().out


# ------------------------------------------------------------ strong floor


class _Model:
    live = True
    model = "fake"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list = []

    def chat(self, system, user, **kwargs):
        self.calls.append((system, user))
        reply = self.replies.pop(0)
        return types.SimpleNamespace(
            text=reply if isinstance(reply, str) else json.dumps(reply))


class _Dead(_Model):
    def chat(self, *args, **kwargs):
        self.calls.append(args)
        raise TimeoutError("strong model unavailable")


CHEAP_ACT = {"decision": "act", "goal": "Research the invoice",
             "reason": "requested", "owes": "owner", "addressee": "person",
             "touches": "read"}


def _brain(cheap_payload, strong):
    brain = Brain(_Model([cheap_payload]))
    brain.strong = strong
    return brain


def test_a_strong_look_that_raises_demotes_a_cheap_act():
    """(h) MUTATION: restore `except Exception: pass` (or make the demotion
    branch unreachable) -> the cheap "act" stands: red."""
    brain = _brain(CHEAP_ACT, _Dead([]))
    result = brain.triage("research the invoice")
    assert result.decision == "ignore"
    assert result.goal is None
    assert result.reason.startswith("no verdict")
    assert "strong second opinion" in result.reason
    assert len(brain.strong.calls) == 1
    assert len(brain.llm.calls) == 1, "no second look on a goal that was dropped"


@pytest.mark.parametrize("reply", ["{}", "[]", '{"decision": "maybe"}',
                                   "not json at all", '{"goal": "x"}'])
def test_a_strong_look_with_no_readable_decision_demotes(reply):
    """A live model that replied without a readable decision said nothing
    this code can read — the same treatment as the timeout."""
    brain = _brain(CHEAP_ACT, _Model([reply]))
    result = brain.triage("research the invoice")
    assert result.decision == "ignore" and result.goal is None
    assert result.reason.startswith("no verdict")


def test_a_cheap_ask_and_a_quiet_goal_are_demoted_too():
    ask = {"decision": "ask", "goal": "Book the table", "missing": ["when"],
           "reason": "one unknown", "owes": "owner", "addressee": "person"}
    result = _brain(ask, _Dead([])).triage("book the table")
    assert result.decision == "ignore" and result.goal is None
    assert result.missing == []
    quiet = {"decision": "ignore", "goal": "Research quantum computing",
             "reason": "quiet lookup", "owes": "nobody", "addressee": "self"}
    brain = _brain(quiet, _Dead([]))
    result = brain.triage("I'm just checking how good this transcription is")
    assert result.decision == "ignore" and result.goal is None
    assert len(brain.llm.calls) == 1, "SECOND_LOOK must not run on a dropped goal"


def test_an_explicit_line_keeps_the_cheap_verdict():
    """He typed it at her: a reply costs no interruption, and the seatbelt
    still holds every consequential goal, so the cheap verdict stands."""
    brain = _brain(CHEAP_ACT, _Dead([]))
    result = brain.triage("research the invoice", explicit=True)
    assert result.decision == "act" and result.goal == "Research the invoice"
    assert len(brain.strong.calls) == 1


def test_no_strong_model_configured_changes_nothing():
    """Prod today: ANTICIPY_STRONG_MODEL unset. The floor is inert."""
    brain = Brain(_Model([CHEAP_ACT]))
    assert brain.strong is None
    result = brain.triage("research the invoice")
    assert result.decision == "act" and result.goal == "Research the invoice"


def test_a_dead_strong_model_is_not_consulted():
    """`live` is checked so a keyless rig's heuristic can never overrule a
    real model — and a strong model that is not live must not demote either:
    it was never asked, so nothing is unanswered."""
    strong = _Dead([])
    strong.live = False
    brain = _brain(CHEAP_ACT, strong)
    result = brain.triage("research the invoice")
    assert result.decision == "act" and strong.calls == []


def test_a_readable_strong_verdict_still_replaces_the_cheap_one():
    """The floor must not become a wall: a strong "ignore" demotes, a strong
    "act" sharpens, exactly as before."""
    strong = _Model([{"decision": "ignore", "goal": None,
                      "reason": "he was testing the mic", "owes": "nobody"}])
    result = _brain(CHEAP_ACT, strong).triage("research the invoice")
    assert result.decision == "ignore" and result.goal is None
    assert "strong second opinion" not in result.reason
    strong = _Model([{"decision": "act", "goal": "Research the Devon invoice",
                      "reason": "sharpened", "owes": "owner",
                      "addressee": "assistant"}])
    result = _brain(CHEAP_ACT, strong).triage("research the invoice")
    assert result.decision == "act" and result.goal == "Research the Devon invoice"
    assert strong.calls[0][0] == TRIAGE_SYSTEM
