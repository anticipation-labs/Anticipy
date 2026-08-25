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


def test_a_flip_back_into_his_lane_clears_the_attribution():
    """`owner_is_party` exists to reverse triage's over-eager "other" — six for
    six on a dinner he plainly agreed to. The reversal has to reach the store,
    or the loop stays fenced on a verdict the code already withdrew."""
    m = Memory(":memory:")
    mem = m.ingest(GUEST_LINE)
    m.attribute_commitment(mem["commitment_id"], owes="other")
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


def _triaging_brain(monkeypatch, owes, party=False):
    """hear() with triage scripted. `_decide` is stubbed rather than driven
    through a fake model because the verdict under test is what hear() DOES
    with `owes`, not how the model arrives at it."""
    import brain.anticipy_core as core
    from brain.orchestrator import Decision
    m = Memory(":memory:")
    a = Anticipy(memory=m, llm=None, owner_id="t", owner_phone=None)
    monkeypatch.setattr(a, "_queue_job", lambda *a_, **k_: "job")
    monkeypatch.setattr(a, "_decide", lambda *a_, **k_: Decision(
        decision="act", goal="send the pitch deck", reason="scripted",
        addressee="person", owes=owes))
    monkeypatch.setattr(core, "owner_is_party", lambda *a_, **k_: party)
    return a, m


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
