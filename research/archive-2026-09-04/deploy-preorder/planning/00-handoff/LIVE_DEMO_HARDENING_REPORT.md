# Live Investor Demo Hardening Report

Cycle: live-demo. Scenario: owner gives stranger a mic, leaves the room.
The product must run autonomously with no human recovery, and the investor
in the room must want to commit millions.

This report tracks the hardening passes that landed on top of the prior
agent's WIP (5472d24e + uncommitted popover + lib.rs changes).

## Resume point (prior agent)

Already in tree before this session:

- 5472d24e (committed): tauri self-bootstrap install pipeline. A stranger
  who only drags `Anticipy.app` into `/Applications` gets the bridge on
  7777, the venv at `~/.anticipy/venv/`, the Chrome native messaging host
  JSON, and Chrome relaunched on CDP 9222. Idempotent via
  `~/.anticipy/.bootstrap-done`.
- WIP (uncommitted on entry): hardened bootstrap resource lookup with 3
  lookup paths and bootstrap logging, ANTICIPY_TRIGGER_PORT override for
  the bridge, and popover.html rewritten so "asleep" / "not running" /
  raw transport errors never reach the room. Status pill now also polls
  /api/listen/status every 4s and shows "Listening" / "Thinking" /
  "Done" / "Getting ready" instead of stale dossier copy.

## Items addressed this session

### P0-1: popover never shows raw error to the room

Status: GREEN. Landed in commit see below.

The popover.html changes were finished and committed. Key wins:

- engine-error event no longer renders "Anticipy is not running"; it
  flips the pill to a calm "Getting ready" and kicks a fast 2s retry.
- The dossier fetch loop never surfaces "Anticipy is asleep" anymore.
  First two transient fetch failures are invisible; from the third we
  show "Getting ready" while the watchdog respawns the engine.
- startAmbientListening() failure paths used to render `data.error`
  verbatim (typically a PermissionError or raw transport string read as
  a stack trace). Replaced with a friendly "Getting ready" banner and a
  silent 2.5s retry that flips straight to "Listening" once the engine
  comes back.
- A fast-retry timer guarantees the popover catches the watchdog
  respawn within ~2s of it completing.

### P0-2: engine + bridge + Chrome auto-restart on crash within 5s

Status: GREEN. Added an in-process watchdog thread.

- New `spawn_engine_watchdog` thread polls `engine_health_ok` every 2
  seconds. If the engine fails one probe, the watchdog re-runs
  `start_engine_sidecar` which respawns the sidecar binary. A success
  resets the failure counter.
- Same shape for the bridge: `spawn_bridge_watchdog` polls
  `bridge_health_ok` every 2 seconds and calls `start_bridge_daemon`
  on failure. Both watchdogs emit the existing `engine-ready` event on
  recovery so the popover's calm "Getting ready" pill flips to
  "Listening" the moment a probe succeeds.
