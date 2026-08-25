"""A fact the owner has contradicted stops being one she acts on.

THE MEASURED BUG, reproduced against the shipped code before any of this:

    consolidate "partner is Dana"    (importance 5, 40 days ago)
    consolidate "broke up with Dana" (importance 3, yesterday)

    PROFILE:
       imp=5 sal=4.7000 'partner is Dana'          <- the dead one leads
       imp=3 sal=2.7556 'broke up with Dana'
    recall('gift for her birthday') -> ['known: partner is Dana',
                                        'known: broke up with Dana']
    SAME_FACT model calls made: []

Both rows stand, the retired one out-ranks the live one by 1.7x, and it is the
first thing recall hands to triage, to the briefing, to the SMS answer and to
fill_gaps_from_memory — which turns a recalled fact into a value the browser
agent types into a real form. The last line is the part that matters most: the
pair was never even PUT to the model. "partner is Dana" and "broke up with
Dana" reduce to {partner, dana} and {broke, dana}, overlap 0.33, and the sift
only sent 0.40-0.80 to be judged. A cheap sift that silently excludes the case
the feature exists for is not a sift in front of the decision; it IS the
decision, which is what HARNESS-LAW 1 forbids.

AND THE FIX SHIPPED WITH TWO MORE OF ITS OWN SENTENCE, both upstream of the
same model call, both reproduced and both closed in the same file (see THE
SIFT, at the bottom):

    a word-LENGTH filter   "partner is Jo" -> {partner}, "broke up with Jo"
                           -> {broke}: overlap 0, no model ever asked, and the
                           same score merged "partner is Al" into "partner is
                           Jo" and let a veto for one delete the other.
    a [:3] truncation      the band by another mechanism. Four facts naming
                           Dana, and the pair the feature exists for scored
                           lowest of the four, because a supersession pair is
                           low-overlap BY NATURE — one sentence asserts and
                           the other negates.

So the answer to "what may a cheap sift do here" is: decide the ORDER the
model is asked in, and nothing else. Every live row is put to the model, in
one call carrying the whole list. See research/2026-08-24-supersession-fixes.md.

WHAT IS BEING TESTED, and where each rule lives:

  * the model decides the relation (same / replaces / different). Nothing here
    reads the words. `test_the_pair_reaches_the_model_at_all` is the leg that
    goes red if the sift ever narrows back, and the SIFT section below is the
    leg for every mechanism that has tried to narrow it so far.
  * retirement gates ACTION absolutely and SPEECH conditionally
    (docs/DECISIONS-2026-08-24.md RULING 2). The action lane is the default of
    profile_facts()/recall(); the speech lane is asked for by name and comes
    back with the retirement written into the fact's own sentence. That holds
    for raw hearing too: recall() filtered only the profile half, so a dead
    fact reached both action sinks through the episode layer.
  * two deterministic guards, both structure: the older side loses whichever
    way it arrived, and untrusted text may not retire something the owner said.
  * with no model, nothing is retired and nothing raises.

Who SPOKE the line a retirement is built on is the other half of this, and it
lives with the rest of the speaker doctrine in
tests/test_memory_knows_who_spoke.py.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brain.memory import (OVERHEARD, RETIRED_EXCLUDED,  # noqa: E402
                          RETIRED_QUOTED, Memory)
from llm_fakes import FakeLLM  # noqa: E402

DAY = 86400.0


def _breakup_store(now: float, relations=("replaces",)):
    """The recorded scenario, driven through the REAL consolidation pass: a
    partner fact distilled forty days ago, a breakup distilled yesterday."""
    llm = FakeLLM(
        consolidations=[
            {"facts": [{"fact": "partner is Dana", "importance": 5,
                        "episode_ids": [1], "kind": "stable"}]},
            {"facts": [{"fact": "broke up with Dana", "importance": 3,
                        "episode_ids": [2]}]},
        ],
        relations=list(relations),
    )
    m = Memory(":memory:", llm=llm)
    m.ingest("Dana and I are heading to Lisbon in the spring.",
             ts=now - 40 * DAY)
    m.consolidate(now=now - 40 * DAY)
    m.ingest("Dana and I broke up last night.", ts=now - 1 * DAY)
    m.consolidate(now=now - 1 * DAY)
    return m, llm


# ------------------------------------------------------------- the model
# The verdict is the model's. These legs pin that it is asked, that its answer
# is obeyed, and that a non-answer changes nothing.


def test_the_pair_reaches_the_model_at_all():
    """The sift, not the verdict. This is the leg that had to go green before
    any other could: at overlap 0.33 the breakup pair scored below the old 0.40
    band and no model ever saw it, so no verdict could have retired anything.
    Asserts on what was ASKED, because a test on the outcome alone stays green
    when the sift narrows and the fake happens to answer anyway."""
    now = time.time()
    _m, llm = _breakup_store(now)
    asked = llm.relation_calls()
    assert len(asked) == 1, f"expected one judgement, got {asked}"
    payload = json.loads(asked[0])
    assert payload["new_note"] == "broke up with Dana"
    assert [n["note"] for n in payload["stored_notes"]] == ["partner is Dana"]
    # And the ages ride along: which fact has taken the other's place is a
    # question about WHEN, and asking it without the dates is asking the model
    # to guess.
    assert payload["new_note_last_heard_days_ago"] == 1
    assert payload["stored_notes"][0]["last_heard_days_ago"] == 40


def test_a_verdict_of_different_leaves_both_facts_standing():
    """Same two sentences, same sift; when the answer is "different" the store
    does exactly what it did before this feature existed. The code has no
    opinion of its own about what a breakup means."""
    now = time.time()
    m, _llm = _breakup_store(now, relations=["different"])
    facts = sorted(f["fact"] for f in m.profile_facts())
    assert facts == ["broke up with Dana", "partner is Dana"]
    assert all(f["retired_ts"] is None for f in m.profile_facts())


def test_a_verdict_this_store_does_not_know_is_no_verdict():
    """A value the model invented, or a reply in the old {"same":bool} shape
    from a prompt revision nobody here has seen. No verdict changes nothing —
    the same contract _fact_kind and _speaker_verdict already hold."""
    now = time.time()
    m, _llm = _breakup_store(now, relations=["supersedes"])   # not a verdict
    assert len(m.profile_facts()) == 2
    assert all(f["retired_ts"] is None for f in m.profile_facts())


def test_with_no_model_nothing_is_retired_and_nothing_raises():
    """The honesty wall. Consolidation is a no-op with llm=None, so this drives
    the seeding path instead: two contradicting facts, no judge, both stand."""
    m = Memory(":memory:", llm=None)
    m.remember_fact("partner is Dana", importance=5)
    m.remember_fact("broke up with Dana", importance=3)
    assert len(m.profile_facts()) == 2
    assert all(f["retired_ts"] is None for f in m.profile_facts())


# -------------------------------------------------- the retirement itself


def test_the_breakup_retires_the_partner_fact():
    now = time.time()
    m, _llm = _breakup_store(now)
    live = [f["fact"] for f in m.profile_facts()]
    assert live == ["broke up with Dana"], live


def test_the_retired_row_is_kept_for_audit_not_deleted():
    """Brief moment 35: "The old facts aren't deleted — they're retired."
    Deleting is the VETO's job (forget_fact) and means something else."""
    now = time.time()
    m, _llm = _breakup_store(now)
    rows = m.db.execute(
        "SELECT fact, retired_ts, retired_by FROM profile_facts "
        "ORDER BY id").fetchall()
    assert len(rows) == 2, "a row was destroyed instead of retired"
    dead, live = rows
    assert dead[0] == "partner is Dana"
    assert dead[1] is not None, "the retirement date was never written"
    assert live[0] == "broke up with Dana"
    assert live[1] is None


