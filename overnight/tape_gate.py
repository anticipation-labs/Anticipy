"""THE TAPE GATE. Law 2, with the polarity the right way round.

HARNESS-LAWS.md Law 2: a string-level patch ships carrying (a) a `TAPE:`
comment naming the real fix, and (b) a gate leg that stays RED until the real
fix replaces it. Tape with no expiry is a rejected diff. Tape whose leg went
green gets DELETED, not kept "just in case."

Until this file existed, Law 2 had no mechanism at all. The 2026-08-24 audit
(research/2026-08-24-law1-audit.md) measured it: five pieces of undeclared
tape, ZERO properly declared, and the only leg in the repository that
mentioned tape — overnight/tejas_gate.py leg 2 — fails when its tape is
REMOVED. So the scoreboard read 8/8 green with every piece of tape still in
the tree. A law whose enforcement passes while it is being broken is not a
law; it is a comment.

  RED here is not a bug. RED here is the law working.

This gate goes green on exactly one condition: there is no tape left. Every
other state — tape present, tape unmarked, tape marked but pointing at a leg
that tracks something else — is red, and the message says which.

--------------------------------------------------------------------------
HOW THIS AVOIDS BEING SATISFIED BY SILENCE
--------------------------------------------------------------------------
A registry of known tape is itself a way to hide tape: if the leg only checks
that each `TAPE:` marker appears in a list, anything WITHOUT the marker is
invisible — which is exactly the state the audit found, five pieces deep. And
a leg that tried to DETECT tape by pattern would be a threshold deciding what
code MEANS: it would fire on every legitimate sense and seatbelt regex, get
tuned down until it passed, and end up being the Law-1 violation it was hunting
— just relocated into the gate, where Law 1 exempts it from being noticed.

So this gate does not claim to detect tape. It makes silence expensive instead,
by requiring THREE INDEPENDENT BOOKS TO AGREE:

  1. THE TREE      — `TAPE:` markers in the shipped organs (brain/, extension/,
                     app/, backend/, chrome/, proof/, firmware/).
  2. THE REGISTRY  — KNOWN_TAPE below, which carries a real expiry PREDICATE
                     per entry, not a promise to edit a gate later.
  3. THE LEDGER    — the "Known standing tape" section of HARNESS-LAWS.md.

A marker in the tree with no registry entry is red (leg 1). A registry entry
whose tape is gone is red until the entry is retired (leg 1). A registry entry
whose tape is still present is red, forever, until the real fix lands (leg 2)
— that is the expiry the law asks for, and it is a predicate this file can
run, not a sentence somebody meant to honor. A registry entry the ledger never
heard of is red (leg 5), and vice versa.

Hiding a piece of tape therefore costs three coordinated edits in three files,
every one of them greppable and reviewable. That is not detection. It is the
next best thing a deterministic gate can honestly offer: it converts silence
into a signed confession.

And because none of that helps with tape that was NEVER marked, leg 3 pins the
audit's census by NAME. The five symbols the audit found undeclared are listed
below. Each must be either DECLARED (marker + registry + the marker naming
this gate) or GONE from the tree. Neither this gate nor a later agent can make
leg 3 pass by doing nothing, because the nothing is already written down. Leg 4
guards the census itself: shortening the list to quiet the gate trips a count
that is declared separately from the list.

What this gate does NOT cover, stated out loud so nobody mistakes green for
safe: tape that was never marked, is not one of the audited five, and nobody
registered. No deterministic gate finds that — finding it is a reading of what
code MEANS, and that belongs to a model with full context (Law 1, Law 5). The
mechanism for that is an audit, and leg 4 prints how old the last one is.

Run:  python3 overnight/tape_gate.py
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

LAWS = "HARNESS-LAWS.md"
AUDIT_DOC = os.path.join("research", "2026-08-24-law1-audit.md")

# The organs that SHIP. overnight/ and tests/ are deliberately excluded from
# the marker scan: Law 1 exempts gates and evals, and both directories discuss
# tape by nature — this file alone would produce a dozen false markers. The
# exclusion is printed in the gate's own output so it is a stated limit rather
# than a silent one.
SHIPPED_DIRS = ("brain", "extension", "app", "backend", "chrome", "proof",
                "firmware")
CODE_EXTS = (".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".swift",
             ".sh", ".m", ".mm", ".h", ".kt", ".java")
SKIP_DIRS = {".git", "node_modules", "__pycache__", "build", "dist", ".build",
             "DerivedData", "Pods", ".venv", "venv", "vendor", ".next"}

# The house marker, in every form the tree actually uses:
#   TAPE: the prose fallback below ...          (anticipy_core.py)
#   TAPE (HARNESS-LAWS.md Law 2): this drop ... (asking.py)
#   TAPE (HARNESS-LAWS.md Law 2). Expiry: ...   (anticipy_core.py)
MARKER_RE = re.compile(r"\bTAPE\b[ \t]*(?:\([^)\n]*\))?[ \t]*[:.]")

# The marker must name the leg that retires it. This gate IS that leg, so the
# declaration is checkable: the marker has to point here. audit item #21 is
# what happens when it is not — a `TAPE:` comment naming "the same leg that
# tracks _READ_ONLY_RE's removal", where that leg tests neither.
THIS_GATE = "overnight/tape_gate.py"


class LegFailed(Exception):
    """The message is what the owner reads. Say what is wrong and what to do."""


# --------------------------------------------------------------------------
# Reading the tree. Everything takes an explicit root so the mutation tests in
# tests/test_tape_gate.py can point these at a synthetic tree — a gate leg
# nobody has watched fail is not a gate leg.
# --------------------------------------------------------------------------
def read(root: str, rel: str) -> str:
    path = os.path.join(root, rel)
    if not os.path.exists(path):
        raise LegFailed(
            f"{rel} does not exist, so this leg cannot be tested — which "
            "counts as failing. If the file moved, the registry entry in "
            f"{THIS_GATE} that names it has to move with it.")
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def iter_shipped_files(root: str, dirs=SHIPPED_DIRS):
    """Every source file in the shipped organs, deepest-first stable order."""
    for d in dirs:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(n for n in dirnames
                                 if n not in SKIP_DIRS
                                 and not n.endswith(".xcarchive")
                                 and not n.endswith(".framework"))
            for fn in sorted(filenames):
                if fn.endswith(CODE_EXTS):
                    yield os.path.relpath(os.path.join(dirpath, fn), root)


def find_markers(root: str, dirs=SHIPPED_DIRS) -> list[tuple[str, int, str]]:
    """Every `TAPE:` marker in the shipped organs, as (relpath, line, text)."""
    out = []
    for rel in iter_shipped_files(root, dirs):
        try:
            with open(os.path.join(root, rel), encoding="utf-8",
                      errors="replace") as f:
                for n, line in enumerate(f, 1):
                    if MARKER_RE.search(line):
                        out.append((rel, n, line.strip()))
        except OSError:
            continue
    return out


def slice_def_span(source: str, name: str) -> tuple[int, int]:
    """Character span of a def, top-level or nested, from its `def` line to the
    next def/class at the same or shallower indent. Used to ask where a marker
    lives: `_THIRD_PERSON_RE` is defined at module level but its TAPE comment
    belongs to question_line(), the function that applies it."""
    m = re.search(rf"^([ \t]*)def {re.escape(name)}\s*\(", source, re.M)
    if not m:
        return (0, 0)
    indent = len(m.group(1))
    rest = source[m.end():]
    nxt = re.search(rf"^[ \t]{{0,{indent}}}(?:def |class |@)", rest, re.M)
    return (m.start(), m.end() + (nxt.start() if nxt else len(rest)))


def slice_def(source: str, name: str) -> str:
    lo, hi = slice_def_span(source, name)
    return source[lo:hi]


def _window_span(source: str, needle: str, before: int = 400,
                 after: int = 900) -> tuple[int, int]:
    i = source.find(needle)
    if i < 0:
        return (0, 0)
    return (max(0, i - before), min(len(source), i + after))


def _line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


# --------------------------------------------------------------------------
# THE REGISTRY. One entry per known piece of tape.
#
#   present()      — is the tape still in the tree? (registry ↔ tree)
#   expired()      — has the REAL FIX landed? This is the expiry Law 2 asks
#                    for, as a predicate this file runs. While it is False the
#                    gate is RED. That is the whole point.
#   marker_home    — the def whose text must carry the `TAPE:` comment, or
#                    None to look in a window around `find`.
#   audit_item     — the row number in research/2026-08-24-law1-audit.md, for
#                    the five the audit recorded as undeclared.
# --------------------------------------------------------------------------
class Tape:
    def __init__(self, tid, rel, find, what, real_fix, marker_home=None,
                 audit_item=None, expired=None, ledger_needle=None):
        self.id = tid
        self.rel = rel
        self.find = find
        self.what = what
        self.real_fix = real_fix
        self.marker_home = marker_home
        self.audit_item = audit_item
        self.ledger_needle = ledger_needle or tid
        self._expired = expired

    def present(self, root: str) -> bool:
        """The tape is in the tree. A missing FILE is not 'gone' — it is a
        leg that cannot be tested, and read() turns that into a failure."""
        return self.find in read(root, self.rel)

    def expired(self, root: str) -> bool:
        """The real fix has landed and the tape is gone. Default: the thing
        `find` points at is no longer in the file."""
        if self._expired is not None:
            return self._expired(root)
        return not self.present(root)

    def _home_span(self, root: str) -> tuple[str, int, int]:
        src = read(root, self.rel)
        if self.marker_home:
            lo, hi = slice_def_span(src, self.marker_home)
        else:
            lo, hi = _window_span(src, self.find)
        return src, lo, hi

    def marker_text(self, root: str) -> str:
        src, lo, hi = self._home_span(root)
        return src[lo:hi]

    def marker_line(self, root: str) -> int:
        """The line number of the FIRST `TAPE:` marker in this entry's home, or
        0 if it carries none. Exactly one marker per entry may be claimed: a
        SECOND marker inside a declared function is a second piece of tape
        riding on the first one's declaration, and leg 1 reports it."""
        src, lo, hi = self._home_span(root)
        if hi <= lo:
            return 0
        m = MARKER_RE.search(src, lo, hi)
        return _line_of(src, m.start()) if m else 0

    def where(self) -> str:
        return f"{self.marker_home or self.find}"


