"""A guest's promise is not the owner's errand.

`Memory.ingest` took `(text, ts)` and nothing else, so every line the pendant
heard entered the store as if the owner had said it. `hear()` already holds the
phone's voice verdict for that line and triage already returns its own verdict
on whose obligation the sentence expresses — both were computed and dropped on
the floor one call before memory saw the words.

The live consequence, reproduced against the shipped code: a guest at the
owner's table says "I'll send you the pitch deck tomorrow morning." It becomes
an open commitment in the owner's memory, its source passes
`_CLOCK_ACTION_SOURCE_RE`, and `clock_tick` may mint a browser job from it. The
owner is then chased about a promise somebody else made.

    open_loops after a GUEST's sentence:
      [{'id': 3, 'what': 'send you the pitch deck tomorrow morning',
        'source': "I'll send you the pitch deck tomorrow morning."}]
      clock may mint a goal from it? True

THE HONESTY WALL IS THE POINT OF THESE TESTS, not a footnote. Live speaker
coverage is 0%: `anticipy_core` records the measurement at the roster
normalisation — 200 tagged lines, 195 distinct identities, 97% seen exactly
once, the owner recognised twice. A fence keyed on "the speaker is not
positively the owner" would refuse to prepare anything at all. So only a
POSITIVE not-his verdict fences, from either sensor, and no verdict must
change nothing. Half of what follows tests that nothing changed.
"""
import json
import sqlite3

from brain.anticipy_core import Anticipy
from brain.memory import Memory

GUEST_LINE = "I'll send you the pitch deck tomorrow morning."


# ------------------------------------------------- the store records who spoke

def test_a_guests_promise_is_recorded_as_someone_elses():
    m = Memory(":memory:")
    m.ingest(GUEST_LINE, speaker="other")
    loop = m.open_loops()[0]
    assert loop["speaker"] == "other", \
        "the promise carries no attribution, so nothing downstream can refuse it"


def test_the_owners_own_promise_is_recorded_as_his():
    m = Memory(":memory:")
    m.ingest(GUEST_LINE, speaker="owner")
    assert m.open_loops()[0]["speaker"] == "owner"


def test_no_verdict_is_stored_as_no_verdict():
    """Not "owner". The 97% of lines that carry no voice verdict must be
    distinguishable from the ones the roster actually placed."""
    m = Memory(":memory:")
    m.ingest(GUEST_LINE)
    assert m.open_loops()[0]["speaker"] is None
    m2 = Memory(":memory:")
    m2.ingest(GUEST_LINE, speaker="unknown")
    assert m2.open_loops()[0]["speaker"] is None, \
        "a build that says 'unknown' out loud means the same as saying nothing"


def test_the_line_itself_keeps_the_verdict():
    """On the episode, not only on the commitment: the episode is the record
    of what was said, and a promise is one thing that can be derived from it."""
    m = Memory(":memory:")
    mem = m.ingest(GUEST_LINE, speaker="other")
    row = m.db.execute("SELECT speaker FROM episodes WHERE id=?",
                       (mem["episode_id"],)).fetchone()
    assert row[0] == "other"


# ------------------------------------------- the model's verdict is kept too

def test_triage_saying_someone_else_owes_it_is_kept_on_the_promise():
    """The sensor that actually fires today. Voice coverage is 0%; `owes` is
    produced on every triaged line by a model with the whole conversation."""
    m = Memory(":memory:")
    mem = m.ingest(GUEST_LINE)
    m.attribute_commitment(mem["commitment_id"], owes="other")
    assert m.open_loops()[0]["owes"] == "other"


def test_a_no_verdict_call_never_erases_a_verdict_already_stored():
    """C1, AT THE LAYER WHERE THE DAMAGE HAPPENED. `owes=None` used to pop the
    key, and _upsert_node hands back the SAME commitment node every time the
    same sentence is extracted again — so the second hearing of one guest
    sentence, triaged with no verdict at all, erased the mark the first hearing
    got right. The erase path is gone: absence is not an answer, exactly as it
    is not for a voice tag or a fact's kind."""
    m = Memory(":memory:")
    mem = m.ingest(GUEST_LINE)
    m.attribute_commitment(mem["commitment_id"], owes="other")
    m.attribute_commitment(mem["commitment_id"], owes=None)
    assert m.open_loops()[0]["owes"] == "other", \
        "a no-verdict call popped the mark and unfenced the guest's promise"
    m.attribute_commitment(mem["commitment_id"], owes="")
    assert m.open_loops()[0]["owes"] == "other"


