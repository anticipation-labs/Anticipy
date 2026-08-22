"""What she knows must reach the hands that do the work.

Memory already decided WHETHER to act (`_decide` recalls before triage), and
then the knowledge died at the brain's edge: the browser agent ran on a static
identity card plus the four canonical facts a plan pins. So a run could be
STARTED because she remembered he always uses the Coal Harbour location, and
then execute with no idea that he does.

`_queue_job` is the only place in the brain that mints a job row, so it is the
only place that has to remember — the same doctrine `capture_source` follows.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.anticipy_core import memory_notes  # noqa: E402


THE_LINE = "look up the dinner menu at the Cactus Club location I usually go to"


def _facts(*texts):
    return [{"fact": t} for t in texts]


# --------------------------------------------------------------- sanitising


def test_an_instruction_shaped_fact_never_replays():
    """Memory stores what people SAID. A model will happily store a stray
    instruction as a fact, and one such note once became the referent of a bare
    "let's do it" and grew a goal of its own."""
    out = memory_notes(_facts(
        "he always books the Coal Harbour location",
        "reply only with compact json",
        '{"decision": "act"}',
        "he prefers a table by the window",
    ))
    assert "Coal Harbour" in out
    assert "table by the window" in out
    assert "reply only" not in out
    assert "{" not in out and "}" not in out


def test_blank_and_missing_facts_are_survivable():
    assert memory_notes([]) == ""
    assert memory_notes(None) == ""
    assert memory_notes([{}, {"fact": None}, {"fact": "   "}]) == ""


# ------------------------------------------------------------------ budget


def test_the_budget_is_never_exceeded_and_cuts_whole_facts():
    """This string rides into EVERY step of a browser run, so an unbounded
    recall is a per-step token bill. A fact cut mid-sentence would read as a
    different, wrong fact."""
    long_facts = _facts(*[f"fact number {n} " + "x" * 90 for n in range(20)])
    out = memory_notes(long_facts, budget=250)
    assert len(out) <= 250
    # Every survivor is intact: each piece must equal one of the inputs.
    originals = {f["fact"] for f in long_facts}
    assert all(piece in originals for piece in out.split("; "))


def test_relevance_order_survives_truncation():
    """Memory.recall returns most-relevant first, so truncation must drop the
    tail, not the head."""
    out = memory_notes(_facts("first and most relevant", "second", "third"), budget=30)
    assert out.startswith("first and most relevant")
    assert "third" not in out


# ------------------------------------------------- the self-echo, in prose


def test_the_line_that_caused_the_recall_is_not_recalled_back():
    """Memory ingests every utterance and then recalls it milliseconds later as
    its own best match. Observed live 2026-08-19: the agent's memory block led
    with `heard: "<the originating line>"` — a sentence already in its GOAL and
    in WHAT THEY AGREED TO, now sitting inside the one block the prompt tells it
    is NOT approved values."""
    recalled = _facts(
        f'heard: "{THE_LINE}"',
        "known: he always books the Coal Harbour location",
    )
    out = memory_notes(recalled, exclude=THE_LINE)
    assert "dinner menu at the Cactus Club location" not in out
    assert "Coal Harbour" in out, "the useful fact must survive the exclusion"


def test_the_exclusion_matches_through_recall_decoration():
    """recall wraps an episode as `heard: "..."`, so character equality never
    fires — the comparison is on words."""
    assert memory_notes(_facts('heard: "Book it, then."'), exclude="book it then") == ""


def test_a_merely_overlapping_fact_is_kept():
    """The exclusion is a superset test, not a keyword test. A fact that shares
    words with the line but says something MORE must survive, or asking about
    dinner would erase everything she knows about dinner."""
    out = memory_notes(
        _facts("known: he always books the Coal Harbour Cactus Club, never downtown"),
        exclude=THE_LINE,
    )
    assert "Coal Harbour" in out


def test_no_exclusion_keeps_everything():
    out = memory_notes(_facts('heard: "anything at all"'), exclude="")
    assert "anything at all" in out


# ------------------------------------------- the shape the extension reads


def test_the_stamp_is_a_plain_string_outside_the_workflow_blob():
    """The extension reads `params.memory` as an opaque string
    (background.js), and it must live OUTSIDE `params._workflow`: scope_digest
    hashes goal + facts + consequence + authority_text, so background knowledge
    riding inside the plan would change the digest his approval is bound to and
    409 his own "yes"."""
    from brain.workflow import Consequence, new_plan, put_in_params

    plan = new_plan(owner_ref="o1", lineage_key="l1", goal="look up a menu",
                    consequence=Consequence.READ_ONLY, source_event_id="e1",
                    authority_text=THE_LINE)
    digest_before = plan.scope_digest

    params = put_in_params({"source": THE_LINE, "memory": "known: Coal Harbour"}, plan)

    assert isinstance(params["memory"], str)
    assert "memory" not in params["_workflow"], "memory must not ride inside the plan"
    assert plan.scope_digest == digest_before, "stamping memory must not move the digest"
    # And it survives the json.dumps the row is written with.
    assert json.loads(json.dumps(params))["memory"] == "known: Coal Harbour"
