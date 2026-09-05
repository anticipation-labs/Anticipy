# Omi port 06 — one decision is bounded: 150 s, 32 calls; one turn hears for 300 s

Built 2026-09-05 from the port-06 brief's ATTACK `corrected_mechanism`. This
file is the Law-4 record of what was built, what each absent/expired case
lands on and why that is the safe side, the residuals the attack named, and
the live leg that closes it. The coverage ledger row
(research/2026-09-04-omi-port-coverage.md, rows 06 and 09) is the
integrator's to flip; the polarity corrections the attack asked for are
recorded here rather than there.

## What was missing, measured

The only bound anywhere beneath the transcript loop was one attempt's 60 s
inactivity timeout in `brain/llm.py:_post_json` (`httpx.Client(timeout=60)`,
three attempts). Per call, per attempt. One heard line walks 12–16
sequential calls — extraction, up to five triage asks, party, world, settled,
sufficiency, one memory fill PER GAP (a count the model's own `missing` list
decides), calendar, voice — and every single-question caller swallows its
own transport error and walks on. Driven in the test rig with the real
client, brain, memory and core, the ordinary chain for "book us dinner at
Cactus Club Thursday" (owes=owner, touches=world) is 4 requests —
extraction, triage, sufficiency, voice; other shapes add party, world,
settled, calendar and the strong second opinion, the 12–16 measured live —
and the same line with sixty `missing` items and a memory fact for each is
63.

- A provider answering slowly-but-successfully at 50 s a call never tripped
  the timeout (it is per read on each of connect/read/write/pool, not a
  total) and walked the whole chain: 10–15 minutes for one line.
- A provider that hung after triage answered cost 3 × 60 s at EACH remaining
  question: ~30 minutes for one line.
- With `BATCH = 20` such lines in one poll turn, `handle_inbound` — the ONLY
  path that reads his yes/no to a question she already asked — plus the
  digests, research, stuck-job asks and finished-job reports were not looked
  at for the duration. One owner, one worker process, one thread.

## What replaced it

`brain/llm.py` ("the budget" section):

