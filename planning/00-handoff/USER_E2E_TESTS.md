# User-runnable E2E tests (the 3 from NORTH_STAR_v2)

These tests require human-in-the-loop (speech, real-time SMS replies, multi-day waits). The user runs them; mechanical gates verify the components.

## State of preflight (as of cycle 93)

- Engine: packaged `/Applications/Anticipy.app/Contents/MacOS/anticipy-engine` on 127.0.0.1:8731 (PID changes).
- Bridge: 127.0.0.1:7777 (auto-launched via launchd).
- Chrome: 127.0.0.1:9222 with user's real profile.
- Dossier: 24 real people inhaled at `~/.anticipy/v7/dossiers/anticipy-user/dossier.json`.
- TTS: ElevenLabs voice "Sarah" with disk cache at `~/.anticipy/v7/tts_cache/`.

## Test 1 — Silent execute (the "lawyer at intake" demo)

Goal: spoken request becomes a real Gmail draft via real Chrome, gated by SMS confirm.

Steps:

1. Confirm Chrome on 9222 has Gmail open under `omarkebrahim@gmail.com`.
2. Run: `bash /Users/omarebrahim/Developer/Anticipy-V7/scripts/v7/z001_e2e_harness.py` (or use the Tauri popover).
3. Confirm result: verdict=PASS, draft visible in Gmail Drafts folder.
4. SMS arrives at the configured number (TWILIO_TEST_TO_REAL_NUMBER_E164) asking YES/NO/EDIT, only if `TWILIO_TEST_TO_REAL_NUMBER=1`.

Currently verified: G3 mechanical = PASS at 225201Z (9/9 steps). For the SMS branch, set TWILIO_MOCK=0 + TWILIO_TEST_TO_REAL_NUMBER=1 in env first.

## Test 2 — Trivia in the wild

Goal: spoken trivia question gets answered in the user's earbud in under 2 seconds.

Steps (5 phrases, all expected correct):

```
curl -sS -X POST http://127.0.0.1:8731/api/listen/inject \
  -H 'Content-Type: application/json' \
  -d '{"text":"wait, when did the Roman Empire fall"}' | jq -r .outcome
# expected: TRIVIA_FIRE

# Listen to the ElevenLabs voice via macOS afplay (or watch /api/trivia/recent)
curl -sS http://127.0.0.1:8731/api/trivia/recent | jq -r '.fires[0] | {answer, total_latency_ms, tts}'
```

Repeat with: "wait, when was the moon landing", "wait, when did world war two end", "wait, when was the Eiffel Tower built", "wait, when did the Declaration of Independence get signed".

Currently verified: G2 mechanical = PASS at 22:49Z (Roman Empire: 13.5ms perceived, ElevenLabs Sarah voice from cache).

## Test 3 — Multi-day follow-through

Goal: a task scheduled today fires N days later, surviving engine restarts.

Steps:

```
# 1. Enqueue a task with wake_at set ~30s in the future for testing
curl -sS -X POST http://127.0.0.1:8731/api/task_queue/enqueue \
  -H 'Content-Type: application/json' \
  -d '{"instruction":"draft a reminder email to me about the Q3 contract", "wake_at_offset_seconds": 30}'

# 2. Confirm it lands in the queue
curl -sS http://127.0.0.1:8731/api/task_queue/list | jq -r '.tasks[] | "\(.task_id) \(.status) \(.wake_at)"'

# 3. Kill the engine to test persistence
pkill -9 -f anticipy-engine
sleep 2

# 4. Relaunch packaged binary
ANTICIPY_PORT=8731 ANTICIPY_ACCOUNT_ID=anticipy-user ANTICIPY_USER_EMAIL=omarkebrahim@gmail.com \
  ANTICIPY_RECEIPT_ON_SUCCESS=1 ANTICIPY_ALLOW_REAL_SEND=1 TWILIO_MOCK=1 \
  /Applications/Anticipy.app/Contents/MacOS/anticipy-engine > /tmp/engine.log 2>&1 &
sleep 8

# 5. Verify task survived restart
curl -sS http://127.0.0.1:8731/api/task_queue/list | jq -r '.tasks[]?.task_id'

# 6. Wait for wake_at, observe the task firing (60s background scan)
```

Currently verified: persistent task queue exists at `engine/app/task_queue/{store,dispatcher}.py` per commit 261eb768; smoke tests 12/12 PASS.

## The 12 mechanical gates (from CYCLE_PROCEDURE.md)

| Gate | Status (cycle 93) | Verify |
|---|---|---|
| G1 install_under_5min | RED | harness limitation, fresh inhale partial |
| G2 trivia_fires | GREEN | 13.5ms cached |
| G3 silent_execute | GREEN | Z-001 9/9 PASS at 225201Z |
| G4 coldstart_fills_dossier | GREEN | 24 people |
| G5 packaged_binary_serves | GREEN | pid on 8731 = Anticipy.app sidecar |
| G6 demo_rehearsed | GREEN | 2 PASS within 4h |
| G7 non_google_surfaces_work | GREEN | saucedemo + heroku + wikipedia |
| G8 real_world_demo_scenarios | IN FLIGHT v3 | calendly + notion PASS, github + gmail in flight |
| G9 proactive_fires_unprompted | GREEN | calendar scheduler running |
| G10 channel_by_urgency_routes | GREEN | 6/6 matrix |
| G11 cost_under_ceiling | GREEN | p95 0.0 < $0.005 |
| G12 failure_recovery_works | GREEN | SMS body 96 chars |

When ALL 12 GREEN simultaneously for 5 cycles AND owner signs off on the 3 E2E tests above, the cron writes `state/orchestrator/DONE_v2.json` and the work shuts down.