def test_the_chain_from_the_dead_fact_to_its_replacement_is_walkable():
    """"Why did she stop believing that?" has to have an answer, or retiring
    is just a quieter kind of deleting."""
    now = time.time()
    m, _llm = _breakup_store(now)
    dead = m.db.execute(
        "SELECT retired_by FROM profile_facts WHERE fact=?",
        ("partner is Dana",)).fetchone()
    successor = m.db.execute(
        "SELECT fact FROM profile_facts WHERE id=?", (dead[0],)).fetchone()
    assert successor[0] == "broke up with Dana"


def test_the_pass_reports_what_it_retired():
    """`retired` is its own counter in the nightly print. "She still thinks
    Sarah is his partner" and "she never learned anything" are different
    failures that look identical from outside if only `new` is counted."""
    now = time.time()
    m, _llm = _breakup_store(now)
    # Re-drive so both passes' counters are visible.
    llm = FakeLLM(
        consolidations=[
            {"facts": [{"fact": "partner is Dana", "importance": 5,
                        "episode_ids": [1]}]},
            {"facts": [{"fact": "broke up with Dana", "importance": 3,
                        "episode_ids": [2]}]},
        ],
        relations=["replaces"])
    m = Memory(":memory:", llm=llm)
    m.ingest("Dana and I are going to Lisbon.", ts=now - 40 * DAY)
    first = m.consolidate(now=now - 40 * DAY)
    m.ingest("Dana and I broke up last night.", ts=now - 1 * DAY)
    second = m.consolidate(now=now - 1 * DAY)
    assert first["retired"] == 0
    assert second["retired"] == 1
    assert second["new"] == 1, "the replacement still has to land"


# --------------------------------------------------------- the ACTION lane
# RULING 2: "A retired fact may never be an INPUT to action." This is the
# default of every read, so a sink written next month that never heard of
# retirement gets the behaviour that cannot spend his money.


def test_a_retired_fact_is_not_in_the_profile_at_all():
    now = time.time()
    m, _llm = _breakup_store(now)
    assert [f["fact"] for f in m.profile_facts()] == ["broke up with Dana"]
    assert [f["fact"] for f in m.profile_facts(limit=10)] == \
        ["broke up with Dana"]


def test_recall_for_an_unrelated_errand_never_mentions_the_dead_partner():
    """The recorded shape of the harm: an errand that has nothing to do with
    Dana pulled "known: partner is Dana" in through the padding branch, which
    fills a short window with the most IMPORTANT facts whether or not they
    matched. Importance 5 made the dead fact the first thing offered."""
    now = time.time()
    m, _llm = _breakup_store(now)
    got = [f["fact"] for f in m.recall("gift for her birthday")]
    assert not any("partner is Dana" in f for f in got), got


def test_a_retired_fact_cannot_settle_a_gap_in_an_approved_plan():
    """The sink where money rides. fill_gaps_from_memory turns a recalled fact
    into filled[gap] -> params[key] -> a value the browser agent types into a
    real form. Brief moment 35 from the owner's side: after the breakup, every
    future booking stops assuming Dana. Driven through the REAL function with
    a REAL Memory, not the predicate alone — the value was correct and simply
    never arrived is this repo's recorded failure shape (8849df15)."""
    import json
    import types

    from brain.orchestrator import fill_gaps_from_memory

    now = time.time()
    m, _llm = _breakup_store(now)

    seen = {}

    class _LLM:
        live = True

        def chat(self, system, user, **kw):
            seen["known"] = user
            return types.SimpleNamespace(
                text=json.dumps({"answer": "Dana"}))

    fill_gaps_from_memory(_LLM(), m, "book a birthday dinner for her",
                          ["guest name"])
    assert "partner is Dana" not in (seen.get("known") or ""), \
        "a retired fact was offered as a value for an approved plan"


