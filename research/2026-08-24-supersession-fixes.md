# Supersession — the three Criticals, and the sentence the commit shipped against itself

Review under fix: `.superpowers/sdd/supersession-criticals.md` (of `82e9dc31`).
Branch `jose_anticipy_system`. Scope: `brain/` and `tests/` only.

`brain/` had moved since the review: `1fe97b61` deleted `_CLOCK_ACTION_SOURCE_RE`
for `orchestrator.work_is_licensed()` and corrected two stale comment clauses in
the guest fence, so every line number in the review is stale. **Everything below
is re-pinned by symbol**: `Memory._compare_words`, `Memory._relate_fact`,
`Memory.recall`, `Memory._search_episodes`, `Memory.consolidate`,
`Memory._supersede`, `Memory._fact`, `anticipy_core._UNTRUSTED_SOURCES`,
`orchestrator.ends_in_the_world`.

The commit shipped this sentence, having found and fixed one instance of it:

> *A threshold that excludes the case is not a sift in front of the decision —
> it **is** the decision.*

It shipped with two more, both upstream of the same model call. Both are closed.

---

## What a cheap sift may legitimately do here

**It may decide the ORDER the model is asked in. It may not decide which pairs
it is asked about. There is no safe word-based exclusion at this seam, and the
reason is structural rather than a matter of picking a better number.**

A supersession pair is low-overlap *by nature*, because one sentence asserts and
the other negates. Word overlap is therefore **anti-correlated** with the thing
being looked for: ranking by it and cutting is worse than random. Three
mechanisms in a row got this backwards, each removed only after it was measured
excluding the deciding pair:

| mechanism | what it excluded |
| --- | --- |
| the `0.40–0.80` band (fixed by `82e9dc31`) | `partner is Dana` / `broke up with Dana`, overlap 0.333 |
| `if overlap > 0` | `partner is Jo` / `broke up with Jo` — see C2, the shared word was thrown away before counting |
| `[:3]` | the same pair again, whenever four facts name one person |

And the general case defeats all three: `home is 4 Maple St` and
`we moved to Rowan Ave` share **no word at all**. That is the review's own
residual #4, and it is not a residual — it is the same defect.

So the honest job of a sift here is cost, and **the alternative was priced and
taken**: the question is now asked once about the whole list rather than once
per pair.

* Cost per incoming fact: **1 model call**, down from up to 3. Worst case is
  `ceil(live_facts / _JUDGE_BATCH)` calls (`_JUDGE_BATCH = 25`), reached only
  when the model finds no match anywhere in the profile.
* Overlap still ranks the list, so the likely answer is in the first batch and
  the batch loop short-circuits on the first verdict. **Ranking changes what is
  asked FIRST, never what is asked.**
* Ties now break to the **lower row id** — the older fact — because the older
  row is by definition the one a supersession is about. `sorted(near, reverse=True)`
  put newer noise in front of it.
* Prompt size, not candidacy, is what `_JUDGE_BATCH` bounds. That is a bound on
  a *bill*, and every excluded row is asked in the next call.

### The bill, since "price the alternative" was the ask

Per incoming candidate fact, with `L` live profile facts:

```
before:  min(3, candidates_scoring > 0)          calls   — and it could miss
after:   1 call when the model finds a match in the first 25
         ceil(L / 25) calls when it finds none anywhere
```

A nightly pass distils on the order of 5–20 facts. At `L = 200` (a mature
profile) the worst case is 8 calls per fact, so ~160 aux calls on a night where
nothing matches anything, against ~60 before. **That is the honest price of the
answer being reachable at all**, it is paid on the cheap `aux` tier, and the
expected case is one call per fact because the ranking puts the plausible
candidates first. If it ever needs lowering, the lever is `_JUDGE_BATCH`
UPWARDS (fewer, larger calls) — never a cut on the ordered list, which is the
mechanism this whole section removes.

Asking the model about a list instead of a pair costs one thing: the model can
now name a note that does not exist. That is validated (`n` must be an integer
naming a note in the batch it was shown) and treated as no verdict, the same
contract `_fact_kind` and `_speaker_verdict` hold.

---

## C2 — a word-LENGTH threshold decided which words carry meaning

`Memory._compare_words`. HARNESS-LAW 1 names **word count** explicitly.

### Before