def _fallback_gone(rel: str, enclosing: str, needle: str):
    """Expiry for tape that is a BRANCH inside a function rather than a whole
    symbol: the function survives, the prose fallback inside it does not."""
    def check(root: str) -> bool:
        return needle not in slice_def(read(root, rel), enclosing)
    return check


CORE = "brain/anticipy_core.py"
ASKING = "brain/asking.py"

KNOWN_TAPE = [
    Tape(
        tid="_READ_ONLY_RE",
        rel=CORE,
        find="_READ_ONLY_RE = re.compile(",
        what="a verb regex is the default hold/run split for every goal that "
             "arrives with no effect-channel declaration",
        real_fix="effect-channel classification owns the split outright, so "
                 "an undeclared goal is re-asked of the model rather than "
                 "guessed at by wording. Then _READ_ONLY_RE is DELETED.",
        audit_item=22,
        ledger_needle="[tape:read_only_re]",
    ),
    Tape(
        tid="is_consequential compute fallback",
        rel=CORE,
        find="if compute_answer(g):",
        what="the calculator is consulted on an undeclared goal and, if it "
             "can answer, flips a held goal to unattended",
        real_fix="the effect-channel rewrite: triage always declares "
                 "`touches`, so nothing reaches a capability sniff. The "
                 "comment already promises this — it just named no leg.",
        marker_home="is_consequential",
        audit_item=19,
        ledger_needle="[tape:compute_fallback]",
        expired=_fallback_gone(CORE, "is_consequential", "if compute_answer(g):"),
    ),
    Tape(
        tid="shard_too_thin",
        rel=CORE,
        find="def shard_too_thin(",
        what="a word count decides that a line is too thin to act on — "
             "the brake fitted after \"At 5:15\" minted a meeting with a "
             "person nobody had mentioned (event nbeb6oze5bmyrge)",
        real_fix="segment-granularity triage: the day the judge reads closed "
                 "conversations instead of raw lines, shards stop existing as "
                 "decision units and the function is DELETED.",
        marker_home="shard_too_thin",
        audit_item=20,
        ledger_needle="[tape:shard_too_thin]",
    ),
    Tape(
        tid="_pending_class prose fallback",
        rel=CORE,
        find="def _pending_class(",
        what="rows minted before the `consequence` column existed get their "
             "consequence re-derived from goal PROSE, which is the exact "
             "question the effect channel exists to stop asking",
        real_fix="expires when no pending row can predate the column. That is "
                 "a date, not a rewrite — but it needs a leg, and the leg it "
                 "named (tejas_gate leg 4) tests neither this nor "
                 "_READ_ONLY_RE's removal.",
        marker_home="_pending_class",
        audit_item=21,
        ledger_needle="[tape:pending_class]",
        expired=_fallback_gone(CORE, "_pending_class",
                               "return is_consequential(job.get("),
    ),
    Tape(
        tid="_THIRD_PERSON_RE degraded drop",
        rel=ASKING,
        find="_THIRD_PERSON_RE = re.compile(",
        what="on the degraded path a pronoun regex deletes any model-written "
             "question containing he/she/they, so the owner is told nothing "
             "rather than told badly",
        real_fix="the composer owns person-flipping explicitly, so a "
                 "third-person item is rewritten instead of dropped. Then the "
                 "regex is DELETED.",
        marker_home="question_line",
        audit_item=50,
        ledger_needle="[tape:third_person_drop]",
    ),
]