def test_a_dead_fact_never_takes_a_padding_slot_from_a_live_one():
    """The padding branch decides WHICH facts ride along when the query
    matched too few — not merely what order they come in. Ranked by importance
    alone, a retired importance-5 fact is SELECTED over a live importance-2
    one, so the live fact does not reach the prompt at all and the dead one
    does. The final retired-last partition cannot repair that: by then the
    live fact has already been left out of the list."""
    now = time.time()
    m = Memory(":memory:", llm=FakeLLM(relations=["replaces"]))
    # The DEAD fact is the most important thing in the store, and every live
    # one is below it. Written with a live fact at the same importance the
    # check passes for the wrong reason: profile_facts already returns retired
    # rows last, so a stable sort on importance alone leaves the tie in the
    # right order and the mutation hides.
    m.remember_fact("partner is Dana", importance=5, ts=now - 40 * DAY)
    m.remember_fact("broke up with Dana", importance=1, ts=now - 1 * DAY)
    m.remember_fact("prefers window seats", importance=2, ts=now)
    assert any(f["retired_ts"] for f in m.profile_facts(retired=RETIRED_QUOTED))
    padded = m.recall("groceries", limit=1, retired=RETIRED_QUOTED)
    assert len(padded) == 1, padded
    assert "partner is Dana" not in padded[0]["fact"], \
        "a retired fact took the only slot a live fact could have used"


def test_the_dead_fact_no_longer_outranks_the_live_one():
    """The 1.7x inversion, at the ranker. Even in the lane that keeps retired
    facts, a dead one may never lead: a four-slot triage window spent on a
    corpse is a live fact that never reached the prompt."""
    now = time.time()
    m, _llm = _breakup_store(now)
    quoted = m.profile_facts(retired=RETIRED_QUOTED)
    assert quoted[0]["retired_ts"] is None
    assert quoted[-1]["retired_ts"] is not None
    order = [f["fact"] for f in m.recall("who is my partner",
                                         retired=RETIRED_QUOTED)]
    assert order[0].startswith("known:"), order
    assert "no longer true" in order[-1], order


# --------------------------------------------------------- the SPEECH lane
# RULING 2's other half: a retired fact "may be QUOTED as history ... only with
# its retirement stated in the same sentence." This is what makes the Brief's
# §7 broadband answer possible — "you moved to Rowan Ave in June; the account
# probably still shows 4 Maple St."


def test_the_speech_lane_still_holds_the_retired_fact():
    now = time.time()
    m, _llm = _breakup_store(now)
    quoted = [f["fact"] for f in m.profile_facts(retired=RETIRED_QUOTED)]
    assert any("partner is Dana" in f for f in quoted), quoted


def test_the_retirement_is_inside_the_sentence_not_beside_it():
    """A sibling key is how briefing_facts once laundered `source`: it
    projected the key away and handed imported text to the prompt as
    established fact. A prompt-builder cannot drop what is inside the sentence
    it is rendering, so the retirement lives in the fact's own text."""
    now = time.time()
    m, _llm = _breakup_store(now)
    dead = [f for f in m.profile_facts(retired=RETIRED_QUOTED)
            if f["retired_ts"] is not None][0]
    assert dead["fact"].startswith("no longer true"), dead["fact"]
    assert "partner is Dana" in dead["fact"]
    assert "retired" in dead["fact"]


def test_the_briefing_carries_it_and_says_it_is_retired():
    """briefing_facts is the §7 sink and RULING 2 puts it in the speech lane.
    The block reaching BRIEFING_SYSTEM is `fact` strings only, so if the
    retirement were not inside them the prompt would read the dead fact as
    established truth about him."""
    now = time.time()
    m, _llm = _breakup_store(now)
    profile = m.briefing_facts(now - 2 * DAY)["profile"]
    dead = [f["fact"] for f in profile if "partner is Dana" in f["fact"]]
    assert dead, [f["fact"] for f in profile]
    assert dead[0].startswith("no longer true"), dead[0]


def test_the_speech_lane_does_not_prefix_a_dead_fact_with_known():
    """"known:" is a claim. Prefixing "no longer true — retired 3 days ago"
    with it hands the prompt both readings of the same fact at once."""
    now = time.time()
    m, _llm = _breakup_store(now)
    got = [f["fact"] for f in m.recall("Dana", retired=RETIRED_QUOTED)]
    dead = [f for f in got if "partner is Dana" in f]
    assert dead, got
    assert not dead[0].startswith("known:"), dead[0]


# --------------------------------------------------- guard 1: the older side


def test_a_replayed_batch_cannot_resurrect_a_dead_fact():
    """consolidate does not advance its cursor when the model fails, so a batch
    is re-read and a fact that has since been replaced can be re-derived days
    later. The incoming fact is then the OLDER side: it lands ALREADY retired,
    pointing at the row that outlived it, so the replay is recorded without
    coming back to life."""
    now = time.time()
    m = Memory(":memory:", llm=FakeLLM(
        consolidations=[
            {"facts": [{"fact": "partner is Maya", "importance": 5,
                        "episode_ids": [1]}]},
            # The replay: an OLD episode re-read, distilling the old fact.
            {"facts": [{"fact": "partner is Dana", "importance": 5,
                        "episode_ids": [2]}]},
        ],
        relations=["replaces"]))
    m.ingest("Maya and I are looking at flats.", ts=now - 1 * DAY)
    m.consolidate(now=now - 1 * DAY)
    m.ingest("Dana and I are heading to Lisbon.", ts=now - 60 * DAY)
    m.consolidate(now=now)
    live = [f["fact"] for f in m.profile_facts()]
    assert live == ["partner is Maya"], live
    dead = m.db.execute(
        "SELECT retired_ts, retired_by FROM profile_facts WHERE fact=?",
        ("partner is Dana",)).fetchone()
    assert dead[0] is not None, "the replayed fact landed active"
    successor = m.db.execute(
        "SELECT fact FROM profile_facts WHERE id=?", (dead[1],)).fetchone()
    assert successor[0] == "partner is Maya"