def test_a_no_verdict_call_on_an_unmarked_promise_still_writes_nothing():
    """The other half of the same contract: writing nothing is not writing
    "owner". A promise nobody judged must stay unjudged, or the clock starts
    reading the absence of an answer as an answer."""
    m = Memory(":memory:")
    mem = m.ingest(GUEST_LINE)
    m.attribute_commitment(mem["commitment_id"], owes=None)
    assert m.open_loops()[0]["owes"] is None


# --------------------------------------------------- hear() stops dropping it

def _brain(monkeypatch, **kw):
    m = Memory(":memory:")
    a = Anticipy(memory=m, llm=None, owner_id="t", owner_phone=None, **kw)
    monkeypatch.setattr(a, "_queue_job", lambda *a_, **k_: "job")
    return a, m


def test_hear_threads_the_phones_verdict_into_the_store(monkeypatch):
    """THE BEHAVIOURAL LEG. Unit-testing the fence alone would stay green
    through the entire bug, because the verdict was correct and simply never
    arrived — the shape of 8849df15."""
    a, m = _brain(monkeypatch)
    a.hear(GUEST_LINE, speaker="other:Sarah")
    assert m.open_loops()[0]["speaker"] == "other"


def test_hear_does_not_invent_a_verdict_from_an_unplaceable_voice(monkeypatch):
    """"other:v215" is the roster failing to recognise a voice, not
    recognising a different one — 195 identities on 200 lines. hear() already
    reduces it to no verdict for triage; memory must see the same thing."""
    a, m = _brain(monkeypatch)
    a.hear(GUEST_LINE, speaker="other:v215")
    assert m.open_loops()[0]["speaker"] is None


def test_hear_with_no_verdict_stores_none(monkeypatch):
    a, m = _brain(monkeypatch)
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["speaker"] is None


def _triaging_brain(monkeypatch, owes, party=False, decision="act",
                    goal="send the pitch deck"):
    """hear() with triage scripted. `_decide` is stubbed rather than driven
    through a fake model because the verdict under test is what hear() DOES
    with `owes`, not how the model arrives at it."""
    import brain.anticipy_core as core
    from brain.orchestrator import Decision
    m = Memory(":memory:")
    a = Anticipy(memory=m, llm=None, owner_id="t", owner_phone=None)
    monkeypatch.setattr(a, "_queue_job", lambda *a_, **k_: "job")
    monkeypatch.setattr(a, "_decide", lambda *a_, **k_: Decision(
        decision=decision, goal=goal, reason="scripted",
        addressee="person", owes=owes))
    monkeypatch.setattr(core, "owner_is_party", lambda *a_, **k_: party)
    return a, m


def _retriage(monkeypatch, a, owes, decision="act", goal="send the pitch deck"):
    """Re-script triage for the NEXT hearing of the same sentence."""
    from brain.orchestrator import Decision
    monkeypatch.setattr(a, "_decide", lambda *a_, **k_: Decision(
        decision=decision, goal=goal, reason="scripted",
        addressee="person", owes=owes))


def test_hear_writes_triages_verdict_back_onto_the_promise(monkeypatch):
    """THE BEHAVIOURAL LEG for the half that fires today. hear() already
    refused to start work on this line; the loop it left behind was unmarked,
    so clock_tick could mint the same work an hour later."""
    a, m = _triaging_brain(monkeypatch, owes="other")
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] == "other"


def test_hear_clears_the_mark_when_the_owner_turns_out_to_be_a_party(monkeypatch):
    a, m = _triaging_brain(monkeypatch, owes="other", party=True)
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] is None, \
        "the loop stayed fenced on a verdict owner_is_party had withdrawn"


# ------------------------------------------------ C1: the fence unmarks itself
#
# The first draft of the write above passed `"other" if owes == "other" else
# None`, and attribute_commitment(id, None) POPPED the key. _upsert_node
# returns the same commitment node whenever the same sentence is extracted
# again, so every later hearing that did not say "other" erased the fence —
# and the whole suite stayed green through it, because nothing here ever heard
# the same sentence twice.