# The 2026-08-24 audit's census, declared SEPARATELY from the list above so
# that shortening the list to quiet this gate trips leg 4 instead of passing.
# Deleting a census item is then a deliberate edit to a number, in a diff, with
# a name on it — not silence.
AUDIT_UNDECLARED = (19, 20, 21, 22, 50)
AUDIT_UNDECLARED_COUNT = 5
AUDIT_DECLARED_COUNT = 0          # what the audit found properly declared


# --------------------------------------------------------------------------
# LEG 1 — NO MARKER THE REGISTRY HAS NEVER HEARD OF, AND NO ENTRY WHOSE
#         TAPE IS ALREADY GONE.
#
# Both directions, because each direction is a different way to hide. An
# unregistered marker is tape that shipped without an expiry — a rejected diff
# by Law 2's own words. An entry whose tape is gone is a ledger that has begun
# to lie, and a lying ledger is how "tracked by leg 4" survived four months of
# leg 4 testing something else.
# --------------------------------------------------------------------------
def leg_1_markers_are_registered(root: str = ROOT, registry=None,
                                 dirs=SHIPPED_DIRS) -> str:
    registry = KNOWN_TAPE if registry is None else registry
    markers = find_markers(root, dirs)
    # Claim by LINE, never by file. Matching on the file alone was this leg's
    # own first draft and it was the bug it exists to catch: brain/
    # anticipy_core.py already holds two declared markers, so ANY new
    # undeclared marker anywhere in that 4000-line file would have been waved
    # through as "a file we know about". One entry claims exactly one line.
    claimed = set()
    for t in registry:
        line_no = t.marker_line(root)
        if line_no:
            claimed.add((t.rel, line_no))
    orphans = [f"{rel}:{line_no}  {text[:96]}"
               for rel, line_no, text in markers
               if (rel, line_no) not in claimed]
    if orphans:
        raise LegFailed(
            f"{len(orphans)} `TAPE:` marker(s) in the shipped organs that "
            f"{THIS_GATE} has never heard of:\n        "
            + "\n        ".join(orphans)
            + "\n        Law 2: tape with no expiry is a rejected diff. Either "
              "DELETE the patch, or add a Tape(...) entry to KNOWN_TAPE naming "
              "the real fix and an expired() predicate that goes true only when "
              "that fix has landed — and add it to the standing-tape ledger in "
              f"{LAWS}.")

    stale = [t.id for t in registry if not t.present(root)]
    if stale:
        raise LegFailed(
            "the registry names tape that is no longer in the tree: "
            + ", ".join(stale)
            + ".\n        Law 2: \"Tape whose gate leg went green gets DELETED, "
              "not kept 'just in case.'\" The tape is gone — now retire it. "
              f"Drop the entry from KNOWN_TAPE, drop its bullet from {LAWS}, "
              "and lower AUDIT_UNDECLARED_COUNT if it was one of the audited "
              "five. A registry that outlives its tape is the next false "
              "'tracked by leg 4'.")
    return (f"{len(markers)} marker(s) in the shipped organs, "
            f"{len(registry)} registered, none orphaned either way")