```
partner name 'Dana'  : SAME_FACT model calls = 1;  live profile = ['broke up with Dana']
partner name 'Jo'    : SAME_FACT model calls = 0;  live profile = ['partner is Jo', 'broke up with Jo']
partner name 'Al'    : SAME_FACT model calls = 0;  live profile = ['partner is Al', 'broke up with Al']
partner name 'Ed'/'Bo'/'Ty'/'Li' : identical

_compare_words('partner is Jo')     = ['partner']
_compare_words('broke up with Jo')  = ['broke']
recall('who is my partner') -> ['known: partner is Jo', 'known: broke up with Jo']
```

Overlap 0, `if overlap > 0` never fired, **no model was ever asked**, and the
dead fact led recall at salience 4.7 forever.

### And one tier down, worse — found while reproducing it

The same score reaches `_same_as`, which answers **with no model in the loop at
all**, and `forget_fact`, where it DELETES:

```
_compare_words('partner is Jo') = ['partner']
_compare_words('partner is Al') = ['partner']
_same_as('partner is Jo','partner is Al') -> True
profile after storing BOTH:  ['partner is Jo']          <- "Al" silently swallowed

forget_fact('dinner with Jo') removed 1 row(s)
profile: []                                              <- "dinner with Al" DELETED
is 'dinner with Ed' now blocked from ever being written? True
```

### After

```
partner name 'Jo'/'Al'/'Ed'/'Bo'/'Ty'/'Li' : SAME_FACT model calls = 1;
                                             live profile = ['broke up with <name>']
_compare_words('partner is Jo')     = ['jo', 'partner']
_compare_words('broke up with Jo')  = ['broke', 'jo']
_same_as('partner is Jo','partner is Al') -> False
forget_fact('dinner with Jo') removed 0 row(s);  profile: ['dinner with Al']
is 'dinner with Ed' blocked? False
```

### The half that is easy to get wrong, and was measured

Deleting the length test alone is **not** the fix. A filler word shared by two
sentences *inflates* their similarity, and two tiers read that score with no
model in the loop. Both regressions appeared immediately in the suite:

```
with "is" counted: 'Their name is Omar.' absorbed 'Their name is Omar Ebrahim.'
                   at exactly 0.80 — the surname thrown away
                   (tests/test_profile_seed.py::test_a_changed_name_updates_the_profile)
with "in" counted: the veto 'the renewal closes in 4 weeks' reached 0.80 against
                   'the Devon renewal closes in 3 weeks' and DELETED it
                   (tests/test_supervised_read_is_fenced.py::test_a_merge_cannot_reinstall_vetoed_wording)
```

The length test was standing in for a stopword list and doing it by counting
letters. `Memory._STOP` is that list, it is written down, it is closed-class
(articles, prepositions, particles, pronouns, auxiliaries, conjunctions), and
**nothing in it is a name**. `"no"` is deliberately absent: negation is exactly
the difference between two facts. With the list in place the overlap figures
return to the exact values the review reported (0.333 / 0.500 / 0.667 / 0.667),
so the *only* behavioural change is that short names now count.

---

## C3 — `[:3]` was the old 0.40 floor wearing a different mechanism

`Memory._relate_fact`.

### Before

```
stored 'partner is Dana'             overlap 0.333
stored 'Dana broke her wrist skiing' overlap 0.500
stored 'Dana broke the blender'      overlap 0.667
stored 'Dana broke up with her boss' overlap 0.667
incoming 'broke up with Dana'

put to the model:  Dana broke up with her boss
                   Dana broke the blender
                   Dana broke her wrist skiing
'partner is Dana' reached the model: False
```

### After

```
model calls: 1
put to the model:  1 Dana broke the blender
                   2 Dana broke up with her boss
                   3 Dana broke her wrist skiing
                   4 partner is Dana
'partner is Dana' reached the model: True
```

Note the first two: the 0.667 tie now resolves to the **older** row.

`SAME_FACT_SYSTEM` was rewritten from a pair question to a list question and
tells the model, in as many words, that nothing was filtered out before it and
that the note that matters may share no word with the new one. The reply shape
is `{"n":N,"relation":"same"|"replaces"}` or `{"n":null,...}`.

`tests/llm_fakes.py::FakeLLM` was updated to answer the list shape; a scripted
verdict answers about `stored_notes[0]` — the note the sift ordered first, which
is the note the old pairwise loop would have asked about first — and `answer_n`
pins it elsewhere when a test needs that.

