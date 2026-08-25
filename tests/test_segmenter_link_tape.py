"""`_ANAPHORIC` AND `decide_link`'s BAND-3 PREFILTER — the stakes, and the expiry.

`brain/segmenter.py:82-84` holds an opener word list, and `decide_link`
(:151-198) combines it with a ">=2 content-word overlap" count and a "<8 words"
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

   BOTH PINS ARE ON THEIR SECOND DRAFT, because a reviewer beat the first of
   each, and how they were beaten is the reason they are shaped as they are:
     - the blast-radius test measured ONE branch of `place_turn` — the only
       branch that already called `decide_link`. Making the OPEN branch
       consult the word list too left every book green while the verdict
       decided segment membership. It is now a matrix over every verdict and
       every branch, and it proves the branch list COMPLETE from the compiled
       function rather than from whoever wrote it.
     - the reader scan allowlisted `brain/sorter.py` and asked only that the
       matched line "be prose", by `startswith("#") or a quote appears in it`
       — and every real read of a column contains a quote, so the predicate
       could not reject one. A reader inserted into sorter.py, the exact file
       the next spec puts one in, passed. It now PARSES the shipped organs:
       comments do not survive `ast.parse`, so prose cannot be confused with
       code, and it walks the filesystem so an untracked module cannot hide
       for the length of a work session.

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

import ast
import importlib.util
import os
import subprocess
import sys

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

    def __init__(self, open_seg=None, closed_seg=None, create_ok=True):
        self._open = open_seg
        self._closed = closed_seg
        self._create_ok = create_ok
        self.created = []          # [(started, parent)]
        self.appended = []         # [(segment_id, text, ended)]
        self.stamped = []          # [(event_id, segment_id)]
        self.closed_calls = []     # [(segment_id, ended)]
        self._n = 0

    def open_segment(self):
        return self._open

    def last_closed(self):
        return self._closed

    def close(self, segment, ended):
        # `ended` is recorded, not dropped: the real store writes it to
        # `last_speech_at`/`ended_at`, and `should_close` reads that on the
        # NEXT turn. A verdict that moved it would be deciding membership one
        # turn later, which a record that only kept the id could not see.
        self.closed_calls.append((segment["id"], ended))

    def create(self, started, parent=None):
        self._n += 1
        self.created.append((started, parent))
        if not self._create_ok:
            return None       # PocketBase said no — place_turn's `failed` path
        return {"id": f"fresh{self._n}", "entities": "[]", "turn_count": 0,
                "word_count": 0}

    def append(self, segment, event, ended):
        self.appended.append((segment["id"], event.get("text") or "", ended))

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


def _open_live(off=600):
    """An open segment whose last speech is recent: `should_close` keeps it.

    This is the branch production spends almost all its time in, and it is the
    branch the previous version of this file never entered.
    """
    from brain.segmenter import iso, parse_ts
    return {"id": "open1", "summary": "the roof needs doing before winter",
            "entities": "[]",
            "started_at": iso(parse_ts(BASE + off - 100)),
            "last_speech_at": iso(parse_ts(BASE + off - 10))}


def _open_quiet(off=0):
    """An open segment that has gone quiet: `place_turn` closes it first and
    then treats it as the conversation to link back to."""
    from brain.segmenter import iso, parse_ts
    return {"id": "open1", "summary": "the roof needs doing before winter",
            "entities": "[]",
            "started_at": iso(parse_ts(BASE + off - 100)),
            "last_speech_at": iso(parse_ts(BASE + off))}


def _no_capture_time():
    return {"id": "ev1", "text": "anyway, where were we"}


# Every shape the live path can be in when a turn arrives, with the segment a
# `link`/`escalate` verdict would thread onto and whether the branch opens a
# row at all. Written out rather than hidden in the loop because the coverage
# assertion below is what proves this list COMPLETE, and a reader has to be
# able to hold both halves at once.
def _live_branches():
    return {
        "no open segment, a closed one behind it": (
            lambda: FakeStore(open_seg=None, closed_seg=_prev_closed()),
            _event, "prev1", True),
        "no open segment and nothing behind it": (
            lambda: FakeStore(open_seg=None, closed_seg=None),
            _event, None, True),
        "an open segment, still live": (
            lambda: FakeStore(open_seg=_open_live(), closed_seg=None),
            _event, None, False),
        "an open segment that has gone quiet": (
            lambda: FakeStore(open_seg=_open_quiet(), closed_seg=None),
            _event, "open1", True),
        "the store refuses to open a segment": (
            lambda: FakeStore(open_seg=None, closed_seg=_prev_closed(),
                              create_ok=False),
            _event, "prev1", True),
        "a turn with no usable capture time": (
            lambda: FakeStore(open_seg=None, closed_seg=_prev_closed()),
            _no_capture_time, None, False),
    }


def _place_turn_lines():
    """Every executable line of `place_turn`, read off the compiled function.

    Not a hand-kept list of branches — that is the thing that goes stale, and
    going stale is exactly how the previous version of this measurement came
    to cover one path out of five. `co_lines()` also reports the signature
    line, for which no `line` event ever fires, so the first statement of the
    body is the floor.
    """
    source = open(os.path.join(ROOT, "brain", "segmenter.py"),
                  encoding="utf-8").read()
    fn = next(n for n in ast.walk(ast.parse(source))
              if isinstance(n, ast.FunctionDef) and n.name == "place_turn")
    floor = fn.body[0].lineno
    return {ln for _, _, ln in place_turn.__code__.co_lines()
            if ln and ln >= floor}


def test_the_live_verdict_only_moves_parent_segment():
    """THE MEASUREMENT THE REGISTRATION RESTS ON — on EVERY branch, not one.

    Three books say the same sentence: in the live path `decide_link`'s
    verdict reaches exactly one field, `parent_segment`, and cannot change
    which segment a turn is stamped into (HARNESS-LAWS.md's standing-tape
    ledger, brain/segmenter.py's own comment, and the `real_fix` on the
    registry entry in overnight/tape_gate.py). That sentence is the entire
    case for REGISTERING `_ANAPHORIC` instead of replacing it with a model
    call, so it had better be measured rather than repeated.

    The first draft of this test measured ONE branch — no open segment — which
    is the one branch that already called `decide_link`. A reviewer made the
    OPEN branch consult the word list too (compute the gap, ask `decide_link`,
    close and re-create on a `new` verdict) and every book stayed green while
    the word list decided segment membership, `events.segment`,
    `recent_turns`, `convo_context` and therefore what `hear()` reads.

    So this is a matrix, and it carries its own completeness proof:

      1. COVERAGE — the branches below entered every executable line of
         `place_turn`. A path this matrix never walks is a path where the
         verdict could be doing anything, and a new branch that consults
         `decide_link` lands here rather than slipping past.
      2. INDEPENDENCE — inside each branch, all four verdicts wrote the
         IDENTICAL thing to the store: same rows opened, same appends, same
         stamps, same closes, same segment returned.
      3. THE ONE THING IT MOVES — `create(parent=…)`, and nothing else.

    WHAT THE COVERAGE HALF CANNOT SEE, said plainly rather than left to be
    found: it is LINE coverage, not branch coverage. A new decision hidden
    inside a line this matrix already walks — a widened `in (...)` test, a
    ternary — does not register as a missing line. That case is caught by (2)
    and (3) instead, which compare what was WRITTEN rather than what ran:
    widening the parent test to fire on `append` was tried and (3) killed it.
    The two halves cover each other; neither is sufficient alone.

    If this test fails, the verdict has become load-bearing and the tape's
    severity has to be re-argued from scratch: a per-turn model call stops
    being the wrong trade the moment the answer reaches `hear()`.
    """
    branches = _live_branches()
    covered: set[int] = set()
    code = place_turn.__code__

    def _tracer(frame, event, arg):
        if frame.f_code is not code:
            return None
        if event == "line":
            covered.add(frame.f_lineno)
        return _tracer

    records = {}
    previous = sys.gettrace()
    sys.settrace(_tracer)
    try:
        for branch, (make_store, make_event, _parent, _opens) in branches.items():
            for verdict in VERDICTS:
                store = make_store()
                original = segmenter.decide_link
                segmenter.decide_link = (
                    lambda *a, _v=verdict, **k: (_v, "forced by the test"))
                try:
                    out = place_turn(store, make_event(), now=None)
                finally:
                    segmenter.decide_link = original
                records[(branch, verdict)] = {
                    # Everything a downstream reader can ever see...
                    "opened": [c[0] for c in store.created],
                    "appended": list(store.appended),
                    "stamped": list(store.stamped),
                    "closed": list(store.closed_calls),
                    "segment": out.get("segment"),
                    # ...and, kept deliberately apart so the comparison below
                    # cannot swallow it, the one field the verdict may move.
                    "parents": [c[1] for c in store.created],
                }
    finally:
        sys.settrace(previous)

    # 1. COVERAGE.
    missing = sorted(_place_turn_lines() - covered)
    assert not missing, (
        "`place_turn` has code this matrix never runs, at brain/segmenter.py "
        f"line(s) {missing}. Until every path is entered, 'the verdict only "
        "moves parent_segment' is a claim about the paths somebody happened "
        "to think of — which is how a word list came to decide segment "
        "membership on the open-segment branch with all three books green. "
        "Add a case to `_live_branches()` that reaches those lines.")

    # 2. INDEPENDENCE.
    for branch in branches:
        base = dict(records[(branch, "append")])
        base.pop("parents")
        for verdict in VERDICTS:
            got = dict(records[(branch, verdict)])
            got.pop("parents")
            assert got == base, (
                f"on the branch {branch!r} the verdict {verdict!r} wrote "
                f"something different from 'append':\n  {verdict}: {got}\n"
                f"  append: {base}\n"
                "`_ANAPHORIC`'s verdict now decides where a live turn is "
                "stamped, so it decides what `recent_turns` returns, so it "
                "decides what `hear()` reads. The registration in "
                "overnight/tape_gate.py rests on it NOT doing that; the model "
                "call is owed and HARNESS-LAWS.md's bullet is now false.")

    # 3. THE ONE THING IT MOVES.
    for branch, (_s, _e, link_parent, opens) in branches.items():
        for verdict in VERDICTS:
            want = ([link_parent if verdict in ("link", "escalate") else None]
                    if opens else [])
            assert records[(branch, verdict)]["parents"] == want, (
                f"{branch!r} / {verdict!r}: parent column is "
                f"{records[(branch, verdict)]['parents']}, expected {want}")

    # And, spelled out rather than left implicit, the two facts the
    # independence check above would still hold under if they broke together.
    assert records[("no open segment, a closed one behind it",
                    "link")]["stamped"] == [("ev1", "fresh1")], (
        "a fresh segment was NOT opened — the turn joined an existing row. "
        "Membership is now the verdict's business.")
    for verdict in VERDICTS:
        live = records[("an open segment, still live", verdict)]
        assert live["stamped"] == [("ev1", "open1")], (
            f"verdict {verdict!r} moved a turn out of the OPEN segment it "
            f"belonged to: {live['stamped']}. Only `should_close` — a clock, "
            "which is a sense and lawful — may end a conversation.")
        assert live["closed"] == [] and live["opened"] == [], verdict


COLUMN = "parent_segment"
# The runtime, as the Law-2 gate itself defines it — imported rather than
# retyped. A hardcoded copy is a list that silently stops matching the tree
# the day somebody adds a shipped directory, and then a reader in the new
# directory is invisible to this test while `overnight/tape_gate.py` sees it.
SCAN_DIRS = tg.SHIPPED_DIRS
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "build",
             "dist", "DerivedData", ".build", "Pods", ".pytest_cache"}
# The only file allowed to name the column outside python: the migration that
# DEFINES it. A schema is not a reader.
SCHEMA_ONLY = ("backend/pb_migrations/",)


def _python_files(root):
    """Every .py file under the shipped organs, tracked or not.

    Walked rather than `git grep`-ed. `git grep` sees tracked files only, so a
    module a reader was just written into is invisible for exactly as long as
    it takes to run the suite and call it green — which is the whole window in
    which an agent decides they are done.
    """
    for top in SCAN_DIRS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(root, top)):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in sorted(filenames):
                if name.endswith(".py"):
                    full = os.path.join(dirpath, name)
                    yield os.path.relpath(full, root), full


def _column_sites_in_code(path):
    """Every mention of `parent_segment` in EXECUTABLE python, with its shape.

    PARSED, NOT GREPPED, and that is the entire point. `ast.parse` discards
    every `#` comment before this function can see it, so a comment can never
    be mistaken for code. The version of this check that shipped first decided
    "this line is prose" with `line.startswith("#") or a quote appears in it`
    — and every real read of a column contains a quote, so the predicate could
    not reject one. A reader inserted into brain/sorter.py passed it, and the
    file that names brain/sorter.py as the next place a reader will land
    (docs/superpowers/specs/2026-08-25-sorter-conversation-granularity.md) was
    already in the tree.

    Docstrings are prose too, excluded by SHAPE — a bare string statement —
    not by looking at what they say.

    Returns sorted [(lineno, kind)]. `kind` is "dict-key" (the column being
    WRITTEN into a payload) or "other", which covers every way of reading it
    and everything ambiguous. Ambiguity counts against, on purpose.

    WHAT THIS CANNOT SEE, said out loud instead of left to be discovered: a
    column name assembled at runtime — `"parent_" + "segment"`, a name pulled
    from config, `getattr(row, name)`. No scanner catches that. Only the flat
    ban on new readers does.
    """
    with open(path, encoding="utf-8", errors="replace") as fh:
        source = fh.read()
    if COLUMN not in source:
        return []
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        # A file that mentions the column and will not parse is a file this
        # check cannot vouch for. That is a failure, not a pass.
        return [(getattr(exc, "lineno", 0) or 0, "unparseable")]
    prose, keys = set(), set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            prose.add(id(node.value))
        elif isinstance(node, ast.Dict):
            keys.update(id(k) for k in node.keys if k is not None)
    sites = set()
    for node in ast.walk(tree):
        named = None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            named = node.value
        elif isinstance(node, ast.Attribute):
            named = node.attr
        elif isinstance(node, ast.Name):
            named = node.id
        elif isinstance(node, ast.arg):
            named = node.arg
        elif isinstance(node, ast.keyword):
            named = node.arg or ""
        if named is None or COLUMN not in named or id(node) in prose:
            continue
        sites.add((node.lineno, "dict-key" if id(node) in keys else "other"))
    return sorted(sites)


def test_nothing_in_the_repo_reads_parent_segment():
    """The other half of the same measurement: `parent_segment` is WRITTEN by
    `SegmentStore.create` and read by NOBODY.

    `decide_link`'s verdict lands in that one column. If anything reads it, the
    verdict reaches a reader, and this file's argument for REGISTERING
    `_ANAPHORIC` rather than replacing it with a model call is void.

    Three rules, and the first two are structural rather than textual because
    the textual version was beaten:

      1. Outside brain/segmenter.py, ZERO mentions of the column in running
         python anywhere in the shipped organs. Not "outside an allowlist of
         files" — the allowlist was the hole. brain/sorter.py was on it with a
         "must be prose" predicate that no real read could fail.
      2. Inside the writer, the column may only appear as a DICT KEY — the
         payload it is written with. Every way of reading it (`row[...]`,
         `.get(...)`, `.parent_segment`, `... in row`) is something else, so
         a reader added to the writer's own file is caught by shape and not by
         remembering to update a line number.
      3. Nothing outside python may name it either, except the migration that
         defines the column.

    Rule 1 scans the FILESYSTEM, not the index: an untracked module is exactly
    as able to read the column as a committed one, and it is untracked for the
    whole window in which somebody runs the suite and believes it.
    """
    writer = os.path.join("brain", "segmenter.py")
    scanned, strays = set(), []
    for rel, full in _python_files(ROOT):
        scanned.add(rel)
        if rel == writer:
            continue
        for lineno, kind in _column_sites_in_code(full):
            strays.append(f"{rel}:{lineno}  ({kind})")
    assert not strays, (
        "`parent_segment` is now touched by RUNNING python outside "
        "brain/segmenter.py:\n  " + "\n  ".join(strays) + "\n"
        "This is an AST walk, so comments and docstrings never reach it — "
        "what it found is code. `decide_link`'s verdict lands in that column; "
        "a reader means the verdict reaches `hear()`, the trade recorded in "
        "overnight/tape_gate.py's `real_fix` is void, and the model call is "
        "owed. Fix the tape, do not widen this test.")

    sites = _column_sites_in_code(os.path.join(ROOT, writer))
    reads = [f"brain/segmenter.py:{ln}  ({kind})"
             for ln, kind in sites if kind != "dict-key"]
    assert not reads, (
        "the writer now does something with `parent_segment` other than "
        "writing it into a payload:\n  " + "\n  ".join(reads) + "\n"
        "Reading the column back inside the writer is still reading it.")
    assert len(sites) == 1, (
        f"brain/segmenter.py writes `parent_segment` at {len(sites)} places, "
        f"expected exactly 1: {sites}. If you added a second WRITE, re-pin "
        "this number. If what you added READS the column, the registration "
        "of `_ANAPHORIC` as tape is void and the model call is owed instead.")

    out = subprocess.run(
        ["git", "grep", "--untracked", "-n", COLUMN, "--", *SCAN_DIRS],
        cwd=ROOT, capture_output=True, text=True).stdout
    hits = [ln for ln in out.splitlines() if ln.strip()]
    others = [h for h in hits
              if not h.split(":", 1)[0].endswith(".py")
              and not h.startswith(SCHEMA_ONLY)]
    assert not others, (
        "something outside python now names `parent_segment`:\n  "
        + "\n  ".join(others) + "\n"
        "Only the migration that defines the column may. A Swift or "
        "JavaScript reader reaches the verdict the same way a python one "
        "does.")

    # And the walk really did open every python file git can see naming it —
    # a directory this scan skips is a directory a reader can hide in.
    for hit in hits:
        rel = hit.split(":", 1)[0]
        if rel.endswith(".py"):
            assert rel in scanned, (
                f"{rel} names `parent_segment` and the walk above never "
                f"opened it. SKIP_DIRS or SCAN_DIRS is wrong.")


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


def test_the_marker_sits_hard_against_the_taped_text():
    """The declaration must not be able to DRIFT out of the gate's window.

    `Tape._home_span` looks back exactly 400 characters from the taped text.
    When this file was first reviewed the marker sat 310 of those 400 back —
    the four-line block was itself most of the window — so ONE more sentence
    in the prose above it would have pushed `marker_line()` to 0, turned the
    declaration into an ORPHAN and exited the gate 2. Loud rather than silent,
    which is why it was only a low finding; but the margin was one line wide
    and nothing in either file said so.

    So the marker is pinned ADJACENT to the regex and this is what holds it
    there: inside 200 characters — half the window — with nothing but comment
    lines in between. An agent extending the WHY block above now cannot reach
    it, because everything they can add lands ABOVE the marker, not between
    the marker and the tape.

    Measured against the marker the GATE would pick (`marker_line`), not
    against whichever `TAPE` a fresh scan happens to find first.
    """
    src = open(os.path.join(ROOT, "brain", "segmenter.py"),
               encoding="utf-8").read()
    needle_at = src.find(NEEDLE)
    assert needle_at >= 0, "the taped text is gone — close the registry entry"

    entry = [t for t in tg.KNOWN_TAPE if t.find == NEEDLE][0]
    line = entry.marker_line(ROOT)
    assert line, "no `TAPE:` marker the gate can see (see the test above)"

    marker_at = 0
    for _ in range(line - 1):
        marker_at = src.index("\n", marker_at) + 1
    distance = needle_at - marker_at
    assert 0 < distance <= 200, (
        f"the `TAPE:` marker starts {distance} characters above `{NEEDLE}` "
        "and overnight/tape_gate.py's window only reaches back 400. Move the "
        "marker back down against the regex and put new prose ABOVE it. Do "
        "NOT widen the gate's window to make this pass: a declaration that "
        "has to be hunted for is audit item #21's shape, and the window is "
        "the only thing that makes `marker_line()` mean 'declared HERE'.")

    between = src[marker_at:needle_at].splitlines()[1:]
    assert all(ln.strip().startswith("#") for ln in between), (
        "something that is not a comment now sits between the `TAPE:` marker "
        f"and `{NEEDLE}`:\n  " + "\n  ".join(
            ln for ln in between if not ln.strip().startswith("#")) + "\n"
        "The marker declares whatever it is nearest. Anything wedged in here "
        "is undeclared tape wearing this entry's declaration.")


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
