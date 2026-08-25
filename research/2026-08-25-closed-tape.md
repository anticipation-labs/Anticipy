# THE TAPE GATE COULD NOT RECORD A CLOSURE

**2026-08-25.** `overnight/tape_gate.py` enforces Law 2 — tape ships with a
`TAPE:` comment and a gate leg that stays red until the real fix replaces it.
It holds five audited items red by name, with the census declared apart from
the list so shrinking it trips a number. That design is sound; a reviewer
cannot turn it green by silence.

It had no green path for tape that is genuinely closed. The one action Law 2
exists to encourage had no way to be reported as success, and **a gate that
cannot express the outcome it wants is a gate people route around.**

Found by `docs/superpowers/specs/2026-08-25-sorter-conversation-granularity.md`
(committed `0a9e8d13`) while planning to retire `shard_too_thin`, one of the
five. Scope of this change: `overnight/tape_gate.py`, `tests/test_tape_gate.py`.

---

## 1. The three reds, reproduced before anything was built

Against a **mirror of the real tree** (`brain/ extension/ app/ backend/ proof/
firmware/` rsynced to a scratchpad, 621 readable files of 1486 — identical
reach to the real run), with `shard_too_thin` and its call site actually
deleted from `brain/anticipy_core.py`. Deleting it turns leg 2 green for that
entry, and immediately turns **leg 1 red**:

```
  [1] FAIL  EVERY MARKER IS REGISTERED
        the registry names tape that is no longer in the tree: shard_too_thin.
        Law 2: "Tape whose gate leg went green gets DELETED, not kept 'just in
        case.'" The tape is gone — now retire it. Drop the entry from
        KNOWN_TAPE, drop its bullet from HARNESS-LAWS.md, and lower
        AUDIT_UNDECLARED_COUNT if it was one of the audited five.
```

Every road out of that instruction was red — including the instruction itself.

**Way 1 — drop the entry (and its ledger bullet), leave the count at 5:**

```
  [4] FAIL  THE CENSUS CANNOT SHRINK QUIETLY
        the registry covers audit items (19, 21, 22, 50), but the 2026-08-24
        audit recorded (19, 20, 21, 22, 50) as undeclared tape. An entry was
        dropped or renumbered. If a piece genuinely no longer exists, leg 1
        retires it and AUDIT_UNDECLARED changes in the same diff — deleting the
        entry alone hides the item instead of closing it.
  RED LEGS: 2 (by design), 3, 4          EXIT=2
```

**Way 2 — lower the census, keep the entry:**

```
  [1] FAIL  the registry names tape that is no longer in the tree: shard_too_thin.
  [4] FAIL  the registry covers audit items (19, 20, 21, 22, 50), but the
        2026-08-24 audit recorded (19, 21, 22, 50) as undeclared tape. An entry
        was dropped or renumbered.
  RED LEGS: 2 (by design), 3, 4          EXIT=2
```

**Way 3 — both: drop the entry AND lower the count to 4.** Internally
consistent, and still red, because the third book is a dated measurement:

```
  [4] FAIL  THE CENSUS CANNOT SHRINK QUIETLY
        research/2026-08-24-law1-audit.md now reports 5 pieces of tape
        undeclared; this gate is pinned to 4. One of the two was edited. The
        audit is the dated record — if it grew, register the new items here; if
        it shrank, say which piece was closed and how.
  RED LEGS: 2 (by design), 3, 4          EXIT=2
```

The fourth road — editing `research/2026-08-24-law1-audit.md` down to 4 —
falsifies a dated finding, and leg 4's own message forbids it.

**And the census shrank by name.** Under way 3, leg 3's header went from *"5 of
the 5 pieces of tape the 2026-08-24 audit found undeclared"* to **"4 of the 4"**,
with item 20 gone from the list entirely. The property that makes leg 3
unsatisfiable by silence — the audited symbols being written down — was being
deleted by the act of fixing one of them.

---

## 2. What proves a piece of tape is closed

Not "somebody moved it to a list." That is the registry-satisfied-by-
declaration attack this gate already defeats for live tape, and closed tape
gets the same rigour. **Four things, computed on every run, none asserted:**

