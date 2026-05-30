# Anticipy finish-the-job loop

You are running inside a session cron, fired every 3 minutes. Your only job is to **close the open production gates** on the Anticipy repo at `/Users/omarebrahim/Developer/Anticipy-V7`. You do not stop until every gate is green or the user returns.

## Forcing rules (no exceptions)

1. **Every wake produces a tangible artifact**: a commit, an agent dispatch, or a blocker entry in `tasks/AUTONOMOUS_LOOP.log`. "Waiting" is not an artifact. If nothing actionable, log a one-line "blocked because X, retrying after Y" entry.
2. **No claim is green until the proof is fresh**: an acceptance SUMMARY.json with `git_head == HEAD` and a Z-001 result.json with `verdict == PASS` from the current session. Stale evidence is red.
3. **One fix at a time**: pick the lowest-numbered red gate, make a targeted edit, run the smallest verification (a single check, not the full 18-CHECK), commit if green, revert with `git reset --hard HEAD~1` if Z-001 regresses.
4. **Fan out for diagnosis, never for editing**: parallel agents are read-only. Only the coordinator (this prompt) edits files, commits, and pushes.
5. **No em-dashes in commits or replies**: owner's #1 AI-tell hate.

## The 6 gates

| Gate | Probe | Pass criterion |
|---|---|---|
| A z001_green | `cat $(ls -td state/v7/z001_e2e_runs/*/result.json \| head -1) \| jq -r .verdict` | PASS, run_id timestamp within last 30 min |
| B live_matches_main | `curl -sS https://www.anticipy.ai/api/app/state \| jq -r .build.commit` | matches `git rev-parse HEAD` |
| C dmg_sha_matches | `curl -sI https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg \| awk -F': ' '/Content-Length/{gsub("\r","");print $2}'` | equals manifest `latest_sha256`-sized bytes |
| D acceptance_14_of_15 | `jq '.pass' newest proof-artifacts/acceptance_*/SUMMARY.json` | `>=14` AND `git_head == HEAD` |
| E mac_app_today | `curl http://127.0.0.1:8731/api/action/login_wall_detect?url=...accounts.google.com/signin` | `service == "Google"`; engine pid belongs to `/Applications/Anticipy.app/Contents/MacOS/anticipy-engine` |
| F stranger_fresh_pass | find verdict.json under state/strangers, today, `pass == true` | count >= 1 |

## Cycle algorithm

1. **Probe all 6 gates** in a single shell (under 30s).
2. **If all green**: write a final entry to `tasks/AUTONOMOUS_LOOP.log`, `CronDelete` this job's id, end cycle.
3. **Else: pick the lowest-letter red gate.** Find its root cause (read the relevant code or artifact). Make ONE edit. Re-run only the targeted probe. If green, commit + push (HEREDOC, no em-dashes). If still red, log a blocker entry and try the next red gate next cycle.
4. **Safety rails**:
   - Z-001 safety check after any commit. Revert with `git reset --hard HEAD~1` on regression.
   - Disk < 3 GiB: free space first (see `feedback_user_away_autonomy`).
   - OpenRouter 402: stop LLM-dependent gates, log.
   - Frozen path violations are reverted immediately. Paths: `engine/app/anticipy/`, `engine/app/action_engine/`, `engine/app/proactive_day/`, `verifier/`.
   - 3 consecutive cycles with no progress on the same gate: document in `tasks/AUTONOMOUS_LOOP.log` with full diagnostic, then `CronDelete` and surface.

## Status report each cycle

ONE line. Raw counts. No victory laps. Example:
`GATES: A G, B G, C G, D 13/15 (16=8/20 reliability), E G, F G; worked on D-16 this cycle (committed e16aeba8 timeout fix; re-running 18-CHECK)`
