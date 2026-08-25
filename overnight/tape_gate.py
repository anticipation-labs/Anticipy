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
HOW TO READ THE VERDICT — because this gate is red on purpose
--------------------------------------------------------------------------
Leg 2 is red permanently, by design, and it runs early. That is a problem for
every OTHER leg: on 2026-08-24 a review shrank the census, leg 4 fired, and it
printed as one lowercase line buried under leg 2's twenty-line block with the
footer still naming leg 2 and the exit code unchanged. Nothing distinguished
"the expected steady state" from "somebody shrank the census." The census
tripwire was firing into the noise the gate makes on purpose.

So every leg declares whether its red is EXPECTED, and the verdict is three
states, not two:

  exit 0  CLEAN            — no tape left anywhere. Celebrate, then delete
                             this gate's registry (leg 1 will ask you to).
  exit 1  TAPE OUTSTANDING — leg 2 is red and NOTHING ELSE IS. This is the
                             steady state. Law 2 is working.
  exit 2  THE BOOKS DISAGREE — a leg that is not red by design went red. The
                             footer reprints its whole message, above the
                             prose, because that is the news.

An unexpected red prints `FAIL`; the by-design red prints `RED `. Never widen
the by-design set to quiet a leg: the set is the definition of "normal", and
adding to it is how a gate stops being able to surprise anyone.

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
                     app/, backend/, proof/, firmware/).
  2. THE REGISTRY  — KNOWN_TAPE below, which carries a real expiry PREDICATE
                     per entry, not a promise to edit a gate later.
  3. THE LEDGER    — the "Known standing tape" section of HARNESS-LAWS.md.

A marker in the tree with no registry entry is red (leg 1). A registry entry
whose tape is gone is red until the entry is retired (leg 1). A registry entry
whose tape MOVED is red, loudly (leg 1 — see below). A registry entry whose
tape is still present is red, forever, until the real fix lands (leg 2) — that
is the expiry the law asks for, and it is a predicate this file can run, not a
sentence somebody meant to honor. A registry entry the ledger never heard of is
red (leg 5), and a ledger bullet this registry never heard of is red too.

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
that is declared separately from the list, and trips the audit doc besides.

--------------------------------------------------------------------------
ONE SCOPE, THREE STATES — the 2026-08-24 refactor hole
--------------------------------------------------------------------------
This gate shipped with the disease it was built to catch. `present()` searched
the whole FILE and `expired()` searched only the enclosing DEF. So an ordinary
extract-method refactor — move a taped branch into a helper, leave the `TAPE:`
comment at the old site — made the tape "expired" while it was still in the
tree and still running. It retired live tape from leg 2 AND leg 3 at once. All
three books agreed and all three were wrong, and NOBODY SOFTENED A PREDICATE:
the predicate's scope was wrong. That is subtler than the failure this gate was
built for, and it is why every entry now resolves through ONE function,
`Tape.state()`, into one of three states:

  LIVE   the tape is where the registry says it is.        leg 2 RED.
  MOVED  it is not there, but it IS somewhere else in the shipped organs.
         RED, in leg 1, naming both places. A move is not a fix, and the
         gate refuses to guess which one it was — re-point the entry or
         retire it, in a diff, with a name on it.
  GONE   the text is nowhere in the shipped organs at all.  leg 2 green
         for that entry, and leg 1 asks you to retire it.

There is no per-entry `expired=` override any more. That parameter is exactly
how the two scopes came to disagree; an entry that needs a different expiry
needs a different `find`, or a new state here with a test behind it.

--------------------------------------------------------------------------
WHAT THIS GATE CANNOT SEE — stated out loud, so green is never read as safe
--------------------------------------------------------------------------
Tape that was never marked, is not one of the audited five, and nobody
registered. No deterministic gate finds that — finding it is a reading of what
code MEANS, and that belongs to a model with full context (Law 1, Law 5). The
mechanism for that is an audit, and leg 4 pins the last one.

Tape in a file type leg 1 does not read. That hole was real: CODE_EXTS held
`.h` and not `.c`, so 142 of firmware/'s 235 files were invisible and a
`/* TAPE: */` in the pendant firmware read as PASS under the leg that enforces
Law 2. It is closed structurally now rather than by adding one extension: every
file in a shipped organ must be classified as code (read) or as data
(declared), and anything UNCLASSIFIED turns leg 1 red until a human files it.
A shipped organ that yields zero readable files is red for the same reason —
the header must never print a scan scope the leg does not have.