# --------------------------------------------------------------------------
# LEG 2 — THE EXPIRY LEG LAW 2 ACTUALLY ASKS FOR: RED WHILE THE TAPE LIVES.
#
# This is the polarity tejas_gate leg 2 does not have. That leg fails when its
# tape is REMOVED — a legitimate regression pin for the recorded "At 5:15"
# failure, but it is not an expiry, and the repo has been reading it as one.
# Here the condition is the other way round: while a registered piece of tape
# is still in the tree and its real fix has not landed, this is RED. It goes
# green the day the tape is deleted, and not one day sooner.
# --------------------------------------------------------------------------
def leg_2_tape_expires(root: str = ROOT, registry=None) -> str:
    registry = KNOWN_TAPE if registry is None else registry
    live = [t for t in registry if not t.expired(root)]
    if live:
        lines = []
        for t in live:
            lines.append(f"{t.id}  ({t.rel})\n"
                         f"          what it decides: {t.what}\n"
                         f"          real fix:        {t.real_fix}")
        raise LegFailed(
            f"{len(live)} piece(s) of tape are still load-bearing. This leg is "
            "RED on purpose and stays red until they are gone — that is what "
            "Law 2 means by an expiry:\n        "
            + "\n        ".join(lines)
            + "\n        Do NOT satisfy this leg by softening the predicate. "
              "expired() names the real fix; the way to green is to land the "
              "fix and delete the tape, then retire the entry (leg 1 will ask "
              "you to).")
    return "no tape is left in the tree — every expiry predicate has come true"


