# The first words respect the night — stranger_gate leg 6

2026-08-25 · branch `jose_anticipy_system` · `brain/worker.py`, `tests/test_welcome.py`

Leg 6 of `overnight/stranger_gate.py`: **fail -> PASS**
(`the welcome consults quiet hours before it speaks — a quiet-hours branch at
brain/worker.py:318 that can stop the send`)

## What was wrong

`maybe_welcome_new_owner` is the very first text a stranger ever receives. It
runs off the 60-second profile beat in `main()` and consulted no clock, while
every other lane in the same file honours `CLOCK_QUIET_START`/`CLOCK_QUIET_END`
— the night digest, the clock lane, the overheard FYIs, the parked question,
the ambient acts. Eight sites. The one message that goes to somebody who has
never heard from her before was the exception.

People set up new things late at night. A stranger who finished onboarding at
1am got the product's first ever words as a phone buzz in the middle of the
night.

## What the leg forecloses

The leg reads a syntax tree and asks a behavioural question: **can the clock
stop this send?** A comment cannot answer it (a `# TODO: honour CLOCK_QUIET…`
once retired this leg); a helper can, because the leg follows a call into it.

And it names the lazy fix out loud: *"A held welcome must still be sent in the
morning: dropping it silently trades one bad first impression for no first
impression at all."* A guard that returns `False` and forgets is not a fix. It
is a stranger who never hears from the product at all — and it would have been
invisible, because the gate cannot see it.

That trap is real and specific here, not hypothetical. The second guardrail on
this function is **the profile must be younger than an hour**. Quiet hours are
ten hours long. So a bare `if _in_quiet_hours(now): return False` sends nothing
at 1am, and then at 08:00 the profile is seven hours old, the young-profile
branch fires, the number is stamped `welcomed_phones` *silently* — and the
stranger is marked as welcomed having never been welcomed. The naive fix does
not delay the hello. It deletes it, permanently, and stamps the deletion.

## What was built

**`_in_quiet_hours(now)`** (`brain/worker.py:73`) — the same night the rest of
the worker keeps, read through the same two constants. Deliberately not a
second, parallel notion of night.

**A hold, in the durable file** (`maybe_welcome_new_owner`). The state now
carries `welcome_held: {digits: created_ts}` beside `welcomed_phones`, in the
same `clock_state.json` the once-ever stamp already lives in:

- **1am** — fresh profile, quiet hours: record the debt, save, `return False`,
  log `welcome held for morning (quiet hours)`. **The number is NOT stamped as
  welcomed.** A stamp here is exactly the silent drop.
- **08:00 onwards** — a held number bypasses the young-profile guardrail (that
  guardrail exists to stop a long-standing owner being "welcomed" after editing
  settings; a hold is proof the profile *was* young when it was seen). Sends,
  stamps `welcomed_phones`, and clears the debt **in the same write** so no
  restart can land between the two and deliver twice.
- **Restart in between** — the hold is on disk, so the morning still happens.
  The delivery beat is the same 60-second profile beat; nothing new is
  scheduled.

**One bound: `WELCOME_HOLD_MAX_SECONDS = 24h`.** Quiet hours are a night, not a
queue. A worker that was down for four days must not open with "your very first
minutes with me" to somebody who onboarded on Tuesday — that is its own
"makes them say WHAT?". Past 24h the hold is stamped and retired, and it
**prints when it does**. The leg forbids dropping a first impression *silently*;
this one announces itself in the log the operator is already reading.

**The call site moved below the timezone refresh** (`main()`, worker.py:3411).
See below — this is the timezone fix, not a tidy-up.

## Whose night? — the timezone question, answered

The existing quiet-hours code assumes **one timezone: `CLOCK_TZ`**, and I
followed it rather than inventing a per-stranger clock.

That assumption is weaker than it looks, in a good way: every worker process is
bound to exactly one account (`ACTIVE_OWNER_REF`, worker.py:47, deliberately
process-local), and the 60-second profile beat rewrites `CLOCK_TZ` from *that
owner's* profile zone. So in a supervised worker this is the owner's own night,
not a server-wide one.