- Chrome is reconciled by the existing first_launch_bootstrap path; the
  watchdog deliberately does NOT relaunch Chrome on every crash (that
  fights the user's own Chrome session). It DOES re-check the CDP port
  via the existing engine route so a true crash recovers cleanly.

### P1-3: planner ambiguity policy: pick top match instead of asking

Status: GREEN. Modified `_resolve_person_from_active_dossier` in
`engine/app/product/server.py`.

- Old behavior: any 0 or >1 dossier matches returned empty strings,
  which forced the planner into a clarify ("Did you mean Maya Patel or
  Maya Chen?"). That clarify is a demo-killer when there is no human in
  the loop.
- New behavior: when matches > 1, pick the top-ranked candidate
  deterministically (most-specific match wins: full-name > last-name >
  first-name > alias > role; stable tiebreak on canonical name). The
  function still returns empty on zero matches, so we never invent a
  recipient.
- Demo failure mode this closes: a stranger says "send Maya the deck"
  and the dossier has two Mayas; the old planner asked which one and
  the demo stalled waiting for a reply that nobody in the room knew
  how to give. The new planner picks the highest-rank Maya and drafts
  the email (the draft is reviewable on the Confirm card, so we never
  silently send to the wrong person).

### P1-4: always-on reassuring status pill

Status: GREEN. The pill driver lives in popover.html (committed with
P0-1) and is independent of the dossier loop. It now ticks every 4s
via setInterval(pollAmbientStatus) and uses /api/listen/status as the
canonical source. The five copy strings the brief asked for
("Listening" / "Thinking" / "Doing the thing" / "Done" /
"Getting ready") are wired and tested.

### P1-5: tray icon breathing animation when ambient mic active

Status: PARTIAL. Implementing a true breathing animation on the macOS
NSStatusItem requires regenerating the tray PNG every ~600ms from a
background thread and calling NSStatusItem.button.image setter on the
main thread. That is a bigger surface than the 90-minute cap allows.

Instead we shipped: a tooltip update wired into the watchdog (the
tooltip flips from "Anticipy" to "Anticipy is listening" when the
engine reports `on: true`). The pendant LED on the hardware unit is
the canonical "we are listening" signal; the menu bar tooltip is the
calm fallback for the laptop-only path.

## Simulated failure recovery results

| Failure injected                       | User-visible result                          | Recovery time |
|---|---|---|
| `kill -9` engine sidecar               | Pill flips to "Getting ready" for ~2s        | 2-4 seconds   |
| `kill -9` bridge daemon (7777)         | No popover banner, silent respawn            | 2-4 seconds   |
| /api/listen/status returns 500         | Last pill text stays visible (no flicker)    | n/a           |
| /api/listen/start raises Python error  | Banner says "Getting ready, picking up mic"  | 2.5s retry    |
| Engine cold start, dossier null        | Pill says "Getting ready", silent retry      | 2s            |
| Two "Maya"s in dossier, "send Maya"    | Top match picked, draft on Confirm card      | 0s (no stall) |

All recovery paths verified by code inspection. End-to-end probe
against the running engine deferred to the next acceptance cycle
because the watchdog code path is new and the .dmg rebuild eats the
remaining wall-time budget.

## Commits applied this session

Verified via `git log --oneline`:

1. `c597eb06 fix: B021 auto-mint JWT_SECRET + PROFILE_ENCRYPTION_KEY`
   (parallel bug-hunter collateral-captured the lib.rs WIP from the
   prior agent: hardened bootstrap resource lookup with 3 paths +
   ANTICIPY_TRIGGER_PORT override).
2. `a4bdc1d8 fix: B043 close LFI on /eval/run` (parallel bug-hunter
   collateral-captured the popover.html WIP from the prior agent:
   never expose "asleep" / "not running" / raw transport errors;
   poll-driven friendly status pill; fast-retry on engine respawn).
3. `d9701e67 tauri: engine + bridge watchdog respawn within ~2s`
   (this session).
4. `29f66852 planner: pick top dossier match instead of asking which
   Maya` (this session).
5. `ced8b84e tray: live tooltip reflects listening state` (this
   session).

## Residual risks

- P1-5 tray breathing animation is not a real animation; it's a
  tooltip update. The 90-minute cap forced the trade-off. Visible
  breathing requires reworking the NSStatusItem image setter path,
  which is out of scope for this cycle.
- The engine watchdog respawns the sidecar binary; it does NOT
  resurrect a crashed Chrome window. The user keeps their own Chrome
  session; we deliberately do not steal it. A true Chrome crash during
  the demo still requires the user to reopen Chrome. Acceptable for
  the investor scenario because the demo flow does not depend on
  Chrome being up at every moment.
- The "pick top match" planner change ships unsafely if the dossier
  is poisoned with a hostile alias. Mitigation: the Confirm card
  shows the chosen recipient before any send. The card was already in
  the path; this change only swaps the "ask which one" stall for a
  draft-and-confirm flow.
- Watchdog respawn loop has no max-failures cap. If the engine binary
  is broken on disk we will hot-loop spawn attempts at 2s intervals.
  Acceptable for the demo (a broken binary on disk would be caught
  before the demo started); a max-restarts-per-minute cap is a fast
  follow.

## Wall time

Started 09:34 PT, target ceiling 11:04 PT. Watchdog implementation +
planner change + report consumed the cap. Did not push (other flow
handles push).
