# LIBRARY — facts that expire

**Card:** LIBRARY — "memory that lasts a life: finder + family tree + librarian,
**facts that expire**, origins that gate action."
**Status of the card's other three parts, verified 2026-08-25, not assumed:**

| Part | State | Evidence |
|---|---|---|
| finder | built | FTS5 over ALL episodes + LIKE fallback, token seeding (`memory.py` recall) |
| family tree | built | nodes/edges, 2-hop walk |
| librarian (retirement) | built | `82e9dc31`, 44 tests in `test_memory_supersession.py` |
| origins gate action | built | `anticipy_core.py:535`, `memory.py:480`, `memory.py:1138`; 80 tests |
| **facts that expire** | **MISSING** | `grep -cE "valid_until\|expires_at\|expiry\|until_ts" brain/memory.py` -> **0** |

## 1. Expiry is not decay, and the difference is the whole card

`_decay` exists (`memory.py:451`): `0.5 ** (age_days / half_life)`, half-life by
kind — `stable: None` (never), `situation: 30.0`. That is **salience sinking**.
The fact stays true; it just stops shouting.

Expiry is a different claim: **the fact stops being true.** "Dana is in Montreal
Friday to Sunday" is not a fact that should quietly get less prominent on Monday
— it is false on Monday. Decay can never express that, because a decayed fact is
still eligible to be recalled, still eligible to fill a gap, just lower down.

Today every time-bounded fact in the store is treated as a permanent fact with a
sinking score. That is why this is on the card.

## 2. The insight the naive design misses

**An expiring fact is usually an ERRAND, not a deletion.**

Brief moment 8: *"You mumble 'ugh, the parking permit expires this month' while
grabbing keys. → One text that afternoon with the renewal page already found."*

The permit expiring is not a row to sweep. It is the **trigger**. A design that
only removes expired rows would silently delete the single most actionable fact
in the store on the day it mattered most. Any implementation that cannot tell
"this expired, forget it" from "this expired, that is the errand" has failed the
card even with green tests.

So expiry has two outcomes, and the fact itself carries which:
- **lapses** — the fact simply stops being true (Dana is home again on Monday).
- **falls due** — the horizon IS the deadline, and reaching it is a reason to act
  (permit, passport, prescription, registration, warranty).

## 3. Where the horizon comes from — Law 1

**A model decides, at extraction. Never a regex, never a date parser on the raw
sentence, never a word list of "expires/renew/until".**

Deciding that "she's in Montreal till Sunday" carries a validity horizon — and
that "the wifi is trout2024" does not — is a judgement about what the words MEAN.
HARNESS-LAWS Law 1 puts that with the model. `EXTRACT_SYSTEM` already returns
structured fields and `_FACT_KINDS` already refuses values it does not recognise
(`memory.py:376-379`); extend that shape, do not bolt on a parser.

The honesty wall applies as everywhere else here: **no verdict is not an expiry.**
A model that returns nothing, garbage, or an unparseable horizon leaves the fact
permanent. Guessing a horizon is strictly worse than having none, because it
makes a true fact vanish.

## 4. What happens at the horizon

Reuse the retirement machinery from `82e9dc31` rather than inventing a second
lifecycle. A fact that expires is **retired, not deleted** — same rules, already
tested: kept for audit, absent from the profile, unable to settle a gap in an
approved plan, and its wrapper text must go in `text` not `fact` so it cannot
become searchable (the bug `88967d73` just fixed — do not reopen it).

The distinction from supersession is the REASON, and the reason is worth storing:
retired-by-contradiction ("we broke up") and retired-by-horizon ("that Friday
passed") answer different questions when a human asks why she stopped believing
something.

## 5. What must not happen

- **No sweep job that deletes.** Nothing in this store deletes; that is the
  standing rule and the audit trail depends on it.
- **No expiry inferred from decay.** A 30-day half-life is not a 30-day horizon.
  Collapsing them would expire every `situation` fact on a schedule nobody stated.
- **No horizon on a `stable` fact.** If the model says a birthday expires, that is
  no verdict, not an expiry.
- **The action lane must not act on an expired fact** — already guaranteed by the
  retirement WHERE clause, but it needs its own test here rather than inheritance
  by assumption.

## 6. The gate leg

It must be unable to pass on a mock: a fact with a horizon in the past is absent
from `recall`, absent from `fill_gaps_from_memory`, present in the audit read,
and — for a `falls due` fact — has produced exactly one errand and not two on the
day it fell due. A leg that only checks the row is gone would pass while moment 8
silently broke.

## 7. Handed back

- Does a `falls due` fact raise its errand through the clock lane
  (`_CLOCK_ACTION_SOURCE_RE` territory, `anticipy_core.py`) or through
  consolidation? This crosses out of `memory.py` and needs the owner of that lane.
- Should a horizon be extendable by a later mention ("permit's renewed till
  March") — presumably yes, via the existing `_merge_fact` update path, but the
  interaction with retirement-by-contradiction is unproven.
- Timezone: horizons are dates in the owner's life, and `CLOCK_TZ` is per-owner
  and hot-refreshed. A UTC horizon would expire facts up to a day early for some
  owners.