# --------------------------------------------------------------------------
# LEG 3 — THE AUDIT'S FIVE ARE DECLARED OR GONE.
#
# This is the leg that cannot be satisfied by silence. The 2026-08-24 audit
# read the shipped source with full context and wrote down five symbols. A
# registry can be quiet about what nobody registered; a NAMED symbol cannot.
# Each of the five must be:
#   * GONE from the tree, or
#   * declared: a `TAPE:` comment in its marker home, and that comment must
#     name THIS gate — because a comment naming a leg that tracks something
#     else is audit item #21, and it read as compliant for months.
# --------------------------------------------------------------------------
def leg_3_audited_five(root: str = ROOT, registry=None, census_ids=None) -> str:
    registry = KNOWN_TAPE if registry is None else registry
    census_ids = AUDIT_UNDECLARED if census_ids is None else census_ids
    census = [t for t in registry if t.audit_item in census_ids]
    open_items, gone = [], []
    for t in sorted(census, key=lambda x: x.audit_item):
        if not t.present(root):
            gone.append(t.id)
            continue
        home = t.marker_text(root)
        if not MARKER_RE.search(home or ""):
            open_items.append(
                f"#{t.audit_item} {t.id} ({t.rel}) — NO `TAPE:` comment at all. "
                f"Add one at {t.where()} in that file, naming the real "
                f"fix and `{THIS_GATE}` as the leg that retires it.")
        elif THIS_GATE not in (home or ""):
            open_items.append(
                f"#{t.audit_item} {t.id} ({t.rel}) — has a `TAPE:` comment, but "
                f"it does not name `{THIS_GATE}`, so nothing tracks its "
                "removal. This is audit item #21's failure exactly: a comment "
                "that names a leg testing something else reads as compliant "
                "and enforces nothing. Point the comment here.")
    if open_items:
        raise LegFailed(
            f"{len(open_items)} of the {len(census)} pieces of tape "
            "the 2026-08-24 audit found undeclared are still undeclared:\n"
            "        - " + "\n        - ".join(open_items)
            + "\n        Declaring is not fixing — leg 2 stays red either way. "
              "But undeclared tape is a rejected diff, and this leg is the "
              "only thing in the repo that knows these five by name.")
    return (f"all {len(census)} audited pieces accounted for"
            + (f"; gone from the tree: {', '.join(gone)}" if gone else ""))