Tape in `overnight/` and `tests/`. Deliberately excluded: Law 1 exempts gates
and evals, and both directories discuss tape by nature — this file alone would
produce a dozen false markers. The exclusion is printed in the gate's output.

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

# The organs that SHIP. `chrome/` used to be listed here and held exactly one
# file — a `.metadata` alias map from a chrome-for-testing download. It is a
# browser download cache, not an organ; the browser arm's code is extension/.
# A directory in this tuple that leg 1 can read nothing out of is now RED, and
# that is what removed it: the header printed a scope the leg did not have.
SHIPPED_DIRS = ("brain", "extension", "app", "backend", "proof", "firmware")

# Files leg 1 READS for markers. Anything a `TAPE:` comment could live in and
# still ship. `.c` and `.s` are here because firmware/ is 142 C files and 3
# assembly files and they were invisible until 2026-08-24.
CODE_EXTS = (".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".swift",
             ".sh", ".bash", ".zsh", ".m", ".mm", ".h", ".hpp", ".hh", ".c",
             ".cc", ".cpp", ".cxx", ".s", ".kt", ".java", ".rb", ".go", ".rs",
             ".html", ".htm", ".css", ".scss")
CODE_NAMES = frozenset({"Dockerfile", "Makefile", "makefile", "Kconfig",
                        "CMakeLists.txt", "Procfile"})

# Files leg 1 does NOT read, declared rather than assumed. Every extension in a
# shipped organ has to be in one list or the other; a third case is red. Data,
# logs, fixtures, images, archives, signing material, editor and build metadata
# — none of them can carry a running string-level patch.
NOT_CODE_EXTS = (
    ".log", ".jsonl", ".ids", ".json", ".md", ".rst", ".txt", ".csv", ".tsv",
    ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".env", ".lock",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf", ".wav", ".mp3",
    ".mp4", ".mov", ".ttf", ".otf", ".woff", ".woff2", ".onnx", ".bin",
    ".hex", ".uf2", ".elf", ".map", ".a", ".o", ".d", ".zip", ".gz", ".tar",
    ".bak", ".orig", ".rej", ".patch", ".diff", ".overlay", ".dtsi", ".dts",
    ".plist", ".pbxproj", ".xcworkspacedata", ".xcscheme", ".xcprivacy",
    ".xcconfig", ".strings", ".storyboard", ".xib", ".entitlements",
    ".mobileprovision", ".cer", ".p12", ".pem", ".crt", ".resolved",
    ".xcuserstate", ".pyc", ".pyo", ".so", ".dylib", ".dll", ".class",
)
SKIP_DIRS = {".git", "node_modules", "__pycache__", "build", "dist", ".build",
             "DerivedData", "Pods", ".venv", "venv", "vendor", ".next"}

# The house marker, in every form the tree actually uses:
#   TAPE: the prose fallback below ...          (anticipy_core.py)
#   TAPE (HARNESS-LAWS.md Law 2): this drop ... (asking.py)
#   TAPE (HARNESS-LAWS.md Law 2). Expiry: ...   (anticipy_core.py)
#   # TAPE                                      (the rest on the next line)
#
# That last form is why `$` is here. A marker split across two comment lines
# was invisible to this regex while a human grepping `TAPE` found it and read
# it as declared — which is audit item #21's shape (a declaration that reads
# compliant and enforces nothing) recreated inside the enforcement. `\bTAPE\b`
# is case-sensitive, so "duct tape and prayer" still does not fire.
MARKER_RE = re.compile(r"\bTAPE\b[ \t]*(?:\([^)\n]*\))?[ \t]*(?:[:.]|$)", re.M)

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


def is_code(filename: str) -> bool:
    """Would leg 1 read this file for `TAPE:` markers?"""
    return (filename in CODE_NAMES
            or filename.lower().endswith(CODE_EXTS))


def is_declared_data(filename: str) -> bool:
    """Has somebody written down that this file cannot carry tape? Dotfiles
    are metadata by convention (.DS_Store, .gitkeep, .metadata) and are the
    one class taken on the convention rather than by extension."""
    return (filename.startswith(".")
            or filename.lower().endswith(NOT_CODE_EXTS))