def test_a_second_hearing_with_no_verdict_does_not_unmark_the_promise(monkeypatch):
    """THE CHECK THAT WOULD HAVE CAUGHT C1. The guest closes the topic with
    the same sentence verbatim — or the worker restarts between hear() and
    mark_processed and re-polls the event — and this time triage times out, so
    _decide() falls through to Decision(decision="ignore", goal=None) with
    owes=None. That is NO VERDICT, and the honesty wall hear() states sixty
    lines further down says no verdict changes nothing."""
    a, m = _triaging_brain(monkeypatch, owes="other")
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] == "other"
    _retriage(monkeypatch, a, owes=None, decision="ignore", goal=None)
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] == "other", \
        ("a triage timeout on the second hearing erased the mark — the guest's "
         "promise is unfenced and the clock is free to mint the browser job")


def test_a_later_contrary_triage_verdict_does_not_unmark_it_either(monkeypatch):
    """Triage is measured wrong in exactly one direction here — six for six
    filing the owner's own dinner under the friend — so its own second opinion
    is the weakest possible reason to drop a fence. owner_is_party(), asked
    that one question alone, is the only thing that may withdraw the mark."""
    a, m = _triaging_brain(monkeypatch, owes="other")
    a.hear(GUEST_LINE)
    _retriage(monkeypatch, a, owes="owner")
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] == "other"


def _clock_against(memory, loop_id):
    """clock_tick over a REAL Memory, with the model naming the loop that
    memory actually holds — the ids a live store hands out are not the ones a
    stand-in invents, and a model naming a loop that is not there gets its
    goal dropped by the authority check one block earlier. A leg that means
    to test the fence has to reach the fence."""
    class _NamesIt:
        owner_zone = "America/Vancouver"

        def chat(self, *_a, **_k):
            class R:
                text = json.dumps({
                    "initiate": True,
                    "say": "Want me to get that pitch deck ready?",
                    "goal": "draft the pitch deck email",
                    "loop_ids": [loop_id],
                })
            return R()

    queued = []
    clock = Anticipy(memory=memory, llm=_NamesIt(), owner_phone=None)
    clock._queue_job = lambda goal, params, hold=False, **_k: (
        queued.append(goal) or "job")
    return clock.clock_tick(now=memory.open_loops()[0]["ts"] + 7200), queued


def test_the_clock_still_refuses_after_a_no_verdict_second_hearing(monkeypatch):
    """THE BEHAVIOURAL LEG — the failure itself, not the field it turns on.
    Asserting the stored mark alone would go green the moment somebody made
    the pop conditional somewhere else; what must never come back is the
    browser job that chases the owner about the guest's promise."""
    a, m = _triaging_brain(monkeypatch, owes="other")
    a.hear(GUEST_LINE)
    _retriage(monkeypatch, a, owes=None, decision="ignore", goal=None)
    a.hear(GUEST_LINE)

    out, queued = _clock_against(m, m.open_loops()[0]["id"])
    assert (out or {}).get("goal") is None, \
        "the owner is being chased about the guest's promise again"
    assert queued == []


def test_that_clock_really_would_have_minted_the_job_without_the_mark(monkeypatch):
    """THE CONTROL. Without it the leg above passes for whatever reason the
    clock happens to stay quiet — and it very nearly did: the goal was being
    dropped by the unevidenced-source check, not the fence, because the model
    was naming a loop id the real store had never issued. Same store, same
    sentence, only the mark absent: the job appears."""
    a, m = _triaging_brain(monkeypatch, owes="owner")
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] is None
    out, queued = _clock_against(m, m.open_loops()[0]["id"])
    assert out["goal"] == "draft the pitch deck email"
    assert queued == ["draft the pitch deck email"]


# ------------------------- I3: the mark reaches the briefing, so it takes the
#                               higher of its two readers' bars
#
# clock_tick refuses to PREPARE work off the mark — a wrong "other" costs one
# lost job and her `say` still carries. briefing_facts() feeds BRIEFING_SYSTEM,
# which is told "other" means somebody else made the promise and to never say
# the owner did — a wrong "other" there tells him his own dinner belongs to his
# friend, or drops it from the briefing entirely. The reversal used to run only
# on act/ask, so a `say` or `ignore` verdict wrote an uncorrected mark straight
# into the prompt.