**But there was a hole precisely at the moment that matters.** The welcome call
sat *above* the zone refresh in the same block, so a stranger's very first beat
— the only evaluation that decides whether their first words arrive at 1am —
was judged against `ANTICIPY_TZ` (default `America/Vancouver`), before the
worker had read their zone. Moving the call below the refresh closes it. Every
later beat was already correct; the first one was not, and the first one is the
whole leg.

**Known limit, stated rather than inherited silently:** where the profile
carries no timezone at all, `fetch_owner_timezone` returns `None`, `CLOCK_TZ`
stays `ANTICIPY_TZ`, and that stranger is judged by the server's clock. A
stranger in Berlin with an empty zone column still gets Vancouver's night. The
fix for that is upstream — onboarding collecting a zone — not another clock in
here.

## HARNESS-LAWS

**Law 1 is not in play, and here is why explicitly.** Law 1 forbids a regex,
word list or threshold deciding what words MEAN. `_in_quiet_hours` is a
threshold on the **clock**, deciding WHEN a text may leave. No word is
classified; nothing is read for meaning; the sentence itself is still composed
by the model, unchanged, on both sides of the branch. Same instrument, same
constants, same justification as the eight sites that already do this.

**Law 2 — no tape.** Nothing here is an emergency string patch; there is no
`TAPE:` comment and none is owed.

**Law 5 — fix order.** This is structure, and it is reached legitimately: the
lane it governs has context (the profile beat), the constants already exist,
and nothing here writes a rule while she is deaf or blind.

## What is proven, and what is not — Law 3

**Proven by tests** (`tests/test_welcome.py`, 5 -> 12):

- 01:00 holds and 10:00 sends — the direction the gate explicitly cannot see
  ("leg 6 proves the clock CAN stop the welcome, not which side of it speaks").
  A guard written backwards has an identical syntax tree; these two tests are
  the only thing standing between the repo and a product that introduces itself
  exclusively at 3am.
- A hold made at 01:00 is delivered at 10:00 the same day, exactly once, even
  though the profile is by then nine hours old.
- The hold survives a restart: the state is round-tripped through
  `json.dumps`/`loads` in the test rig, so a hold that could not be written to
  the file fails here rather than in production.
- After delivery, a further restart sends nothing.
- A hold past its morning is retired, not sent four days late.
- `_in_quiet_hours` on its own: night at 01:00, day at 10:00, and the
  boundaries land on the constants themselves.
- A malformed `welcome_held` never crashes the profile beat.

Every one of the seven new tests was mutated to red and back
(guard inverted, helper forced to daylight, debt not recorded, debt not
cleared, expiry removed, hold never persisted, stamp written while holding,
type guard removed). No test survived its own mutant.

Full suite: **1784 -> 1791 passing**, 0 failed.

**Not proven, and it cannot be from here:**

- **Nothing is verified against LIVE.** The ears have been dead ~30 hours and
  production is running code that was never committed, so there is no honest
  way to say this behaves in prod. Repo-green is not done. This is a `(tree)`
  leg — it proves this checkout, not the deploy.
- **The clock has never actually been moved on a running worker.** The tests
  pin direction by injecting `now`; they do not prove the process behaves as
  the wall clock crosses 08:00. That needs a running worker, which is what the
  gate itself says about polarity.
- **No real SMS has been held and then delivered.** The transport is mocked in
  every test here.

## Smaller notes

- The tests in this file previously read `time.time()`, which made the whole
  file's result depend on what time of day the suite ran. After this change
  that would have been an outright bug — the existing fresh-onboarding test
  fails at 2am. Every `now` is now pinned by `_at(hour)` in the worker's own
  zone. This suite runs overnight; that mattered within the hour.
- `first_name` is now read as `items[0]... if items else ""`. A held welcome
  reaches the compose step on a beat where the profile row could be missing,
  which the old ordering made unreachable and the new one does not.
- Cruft, not a bug: if the owner changes their phone number between a hold and
  its morning, the old number's entry lingers in `welcome_held` until nothing
  ever reads it again. It is never consulted for a different number. Pruning it
  would mean sweeping every key on every beat; not worth it for a file with a
  handful of entries.
- The other eight quiet-hours sites still inline the comparison. They could
  adopt `_in_quiet_hours` and probably should, but not in this diff — other
  agents are in this file tonight and several gate legs read it by line number.