def test_a_restatement_older_than_the_retirement_accrues_on_the_dead_row():
    """The same replay one tier down, where the wording is identical and no
    model is consulted at all. The evidence belongs on the row it is evidence
    for; what must not happen is a fresh ACTIVE duplicate of a fact that has
    already been retired."""
    now = time.time()
    m, _llm = _breakup_store(now)
    before = len(m.db.execute("SELECT id FROM profile_facts").fetchall())
    m._relate_fact("partner is Dana", ts=now - 30 * DAY)
    rid, relation = m._relate_fact("partner is Dana", ts=now - 30 * DAY)
    assert relation == "same"
    dead = m.db.execute("SELECT id FROM profile_facts WHERE fact=?",
                        ("partner is Dana",)).fetchone()
    assert rid == dead[0], "the replay matched something other than the corpse"
    assert before == len(
        m.db.execute("SELECT id FROM profile_facts").fetchall())


def test_a_restatement_newer_than_the_retirement_is_judged_afresh():
    """The retired-row merge trap, from the adversarial pass on the roadmap.
    "Actually, we're back together" must not accrue silently onto the corpse —
    evidence lands on a dead row, _merge_fact never touches its status, the
    live occupant is never judged against it, and the owner's correction
    changes NOTHING she says: this card's own bug rebuilt one level down."""
    now = time.time()
    m, _llm = _breakup_store(now)
    rid, relation = m._relate_fact("partner is Dana", ts=now)
    dead = m.db.execute("SELECT id FROM profile_facts WHERE fact=?",
                        ("partner is Dana",)).fetchone()
    assert rid != dead[0], \
        "a restatement newer than the retirement accrued on the dead row"


def test_a_retired_row_is_never_put_to_the_model():
    """The prompt asks which stored fact is true NOW. That question has no
    answer about a fact that already stopped being true, and a "replaces"
    verdict against a corpse would retire something twice.

    ASSERTED ON THE LIST THE MODEL WAS HANDED, not on whether it was asked at
    all. Every live row is now a candidate — that is the whole point of the
    sift no longer excluding anything — so "no call was made" would be green
    for an empty store and for a store that offered the corpse alongside the
    live row. What must hold is that the dead row's wording is not in the
    payload."""
    now = time.time()
    m, llm = _breakup_store(now)
    llm.calls.clear()
    llm.relations = ["different", "different"]
    m._relate_fact("partner is away this week", ts=now - 20 * DAY)
    asked = llm.relation_calls()
    assert asked, "the live row should still have been judged"
    offered = [n["note"] for a in asked for n in json.loads(a)["stored_notes"]]
    assert offered == ["broke up with Dana"], offered
    assert not any("partner is Dana" in n for n in offered), offered


# ------------------------------------------------- guard 2: the provenance


def test_a_mail_derived_fact_cannot_retire_something_he_said():
    """Otherwise "delete his boundary" is a thing a stranger can do by sending
    him an email: the read distils a contradicting line, the model quite
    reasonably calls it a replacement, and an importance-5 interview answer is
    gone. Mirrors forget_fact's veto fence and _merge_fact's launder guard,
    arriving through a third door. The mail fact still LANDS — it just does not
    get to kill anything."""
    now = time.time()
    m = Memory(":memory:", llm=FakeLLM(relations=["replaces"]))
    m.remember_fact("never books anything through Kayak", importance=5,
                    source="interview", ts=now - 10 * DAY)
    m.remember_fact("books flights through Kayak", importance=4,
                    source="supervised_mail", ts=now)
    facts = {f["fact"] for f in m.profile_facts()}
    assert "never books anything through Kayak" in facts, \
        "a mail-derived fact retired something the owner said out loud"
    assert "books flights through Kayak" in facts, \
        "the fence must not also swallow the fact"


def test_a_spoken_fact_may_retire_an_imported_one():
    """The intended direction, and the Grandma pattern from the Brief: he
    moved, and the calendar has not caught up. A fence that blocked this would
    make every imported fact permanent."""
    now = time.time()
    m = Memory(":memory:", llm=FakeLLM(relations=["replaces"]))
    m.remember_fact("home is 44 Birch Lane", importance=4, source="import",
                    ts=now - 200 * DAY)
    m.remember_fact("home is 18 Rowan Ave", importance=5, source="interview",
                    ts=now)
    assert [f["fact"] for f in m.profile_facts()] == ["home is 18 Rowan Ave"]


def test_untrusted_may_retire_untrusted():
    now = time.time()
    m = Memory(":memory:", llm=FakeLLM(relations=["replaces"]))
    m.remember_fact("standup is at 9", importance=3, source="import",
                    ts=now - 30 * DAY)
    m.remember_fact("standup moved to 10", importance=3, source="import",
                    ts=now)
    assert [f["fact"] for f in m.profile_facts()] == ["standup moved to 10"]


# ------------------------------------------------------ the veto interplay


