"""The profile ranker reads importance and the clock, and nothing else.

`brain/EXEMPLARS-A-LIFE.md:465-470` writes the rule down:

    1. Importance gates, confidence orders. Confidence-first ranking buries
       the shellfish allergy under the coffee order.
    2. Confidence saturates. Past ~0.95 a re-sighting refreshes last_seen and
       nothing else, or the profile becomes whatever he says most, not what
       matters most.

The expression did neither. It was `importance * 0.5 ** (age_days / 30)`:
importance ORDERED by multiplication rather than gating, confidence was
projected into the dict one line above and read by nothing anywhere in
`brain/`, and the single uniform half-life ran backwards from what anyone
intends — because `last_seen_ts` refreshes on every restatement, a live
situation mentioned daily never decayed while a stable fact stated once
decayed away.

Measured on the shipped code, and these are the numbers the legs below turn:

    90-day-old ALLERGY vs 1-day-old SITUATION:
       imp=4 sal=3.9086 'mom is in hospital'
       imp=5 sal=0.6250 'allergic to shellfish'

    equal importance, conf 0.99 (1s older) vs conf 0.10 (newest):
       conf=0.10 sal=3.999999999 'prefers window seats'
       conf=0.99 sal=3.999998930 'partner is Sarah'

The allergy is the one that could hurt somebody, and it lost by 6x to a
situation that will resolve itself. The 0.10-confidence fact won on a
microsecond of recency.

THE LAW-1 TRAP IS IN THE SECOND HALF. "Is this a situation or a stable fact"
is a judgement about MEANING and may never be a word list at recall time. It
is a label the model produces at distillation and the ranker only compares —
the same rule as the speaker verdict one commit earlier.
"""
import sqlite3
import time

from brain.memory import Memory

from llm_fakes import FakeLLM


# ------------------------------------------------------- confidence is read

def test_confidence_orders_facts_of_equal_importance():
    """Stored since the schema shipped, bumped on every restatement, and read
    by nothing: the two tied at 4.000000 and the sort being stable meant
    INSERTION ORDER decided. The weak belief goes in first here for that
    reason — written the other way round this leg passes by accident."""
    now = time.time()
    m = Memory(":memory:")
    m.remember_fact("prefers window seats", importance=4, confidence=0.6, ts=now)
    m.remember_fact("partner is Sarah", importance=4, confidence=0.9, ts=now)
    order = [f["fact"] for f in m.profile_facts()]
    assert order[0] == "partner is Sarah", order


def test_confidence_can_never_lift_a_fact_out_of_its_importance_tier():
    """THE LEG THAT CATCHES A NAIVE MULTIPLICATION, and the sentence the
    doctrine actually writes down. `salience * confidence` gives
    importance 4 x 0.99 = 3.96 over importance 5 x 0.60 = 3.00 — which is
    precisely the shellfish allergy buried under the coffee order that rule 1
    forbids. Confidence may reorder within a tier; it may never cross one."""
    now = time.time()
    m = Memory(":memory:")
    m.remember_fact("allergic to penicillin", importance=5,
                    confidence=0.6, ts=now)
    m.remember_fact("prefers oat milk", importance=4, confidence=0.99, ts=now)
    assert m.profile_facts()[0]["fact"] == "allergic to penicillin"


def test_the_weakest_belief_at_one_tier_still_beats_the_strongest_below_it():
    """The general form, checked across every adjacent pair rather than at one
    convenient point: no confidence a fact can hold reaches the tier above.

    THIS LEG USED TO PASS BY INSERTION ORDER AT THE ONE POINT THAT MATTERS.
    Written with both rows at ts=now and the important one first, setting
    `_CONFIDENCE_FLOOR` to exactly 0.80 — the 4/5 ratio the constant's own
    comment names as the limit it must clear — left it green: 5 x 0.80 and
    4 x 1.00 both come to 4.0, the `-last_seen_ts` tie-break is a tie too,
    and Python's stable sort handed first place to whichever row went in
    first. Both defences the sibling at the top of this file uses are applied
    here now. The weak belief is inserted FIRST, so insertion order argues
    against the assertion rather than for it, and the important fact is one
    second OLDER — the production shape, where the thing said most recently
    is the situation and not the allergy. At the shipped floor of 0.85 the
    important fact wins on salience (4.25 vs 4.00) and neither crutch is
    load-bearing; at 0.80 it loses, which is the whole point of the floor."""
    now = time.time()
    for high in (2, 3, 4, 5):
        m = Memory(":memory:")
        m.remember_fact("the lesser one", importance=high - 1,
                        confidence=1.0, ts=now)
        m.remember_fact("the important one", importance=high,
                        confidence=0.0, ts=now - 1)
        assert m.profile_facts()[0]["fact"] == "the important one", high


# ------------------------------------------------------- the bump still says
#                                                          something after
#                                                          three restatements