---

## C1 — a retired fact reached BOTH action sinks through the episode layer

`Memory.recall` returned `(profile + graph)[:limit]` and only `profile` was
filtered. The docstring ruled episodes out of scope — true of the *record*,
irrelevant to the *ruling*, which governs what may be an input to action.

### Before — RULING 2 §7's own example

```
recall("what is my home address for the delivery", retired=RETIRED_EXCLUDED):
   src_type='profile'  known: home is 18 Rowan Ave
   src_type='episode'  heard: "Our home address is 4 Maple St, put that on the delivery."

KNOWN block handed to fill_gaps_from_memory:
  - known: home is 18 Rowan Ave
  - heard: "Our home address is 4 Maple St, put that on the delivery."
dead address in the approved-values path: True
```

The dead address, unmarked, **phrased as an imperative** — a stronger action
signal than the live fact beside it — on its way to
`filled[gap] → params[key] → the browser agent's approved values → a form it
submits`. RULING 2's table for `fill_gaps_from_memory` reads
*"NEVER — hard filter. No exception, no flag."* The only mitigation was that
profile sorts first and the model *might* prefer it: model-dependent, which is
precisely what the ruling refuses for this lane.

### After

```
recall(..., retired=RETIRED_EXCLUDED):
   src_type='profile'  known: home is 18 Rowan Ave
KNOWN block handed to fill_gaps_from_memory:
  - known: home is 18 Rowan Ave
dead address in the approved-values path: False
```

The filter is **structural, id-only**: `Memory._episodes_behind_retired_facts()`
reads `provenance`, which is the list of episode ids `consolidate` recorded, and
never looks at a sentence. An episode a retired fact was distilled from *is* that
fact in undistilled form. The speech lane (`RETIRED_QUOTED`) keeps every episode,
because "he said the address was 4 Maple St" is a true record of a thing that was
said — that is what makes §7's broadband answer possible, and it is pinned.

### Residual R1, written down rather than hidden

An episode that states the same dead thing but was **never distilled into that
fact** is in no provenance list and still reaches the action lane. Closing it
completely means excluding raw episodes from the action lane entirely.

**Price:** that costs the ability to act on anything said since the last nightly
consolidation — a fact stated this morning lives only in episodes until the
overnight pass runs. That is a capability decision, not a bug fix, and it is an
owner ruling. Flagged here and in `_episodes_behind_retired_facts`' docstring.

---

## I4 + I6 — one fix, both provenance holes, and a third door

**Yes: one fix closed both, and it closed a third the reviewer had not named.**

`episodes.speaker` is the phone's local voice verdict. It is stored by `ingest`,
carried onto every commitment, and carried into `briefing_facts` — and it was
dropped at exactly the places where a line can KILL a fact or put a value in a
form. Law 5 order: the sense exists and is captured, and the destructive decision
was the one place it was not passed along.

### Before

```
episodes: (1,'owner','Dana and I are heading to Lisbon.')
          (2,'other',"Oh, didn't you hear? Omar and Dana broke up.")
listing the model saw: "[2] Oh, didn't you hear? Omar and Dana broke up."
live profile: ['broke up with Dana']
retired:      ('partner is Dana', ..., source='consolidation')
```

```
recall(...) -> src_type='episode' source=<key absent>
memory_notes -> known: home is 18 Rowan Ave; heard: "..."
episode text fenced: False
```

### After

```
listing the model saw:
  "[2] (NOT them — someone else in earshot) Oh, didn't you hear? Omar and Dana broke up."
live profile: ['partner is Dana', 'broke up with Dana']
retired: []
sources: partner is Dana -> 'consolidation';  broke up with Dana -> 'overheard'
```

```
recall(...) -> src_type='episode' source='overheard'
memory_notes -> <<<UNTRUSTED:… other people wrote this … heard: "…" …>>>
fill_gaps_from_memory: filled={}  remaining=['reservation name']   (the model was never asked)
```

### The mechanism

One new tag, `memory.OVERHEARD`, imported into `anticipy_core._UNTRUSTED_SOURCES`
so there is one string and one definition. Everything else is the fence every
consumer already keys on:

* `_supersede` guard 1 — an overheard fact lands but cannot retire something the
  owner said (**I4**);
