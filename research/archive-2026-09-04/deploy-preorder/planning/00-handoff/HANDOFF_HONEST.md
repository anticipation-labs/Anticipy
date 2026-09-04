# Anticipy Honest Handoff (every micro detail, no spin)

Last updated: 2026-05-29 ~20:26 PDT, cycle 169.

This document does NOT claim everything is done. Read every section. The "Not done" section is as important as the "Done" section.

If you only read one file: read this one. It supersedes HANDOFF_COMPLETE.md as the truthful current state.

---

## 1. What Anticipy IS

An AI pendant (today a Mac app standing in for the pendant) that listens to every conversation the user is in and silently completes whatever needs doing. Donna from Suits, for everyone. Works on any web app the user is logged into, no per-app code.

Form factor today: Tauri menubar app + packaged Python FastAPI sidecar on 127.0.0.1:8731 + bridge on 127.0.0.1:7777 multiplexing CDP to user's real Chrome on 127.0.0.1:9222.

Form factor V2 (DOES NOT EXIST YET): pendant + phone (edge brain) + mini-PC (Raspberry Pi class).

---

## 2. What is actually running RIGHT NOW

- Engine: `/Applications/Anticipy.app/Contents/MacOS/anticipy-engine` PID 66923, etime over 1 hour, port 8731. The binary was rebuilt + swapped at 18:34 + 19:16 PDT to include all cycle 122b through 130 source fixes (ASR bundled-weights, no-default-omar-email, multi-tenant account_id, dead code removal, cost telemetry binding, warmup, Chrome browser fallback).
- Bridge: PID 62882, port 7777, cdp_primary, python 3.10.14.
- Chrome: Chrome/148.0.7778.215 on port 9222 with cloned user profile at `~/.anticipy/chrome-real-clone`.
- Dossier: 24 real people on disk at `~/.anticipy/v7/dossiers/anticipy-user/dossier.json`, 16 of them have email field populated.
- ASR: parakeet_mlx, weights bundled in DMG resources, runs locally on Apple MLX.
- TTS: ElevenLabs Sarah voice with disk cache at `~/.anticipy/v7/tts_cache/` (168 facts pre-cached).
- Task queue: 153+ persisted tasks at `~/.anticipy/v7/task_queue/queue.jsonl`, 22+ in waiting status.
- Machine ID: `~/.anticipy/machine_id` 0600 perms, 32-char UUID (cycle 123 multi-tenant fix live).

---

## 3. What is verified working (DONE, with evidence)

All 12 mechanical gates have been GREEN simultaneously for 50+ consecutive cycles since cycle 97. Latest verification this cycle:

| Gate | Verify | Latest evidence |
|---|---|---|
| G1 install_under_5min | `bash scripts/v7/stranger_flow.sh` | `state/v7/stranger_flow_runs/20260529T232452Z/result.json` verdict=PASS 8/8 steps approx 120s, used the SMS auto-dispatch patch |
| G2 trivia_fires | `python3 scripts/v7/discovery_trivia.py` | 11-35ms perceived latency, ElevenLabs cached, correct Roman Empire fact |
| G3 silent_execute | `python3 scripts/v7/z001_e2e_harness.py` | Latest PASS at `20260530T032123Z` 9/9 steps, real Gmail draft visible in real Chrome |
| G4 coldstart_fills_dossier | `python3 scripts/v7/discovery_coldstart.py` | 24 people, 16 with email |
| G5 packaged_binary_serves | `lsof -t -nP -iTCP:8731 -sTCP:LISTEN` | pid 66923 = /Applications/Anticipy.app/Contents/MacOS/anticipy-engine |
| G6 demo_rehearsed | dress_rehearsal.sh PASS twice in 4h | 03:05:55Z + 03:23:23Z PASS within 4h |
| G7 non_google_surfaces_work | `bash scripts/v7/universal_beyond_google.sh` | `state/v7/universal_beyond_google_runs/20260529T223738Z/result.json` aggregate verdict=PASS 3/3 surfaces |
| G8 real_world_demo_scenarios | `bash scripts/v7/demo_scenarios.sh` | `state/v7/demo_scenarios_runs/20260529T225813Z/aggregate.json` aggregate_verdict=PASS 4/5 (stripe + calendly + notion + github PASS; gmail FAIL via universal-loop path) |
| G9 proactive_fires_unprompted | `python3 scripts/v7/discovery_proactive.py` | Calendar prep scheduler running, briefs_fired observed |
| G10 channel_by_urgency_routes | `python3 scripts/v7/discovery_channel_router.py` | 6/6 matrix PASS (voice/sms/sms+email/email/silent) |
| G11 cost_under_ceiling | `curl /api/cost/stats` | p95 in current rolling window=$0.0, peak observed $0.000697 (34% of $0.005 hard cap) |
| G12 failure_recovery_works | `curl -X POST /api/recovery/test` | All 6 failure_kinds render plain-English SMS bodies 89-114 chars + `fire_route=true` parks real task in queue |

