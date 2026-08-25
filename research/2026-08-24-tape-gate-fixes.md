# The tape gate shipped with the disease it was built to catch — 1 Critical, 3 Important, 1 Minor, all fixed

Fixes for the review in `.superpowers/sdd/tape-gate-criticals.md` (of `bd93df3c`).
Verdict there was **fix in place, not revert**, because every "turn it green
dishonestly" attack had already failed. Nothing on that list regressed; the
list is re-run at the bottom of this file.

Scope held: `overnight/` and `tests/` only. `brain/`, `extension/`, `app/ios/`
and `proof/` belong to other trees tonight; what they need is at the end.

Files changed: `overnight/tape_gate.py`, `tests/test_tape_gate.py`.

---

## Method

Every reproduction and every mutation ran against a **mirror tree** in the
scratchpad — symlinks to the repo for the organs I was not mutating, real
copies of the ones I was — so that no reproduction could write into another
agent's in-flight files. That precaution earned itself twice: on the first
build the mirror still held symlinks inside `brain/` and `overnight/`, and two
edits went through them into the real `brain/asking.py` and
`overnight/MORNING.md`. Both were caught by `git status`, reverted with
`git checkout --`, and every check that touched them was re-run against a
mirror rebuilt with `cp -R`. **If you copy this method, dereference before you
mutate: `find <mirror> -type l` must print nothing for any directory you write
into.**

---

## C1 — an extract-method refactor retired live tape from BOTH leg 2 and leg 3

`present()` searched the whole FILE; `expired()` searched only the enclosing
DEF. The scopes disagreed, so tape that *moved* read as "expired" while it was
still in the tree and still running.

### Before

Split the tail of `is_consequential` into `_undeclared_default(g)` — a routine
refactor — leaving the `TAPE:` marker at the old site:

```
$ grep -n "compute_answer(g)" brain/anticipy_core.py
598:    if compute_answer(g):        <- the tape, still there, still running
860:    if compute_answer(g):

  [1] PASS  EVERY MARKER IS REGISTERED
        4 marker(s) in the shipped organs, 5 registered, none orphaned either way
  [2] FAIL  TAPE IS RED WHILE IT LIVES
        4 piece(s) of tape are still load-bearing.          <- was 5
  [3] fail  THE AUDITED FIVE ARE DECLARED OR GONE
        4 of the 5 pieces of tape ... are still undeclared   <- #19 fell out
```

All three books agreed, and all three were wrong. **Nobody softened a
predicate — the predicate's scope was wrong**, which is a subtler failure than
the one the gate was built for.

The second half, from the same cause in the other direction: `if
compute_answer(g):` occurs twice (`:595` in `is_consequential`, `:858` in the
unrelated browser-arm router `job_lane`). Delete the real tape at `:595` — the
fix landing — and:

```
  [1] PASS  EVERY MARKER IS REGISTERED
        3 marker(s) in the shipped organs, 5 registered, none orphaned either way
```

`present()` matched `job_lane`'s copy, so leg 1 never prompted anyone to retire
the entry.

### After

**One scope, three states.** Every entry now resolves through one function,
`Tape.state()`, and `present()` and `expired()` are two views of its answer:

| state | meaning | verdict |
|---|---|---|
| `LIVE` | the tape is where the registry says it is | leg 2 RED |
| `MOVED` | it is not there, but it IS somewhere else in the shipped organs | leg 1 RED, naming both places |
| `GONE` | the text is nowhere in the shipped organs at all | leg 2 green for it; leg 1 asks you to retire the entry |

`MOVED` is the state that did not exist. A move is not a fix, and the gate
refuses to guess which one happened — it names both sites and makes the human
re-point or retire the entry, in a diff, with a name on it. The same rule
catches a move to another *file*: before an entry can reach `GONE`, the rest of
the shipped organs are searched for its text.

The `expired=` per-entry override and `_fallback_gone()` are **deleted** — that
parameter is exactly how the two scopes came to disagree. `#19` and `#21` are
fallback *branches* rather than whole symbols, and they are now expressed as
`find` (the branch) + `home` (the def it lives in), which is one scope by
construction.

Same refactor, fixed gate:

