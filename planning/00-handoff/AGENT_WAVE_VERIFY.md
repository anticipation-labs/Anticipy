# Wave verification protocol (cycle 88+)

Owner asked: "build some system in place to ensure that this actually gets done?"

Yes. Here is the protocol the cron follows for every agent in this wave. Each cycle the planner runs through it.

## The 8 agents in this wave

| Agent ID | Mission | Verify command | Files claimed |
|---|---|---|---|
| a58b648e (G7) | universal loop on 3 non-Google surfaces | `bash scripts/v7/universal_beyond_google.sh` exits 0 + result.json verdict=PASS | scripts/v7/universal_beyond_google.sh, planning/00-handoff/NORTH_STAR_v2.md (G7 row), CYCLE_PROCEDURE.md (G7 row) |
| af9908989 (demo scenarios) | 5+ real-world scenarios PASS | `bash scripts/v7/demo_scenarios.sh` exits 0 with verdict=PASS (>=4 of 5 scenarios complete) | scripts/v7/demo_scenarios.sh, state/v7/demo_scenarios_runs/ |
| a967fe7f (channel router) | phone-call channel + urgency router | server.py has channel_router.select_channel + sms_pre_confirm._send_voice_confirm | engine/app/product/channel_router.py, sms_pre_confirm.py extensions |
| aabb6378 (popover polish) | Apple-quality popover UI | screenshot of popover shows SF Pro + no jargon + status dot; Z-001 PASS | desktop/src/popover.html, desktop/src/styles.css, desktop/src-tauri/src/lib.rs |
| a8bd1a31 (calendar auto-prep) | meeting brief generator | POST /api/calendar/prep/trigger returns real brief referencing real attendee | engine/app/product/calendar_prep.py + server.py endpoint |
| a52d4943 (cost telemetry) | per-task cost stats + budget enforcement | GET /api/cost/stats returns p50/p95 per-task cost; budget guard active | engine/app/product/cost_telemetry.py + server.py endpoint |
| a4297114 (failure recovery) | friendly SMS + queue park on login/MFA/CAPTCHA | POST /api/recovery/test {failure_kind} returns formatted SMS body | engine/app/product/failure_recovery.py + server.py endpoint |
| ae49b8dc (real-voice TTS) | ElevenLabs/Polly replaces macOS say | trivia smoke produces real-voice TTS (cached <50ms hit) | engine/app/product/tts.py + deliver.py swap |

## Per-cycle verification protocol

Each cron fire (every 3 min) the planner does, for each in-flight agent:

1. **Agent alive?** Check jsonl mtime in `~/.claude/projects/-Users-omarebrahim-Developer-Anticipy-DEV-FINAL/f0491f60-df8c-4801-9ccb-8af58a257677/subagents/agent-<id>.jsonl`. If mtime > 15 min ago, agent is wedged. Kill + respawn with same prompt.
2. **Files produced?** Check whether the agent's claimed files exist (per the table above). If 15 min in and zero files, agent is stuck. Kill + respawn.
3. **Commit landed?** Check `git log --since="15 minutes ago" --oneline | grep -i <agent_keyword>`. If 30 min in and no commit, agent is stalled. Send SendMessage asking for status.
4. **Verify command run?** Once agent reports done, run their verify command. If FAIL, flip the corresponding gate to RED with note. Don't trust the agent's self-report.
5. **Z-001 regression?** After each agent's commit, run Z-001. If FAIL, `git reset --hard HEAD~1` and re-queue the work.

## The mechanical done state for THIS wave

All 8 agents must:
- Have their claimed files on disk
- Have their verify command exit 0
- Have Z-001 9/9 PASS after their commit
- Have their corresponding planning task (#141 / #142 / #143-148) marked completed
- Have evidence in their commit message (sha + verify output)

When all 8 are done AND the 7 gates are GREEN AND the 3 full E2E tests from NORTH_STAR_v2.md PASS, the cron writes DONE_v2.json.

## What's NOT acceptable

- Agent says "shipped" but file doesn't exist. Status flips back to in-progress.
- Agent says "Z-001 PASS" but `ls -t state/v7/z001_e2e_runs/` shows their run as FAIL. Status flips back.
- Agent's commit breaks Z-001 silently. Auto-revert.
- Cycle hits stagnation 3 without any agent landing. STUCK.json + notify user.

## Owner sees the truth, not the spin

The orchestrator log in ORCHESTRATOR.md status table shows per-cycle:
- Which agents are alive
- Which gates are GREEN/RED
- Which verify commands exited 0
- What commit landed
- Stagnation counter

You can audit any time. Every "GREEN" claim is backed by a command you can run yourself.