def test_confidence_keeps_discriminating_past_the_third_restatement():
    """A tie-breaker that is constant for most facts is not a tie-breaker.
    The flat +0.15 step reached the 0.99 ceiling from the 0.6 consolidation
    seed in THREE restatements — 0.75, 0.90, 0.99 — after which confidence was
    a "seen more than twice" flag rather than a graded belief."""
    now = time.time()
    m = Memory(":memory:")
    fid = m.remember_fact("drinks oat milk", importance=3,
                          confidence=0.6, ts=now)
    seen = []
    for i in range(8):
        m._merge_fact(fid, 3, now + i, [])
        seen.append(round(m.db.execute(
            "SELECT confidence FROM profile_facts WHERE id=?",
            (fid,)).fetchone()[0], 4))
    assert len(set(seen)) >= 6, \
        f"confidence stopped saying anything after {len(set(seen))} steps: {seen}"
    assert seen == sorted(seen), seen


def test_a_settled_belief_refreshes_last_seen_and_stops_climbing():
    """Doctrine 2, written down and never implemented: "past ~0.95 a
    re-sighting refreshes last_seen and nothing else, or the profile becomes
    whatever he says most, not what matters most."""
    now = time.time()
    m = Memory(":memory:")
    fid = m.remember_fact("partner is Sarah", importance=5,
                          confidence=0.96, ts=now)
    m._merge_fact(fid, 5, now + 600, [])
    m.db.commit()
    conf, last = m.db.execute(
        "SELECT confidence, last_seen_ts FROM profile_facts WHERE id=?",
        (fid,)).fetchone()
    assert conf == 0.96, "a settled belief kept climbing on repetition"
    assert last == now + 600, "the re-sighting did not refresh last_seen"


# ----------------------------------------------------------------- the aging

ALLERGY = "allergic to shellfish"
SITUATION = "mom is in hospital"


def _the_measured_pair(**kw):
    """EXEMPLARS-A-LIFE fact 8 against a live situation, exactly as measured:
    importance 5 said once eleven weeks ago, against importance 4 said
    yesterday and mentioned constantly since."""
    now = time.time()
    m = Memory(":memory:")
    m.remember_fact(ALLERGY, importance=5, ts=now - 90 * 86400, **kw)
    m.remember_fact(SITUATION, importance=4, ts=now - 1 * 86400)
    return m


def test_a_stable_fact_does_not_decay_out_from_under_a_fresh_situation():
    """3.9086 to 0.6250, the wrong way round, on the ranker that feeds the
    briefing and memory_notes."""
    m = _the_measured_pair(kind="stable")
    ranked = [f["fact"] for f in m.profile_facts()]
    assert ranked[0] == ALLERGY, ranked


def test_an_unlabelled_fact_ages_exactly_as_it_did():
    """THE HONESTY WALL. Every row in every existing owner's database has no
    stability label and never will unless a model relabels it. Unlabelled must
    mean the 30-day half-life it has always meant, not a guess in either
    direction — so this pair stays inverted, and that is correct."""
    m = _the_measured_pair()
    ranked = [f["fact"] for f in m.profile_facts()]
    assert ranked[0] == SITUATION, ranked
    aged = next(f for f in m.profile_facts() if f["fact"] == ALLERGY)
    # 90 days at a 30-day half-life is three halvings: 5 x 0.125 = 0.625,
    # times the confidence band. The band is the only thing that moved.
    assert 0.53 < aged["salience"] < 0.63, aged["salience"]


def test_age_still_orders_two_otherwise_identical_facts():
    """Guards against an over-clever floor inverting recency: for one
    importance and one confidence, older is never more salient."""
    now = time.time()
    m = Memory(":memory:")
    m.remember_fact("said last week", importance=3, ts=now - 7 * 86400)
    m.remember_fact("said this morning", importance=3, ts=now - 3600)
    assert [f["fact"] for f in m.profile_facts()] == [
        "said this morning", "said last week"]


def test_a_stable_fact_still_ages_against_another_stable_fact():
    """No decay does not mean no clock. Two facts the model called stable are
    still ordered by importance and belief, and among equals by age."""
    now = time.time()
    m = Memory(":memory:")
    m.remember_fact("older stable", importance=3, kind="stable",
                    ts=now - 300 * 86400)
    m.remember_fact("newer stable", importance=3, kind="stable", ts=now)
    assert [f["fact"] for f in m.profile_facts()] == [
        "newer stable", "older stable"]


# ------------------------------------------------- the model names the kind

def _consolidating(fact_payload):
    m = Memory(":memory:", llm=FakeLLM(consolidations=[{"facts": [fact_payload]}]))
    m.ingest("no shellfish for me, I'm allergic", ts=time.time())
    m.consolidate()
    return m.profile_facts()[0]


def test_the_model_names_stability_and_the_store_keeps_it():
    f = _consolidating({"fact": ALLERGY, "importance": 5,
                        "kind": "stable", "episode_ids": [1]})
    assert f["kind"] == "stable"


def test_a_pass_that_says_nothing_about_stability_leaves_no_verdict():
    """Every consolidation reply written before the field existed, and every
    reply from a model that ignores it. No verdict, not a guessed one."""
    f = _consolidating({"fact": ALLERGY, "importance": 5, "episode_ids": [1]})
    assert f["kind"] is None


