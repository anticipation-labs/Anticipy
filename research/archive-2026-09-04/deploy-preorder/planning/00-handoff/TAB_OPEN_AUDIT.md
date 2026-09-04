# TAB_OPEN_AUDIT (2026-05-29, owner: Omar)

Inventory of every code path that can open a Chrome tab inside the
shipping Anticipy engine + bridge. Built as part of the
`ANTICIPY_QUIET=1` kill-switch work so the engine can be restarted in
a fully passive mode for demos / debugging.

The bridge process (`anticipy_bridge_fallback_cdp.py`) lives in
`scripts/v7/` and runs as a separate process on `:7777`. It is the
only thing that ACTUALLY speaks CDP to Chrome on `:9222`. Every
engine path that opens a tab eventually reaches one of:

  - `Target.createTarget` (background CDP RPC, via the bridge OR via
    direct WebSocket)
  - `Chrome /json/new` (HTTP shorthand for Target.createTarget)

Tabs are NEVER opened in response to a user click in the popover
unless the user explicitly issued a command. The "phantom tab"
behaviour Omar reports is from the proactive paths below.

## Inventory

| # | File | Line | Function / trigger | Trigger source | Proactive vs on-demand |
| - | ---- | ---: | ------------------ | -------------- | ---------------------- |
| 1 | `engine/app/coldstart/cdp_walker.py` | 147 | `_cdp_create_new_tab` -> `/json/new` (PUT then GET) | called from `CDPWalker._open_anticipy_tab` on every `walk_gmail` / `walk_calendar` / `walk_drive` | PROACTIVE when triggered by inhale orchestrator (#2) or calendar prep scheduler (#3) |
| 2 | `engine/app/coldstart/auto_inhale.py` | 716 | `start_inhale` spawns background `anticipy.coldstart.inhale` thread that opens 2-4 tabs (Gmail inbox, Gmail sent, Calendar agenda, optionally Drive) | `/api/coldstart/start` HTTP route | ON-DEMAND (popover sends the call), but the popover may auto-call it during onboarding |
| 3 | `engine/app/product/calendar_prep.py` | 1024 | `start_scheduler` spawns `anticipy.calendar_prep.scheduler` thread; every 300 s it runs `find_upcoming_meeting` -> opens Calendar tab; then `prep_meeting` -> opens Gmail search tab + Drive search tab | startup hook in `engine/app/product/server.py:11283 _start_calendar_prep_scheduler` (auto-fires unless `ANTICIPY_CALENDAR_PREP_DISABLE=1`) | PROACTIVE, default-on, fires every 5 minutes for the engine's lifetime. **Primary culprit.** |
| 4 | `engine/app/action_engine/dsv4_skill_runner.py` | 126 | `_ensure_agent_window` opens a dedicated `about:blank` background window once, reuses it | `DSv4SkillRunner.run` invoked from `engine/app/universal/action_loop.py:run_universal_loop` | ON-DEMAND (user-issued action). Idempotent; one window total. |
| 5 | `engine/app/universal/action_loop.py` | (helper) | Calls `DSv4SkillRunner.run`, which reaches #4 | popover "Run on Chrome" path | ON-DEMAND |
| 6 | `scripts/v7/anticipy_bridge_fallback_cdp.py` | 471 | `_cdp_create_target` (the real CDP `Target.createTarget`) | called from `_cdp_navigate` (`560`) when `prefer_in_place=False` OR when no Anticipy-owned tab exists for the host | ON-DEMAND (driven by `/surface-command navigate` from engine code paths #2/#3 above) |
| 7 | `engine/app/product/surface_dom_extractor.py` | 126 | `POST /surface-command navigate` | called by the action engine + surface runtime when the agent needs a new page | ON-DEMAND |
| 8 | `engine/app/product/universal_surface_runtime.py` | 192 | `POST /surface-command navigate` | universal runtime | ON-DEMAND |
| 9 | `engine/app/product/surface_runtime.py` | 240+ | navigate / navigate-then-extract primitives | surface runtime, called from action dispatcher | ON-DEMAND |

## Background loops in the bridge (`anticipy_bridge_fallback_cdp.py`)

The bridge itself runs a single `while True` (line 888) that drives
the persistent CDP WebSocket reader. That is plumbing, not a tab
opener. No periodic / cron loop in the bridge opens tabs on its own.
Tabs are only opened in response to an HTTP request from the engine.

## Tabs that open WITHOUT explicit user request (the "phantom" set)

After tracing the call graph, two paths can open tabs without a
direct user action:

  1. **Calendar prep scheduler (#3)** runs every 5 minutes after engine
     start. Each scan opens a fresh Calendar tab. If a meeting falls
     in the next 30 min window, it ALSO opens a Gmail search tab plus
     a Drive search tab. Default-on. **Loudest source of phantom tabs.**
  2. **Cold-start inhale (#2)** fires when the popover hits
     `/api/coldstart/start`. The popover triggers this on welcome
     flow. The orchestrator opens Gmail inbox, Gmail sent, and Google
     Calendar tabs. Single-shot per popover open, but still surprising
     for the user during onboarding.

Everything else (#4 once-per-process, #5/#7/#8/#9 user-driven) is
allowed through `ANTICIPY_QUIET=1` because it ONLY fires from an
explicit user request.

## Kill-switch design

A single helper `_quiet_mode_enabled()` lives in `engine/app/config.py`.
It reads the `ANTICIPY_QUIET` env, treats `1`/`true`/`yes`/`on` as
enabled, anything else as disabled.

The gates:

  - `engine/app/product/server.py:_start_calendar_prep_scheduler`:
    if `_quiet_mode_enabled()`, log `quiet_mode_skipped path=calendar_prep_scheduler`
    and return early. (Wraps the existing
    `ANTICIPY_CALENDAR_PREP_DISABLE` check.)
  - `engine/app/coldstart/auto_inhale.py:start_inhale`: if
    `_quiet_mode_enabled()`, log `quiet_mode_skipped path=coldstart_auto_inhale`
    and return an idle state snapshot without spawning the thread.
  - `engine/app/product/calendar_prep.py:start_scheduler`: if
    `_quiet_mode_enabled()`, log `quiet_mode_skipped path=calendar_prep_start_scheduler`
    and return an idle snapshot without spawning the loop. Defence
    in depth in case start_scheduler gets called from a route
    (`/api/calendar/prep/scheduler/start`) bypassing the startup
    hook.

Anything below the proactive scheduler / inhale (#4-#9 above) stays
unchanged: those paths only fire from an explicit user action.

