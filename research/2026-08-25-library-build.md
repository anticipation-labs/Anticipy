# LIBRARY — what the card asked for, what was already there, and the one thing that was still broken

2026-08-25. Branch `jose_anticipy_system`. Owned paths only: `brain/memory.py`,
`tests/test_library_recall_matches_the_fact.py`.

**Nothing here is proven against LIVE.** The ears are dead — zero transcript rows
in ~31 hours, builds 76–80 delivered none — so no memory behaviour could be
exercised end to end today. Everything below is proven by tests against the repo
and by direct measurement, which under HARNESS-LAW 3 is a claim, not a fix.

---

## Headline: both jobs on the card were already built. The card's grep was a false negative.

The card said to build supersession, citing
`grep -c "superseded_by\|def supersede" brain/memory.py` → 0.

That grep returns 0 because **this store does not use those two names**. It calls
the pointer `retired_by` and the method `_supersede` (leading underscore, so
`def supersede` misses it). The feature landed on 2026-08-24:

| commit | what it did |
|---|---|
| `6ece3660` | *The ranker finally reads what the model bothered to judge* — wired confidence + kind into salience |
| `82e9dc31` | *"We broke up" now retires "partner is Sarah" instead of losing to it* — supersession |
| `1a20dea2`, `60ebd20f`, `659d5ac7` | the fence, its way down, and the sift fixes |

`tests/test_memory_supersession.py` already carries **44 legs** over it. I re-ran
them cold: green. I did not rebuild any of it.

### JOB 1 — supersession: built, and the three design questions are already settled in code

The card told me to settle and state three things. All three are answered in the
shipped implementation; I verified each by measurement, not by reading comments.

**1. What does a retired fact do to recall?** Two lanes, asymmetric, per
`docs/DECISIONS-2026-08-24.md` RULING 2 — retirement *gates action absolutely and
speech conditionally*.

- Action lane (`RETIRED_EXCLUDED`, the default): filtered in the **SQL WHERE
  clause** of `profile_facts`, so a dead row never reaches Python and cannot
  occupy a bounded-window slot. `recall()` additionally drops raw episodes a
  retired fact was distilled from — otherwise the dead address reached
  `filled[gap] → params[key] → a form the browser agent submits` as unmarked
  `heard: "..."` text.
- Speech lane (`RETIRED_QUOTED`, asked for by name): the fact comes back with its
  retirement **inside its own sentence** — `no longer true — retired 30 days ago:
  home is 4 Maple St` — built once in `_retired_note` so no sink can render it
  bare. It never leads and is dropped first from a short window.

**2. What if the superseding fact is itself later retired?** Measured — a
three-link chain resolves correctly and does not cycle:

```
partner is Dana   retired, retired_by → 2
partner is Priya  retired, retired_by → 3
broke up with Priya   live
live profile: ['broke up with Priya']
```

The chain is walkable backwards from the live row; nothing loops. It holds because
`_relate_fact` only ever puts **live** rows to the model, so a retired row can
never be the match a new fact retires.

**3. Can an untrusted source retire an owner-told fact?** No — GUARD 1 in
`_supersede`, the provenance fence. An untrusted row still *lands*; it just may
not kill anything. Otherwise "delete his boundary" becomes a thing a stranger
does by sending him an email. Spoken-retires-imported is allowed, which is the
intended direction (he moved; the calendar has not caught up).

I probed one case the tests did not name — **vetoing the replacement**. It behaves
correctly and does not resurrect the dead fact: the live row is deleted, the
retired row keeps `retired_ts` and a now-dangling `retired_by`, the live profile
goes empty, the quoted lane still carries the history. Defensible (a veto means
*stop deriving this*), and worth knowing the pointer can dangle.

### JOB 2 — the contradiction, settled empirically: **the docstring is right, the Brief is stale**

The card asked which of these is false. Measured, at equal importance and equal
age, varying only confidence:

```
imp=3 conf=0.95 sal=2.9775  drinks oat milk
imp=3 conf=0.30 sal=2.6850  prefers window seats     <- confidence reordered these
```

Confidence **is** read by the ranking. It enters via `_confidence_band` inside
`profile_facts`, and `profile_facts` is the single chokepoint — `recall`,
`_profile_recall` and `briefing_facts` all read the profile through it, and
nothing outside `brain/memory.py` calls it at all.

It is also correctly *bounded*, which is the part worth keeping. EXEMPLARS-A-LIFE:465
says "importance gates, confidence orders — confidence-first ranking buries the
shellfish allergy under the coffee order." Measured:

```
imp=5 conf=0.10 sal=4.3250  shellfish allergy
imp=4 conf=0.99 sal=3.9940  coffee order is flat white
```

The weakest belief at importance 5 still outranks the strongest at importance 4,
because confidence is compressed into `[0.85, 1]` — a floor above the tightest
adjacent-tier ratio (4/5). A plain `× confidence` would have inverted that pair.

**So the Brief's claim is now false, and §9 already knows it** — it reads
"Memory supersession — CLOSED 2026-08-25 … Both halves of this entry are now
false and it is kept, struck, so nobody rebuilds what exists."

**But §5 is still stale and is what sent this card out.** Around offset 101629,
`docs/BRIEF.html` still lists under *What is MISSING*: "no `superseded_by` pointer
on facts, no temporal validity intervals, no conflict resolution between two
contradicting facts (a new fact that contradicts an old one just coexists unless
word-overlap merges them)". The first and third clauses are false as of
`82e9dc31`. `docs/BRIEF.html` is **not mine to edit** under this card's ownership
fence, so I am reporting it rather than changing it. It should be struck the way
§9 was, or the next agent rebuilds supersession a third time.