def _walk(root: str, d: str):
    base = os.path.join(root, d)
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(n for n in dirnames
                             if n not in SKIP_DIRS
                             and not n.endswith(".xcarchive")
                             and not n.endswith(".framework"))
        for fn in sorted(filenames):
            yield os.path.relpath(os.path.join(dirpath, fn), root), fn


def iter_shipped_files(root: str, dirs=SHIPPED_DIRS):
    """Every source file in the shipped organs, deepest-first stable order."""
    for d in dirs:
        if not os.path.isdir(os.path.join(root, d)):
            continue
        for rel, fn in _walk(root, d):
            if is_code(fn):
                yield rel


def scan_reach(root: str, dirs=SHIPPED_DIRS) -> dict:
    """How much of each shipped organ leg 1 can actually read, and what it
    cannot classify. This is the leg's own honesty check: a scan scope printed
    in the header that the code does not have is the I3 failure, where
    undeclared tape in the pendant firmware was a rejected diff under Law 2 and
    a PASS under the leg that enforces it."""
    per_dir: dict[str, tuple[int, int]] = {}
    unknown: list[str] = []
    missing: list[str] = []
    for d in dirs:
        if not os.path.isdir(os.path.join(root, d)):
            missing.append(d)
            continue
        n_read = n_total = 0
        for rel, fn in _walk(root, d):
            n_total += 1
            if is_code(fn):
                n_read += 1
            elif not is_declared_data(fn):
                unknown.append(rel)
        per_dir[d] = (n_read, n_total)
    hollow = [d for d, (r, t) in per_dir.items() if t and not r]
    return {"per_dir": per_dir, "unknown": unknown, "missing": missing,
            "hollow": hollow,
            "read": sum(r for r, _ in per_dir.values()),
            "total": sum(t for _, t in per_dir.values())}


def find_markers(root: str, dirs=SHIPPED_DIRS) -> list[tuple[str, int, str]]:
    """Every `TAPE:` marker in the shipped organs, as (relpath, line, text)."""
    out = []
    for rel in iter_shipped_files(root, dirs):
        try:
            with open(os.path.join(root, rel), encoding="utf-8",
                      errors="replace") as f:
                for n, line in enumerate(f, 1):
                    if MARKER_RE.search(line.rstrip()):
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


def _all_offsets(hay: str, needle: str):
    start = 0
    while True:
        i = hay.find(needle, start)
        if i < 0:
            return
        yield i
        start = i + 1


# --------------------------------------------------------------------------
# THE REGISTRY. One entry per known piece of tape.
#
#   find           — the TAPE ITSELF, as text. Not an anchor near it: the
#                    thing whose deletion is the fix.
#   home           — the def that text lives in, or None for file scope. ONE
#                    scope answers both "is it present" and "has it expired";
#                    see the header. Do not add a second one.
#   marker_home    — the def whose text must carry the `TAPE:` comment, or
#                    None to look in a window around `find`. This is a
#                    DIFFERENT question from `home`: `_THIRD_PERSON_RE` is
#                    defined at module level and commented in question_line().
#   audit_item     — the row number in research/2026-08-24-law1-audit.md, for
#                    the five the audit recorded as undeclared.
# --------------------------------------------------------------------------
LIVE, MOVED, GONE = "live", "moved", "gone"