Plus verified beyond gates:
- Audio pipeline end-to-end (cycle 121): real WAV via `say` + `afconvert` POSTed to `/api/listen/upload` → parakeet ASR transcribed correctly → trigger fired → trivia returned correct answer.
- DMG download: `https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg` HTTP/2 200, 2,515,666,283 bytes, `application/x-apple-diskimage`.
- Website pages: `/`, `/app`, `/app/download`, `/onboarding/{audio,chat,call}`, `/flash`, `/admin` all 200.
- API endpoints correctly auth-gated: `/api/engine/model` 401, `/api/dossiers/upsert` 401, `/api/engine/session` 401, `/api/auth/handoff/mint` 401.
- Multi-day persistence (cycle 154 task #3): task enqueued, engine killed -9, engine restarted, task survived with status=waiting, then fired through to done.
- WWII trivia fix lives in cache and returns "May 8, 1945 (VE Day) and September 2, 1945 (VJ Day)" correctly.

---

## 4. What is NOT done (truthful gaps)

### V2 hardware (out of scope for v-final-prototype, in scope for the company North Star)
- Pendant hardware does not exist
- Phone edge brain does not exist
- Mini-PC at home does not exist
- Speaker biometrics (voice-print enrollment) not implemented

### Real-world distribution (not validated)
- A second human has NOT installed the DMG on a fresh macOS. N=1 (Omar) is not "distribution at scale". Until a stranger installs and uses it, "scale by distribution" is theoretical.
- The full Supabase signin flow on first-launch popover has not been visually verified end-to-end on a fresh user. The pieces are wired but the actual flow has not been recorded.
- Twilio for strangers: needs either a per-user provisioning UI OR a website-side Twilio relay (similar to the model broker pattern). Currently runs in `TWILIO_MOCK=1` on Omar's machine. Real Twilio works if Omar sets `TWILIO_TEST_TO_REAL_NUMBER=1` + creds.

### Tauri bundle is stale
- The Tauri Rust shell on disk in `/Applications/Anticipy.app` was built BEFORE the cycle 122b (dead `run_task` removal) and cycle 130 (Chrome browser fallback) Rust changes. The bundled SIDECAR binary IS current. The Tauri SHELL is not. Dead code in production, harmless but real. A `node ./scripts/tauri.mjs build --target aarch64-apple-darwin` would rebuild the bundle.

### Source-side audit warnings still open
- W5 dev-default JWT_SECRET + PROFILE_ENCRYPTION_KEY when ENGINE_ENV != production. Acceptable for single-user pendant prototype but real shipping needs per-install secrets.
- W7 TCC walkthrough only covers mic. Other TCCs (screen recording, accessibility, automation) are not needed by the current CDP-only architecture. If any non-CDP path gets added, those would need pre-explainer + dialog like mic.

### Known product behavior quirks (verified, not bugs but worth knowing)
- Gmail drafts BYPASS the SMS pre-confirm gate BY DESIGN (drafts are reversible, gate only fires on click-Send and non-Gmail sends). See `engine/app/product/sms_pre_confirm.py:380` docstring.
- Parakeet ASR mishears long alphanumeric email aliases. "omarkebrahim+anticipy-pipeline@gmail.com" becomes garbled. Demo guidance: do not voice long email aliases out loud; use in-dossier names instead.
- Cold-cache first-call latency on freshly-spawned binary can blow universal action loop deadlines (lesson from cycle 115). The `universal_beyond_google.sh` script now has a warm-up step (cycle 118) but other scripts/integrations might hit the same.
- Cost telemetry rolling window can decay to 0 if no `/api/act` tasks finish in the recent past. Misleading at a glance, not a bug.
- LLM intent extractor is non-deterministic. Same prompt can return different classifications across calls. Most observed mis-classifications self-recover on retry.

### Anti-claims (things I will NOT claim done)
- "Trillion-dollar product": that's market reality + adoption, not technical correctness
- "Fully shipped to strangers": N=0 strangers actually using it
- "All E2E pipelines verified together": the full audio-in to action-out chain has been verified in PIECES, not in a single uninterrupted live run (the cycle 121 audio test stopped at trivia; the cycle 125 pipeline test surfaced the Gmail-drafts-bypass-SMS-gate architectural fact)

---

## 5. Open work units (none are gate-blocking, all are real)

| ID | Title | Status | Priority |
|---|---|---|---|
| W5 | ENGINE_ENV=production + per-install JWT/PROFILE secrets | open | P2 (acceptable for prototype) |
| W7 | TCC walkthrough beyond mic | open | P2 (CDP architecture does not need it) |
| TAURI-REBUILD | Tauri bundle stale, missing cycle 122b + 130 Rust changes | open | P2 (dead code harmless) |
| TWILIO-BROKER | Website Twilio relay so strangers don't need own creds | open | P1 for shipping at scale, P3 for Omar |
| STRANGER-INSTALL-N=2 | Actually install on fresh macOS user account | open | P0 for "scale by distribution" proof |
| PENDANT-HARDWARE | V2 form factor | open | V2 scope, not v-final-prototype |
| ASR-EMAIL-ALIAS | parakeet mishears long alphanumeric email aliases | open | P2 (workaround: do not voice them) |

---

## 6. Architecture snapshot (where every important piece lives)

### Engine (`engine/app/product/server.py`, ~11000 lines)
- Hot paths: `/api/listen/upload`, `/api/listen/inject`, `/api/act`, `/api/universal/run`, `/api/coldstart/start`, `/api/sms/inbound`, `/api/sms/pending/<id>/dispatch`, `/api/task_queue/*`, `/api/recovery/test`, `/api/cost/stats`, `/api/dossier/events`, `/api/calendar/prep/*`, `/api/notify/test`
- Multi-tenant `account_id` derivation: lines 142-216 (`_default_account_id` materializes `~/.anticipy/machine_id`, `_resolve_account_id_at_startup` chain env -> USER_ID -> session profile -> machine_id)
- SMS pre-confirm gate: at `/api/act` line 8928 (`should_pre_confirm(plan, instruction)`), bypassed for safe-draft Gmail paths per `engine/app/product/sms_pre_confirm.py:380`
- Cost telemetry: bound in `_pa_for_telemetry.set_telemetry_sink + set_budget_gate` at module-import time; per-task lifecycle managed in `/api/act` and `/api/universal/run`

### ASR
- `engine/app/audiostack/audio.py`
- Model `mlx-community/parakeet-tdt-0.6b-v3` bundled in DMG at `/Applications/Anticipy.app/Contents/Resources/parakeet-tdt-0.6b-v3/`
- `_bundled_parakeet_dir()` finds it; falls back to HF Hub `parakeet-tdt-0.6b-v2` if missing (dev/source runs)

### TTS
- `engine/app/product/tts.py`
- Cascade: ElevenLabs (Sarah voice) > Polly > macOS `say`
- Cache `~/.anticipy/v7/tts_cache/*.mp3` keyed by sha256(provider:voice:text)

### Planner / LLM
- `engine/app/anticipy/platform_adapter.py`
- DeepSeek V4 Flash via OpenRouter (primary), with prompt caching (90%+ hit rate)
- Falls back to website model broker at `https://www.anticipy.ai/api/engine/model` when no local key

### Bridge / Chrome
- `scripts/v7/anticipy_bridge_fallback_cdp.py` runs on port 7777
- Chrome at 9222 with `--user-data-dir=~/.anticipy/chrome-real-clone`
- Tab-ownership map `_ANTICIPY_OWNED_TARGETS` prevents agent from hijacking user's tabs

### Tauri app
- `desktop/src-tauri/src/lib.rs` Rust shell
- `desktop/src/popover.html` polished menubar UI (SF Pro, status dot, plain English copy)
- `bootstrap_anticipy_chrome` at lib.rs:694 auto-clones Chrome profile + launches Chrome on 9222
- `start_engine_sidecar` at lib.rs:1057 short-circuits if 8731 already healthy
- `_resolve_chrome_binary` (cycle 130) returns first existing of 6 Chromium-family browsers

### Website (`src/app/`, Next.js 14 on Vercel)
- `/api/engine/model` model broker (requires Supabase auth, uses server-side OPENROUTER_API_KEY)
- `/api/auth/exchange` handoff token claim
- `/api/auth/handoff/mint` issuer
- `/api/twilio/sms-inbound` Twilio webhook with HMAC-SHA1 verify
- `/api/dossiers/upsert` cross-device dossier sync
- `/api/engine-transfer-gate` cross-device gating
- `/onboarding/{audio,chat,call}` onboarding flows
- `/app/download` DMG redirect
- `/admin`, `/analytics` (password-gated)
- Supabase project "handlit" ref `ogbxpqkmsdrcuilafycn`

### install.sh (`public/install.sh`)
- Downloads DMG, hdiutil imageinfo validate, mount, validate `.app`, then rm -rf old + cp new
- Clears `xattr -dr com.apple.quarantine`
- Installs Chrome native messaging bridge from `https://www.anticipy.ai/anticipy-extension.zip`
- Sets up Python 3.9+ venv at `~/.anticipy/venv/` with httpx + cryptography + supabase + python-dotenv
- Spawns engine via perl-setsid daemon (so SSH closing doesn't kill it)

---

## 7. Test harnesses (what you can re-run yourself)

| Script | What it does | Cost |
|---|---|---|
| `python3 scripts/v7/z001_e2e_harness.py` | Full chain: bridge + engine + create Supabase user + handoff + inject + act + verify Gmail draft | LLM credits for planner + supabase signup, takes 45-90s |
| `bash scripts/v7/stranger_flow.sh` | Snapshot dossier + wipe + cold-start + inject + act + restore | 2-3 minutes, real LLM calls during cold-start |
| `bash scripts/v7/dress_rehearsal.sh` | 3 scenes: trivia Roman Empire + Z-001 mini + cold start dossier count | 60-70 seconds |
| `bash scripts/v7/universal_beyond_google.sh` | Run universal action loop on saucedemo + heroku + wikipedia | 2-4 minutes, real LLM calls |
| `bash scripts/v7/demo_scenarios.sh` | 5 real-world scenarios (stripe + calendly + notion + github + gmail) | 8-25 minutes, real LLM |
| `python3 scripts/v7/discovery_trivia.py` | Inject trivia phrase + read recent fires + verify latency | Free (cache hit) |
| `python3 scripts/v7/discovery_coldstart.py` | Read dossier on disk; if <10 people, kick coldstart | Free if dossier already has 10+ |
| `python3 scripts/v7/discovery_channel_router.py` | 6 matrix cases exercised | Free (pure Python) |
| `python3 scripts/v7/discovery_proactive.py` | Probe calendar prep scheduler + notify_test | Free |
| `curl /api/cost/stats` | Read per-task cost telemetry | Free |
| `curl -X POST /api/recovery/test` | Render SMS body for any failure_kind, optionally fire_route to park retry task | Free |

---

## 8. The cron history (165 cycles, ~8 hours)

- Cycles 1-89: active build phase, 8 parallel agents, 30+ commits, the bulk of the work
- Cycles 90-101: 12-gate scoreboard built, ASR + email + multi-tenant + cost telemetry shipped, DONE_v2.json written
- Cycles 102-122: monitoring + closing audit warnings W1-W6 + sidecar rebuild
- Cycles 123-146: parallel agents for stranger install audit + multi-tenant + full pipeline E2E test + binary swap
- Cycles 147-169: pure heartbeat monitoring (no new bugs found, no new code shipped)

**Honest call: cycles 138 onward have been low-value heartbeat. The cron has served its purpose. If owner stops sending cycle messages, the system is stable as it sits.**

---

## 9. The 3 demo moments and how to fire each

### Trivia in your ear
```bash
curl -sS -X POST http://127.0.0.1:8731/api/listen/inject \
  -H 'Content-Type: application/json' \
  -d '{"text":"wait, when did the Roman Empire fall"}'
```
Expected: outcome=TRIVIA_FIRE, ElevenLabs Sarah voice speaks "The Western Roman Empire fell in 476 AD. Constantinople, the eastern capital, held until 1453." within 20ms perceived latency.

### Silent execute
```bash
bash scripts/v7/z001_e2e_harness.py
```
Expected: 9/9 steps PASS, real Gmail draft appears in Omar's real Chrome at https://mail.google.com/u/0/#drafts.

### "I just do" (the Donna effect)
- Open `/Applications/Anticipy.app` to surface the menubar popover
- Click "Skip onboarding, just listen"
- Speak naturally: "draft a thank-you email to Altaf Ebrahim about today"
- Within ~30s: Gmail draft appears with Altaf as recipient + body in Omar's voice

---

## 10. How to read the state in one command

```bash
PID=$(lsof -t -nP -iTCP:8731 -sTCP:LISTEN | head -1)
echo "engine pid=$PID, etime=$(ps -p $PID -o etime= | xargs), binary=$(ps -p $PID -o command= | awk '{print $1}')"
echo "dossier people: $(jq -r '.people | length' ~/.anticipy/v7/dossiers/anticipy-user/dossier.json)"
echo "task queue: $(curl -sS http://127.0.0.1:8731/api/task_queue/list | jq -r '.tasks | length')"
echo "cost p95: $(curl -sS http://127.0.0.1:8731/api/cost/stats | jq -r .stats.p95_cost_usd)"
echo "latest Z-001: $(ls -t state/v7/z001_e2e_runs/*/result.json | head -1 | xargs jq -r .verdict)"
echo "G6 rehearsals 4h: $(jq -r '.runs[-3:] | .[] | "\(.started_at) \(.verdict)"' state/demo/dress_rehearsal_log.json)"
```

---

## 11. The owner sign-off line that hasn't been written yet

The mechanical bar (12 gates GREEN for 5 cycles) was hit at cycle 101. Per NORTH_STAR_v2.md the formal v2 DONE also requires owner sign-off in ORCHESTRATOR.md. That sign-off has NOT been written. The cron continues to run because the formal DONE is gated on it.

If Omar writes "OWNER SIGN-OFF: ship v-final-prototype" into ORCHESTRATOR.md and commits it, the v-final-prototype milestone is formally closed. The remaining open items (W5, W7, TAURI-REBUILD, TWILIO-BROKER, STRANGER-INSTALL-N=2, PENDANT-HARDWARE, ASR-EMAIL-ALIAS) carry forward as separate work units.

---

That's everything. The Mac prototype works for Omar on Omar's Mac today. The company North Star (trillion-dollar pendant + scale adoption) is NOT done and is not my work.