```
  [1] FAIL  EVERY MARKER IS REGISTERED
        1 piece(s) of registered tape MOVED out from under their registry entry,
        and moved tape is running tape:
        is_consequential compute fallback: the registry says `if compute_answer(g):`
        lives in is_consequential() of brain/anticipy_core.py. It is not there.
        It IS at brain/anticipy_core.py:598, brain/anticipy_core.py:860.
        [...] This is red because an ordinary extract-method refactor does it
        without anyone touching a predicate. On 2026-08-24 that retired live tape
        from BOTH leg 2 and leg 3 at once: all three books agreed, and all three
        were wrong.
  [2] RED   TAPE IS RED WHILE IT LIVES   (red by design — Law 2's expiry)
        5 piece(s) of tape are still load-bearing.           <- 5, not 4
        is_consequential compute fallback  (brain/anticipy_core.py:598)
          MOVED: it is no longer where the registry says it is — see leg 1.
  RED LEGS: 1, 2 (by design), 3          exit 2
```

And the ambiguous-needle half — the real fix lands, `job_lane`'s line stays:

```
  [1] FAIL  EVERY MARKER IS REGISTERED
        1 piece(s) of registered tape MOVED out from under their registry entry [...]
        Re-point the entry's `find`/`home` at where the code is now — or, if the
        real fix landed and those other sites are unrelated code that merely reads
        the same, retire the entry: drop it from KNOWN_TAPE, drop its bullet from
        HARNESS-LAWS.md, and lower AUDIT_UNDECLARED_COUNT in the same diff.
```

**Can a refactor still retire live tape? No.** Verified four ways in
`tests/test_tape_gate.py`: extract-method, move-to-another-file, rename the
enclosing def, and an identical line elsewhere in the same file. A fifth test,
`test_present_and_expired_are_the_same_question`, asserts the invariant C1
broke — across five different tree shapes, `present()` and `expired()` are
never both true and never both false.

---

## I2 — leg 4 printed "the audit agrees" when its regex matched nothing

### Before

Rename one heading in the audit doc from `**TAPE, UNDECLARED**` to
`**TAPE (undeclared)**` — a formatting edit, no number touched — then edit the
census to 1:

```
$ grep -n "TAPE (undeclared)" research/2026-08-24-law1-audit.md
73:| **TAPE (undeclared)** (...) | **1** |

  [4] PASS  THE CENSUS CANNOT SHRINK QUIETLY
        census intact (5 audited items, 5 registered);
        research/2026-08-24-law1-audit.md agrees: 5 undeclared
```

It agreed with nothing. `m is None` skipped the check and still printed the
affirmative claim, so the third book went silently offline inside the one leg
built to be the tripwire.

### After

Four changes:

1. **A row that cannot be read is RED**, not skipped. A failure message that
   asserts something untrue is worse than no message.
2. **The row regexes are anchored to one table row, end to end** (`^\|…\|$`,
   `re.M`). The old pattern spanned the whole document under `re.S` with `.*?`,
   so a reformatted row let the match slide forward onto some unrelated bolded
   number and vouch for that instead. Demonstrated directly: unbold the census
   row's count and put `| some other tally | **9** |` beneath it, and the old
   regex returns `9` — a number from a different row entirely — while the new
   one returns `None` and the leg goes red.
3. **`AUDIT_DECLARED_COUNT` is now read too.** It was a constant no leg ever
   looked at — its own quiet way of looking thorough while checking nothing.
4. **A missing audit doc is RED.** It used to pass with the note "audit doc
   missing from the tree" — honest, but deleting the third book must not be
   cheaper than editing it.

```
  [4] FAIL  THE CENSUS CANNOT SHRINK QUIETLY
        research/2026-08-24-law1-audit.md is in the tree, but this leg can no
        longer find the row that states how many pieces of tape were undeclared.
        Until 2026-08-24 that made the check SKIP while the leg still printed
        "the audit agrees" — so the doc could be edited down to any census and
        this leg kept vouching for a number it had not read. It fails instead now.
        Either the row was reformatted (restore it, or re-point CENSUS_ROWS at its
        new shape) or the audit was replaced (point AUDIT_DOC at the new one).
  RED LEGS: 2 (by design), 3, 4          exit 2
```

Deleting the doc outright:

```
  [4] FAIL  THE CENSUS CANNOT SHRINK QUIETLY
        research/2026-08-24-law1-audit.md is not in this tree. It is the third
        book — the dated record this gate's census is a copy of [...]
```