class Tape:
    def __init__(self, tid, rel, find, what, real_fix, home=None,
                 marker_home=None, audit_item=None, ledger_needle=None):
        self.id = tid
        self.rel = rel
        self.find = find
        self.what = what
        self.real_fix = real_fix
        self.home = home
        self.marker_home = marker_home
        self.audit_item = audit_item
        self.ledger_needle = ledger_needle or tid

    # -- the one scope ------------------------------------------------------
    def state(self, root: str, dirs=SHIPPED_DIRS) -> tuple[str, list[str]]:
        """(LIVE | MOVED | GONE, where). `where` is the sites that decided it:
        for LIVE the lines inside the entry's home, for MOVED the lines the
        tape is at instead. A missing FILE is not 'gone' — it is a leg that
        cannot be tested, and read() turns that into a failure."""
        src = read(root, self.rel)
        if self.home:
            lo, hi = slice_def_span(src, self.home)
        else:
            lo, hi = 0, len(src)
        inside, elsewhere = [], []
        for i in _all_offsets(src, self.find):
            line = f"{self.rel}:{_line_of(src, i)}"
            (inside if lo <= i < hi and hi > lo else elsewhere).append(line)
        if inside:
            return LIVE, inside
        if elsewhere:
            return MOVED, elsewhere
        # Not in this file at all. Before calling it gone — which retires the
        # entry and lets leg 2 go green for it — look in the rest of the
        # shipped organs. Moving a file is a refactor too.
        for rel in iter_shipped_files(root, dirs):
            if rel == self.rel:
                continue
            try:
                with open(os.path.join(root, rel), encoding="utf-8",
                          errors="replace") as f:
                    other = f.read()
            except OSError:
                continue
            for i in _all_offsets(other, self.find):
                elsewhere.append(f"{rel}:{_line_of(other, i)}")
        return (MOVED, elsewhere) if elsewhere else (GONE, [])

    def present(self, root: str, dirs=SHIPPED_DIRS) -> bool:
        """The tape is still in the tree — anywhere. MOVED counts as present,
        because moved tape is running tape."""
        return self.state(root, dirs)[0] != GONE

    def expired(self, root: str, dirs=SHIPPED_DIRS) -> bool:
        """The real fix has landed: the tape's own text is nowhere in the
        shipped organs. Same scope, same call, same answer as present()."""
        return self.state(root, dirs)[0] == GONE

    # -- where the comment has to be ---------------------------------------
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
        return f"{self.marker_home or self.home or self.find}"


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
        # `if compute_answer(g):` also appears in job_lane(), which is an
        # unrelated browser-arm router. home= is what tells the two apart, and
        # is why deleting THIS one does not leave the entry looking alive.
        find="if compute_answer(g):",
        home="is_consequential",
        what="the calculator is consulted on an undeclared goal and, if it "
             "can answer, flips a held goal to unattended",
        real_fix="the effect-channel rewrite: triage always declares "
                 "`touches`, so nothing reaches a capability sniff. The "
                 "comment already promises this — it just named no leg.",
        marker_home="is_consequential",
        audit_item=19,
        ledger_needle="[tape:compute_fallback]",
    ),
    Tape(
        tid="shard_too_thin",
        rel=CORE,
        find="def shard_too_thin(",
        what="a word count decides that a line is too thin to act on — "
             "the brake fitted after \"At 5:15\" minted a meeting with a "
             "person nobody had mentioned (event nbeb6oze5bmyrge)",
        marker_home="shard_too_thin",
        real_fix="segment-granularity triage: the day the judge reads closed "
                 "conversations instead of raw lines, shards stop existing as "
                 "decision units and the function is DELETED.",
        audit_item=20,
        ledger_needle="[tape:shard_too_thin]",
    ),
    Tape(
        tid="_pending_class prose fallback",
        rel=CORE,
        # The tape is the FALLBACK BRANCH, not the function: _pending_class()
        # survives the fix, the re-derivation from prose does not. `find` is
        # therefore the branch, scoped to the def that holds it.
        find="return is_consequential(job.get(",
        home="_pending_class",
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

# The rows leg 4 reads back out of the audit doc. Each is anchored to ONE table
# row, end to end, so a match cannot wander across the document into some other
# table's bolded number — and a row that stops matching is RED, never a silent
# skip. Both are pinned: AUDIT_DECLARED_COUNT had no leg reading it at all,
# which is its own way of looking thorough while checking nothing.
CENSUS_ROWS = (
    ("undeclared", AUDIT_UNDECLARED_COUNT,
     re.compile(r"^\|[^|\n]*\*\*TAPE,\s*UNDECLARED\*\*[^|\n]*\|"
                r"\s*\*\*(\d+)\*\*\s*\|\s*$", re.M)),
    ("properly declared", AUDIT_DECLARED_COUNT,
     re.compile(r"^\|[^|\n]*\*\*TAPE,\s*properly declared\*\*[^|\n]*\|"
                r"\s*\*\*(\d+)\*\*\s*\|\s*$", re.M)),
)


# --------------------------------------------------------------------------
# LEG 1 — THE LEG CAN READ THE TREE; NO MARKER THE REGISTRY HAS NEVER HEARD
#         OF; NO ENTRY WHOSE TAPE HAS MOVED OR IS ALREADY GONE.
#
# Four directions, because each is a different way to hide. A file type the
# leg cannot read is tape it will never see. An unregistered marker is tape
# that shipped without an expiry — a rejected diff by Law 2's own words. Tape
# that MOVED retires itself from two legs at once without anybody softening a
# predicate. An entry whose tape is gone is a ledger that has begun to lie, and
# a lying ledger is how "tracked by leg 4" survived four months of leg 4
# testing something else.
# --------------------------------------------------------------------------
def leg_1_markers_are_registered(root: str = ROOT, registry=None,
                                 dirs=SHIPPED_DIRS) -> str:
    registry = KNOWN_TAPE if registry is None else registry

    # (a) Can this leg read what it claims to scan? Everything below is a
    # statement about files it opened, so this question comes first.
    reach = scan_reach(root, dirs)
    if reach["missing"]:
        raise LegFailed(
            "SHIPPED_DIRS names " + ", ".join(f"`{d}/`" for d in reach["missing"])
            + ", and there is no such directory in this tree. The header "
              "prints that scan scope every run, so the gate is claiming to "
              "read an organ it never opens. Either the directory moved (point "
              "SHIPPED_DIRS at it) or it is gone (drop it, and say so in the "
              "commit).")
    if reach["hollow"]:
        details = ", ".join(f"`{d}/` ({reach['per_dir'][d][1]} files, 0 readable)"
                            for d in reach["hollow"])
        raise LegFailed(
            f"this leg can read nothing at all out of {details}. A shipped "
            "organ that yields zero files is a scan scope on paper only: the "
            "header says the gate reads it, and a `TAPE:` comment in there "
            "would be a rejected diff under Law 2 and a PASS under this leg. "
            "Add the file types to CODE_EXTS, or drop the directory from "
            "SHIPPED_DIRS if it holds no source (`chrome/` was dropped on "
            "2026-08-24 for exactly this: one .metadata file from a browser "
            "download cache).")
    if reach["unknown"]:
        shown = reach["unknown"][:8]
        more = len(reach["unknown"]) - len(shown)
        raise LegFailed(
            f"{len(reach['unknown'])} file(s) in the shipped organs are "
            "neither read for `TAPE:` markers nor declared as non-code, so "
            "this leg cannot say whether they carry tape:\n        "
            + "\n        ".join(shown)
            + (f"\n        ... and {more} more" if more else "")
            + "\n        Put the extension in CODE_EXTS if it is source — this "
              "leg then reads it — or in NOT_CODE_EXTS if it is data, logs or "
              "signing material. Unclassified is red on purpose: on 2026-08-24 "
              "CODE_EXTS held `.h` and not `.c`, so 142 of firmware/'s 235 "
              "files were invisible and `/* TAPE: */` in the pendant firmware "
              "read as PASS under the leg that enforces Law 2.")

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
              "DELETE the patch, or add a Tape(...) entry to KNOWN_TAPE whose "
              "`find` is the taped text itself and whose `home` is the def it "
              "lives in — that pair IS the expiry, and it goes true only when "
              "the text is gone from the shipped organs — and add it to the "
              f"standing-tape ledger in {LAWS}.")

    states = {t.id: t.state(root, dirs) for t in registry}
    moved = [t for t in registry if states[t.id][0] == MOVED]
    if moved:
        lines = []
        for t in moved:
            lines.append(
                f"{t.id}: the registry says `{t.find}` lives in "
                + (f"{t.home}() of {t.rel}" if t.home else t.rel)
                + ". It is not there. It IS at "
                + ", ".join(states[t.id][1][:4]) + ".")
        raise LegFailed(
            f"{len(moved)} piece(s) of registered tape MOVED out from under "
            "their registry entry, and moved tape is running tape:\n        "
            + "\n        ".join(lines)
            + "\n        Re-point the entry's `find`/`home` at where the code "
              "is now — or, if the real fix landed and those other sites are "
              "unrelated code that merely reads the same, retire the entry: "
              f"drop it from KNOWN_TAPE, drop its bullet from {LAWS}, and lower "
              "AUDIT_UNDECLARED_COUNT in the same diff.\n        This is red "
              "because an ordinary extract-method refactor does it without "
              "anyone touching a predicate. On 2026-08-24 that retired live "
              "tape from BOTH leg 2 and leg 3 at once: all three books agreed, "
              "and all three were wrong.")

    stale = [t.id for t in registry if states[t.id][0] == GONE]
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
    return (f"read {reach['read']} of {reach['total']} files in "
            + ", ".join(f"{d}/" for d in dirs)
            + f"; {len(markers)} marker(s), {len(registry)} registered, "
              "none orphaned, none moved, none stale")