**a. The text is gone — the entry's own predicate, still running.**
`CLOSED_TAPE` holds `ClosedTape(Tape(...), …)`: the live entry is **moved
verbatim**, not retyped. `find`, `rel`, `home`, `marker_home`, `audit_item` and
`ledger_needle` are delegated to the wrapped `Tape`, so a closure cannot
quietly carry a different needle than the entry it replaced — there is only one
needle. Leg 6 re-runs it against the shipped organs every run, forever.

**b. The marker is gone — checked, not assumed.** A closed entry claims **no**
marker line. Leg 1's `claimed` set is built from `KNOWN_TAPE` alone, so a
`TAPE:` comment left behind at the old site lands as an **orphan** — the same
red as tape that shipped with no expiry at all. Letting a closed entry keep its
claim would have given the abandoned marker a permanent hiding place.

**c. The replacement leg exists.** `replaced_by` must be a path in the tree and
`proves` a symbol inside it. This proves the leg **exists and is named what the
entry says**; it does not prove the leg tests the right thing, and leg 6's own
failure message says so out loud rather than implying otherwise.

**d. The books moved, in all three.** Leg 5 requires the `[tape:…]` bullet to
have **left** `## Known standing tape` and to be in `## Retired tape` naming
`closed_by`; a retired bullet with no `CLOSED_TAPE` entry is red in the other
direction, the same shape as the standing-ledger check one section up. The
retired heading must be `##`, not `###` — a subsection would leave every
retired bullet inside the standing section.

`closed_by` is checked for **shape only** and is deliberately not resolved
against git. This repo runs two worktrees on divergent lineages; an id that
resolves in one does not resolve in the other, and a gate red on that would be
wrong-firing in half the repository. It is provenance for a human, and the
gate's footer says it is unverified.

### Walked, not argued

Following leg 1's new instruction on the mirror — move the entry, move the
bullet, touch no number — the audit document stayed **byte-identical** and:

```
  [1] PASS  read 621 of 1486 files …; 2 marker(s), 4 registered, 1 closed,
            none orphaned, none moved, none stale
  [2] RED   4 piece(s) of tape are still load-bearing   (by design)
  [3] FAIL  4 of the 5 pieces of tape the 2026-08-24 audit found undeclared
            are still undeclared                        (the other four)
  [4] PASS  census intact (5 audited items: 4 open, 1 closed; 4 + 1 entries
            registered); research/2026-08-24-law1-audit.md agrees:
            5 undeclared, 0 properly declared
  [5] PASS  4 standing and 1 retired, and HARNESS-LAWS.md's ledger names every
            one — and names nothing these registers do not
  [6] PASS  1 closed piece(s), still gone from brain/, …: shard_too_thin
            (closed by 0a9e8d13, replacement pinned in overnight/tejas_gate.py)
  RED LEGS: 2 (by design), 3
```

Leg 3 still counts **five**. Leg 4 still agrees with the doc's **5**. The only
reds are the pre-existing ones.

---

## 3. How a resurrection is caught

If the code is reverted and the tape returns, an entry sitting in a list and
nothing else would say nothing. That is the same class as the `MOVED` bug this
gate already had, where a refactor retired live tape from two legs at once.

**Leg 6, `CLOSED TAPE STAYS CLOSED`, is not red by design.** A resurrection is
`exit 2` and changes the fingerprint from `RED LEGS: 2 (by design), 3` to
`RED LEGS: 2 (by design), 3, 6`. It is deliberately **not** leg 2's business:
leg 2 is red by design, and a real failure arriving inside a permanent red is
the I4 hole this gate was already fixed for once.

Three revert shapes, all run at full scale against the mirror:

| shape | what fires |
|---|---|
| **A** — the function comes back where it was, `TAPE:` comment and all | leg 1 (orphan marker), leg 3 (no longer gone), **leg 6**. `RED LEGS: 1, 2 (by design), 3, 6` |
| **B** — a partial revert brings the code back **without** the comment | leg 1 **passes**; leg 3 and **leg 6** fire. `RED LEGS: 2 (by design), 3, 6` |
| **C** — it lands in a different file (`brain/shards.py`) | **leg 6**, naming `brain/shards.py:5`. `sites_anywhere` is deliberately not written in terms of a home path |

Removing it again returns the gate to green for that entry — the round trip
works in both directions, which is the part a one-way check never proves.

**The route-around was tested too.** Faced with leg 6 red, delete the
`CLOSED_TAPE` entry:

```
  [4] FAIL  the two registers together cover audit items (19, 21, 22, 50), but
        the 2026-08-24 audit recorded (19, 20, 21, 22, 50) …
  [5] FAIL  the `## Retired tape` section of HARNESS-LAWS.md claims tape was
        retired that CLOSED_TAPE has never heard of: [tape:shard_too_thin].
  RED LEGS: 2 (by design), 3, 4, 5
```

The census still cannot shrink. Closing gave it somewhere to shrink **to** that
is still counted, not a way out.

Beyond a revert, leg 6 also catches a closure that **never happened** (an entry
moved into `CLOSED_TAPE` with nothing deleted — same predicate, same red), an
entry present in **both** registers, a closure with a placeholder commit, and a
`replaced_by` that is not in the tree or does not define `proves`.

---

## 4. How the dated audit number reconciles

`research/2026-08-24-law1-audit.md` says **5 undeclared, 0 properly declared**.
That is a measurement of 2026-08-24, and it never changes, because nothing
about 2026-08-24 changes. `AUDIT_UNDECLARED = (19, 20, 21, 22, 50)` and
`AUDIT_UNDECLARED_COUNT = 5` are copies of it and never change either.

**What changes is the partition.** The dated five is a fixed set; the present
state splits it into OPEN (`KNOWN_TAPE`) and CLOSED (`CLOSED_TAPE`). Leg 4
checks the split is exact — union equals the dated tuple, no item in both, none
lost — and reports it as `5 audited items: 4 open, 1 closed`. Legs 3 and 6
count both registers too.

So the fixed historical number is a **total that is conserved**; closure moves
an item across the line. The document is never edited, the count is never
lowered, and the census still cannot be shortened quietly — the tripwire is
unchanged, it simply now distinguishes *moved* from *deleted*.

`AUDIT_DECLARED_COUNT` stays 0 for the same reason: on 2026-08-24 zero pieces
were properly declared, and declaring the four open ones tomorrow does not make
that sentence less true.

One consequence worth stating: the gate's old exit-0 prose told you to *"delete
this gate's registry"* once the tape was gone. With `CLOSED_TAPE` that advice
was backwards — deleting the registry deletes the only thing that would catch a
revert. The prose now says the opposite, and `exit 0` means "no **live** tape".

---

## 5. Watching it fail

Twenty fail-open or wrong-fire rules were found in this repo the night before
this, several inside gates written to catch exactly that, and this gate has had
two of its own. So every mechanism was broken on purpose and watched:

| mutation | tests that went red |
|---|---|
| `sites_anywhere` always returns `[]` (closure never checked) | 5, incl. all three resurrection tests |
| leg 6 skips its reach check | `test_leg6_refuses_to_vouch_when_the_scan_is_not_intact` |
| closed entries claim their marker line | `…_orphan_after_closure`, `…the_road_that_now_exists` |
| leg 3 reads `KNOWN_TAPE` only | 4, incl. `test_closing_cannot_shrink_the_named_census` |
| leg 4 counts only the open register | `…counts_both_registers_against_the_dated_number` |
| leg 5 stops requiring the bullet to move | `…still_listed_as_standing`, `…top_level_section` |
| leg 6 declared red by design | `test_i4_only_leg_2_is_red_by_design` |

**A fail-open in the new leg, found before it shipped.** `sites_anywhere` over
an empty set of organs returns nothing, nothing reads as GONE, and every closed
entry would go green having opened zero files — and `scan_reach()` would not
catch it, because an empty scope has no missing organ, no hollow one and no
unclassified file. `dirs=()` is now red, with a test.

**A second one, closed by design rather than found late.** "The text is nowhere
in the shipped organs" is a statement about files that were **opened**. Leg 1
checks reach, but leg 1 is a different leg: if it went red for reach reasons,
leg 6 would still have reported "still closed" — I2's disease, a message
asserting what it did not check. Leg 6 re-checks reach itself, and only when
`CLOSED_TAPE` is non-empty, so an empty register does not double every reach
complaint into two red legs.

**And the empty-register message.** With nothing closed, leg 6 says *"CLOSED_TAPE
is empty — no tape has been closed yet, so this leg has checked nothing and is
vouching for nothing."* It never says "all closed tape is still closed", which
is the sentence leg 4 used to print about an audit row it had not read.

**Wrong-fire, tested in the other direction:** `proof/outcome_rate.py` names
`shard_too_thin` in five comments and a dict key. The needle is the tape's own
text (`def shard_too_thin(`), not the name, so prose that merely mentions a
closed piece does not resurrect it. A gate that fired on the name would make
tape un-closeable.

Tests: **70 → 116** in `tests/test_tape_gate.py`. Full suite 1696 passing.
`tape_gate` still exit 2, `RED LEGS: 2 (by design), 3` — unchanged.
`CLOSED_TAPE` ships **empty**: the mechanism lands before the first closure so
that the retirement diff has a reviewed road to land into, rather than
inventing one in the same commit as the thing that needs it.

---

## 6. Reported, not fixed — `app/ios/Tests/run_build_number_tests.sh`

Another agent holds `app/ios/**`. **This is a second instance of the same
disease: a check that cannot express the difference between two outcomes, and
so vouches for both.**

`app/ios/Tests/run_build_number_tests.sh:110` tests **inequality**, not an
increase:

```sh
if [ "$version" != "$was" ]; then
    echo "build $version, bumped from $was and not yet committed"
    exit 0
fi
```

`$version` is the working tree's `CURRENT_PROJECT_VERSION`; `$was` is its value
at the commit where it last changed. A **downgrade satisfies `!=` exactly as
well as a bump**, and the message it prints is word-for-word the one a
legitimate bump prints. Reproduced in a throwaway repo (build 79 → 80 in
history, working tree back at 79):

```
=== working tree takes the OLDER project.yml (uncommitted) ===
build 79, bumped from 80 and not yet committed
EXIT=0
=== control: a genuine forward bump ===
build 81, bumped from 80 and not yet committed
EXIT=0
```

Nothing distinguishes them — not the exit code, not the text.

**A second, worse variant, also reproduced.** If the downgrade is *committed*,
the `-G` pickaxe at `:95` finds the **downgrade commit itself** as "the commit
where the number last changed", so `$was == $version`, leg 3 compares the source
against that commit, finds no change, and reports:

```
build 79, and the iOS source has not moved since it was set
EXIT=0
```

The number is now permanently below one that already shipped, and the check is
actively vouching for it. This survives the commit, so it is the more dangerous
of the two.

Reachable on a revert, a rebase, a merge taking the older file, or a stash pop
— and this repo has two worktrees on divergent lineages. App Store Connect
refuses a re-used build number, which is where it would surface: at upload,
days after the tree it should have described. That is the exact failure the
script's own header says it exists to prevent.

Third, smaller: `$version` is validated as a plain integer at `:37-46`; `$was`
is **not**. An unreadable historical value (empty, or a line the `sed` did not
match) makes `!=` true and prints "bumped from …", exit 0.

Not fixed here — `app/ios/Tests/` belongs to another agent tonight.

---

## 7. What the gate still cannot see

Stated so green is never read as safe:

- **Tape nobody marked, nobody registered, and that is not one of the audited
  five.** Unchanged, and no deterministic gate finds it — that is a reading of
  what code MEANS (Law 1, Law 5). The mechanism is an audit; leg 4 pins the
  last one.
- **The same DECISION coming back under a different name.** Leg 6 watches one
  string. Reintroduce `shard_too_thin`'s word count as `too_short()` and every
  book agrees and every book is wrong.
- **A closure whose `find` was weakened in the same diff that deleted the
  marker.** Point the needle at text the tree never held and leg 6 reads GONE.
  Leaving the `TAPE:` comment behind is caught — it becomes an orphan in leg 1,
  and there is a test for it. Evading *both* means deleting a Law-2 marker from
  shipped code in a diff with a name on it, and what remains is then ordinary
  unmarked tape — the blind spot already stated above, not a new one this state
  opened.
- **Whether the replacement leg tests the right thing.** Leg 6 checks the file
  exists and defines the symbol. Whether that symbol pins the behaviour the
  tape provided is a review's job.
- **Whether `closed_by` is a real commit.** Shape only, on purpose (§2).
- **Leg 1 has the twin of the empty-scope hole I closed in leg 6.** Called with
  `dirs=()`, `scan_reach` reports no missing organ, no hollow one and no
  unclassified file, and leg 1 passes printing "read 0 of 0 files". `run()`
  never does this, so it is latent rather than live; it is left for whoever
  next opens leg 1, noted here so it is not rediscovered from scratch.
- **Tape in `overnight/` and `tests/`.** Still excluded, still printed in the
  gate's own output.