The remaining true clause is **temporal validity intervals** — there is still no
`valid_from`/`valid_to`, only a retirement instant. "Priya was my partner *from
March to August*" is not expressible. Genuinely open.

---

## What I actually changed: relevance was scored on text the store wrote itself

The one real defect the adversarial pass found, and the only code I shipped.

`profile_facts` puts the **rendered** sentence in a row's `fact` key — for a
retired row that is the whole `no longer true — retired N days ago: …` wrapper.
`_profile_recall` then counted query-word matches **against that same key**. So
seven words the owner never said about the fact — *longer, true, retired, days,
ago, today, yesterday* — became matchable text on every retired row in the store,
permanently.

Measured against the shipped code:

```
store: "home is 4 Maple St"  retired by  "home is 18 Rowan Ave"
recall("is that still true", retired=RETIRED_QUOTED)

  sal=  0.000  known: home is 18 Rowan Ave                    <- padded, matched nothing
  sal=  4.700  no longer true — retired 2 days ago: home is 4 Maple St
```

`"is that still true"` reduces to `{"true"}` — *is*, *that* and *still* are all in
`_STOP`. **No fact in that store contains the word "true".** The dead row was the
only thing recall scored as relevant to the question, at 4.7, because it matched a
word this module's own renderer had put there.

**Honest bound on the blast radius:** the action lane filters retired rows in SQL,
so this could never reach a form the browser agent fills. It is a **speech-lane**
defect — the briefing, the SMS answer and triage context are the sinks that ask
for `RETIRED_QUOTED` by name, and they were handed a dead fact as the most
relevant thing in the store on a question it had nothing to do with. Ordering
harm is capped by the retired-last sort; the harm is *membership and score*.

**The fix** (two hunks, `brain/memory.py`): `profile_facts` now carries the stored
wording as a separate `text` key beside the rendered `fact`, and `_profile_recall`
counts relevance over `text`. Sinks divide by use — anything **shown to a model**
reads `fact`, so the retirement can never be dropped by accident; anything that
**searches** reads `text`.

**This is not a Law-1 fix and not a word list.** Nothing here decides what any
sentence means. The model still decides `replaces`; `_retired_note` still decides
the wording. This only says *which column* the count is taken over — the fact as
stored, not the presentation this module generated. Reading a score off your own
boilerplate is a column mix-up, not a judgement about meaning. **No tape, no
`TAPE:` comment needed, no new gate leg** (Law 2 not engaged).

### The test: `tests/test_library_recall_matches_the_fact.py`, 6 legs

The load-bearing one is `test_no_word_of_the_retirement_wrapper_ever_scores`. It
does **not** hard-code the seven words — it derives the wrapper's whole vocabulary
from `_retired_note` itself at three ages (it branches on *today* / *yesterday* /
*N days ago*), then asks each word as its own one-word question. Adding a word to
that sentence later **re-arms this test** instead of quietly reopening the hole.

Every leg was mutated in place and watched fail for the right reason:

| mutation | leg that went red |
|---|---|
| A — relevance reads `fact` again (the original bug) | the two wrapper legs, at sal 4.7 |
| B — dead facts never score at all (over-fixing) | `…the_question_really_is_about_still_scores`: `0.0 > 0.0` |
| C — `_retired_note` returns the bare fact | the `startswith("no longer true — retired")` assert |
| D — action lane stops filtering retired rows | `…the_action_lane_is_unchanged…` |
| E — the retirement is never written | 4 of 6, including the scenario guard |
| F — live facts stop scoring | `…a_live_fact_scores_exactly_as_it_did` |

**A process note, recorded because it nearly poisoned the results.** My first
mutation round restored with `git checkout -- brain/memory.py`, which reverted my
own *uncommitted* fix — so mutations B and C silently ran against unfixed code and
their "failures" proved nothing. I caught it because B produced byte-identical
output to A. Redone restoring from a `cp` backup, and the tree was confirmed
`diff`-identical to the fixed file afterwards. The briefing warns that
`git checkout` will not restore an untracked file; the symmetric trap is that it
*will* discard a tracked file's uncommitted fix.

---

## Test counts, honestly, at the moment of commit

- My file: **6 passed**.
- Memory-owned suites (8 files + mine): **175 passed**.
- Full suite: **1855 passed**, with these exclusions and caveats, none mine:
  - `tests/test_day_zero_oracle.py` — collection error, `ModuleNotFoundError: playwright`. Pre-existing.
  - `tests/test_shelf2_admissible.py` — collection error, `ADMITTED_ACT_TYPES` missing from `brain/workflow.py`.
  - `tests/test_research_shape_parity.py` — 5 failures on one run, **green on the next**.

The last two are **another agent editing `brain/workflow.py` and
`brain/research.py` in this same working tree while I ran**. `git status` showed
both modified and their test files untracked, and the research failures
disappeared between two consecutive runs. I did not touch those files. A full-suite
number taken from this tree today is a snapshot of a moving tree, and I would not
report it as a clean 1855 without that sentence attached.

---

## Left open

1. **Temporal validity intervals** — the last true clause of the Brief §5 entry.
   A retirement is an instant, not an interval; "partner from March to August"
   is not expressible.
2. **`docs/BRIEF.html` §5 is stale** and outside my ownership fence. Strike it the
   way §9 was struck.
3. **A dangling `retired_by`** after the replacement is vetoed. Harmless today
   (nothing dereferences it), worth knowing before anything starts to.
4. **Substring, not token, matching** in `_profile_recall`'s relevance count
   (`w in blob`) — "ago" matches "Chicago", "art" matches "partner". Pre-existing,
   untouched here, and a separate cleanup from the one this file fixes.
5. **Nothing above is live-proven.** The ears are dead; all of it waits on a
   working build.
