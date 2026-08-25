"""A deterministic tier may not answer "same fact" across a word it deleted.

THE MEASURED BUG (Law-1 audit item #44, and the reviewer's re-measurement).
`_compare_words` removes `_STOP` before scoring, and `_STOP` contains "not".
So both of these reduce to {priya, partner}:

    "Priya is my partner"
    "Priya is not my partner"

overlap 1.00, and the `>= 0.8` shortcut in `_relate_fact` returned ("same")
with ZERO model calls. Driven through the real store — ingest, consolidate,
_relate_fact — three shapes, all identical before the fix:

    'Priya is my partner' THEN 'Priya is not my partner'
       model asked 0x -> rows=[('Priya is my partner', 0.6975, retired=None)]
    'Dana is coming to dinner' THEN 'Dana is not coming to dinner'
       model asked 0x -> rows=[('Dana is coming to dinner', 0.6975, None)]
    'the Devon renewal is signed' THEN 'the Devon renewal is not signed'
       model asked 0x -> rows=[('the Devon renewal is signed', 0.6975, None)]

The denial was swallowed by the assertion and the assertion's confidence ROSE
(0.6 -> 0.6975). Nothing was retired. The owner said the opposite of a stored
fact and memory answered by believing the fact harder.

WHY DELETING "not" FROM `_STOP` IS NOT THE FIX, and this file proves it:
`test_the_instance_fix_would_have_left_the_class_open` uses "is"/"was", both
of which are also in `_STOP` and both of which must stay there — they are the
function words a SEARCH must ignore. Tense is the difference between a live
fact and a dead one, exactly as negation is. The family is not "negation
words"; it is EVERY word the comparator cannot see.

THE FIX IS STRUCTURAL, NOT A WORD LIST. `_near_identical_wording` is now the
only route from a word score to a modelless "same", and it refuses whenever
the two texts differ in the tokens the filter REMOVED. A difference the tier
cannot see is a difference it may not rule on — it falls through to the model,
which is where HARNESS-LAW 1 puts the question anyway. No word is classified;
nothing here reads what a sentence means.

`test_no_stopword_alone_may_decide_two_facts_are_one` is the general leg: it
walks `_STOP` itself, so a word added to that list later arrives already
covered instead of re-opening the hole.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brain.memory import Memory  # noqa: E402
from llm_fakes import FakeLLM  # noqa: E402

DAY = 86400.0

# The three shapes the reviewer measured, plus the tense pair that survives
# deleting "not". (first said, said later)
CONTRADICTIONS = [
    ("Priya is my partner", "Priya is not my partner"),
    ("Dana is coming to dinner", "Dana is not coming to dinner"),
    ("the Devon renewal is signed", "the Devon renewal is not signed"),
]


def _two_pass_store(first: str, second: str, now: float):
    """The real path: two nights of consolidation, the second one distilling
    a fact that contradicts the first."""
    llm = FakeLLM(
        consolidations=[
            {"facts": [{"fact": first, "importance": 5,
                        "episode_ids": [1], "kind": "stable"}]},
            {"facts": [{"fact": second, "importance": 5,
                        "episode_ids": [2], "kind": "stable"}]},
        ],
        relations=["replaces"],
    )
    m = Memory(":memory:", llm=llm)
    m.ingest("he said the first thing", ts=now - 40 * DAY)
    m.consolidate(now=now - 40 * DAY)
    m.ingest("he said the second thing", ts=now - 2 * DAY)
    m.consolidate(now=now - 2 * DAY)
    return m, llm


def _store_holding(fact: str, ts: float) -> Memory:
    """One stored fact and NO model at all, so a deterministic "same" is the
    only thing that can possibly answer."""
    m = Memory(":memory:", llm=None)
    m._insert_fact(fact, 5, 0.6, "consolidation", ts, [])
    m.db.commit()
    return m


# ------------------------------------------------------- the measured shapes

def test_a_denial_reaches_the_model_instead_of_merging_into_what_it_denies():
    now = time.time()
    for first, second in CONTRADICTIONS:
        m, llm = _two_pass_store(first, second, now)
        assert llm.relation_calls(), (
            f"{second!r} never reached the model at all; it was merged into "
            f"{first!r} by a word score")
        rows = dict(m.db.execute(
            "SELECT fact, retired_ts IS NOT NULL FROM profile_facts"))
        assert rows == {first: 1, second: 0}, (first, second, rows)


def test_the_denied_fact_does_not_gain_confidence_from_being_denied():
    """The half of the bug that is worse than the missing question: the
    contradiction landed as EVIDENCE FOR the thing it contradicted."""
    now = time.time()
    first, second = CONTRADICTIONS[0]
    m, _ = _two_pass_store(first, second, now)
    conf = dict(m.db.execute("SELECT fact, confidence FROM profile_facts"))
    assert conf[first] == 0.6, conf


def test_the_instance_fix_would_have_left_the_class_open():
    """Deleting "not" from `_STOP` closes three sentences and nothing else.

    "is" and "was" are both in `_STOP`, both belong there for search, and the
    difference between them is the difference between a partner and an ex.
    """
    now = time.time()
    m, llm = _two_pass_store("Priya is my partner", "Priya was my partner", now)
    assert llm.relation_calls(), (
        "'Priya was my partner' was merged into 'Priya is my partner' by a "
        "word score — the tense was invisible to it")


# ------------------------------------------------------------- the class leg

def test_no_stopword_alone_may_decide_two_facts_are_one():
    """THE GENERAL LEG. For every word `_compare_words` throws away, two facts
    differing by exactly that word must not be called the same one without a
    model. With `llm=None` the honest answer is (None, "different") — no
    verdict, so no merge.

    The base sentence deliberately contains no stopword of its own, so the
    inserted word is the ONLY difference and the two dropped-token sets differ
    by exactly it.
    """
    now = time.time()
    base = "devon renewal signed"
    failures = []
    for w in sorted(Memory._STOP):
        m = _store_holding(base, now - 10 * DAY)
        rid, relation = m._relate_fact(f"devon renewal {w} signed", ts=now)
        if relation != "different":
            failures.append((w, rid, relation))
    assert not failures, failures


# --------------------------------------------- and the shortcut still works

def test_wording_that_differs_only_where_the_tier_can_see_still_merges():
    """The mutation guard. The `>= 0.8` shortcut exists so a near-verbatim
    restatement does not cost a model call, and that must survive: same
    dropped words on both sides, one extra visible word, still "same" with no
    model in the store at all."""
    now = time.time()
    m = _store_holding("devon renewal closes friday", now - 10 * DAY)
    rid, relation = m._relate_fact("devon renewal closes friday soon", ts=now)
    assert (rid, relation) == (1, "same"), (rid, relation)


def test_a_changed_number_is_still_reported_as_a_changed_detail():
    """The other deterministic shortcut — same subject, different number —
    also still fires when the dropped words match on both sides."""
    now = time.time()
    m = _store_holding("dinner with sarah at 6", now - 10 * DAY)
    rid, relation = m._relate_fact("dinner with sarah at 8", ts=now)
    assert (rid, relation) == (1, "same"), (rid, relation)
    assert m._last_match_changed_detail is True


def test_the_changed_number_shortcut_cannot_cross_an_invisible_word_either():
    """Both deterministic tiers go through the same guard, so the hole cannot
    be reopened by walking in through the numbers branch."""
    now = time.time()
    m = _store_holding("dinner with sarah at 6", now - 10 * DAY)
    rid, relation = m._relate_fact("dinner with sarah is not at 8", ts=now)
    assert relation == "different", (rid, relation)
    assert m._last_match_changed_detail is False