The steady-state detail line now reads
`research/2026-08-24-law1-audit.md agrees: 5 undeclared, 0 properly declared` —
and it only says "agrees" when it read both rows.

---

## I3 — leg 1 could not read 142 of 235 files in a directory it said it scanned

### Before

```
$ cat >> firmware/source/src/led.c
/* TAPE: clamp the LED duty cycle by hand until the driver is fixed. */

  [1] PASS  EVERY MARKER IS REGISTERED
        3 marker(s) in the shipped organs, 5 registered, none orphaned either way
```

`CODE_EXTS` had `.h` and not `.c`. Undeclared tape in the pendant firmware was
a rejected diff under Law 2 and a PASS under the leg that enforces it.

### After

The fix is deliberately **not** "add `.c`". Adding one extension leaves the
next hole exactly where this one was. Instead the gate now states its own
reach, and **anything it cannot classify is red**:

* `CODE_EXTS` widened to every language the shipped organs are actually written
  in (`.c .cc .cpp .cxx .hpp .hh .s .html .htm .css .rb .go .rs` added), plus
  `CODE_NAMES` for extensionless source (`Dockerfile`, `Makefile`, `Kconfig`,
  `CMakeLists.txt`, `Procfile`).
* `NOT_CODE_EXTS` declares what is data, logs, fixtures, images, archives,
  signing material and build metadata. Dotfiles are data by convention.
* Every file in a shipped organ must fall in one list or the other. **A third
  case turns leg 1 red** until a human files it.
* **A shipped organ that yields zero readable files is red**, and so is one
  named in `SHIPPED_DIRS` that does not exist — the header must never print a
  scan scope the code does not have.
* `chrome/` was **dropped from `SHIPPED_DIRS`**. It is not an organ: it holds
  one `.metadata` alias map from a chrome-for-testing download cache. The
  browser arm's code is `extension/`. The hollow-directory check is what forced
  the removal, and re-adding `chrome` reproduces the red on demand (mutation 3c
  below).

```
  [1] PASS  EVERY MARKER IS REGISTERED
        read 614 of 1479 files in brain/, extension/, app/, backend/, proof/,
        firmware/; 3 marker(s), 5 registered, none orphaned, none moved, none stale
```

The reach is now printed every run. With the firmware tape re-applied:

```
  [1] FAIL  EVERY MARKER IS REGISTERED
        1 `TAPE:` marker(s) in the shipped organs that overnight/tape_gate.py has
        never heard of:
        firmware/source/src/led.c:35  /* TAPE: clamp the LED duty cycle by hand [...]
```

A new language lands in a shipped organ:

```
  [1] FAIL  EVERY MARKER IS REGISTERED
        1 file(s) in the shipped organs are neither read for `TAPE:` markers nor
        declared as non-code, so this leg cannot say whether they carry tape:
        brain/router.rs
```

**The quieter way to reopen I3** is not deleting an extension but demoting one
— moving `.c` from `CODE_EXTS` into `NOT_CODE_EXTS` keeps the reach check
passing while the files stop being read. `test_the_languages_this_repo_actually_ships_are_read`
pins the eight that matter, so demoting one has to break a named test.

---

## I4 — the by-design-red alarm problem, and my answer

### Before

Leg 2 is red by design, permanently, and runs first. Drop the `_READ_ONLY_RE`
entry from `KNOWN_TAPE` (it carries no marker, so leg 1 stays quiet):

```
  [1] PASS  EVERY MARKER IS REGISTERED
  [2] FAIL  TAPE IS RED WHILE IT LIVES
  [3] fail  THE AUDITED FIVE ARE DECLARED OR GONE
  [4] fail  THE CENSUS CANNOT SHRINK QUIETLY        <- lowercase, buried
  [5] PASS  THE LAW'S LEDGER AGREES
  TAPE OUTSTANDING — first failing leg: 2 (TAPE IS RED WHILE IT LIVES)

EXIT=1                                              <- same as the steady state
```

Nothing in the exit code or the headline distinguished "the expected steady
state" from "somebody shrank the census."

### The answer: a by-design red is a *declared* red, and everything else is news

Three mechanisms, none of which widens the set of reds the gate treats as
normal:

**1. Expectedness is declared per leg, and the verdict has three states.**
`LEGS` carries a `by_design_red` flag; `BY_DESIGN_RED == (2,)` and a test pins
it. `verdict()` returns:

* `0` CLEAN — no tape left anywhere.
* `1` TAPE OUTSTANDING — leg 2 is red and **nothing else is**. The steady state.
* `2` THE BOOKS DISAGREE — a leg that is *not* red by design went red.

Two nonzero codes, because one of them is news and the other is Tuesday.
Anything checking `!= 0` still sees red in both. Nothing in the repo consumes
this gate's exit code today, so `2` is safe to introduce.

**2. A one-line fingerprint**, printed at the top of the footer:

```
  RED LEGS: 2 (by design), 3              <- the state today
  RED LEGS: 2 (by design), 3, 4           <- somebody shrank the census
```

The exit code says *whether* it changed; this says *what* changed, in a string
short enough to eyeball or diff. `fingerprint()` is a pure function of the
results and is unit-tested against both shapes.

**3. The unexpected failure's whole message is reprinted in the footer**, below
the separator, so a real red is never read as part of leg 2's twenty-line
block. Buried is the same as missing.

Marks changed too: the by-design red prints `RED ` with
`(red by design — Law 2's expiry)`; an unexpected red prints `FAIL`. `[4] FAIL`
in caps next to `[2] RED` is distinguishable at a glance.

**4. And a tripwire outside the gate.** `EXPECTED_RED_LEGS` in
`tests/test_tape_gate.py` pins today's fingerprint. It is the one test in that
file that pins repo state, and it pins the only thing worth pinning: *which*
legs are red, not that tape exists. Any other leg going red breaks the suite
with a message telling the reader to run the gate and read the
`THE BOOKS DISAGREE` block. When leg 3 is closed it also goes red — that is the
fix being recorded, not punished, and the message says to update the constant
in the same diff.

Same census shrink, fixed gate:

```
  [1] PASS  EVERY MARKER IS REGISTERED
  [2] RED   TAPE IS RED WHILE IT LIVES   (red by design — Law 2's expiry)
  [3] FAIL  THE AUDITED FIVE ARE DECLARED OR GONE
  [4] FAIL  THE CENSUS CANNOT SHRINK QUIETLY
        the registry covers audit items (19, 20, 21, 50), but the 2026-08-24
        audit recorded (19, 20, 21, 22, 50) [...]
  [5] FAIL  THE LAW'S LEDGER AGREES
  RED LEGS: 2 (by design), 3, 4, 5
  THE BOOKS DISAGREE — leg 3, 4, 5 are red, and that is not a red this gate
  is designed to have. Reprinted here so it is not read as part of leg 2:
      [4] THE CENSUS CANNOT SHRINK QUIETLY
          the registry covers audit items (19, 20, 21, 50) [...]
  Leg 2 is red too, and always is — that is Law 2's expiry, not news.
EXIT=2
```

(Leg 5 fired as a bonus: its new reverse-direction check saw the
`[tape:read_only_re]` bullet left standing in `HARNESS-LAWS.md` with no
registry entry behind it.)

### The judgement call inside the judgement call: the gate exits **2** today

Leg 3 is red on this tree — the five audited pieces still carry no `TAPE:`
comment naming this gate. So today's verdict is `exit 2`, not `exit 1`.

I considered adding leg 3 to `BY_DESIGN_RED` so that today reads as the steady
state, and rejected it. Leg 3's red is not a design property; it is an open
Law-2 violation that is **five comments away from closed** in `brain/`. Adding
it to the expected set would be widening the definition of "normal" to quiet a
leg, which is the disease one level up — and it is what let leg 3's red print
as a lowercase `fail` under leg 2 for as long as this gate has existed. The
honest reading is that the fix *surfaced a real red that was already hiding*.

Proof that the distinction works rather than being permanently stuck at 2:
declare all five in the mirror and remove nothing —

```
  [1] PASS  EVERY MARKER IS REGISTERED
        [...] 5 marker(s), 5 registered, none orphaned, none moved, none stale
  [2] RED   TAPE IS RED WHILE IT LIVES   (red by design — Law 2's expiry)
        5 piece(s) of tape are still load-bearing.
  [3] PASS  THE AUDITED FIVE ARE DECLARED OR GONE
  [4] PASS  THE CENSUS CANNOT SHRINK QUIETLY
  [5] PASS  THE LAW'S LEDGER AGREES
  RED LEGS: 2 (by design)
  TAPE OUTSTANDING — leg 2 red, and every other book agrees. This is
  the steady state: Law 2 has an expiry and it has not come true.
EXIT=1
```