# --------------------------------------------------------------------------
# LEG 2 — THE EXPIRY LEG LAW 2 ACTUALLY ASKS FOR: RED WHILE THE TAPE LIVES.
#
# This is the polarity tejas_gate leg 2 does not have. That leg fails when its
# tape is REMOVED — a legitimate regression pin for the recorded "At 5:15"
# failure, but it is not an expiry, and the repo has been reading it as one.
# Here the condition is the other way round: while a registered piece of tape
# is still in the tree and its real fix has not landed, this is RED. It goes
# green the day the tape is deleted, and not one day sooner.
#
# THIS LEG IS RED BY DESIGN. See BY_DESIGN_RED and the verdict in main().
# --------------------------------------------------------------------------
def leg_2_tape_expires(root: str = ROOT, registry=None,
                       dirs=SHIPPED_DIRS) -> str:
    registry = KNOWN_TAPE if registry is None else registry
    live = [(t, t.state(root, dirs)) for t in registry]
    live = [(t, st, where) for t, (st, where) in live if st != GONE]
    if live:
        lines = []
        for t, st, where in live:
            lines.append(f"{t.id}  ({where[0] if where else t.rel})\n"
                         f"          what it decides: {t.what}\n"
                         f"          real fix:        {t.real_fix}"
                         + ("\n          MOVED: it is no longer where the "
                            "registry says it is — see leg 1." if st == MOVED
                            else ""))
        raise LegFailed(
            f"{len(live)} piece(s) of tape are still load-bearing. This leg is "
            "RED on purpose and stays red until they are gone — that is what "
            "Law 2 means by an expiry:\n        "
            + "\n        ".join(lines)
            + "\n        Do NOT satisfy this leg by softening the predicate. "
              "The predicate is `the taped text is nowhere in the shipped "
              "organs`; the way to green is to land the real fix and delete "
              "the tape, then retire the entry (leg 1 will ask you to).")
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
def leg_3_audited_five(root: str = ROOT, registry=None, census_ids=None,
                       dirs=SHIPPED_DIRS) -> str:
    registry = KNOWN_TAPE if registry is None else registry
    census_ids = AUDIT_UNDECLARED if census_ids is None else census_ids
    census = [t for t in registry if t.audit_item in census_ids]
    open_items, gone = [], []
    for t in sorted(census, key=lambda x: x.audit_item):
        if t.state(root, dirs)[0] == GONE:
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
# LEG 4 — THE CENSUS CANNOT BE SHORTENED QUIETLY, AND THE THIRD BOOK IS
#         ACTUALLY READ.
#
# The failure mode this prevents is the obvious one: an agent facing a red
# leg 3 deletes a Tape entry instead of the tape. The count is declared apart
# from the list, so that edit lands here as a number that stopped matching,
# with a name on the diff — rather than as one fewer red line nobody counted.
#
# It shipped, itself, with the disease: `m is None` skipped the audit-doc check
# AND STILL PRINTED "the audit doc agrees: 5 undeclared". Renaming one heading
# in the doc — a formatting edit, no number touched — took the third book
# offline inside the one leg built to be the tripwire, and it kept vouching.
# A message that asserts something untrue is worse than no message: this leg
# now fails when it cannot read the row, and says which row it could not read.
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
    if not os.path.exists(doc):
        raise LegFailed(
            f"{AUDIT_DOC} is not in this tree. It is the third book — the "
            "dated record this gate's census is a copy of — and without it "
            "the only ledger is this file, which is the state that let five "
            "pieces of tape accumulate. If a newer audit superseded it, point "
            "AUDIT_DOC at that one in the same diff and carry the counts "
            "across; do not let the leg run without it.")
    with open(doc, encoding="utf-8", errors="replace") as f:
        text = f.read()
    agreed = []
    for label, pinned, row_re in CENSUS_ROWS:
        m = row_re.search(text)
        if m is None:
            raise LegFailed(
                f"{AUDIT_DOC} is in the tree, but this leg can no longer find "
                f"the row that states how many pieces of tape were {label}. "
                "Until 2026-08-24 that made the check SKIP while the leg still "
                "printed \"the audit agrees\" — so the doc could be edited down "
                "to any census and this leg kept vouching for a number it had "
                "not read. It fails instead now.\n        Either the row was "
                "reformatted (restore it, or re-point CENSUS_ROWS at its new "
                "shape) or the audit was replaced (point AUDIT_DOC at the new "
                "one). The row this leg expects looks like:\n        "
                f"| **TAPE, {label.upper() if label == 'undeclared' else label}"
                "** (…) | **N** |")
        if int(m.group(1)) != pinned:
            raise LegFailed(
                f"{AUDIT_DOC} now reports {m.group(1)} pieces of tape "
                f"{label}; this gate is pinned to {pinned}. One of the two was "
                "edited. The audit is the dated record — if it grew, register "
                "the new items here; if it shrank, say which piece was closed "
                "and how.")
        agreed.append(f"{pinned} {label}")
    return (f"census intact ({AUDIT_UNDECLARED_COUNT} audited items, "
            f"{len(registry)} registered); {AUDIT_DOC} agrees: "
            + ", ".join(agreed))


