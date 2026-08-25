"""Recall scores a fact on what HE said, never on what the store wrote around it.

A retired fact does not reach a speech sink bare. `_retired_note` wraps it so
the retirement travels inside the sentence (RULING 2):

    no longer true — retired 30 days ago: home is 4 Maple St

`profile_facts` puts that rendered sentence in the row's `fact` key, and
`_profile_recall` then scored query relevance by counting query words in that
same key. So seven words the owner never said about the fact — "longer",
"true", "retired", "days", "ago", "today", "yesterday" — became matchable
text, on every retired row in the store, forever.

MEASURED against the shipped code before this file existed:

    store: "home is 4 Maple St"  retired by  "home is 18 Rowan Ave"
    recall("is that still true", retired=RETIRED_QUOTED)

      sal=  0.000  known: home is 18 Rowan Ave          <- padded, matched nothing
      sal=  4.700  no longer true — retired 2 days ago: home is 4 Maple St

    "is that still true" reduces to {"true"} — "is"/"that"/"still" are all in
    _STOP. The word "true" appears in NO fact this store holds. The dead row
    was the only thing recall scored as RELEVANT to the question, and it scored
    4.7, because it matched a word this file's own renderer had put there.

WHY IT IS ONLY HALF A DISASTER, stated plainly rather than left flattering:
the action lane filters retired rows in the WHERE clause (`profile_facts`), so
this can never reach a form the browser agent fills. It is a SPEECH-lane
defect: the briefing, the SMS answer and triage context ask for RETIRED_QUOTED
by name, and they are the sinks that got handed a dead fact as the most
relevant thing in the store on a question it has nothing to do with.

WHY IT IS NOT A LAW-1 FIX AND NOT A WORD LIST. Nothing here decides what any
sentence MEANS. The model still decides "replaces"; `_retired_note` still
decides the wording. This only says WHICH TEXT the relevance count is taken
over — the fact as stored, not the presentation this module generated. Reading
a score off your own boilerplate is not a judgement about meaning, it is a
column mix-up.

The general leg is `test_no_word_of_the_retirement_wrapper_ever_scores`: it
derives the wrapper's whole vocabulary from `_retired_note` itself, so adding
a word to that sentence later re-arms this test instead of quietly widening
the hole again. `_wrapper_words` takes EVERY token the renderer adds — it used
to filter to `len(w) > 2 and w.isalpha()`, which silently dropped a day count
or a bracketed marker from the derived set and made that promise false for
anything but plain words.

WHAT THE FIX DELIBERATELY GIVES UP, stated here because nothing else in the
tree records it. After it, no query can reach a retired fact by asking about
RETIREMENT ITSELF: "what is no longer true", "what did you retire recently",
"is that still true" all score every dead row 0.0. A dead row now arrives only
by its OWN wording, or through the salience-0 padding branch that sorts it
last and drops it first. That is a real narrowing and it is the intended one —
matching a fact on boilerplate this module wrote is not evidence the question
was about that fact — but a future agent looking for "why did asking about
retirement stop working" should find the answer here.

AND THE BLAST RADIUS IS SMALLER THAN IT LOOKS. `_profile_recall` already
sorted dead rows last before this fix, and no sink reads `salience`, so the
delta is not ordering — it is WHICH ROWS SURVIVE A FULL RECALL WINDOW. When
the window is not full, the same rows come back either way.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from brain.memory import (RETIRED_EXCLUDED, RETIRED_QUOTED,  # noqa: E402
                          Memory, _retired_note)
from llm_fakes import FakeLLM  # noqa: E402

DAY = 86400.0


def _moved_store(now: float):
    """The §7 broadband scenario, driven through the real consolidation pass:
    an address distilled forty days ago, the move distilled two days ago."""
    llm = FakeLLM(
        consolidations=[
            {"facts": [{"fact": "home is 4 Maple St", "importance": 5,
                        "episode_ids": [1], "kind": "stable"}]},
            {"facts": [{"fact": "home is 18 Rowan Ave", "importance": 5,
                        "episode_ids": [2], "kind": "stable"}]},
        ],
        relations=["replaces"],
    )
    m = Memory(":memory:", llm=llm)
    m.ingest("Our place at 4 Maple St.", ts=now - 40 * DAY)
    m.consolidate(now=now - 40 * DAY)
    m.ingest("We moved to 18 Rowan Ave last week.", ts=now - 2 * DAY)
    m.consolidate(now=now - 2 * DAY)
    return m, llm


def _wrapper_words(now: float) -> set:
    """Every word `_retired_note` adds that a query could match, read off the
    renderer rather than copied from it.

    Three ages, because the sentence branches on them ("today", "yesterday",
    "N days ago") and a word that only appears in one branch is still a word
    the owner never said. The fact passed in is a nonsense token so that
    nothing of the FACT's own wording is mistaken for the wrapper's.

    NOTHING IS FILTERED OUT OF THIS SET. It used to keep only
    `len(w) > 2 and w.isalpha()`, which is the derivation quietly making the
    same call the code under test makes — so a day count ("30") or a bracketed
    marker added to the wrapper later would have been dropped here and would
    NOT have re-armed the test, which is the one thing this leg promises. A
    token `recall` itself declines to seed on simply asks nothing and passes;
    that costs a case, where dropping it costs the guarantee."""
    words = set()
    for age in (0.0, 1 * DAY, 30 * DAY):
        rendered = _retired_note("zzqqxx", now - age, now)
        words |= {w.strip(".,!?:—-").lower()
                  for w in rendered.replace("zzqqxx", " ").split()}
    return {w for w in words if w}


# ------------------------------------------------------------ the measured bug

def test_the_setup_really_does_retire_the_old_address():
    """Guard on the scenario itself: if the retirement stops happening these
    legs would pass by having nothing to test."""
    now = time.time()
    m, _ = _moved_store(now)
    rows = dict(m.db.execute(
        "SELECT fact, retired_ts IS NOT NULL FROM profile_facts"))
    assert rows == {"home is 4 Maple St": 1, "home is 18 Rowan Ave": 0}


def test_a_word_only_the_store_wrote_does_not_make_a_dead_fact_relevant():
    now = time.time()
    m, _ = _moved_store(now)
    # "true" is in no fact this store holds. It is only in the wrapper.
    for (fact,) in m.db.execute("SELECT fact FROM profile_facts"):
        assert "true" not in fact.lower(), fact

    hits = m.recall("is that still true", retired=RETIRED_QUOTED)
    dead = [h for h in hits if h.get("retired_ts") is not None]
    assert dead, "the quoted lane must still carry the retired fact"
    # It may be PRESENT — the padding branch pads the window with facts that
    # matched nothing, and that is deliberate. It may not be SCORED, because
    # scoring it is the claim that it answers the question.
    assert all(h["salience"] == 0.0 for h in dead), \
        [(round(h["salience"], 3), h["fact"]) for h in dead]


def test_the_derived_vocabulary_is_every_token_the_wrapper_adds():
    """Guard on the leg below, because that leg is only as general as its
    derivation. Every token `_retired_note` writes around the fact must be in
    the set — including the day count, which `w.isalpha()` used to drop."""
    now = time.time()
    derived = _wrapper_words(now)
    for age in (0.0, 1 * DAY, 30 * DAY):
        rendered = _retired_note("zzqqxx", now - age, now)
        for raw in rendered.replace("zzqqxx", " ").split():
            token = raw.strip(".,!?:—-").lower()
            if token:
                assert token in derived, (rendered, token, sorted(derived))


def test_no_word_of_the_retirement_wrapper_ever_scores():
    """The general leg. Every word `_retired_note` adds, asked as its own
    one-word question, must leave every dead row unscored."""
    now = time.time()
    for word in sorted(_wrapper_words(now)):
        m, _ = _moved_store(now)
        hits = m.recall(word, retired=RETIRED_QUOTED)
        scored_dead = [h for h in hits
                       if h.get("retired_ts") is not None
                       and h["salience"] > 0.0]
        assert not scored_dead, (
            word, [(round(h["salience"], 3), h["fact"])
                   for h in scored_dead])


# ------------------------------------------- and the fix did not zero the lane

def test_a_dead_fact_the_question_really_is_about_still_scores():
    """The mutation guard. Making relevance read the stored wording must not
    turn into 'retired facts never match anything' — the §7 answer needs the
    old address to come back when he asks about the old address."""
    now = time.time()
    m, _ = _moved_store(now)
    hits = m.recall("what was our maple address", retired=RETIRED_QUOTED)
    dead = [h for h in hits if h.get("retired_ts") is not None]
    assert dead, "the old address must still be reachable as history"
    assert dead[0]["salience"] > 0.0, [
        (round(h["salience"], 3), h["fact"]) for h in dead]
    # and it still says out loud that it is history
    assert dead[0]["fact"].startswith("no longer true — retired")


def test_a_live_fact_scores_exactly_as_it_did():
    """Live rows carry no wrapper, so nothing about them may move."""
    now = time.time()
    m, _ = _moved_store(now)
    hits = m.recall("what is our rowan address", retired=RETIRED_QUOTED)
    live = [h for h in hits if h.get("retired_ts") is None]
    assert live and live[0]["fact"] == "known: home is 18 Rowan Ave"
    assert live[0]["salience"] > 0.0


def test_the_action_lane_is_unchanged_and_still_holds_nothing_dead():
    """The PROFILE half of the action-lane guard — the WHERE clause in
    `profile_facts`. It does not reach the episode layer; see the leg below,
    which does, and which this one was once wrongly credited with covering."""
    now = time.time()
    m, _ = _moved_store(now)
    for q in ("is that still true", "what was our maple address"):
        hits = m.recall(q, retired=RETIRED_EXCLUDED)
        assert all(h.get("retired_ts") is None for h in hits), (q, hits)
        assert not any("Maple" in h["fact"] for h in hits), (q, hits)


def test_the_dead_address_cannot_come_back_through_the_raw_episode_either():
    """The OTHER half of the same guard: `dead_episodes` in `recall`.

    A retired fact's source episode is that fact in undistilled form, and it
    carries no retirement marker at all — `heard: "Our place at 4 Maple St."`
    reads as a live instruction on its way to filled[gap] -> params[key].

    The queries above never exercise this: the episode scores 1 hit and the
    layer needs 2, so forcing `dead_episodes = set()` left every leg in this
    file green. "maple place" scores 2 and reaches it. MEASURED here — in the
    speech lane the same query returns `heard: "Our place at 4 Maple St."`, so
    the row genuinely exists and is genuinely being filtered, not merely
    absent."""
    now = time.time()
    m, _ = _moved_store(now)

    quoted = m.recall("maple place", retired=RETIRED_QUOTED)
    assert any(h["fact"].startswith('heard:') and "Maple" in h["fact"]
               for h in quoted), quoted

    hits = m.recall("maple place", retired=RETIRED_EXCLUDED)
    assert not any("Maple" in h["fact"] for h in hits), hits