* `memory_notes` — fenced, not mixed with what the owner told us (**I6**);
* `fill_gaps_from_memory` — excluded outright, so she asks him instead;
* `_provenance_window` — capped at a third of any bounded window.

Applied in three places, all label-only, none reading a word:

1. `consolidate` — the listing carries the verdict, and `CONSOLIDATE_SYSTEM` is
   told what the tag means and that an untagged line is the ordinary case. A
   fact lands as `overheard` only when **every** contributing episode is a
   positive "not the owner".
2. `recall` — the episode row carries `source`.
3. `Memory._fact` — **the third door**, found while checking the second. An edge
   is derived from one episode and carries its authority. Fencing only the
   episode row moved the same content one row down and let it through unfenced:
   `Kowalski —about→ reservation` reached the trusted half, and
   `fill_gaps_from_memory` still filled the reservation name off an overheard
   line. Both are fenced now.

**Only an explicit `"other"` labels.** Live roster coverage is 0%, so reading
absence as "not his" would fence every line the product has ever heard. Pinned
by three legs (`test_an_unattributed_line_is_listed_exactly_as_it_always_was`,
`test_an_unattributed_line_still_retires`,
`test_the_owners_own_line_still_settles_a_gap`).

---

## M7 — the `retired` counter, promoted from latent to reachable

`_supersede` returns a truthy row id on the provenance-fence path too, having
retired nothing, so `consolidate` counted a retirement that did not happen. The
review called it latent *because consolidation could not produce an untrusted
source* — **the I4 fix makes it reachable the same night**, so it had to be
fixed in the same wave.

`retired` now counts only when a row actually carries a `retired_ts`
(`Memory._is_retired`). Measured on the I4 scenario:

```
before: counters {'new': 1, 'merged': 0, 'retired': 1}   <- nothing died
after:  counters {'new': 1, 'merged': 0, 'retired': 0}
```

This is the one number the nightly print shows, and the one place anybody would
notice supersession quietly stopping. A mislabel reads as "she corrected
herself" on a night she refused to.

---

## `ends_in_the_world` — disposition

`brain/orchestrator.py::ends_in_the_world`. `grep -rn ends_in_the_world tests/`
returned nothing: no test at all, not even a scripted one, for the function that
decides whether a read-only-*worded* goal is actually consequential.

**Disposition: fixed as far as it can be fixed without an owner ruling.**

* **Written**: `tests/test_ends_in_the_world.py`, 14 legs. Every state pinned —
  explicit true, explicit false, dead model (never asked, no bill), no goal,
  a call that raises, a non-JSON reply, a live model that answered a *different*
  question, truthiness (`"true"`, `1`, `"yes"`, `[True]` are all no), null, the
  prompt judging substance and not verbs, the stale-alias check, and the verdict
  followed through the **real ambient path** to the thing it buys: `hold=True`
  on the queued job (the card he is asked about) versus `hold=False` (quiet
  research he never hears about).
* **Changed**: the failure is no longer silent. `party_verdict` prints when its
  question goes unanswered; this one swallowed the exception, so a model that
  timed out every night looked exactly like a model that answered "no" every
  night. It now prints on both the exception and the unreadable reply, naming
  the goal that is staying quiet.
* **NOT changed, and this is the owner ruling**: the collapse direction. A
  timeout returns False, the plan stays quiet research, and the owner never gets
  the text — which is the 2026-08-09 failure its own docstring cites, arriving
  through the mechanism built to stop it. Its three siblings carry four states
  precisely because "no" and "nobody answered" are different things.

  **Why it was not simply changed:** making UNANSWERED escalate means every
  transient model fault interrupts him about prep work, which is the failure the
  quiet lane exists to prevent. That is a live behaviour trade nobody can
  measure from a laptop, and Law 3 says repo-green is not the test for it. The
  collapse is now pinned by tests and documented in the docstring, so moving it
  is a decision somebody makes rather than a default nobody can see.

  Sketch, if the owner rules the other way: `WORLD_YES/NO/UNASKED/UNANSWERED`
  as strings, and `anticipy_core.py`'s call site becomes an explicit
  `verdict in (WORLD_YES, WORLD_UNANSWERED)`. **Do not return the strings while
  the call site is `and ends_in_the_world(...)`** — `"no"` is truthy, and that
  turns a fence into a wall in one line.

---

## Mutations — every check proven, 27 for 27