# --------------------------------------------------------------------------
# LEG 5 — THE LAW'S OWN LEDGER AND THIS REGISTRY SAY THE SAME THING, BOTH WAYS.
#
# The third book. HARNESS-LAWS.md carries a "Known standing tape" section that
# a human reads; this file carries the version a machine runs. When they drift,
# the human one is what the next agent believes, and it was already wrong once:
# the ledger said _READ_ONLY_RE was "tracked by tejas_gate.py leg 4" while
# leg 4 was green and the regex was still deciding.
#
# Both directions. The docstring said "and vice versa" from the first day; only
# one direction was implemented, so a `[tape:…]` bullet whose registry entry
# had been deleted read as compliant — which is the same shape as leg 4's
# shrinking census, one file over.
# --------------------------------------------------------------------------
LEDGER_NEEDLE_RE = re.compile(r"\[tape:[A-Za-z0-9_.-]+\]")


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
    registered = {t.ledger_needle for t in registry}
    unbacked = sorted(set(LEDGER_NEEDLE_RE.findall(section)) - registered)
    if unbacked:
        raise LegFailed(
            f"the standing-tape ledger in {LAWS} carries bullets this registry "
            "has never heard of: " + ", ".join(unbacked)
            + ".\n        A ledger bullet with no registry entry is a promise "
              "with no predicate behind it — the human book says the tape is "
              "tracked and nothing runs. Either add the Tape(...) entry here, "
              "or delete the bullet because the tape is gone. (If the entry "
              "does exist, its `ledger_needle` is not this tag — set it to the "
              "tag, because the tag is what a human greps for.)")
    if THIS_GATE not in section:
        raise LegFailed(
            f"the standing-tape ledger in {LAWS} does not name `{THIS_GATE}` as "
            "the leg that tracks these. A ledger entry with no leg is the "
            "state Law 2 was written to end.")
    return (f"{len(registry)} entries, and {LAWS}'s ledger names every one — "
            f"and names nothing this registry does not")


