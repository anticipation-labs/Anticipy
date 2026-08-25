# The outcome rate: of the lines that arrived, what came of them

`proof/outcome_rate.py` + `tests/test_outcome_rate.py`. Read-only against
production. Written 2026-08-25.

**The number, from PRODUCTION, not from the repo (Law 3):**

| window | lines | produced something | rate |
|--------|-------|--------------------|------|
| 24h    | **0** | 0                  | **n/a — she was deaf, and she sent 3 messages anyway** |
| 48h    | 263   | 16                 | **6.1%** |
| 168h   | 542   | 51                 | **9.4%** |

Read against `https://backend-production-61e0a.up.railway.app` with the
`ANTICIPY_SERVICE_TOKEN` in `.env.local`, `rows_unread: 0` on every run, so
these are whole windows and not subsets.

---

## What I verified versus what I was told

I was handed six claims. Four held, two were wrong about the code, and the
two that were wrong both mattered to the design.

**HELD — `is_the_brain_live.py` cannot see a silent day.** It reads
`anticipy_says` rows only (`overnight/is_the_brain_live.py`, the single
`fetch("events", ...)` in `main()`), and every leg of `evaluate_rules` is an
over-speaking check: asked more than twice, spoke in quiet hours, over the
daily uninvited budget, sent the same sentence twice, recorded as told but
never landed. On an empty read it calls `note(..., "not a pass")` and then
returns 0. Confirmed live on the same 24h window:

    is_the_brain_live.py --hours 24        -> exit 0
    outcome_rate.py --hours 24 --min-lines 1 -> exit 1

**HELD — zero transcript lines in 24 hours.** Independently reproduced.
`kind="transcript"` in the last 24h: nothing. `anticipy_says` in the same
window: three, to two different owners. One of those owners
(`xg7i6qglmd53il1`) has no transcript lines in 48h at all.

**HELD — the guards leave no trace.** `mark_processed` (`brain/worker.py`)
writes exactly three fields onto a transcript row: `decision`, `addressee`,
`goal`. Every `Decision` the core builds carries a fourth, `reason`, and it is
where `"a shard with no thread to continue"`, `"stays ambient"`, `"not his to
do"`, `"nothing speakable to ask"` and a dozen more all live
(16 `decision="ignore"` sites in `anticipy_core.py`, each with its own
`reason`). **Nothing writes
`reason` down.** There is no `reason` column in any `backend/pb_migrations/`
file and no `"reason"` key in any `post_event` or `pb.patch` body.

**HELD — 42% of lines are four words or fewer.** `capture_day.py --hours 48`
against the same window: `short thoughts 42%`.

**WRONG — "6.4%".** Close, and it is the right order of magnitude, but I
could not reproduce that exact figure. I measure **6.1%** at 48h and 9.4% at
168h. The row-only calculation (ignoring jobs) gives 5.7% at 48h; the extra
0.4pp is the job join described below. I report what I measured.

**WRONG — "the meeting latch silences the line."** It does not. The latch
(`anticipy_core.py`, `if fresh and in_meeting`) stamps `decision="act"` with
the goal and appends to `self._meeting_held`; what waits for the digest is the
TEXT, not the card. A latched line shows up here as an **outcome**. What the
latch delays is delivery, which is a different measurement and needs a
different instrument. Folding it into "silenced" would have understated the
rate and blamed the wrong subsystem.

**WRONG-ish — "the parked ask is one of six guards."** It is, but not for the
reason given, and the real reason is worse. The ask valve returns
`decision="ask", goal=""` and says nothing yet. Then `stamp_for()` rewrites an
ask that asked nothing into `"ignore"` — correctly; the app renders any "ask"
as the header *"Quick question for you"* and Omar got that header with no
question under it. The rewrite is right, and the record it leaves is
**byte-identical to a line she correctly let pass**. That is why `decision="ask"`
is nearly absent from production rows: 0 in 48h, 8 in 168h.

---

## What is actually stored, per line and per outcome

Verified against live rows, not against the migrations alone.

**A transcript row** (`kind="transcript"`) carries: `device_id, text,
decision, goal, needs_confirmation, addressee, speaker, source, explicit,
parent_line, capture_started_at, spoken_at, segment, seq, owner_ref, owner,
external_event_id, created, updated`. The app writes it with `decision=""`;
`fetch_unprocessed` selects exactly that; `claim()` stamps `"processing"`;
`mark_processed` writes the final `decision`/`addressee`/`goal`.