# --------------------------------------------------------------------------
# LEG 4 — THE CENSUS CANNOT BE SHORTENED QUIETLY, AND THE GATE STATES ITS
#         OWN COVERAGE.
#
# The failure mode this prevents is the obvious one: an agent facing a red
# leg 3 deletes a Tape entry instead of the tape. The count is declared apart
# from the list, so that edit lands here as a number that stopped matching,
# with a name on the diff — rather than as one fewer red line nobody counted.
# --------------------------------------------------------------------------
def leg_4_census_intact(root: str = ROOT, registry=None) -> str:
    registry = KNOWN_TAPE if registry is None else registry
    have = tuple(sorted(t.audit_item for t in registry
                        if t.audit_item is not None))
    if have != tuple(sorted(AUDIT_UNDECLARED)):
        raise LegFailed(
            f"the registry covers audit items {have or '()'}, but the "
            f"2026-08-24 audit recorded {tuple(sorted(AUDIT_UNDECLARED))} as "
            "undeclared tape. An entry was dropped or renumbered. If a piece "
            "genuinely no longer exists, leg 1 retires it and AUDIT_UNDECLARED "
            "changes in the same diff — deleting the entry alone hides the "
            "item instead of closing it.")
    if len(AUDIT_UNDECLARED) != AUDIT_UNDECLARED_COUNT:
        raise LegFailed(
            f"AUDIT_UNDECLARED lists {len(AUDIT_UNDECLARED)} items but "
            f"AUDIT_UNDECLARED_COUNT says {AUDIT_UNDECLARED_COUNT}. The count "
            "is declared separately on purpose: it is the tripwire on "
            "shortening the census.")
    doc = os.path.join(root, AUDIT_DOC)
    doc_note = "audit doc missing from the tree — census held from this file"
    if os.path.exists(doc):
        with open(doc, encoding="utf-8", errors="replace") as f:
            text = f.read()
        m = re.search(r"\*\*TAPE, UNDECLARED\*\*.*?\|\s*\*\*(\d+)\*\*\s*\|",
                      text, re.S)
        if m and int(m.group(1)) != AUDIT_UNDECLARED_COUNT:
            raise LegFailed(
                f"{AUDIT_DOC} now reports {m.group(1)} undeclared pieces of "
                f"tape; this gate is pinned to {AUDIT_UNDECLARED_COUNT}. One of "
                "the two was edited. The audit is the dated record — if it grew, "
                "register the new items here; if it shrank, say which piece was "
                "closed and how.")
        doc_note = f"{AUDIT_DOC} agrees: {AUDIT_UNDECLARED_COUNT} undeclared"
    return (f"census intact ({AUDIT_UNDECLARED_COUNT} audited items, "
            f"{len(registry)} registered); {doc_note}")