That is the honest steady state, one `brain/` diff away — and it also
re-confirms that **declaring all five does not turn the gate green**.

---

## M5 — a marker split across two comment lines was invisible

### Before

```python
# TAPE
# (HARNESS-LAWS.md Law 2): urgency by word list. Tracked by overnight/tape_gate.py.
_URGENT = ('asap', 'now', 'urgent')
```

```
$ grep -rn "TAPE" brain/memory.py
1907:# TAPE                                <- the human finds it, reads it as declared

  [1] PASS  EVERY MARKER IS REGISTERED
        3 marker(s) in the shipped organs, 5 registered, none orphaned either way
```

Audit item #21's shape — a declaration that reads compliant and enforces
nothing — recreated inside the enforcement.

### After

`MARKER_RE` accepts `TAPE` at end-of-line (`(?:[:.]|$)`, `re.M`).
`\bTAPE\b` stays case-sensitive, so "duct tape and prayer" still does not fire,
and the four existing false-positive tests still pass with a fifth added
(`label = TAPE_KINDS[0]`).

```
  [1] FAIL  EVERY MARKER IS REGISTERED
        1 `TAPE:` marker(s) in the shipped organs that overnight/tape_gate.py has
        never heard of:
        brain/memory.py:1907  # TAPE
```

The real tree still finds exactly 3 markers, so the widened regex added no
false positives here.

---

## Leg 5 also gained its missing half

Its docstring said "and vice versa" from day one and only one direction was
implemented: a `[tape:…]` bullet in `HARNESS-LAWS.md` whose registry entry had
been deleted read as compliant to a human and ran no predicate at all — the
same shape as leg 4's shrinking census, one file over. Both directions now
check, and the mutation is tested.

---

## Every mutation run

Each was applied to a mirror tree, watched go red, and restored. Baseline
between mutations was re-confirmed each time.

| # | mutation | before | after |
|---|---|---|---|
| C1 | extract-method refactor, marker left at old site | leg 1 PASS, leg 2 says 4, leg 3 says 4 of 5 | `RED LEGS: 1, 2 (by design), 3` — leg 1 names both sites, leg 2 says 5 |
| C1b | real fix lands; `job_lane`'s identical line stays | leg 1 PASS, entry never retired | leg 1 RED: MOVED, "retire the entry ... in the same diff" |
| I2 | rename one audit-doc heading, then shrink the count to 1 | `[4] PASS ... agrees: 5 undeclared` | `[4] FAIL ... can no longer find the row` |
| I2b | delete the audit doc | `[4] PASS` with a note | `[4] FAIL ... is not in this tree` |
| I2c | audit row loses its bold count; a bolded number sits in the next row | old regex read the OTHER row's number (`9`) and reported it as the census | `[4] FAIL ... can no longer find the row` |
| I2d | rename the *properly declared* row | never checked | `[4] FAIL ... properly declared` |
| I3 | `/* TAPE: */` appended to `firmware/source/src/led.c` | `[1] PASS` | `[1] FAIL` naming `firmware/source/src/led.c:35` |
| I3b | `brain/router.rs` added with a marker | (invisible) | `[1] FAIL ... neither read for markers nor declared as non-code` |
| I3c | `chrome` put back into `SHIPPED_DIRS` | silent | `[1] FAIL ... can read nothing at all out of chrome/ (1 files, 0 readable)` |
| I4 | drop the `_READ_ONLY_RE` entry from the registry | `[4] fail` buried, footer says leg 2, exit 1 | `RED LEGS: 2 (by design), 3, 4, 5`, footer reprints leg 4, exit 2 |
| M5 | marker split across two comment lines | `[1] PASS` | `[1] FAIL ... brain/memory.py:1907  # TAPE` |
| — | delete each of the five tapes in turn | — | all five reach `GONE` — the leg can still go green |

### Non-regression: the review's "what FAILED" list, re-run

Baseline for these was the honest steady state (all five declared,
`RED LEGS: 2 (by design)`, exit 1).