**An outcome row** (`kind="anticipy_says"`) carries `text`, `decision`
(`act|ask|done|clock|needs_user|deaf|welcome`), `goal`, `owner_ref`, and
optionally `source`. **`post_event` writes no pointer back to the line that
caused it** — no `parent_line`, no source event id. So a says row cannot be
attributed to a line except by matching the `goal` string, which repeats.

**A job** carries the link, and this is where I was wrong first and had to
check. Grepping the params string for `source_event_id` matches 63 of 65
production jobs — and **not one of them has that key at the top level.** It
lives inside `_workflow`, a JSON string nested inside the params JSON string
(`workflow.py`'s `Plan`, serialised). Parsed properly: **53 of 65 jobs name at
least one source event**, 49 of those ids fall inside the 168h transcript
window, and **2 of those lines carry `decision=ignore` and no goal on their own
row** — an outcome that is invisible from the line. That is the `job_only`
bucket, and it is the 0.4pp difference between 5.7% and 6.1%.

**Memory is not observable.** `brain/memory.py` is SQLite
(`sqlite3.connect`, `ANTICIPY_MEMORY_DB`), local to the worker process. "A
fact remembered" is in the brief's list of outcomes and **cannot be measured
from production at all.** Every silent line in this report may have been
remembered; there is no way to tell from here.

---

## Which silences can be told apart, and which cannot

The report buckets rather than subtracts. Every line lands in exactly one
bucket and the buckets sum to `lines` — carried in the output as
`rows_bucketed` so a regression that loses lines is a visible disagreement
rather than a quietly nicer rate.

**Distinguishable, from the stored rows:**

- `never_processed` — `decision=""`. The worker never reached it. A dead
  worker, a poll that never ran, an owner nothing is polling for.
- `in_flight` — `decision="processing"`. Claimed and unfinished, or stranded
  by a restart until `release_stranded_claims` sweeps it back after 10 min.
- `refused` — `ignored_nonowner`, `error`, `refused_read_fact_ceiling`, and
  any stamp this file has not heard of. An unknown stamp is the brain having
  said *something*, so it is a refusal, not a mystery.
- `echo_of_her` — **recomputed, not guessed.** `is_echo_of_her` is the one
  named guard that reads a durable record: the same `anticipy_says` /
  `anticipy_text` rows this report already holds. `outcome_rate.py` imports
  `longest_shared_run`, `ECHO_RUN`, `ECHO_FRACTION` and `_words` from
  `brain/worker.py` and re-runs the guard's own rule at its own thresholds —
  including reading `ECHO_MINUTES` off the function signature so it cannot
  drift. It reproduces the worker's two-clock quirk faithfully: spoken time
  for his line (`before=capture_key(ev)`), arrival time for her rows.

  **Live result: 0 echoes in every window** — and that is a real measurement,
  not dead code. 246 comparable (line, message) pairs were actually examined
  over 168h; the top scorer shares 13 words in order at 0.54 of his line,
  clearing `ECHO_RUN=6` and missing `ECHO_FRACTION=0.6`.

**NOT distinguishable — all of these land in `unexplained_silence` together,
which is 247 of 263 lines at 48h and 491 of 542 at 168h:**

| what happened | why it is invisible | what `brain/` would have to record |
|---|---|---|
| correctly ignored (a TV, a joke, someone else's errand) | `ignore` + `goal=""` | — this is the baseline the others hide in |
| `shard_too_thin` | returns `ignore` + `goal=""`; reason printed to a log | **persist `Decision.reason` onto the row** |
| the parked ask | `ask` + `goal=""`, then `stamp_for` → `ignore` | a `parked_ask` flag, or `Decision.reason` |
| the parked-ask gauntlet (120s of total silence) | a question that never found its quiet moment leaves the same row as one never formed | when a parked question expired |
| `already_raised` / `already_said` | fire at the SAYING site, not the line; **a refused say writes no row at all** | write the refusal |
| no live LLM | every line falls to `llm.py`'s `_heuristic`; nothing on the row says which engine judged it | stamp the LLM mode on the row |

**One thing the rows CAN say about the mixture, and the report prints it:**
`addressee` is stored. At 48h the 247 unexplained lines split
`self: 117, person: 69, unclassified: 61`. `person` is the lane that is
*supposed* to be quiet. **`unclassified: 61` — 23% of every line that arrived —
is triage having returned no addressee at all**, which is a different animal
and worth someone's attention.

**And one honest ceiling:** `at most 107 of the 247` were short enough for
`shard_too_thin` to fire. Necessary, not sufficient — the guard also requires
the model to have wanted to act, to have had no thread, and to have minted a
goal carrying more than two invented words, none of which is stored. It is
printed as a ceiling and named `at_most_shard_too_thin`.

**The single highest-value fix, and it is in `brain/` which I do not hold:
persist `Decision.reason` onto the transcript row.** One text column. It alone
would split `shard_too_thin`, the parked ask, the gauntlet, "stays ambient",
"not his to do" and "correctly ignored" apart from each other — six of the
seven rows in the table above.

---

## Every check, with its mutation

25 mutations, applied to `proof/outcome_rate.py` in place, suite run, restored.
**All 25 were caught.** A mutation whose anchor was not unique was a hard error,
so none was silently skipped. Three survived the first pass — each was a
genuine hole in the tests, and each is now closed (noted below).

| mutation | check that went red |
|---|---|
| a deaf window scores a perfect rate | `test_a_deaf_window_never_reports_a_perfect_rate` |
| a deaf window denies it was deaf | `test_a_deaf_window_never_reports_a_perfect_rate` |
| quiet work stops counting as an outcome | `test_a_quiet_goal_is_an_outcome_even_though_the_decision_says_ignore` |
| an ask is filed as a silence | `test_a_question_she_actually_asked_is_an_outcome` ← **survivor 1** |
| `outcomes` counts the silences too | `test_a_silent_ignore_is_not_an_outcome` |
| the job link is read from the top level only | `test_a_line_a_job_points_at_is_an_outcome_even_when_its_row_shows_nothing` |
| a job that names no line credits every line | `test_a_blank_source_event_id_does_not_enter_the_id_set` ← **survivor 2** |
| her later reply explains away the line that caused it | `test_something_she_said_after_he_spoke_cannot_be_what_he_echoed` |
| the echo read stops being scoped to the owner | `test_another_owner_s_message_is_not_his_echo` |
| the echo threshold drops to one shared word | `test_a_long_line_that_merely_shares_a_topic_is_not_an_echo` ← **survivor 3** |
| a line never processed is filed as an ignore | `test_a_line_never_processed_is_not_the_same_as_a_line_ignored` |
| a claimed line is filed as an ignore | `test_a_line_still_in_flight_is_named_separately` |
| a stamped refusal is filed as an unexplained silence | `test_an_explicit_refusal_is_named_rather_than_filed_as_an_ignore` |
| the shard ceiling stops being the guard's own rule | `test_the_shard_bound_is_an_upper_bound_and_says_so` |
| the unexplained bucket stops naming the addressee | `test_the_unexplained_bucket_is_broken_down_by_addressee` |
| her own messages are counted as lines that arrived | `test_anticipy_says_rows_are_not_counted_as_lines_that_arrived` |
| her side stops being counted at all | `test_her_side_is_counted_separately_so_a_deaf_talkative_day_is_visible` |
| the lost-line invariant is defeated | `test_a_bucketer_that_loses_lines_is_shouted_about_not_averaged_over` |
| the report stops splitting the owners | `test_the_blind_spot_is_stated_once_and_not_repeated_per_owner` |
| the read takes the first page and calls it a window | `test_the_report_reads_the_whole_window_not_the_newest_page` |
| an unreadable window is reported as unknown-free | `test_a_window_it_could_not_finish_reading_says_so_loudly` |
| a jobs read that failed is swallowed | `test_jobs_that_could_not_be_read_are_admitted_not_silently_skipped` |
| a rate floor is met by a window that heard nothing | `test_a_rate_floor_cannot_be_met_by_a_window_that_heard_nothing` |
| a line floor stops being checked | `test_a_deaf_window_fails_when_a_floor_was_asked_for` |
| a read that threw is reported as a clean window | `test_a_window_that_could_not_be_read_is_never_a_pass` |

**Why the three survivors survived, since that is the useful part:**

1. *an ask is filed as a silence* — I had no test whose line carried
   `decision="ask"` at all. Production has 0 of them at 48h, so writing tests
   from the live shape alone left the branch unexercised.
2. *a job that names no line credits every line* — my test asserted an *empty
   list* of ids yields an empty set, but never an *empty string* id. A job
   carrying `source_event_id: ""` would have put `""` into the id set.
3. *the echo threshold drops to one shared word* — my "shares a topic" case
   used a two-word line, which returns at the `mine < ECHO_RUN` length gate
   before the threshold is ever consulted. The threshold was untested. The
   replacement uses a ten-word line sharing two words.

**A separate pin found a real disagreement.**
`test_the_shard_bound_agrees_with_the_real_guard_about_length` drives
`could_be_a_shard` against the actual `shard_too_thin` from
`brain/anticipy_core.py`. It failed on first run: the guard's `> 4` fires on a
line of **zero** words, and my bound used `0 < n <= 4` (copied from
capture_day's shard rate, which correctly excludes empty). A ceiling may not
exclude something the guard would catch, so the bound now matches the guard
exactly. `capture_day` is computing a rate and is right to differ; this is
computing a ceiling.

---

## What the instrument refuses to do

- **Zero lines yields `outcome_rate: null`**, never `0.0` and never `1.0`.
  There is no rate of a day that held nothing, and a `--min-rate` floor is
  **missed** rather than met by it — otherwise the deaf day would walk through
  the one gate written to catch it, which is precisely the existing checker's
  bug re-implemented inside its replacement.
- **A read that threw exits 1.** A reader that fails silently would report a
  perfect day.
- **A jobs read that failed is announced**, the rate is labelled a FLOOR, and
  `jobs_read` goes to `null` in the JSON. Losing the jobs understates the rate,
  and understating is the direction that gets believed.
- **A blended multi-owner rate is announced as blended**, with per-owner
  numbers beside it. At 168h the blend reads 9.4% while one owner sits at 5%
  and another at 43%, and a fourth owner has no lines at all.
- **The blind spot is printed whatever the numbers say**, because it is a
  property of what `brain/` records, not of today's window.

## One stated edge

The echo recomputation looks 30 minutes back from each line and the read starts
at the window's edge, so a line in the first half hour that read back something
she said just *before* the window opened cannot be recognised and lands in
`unexplained_silence`. That direction is the safe one — it over-fills the
bucket meaning "we do not know" rather than explaining a silence away.

## Findings for other agents (I hold only `proof/` and `tests/`)

1. **`brain/`** — persist `Decision.reason` onto the transcript row. One
   column; it splits six of the seven indistinguishable silences apart.
2. **`brain/`** — `post_event` writes no pointer from an `anticipy_says` row
   back to the line that caused it. Her half of an exchange cannot be
   attributed to his half except by matching a repeated goal string.
3. **`brain/`** — 23% of arriving lines (61 of 263 at 48h) carry an **empty
   `addressee`**. Triage returned no classification at all for nearly a quarter
   of everything heard.
4. **`overnight/`** — `is_the_brain_live.py` exits 0 on a totally deaf day.
   The fix is not inside it (every leg it has is denominated in her speech); it
   needs a leg denominated in his, i.e. this file with `--min-lines`.
5. **`brain/`** — `_workflow.source_event_ids` is present on 53 of 65 jobs but
   absent from 12. The write is conditional on `stitched_goal` in two of the
   three places `params` is built (`anticipy_core.py` ~1979 and ~2311), so a
   non-continuation job records no provenance.
6. **`tests/`, mine, noted not fixed** — `tests/test_day_zero_oracle.py`
   fails collection on a missing `playwright` module via
   `proof/day_zero_20.py`. Pre-existing, unrelated to this work, and it stops
   a bare `pytest tests/` from running at all.

## Running it

    python3 proof/outcome_rate.py                     # today, every owner
    python3 proof/outcome_rate.py --hours 48 --owner <owner_ref>
    python3 proof/outcome_rate.py --min-lines 1       # a gate: she was not deaf
    python3 proof/outcome_rate.py --min-rate 0.10     # a gate: the brain did something

Suite: 1650 passed (54 of them this file's), 0 failed, with
`--ignore=tests/test_day_zero_oracle.py`. Run with `PYTHONDONTWRITEBYTECODE=1
-p no:cacheprovider`.