def test_a_vetoed_replacement_retires_nothing():
    """Otherwise the veto becomes a silent deletion weapon: tap away "partner
    is Maya", say it once, and "partner is Dana" dies with nothing written in
    its place. The owner is left with neither fact and no gesture that explains
    where they went."""
    now = time.time()
    m = Memory(":memory:", llm=FakeLLM(relations=["replaces"]))
    m.remember_fact("partner is Dana", importance=5, ts=now - 30 * DAY)
    m.forget_fact("partner is Maya")
    m.remember_fact("partner is Maya", importance=5, source="consolidation",
                    ts=now)
    live = [f["fact"] for f in m.profile_facts()]
    assert live == ["partner is Dana"], live


def test_a_retired_fact_is_still_vetoable():
    """The tap has to work on a card the app is showing, and the app shows
    history too. forget_fact scans every row, retired ones included."""
    now = time.time()
    m, _llm = _breakup_store(now)
    removed = m.forget_fact("partner is Dana")
    assert removed == 1
    assert m.db.execute("SELECT COUNT(*) FROM profile_facts WHERE fact=?",
                        ("partner is Dana",)).fetchone()[0] == 0


# ------------------------------------------------------------- migration


_PRE_SUPERSESSION_SCHEMA = """
CREATE TABLE episodes (
    id INTEGER PRIMARY KEY, ts REAL NOT NULL, text TEXT NOT NULL
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


def test_an_owners_existing_database_gains_the_columns(tmp_path):
    """profile_facts is one SQLite file per owner (brain/supervisor.py:93), so
    a column declared only in SCHEMA exists for new owners and for nobody who
    already has a file. Every fact in every existing owner's database predates
    retirement, and none of them may be lost by it."""
    db = tmp_path / "memory.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(_PRE_SUPERSESSION_SCHEMA)
    now = time.time()
    conn.execute(
        "INSERT INTO profile_facts(fact, first_seen_ts, last_seen_ts) "
        "VALUES (?,?,?)", ("partner is Sarah", now, now))
    conn.commit()
    conn.close()

    m = Memory(path=db)
    facts = m.profile_facts()
    assert [f["fact"] for f in facts] == ["partner is Sarah"]
    assert facts[0]["retired_ts"] is None, \
        "a pre-existing fact came back retired, which retires the whole store"
    cols = {r[1] for r in m.db.execute(
        "PRAGMA table_info(profile_facts)").fetchall()}
    assert {"retired_ts", "retired_by"} <= cols
    m.db.close()
    # Opening it again is the steady state, not a failure.
    Memory(path=db).db.close()


def test_a_retrofitted_database_has_the_same_profile_shape_as_a_fresh_one(
        tmp_path):
    """The columns are declared TWICE — in SCHEMA so a fresh database is right
    in one statement, and in _ADDED_COLUMNS so an old one catches up. Two
    declarations drift; this is what notices."""
    old = tmp_path / "old.db"
    conn = sqlite3.connect(str(old))
    conn.executescript(_PRE_SUPERSESSION_SCHEMA)
    conn.commit()
    conn.close()
    retro = Memory(path=old)
    fresh = Memory(path=tmp_path / "fresh.db")
    shape = lambda m: [(r[1], r[2]) for r in m.db.execute(  # noqa: E731
        "PRAGMA table_info(profile_facts)").fetchall()]
    assert sorted(shape(retro)) == sorted(shape(fresh))
    retro.db.close()
    fresh.db.close()


# ------------------------------------------------- what the prompts are told
# No unit test can stop a model reading a note wrong, so the PRESENTATION is
# the fix and these checks hold the presentation. Both prompts are live: a
# retired fact now reaches them, and a prompt that was never told what "no
# longer true — retired ..." means would read it as established fact about him,
# which is the moment-35 violation one layer above the store.


def test_the_briefing_prompt_is_told_what_a_retired_note_means():
    from brain.anticipy_core import BRIEFING_SYSTEM
    flat = " ".join(BRIEFING_SYSTEM.split())
    assert "no longer true — retired" in flat
    assert "already CORRECTED" in flat
    assert "never plan around it" in flat


def test_the_sms_answer_reaches_the_prompt_with_its_retirement_intact():
    """The §7 sink, end to end: the retired fact must ARRIVE in the notes (so
    the question about the account's stale copy is answerable at all) and the
    prompt must be told it is history. Driven through the real
    _answer_from_memory rather than asserted against the source, because this
    repo's recorded failure shape is a value that was correct and simply never
    arrived (8849df15)."""
    import types

    from brain.anticipy_core import Anticipy

    now = time.time()
    m, _llm = _breakup_store(now)
    seen = {}

    class _LLM:
        live = True

        def chat(self, system, user, **kw):
            seen["system"] = system
            seen["user"] = user
            return types.SimpleNamespace(text="NO_ANSWER")

    Anticipy(memory=m, llm=_LLM())._answer_from_memory("who is my partner?")
    assert "partner is Dana" in seen["user"], seen.get("user")
    assert "no longer true" in seen["user"], seen["user"]
    flat = " ".join(seen["system"].split())
    assert "no longer true — retired" in flat
    assert "same sentence" in flat


def test_triage_context_is_asked_for_in_the_speech_lane():
    """RULING 2's third row: "recall() feeding triage context — allowed,
    marked." Triage is not an action sink, so getting this wrong fails SAFE
    (she simply loses the correction from her context) — which is exactly why
    it needs a check of its own: nothing else would ever notice it drift back.
    Recorded at the call, because the choice being pinned is which lane the
    sink ASKS for."""
    import types

    from brain.anticipy_core import Anticipy

    now = time.time()
    m, _llm = _breakup_store(now)
    asked = []
    real = m.recall
    m.recall = lambda q, limit=8, retired=None, **kw: (   # noqa: E731
        asked.append(retired) or real(q, limit=limit, retired=retired))

    class _LLM:
        live = True

        def chat(self, system, user, **kw):
            return types.SimpleNamespace(text="{}")

    a = Anticipy(memory=m, llm=_LLM())
    a._decide("who is my partner these days", {"commitment": None})
    assert asked and asked[0] == RETIRED_QUOTED, asked


# ================================================================= THE SIFT
# The commit that shipped supersession also shipped this sentence, having
# found and fixed ONE instance of it:
#
#   "A threshold that excludes the case is not a sift in front of the
#    decision — it IS the decision."
#
# It shipped with two more, both upstream of the same model call. These legs
# are the ones that go red if either comes back. They assert on WHAT WAS
# ASKED, never on the outcome: with a scripted fake, an outcome assertion goes
# green for a sift that excluded the pair and a verdict that happened to land
# on something else.


def _four_facts_naming_dana(now, relations=("different",) * 8):
    """The reproduced C3 shape: four stored facts naming one person, of which
    the supersession candidate scores LOWEST. Word overlap is anti-correlated
    with the thing being looked for, because one sentence asserts and the
    other negates."""
    llm = FakeLLM(relations=list(relations))
    m = Memory(":memory:", llm=llm)
    for fact in ("partner is Dana",            # overlap 0.333 — the one
                 "Dana broke her wrist skiing",    # 0.500
                 "Dana broke the blender",         # 0.667
                 "Dana broke up with her boss"):   # 0.667
        m.remember_fact(fact, importance=3, ts=now - 30 * DAY)
    llm.calls.clear()
    return m, llm


def test_a_two_letter_name_is_not_thrown_away_before_the_question():
    """C2, reproduced on the shipped code. `_compare_words` dropped every
    non-digit token of two characters or fewer, so

        "partner is Jo"    -> {partner}
        "broke up with Jo" -> {broke}

    overlap 0, `if overlap > 0` never fired, NO MODEL WAS EVER ASKED, and the
    dead fact led recall at salience 4.7 forever:

        partner name 'Dana': SAME_FACT calls = 1; live = ['broke up with Dana']
        partner name 'Jo'  : SAME_FACT calls = 0; live = ['partner is Jo',
                                                          'broke up with Jo']

    Jo, Al, Ed, Bo, Mo, Ty, Li — one class of name, silently unlearnable. The
    residual list in the review does not cover it, because these sentences DO
    share a word: the code threw it away before counting.

    Driven through the real consolidation pass and asserted on the CALL, so
    restoring `len(w) > 2` in _compare_words goes red here even though the
    fake would have answered "replaces" if it had been asked."""
    now = time.time()
    for name in ("Jo", "Al", "Ed", "Bo", "Ty", "Li"):
        llm = FakeLLM(
            consolidations=[
                {"facts": [{"fact": f"partner is {name}", "importance": 5,
                            "episode_ids": [1], "kind": "stable"}]},
                {"facts": [{"fact": f"broke up with {name}", "importance": 3,
                            "episode_ids": [2]}]},
            ],
            relations=["replaces"])
        m = Memory(":memory:", llm=llm)
        m.ingest(f"{name} and I are heading to Lisbon.", ts=now - 40 * DAY)
        m.consolidate(now=now - 40 * DAY)
        m.ingest(f"{name} and I broke up last night.", ts=now - 1 * DAY)
        m.consolidate(now=now - 1 * DAY)
        asked = llm.relation_calls()
        assert len(asked) == 1, f"{name}: no model was asked at all"
        offered = [n["note"] for n in json.loads(asked[0])["stored_notes"]]
        assert f"partner is {name}" in offered, (name, offered)
        assert [f["fact"] for f in m.profile_facts()] == \
            [f"broke up with {name}"], (name, m.profile_facts())


def test_a_short_name_is_not_swallowed_by_the_wording_shortcut():
    """The same letter-count one tier DOWN, where it is worse than a missed
    question. "partner is Jo" and "partner is Al" both reduced to {partner},
    scored 1.00, and the >= 0.8 shortcut returned "same" WITH NO MODEL IN THE
    LOOP — so _merge_fact kept the original wording and "Al" was thrown away:

        _same_as('partner is Jo', 'partner is Al') -> True
        profile after storing BOTH: ['partner is Jo']

    llm=None on purpose: this tier answers with no model available, which is
    exactly why nothing could have caught it."""
    now = time.time()
    m = Memory(":memory:", llm=None)
    assert not m._same_as("partner is Jo", "partner is Al")
    m.remember_fact("partner is Jo", importance=5, ts=now - 10 * DAY)
    m.remember_fact("partner is Al", importance=5, ts=now)
    assert sorted(f["fact"] for f in m.profile_facts()) == \
        ["partner is Al", "partner is Jo"]


def test_a_veto_for_one_short_name_does_not_delete_another():
    """And one tier down again, where the same score DELETES. forget_fact is
    the owner's tap; `_same_as` is how it recognises a reworded re-derivation.
    Reproduced: a tap on "dinner with Jo" removed "dinner with Al" and then
    blocked "dinner with Ed" from ever being written."""
    now = time.time()
    m = Memory(":memory:", llm=None)
    m.remember_fact("dinner with Al", importance=4, source="interview", ts=now)
    assert m.forget_fact("dinner with Jo") == 0
    assert [f["fact"] for f in m.profile_facts()] == ["dinner with Al"]
    assert not m._is_vetoed("dinner with Ed")


def test_the_filler_words_the_letter_count_stood_in_for_are_still_dropped():
    """The fix is not "count nothing". A filler word shared by two sentences
    INFLATES their similarity, and two tiers read that score with no model in
    the loop. Both directions were measured while writing this:

        with "is" counted: "Their name is Omar." absorbed "Their name is Omar
                           Ebrahim." at exactly 0.80 and the surname was lost
        with "in" counted: the veto "the renewal closes in 4 weeks" reached
                           0.80 against "the Devon renewal closes in 3 weeks"
                           and DELETED it

    So the closed class is written down instead of counted. This leg goes red
    if a filler word starts counting, and its sibling above goes red if a name
    stops — a fix that only satisfies one of them is not the fix."""
    m = Memory(":memory:", llm=None)
    assert m._compare_words("partner is Jo") == {"partner", "jo"}
    assert m._compare_words("broke up with Jo") == {"broke", "jo"}
    assert not m._same_as("Their name is Omar.", "Their name is Omar Ebrahim.")
    assert not m._same_as("the Devon renewal closes in 3 weeks",
                          "the renewal closes in 4 weeks")


def test_every_live_fact_reaches_the_model_however_low_it_ranks():
    """C3, reproduced on the shipped code. The 0.40 band was removed and the
    RANKING was not: only the three highest-overlap candidates reached the
    model, and a supersession pair is low-overlap BY NATURE because one
    sentence asserts and the other negates.

        stored:   'partner is Dana' (0.333), 'Dana broke her wrist' (0.500),
                  'Dana broke the blender' (0.667), 'Dana broke up with her
                  boss' (0.667)
        incoming: 'broke up with Dana'
        put to the model: the boss, the blender, the wrist
        'partner is Dana' reached the model: False

    Any owner with four facts naming one person lost the pair the feature
    exists for. Restoring `[:3]` — or any cut on the ordered list — goes red
    here."""
    now = time.time()
    m, llm = _four_facts_naming_dana(now)
    m._relate_fact("broke up with Dana", ts=now)
    offered = [n["note"] for a in llm.relation_calls()
               for n in json.loads(a)["stored_notes"]]
    assert "partner is Dana" in offered, offered
    assert len(offered) == 4, offered
    # AND THE TIE GOES TO THE OLDER ROW. The blender and the boss both score
    # 0.667; `sorted(near, reverse=True)` put the higher rowid — the NEWER
    # noise — in front of the older row, which is by definition the one a
    # supersession is about. It decides only ordering now, but ordering is
    # what survives when a batch boundary falls between them.
    assert offered[:2] == ["Dana broke the blender",
                           "Dana broke up with her boss"], offered


def test_the_ranking_only_decides_what_is_asked_first():
    """What a cheap sift may legitimately do here, and the only thing. Overlap
    orders the list so the likely answer is in the first batch — that is honest
    cost control, because the worst case is unchanged and the expected case is
    one call. Excluding is not.

    Sized past _JUDGE_BATCH so the batching itself is exercised: a store with
    more live facts than one prompt holds must still put EVERY one of them to
    the model, in as many calls as it takes. The zero-overlap fact is written
    last so it lands in the final batch."""
    from brain.memory import _JUDGE_BATCH

    now = time.time()
    llm = FakeLLM(relations=["different"] * 200)
    m = Memory(":memory:", llm=llm)
    for i in range(_JUDGE_BATCH + 3):
        # Distinct SUBJECTS, not one subject with a changing number: the
        # latter is a detail update and _relate_fact rightly merges them, so
        # the store would end up holding two rows and never batch.
        m.remember_fact(f"Dana enjoys thing{i}", importance=3,
                        ts=now - 30 * DAY)
    m.remember_fact("home is 4 Maple St", importance=4, ts=now - 30 * DAY)
    llm.calls.clear()
    m._relate_fact("we moved to Rowan Ave", ts=now)
    calls = llm.relation_calls()
    assert len(calls) > 1, "the batching never ran; resize the store"
    offered = [n["note"] for a in calls for n in json.loads(a)["stored_notes"]]
    # Shares NO word with the incoming fact — the shape residual #4 named, and
    # the shape a move actually arrives in.
    assert "home is 4 Maple St" in offered, offered
    assert len(offered) == _JUDGE_BATCH + 4, len(offered)


def test_a_low_ranked_fact_is_still_obeyed_when_the_model_names_it():
    """The other half of the same rule: reaching the model is worth nothing if
    the verdict about it cannot be acted on. The model names the LAST note in
    the list — the lowest-overlap one — and the store retires that row and no
    other."""
    now = time.time()
    m, llm = _four_facts_naming_dana(now)
    llm.relations = ["replaces"]
    llm.answer_n = 4          # 'partner is Dana', ranked last on overlap
    m.remember_fact("broke up with Dana", importance=3, ts=now)
    dead = m.db.execute(
        "SELECT fact FROM profile_facts WHERE retired_ts IS NOT NULL"
    ).fetchall()
    assert [d[0] for d in dead] == ["partner is Dana"], dead


def test_a_verdict_naming_a_note_the_store_never_offered_is_no_verdict():
    """The list-shaped question has one more way to be unreadable than the
    pairwise one did: an "n" that names nothing. A model that answers 9 to a
    list of two has not identified a fact, and acting on it would retire an
    arbitrary row. Same contract as an unknown relation — no verdict leaves
    the profile exactly as it was."""
    import types

    now = time.time()

    class _LLM:
        live = True

        def chat(self, system, user, **kw):
            if "SAME underlying fact" not in system:
                return types.SimpleNamespace(text="{}")
            return types.SimpleNamespace(
                text=json.dumps({"n": 9, "relation": "replaces"}))

    m = Memory(":memory:", llm=_LLM())
    m.remember_fact("partner is Dana", importance=5, ts=now - 30 * DAY)
    m.remember_fact("broke up with Dana", importance=3, ts=now)
    assert all(f["retired_ts"] is None
               for f in m.profile_facts(retired=RETIRED_QUOTED))


# ============================================== THE EPISODE LAYER (RULING 2)
# recall() returned (profile + graph)[:limit] and only `profile` was filtered.
# The docstring ruled episodes out of scope — true of the RECORD, irrelevant
# to the RULING, which governs what may be an input to ACTION.


def _moved_house(now):
    """RULING 2 §7's own example, driven through the real consolidation pass.
    The old address arrives phrased as an IMPERATIVE, which is a stronger
    action signal than the live fact beside it."""
    llm = FakeLLM(
        consolidations=[
            {"facts": [{"fact": "home is 4 Maple St", "importance": 5,
                        "episode_ids": [1], "kind": "stable"}]},
            {"facts": [{"fact": "home is 18 Rowan Ave", "importance": 5,
                        "episode_ids": [2], "kind": "stable"}]},
        ],
        relations=["replaces"])
    m = Memory(":memory:", llm=llm)
    m.ingest("Our home address is 4 Maple St, put that on the delivery.",
             ts=now - 200 * DAY)
    m.consolidate(now=now - 200 * DAY)
    m.ingest("We moved — home is 18 Rowan Ave now.", ts=now - 1 * DAY)
    m.consolidate(now=now - 1 * DAY)
    return m


def test_a_retired_fact_does_not_reach_the_action_lane_as_raw_hearing():
    """Reproduced on the shipped code:

        recall("what is my home address for the delivery",
               retired=RETIRED_EXCLUDED):
           src_type='profile'  known: home is 18 Rowan Ave
           src_type='episode'  heard: "Our home address is 4 Maple St, put
                                       that on the delivery."

    The only mitigation was that profile sorts first and the model MIGHT
    prefer it — model-dependent, which is precisely what RULING 2 refuses for
    this lane: fill_gaps_from_memory is "NEVER — hard filter. No exception, no
    flag."."""
    now = time.time()
    m = _moved_house(now)
    got = m.recall("what is my home address for the delivery",
                   retired=RETIRED_EXCLUDED)
    assert got, "recall came back empty; the fixture is not exercising it"
    assert not any("4 Maple St" in f["fact"] for f in got), got
    assert any("18 Rowan Ave" in f["fact"] for f in got), got


def test_the_dead_address_cannot_settle_a_gap_through_the_episode_layer():
    """The sink where money rides, driven through the REAL function — the
    value being correct and simply never arriving is this repo's recorded
    failure shape (8849df15). filled[gap] -> params[key] -> the browser
    agent's approved values -> a form it submits."""
    import types

    from brain.orchestrator import fill_gaps_from_memory

    now = time.time()
    m = _moved_house(now)
    seen = {}

    class _LLM:
        live = True

        def chat(self, system, user, **kw):
            seen["known"] = user
            return types.SimpleNamespace(text=json.dumps({"answer": "x"}))

    fill_gaps_from_memory(_LLM(), m, "order the groceries for delivery",
                          ["delivery address"])
    assert seen.get("known"), "the gap filler was never reached"
    assert "4 Maple St" not in seen["known"], seen["known"]
    assert "18 Rowan Ave" in seen["known"], seen["known"]


def test_the_speech_lane_still_hears_the_line_that_was_actually_said():
    """The half that must NOT regress. "He said the address was 4 Maple St" is
    a true record of a thing that was said, whenever it is read, and §7's
    broadband answer needs it — she has to name the old address because the
    company's records still show it. Only the ACTION lane drops it."""
    now = time.time()
    m = _moved_house(now)
    got = m.recall("what is my home address for the delivery",
                   retired=RETIRED_QUOTED)
    assert any("4 Maple St" in f["fact"] and f["src_type"] == "episode"
               for f in got), got


def test_a_live_fact_s_own_episode_is_not_collateral():
    """The filter is provenance, so it must take the episodes behind RETIRED
    facts and nothing else. A rule that dropped every episode mentioning a
    retired fact's words, or every episode older than a retirement, would take
    the live fact's own hearing with it."""
    now = time.time()
    m = _moved_house(now)
    got = m.recall("home Rowan moved", retired=RETIRED_EXCLUDED)
    assert any("We moved" in f["fact"] for f in got), got


def test_the_retired_counter_does_not_count_a_retirement_the_fence_refused():
    """M7. _supersede returns a truthy row id on the provenance-fence path too,
    having retired nothing — latent while only mail and calendar were fenced
    and consolidation could not produce them, and REACHABLE the moment an
    overheard line could. `retired` is the one number the nightly print shows,
    and the one place anybody would notice supersession quietly stopping: a
    mislabel there reads as "she corrected herself" on a night she refused
    to."""
    now = time.time()
    m = Memory(":memory:", llm=FakeLLM(relations=["replaces"]))
    m.remember_fact("never books anything through Kayak", importance=5,
                    source="interview", ts=now - 10 * DAY)
    llm = FakeLLM(
        consolidations=[{"facts": [
            {"fact": "books flights through Kayak", "importance": 4,
             "episode_ids": [1]}]}],
        relations=["replaces"])
    m.llm = llm
    m.ingest("They always book through Kayak, you know.", ts=now,
             speaker="other")
    res = m.consolidate(now=now)
    assert res["new"] == 1, res          # the fact still LANDS
    assert res["retired"] == 0, res      # and it killed nothing
    assert "never books anything through Kayak" in \
        [f["fact"] for f in m.profile_facts()]