Each fix was broken and the named legs had to go red. Harness re-run at the end
to confirm the tree was restored (green).

| # | mutation | legs that went red |
| --- | --- | --- |
| 1 | restore the word-LENGTH filter | 3 sift legs + the filler-word leg |
| 2 | drop the short function words from `_STOP` | `test_the_filler_words_the_letter_count_stood_in_for_are_still_dropped` |
| 3 | restore `if overlap > 0` as a candidacy gate | `test_the_ranking_only_decides_what_is_asked_first` |
| 4 | restore the `[:3]` rank-and-truncate | `test_every_live_fact_reaches_the_model_however_low_it_ranks`, `…_asked_first` |
| 5 | break ties to the NEWER row | `test_every_live_fact_reaches_the_model_however_low_it_ranks` |
| 6 | ask only the FIRST batch | `test_the_ranking_only_decides_what_is_asked_first` |
| 7 | stop validating the `n` the model names | `test_a_verdict_naming_a_note_the_store_never_offered_is_no_verdict` |
| 8 | let retired facts back through the episode layer | 2 action-lane legs |
| 9 | apply the episode filter in BOTH lanes | `test_the_speech_lane_still_hears_the_line_that_was_actually_said` |
| 10 | take the episodes behind EVERY fact | `test_a_live_fact_s_own_episode_is_not_collateral` |
| 11 | drop the speaker from the consolidation listing | `test_the_consolidation_listing_says_who_spoke` |
| 12 | tag every line, unattributed ones included | `test_an_unattributed_line_is_listed_exactly_as_it_always_was` |
| 13 | stop labelling a stranger-only fact | 3 legs across two files |
| 14 | label on ANY stranger line rather than ALL | `test_one_line_of_his_in_the_evidence_is_enough_to_make_it_ordinary` |
| 15 | drop the source key from an episode row | 2 fence legs |
| 16 | drop the source key from a derived edge | `test_the_edge_derived_from_an_overheard_line_is_fenced_too` |
| 17 | read ABSENCE as "not the owner" (episode row) | `test_the_owners_own_line_still_settles_a_gap` |
| 17b | read ABSENCE as "not the owner" (derived edge) | `test_the_owners_own_line_still_settles_a_gap` |
| 17c | obey the verdict on the TOP note whatever `n` said | `test_a_low_ranked_fact_is_still_obeyed_when_the_model_names_it` |
| 17d | treat ONE unreadable batch as an answer about the rest | `test_the_ranking_only_decides_what_is_asked_first` |
| 18 | count a retirement the fence refused | `test_the_retired_counter_does_not_count_a_retirement_the_fence_refused` |
| 19 | take `OVERHEARD` out of the fence set | 3 legs |
| 20 | swallow the unanswered consequence question | 2 legs |
| 21 | swallow a reply that answered another question | `test_a_live_model_that_answered_a_different_question_says_so` |
| 22 | accept a truthy answer instead of a real boolean | `test_only_a_real_boolean_true_counts` |
| 23 | ask a model that is not live | `test_a_dead_model_is_never_asked_and_never_escalates` |
| 24 | stop consulting the question at the call site | `test_the_verdict_reaches_the_decision_that_spends_it` |

### One of my own checks was fail-open, and this is how it was caught

Mutation 17 went **GREEN on the first run**. `test_the_owners_own_line_still_settles_a_gap`
asserted only the outcome — "the gap still got filled". `recall` returns the
episode *and* the edge derived from it; the mutation fenced one of them and the
survivor answered the question. **An outcome assertion over a set of rows cannot
tell "nothing was fenced" from "not everything was."** The leg now asserts row by
row on `source`, plus that `memory_notes` renders no fence, and mutation 17b was
added to prove the same for the edge path. Both are red now.

---

## A word list is still a word list — flagged, per HARNESS-LAW 1

CLAUDE.md says to flag rather than complete, so: **this diff adds 24 entries to
`Memory._STOP`**, and Law 1 names word lists. The honest account of why it is
legal, so the next reader can disagree with it on the merits:

* It is **tokenisation, not judgement**. `_STOP` decides which tokens enter a
  string-similarity set. It does not decide what a sentence means, and it
  cannot decide that a fact is dead — that verdict belongs to the model and is
  now reached for *every* live row.
* The list it replaces was **worse and unwritten**: `len(w) > 2` was the same
  list, approximated by counting letters, invisible, and unable to tell a
  preposition from a person.