# Each leg carries whether its red is EXPECTED. Leg 2 is the only one: it is
# Law 2's expiry, and it is red until the tape is deleted. Everything else
# going red is NEWS, and main() reports it as news rather than as one more
# lowercase line under leg 2's block.
LEGS = [
    (1, "EVERY MARKER IS REGISTERED", leg_1_markers_are_registered, False),
    (2, "TAPE IS RED WHILE IT LIVES", leg_2_tape_expires, True),
    (3, "THE AUDITED FIVE ARE DECLARED OR GONE", leg_3_audited_five, False),
    (4, "THE CENSUS CANNOT SHRINK QUIETLY", leg_4_census_intact, False),
    (5, "THE LAW'S LEDGER AGREES", leg_5_ledger_agrees, False),
]
BY_DESIGN_RED = tuple(n for n, _, _, d in LEGS if d)


def run(root: str = ROOT) -> list[tuple[int, str, bool, bool, str]]:
    """Every leg, in order: (num, name, by_design_red, ok, detail_or_message).
    Split out of main() so tests/test_tape_gate.py can drive the VERDICT and
    not only the legs — the 2026-08-24 hole was in the verdict."""
    out = []
    for num, name, fn, by_design in LEGS:
        try:
            out.append((num, name, by_design, True, fn(root)))
        except LegFailed as e:
            out.append((num, name, by_design, False, str(e)))
        except Exception as e:  # noqa: BLE001
            out.append((num, name, by_design, False, f"gate itself errored: {e}"))
    return out