# --------------------------------------------------------------------------
# LEG 5 — THE LAW'S OWN LEDGER AND THIS REGISTRY SAY THE SAME THING.
#
# The third book. HARNESS-LAWS.md carries a "Known standing tape" section that
# a human reads; this file carries the version a machine runs. When they drift,
# the human one is what the next agent believes, and it was already wrong once:
# the ledger said _READ_ONLY_RE was "tracked by tejas_gate.py leg 4" while
# leg 4 was green and the regex was still deciding.
# --------------------------------------------------------------------------
def leg_5_ledger_agrees(root: str = ROOT, registry=None) -> str:
    registry = KNOWN_TAPE if registry is None else registry
    laws = read(root, LAWS)
    m = re.search(r"^##\s*Known standing tape.*?(?=^## |\Z)", laws,
                  re.S | re.M)
    if not m:
        raise LegFailed(
            f"{LAWS} has no \"Known standing tape\" section any more. That "
            "section is the human-readable half of Law 2's registry; without "
            "it the only ledger is this file, and a ledger with one copy is a "
            "ledger nobody cross-checks.")
    section = m.group(0)
    missing = [t.id for t in registry if t.ledger_needle not in section]
    if missing:
        raise LegFailed(
            "registered tape that the standing-tape ledger in "
            f"{LAWS} never mentions: " + ", ".join(missing)
            + ".\n        Both books have to name it, or the next agent reads "
              "the law file, sees four bullets, and believes that is all of it.")
    if THIS_GATE not in section:
        raise LegFailed(
            f"the standing-tape ledger in {LAWS} does not name `{THIS_GATE}` as "
            "the leg that tracks these. A ledger entry with no leg is the "
            "state Law 2 was written to end.")
    return f"{len(registry)} entries, and {LAWS}'s ledger names every one"


LEGS = [
    (1, "EVERY MARKER IS REGISTERED", leg_1_markers_are_registered),
    (2, "TAPE IS RED WHILE IT LIVES", leg_2_tape_expires),
    (3, "THE AUDITED FIVE ARE DECLARED OR GONE", leg_3_audited_five),
    (4, "THE CENSUS CANNOT SHRINK QUIETLY", leg_4_census_intact),
    (5, "THE LAW'S LEDGER AGREES", leg_5_ledger_agrees),
]


def main() -> int:
    print()
    print(f"  TAPE GATE    tree: {ROOT}")
    print(f"               law:  {LAWS} Law 2 — tape ships only with an expiry")
    print(f"               scan: {', '.join(SHIPPED_DIRS)}  "
          "(overnight/ and tests/ excluded: Law 1 exempts gates)")
    print("  " + "-" * 62)
    first = None
    for num, name, fn in LEGS:
        try:
            detail = fn()
            print(f"  [{num}] PASS  {name}")
            print(f"        {detail}")
        except LegFailed as e:
            mark = "FAIL" if first is None else "fail"
            print(f"  [{num}] {mark}  {name}")
            print(f"        {e}")
            if first is None:
                first = (num, name, str(e))
        except Exception as e:  # noqa: BLE001
            print(f"  [{num}] FAIL  {name}")
            print(f"        gate itself errored: {e}")
            if first is None:
                first = (num, name, f"gate errored: {e}")
    print("  " + "-" * 62)
    if first is None:
        print("  CLEAN — no tape is left in the shipped organs")
        print()
        return 0
    num, name, _ = first
    print(f"  TAPE OUTSTANDING — first failing leg: {num} ({name})")
    print("  Red here is the law working. Green means the tape is GONE, not")
    print("  that it was written down. Do not soften a predicate to get there.")
    print("  What this gate cannot see: tape nobody marked, nobody registered,")
    print("  and that is not one of the audited five. Only an audit finds that")
    print(f"  — the last one is {AUDIT_DOC}.")
    print()
    return 1


if __name__ == "__main__":
    sys.exit(main())
