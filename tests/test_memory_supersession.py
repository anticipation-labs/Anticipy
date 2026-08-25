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

WHAT IS BEING TESTED, and where each rule lives:

  * the model decides the relation (same / replaces / different). Nothing here
    reads the words. `test_the_pair_reaches_the_model_at_all` is the leg that
    goes red if the sift ever narrows back.
  * retirement gates ACTION absolutely and SPEECH conditionally
    (docs/DECISIONS-2026-08-24.md RULING 2). The action lane is the default of
    profile_facts()/recall(); the speech lane is asked for by name and comes
    back with the retirement written into the fact's own sentence.
  * two deterministic guards, both structure: the older side loses whichever
    way it arrived, and untrusted text may not retire something the owner said.
  * with no model, nothing is retired and nothing raises.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brain.memory import RETIRED_QUOTED, Memory  # noqa: E402
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
    assert "partner is Dana" in asked[0]
    assert "broke up with Dana" in asked[0]
    # And the ages ride along: which fact has taken the other's place is a
    # question about WHEN, and asking it without the dates is asking the model
    # to guess.
    assert "a_last_heard_days_ago" in asked[0]
    assert "b_last_heard_days_ago" in asked[0]


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
    """The prompt asks which of two facts is true NOW. That question has no
    answer about a fact that already stopped being true, and a "replaces"
    verdict against a corpse would retire something twice.

    THE INCOMING TEXT IS CHOSEN SO ONLY THE DEAD ROW CAN BE A CANDIDATE.
    Written the obvious way — an incoming fact sharing a word with both rows —
    this check passed while the guard was removed: the live row sorted first,
    answered "replaces", and _relate_fact returned before the dead row was ever
    reached. It was green for the ordering, not for the rule. "partner is away
    this week" overlaps the retired "partner is Dana" and shares nothing with
    "broke up with Dana", so if the dead row is a candidate at all the model
    gets asked and this goes red."""
    now = time.time()
    m, llm = _breakup_store(now)
    llm.calls.clear()
    llm.relations = ["different", "different"]
    m._relate_fact("partner is away this week", ts=now - 20 * DAY)
    assert llm.relation_calls() == [], llm.relation_calls()


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
