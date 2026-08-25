# The fence gets a way down — LIBRARY 1b criticals, answered

Review answered: `.superpowers/sdd/library-1b-criticals.md` (review of `1a20dea2`).
Three commits landed in `brain/` after the reviewed one (`82e9dc31`, `99d0b7b9`,
`32515a12`), so **every reference below is re-pinned by symbol name**, with the
line numbers they carried at the time of writing.

Scope kept: `brain/` and `tests/` only. Files touched — `brain/orchestrator.py`,
`brain/memory.py`, `brain/anticipy_core.py`, `tests/test_memory_knows_who_spoke.py`.

---

## C1 — one absent `owner_is_party` answer stuck the mark forever

### Reproduced first

`owner_is_party()` returned a bare `bool`, and **every** failure came back as the
same `False` a model saying "no, he is not a party" comes back as: no goal, no
llm, `live` false, and `except Exception: return False` — a timeout, a 5xx, a
rate limit, an unparseable reply. Driven against a real `Memory` on the recorded
dinner line, with a live model whose first call raises `TimeoutError` and whose
second works:

```
hearing 1 (party call FAILED -> False):  owes = other
hearing 2 (party call WORKS  -> True):   owes = other
hearing 3 (triage itself says 'owner'):  owes = other
briefing sees: other
```

One flaky call, and `BRIEFING_SYSTEM` — instructed *"never say they promised
it"* — is handed `owes: "other"` for the owner's own dinner, forever, because
nothing anywhere closes a guest-attributed commitment.

### What I built, and why both halves

The brief said: build the named correction method the docstring promises, **or**
make the failure path not write — and argue which. **Both, because they answer
two different questions**, and shipping either alone leaves the disease:

- **The failure path must not write**, because the write's own stated rule is
  that it *"takes the HIGHER of the two bars"* — a briefing lie about the owner's
  own life outranks a lost clock job. **A call that failed does not clear a bar.**
  The code had already made this decision; the bug was that it could not
  implement it, because a bool cannot tell a failure from a "no".
- **The named method must exist anyway**, because *permanence* is a separate
  disease with other triggers that not-writing does not touch: the **inert
  path** (no live model → `PARTY_UNASKED` → triage's verdict is written, and
  triage is measured wrong six for six in exactly this direction), an empty
  `goal`, and a live model that simply answers wrong. Every one of those still
  wrote a mark nothing could remove. And a decision living only in a docstring
  is what Law 4 exists to stop.

**`party_verdict()`** (`brain/orchestrator.py:1314`) replaces `owner_is_party`
and answers with four states, not two (`:1308-1311`):

| state | means | what the write does |
|---|---|---|
| `PARTY_YES` | model said yes | do not write; **withdraw** any mark an earlier hearing left |
| `PARTY_NO` | model said no | write `"other"` — unchanged |
| `PARTY_UNASKED` | nothing to ask: no goal, no llm, dead model, **or an explicit line** | write `"other"` — the documented inert mode, unchanged |
| `PARTY_UNANSWERED` | a **live** model was asked and no readable answer came back | **write nothing, withdraw nothing** |

`PARTY_UNASKED` and `PARTY_UNANSWERED` are deliberately not the same state:
"there is no model to ask" is the documented inert mode and must not change,
while "the model was asked and blew up" is a transient fault that must never be
carved into the store.

**`Memory.withdraw_attribution(commitment_id, reason)`** (`brain/memory.py:800`)
is the one named erase. What makes it not the erase that was removed is not the
SQL — it is the gate and the ledger:

- `reason` is **required and recorded**. A reasonless correction is the falsy
  argument under a new name, reachable from any path holding an empty variable.
- The withdrawal is **kept** (`owes_withdrawn`: reason + ts), so "a verdict was
  made and taken back" stays distinguishable from "nobody ever judged this".
- Its only caller is a positive `PARTY_YES` — never triage's second opinion,
  never absence, never a failed call. `hear()` holds the gate, the store holds
  the ledger.
- It returns whether anything was actually removed, so a caller cannot read
  "there was nothing to withdraw" as "the withdrawal worked".

### After

The failure no longer writes:

```
hear: the reversal went unanswered — leaving the attribution exactly as it stands
hearing 1 (party call FAILED):           owes = None
hearing 2 (party call WORKS  -> True):   owes = None
hearing 3 (triage itself says 'owner'):  owes = None
briefing sees: None
```

And the fence can be **lowered** — a mark written by the inert path, then
withdrawn by a working reversal:

```
hearing 1 (no live model to ask):        owes = other
hear: withdrew an attribution the reversal reversed
hearing 2 (live reversal says 'party'):  owes = None
the store kept WHY: the reversal, asked on its own, says the owner is a party
                    to this plan: "Let's do dinner tomorrow, I'll text you a time."
briefing sees: None
```

### Named residual

On `PARTY_UNANSWERED`, a guest promise that no earlier hearing marked is left
unmarked, so a later `clock_tick` could prepare work from it. That is the
cheaper of the two harms this block already ranked, and it is bounded:
`hear()` still refuses to act on the line (the routing branch reads
`owner_is_a_party`, which `PARTY_UNANSWERED` leaves `False`), and the next
hearing of the same sentence re-asks. The alternative — writing — is the
unbounded, unrecoverable harm stated to the owner as fact about his own life.

A second residual, kept from the old doctrine rather than introduced: if triage
stops saying `"other"`, the reversal is not asked and a stuck mark is not
re-examined. That is deliberate (triage's second opinion may not drop a fence),
and it does not bite the C1 scenario, where triage is consistently wrong in the
`"other"` direction and so keeps re-asking.

---

## I2 — the report said explicit lines keep the mark; the code withdrew it

### Reproduced

`routing_asks_it` excluded explicit lines, but the write's gate did not, so a
commitment on an **explicit** line still paid for a party call and a `True`
suppressed the mark:

```
explicit=True  owner_is_party=True  -> owes=None    party calls=1
explicit=True  owner_is_party=False -> owes='other' party calls=1
```

This contradicted the routing branch's own stated principle — *"he is the one
asking, and no second opinion overrides him"*. Failure scenario: he texts her
*"Bob said he'll send the deck tomorrow — keep an eye on it."* Triage is **right**
that Bob owes it. The reversal, shown only the line and the task, says True
because it is his deck, the mark is suppressed, and that night the clock mints a
browser job to draft the deck email — through the one path the code says must
not be second-guessed.

### Fixed

`asks_the_reversal` (`brain/anticipy_core.py:1648`) carries `not explicit`, so an
explicit line yields `PARTY_UNASKED` and triage's verdict stands as written.

```
explicit=True  party=yes -> owes='other'  party calls=0
explicit=True  party=no  -> owes='other'  party calls=0
```

Zero model calls on explicit lines now, which is also strictly cheaper.

---

## I3 — the `ignore` leg had no negative control

### Reproduced

`test_an_ignore_verdict_asks_the_reversal_too` asserted only that the mark was
*absent* — equally true if the write never fires for `ignore` at all. Its `say`
sibling has a control; this one did not. Mutation applied to the write gate — an
`ignore`-routed guest promise is never marked:

```
tests/test_memory_knows_who_spoke.py .......  35 passed
full suite: 1268 passed, 2 failed (both other agents' files, neither mine)
```

**The mutation survived.** That matters because `ignore` is the lane where
overheard guest speech actually lands: `ingest()` has already created the
commitment, the mark is never written, and the clock mints the job — the original
Critical's outcome on its busiest path.

### Fixed

`test_an_ignore_verdict_still_marks_a_promise_that_really_is_the_guests` —
`decision="ignore"`, `party=PARTY_NO`, asserts `owes == "other"`. The same
mutation now goes red.

---

## I4 — the unnamed branch effectively never fenced on a real store

### Reproduced — two distinct defects

**(a) A malformed `loop_ids` was discarded silently.** `raw.get("loop_ids", [])`
plus the `isdigit()` filter turned `[3.0]` or `["seven"]` into `[]` — the exact
value a model that named nothing produces — dropping the goal into the unnamed
branch, whose `all()` only fences when *every* open loop in the store is somebody
else's. Any owner who uses the product has one of his own. On the ordinary
two-loop store (one his, one a guest's), asking for a guest-derived goal:

```
loop_ids omitted         -> goal='draft the pitch deck email' queued=[...]
loop_ids: [3.0] (float)  -> goal='draft the pitch deck email' queued=[...]
loop_ids: ['seven']      -> goal='draft the pitch deck email' queued=[...]
loop_ids: [7] (named)    -> goal=None                         queued=[]
```

**(b) The model was shown `fresh[:10]`, while both checks ran over all of
`fresh`.** A loop the model never saw voted on whether the goal was somebody
else's, and on whether any quote licensed preparing work at all:

```
A) 10 guest loops shown + 1 of his beyond the cap -> goal='draft the pitch deck email' queued=[...]
B) 10 bland  loops shown + 1 authored beyond cap  -> goal='draft the pitch deck email' queued=[...]
```

### Fixed

- `shown = fresh[:10]` (`brain/anticipy_core.py:3579`) is one name used by the
  payload **and** by `selected`, so the set the model reasons over and the set
  the fence reasons over cannot drift apart again.
- An unreadable `loop_ids` (`:3624`) now **drops the goal** rather than guessing;
  the `say` survives. This is not a stricter operator over the store — it fences
  on our own inability to read the answer, not on other loops' verdicts, so it
  cannot resurrect "one guest promise disables every goal every night forever".
- `CLOCK_SYSTEM` now **requires** `loop_ids` when the model sets a goal, which is
  the fix the code's own comment named as the only way to close the residual.

```
A) 10 guest loops shown + 1 of his beyond the cap -> goal=None queued=[]
B) 10 bland  loops shown + 1 authored beyond cap  -> goal=None queued=[]
loop_ids: [3.0]  -> goal=None ("loop_ids named loops I cannot read")
loop_ids: ['seven'] -> goal=None
loop_ids omitted -> unchanged: his own goal is still prepared
```

### Deliberately NOT changed, and why

`named` (`:3716`) still reads `fresh`, not `shown`. I tried narrowing it and
**reverted it**: `named` feeds `any()`, a ceiling, so widening its input can only
*add* a refusal — the change is unfalsifiable in the fail-open direction, no
check could ever prove it, and shipping a change no check can catch is the exact
thing this wave exists to stop. The asymmetry is now documented at the line.

The residual the reviewer named stands and is now measured: with `loop_ids`
omitted and a mixed store, a guest-derived goal can still get through the unnamed
branch. Closing it needs the model to name loops — hence the prompt change,
whose effect **waits on LIVE**.

---

## Every check, with the mutation that proves it

Fifteen mutations run, **zero survivors**. Harness:
`scratchpad/mutate.py` — applies one mutation, runs the file, restores.

| # | Mutation | Killed by |
|---|---|---|
| C1-a | `PARTY_UNANSWERED` falls through to the write | `test_a_reversal_that_could_not_be_answered_writes_no_verdict` |
| C1-b | the `PARTY_YES` branch withdraws nothing | `..._can_be_withdrawn_later`, `..._is_recorded_on_the_promise...`, `test_the_clock_starts_working_again...` |
| C1-c | `withdraw_attribution` accepts an empty reason | `test_withdrawing_an_attribution_needs_a_reason` |
| C1-d | `withdraw_attribution` always claims success | `test_withdrawing_reports_whether_it_actually_removed_anything` |
| C1-e | a failed call withdraws too | `test_a_failed_reversal_may_not_lower_a_fence_either` |
| C1-f | `party_verdict` collapses `UNANSWERED` into `NO` (**the original bug**) | `test_a_party_call_that_raises_is_unanswered_not_a_no`, `..._reply_that_cannot_be_read...` |
| C1-g | an unreadable reply is read as a no | `test_a_reply_that_cannot_be_read_is_unanswered_not_a_no` |
| C1-h | a dead model is treated as a failed call | `test_nothing_to_ask_is_a_different_state_from_a_call_that_failed` |
| C1-i | `PARTY_UNANSWERED` aliased onto `PARTY_NO` | 8 legs, incl. `test_the_four_party_states_are_four_distinct_values` |
| I2 | the write second-guesses explicit lines again | `test_an_explicit_line_is_not_second_guessed_by_the_reversal`, `..._does_not_even_pay_for_the_reversal` |
| I3 | an `ignore`-routed guest promise is never marked | `test_an_ignore_verdict_still_marks_a_promise_that_really_is_the_guests` |
| I4-a2 | the authority check ranges over `fresh` again | `test_the_not_his_fence_only_ranges_over_the_loops_the_model_was_shown`, `test_a_loop_the_model_never_saw_cannot_authorise_preparing_work` |
| I4-b | an unreadable `loop_ids` is silently discarded again | `test_loop_ids_that_cannot_be_read_drop_the_goal_instead_of_guessing`, `test_an_unreadable_loop_ids_is_not_read_as_naming_nothing` |
| I4-c | the prompt stops requiring `loop_ids` | `test_the_clock_prompt_requires_the_loops_a_goal_rests_on` |
| MNR | `_upsert_node` rewrites `attrs` on re-ingest | `test_a_withdrawal_survives_the_same_sentence_being_heard_again` + 5 others |

### Two of my own checks were fail-open on the first pass

Exactly the disease the brief warned about, found in my own work by running the
mutations rather than trusting the green:

1. **`party_verdict` had no test at all.** Every `hear()` leg scripts
   `core.party_verdict`, so not one of them ever ran the real function — and the
   entire C1 fix rests on it answering `PARTY_UNANSWERED` rather than
   `PARTY_NO`. Mutation C1-f, *which is literally the original bug*, left every
   `hear()` leg green. Fixed by testing the root at the root (`_PartyLLM`, six
   new legs) plus `test_hear_calls_the_real_reversal_and_not_a_stale_alias`,
   which pins that the monkeypatch target is the real function.
2. **`test_loop_ids_that_cannot_be_read...` included `"7"`**, which coerces to a
   readable `[7]` — the goal was being dropped by the *not-his* fence, not the
   unreadable fence. The assertion passed while testing nothing. Every shape in
   that loop is now unreadable for the right reason, and the store's readable id
   is the **owner's**, so a shape that leaked through as readable turns the leg
   red instead of green.

### Must-not-regress, re-verified

`_upsert_node` still updates only `last_seen_ts` and never rewrites `attrs`, so
re-`ingest()` of the same commitment text cannot clobber `owes`. The reviewer
verified this by reading and nothing pinned it; it is now load-bearing for the
`owes_withdrawn` record too, so it is pinned by
`test_a_withdrawal_survives_the_same_sentence_being_heard_again` and
mutation-proven.

---

## HARNESS-LAW 1

Nothing added here decides meaning from a pattern. The four-state verdict is a
model's answer; `withdraw_attribution` compares a stored label; the `isdigit()`
filter parses an **id field**, not words; the clock prompt change asks the model
for more, not less.

~~**`_CLOCK_ACTION_SOURCE_RE` (`brain/anticipy_core.py:937`) remains a known,
unregistered Law-1 violation — this is the fourth wave to flag it.**~~
**CLOSED 2026-08-24, the wave after this one** (research/2026-08-24-clock-verb-list.md).
The regex is deleted; the meaning question now goes to
`orchestrator.work_is_licensed()`, a four-state model verdict `clock_tick()`
compares. The dependency this section recorded was real and turned out to be
LOAD-BEARING FOR A REASON NOBODY HAD NAMED: on a hallucinated loop id it was not
the regex doing the work at all, it was `any()` over an empty `selected`. That
half was mechanism wearing a meaning check's clothes, and it is now its own
explicit guard with its own message — mutation-proven, because deleting it while
the licence backstop stood left every test in the tree green.

---

## Law 3 — what waits on LIVE

Repo-green is not done. Nothing below is verified against LIVE:

1. **`CLOCK_SYSTEM` requiring `loop_ids`.** Whether the model actually emits the
   field when it sets a goal is unknowable from the repo. Until measured live,
   the unnamed branch's residual is unchanged in practice. This is the only
   change here whose *effect* is unverifiable repo-side.
2. **`party_verdict`'s failure taxonomy against a real provider.** The
   exception path is tested with synthetic raises. Which failures a live gateway
   actually produces — and whether any of them return a parseable body that
   reads as a verdict — has not been observed.
3. **The recovery actually firing in production.** It needs a second hearing of
   the same sentence with a live model. Not demonstrated live.
4. **No deploy, no keyed eval, no live model call was made in this work.**
   Per the live-deploy rule, `railway up` reports success while failing, so none
   of this is in prod until an `is_it_live.py`-style check says so.

---

## Scoreboards

- `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q --ignore=tests/test_day_zero_oracle.py -p no:cacheprovider`
  → **1393 passed, 4 failed**. All four are in files other agents are editing
  live (`tests/test_earls_live_failures.py` → `extension/agent_loop.js`,
  `tests/test_engine_or_audio.py` → `proof/engine_or_audio.py`,
  `tests/test_tape_gate.py` → `overnight/tape_gate.py`). None are mine;
  `test_earls_live_failures` was already failing at baseline before I began.
- `tests/test_memory_knows_who_spoke.py` → **57 passed** (was 35). Stress-run 15×
  standalone and 12× inside the full suite: **zero failures**, no order
  dependence.
- `python3 overnight/tejas_gate.py` → **8/8 PASS**.
- `overnight/tape_gate.py` and `overnight/consolidation_gate.py` → RED, by
  design, unchanged by this work.