- `DECISION_DEADLINE_SECONDS = 150`, `DECISION_CALL_CEILING = 32`, in code
  not env (a stray env value switching a bound off in silence is the
  `ANTICIPY_SEGMENTS` failure the worker's own comment records).
- `Budget(deadline, calls_left, spent)` in a `ContextVar`;
  `decision_budget()` installs one or yields the active one (nesting never
  widens) and resets it in `finally` — the load-bearing line, see "the leak"
  below — and records the closed budget's `spent` for the worker to stamp.
- `LLM.chat` opens with `_spend()`: the slot is reserved BEFORE the request
  leaves (Omi's ordering), raising `DeadlineExceeded(TimeoutError)` when the
  clock is spent and `CallCeilingExceeded(RuntimeError)` when the count is.
  Every instance (main, `Brain.strong`, aux, memory's) and every mode
  (gemini, openrouter, heuristic) is counted; with no budget active it is a
  no-op.
- `_post_json` opens each attempt with `timeout=min(60, remaining)` and,
  on BOTH retry paths (status and transport), refuses to sleep into a retry
  once the deadline is spent. `_RETRY_ATTEMPTS = 3` stays; the deadline now
  bounds the retries rather than the retries defining the bound.
- NOT added: `"max_tokens": 2048` on the OpenRouter payload. On OpenRouter a
  reasoning model's hidden tokens count against `max_tokens`, and the strong
  second opinion would truncate into `orchestrator.py`'s `except Exception:
  pass` with no log — the Tejas-call shape. Ship it separately, if at all,
  after the ledger's `reasoning_tokens` column says what the live strong
  model spends, with `reasoning: {exclude|max_tokens}` set beside it.

`brain/anticipy_core.py`: `hear` and `clock_tick` are budget wrappers —
public signature and docstring on the wrapper (so the worker's `except
TypeError` fallback fires on a kwarg mismatch exactly as before), body in
`_hear` / `_clock_tick` byte for byte. Nothing else in the core changed:
not one verdict function, prompt, or single-question caller.

`brain/worker.py`: `TURN_HEARING_SECONDS = 300` and the pure
`turn_has_time(started, now)`; the per-event loop checks it at the top of
every iteration BEFORE `claim()` and `break`s. The `hear()` call is
bracketed with a monotonic clock, and `mark_processed` carries
`heard_ms` and `heard_calls` (added only when measured — absent, never 0).
`record_failure` is untouched: it must not PATCH, because a PATCH resets the
ten-minute stranded clock. Startup prints
`budget=150s/32calls/turn300s` beside `brain=`.

`backend/pb_migrations/1700000056_events_heard.js`: the two number fields.

`overnight/is_the_decision_bounded.py`: the live leg (below).

## Polarity — what each absent or expired case lands on

DEADLINE SPENT BEFORE TRIAGE HAS ANSWERED. `memory.ingest`'s extraction is
inside `except Exception`; triage's two `chat` calls are outside any try;
`_decide` is called bare. So `DeadlineExceeded` escapes `hear`, the worker's
`except Exception as e: record_failure(...)` sees a `TimeoutError`,
`unreachable_model` is True, nothing is stamped, `release_stranded_claims`
hands the line back in ten minutes, `DEAF_STREAK` climbs and he is told at
three. 150 s is a quarter of the ten-minute window, so a bounded line can
never be reclaimed under itself. Safe side, and strictly better than today.

DEADLINE OR CEILING SPENT AFTER TRIAGE. Every later `chat` raises instantly
at zero cost and each caller's existing `except Exception` returns its
inert state: `party_verdict` → PARTY_UNANSWERED (attribution untouched);
`work_is_licensed` → LICENCE_UNANSWERED (refuses: a floor);
`calendar_plan_verdict` → CALENDAR_UNANSWERED (never the phone lane);
`ends_in_the_world` / `plan_is_settled` → False (the pinned quiet collapse,
tests/test_ends_in_the_world.py, unchanged); `check_sufficiency` → []
(waves through — but `is_consequential(goal, touches=decision.touches)` is
evaluated from triage's already-answered declaration and `_IRREVERSIBLE_RE`
outranks everything, so a world goal is still HELD); `fill_gaps_from_memory`
leaves the gap unfilled and it rides on the card's `params["missing"]`,
where the one text names it — measured in the rig: 60 gaps, 32 requests,
gaps 29–59 asked. `_voice` → None, so the owner receives the TEMPLATE ask
through `say_handling`, and on the DEGRADED path `asking.question_line`
carries the registered `[tape:third_person_drop]`. Not new — a 5xx does the
same today — but written down: a spent budget routes asks through named
tape.

CEILING SPENT BEFORE TRIAGE. Unreachable on the hear path: the memory judge
(`_relate_fact` → `_JUDGE_BATCH` loop) runs only from `remember_fact`
(worker callers) and nightly `consolidate`, never from `ingest`. If it ever
became reachable, `CallCeilingExceeded` is not a `TimeoutError`, so
`record_failure` tombstones `error` — the right side: the same words through
the same code would hit the same count every ten minutes forever, and a
tombstoned row is visible where a held one is not.

TURN BOUND SPENT. `break` before `claim()`: no claimed row is abandoned,
the rest keeps `decision=""` and `fetch_unprocessed` returns it next turn
in the same `capture_key` order. The honest bound is 300 s PLUS the line in
flight: at most 300 + 150 + one attempt of dribble.

SMS LANE (`conversation.py:_think`). `except Exception: return None`
swallows a spent deadline: `_think` returns None, `on_reply` falls through,
`handle_inbound` marks the row with an intent. NOT held, not retried —
today's behaviour for any exception on that lane, and the design's earlier
"held" claim for this lane was false. Recorded as-is.

NO BUDGET ACTIVE (research, briefings, nightly consolidation, `remember_fact`,
anything outside `hear`/`clock_tick`). `_spend` is a no-op; behaviour is
today's. An absent cost bound is not a reason to refuse work, and a
process-wide default would silently cap those with no reset point.

TRANSPORT DIES MID-CALL. Same httpx classes, same handling. A provider that
dribbles bytes can overrun the deadline by at most one attempt, because the
read timeout is per read — which is why the live gate allows 150 + 60 s.

THE LEAK. An exception leaving `hear` is a designed path (deadline before
triage). Without `finally: _BUDGET.reset(token)` the spent budget would stay
installed in the worker thread and every later `LLM.chat` in the process —
the next line's extraction, research, digests, the clock, the apology in
`handle_inbound` — would raise instantly: every line held, `DEAF_STREAK` at
three, one text, mute until redeploy. tests/test_decision_budget.py leg 8
asserts the ContextVar is clear after the escape and that a bare chat reaches
the provider; its mutation is a bare `yield`.

LIVE SCHEMA LACKS THE COLUMNS. The brief said "PocketBase drops the
unknown field, `mark_processed` still lands the decision" — TRUE of
PocketBase, FALSE of the live backend. Production runs the Cloudflare
Worker over D1 (`migration/workers/src`, schema `migration/d1/schema.sql`),
and `records.ts:update()` answers **400 `unknown_field`** for any key
outside its column map (`pb/schema.ts`, `events`), which today has neither
`heard_ms` nor `heard_calls`. A stamp that insisted on them would have left
EVERY decision unlanded — the row at "processing", handed back by the
ten-minute sweep, heard again with a duplicate job and text each time: the
2026-07-30 six-jobs-from-one-line failure by a new road. So
`mark_processed` retries once WITHOUT the measurement on a 400 (an HTTP
status; never the error's words), lands the decision, and sets
`_HEARD_COLUMNS_ACCEPTED = False` for the rest of the process — one extra
round trip, once per boot, only on a backend without the columns. A 5xx or
a timeout is not about the keys and is not retried (False, as today). Both
directions are pinned in tests/test_decision_budget.py.

What `backend/pb_migrations/1700000056_events_heard.js` does: adds two
optional number fields, `heard_ms` and `heard_calls`, to PocketBase's
`events` collection. It is the PocketBase half only. **The D1 schema needs
the same two columns** — `"heard_ms" REAL NOT NULL DEFAULT 0` and
`"heard_calls" REAL NOT NULL DEFAULT 0` on `events` in
`migration/d1/schema.sql`, AND `heard_ms: N, heard_calls: N` in the `events`
column map of `migration/workers/src/pb/schema.ts` — or the Worker keeps
answering 400 and the live leg stays UNPROVEN forever. Not touched here
(migration/ is not this port's to edit); recorded for the integrator.

## Merged onto ports 09b and 10a (2026-09-05)

Port 09b made the second credential a fallback: `LLM.chat` →
`_transports` → `_fall_through`, which catches any exception from the
primary, remembers a TRANSPORT-typed one as "the primary is down" for 60 s,
and tries the fallback. `DeadlineExceeded` is a `TimeoutError`, so without
a carve-out one decision running out of time would have put the primary
into cooldown for every OTHER line, tried the fallback with a 1 ms attempt,
and counted `both_dead` — a per-decision clock steering the wire. So
`_fall_through` re-raises `DeadlineExceeded` at all four sites: no
cooldown, no fallback, no tally, no print; the worker holds the line as for
any TimeoutError. A real fault with time left still falls through exactly
as 09b built it. Pinned both ways in
`test_a_spent_deadline_is_not_a_dead_primary`. `_spend()` sits above
`_transports`, so one `chat` is one reservation however many wires it
tries; the deadline still bounds both wires' attempts through
`_attempt_timeout()` and the pre-retry check.

## Residuals, named

1. **The duplicate card** (the attack's real ceiling blast radius).
   `_same_plan` asks the model only when words cannot tell (overlap < 0.5)
   and its no-verdict state is False. After the ceiling every running-job
   comparison at `_queue_job`'s `for j in self._running_jobs()` answers
   "different", so a re-mention of a plan already in motion mints a SECOND
   held card and a second text — the recorded five-copies failure, reachable
   by structure. Pinned BOTH WAYS in tests/test_decision_budget.py
   (`test_the_ceiling_reopens_the_duplicate_card_residual`): it goes red the
   day the residual is fixed or regressed. The fix is `_same_plan` carrying
   a fourth state and the caller absorbing on no-verdict for a RUNNING job
   (a duplicate card is an annoyance, a swallowed errand is a loss — but a
   running job is not swallowed by being absorbed into).
2. **The word-overlap sift becomes the only dedupe judge** on a
   ceiling-spent line (`>= 0.5` at `_same_plan`) — a threshold deciding
   meaning by default, already present, now reachable by a deterministic
   route. Law-1-adjacent; not extended here.
3. **The 32 is provisional.** The rig's ordinary chain is 6 calls; the
   gate prints max and p95 of `heard_calls` per day. Raise the ceiling before
   an ordinary line is ever seen within 25 % of it.
4. **No token budget.** Declined: `usage` is absent on some providers so a
   token counter could not fail safe; input is bounded by construction
   (`convo[-16:]`, `memory_notes(budget=600)`, `LINK_WINDOW = 40`); output is
   capped per call on Gemini and deliberately NOT on OpenRouter (above).

## The live leg (Law 3)

`python3 overnight/is_the_decision_bounded.py` — read-only, never requests
`text`, `--self-test` 9/9. Over the last 24 h of decided transcript rows:
UNPROVEN (exit 2) when no row carries a measurement; RED naming rows when
any `heard_ms > 210 000` or any `heard_calls > 32` — the second is impossible
if the deployed worker enforces the ceiling, so it is the positive control
that turns weather into proof; GREEN otherwise; always prints rows, max and
p95 of both, and "bound fired: N" (a line cut AT the bound is the bound
working). Paired with the deploy proof: the live worker's startup line
prints `budget=150s/32calls/turn300s` beside a `brain=` fingerprint equal to
`_brain_fingerprint()` in the tree, and the migration applied. This port is
not done until that gate is GREEN against the Railway worker.

## What an ordinary day pays

Zero new model calls, zero new texts, zero new rows. One `time.monotonic()`
read and one integer decrement per model call; two monotonic reads per heard
line; two integers on a PATCH that already happens. On a day where no
decision exceeds 150 s / 32 calls and no turn exceeds 300 s — every recorded
ordinary day: 12–16 calls at 2–4 s — the log, the rows (bar the two new
numbers) and the owner's phone are byte-identical to before.
