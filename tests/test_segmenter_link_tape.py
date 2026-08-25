"""`_ANAPHORIC` AND `decide_link`'s BAND-3 PREFILTER — the stakes, and the expiry.

`brain/segmenter.py:44-46` holds an opener word list, and `decide_link`
(:113-156) combines it with a ">=2 content-word overlap" count and a "<8 words"
length test to decide whether two turns are ABOUT THE SAME THING. That is
meaning decided by a word list — Law 1. It was flagged on 2026-08-25 by the
EARS turn-envelope spec (docs/superpowers/specs/2026-08-25-ears-turn-envelope.md
§9 item 1 and §12 item 4), which explicitly declines to defend it.

This file does two jobs, and the second only makes sense because of the first.

1. IT PINS THE BLAST RADIUS, MEASURED RATHER THAN REPEATED. Two claims were in
   circulation and they cannot both be acted on:
     - worker.py:3774 says of `place_turn` "NOTHING reads it yet ... this is
       observation only";
     - the brief-level worry that `decide_link` feeds triage, because
       `SegmentStore.recent_turns` really does become `convo_context` at
       worker.py:3703 and is really passed to `hear()` at :3725/:3746.
   Both are half true, and the half that matters is neither. `recent_turns`
   IS live and DOES feed the judge — but it reads `events.segment`, and which
   segment a live turn is stamped into is decided by `should_close`, a pure
   CLOCK rule (a sense, and lawful). `decide_link`'s verdict reaches exactly
   one field, `parent_segment`, which nothing in the repository reads.
   `test_the_live_verdict_only_moves_parent_segment` is that measurement, and
   it is the reason this ships REGISTERED rather than rewritten around a model
   call in the ingest hot path.

   The pin matters more than the finding: the day somebody wires the verdict
   into segment membership, the trade this registration rests on is void, and
   that test is what says so out loud instead of letting the tape quietly
   become load-bearing.

2. IT PINS THAT THE TAPE IS DECLARED. Law 2: an emergency string patch ships
   with a `TAPE:` comment naming the real fix AND a gate leg that stays red
   until it is gone. `test_the_word_list_is_registered_as_tape` and
   `test_leg_2_is_red_because_of_this_tape` fail the moment either book stops
   naming it — a marker deleted, or a registry entry dropped — while the
   regex is still running.

WHAT THIS FILE DOES NOT DO: build Trigger A, the gate's "<6 content words ->
auto-fail" short-circuit, or a replacement for the "<2 words = fragment" guard
at anticipy_core.py:1452-1455. All three are named as unbuilt in the same spec
section, and naming them here is so nobody reads this file as cover for them.
"""
from __future__ import annotations

import importlib.util
import os

import pytest