def verdict(results) -> int:
    """0 clean, 1 the expected steady state, 2 a leg that is not red by design
    went red. Two nonzero codes, because one of them is news and the other is
    Tuesday."""
    reds = [r for r in results if not r[3]]
    if not reds:
        return 0
    return 1 if all(r[2] for r in reds) else 2


def fingerprint(results) -> str:
    """One short line naming exactly which legs are red, so two runs can be
    told apart by eye or by diff. This is the other half of the answer to
    "nothing distinguishes the steady state from somebody shrinking the
    census": the exit code says WHETHER it changed, this says WHAT changed.

        RED LEGS: 2 (by design), 3          the state on 2026-08-24
        RED LEGS: 2 (by design), 3, 4       somebody shrank the census
    """
    reds = [r for r in results if not r[3]]
    if not reds:
        return "RED LEGS: none"
    return "RED LEGS: " + ", ".join(
        f"{r[0]} (by design)" if r[2] else str(r[0]) for r in reds)


def main(root: str = ROOT) -> int:
    print()
    print(f"  TAPE GATE    tree: {root}")
    print(f"               law:  {LAWS} Law 2 — tape ships only with an expiry")
    print(f"               scan: {', '.join(SHIPPED_DIRS)}  "
          "(overnight/ and tests/ excluded: Law 1 exempts gates)")
    print(f"               read: RED at leg {', '.join(map(str, BY_DESIGN_RED))}"
          " is the steady state (exit 1). Exit 2 means a leg")
    print("                     that is NOT red by design went red — that is "
          "the news.")
    print("  " + "-" * 62)
    results = run(root)
    for num, name, by_design, ok, detail in results:
        mark = "PASS" if ok else ("RED " if by_design else "FAIL")
        suffix = "   (red by design — Law 2's expiry)" if by_design and not ok else ""
        print(f"  [{num}] {mark}  {name}{suffix}")
        print(f"        {detail}")
    print("  " + "-" * 62)

    code = verdict(results)
    print("  " + fingerprint(results))
    if code == 0:
        print("  CLEAN — no tape is left in the shipped organs")
        print()
        return 0

    if code == 2:
        news = [r for r in results if not r[3] and not r[2]]
        expected = [r for r in results if not r[3] and r[2]]
        print("  THE BOOKS DISAGREE — leg "
              + ", ".join(str(r[0]) for r in news)
              + (" is" if len(news) == 1 else " are")
              + " red, and that is not a red this gate")
        print("  is designed to have. Reprinted here so it is not read as part "
              "of leg 2:")
        for num, name, _by, _ok, msg in news:
            print(f"      [{num}] {name}")
            for line in msg.splitlines():
                body = line[8:] if line.startswith(" " * 8) else line.strip()
                print(f"          {body}" if body else "")
        if expected:
            print("  Leg " + ", ".join(str(r[0]) for r in expected)
                  + " is red too, and always is — that is Law 2's expiry, not")
            print("  news. Read the leg(s) above it, not that one.")
    else:
        live = [r for r in results if not r[3]]
        print("  TAPE OUTSTANDING — leg "
              + ", ".join(str(r[0]) for r in live)
              + " red, and every other book agrees. This is")
        print("  the steady state: Law 2 has an expiry and it has not come true.")

    print("  Red here is the law working. Green means the tape is GONE, not")
    print("  that it was written down. Do not soften a predicate to get there.")
    print("  What this gate cannot see: tape nobody marked, nobody registered,")
    print("  and that is not one of the audited five. Only an audit finds that")
    print(f"  — the last one is {AUDIT_DOC}.")
    print()
    return code


if __name__ == "__main__":
    sys.exit(main())