def test_a_say_verdict_asks_the_reversal_before_marking_the_promise(monkeypatch):
    """The recorded dinner failure, routed the way it was actually routed.
    The friend says "I'll text you a time" at a dinner the owner plainly
    agreed to; triage files it under the friend and decides to SAY something.
    owner_is_party is the model that gets this right, and it must be asked
    before the store — and therefore the briefing — believes triage."""
    a, m = _triaging_brain(monkeypatch, owes="other", party=True,
                           decision="say", goal=None)
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] is None, \
        ("the briefing will now be told the owner's own plan is somebody "
         "else's, and told never to say he promised it")


def test_an_ignore_verdict_asks_the_reversal_too(monkeypatch):
    a, m = _triaging_brain(monkeypatch, owes="other", party=True,
                           decision="ignore", goal=None)
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] is None


def test_a_say_verdict_still_marks_a_promise_that_really_is_the_guests(monkeypatch):
    """The other direction, and the one that matters more: raising the bar for
    writing the mark must not lower the fence. owner_is_party says no, so the
    guest's promise is marked exactly as before, on a decision that never
    reached the reversal at all until now."""
    a, m = _triaging_brain(monkeypatch, owes="other", party=False,
                           decision="say", goal=None)
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] == "other"


def test_the_briefing_never_sees_an_attribution_the_code_has_withdrawn(monkeypatch):
    """The sink, asserted at the sink. briefing_facts() is what BRIEFING_SYSTEM
    is handed, so this is the leg that says the owner is not told his own
    dinner was somebody else's."""
    a, m = _triaging_brain(monkeypatch, owes="other", party=True,
                           decision="say", goal=None)
    a.hear(GUEST_LINE)
    loop = m.briefing_facts(since_ts=0)["open_loops"][0]
    assert loop["owes"] is None


def test_hear_marks_nothing_when_triage_says_the_promise_is_his(monkeypatch):
    a, m = _triaging_brain(monkeypatch, owes="owner")
    a.hear(GUEST_LINE)
    assert m.open_loops()[0]["owes"] is None


def test_the_briefing_is_handed_the_attribution_and_told_what_it_means():
    """The clock is not the only thing that reads an open loop. `briefing()`
    JSON-dumps the whole loop record into BRIEFING_SYSTEM, so telling him he
    promised something a guest promised is the same lie one layer up — and a
    key in the payload that the prompt never explains is evidence the model
    has to guess at."""
    from brain.anticipy_core import BRIEFING_SYSTEM
    m = Memory(":memory:")
    m.ingest(GUEST_LINE, speaker="other")
    loop = m.briefing_facts(since_ts=0)["open_loops"][0]
    assert loop["speaker"] == "other"
    assert "owes" in loop
    assert "speaker" in BRIEFING_SYSTEM and '"owes"' in BRIEFING_SYSTEM


# ------------------------------------------------------- the clock's refusal

class _Loops:
    """Just enough Memory for clock_tick — the same stand-in
    tests/test_clock_authority.py uses, plus the attribution."""

    def __init__(self, **extra):
        self.loop = {"id": 7, "what": "send the pitch deck",
                     "source": "I'll send you the pitch deck tomorrow morning.",
                     "ts": 1000, "speaker": None, "owes": None}
        self.loop.update(extra)

    def open_loops(self):
        return [dict(self.loop)]


class _LLM:
    owner_zone = "America/Vancouver"

    def chat(self, *_a, **_k):
        class R:
            text = json.dumps({
                "initiate": True,
                "say": "Want me to get that pitch deck ready?",
                "goal": "draft the pitch deck email",
                "loop_ids": [7],
            })
        return R()


def _clock(**extra):
    a = Anticipy(memory=_Loops(**extra), llm=_LLM(), owner_phone=None)
    queued = []
    a._queue_job = lambda goal, params, hold=False, **_k: queued.append(
        (goal, hold)) or "job"
    return a.clock_tick(now=2000), queued


def test_the_clock_will_not_prepare_work_off_a_guests_promise():
    out, queued = _clock(speaker="other")
    assert out["goal"] is None, \
        "the clock minted a job from a promise somebody else made"
    assert queued == []
    assert out["say"], "the reminder survives — this fences the action, not her voice"


def test_the_model_saying_someone_else_owes_it_fences_the_clock_too():
    out, queued = _clock(owes="other")
    assert out["goal"] is None
    assert queued == []


def test_no_verdict_leaves_the_clock_exactly_as_it_was():
    """THE HONESTY WALL. This is the leg that stops the fix from deleting the
    product on the 100% of live lines that carry no voice verdict."""
    out, queued = _clock()
    assert out["goal"] == "draft the pitch deck email"
    assert queued and queued[0][0] == "draft the pitch deck email"


