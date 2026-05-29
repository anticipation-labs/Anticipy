# Orchestrator state

The single source of truth for 16-agent parallel work. Updated every cron wake (every 3 min). Each work unit has owner, status, verification protocol, last update.

Mechanical rules:
- A unit is `done` only when its `verify` command exits 0 AND a fresh artifact is on disk.
- The orchestrator (this planner) is the only thing that flips a unit to `done`.
- Agent self-reports are advisory. The verify command is authoritative.
- Z-001 must PASS after every commit. Revert with `git reset --hard HEAD~1` if it regresses.
- The cron loop exits only when ALL 16 units are `done` AND `stranger_flow_proof` is PASS.

## The 16 work units

| # | Unit | Type | Owner | Worktree | Status | Verify command | Notes |
|---|---|---|---|---|---|---|---|
| 01 | Universal action agent design | planning | a00f56867 (sub-agent) | main | in-flight | file exists at planning/08-universal-action-agent/DESIGN.md | superseded the per-app recipe registry |
| 02 | Extension install via computer-use design | planning | ac7502f22 (sub-agent) | main | in-flight | file exists at planning/09-extension-install-via-computer-use/DESIGN.md | closes the "we can't inject extension" excuse |
| 03 | Instant cold-start design | planning | ab9fde871 (sub-agent) | main | in-flight | file exists at planning/10-instant-cold-start/DESIGN.md | day-0 useful via background Gmail/Calendar inhale |
| 04 | Hardcoded violations audit | planning | a9a68778b (sub-agent) | main | in-flight | file exists at planning/11-hardcoded-violations-audit/EXCISE_LIST.md | excise list for regex + per-app recipes |
| 05 | Investor demo tomorrow plan | planning | a1abcdb40 (sub-agent) | main | in-flight | file exists at planning/12-investor-demo-tomorrow/PLAN.md | 24-hour build schedule |
| 06 | Tab-hijack bug fix | execution | unassigned | worktree-tab-hijack | queued | grep '_cdp_navigate' scripts/v7/anticipy_bridge_fallback_cdp.py:528-554 returns the patched code AND Z-001 9/9 PASS | blocks every cross-app flow |
| 07 | Engine stability (one process on 8731) | execution | unassigned | worktree-engine-stability | queued | lsof :8731 returns one PID == /Applications/Anticipy.app sidecar AND launchctl list shows human-ready-loop + finish-overnight as removed | half of CHECK 16 noise is from this |
| 08 | Planner latency unfreeze (platform_adapter.py) | execution | unassigned | worktree-planner-latency | queued | timeout_s == 15 AND backoffs == [0.5, 1.0] AND OpenRouter cache_control set AND Z-001 9/9 PASS | lifts CHECK 16 from 17/30 to ~25/30 |
| 09 | Excise hardcoded regex from _is_actionish | execution | unassigned | worktree-excise-actionish | queued | engine/app/product/server.py:2548 returns a function that calls LLM, not regex | depends on unit 04 audit |
| 10 | Excise hardcoded fastpaths | execution | unassigned | worktree-excise-fastpaths | queued | engine/app/product/server.py:5276 + :5399 use LLM not regex | depends on unit 04 audit |
| 11 | Memory consolidation (pick ONE impl) | execution | unassigned | worktree-memory | queued | 1 active dossier path, 3 deprecated paths marked dead, pronoun map deduped | enables clean cold-start writes |
| 12 | Instant cold-start build (per unit 03 design) | execution | unassigned | worktree-cold-start | queued | fresh macOS user opens Anticipy → 60s later dossier has >=20 people | the day-0 useful proof |
| 13 | Trivia-fire end-to-end build | execution | unassigned | worktree-trivia-fire | queued | scripted phrase "when did the Roman empire fall" produces answer notification in <2s | the killer demo |
| 14 | DeliveryRoutes wiring (APNs + Twilio + osascript) | execution | unassigned | worktree-delivery | queued | proactive/notifier.py routes a test notification to all three surfaces | the cascade has no delivery today |
| 15 | Universal action loop (per unit 01 design) | execution | unassigned | worktree-universal-loop | queued | utterance "make a calendar event for next tuesday at 3pm" works in calendar.google.com WITHOUT a per-app recipe | the action moat |
| 16 | Stranger-flow proof harness | execution | unassigned | worktree-stranger-proof | queued | scripts/v7/stranger_flow.sh runs on a fresh macOS user account → DMG install → onboarding → real trivia-fire + real Gmail draft, all green | the missing end-to-end test |

