# Plan execution validation summary

Date: 2026-05-27 (UTC 2026-05-28T04:08:04Z)
Run dir: `state/v7/plan_execution_validation_20260528T040804Z/`
Validator: `scripts/v7/plan_execution_validator.py`
Source E2E run (plan generation only):
`state/v7/e2e_hard_transcripts_20260528T031414Z/`
Engine: `http://127.0.0.1:8731` (the installed `/Applications/Anticipy.app`
backend, pid 37580). Bridge: `http://127.0.0.1:7777`, kind=`cdp_primary`,
cdp_alive=true.

## Background

The prior end-to-end run scored 20 hard transcripts and verified that
the engine GENERATED a plan for each. It did NOT verify that the plan
EXECUTED. This validator closes that gap by:

1. Re-injecting the transcript into the live engine
   (`/api/listen/inject`).
2. Posting `/api/act` to trigger the engine's confirm-card / action
   path on the populated `_LISTEN["pending"]`.
3. Probing the user's real Google Calendar (and Gmail when relevant)
   via CDP `Target.createTarget {background:true}` on
   `http://localhost:9222`, scanning the rendered results pane for
   the literal event title or recipient.
4. Closing every tab the validator created via CDP
   `/json/close/<targetId>` so no user tabs are mutated and no new
   tabs leak.

R4 browser safety is enforced end-to-end: validator-created tabs are
identified by `targetId`, never by `url_prefix`. The bridge's
prefer_in_place navigate path is bypassed because it can silently
re-target an existing same-host user tab.

## Plans tested

| ID  | Intent          | Category | Verdict   | Reason                                           |
| --- | --------------- | -------- | --------- | ------------------------------------------------ |
| T01 | other           | calendar | FAILED    | engine returned `clarify`; calendar has no event |
| T03 | calendar_event  | calendar | FAILED    | engine returned `gated: No real Chrome on :9222` |
| T04 | calendar_event  | calendar | FAILED    | engine returned `gated: No real Chrome on :9222` |
| T20 | other           | calendar | FAILED    | engine returned `gated: No real Chrome on :9222` |
| T05 | clarify         | unknown  | SKIPPED   | plan mode is `clarify`; not an `act` plan        |

`FAILED` here means "the engine never actually created the calendar
event the plan proposed." Verified by searching the user's real
Google Calendar via CDP and getting "No events found" or matching
zero rows in the `[role=main]` results pane.

## What the verdicts mean

The 4 calendar plans all looked plausible on the surface in the prior
E2E run (HTTP 200, intent extracted, plan emitted). The validator now
demonstrates that none of them produced a real-world side effect on
the user's Chrome:

- T01 (Dentist appointment): on re-inject, the engine asked a
  clarifying question instead of acting. Calendar search confirms no
  matching event exists.
- T03 / T04 / T20: on re-inject + `/api/act`, the engine returned
  `gated: true` with the error
  `"No real Chrome on :9222 and the launchd agent could not be kicked"`,
  even though CDP IS up on 9222 (the bridge's `/status` reports
  `cdp_alive: true`). The engine's `_ensure_cdp_chrome` runs with
  `CDP_PORT=0` because the installed-app launchd unit doesn't pass
  `ANTICIPY_CDP_PORT`. So the engine's action layer is wired but
  disabled: it never reaches `make_real_action_engine`. Calendar
  confirms zero matching events for every probed title.

T05 was deliberately included as a control case: its prior plan was
`mode=clarify`, so the validator correctly short-circuits with
`engine_skipped: true` and opens zero tabs.

## Tab inventory (R4 audit)

| Metric                   | Value |
| ------------------------ | ----- |
| Tabs opened by validator | 4     |
| Tabs closed by validator | 4     |
| Tab leakage              | 0     |

Tabs are opened via `PUT /json/new` (Chrome's `Target.createTarget`
shorthand) and closed via `GET /json/close/<targetId>`. The
validator's `result.json` also captures the full set of tabs
observed before vs after the run for forensic review.

## Headline takeaway

Plan GENERATION is real (the existing E2E proved that). Plan
EXECUTION on the installed-app engine is currently a no-op:
`/api/act` either asks a clarifying question or is gated by a
misconfigured `ANTICIPY_CDP_PORT`. The validator's evidence (per-plan
screenshots of the empty Calendar search pane plus structured
`result.json`) is on disk under
`state/v7/plan_execution_validation_20260528T040804Z/`.

The fix is downstream of this validator: pass `ANTICIPY_CDP_PORT=9222`
to the installed engine's launchd plist, then re-run the validator.
The next pass should show calendar event matches for the plans that
the engine actually fires.
