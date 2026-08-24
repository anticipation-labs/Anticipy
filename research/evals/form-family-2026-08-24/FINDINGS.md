# The form family, re-measured after submissionDigest

13 form tasks, 1 pass, 34 minutes, one paired Chrome for Testing 152.0.7977.54
running extension 0.11.0 against the deterministic fixture on :8899. Model
`google/gemini-3.1-pro-preview` via `/agent/llm`. Results:
`proof/battery/results/form-recheck.jsonl`.

Why this run exists: `TESTING-PASS-2026-08-21-ROUND2.md` §3 measured the form
family at **43.6% (17/39)** and diagnosed it as "the three-step permit flow
stops rather than commits". That measurement predates `submissionDigest`
(`cf4b5e3f`), so the number was stale in both directions and nobody knew which.

## The scoreboard

```
TASK SUCCESS      53.8%  (7/13)   target 80%   NOT MET
TIME TO DONE      median 1m51s · p90 4m06s
MODEL DECISIONS   median 8 per run · p90 31
RECEIPTS          100% of done runs carried a verified receipt
MODEL FAULTS      0%
VISION            used in 23.1% of runs
```

**Do not read 43.6% -> 53.8% as an improvement.** n=13 against n=39, one pass
against three, and a different browser and model. The number is not the finding.

## The finding: two of the six failures are finished work, reported as unfinished

The battery records the fixture's own ledger next to each result, and that is
what settles it. `--only=form`, per task, permits filed:

| task | status | expected | permits in the ledger | run |
|---|---|---|---|---|
| ext-b-permit-riverside-commit | needs_user | done | **1, correct** (zone B, 18 Kestrel Row) | 363.5s |
| ext-b-permit-zone-c-start-date | needs_user | done | **1, correct** (zone C, 4 Hillcrest Way) | 363.5s |
| ext-b-permit-report-the-bounce | needs_user | done | 0 | 369.5s |
| form-verify-code | needs_user | done | 0 | 18s |
| ext-b-verify-side-trip-inbox | needs_user | done | 0 | 9s |
| ext-b-permit-readonly-dry-run | needs_user | needs_user | 0 | 54.1s |

The first two did the work. The permit is filed, once, with the right values.
Then the run spent the rest of its six-minute budget trying to do it again,
was correctly refused every time, and handed back:

> "I have been at this a while and I have used up the time I am allowed to work
> on my own."

So behavioural success is **9/13**, not 7/13, and what is broken in those two
is the REPORT, not the errand.

## Why they could not stop

`ext-b-permit-riverside-commit`, the last eight steps:

```
step 24: {"action":"click","index":3}
step 25: {"action":"click","index":3}
step 25: BLOCKED DUPLICATE EFFECT — this same consequential control was already
         dispatched once and nothing it sends has changed since.
step 26: looking at the page as well as reading it — the last step got nowhere
step 26: {"action":"type","index":0,"text":"18 Kestrel Row","enter":true}
step 26: BLOCKED DUPLICATE EFFECT — this form, with exactly these values, was
         already submitted once.
step 27: {"action":"click","index":2}
step 28: {"action":"click","index":3}
step 28: BLOCKED DUPLICATE EFFECT — ...
step 29: {"action":"click","index":2}
step 30: {"action":"click","index":3}
step 30: BLOCKED DUPLICATE EFFECT — ...
```

Four refusals in six steps, alternating the click path and the Enter path, and
the ledger stayed at one permit throughout.

## What this says about the safety guarantee: IT HELD

This is the good news and it should be recorded as loudly as the defect.
`submissionDigest` was written after one double booking in 306 runs. Under this
run it refused **five or more** repeat dispatches of an already-sent payload,
across BOTH the click and the Enter path, and the fixture ledger ended with
exactly one permit every time. The cross-path collapse works in a live run, not
only in `extension/tests/test_one_submission_two_keys.mjs`.

It also did not break the wizard: `form-permit-file` and `form-terms-box` both
completed through the same multi-step form on the same URL, which is the
regression a `url + formAction` key would have caused (ROUND2 §3 predicted
exactly that, and it is why the key digests VALUES).

## So the fix direction is the opposite of loosening the key

The tempting read of "blocked four times then gave up" is that the duplicate
guard is too strict. It is not. Loosening it re-opens the double booking, and
the two tasks above prove the guard is the only reason the ledger has one row
instead of five.

The actual defect is that **a duplicate-effect refusal is not being read as
evidence.** If this exact payload was already dispatched, the effect almost
certainly happened — that is what the guard knows and the message already says
out loud ("inspect the current state"). The agent's response is to click again.
The block should route into the verification path that `done` already uses, and
turn into a receipt, instead of being one more dead step against the clock.

**Not implemented here, deliberately.** It is a change at the commit-integrity
seam on the evidence of one 13-task pass, which is the same call ROUND2 §3 made
and for the same reason. What it needs first:

1. A repeat pass (`--only=form --passes=3`, 39 runs, ~1h45m) so this is measured
   against the number it is meant to move, on the same shape as the original.
2. A decision on what counts as verification. `verifyDone` already exists; the
   question is whether a blocked repeat may CALL it, or whether that risks
   reporting `done` off a block that fired for some other reason.
3. `ext-b-permit-report-the-bounce` (0 permits after 35 decisions) must be
   separated out — it burned the same budget on the same blocks but never
   landed the permit, so it is not the same bug and would be hidden by a fix
   that only improves reporting.

## The other three failures are three different things

- **`form-verify-code` and `ext-b-verify-side-trip-inbox`** — 18s and 9s, ONE
  decision each, `needs_user` at step 0: *"a 6-digit code just went to your
  email to finish this — want me to open your inbox and read it, or will you
  paste it?"* The side trip was never attempted. `ext-b-verify-side-trip-inbox`
  is named for that side trip and expects `done`, so either the minted approval
  does not authorise the inbox (`inboxAuthorized(scope)`,
  `agent_loop.js` side-trip branch) or the model asks before it tries. One
  cheap experiment separates those: mint the same task with the inbox
  explicitly in scope and see whether step 0 changes.
- **`ext-b-permit-readonly-dry-run`** — not a behaviour failure at all. The
  read-only refusal is exactly right and fires at the right control ("the
  *Review* button ... which would act in the world"). It fails the scorer's
  PHRASING contract: the sentence matches none of `/you/ /confirm/ /approve/
  /before i/ /say the word/ /ok/`. A refusal that does not tell the person what
  to do next is a copy defect worth fixing on its own, and it is a one-line
  change to a string rather than anything structural.

## Rig note, because it cost the first hour

The local rig would not boot: PocketBase started, wrote NOT ONE BYTE of log,
never bound 8090. `pb_data/auxiliary.db` was **1.0GB behind a 656MB WAL**.
`backend/start.sh:12` drops that file on every container boot precisely because
it is the proven runaway grower (`1700000038_log_db_footprint.js`), but
`proof/local_rig.sh` starts the binary directly and never had the same guard.
Added there now. The symptom is worth remembering: an empty `pb.log` reads as a
bad binary or a bad hook, and is neither.