## Scorecard (mechanical, updated each cycle)

```
Component             %    Source of truth
---------             ---  ---------------
Capture (ASR)         80%  CHECK 11 PASS + listen daemon alive
Memory                40%  unit 11 done → 80%, unit 12 done → 95%
Action brain          50%  unit 08 done → 75%, unit 15 done → 95%
Action surfaces       30%  unit 15 done → 85% (universal, no app count)
Confidence ladder     40%  unit 11 done (memory) → enables calibration
Notification          20%  unit 14 done → 80%
Authority vault       30%  units 06 + 07 done → 50%
Cold start             0%  unit 12 done → 95%
Trivia fire            0%  unit 13 done → 100%
Engine stability      40%  unit 07 done → 95%
Tab isolation         20%  unit 06 done → 90% (+ extension install per unit 02)
Stranger flow          0%  unit 16 done → 100%
Distribution          90%  no work needed
Handoff               70%  unit 11 (handoff ghost import) → 95%
UI surfaces           40%  out of scope this batch
Pendant hardware       0%  out of scope V1
Phone app              0%  out of scope V1
---------------------------
TOTAL                 32%  → target 90%+ this batch (10 in-scope components hitting 90%+)
```

## Done criteria for the cron loop

The cron stops firing when ALL of these are mechanically true:

1. Units 01-16 all show `status: done` in this file.
2. `python3 scripts/v7/z001_e2e_harness.py` exits 0 with verdict=PASS in last 30 min.
3. `scripts/v7/stranger_flow.sh` (built in unit 16) exits 0 in last 60 min.
4. `python3 engine/tests/anticipy_acceptance.py --skip 6,9,10` SUMMARY.json shows pass>=14, git_head=HEAD.
5. CHECK 16 (agent_reliability) shows resolvable>=18/20 AND ambiguous>=8/10.
6. Engine on port 8731 is the packaged binary (verified by `ps -p $(lsof -t :8731) -o command=` matches /Applications/Anticipy.app/Contents/MacOS/anticipy-engine).
7. Manual demo script (planning/12-investor-demo-tomorrow/PLAN.md) is rehearsed AND result.json shows zero failures.

When all 7 are true, the cron writes `state/orchestrator/DONE.json` with timestamps and the work shuts down, the user gets notified via the cron prompt (which becomes a "DONE" message instead of a "next cycle" message).

## How the cron cycle works

Procedure (in planning/00-handoff/CYCLE_PROCEDURE.md). Summary: each wake, the planner reads this file, advances any unit it can, runs any verify command that's ripe, updates the scorecard, spawns the next agent if a queued unit becomes ready, writes a status line, and either re-arms (work remaining) or exits (done criteria met).

## Notes on parallelism

- Each execution unit runs in its own `git worktree`. The agent commits to a branch like `worktree-tab-hijack`. The planner merges to main only after Z-001 PASS.
- Planning units (01-05) work on docs in `planning/<thread>/` and don't touch source code, so they share `main`.
- The 16 units are mostly independent. Dependencies that exist:
  - 09 + 10 (excise hardcoded) depend on 04 (audit) producing the list.
  - 12 (cold-start build) depends on 03 (cold-start design) and 11 (memory consolidation).
  - 13 (trivia-fire build) depends on 14 (delivery routes for notification surface).
  - 15 (universal loop) depends on 01 (design) and 04 (audit list of things to excise).
  - 16 (stranger flow) depends on 06 + 07 + 08 + 12 + 13 + 14 + 15 being done.

## Status log

| Cycle | Time | Note |
|---|---|---|
| 0 | 2026-05-29 ~10:55 PDT | orchestrator created, 5 planning agents launched, 11 execution agents queued |
| 1 | 2026-05-29 ~11:18 PDT | user accidentally killed all sub-agents; salvaged 3-of-5 platform_adapter.py fixes (a4c707b9), Z-001 9/9 PASS, respawned 7 exec agents in worktrees (units 06, 08-remainder, 09+10 combined, 12, 13, 14, 16) |
| 2 | 2026-05-29 ~11:21 PDT | cycle 2: all 7 exec agents alive (jsonl files growing), no commits landed yet, capacity 7/16, engine alive on 8731, no new work to spawn (queue exhausted of dep-clear units), self-arm. Engine onboarded flipped to false (probably from a cold-start agent wiping dossier for testing); will re-verify Z-001 after agents land. |