| attack | result |
|---|---|
| Declare all five and remove nothing | leg 2 stays RED with all five listed — exit 1 |
| Shrink the census | `RED LEGS: 1, 2 (by design), 4, 5` — exit 2 |
| A second marker inside an already-declared function | `RED LEGS: 1, 2 (by design)` — exit 2 |
| A new marker anywhere in the 4,000-line file | `RED LEGS: 1, 2 (by design)` — exit 2 |
| Rename a tape symbol | `RED LEGS: 1, 2 (by design)` — exit 2 |
| Move tape outside `SHIPPED_DIRS` | `RED LEGS: 1, 2 (by design)` — exit 2 |
| Empty the registry | `RED LEGS: 1, 4, 5` — exit 2 |
| Move the ledger anchors | `RED LEGS: 2 (by design), 5` — exit 2 |
| Tape written into `overnight/` | still excluded, still exit 1 — the exclusion is intact |

### Tests

`tests/test_tape_gate.py`: 29 tests → **70**, all passing. New coverage: the
three states and the four ways tape can move, the present/expired invariant,
the reach checks, the marker regex's end-of-line form and its false-positive
guards, leg 4's four audit-doc mutations, leg 5's reverse direction, and
`verdict()` / `fingerprint()` / the footer reprint driven directly.

Whole suite: **1440 passed, 1 failed** — `test_earls_live_failures.py::
test_needs_user_questions_are_never_swallowed_into_fallback`, which is another
agent's in-flight `extension/` work and was already red before this change.
`python3 overnight/tejas_gate.py` — **8/8, unchanged**.
`python3 overnight/tape_gate.py` — **RED, exit 2**, as it should be.

---

## Left for another tree

* **`brain/` — five comments, and the gate goes to its honest steady state.**
  Leg 3 is red because the five audited pieces carry no `TAPE:` comment naming
  `overnight/tape_gate.py`. `#19` (`is_consequential`) and `#22`
  (`_READ_ONLY_RE`) have no marker at all; `#20` (`shard_too_thin`), `#21`
  (`_pending_class`) and `#50` (`brain/asking.py:216`) have markers that name
  no leg or the wrong one. Adding them takes the gate from `exit 2` to
  `exit 1` / `RED LEGS: 2 (by design)`, and `EXPECTED_RED_LEGS` in
  `tests/test_tape_gate.py` must be updated in the same diff.
* **`CLAUDE.md`** says `tape_gate.py` "is **RED right now on purpose**". It is
  worth adding the fingerprint line — `RED LEGS: 2 (by design), 3` — next to
  that sentence, so a change in one short string is the alarm for anyone
  reading the map rather than the gate. Root file, not my scope.
* **`HARNESS-LAWS.md`** now has a leg reading its ledger in both directions and
  a gate with three exit codes; neither is described there. Also not my scope.
* **`AGENTS.md`** still cites `fellowship_gate.py` and
  `research/HOW-AN-AGENT-EXISTS.md`, neither of which has ever existed on any
  ref. Unchanged from the previous review; still true.

---

## What this gate still cannot see

Stated in the file's own header too, so green is never read as safe.

* **Tape nobody marked, that is not one of the audited five, and nobody
  registered.** Unchanged and unfixable deterministically: finding it is a
  reading of what code MEANS, which belongs to a model with full context
  (Law 1, Law 5). The mechanism is an audit, and leg 4 pins the last one.
* **Tape in `overnight/` and `tests/`.** Deliberately excluded — Law 1 exempts
  gates and evals, and both directories discuss tape by nature. Verified still
  excluded, and the exclusion is printed in the gate's output every run.
* **A `find` needle that is not really the tape.** The registry is only as
  honest as its five `find` strings. Nothing checks that `find` names the
  construct the `what` sentence describes; that is a reading of meaning.
  `test_the_real_registry_still_points_at_real_code` checks only that each
  needle resolves and is `LIVE`.
* **A demotion in `NOT_CODE_EXTS`.** Eight languages are pinned by test; a
  ninth could still be demoted from code to data in a diff, and only a reviewer
  would catch it.
* **Whether a `TAPE:` comment tells the truth.** Leg 3 checks a marker exists
  and names this gate. Whether the "real fix" it promises is real is a reading
  of meaning, and the review is the mechanism.
* **`MOVED` cannot tell a move from a coincidence.** By design: it names every
  site and refuses to guess, which converts the ambiguity into a signed
  confession rather than a silent green.