* **It can no longer exclude anything from the model.** Before this change,
  `_compare_words` fed `if overlap > 0`, so a stopword decision could silence
  the question entirely. It now feeds only ordering plus the two deterministic
  same-wording tiers.

Those two tiers — `_relate_fact`'s `>= 0.8` shortcut and `_same_as` — remain
thresholds that answer "are these the same fact?" **with no model in the loop**.
They predate this work and the review verified the retired-row behaviour around
them as sound, so removing them was out of scope; they are named here because
they are the last place in this file where a number decides sameness, and the
C2 reproduction is a demonstration of what happens when their inputs are wrong.
If a future wave takes them to a model, `_STOP` goes with them.

---

## What was verified sound and is NOT regressed

Re-run after every change, all green:

* both action sinks still name `RETIRED_EXCLUDED` out loud; `conversation.py`
  inherits the safe default; the profile half of the filter is untouched;
* the veto interaction — a vetoed replacement retires nothing, so the veto is
  still not a silent deletion weapon; `llm=None` retires nothing and raises
  nothing; an unknown verdict (including the old `{"same":bool}` shape) changes
  nothing;
* the retired-row merge trap — "actually, we're back together" is judged against
  the live occupant, not the corpse; the older-side-loses guard survives a
  replayed consolidation batch; a retired row is still never put to the model
  (re-asserted on the payload now, not on "no call happened", because every live
  row is a candidate);
* retired facts never lead, in either lane, across three orderings;
* the provenance fence is still structural, label-only, correct polarity, and
  reads no wording — it gained a fourth member and no new mechanism.

---

## What waits on LIVE (Law 3)

Repo-green is not done. Nothing below has run against a live model:

1. **The list-shaped `SAME_FACT_SYSTEM` has only ever been answered by a fake.**
   The fake picks `stored_notes[0]`. What is unmeasured is whether a real model,
   shown 25 notes instead of 2, holds the "MOST NEW NOTES STAND IN NEITHER" line
   — the failure direction is a *false* `replaces`, and a wrongly retired fact is
   a thing she stops knowing about him. `overnight/consolidation_gate.py` leg 4
   ("IT WROTE WHAT THE RANKER READS") is where that shows up, and it can only run
   on the deploy host: it needs a real owner memory database.
2. **The overheard tag has never been produced by a real phone.** Live voice
   roster coverage is 0%, so `speaker='other'` is currently a test-only value.
   Every leg here says absence must change nothing, and that half *is* what
   production exercises today. The other half turns on when the roster does.
3. **`done_gate` leg 3 (SHE JUDGES RIGHT) still blocks on `OPENROUTER_API_KEY`.**
   Unchanged by this work and unchanged by it.
4. **`ends_in_the_world`'s new print lines have never appeared in a real log.**
   The whole point of them is that a nightly timeout stops looking like a "no";
   confirming that is reading production logs after a deploy.
5. **Deploy verification.** `railway up` reports success while failing; verify
   with an `overnight/is_it_live.py`-style check after any deploy of this.

Gates as of this change: `tejas_gate` **8/8**. `tape_gate`,
`consolidation_gate` and `stranger_gate` red **by design** — untouched, and the
tape census was not touched (no tape was added: every change here removes a
pattern or passes a stored label along, and none of it is a string-level patch
buying time).

## Files

* `brain/memory.py` — `_compare_words`, `_STOP`, `_relate_fact`,
  `_ask_the_model_which_note` (new), `SAME_FACT_SYSTEM`, `_JUDGE_BATCH` (new),
  `OVERHEARD` (new), `recall`, `_episodes_behind_retired_facts` (new),
  `_search_episodes`, `_fact`, `consolidate`, `CONSOLIDATE_SYSTEM`,
  `_speaker_tag` (new), `_is_retired` (new)
* `brain/anticipy_core.py` — `_UNTRUSTED_SOURCES` gains `OVERHEARD`
* `brain/orchestrator.py` — `ends_in_the_world` says when it could not answer
* `tests/llm_fakes.py` — `FakeLLM` answers the list-shaped question
* `tests/test_memory_supersession.py` — THE SIFT and THE EPISODE LAYER sections
* `tests/test_memory_knows_who_spoke.py` — the destructive-decision section
* `tests/test_ends_in_the_world.py` — new file