def test_the_owners_own_promise_still_prepares_work():
    out, queued = _clock(speaker="owner")
    assert out["goal"] == "draft the pitch deck email"
    assert queued


# ----------------------------- I2: WHICH loops does the goal actually rest on
#
# `selected` is `[l for l in fresh if not loop_ids or l["id"] in loop_ids]`, so
# a model that omits `loop_ids` — the field CLOCK_SYSTEM does not require, and
# the field :3421 silently empties when an id is not a digit string — makes it
# EVERY fresh loop in the store. Asking `any()` over the whole store means one
# guest promise fences every goal the clock will ever prepare, and nothing ever
# closes a guest's commitment, so it fences them again every night forever.


class _ManyLoops:
    """A store with more than one open loop, which is the ordinary case and
    the case the single-loop stand-in above could never express."""

    def __init__(self, *loops):
        self.loops = list(loops)

    def open_loops(self):
        return [dict(loop) for loop in self.loops]


def _loop(id_, what, source, **extra):
    row = {"id": id_, "what": what, "source": source, "ts": 1000,
           "speaker": None, "owes": None}
    row.update(extra)
    return row


HIS = _loop(1, "book the Earls table for Friday",
            "I need to book the Earls table for Friday", owes="owner")
GUESTS = _loop(7, "send the pitch deck",
               "I'll send you the pitch deck tomorrow morning.", owes="other")


def _clock_over(loops, goal, loop_ids=None):
    """clock_tick against a multi-loop store, with the model's reply — and in
    particular whether it named any loop_ids — under the test's control."""
    reply = {"initiate": True, "say": "Want me to sort that?", "goal": goal}
    if loop_ids is not None:
        reply["loop_ids"] = loop_ids

    class _Reply:
        owner_zone = "America/Vancouver"

        def chat(self, *_a, **_k):
            class R:
                text = json.dumps(reply)
            return R()

    a = Anticipy(memory=_ManyLoops(*loops), llm=_Reply(), owner_phone=None)
    queued = []
    a._queue_job = lambda g, params, hold=False, **_k: queued.append(g) or "job"
    return a.clock_tick(now=2000), queued


def test_a_guest_promise_elsewhere_in_the_store_does_not_disable_his_own_goal():
    """THE CHECK THAT WOULD HAVE CAUGHT I2. The owner says "I need to book the
    Earls table for Friday" and a guest at the same dinner says "I'll send you
    the pitch deck tomorrow". That night the clock acts on the Earls booking
    and names no loop_ids. His own booking must still be prepared."""
    out, queued = _clock_over([HIS, GUESTS], "book the Earls table for Friday")
    assert out["goal"] == "book the Earls table for Friday", \
        ("one guest promise disabled every clock-prepared goal — and since "
         "nothing ever closes a guest's commitment, it does so every night")
    assert queued == ["book the Earls table for Friday"]


def test_a_named_guest_loop_fences_even_beside_one_of_his():
    """When the model DOES say which loops it is acting on, those are the
    loops the goal rests on and one not-his verdict among them is enough. The
    job is keyed to loop_ids[0], so this is the set the work is bound to."""
    out, queued = _clock_over([HIS, GUESTS], "send the pitch deck",
                              loop_ids=[1, 7])
    assert out["goal"] is None
    assert queued == []
    assert out["say"], "the fence takes the action, never her voice"


def test_a_named_loop_of_his_beside_a_guests_still_prepares_work():
    out, queued = _clock_over([HIS, GUESTS], "book the Earls table for Friday",
                              loop_ids=[1])
    assert out["goal"] == "book the Earls table for Friday"
    assert queued


def test_an_unnamed_goal_over_nothing_but_guest_promises_is_still_fenced():
    """The original brief's failure, with the model naming nothing. Every
    candidate loop is somebody else's, so the goal can only have come from
    somebody else's — narrowing the set must not lose this."""
    other_guest = _loop(9, "drop off the keys",
                        "I'll drop the keys off on Sunday.", owes="other")
    out, queued = _clock_over([GUESTS, other_guest], "draft the pitch deck email")
    assert out["goal"] is None
    assert queued == []