def test_a_kind_the_model_invented_is_no_verdict():
    f = _consolidating({"fact": ALLERGY, "importance": 5,
                        "kind": "permanent-ish", "episode_ids": [1]})
    assert f["kind"] is None


def test_a_restatement_can_label_a_row_that_had_no_verdict():
    """Otherwise the column is inert for everything that already exists.
    Every fact in every owner's database predates it, and a fact that keeps
    coming up goes down the MERGE path — so a row that is never re-inserted
    would never be labelled however many times the model judged it."""
    m = Memory(":memory:", llm=FakeLLM(consolidations=[
        {"facts": [{"fact": ALLERGY, "importance": 5, "episode_ids": [1]}]},
        {"facts": [{"fact": ALLERGY, "importance": 5, "kind": "stable",
                    "episode_ids": [2]}]},
    ]))
    m.ingest("no shellfish for me", ts=time.time())
    m.consolidate()
    assert m.profile_facts()[0]["kind"] is None
    m.ingest("still allergic to shellfish", ts=time.time())
    m.consolidate()
    assert m.profile_facts()[0]["kind"] == "stable"


def test_a_restatement_never_overwrites_a_verdict_already_recorded():
    """Filling a blank is not churning a label. A merge keeps the row's
    original wording for auditability and keeps its kind for the same
    reason."""
    m = Memory(":memory:", llm=FakeLLM(consolidations=[
        {"facts": [{"fact": ALLERGY, "importance": 5, "kind": "stable",
                    "episode_ids": [1]}]},
        {"facts": [{"fact": ALLERGY, "importance": 5, "kind": "situation",
                    "episode_ids": [2]}]},
    ]))
    m.ingest("no shellfish for me", ts=time.time())
    m.consolidate()
    m.ingest("still allergic to shellfish", ts=time.time())
    m.consolidate()
    assert m.profile_facts()[0]["kind"] == "stable"


def test_the_owners_own_interview_answers_are_not_labelled():
    """Nothing judged them, so nothing claims to have. remember_fact is the
    day-zero interview and the supervised read; neither runs a model over the
    question of how long the fact stays true."""
    m = Memory(":memory:")
    m.remember_fact("partner is Sarah", importance=5)
    assert m.profile_facts()[0]["kind"] is None


def test_the_prompt_actually_asks_for_it():
    """A column nothing ever fills is the defect this commit exists to close,
    one table over."""
    from brain.memory import CONSOLIDATE_SYSTEM
    assert '"kind"' in CONSOLIDATE_SYSTEM
    assert "situation" in CONSOLIDATE_SYSTEM


def test_the_prompt_does_not_present_kind_as_part_of_the_required_shape():
    """ASKING FOR IT AND REQUIRING IT ARE DIFFERENT THINGS, and the schema
    line is the part of a prompt a model actually obeys. `kind` used to sit in
    it formatted identically to `fact` and `importance`, with "Leave kind out
    if you are unsure" arriving four lines later in prose — so a model that
    always answers had a required-looking slot to fill and would guess.

    A guessed "stable" is not a small error. `_HALF_LIFE_DAYS["stable"] is
    None`, so `_decay` returns 1.0 and the fact NEVER fades: "the Devon deal
    closes Friday", labelled stable, outranks fresher facts indefinitely after
    the deal has closed. Omitting the key falls to the 30-day default, which
    is the safe answer. No unit test can catch a model guessing and there is
    no keyed eval of this prompt, so the presentation IS the fix and this leg
    is what holds it."""
    from brain.memory import CONSOLIDATE_SYSTEM
    schema = [line for line in CONSOLIDATE_SYSTEM.splitlines()
              if line.startswith('{"facts"')]
    assert len(schema) == 1, CONSOLIDATE_SYSTEM
    assert '"kind"' not in schema[0], \
        f"kind is formatted as a required field: {schema[0]}"
    # Flattened: the prompt is hard-wrapped, so the instruction can and does
    # straddle a line break.
    flat = " ".join(CONSOLIDATE_SYSTEM.split())
    assert "OPTIONAL" in flat, "nothing tells the model the key may be left out"
    assert "OMIT THE KEY" in flat, \
        "nothing tells the model what to do when it is not sure"


# ------------------------------------------------------------- the migration

_PRE_KIND_PROFILE_FACTS = """
CREATE TABLE episodes (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    text TEXT NOT NULL
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


def test_an_existing_profile_survives_the_new_column(tmp_path):
    db = tmp_path / "mem.db"
    conn = sqlite3.connect(db)
    conn.executescript(_PRE_KIND_PROFILE_FACTS)
    conn.execute("INSERT INTO profile_facts(fact, importance, first_seen_ts, "
                 "last_seen_ts) VALUES (?,?,?,?)",
                 (ALLERGY, 5, time.time(), time.time()))
    conn.commit()
    conn.close()

    m = Memory(path=db)
    facts = m.profile_facts()
    assert len(facts) == 1
    assert facts[0]["kind"] is None, \
        "a row nobody judged must not be labelled by the migration"
    assert facts[0]["salience"] > 0