from brain import segmenter
from brain.segmenter import (CONTINUE_S, GATE_BAND_S, decide_link, place_turn,
                             segment_all)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 1_756_000_000


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "tape_gate", os.path.join(ROOT, "overnight", "tape_gate.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tg = _load_gate()

# The taped text, spelled here exactly as the registry spells it. If these two
# ever disagree the registry is tracking something this file does not mean.
NEEDLE = "_ANAPHORIC = re.compile("


# --------------------------------------------------------------------------
# 1. THE BLAST RADIUS — what a wrong verdict can actually reach today.
# --------------------------------------------------------------------------
class FakeStore:
    """The four calls `place_turn` makes, recorded rather than performed.

    Deliberately NOT a mock of SegmentStore: it records what was WRITTEN, which
    is the only thing a downstream reader can ever see.
    """

    def __init__(self, open_seg=None, closed_seg=None):
        self._open = open_seg
        self._closed = closed_seg
        self.created = []          # [(started, parent)]
        self.appended = []         # [(segment_id, text)]
        self.stamped = []          # [(event_id, segment_id)]
        self.closed_calls = []
        self._n = 0

    def open_segment(self):
        return self._open

    def last_closed(self):
        return self._closed

    def close(self, segment, ended):
        self.closed_calls.append(segment["id"])

    def create(self, started, parent=None):
        self._n += 1
        self.created.append((started, parent))
        return {"id": f"fresh{self._n}", "entities": "[]", "turn_count": 0,
                "word_count": 0}

    def append(self, segment, event, ended):
        self.appended.append((segment["id"], event.get("text") or ""))

    def stamp_event(self, event_id, segment_id):
        self.stamped.append((event_id, segment_id))


def _prev_closed(ended_off=0):
    from brain.segmenter import iso, parse_ts
    end = parse_ts(BASE + ended_off)
    return {"id": "prev1", "summary": "the roof needs doing before winter",
            "entities": "[]", "ended_at": iso(end), "last_speech_at": iso(end)}


def _event(off=600, text="anyway I was going to say something else entirely"):
    return {"id": "ev1", "text": text,
            "capture_started_at": BASE + off,
            "capture_ended_at": BASE + off + 4}


VERDICTS = ("append", "link", "new", "escalate")


def test_the_live_verdict_only_moves_parent_segment():
    """THE MEASUREMENT THE REGISTRATION RESTS ON.

    `place_turn` creates a FRESH segment and stamps the turn into it on every
    one of the four verdicts. The verdict changes `parent_segment` and nothing
    else — not which segment the turn joins, not what `recent_turns` will
    return for it, not what the iOS feed groups by (`events.segment`).

    So a wrong `_ANAPHORIC` verdict today cannot change what the triage judge
    reads. It writes one column that no reader in this repository opens.

    If this test ever fails, the verdict has become load-bearing and the tape's
    severity has to be re-argued from scratch — a per-turn model call stops
    being the wrong trade the moment the answer reaches `hear()`.
    """
    seen = {}
    for verdict in VERDICTS:
        store = FakeStore(open_seg=None, closed_seg=_prev_closed())
        original = segmenter.decide_link
        segmenter.decide_link = lambda *a, **k: (verdict, "forced by the test")
        try:
            out = place_turn(store, _event(), now=None)
        finally:
            segmenter.decide_link = original
        # Read defensively and say what happened. The obvious way to break
        # this property — rejoining `prev` on a link verdict instead of
        # opening a fresh row — makes `store.created` EMPTY, and indexing it
        # blind fails with a bare IndexError that reads like a broken test
        # rather than like the news it actually is.
        assert store.created, (
            f"verdict {verdict!r} joined an EXISTING segment instead of "
            f"opening a fresh one (stamped {store.stamped}). The verdict now "
            "decides segment membership, so it decides what `recent_turns` "
            "returns, so it decides what `hear()` reads. `_ANAPHORIC` is no "
            "longer cosmetic and the registration in overnight/tape_gate.py "
            "has to be re-argued as a fix.")
        seen[verdict] = {
            "stamped": list(store.stamped),
            "appended": list(store.appended),
            "parent": store.created[0][1],
            "segment": out.get("segment"),
        }

    # Membership is identical under every verdict.
    first = seen["append"]
    for verdict in VERDICTS:
        assert seen[verdict]["stamped"] == first["stamped"], (
            f"{verdict} stamped the turn somewhere else: "
            f"{seen[verdict]['stamped']} vs {first['stamped']}")
        assert seen[verdict]["appended"] == first["appended"], verdict
        assert seen[verdict]["segment"] == first["segment"], verdict

    # And a fresh segment really was opened — not the previous one rejoined.
    assert first["stamped"] == [("ev1", "fresh1")], first["stamped"]

    # The ONE thing the verdict moves.
    assert seen["link"]["parent"] == "prev1"
    assert seen["escalate"]["parent"] == "prev1"
    assert seen["new"]["parent"] is None
    assert seen["append"]["parent"] is None


def test_nothing_in_the_repo_reads_parent_segment():
    """The other half of the same measurement, and the half a unit test cannot
    reach: `parent_segment` is WRITTEN by segmenter.create and read by nobody.

    Scanned rather than asserted from memory, because this is exactly the kind
    of claim that goes stale — two Brief claims were found stale on 2026-08-25,
    and worker.py's own "NOTHING reads it yet" is one of them.

    A hit outside the writer and the schema means somebody built a reader, and
    the verdict now reaches whatever they built.
    """
    import subprocess
    out = subprocess.run(
        ["git", "grep", "-n", "parent_segment", "--", "brain", "app",
         "extension", "backend", "proof", "firmware"],
        cwd=ROOT, capture_output=True, text=True).stdout
    hits = [ln for ln in out.splitlines() if ln.strip()]
    allowed = (
        "brain/segmenter.py",      # the writer
        "backend/pb_migrations/",  # the column definition
        "brain/sorter.py",         # prose only — checked below
    )
    stray = [h for h in hits if not h.startswith(allowed)]
    assert not stray, (
        "somebody now reads or writes `parent_segment` outside the writer and "
        "the schema:\n  " + "\n  ".join(stray) + "\n"
        "`decide_link`'s verdict lands in that column. If it is read, the "
        "verdict reaches a reader, and tests/test_segmenter_link_tape.py's "
        "argument for registering rather than fixing is void.")
    # sorter.py must be prose, not code: a comment and a constant's docstring.
    for hit in hits:
        if hit.startswith("brain/sorter.py"):
            body = hit.split(":", 2)[-1].strip()
            assert body.startswith("#") or '"' in body or "'" in body, (
                f"brain/sorter.py now touches parent_segment in code: {hit}")


def test_the_word_list_decides_a_conversation_boundary_in_segment_all():
    """Where the verdict IS the answer: the pure entry point.

    `segment_all` is what `overnight/done_gate.py` leg 2 measures and what any
    future segment-granularity triage will group by. Here `decide_link` decides
    the boundary outright — so the tape is inert in the live path and decisive
    in the measured one, and both halves belong in the record.

    The demonstration is the Law-1 violation itself: two continuations of the
    same length, the same emptiness of shared vocabulary and the same gap, told
    apart ONLY by which word they open with.
    """
    prior = {"id": "t0", "text": "the roof needs doing before winter",
             "capture_started_at": BASE, "capture_ended_at": BASE + 4}
    gap = int((CONTINUE_S + GATE_BAND_S) / 2)      # inside the near band
    assert CONTINUE_S < gap < GATE_BAND_S

    def follow(text):
        return {"id": "t1", "text": text,
                "capture_started_at": BASE + 4 + gap,
                "capture_ended_at": BASE + 8 + gap}

    on_the_list = "anyway I was going to say something else entirely about that"
    off_the_list = "returning to it I was going to say something else entirely"

    # Same length band, same absence of overlap: only the opener differs.
    assert len(on_the_list.split()) >= 8 and len(off_the_list.split()) >= 8

    assert len(segment_all([prior, follow(on_the_list)])) == 1, (
        "'anyway ...' no longer relinks — the opener list changed")
    assert len(segment_all([prior, follow(off_the_list)])) == 2, (
        "'returning to it ...' no longer splits — the opener list changed")


def test_the_opener_list_is_what_makes_that_difference():
    """The same two lines through `decide_link` directly, so the failure names
    the rule rather than the grouping."""
    prior = {"summary": "the roof needs doing before winter", "entities": "[]"}
    gap = float(int((CONTINUE_S + GATE_BAND_S) / 2))
    linked, why_linked = decide_link(
        gap, "anyway I was going to say something else entirely about that",
        prior)
    escalated, _ = decide_link(
        gap, "returning to it I was going to say something else entirely",
        prior)
    assert (linked, escalated) == ("link", "escalate"), (linked, escalated)
    assert "anaphoric" in why_linked


# --------------------------------------------------------------------------
# 2. THE EXPIRY — Law 2, from the side of the file that carries the tape.
# --------------------------------------------------------------------------
def test_the_word_list_is_registered_as_tape():
    """The regex is in the tree, so a registry entry has to be tracking it.

    Law 2's registry is `overnight/tape_gate.py`. An entry whose `find` is the
    taped text and whose state is LIVE is the expiry: it goes green only when
    the text is gone from the shipped organs.
    """
    src = open(os.path.join(ROOT, "brain", "segmenter.py"),
               encoding="utf-8").read()
    assert NEEDLE in src, (
        "the tape is gone from brain/segmenter.py — good. Now CLOSE its "
        "registry entry (move the Tape(...) literal into CLOSED_TAPE) and "
        "delete this test's expectation, in the same diff.")

    entries = [t for t in tg.KNOWN_TAPE if t.find == NEEDLE]
    assert len(entries) == 1, (
        "`_ANAPHORIC` is running in brain/segmenter.py and "
        f"overnight/tape_gate.py has {len(entries)} registry entries whose "
        "`find` is it. Law 2: tape with no expiry is a rejected diff.")
    entry = entries[0]
    assert entry.rel == "brain/segmenter.py"
    state, where = entry.state(ROOT)
    assert state == tg.LIVE, (state, where)


def test_the_tape_comment_is_in_range_and_names_the_gate():
    """The marker has to be findable BY THE GATE, not merely nearby.

    `MARKER_RE` wants `TAPE` then an optional (...) then a colon or a full
    stop — a comma does not match — and `Tape.marker_line` only looks in a
    window around the taped text. A declaration outside that window reads as
    compliant to a human grepping TAPE and enforces nothing, which is audit
    item #21's shape.
    """
    entry = [t for t in tg.KNOWN_TAPE if t.find == NEEDLE][0]
    line = entry.marker_line(ROOT)
    assert line, (
        "no `TAPE:` marker inside the window overnight/tape_gate.py searches "
        "around `_ANAPHORIC`. It has to sit within 400 characters BEFORE the "
        "taped text (or 900 after), and the marker form is `TAPE:` or "
        "`TAPE (...):` — a comma does not match.")
    home = entry.marker_text(ROOT)
    assert tg.THIS_GATE in home, (
        "the `TAPE:` comment does not name overnight/tape_gate.py, so nothing "
        "tracks its removal — audit item #21 exactly.")
    assert "Law 2" in home


def test_leg_2_is_red_because_of_this_tape():
    """The expiry is a predicate that RUNS, not a sentence somebody meant.

    Leg 2 is red by design while any registered tape lives. This asserts our
    entry is one of the reasons — so deleting the registry entry without
    deleting the regex shows up here as well as in leg 1.
    """
    with pytest.raises(tg.LegFailed) as e:
        tg.leg_2_tape_expires(ROOT)
    assert "_ANAPHORIC" in str(e.value)


def test_the_ledger_carries_the_bullet_too():
    """Three books, and the human one is what the next agent believes."""
    entry = [t for t in tg.KNOWN_TAPE if t.find == NEEDLE][0]
    laws = open(os.path.join(ROOT, "HARNESS-LAWS.md"), encoding="utf-8").read()
    section = tg.ledger_section(laws, tg.STANDING_HEADING)
    assert section and entry.ledger_needle in section, (
        f"HARNESS-LAWS.md's standing-tape ledger has no {entry.ledger_needle} "
        "bullet. Law 2 costs three edits in three files, in one diff.")


def test_registering_did_not_turn_another_leg_red():
    """Adding an entry must not be news anywhere else.

    Leg 2 is the by-design red. If registering `_ANAPHORIC` had broken the
    census (leg 4) or the ledger (leg 5), that would land as exit 2 — a real
    failure hiding under a permanent one, which is the I4 hole this gate was
    rebuilt to close.
    """
    for leg in (tg.leg_1_markers_are_registered, tg.leg_3_audited_five,
                tg.leg_4_census_intact, tg.leg_5_ledger_agrees,
                tg.leg_6_closed_tape_stays_closed):
        leg(ROOT)      # raises LegFailed if this registration broke it


def test_the_registration_did_not_join_the_audited_census():
    """`_ANAPHORIC` is NOT one of the 2026-08-24 audit's five.

    That census is a dated measurement and it never changes. A new entry
    carries `audit_item=None` and is tracked by legs 1, 2 and 5 instead — which
    is why registration is visible here at all.
    """
    entry = [t for t in tg.KNOWN_TAPE if t.find == NEEDLE][0]
    assert entry.audit_item is None
    assert len(tg.AUDIT_UNDECLARED) == tg.AUDIT_UNDECLARED_COUNT == 5