def test_a_loop_from_before_attribution_existed_still_prepares_work():
    """Every commitment already in every owner's database has no attribution
    key at all. Reading a missing key as "not his" would silently retire every
    loop she has ever recorded."""
    a = Anticipy(memory=_Loops(), llm=_LLM(), owner_phone=None)
    a.memory.loop.pop("speaker")
    a.memory.loop.pop("owes")
    queued = []
    a._queue_job = lambda goal, params, hold=False, **_k: queued.append(goal) or "job"
    out = a.clock_tick(now=2000)
    assert out["goal"] == "draft the pitch deck email"
    assert queued


# ------------------------------------------------------------- the migration

_PRE_SPEAKER_SCHEMA = """
CREATE TABLE episodes (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE nodes (
    id INTEGER PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    attrs TEXT NOT NULL DEFAULT '{}',
    status TEXT,
    created_ts REAL NOT NULL,
    last_seen_ts REAL NOT NULL,
    UNIQUE(type, name)
);
CREATE TABLE profile_facts (
    id INTEGER PRIMARY KEY,
    fact TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 3,
    confidence REAL NOT NULL DEFAULT 0.6,
    source TEXT NOT NULL DEFAULT 'consolidation',
    provenance TEXT NOT NULL DEFAULT '[]',
    first_seen_ts REAL NOT NULL,
    last_seen_ts REAL NOT NULL
);
"""


def _old_database(tmp_path):
    db = tmp_path / "mem.db"
    conn = sqlite3.connect(db)
    conn.executescript(_PRE_SPEAKER_SCHEMA)
    conn.execute("INSERT INTO episodes(ts, text) VALUES (1.0, 'an old line')")
    conn.execute("INSERT INTO profile_facts(fact, first_seen_ts, last_seen_ts) "
                 "VALUES ('partner is Sarah', 1.0, 1.0)")
    conn.commit()
    conn.close()
    return db


def test_an_existing_owners_database_gains_the_column(tmp_path):
    """`CREATE TABLE IF NOT EXISTS` reaches an old database with a new TABLE
    and never with a new COLUMN. Every current owner has a file already."""
    db = _old_database(tmp_path)
    m = Memory(path=db)
    assert m.db.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] == 1
    assert len(m.profile_facts()) == 1
    m.ingest(GUEST_LINE, speaker="other")
    assert m.open_loops()[0]["speaker"] == "other"


def test_opening_the_same_database_twice_is_not_an_error(tmp_path):
    """The retrofit runs on every open. The second one finds the column
    already there, and that is the normal case, not a failure."""
    db = _old_database(tmp_path)
    Memory(path=db).ingest(GUEST_LINE, speaker="other")
    m = Memory(path=db)
    assert m.open_loops()[0]["speaker"] == "other"


class _AlterRefused:
    """A connection whose ALTER statements fail the way a locked or damaged
    file fails — with the same OperationalError that "duplicate column name"
    arrives as. Everything else is a real SQLite connection."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, *a):
        if sql.lstrip().upper().startswith("ALTER TABLE"):
            raise sqlite3.OperationalError("database is locked")
        return self._conn.execute(sql, *a)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def test_a_retrofit_that_cannot_run_fails_the_open_instead_of_degrading(
        tmp_path, monkeypatch):
    """"duplicate column name" is the ordinary case and is swallowed. A locked
    or damaged file raises the SAME exception class, and swallowing THAT would
    leave the store one column short for good while every later read of it
    failed somewhere far away with no clue why. The open is the only place
    that knows what went wrong, so it is the place that says so."""
    import pytest

    import brain.memory as memory_module
    db = _old_database(tmp_path)
    real = memory_module.sqlite3.connect
    monkeypatch.setattr(memory_module.sqlite3, "connect",
                        lambda *a, **k: _AlterRefused(real(*a, **k)))
    with pytest.raises(sqlite3.OperationalError):
        Memory(path=db)


def _columns(db, table):
    return {r[1]: r[2] for r in
            db.execute(f"PRAGMA table_info({table})").fetchall()}


def test_a_retrofitted_database_has_the_same_shape_as_a_fresh_one(tmp_path):
    """The column is written down twice — once in SCHEMA for new databases,
    once in the retrofit list for old ones. Two declarations drift; this is
    the check that notices."""
    fresh = Memory(":memory:")
    migrated = Memory(path=_old_database(tmp_path))
    for table in ("episodes", "profile_facts"):
        assert _columns(fresh.db, table) == _columns(migrated.db, table), table
