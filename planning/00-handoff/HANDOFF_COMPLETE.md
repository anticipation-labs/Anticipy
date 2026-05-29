# Anticipy Complete Handoff (single source of truth)

Last updated: 2026-05-29 ~15:15 PDT. Update this file every time something material changes.

If you are a new agent picking up this project: READ THIS WHOLE FILE BEFORE TOUCHING ANYTHING. Then read `HANDOFF_FOR_NEXT_AGENT.md` (the rules), `NORTH_STAR_v2.md` (what we are building), `ORCHESTRATOR.md` (current state), `CYCLE_PROCEDURE.md` (how the cron advances things).

## 1. The product

**Anticipy** is an AI pendant that listens to every conversation the user is in and silently completes whatever needs doing. Donna from Suits, for everyone. Works in any industry, any web app the user is logged into, with no per-app code.

Form factor today: Mac prototype (Tauri menubar app + Python sidecar engine + bridge + user's real Chrome). Form factor V2: pendant + phone (edge brain) + mini-PC ($30 Raspberry-Pi-class) running Chrome. Same engine code ports.

**Wake-word is NOT primary input.** Pendant always listens. Engine decides what fires.

## 2. Three demo moments

1. **Trivia in your ear.** Friend says "when did the Roman Empire fall" → 1.2s later earbud whispers "476 AD Western, 1453 Constantinople". 11-22ms perceived audio start measured today.
2. **Silent execute.** Lawyer at intake hears client → demand letter drafted in case management system + matter opened before lawyer is back at desk.
3. **"I just do."** Anyone asks user a question → user looks like Donna because Anticipy already handled it.

## 3. The 12 mechanical gates (the only definition of "done")

Per `CYCLE_PROCEDURE.md`. Stop the cron only when ALL 12 GREEN.

Status as of cycle 93 (2026-05-29 23:02Z):

| # | Gate | Verify command | Today |
|---|---|---|---|
| G1 | install_under_5min | `bash scripts/v7/stranger_flow.sh` exits 0 + elapsed < 300s | RED (harness limitation: fresh inhale during stranger flow stops at 4-11 people before resolving "Zara Somani"; SMS auto-dispatch patch in e233d1b5 ready when inhale is complete) |
| G2 | trivia_fires | `python scripts/v7/discovery_trivia.py` exits 0 (latency<2s, correct fact, audio plays) | GREEN (13.5ms cached Roman Empire) |
| G3 | silent_execute | `python scripts/v7/z001_e2e_harness.py` PASS | GREEN (9/9 PASS at 225201Z) |
| G4 | coldstart_fills_dossier | `python scripts/v7/discovery_coldstart.py` (≥10 real people in 60s) | GREEN (24 real people in dossier) |
| G5 | packaged_binary_serves | `lsof :8731` = Anticipy.app sidecar + `/api/trivia/recent` 200 | GREEN (pid 12121 = /Applications/Anticipy.app/Contents/MacOS/anticipy-engine on 8731) |
| G6 | demo_rehearsed | 2 consecutive `dress_rehearsal.sh` PASS in last 4h | GREEN (19:39 + 20:01 PASS, within 4h window) |
| G7 | non_google_surfaces_work | `bash scripts/v7/universal_beyond_google.sh` exits 0 | GREEN (aggregate=PASS at 223332Z: saucedemo + herokuapp + wikipedia) |
| G8 | real_world_demo_scenarios | `bash scripts/v7/demo_scenarios.sh` exits 0 (≥4 of 5 scenarios) | GREEN (aggregate_verdict=PASS at 20260529T225813Z, 4 of 5: stripe+calendly+notion+github PASS, gmail FAIL; threshold=4 met) |
| G9 | proactive_fires_unprompted | `python scripts/v7/discovery_proactive.py` exits 0 | GREEN (calendar prep scheduler running, briefs_fired=1, proactive_fire logged) |
| G10 | channel_by_urgency_routes | `python scripts/v7/discovery_channel_router.py` exits 0 | GREEN (6/6 matrix PASS) |
| G11 | cost_under_ceiling | `curl /api/cost/stats` p95 per-task < $0.005 | GREEN (p95=0.0, max=0.000697 well under $0.005) |
| G12 | failure_recovery_works | `curl -X POST /api/recovery/test {login_required}` returns formatted SMS | GREEN (renders "Anticipy couldn't finish the task because the site is logged out..." 96 chars) |

**11 of 12 GREEN. Only G1 outstanding.**

## 4. The 10 hard rules

From `NORTH_STAR_v2.md`. NEVER violate. Every PR checked against these.

1. **Universal action agent.** No per-app code, no recipe registry. DOM + screenshot + LLM decides, CDP executes.
2. **No service APIs.** Browser nav only. OpenRouter LLM is the one outbound.
3. **Pre-action confirm channel-by-urgency.** Phone for CRITICAL+time-sensitive, SMS for CRITICAL+not, SMS+email for HIGH, email for MEDIUM, silent for LOW.
4. **Persistent follow-through.** Tasks survive restarts, sleep days/weeks, wake on schedule, retry with backoff.
5. **Apple-quality polish.** SF Pro typography, plain-English copy, smooth animations, real-voice TTS, permission explainers before dialogs, NO em-dashes anywhere.
6. **Local-first privacy moat.** Audio + dossier stay on user's hardware. Only LLM brain + Twilio + Supabase auth go out.
7. **Cost ceiling $200/user/year on 100k tasks** ($0.002/task). DOM-first, vision only on canvas. Aggressive prompt caching.
8. **Day-zero useful.** Cold-start inhales user's Gmail + Calendar + Drive in <60s.
9. **Pendant always-on. No wake-word.** Engine decides what matters.
10. **Confirm + receipt for every external action.** Pre-action SMS confirm (YES/NO/EDIT) + post-action receipt with verifiable identifier.

## 5. Component status (every micro detail)

### Engine core
- Shipping engine: `engine/app/product/server.py:53` on port 8731.
- Packaged as PyInstaller binary at `/Applications/Anticipy.app/Contents/MacOS/anticipy-engine`.
- Build script: `desktop/scripts/build-engine-sidecar.sh`.
- Hot path: `/api/listen/upload|inject` → `_intent_extract_llm` (unified LLM extractor) or fastpaths → `_compose_task_from_memory` → `/api/act` → confirm card or universal action loop.

### Memory (4 implementations coexist — TODO consolidate)
- Frozen Mem0: `~/.anticipy/system_v1/users/<uid>/memory.jsonl` (`engine/app/anticipy/memory.py`)
- Onboarding profile: `~/.anticipy/system_v1/product_profile.json`
- V7 ScopedMemory: `~/.anticipy/v7/memory/<acct>/<dev>/memory.jsonl` (`engine/app/product/scoped_memory.py:106`)
- Active dossier: `~/.anticipy/v7/dossiers/<acct>/dossier.json` (`engine/app/product/dossier_active_loader.py:139`) ← canonical, 24 people from real Gmail today
- Cross-device sync: Supabase outbox at `engine/app/product/memory_cloud_sync.py` (one-way reconciliation)
- Pronoun gender map duplicated in 3 files (`dossier_active_loader.py:26`, `scoped_memory.py:36`, `person_resolver.py:15`)

### Cold start
- `engine/app/coldstart/cdp_walker.py` (NEW today, 562 lines): opens Anticipy-owned tabs at gmail/calendar/drive via CDP, scroll-extracts via `[role="row"]` + `[data-eventid]`
- `engine/app/coldstart/auto_inhale.py` (NEW today, 730 lines): orchestrator, threads inhale, LLM extract via DeepSeek V4 Flash with prompt caching
- Endpoints: `POST /api/coldstart/start`, `GET /api/coldstart/status`
- Verified live: 24 people inhaled from real Gmail in 44-91s

### Action engine (universal loop)
- `engine/app/universal/action_loop.py` (NEW today, 222 lines): wraps DSv4SkillRunner with deadline. `run_until_done(intent, surface_hint, deadline_sec)`
- `engine/app/action_engine/dsv4_skill_runner.py`: V4 Ralph Loop, vision-verifier confirmed each step, Kimi K2.6 visual reasoning
- `engine/app/action_engine/cdp_dispatcher.py`: generic CDP execution
- Endpoint: `POST /api/universal/run`
- Verified on Google Calendar with zero calendar-specific code

### Planner
- Hot path entries in `engine/app/product/server.py`:
  - `_intent_extract_llm` (line 5588+): unified LLM extractor replacing V1+V2+V3 hardcoded regex (commit 51d3c609)
  - `_compose_task_from_memory` (line 5479): merges legacy profile + active dossier via `_active_dossier_people_dicts` + `_merged_profile_people` (commit a1d7b096)
  - `_fastpath_plan_from_memory` (regression safety net only)
- Model: DeepSeek V4 Flash via OpenRouter
- Latency: 0.9-1.8s cached calls (90% prompt cache hit), 3.6-7.5s cold (down from 211s worst case)
- CHECK 16 reliability: 28/30 (resolvable 20/20, ambiguous 8/10) Codex-class

### Trivia fire
- `engine/app/trivia/trigger.py`: 4-feature classifier (lexical opener + question prosody + group context + recent answer absence)
- `engine/app/trivia/cache.py`: local SQLite at `~/.anticipy/trivia_cache.db` with 200+ seed facts
- `engine/app/trivia/answer.py`: 3-lane router (cache → Perplexity Sonar → Brave+Sonnet)
- `engine/app/trivia/deliver.py`: macOS `say` for TTS (TODO: swap to ElevenLabs/Polly via TTS module being built by ae49b8dc)
- `engine/app/trivia/seed_facts.py`: hand-curated facts, includes Roman/Moon/Eiffel/Declaration/WWII
- Verified live: Roman Empire / Moon / Eiffel / Declaration of Independence all correct, 11-22ms perceived audio start

### SMS pre-confirm (commit c2879c67)
- `engine/app/product/sms_pre_confirm.py` (807 lines): `should_pre_confirm`, `PendingConfirmStore`, `build_proposal_text`, `send_sms_sync`, `parse_reply`, `resolve_inbound`, `expire_pending`
- Persisted store: `~/.anticipy/v7/pending_confirms/{task_id}.json` (atomic temp+os.replace)
- Inbound poller (10s default): `_poll_inbound_rows`, `start_inbound_poller`. Polls Supabase `anticipy_sms_inbound` table.
- Background expiry sweeper (60s): marks expired after 5 min, sends follow-up
- 5 endpoints: `/api/sms/inbound`, `/api/sms/pending`, `/api/sms/pending/{id}`, `/api/sms/pending/{id}/dispatch`, `/api/sms/expire/run`
- Gates: defense-in-depth in `/api/act` AND inside `_run_action_engine` before DSv4SkillRunner clicks Send
- `__sms_confirmed` marker prevents YES-reply loop
- Twilio safety: `TWILIO_MOCK=1` OR `TWILIO_TEST_TO_REAL_NUMBER!=1` returns mock response, no real SMS

### Post-action receipt (commit fc3a041f)
- `_emit_action_receipt` in `server.py`: orchestrates SMS + self-email
- `_send_receipt_sms_sync`: Twilio gated as above
- `_send_receipt_email_via_cdp`: Gmail draft to `omarkebrahim@gmail.com` (default `ANTICIPY_USER_EMAIL` env)
- `_capture_gmail_action_proof`: extracts Message-ID from `location.hash`, takes PNG screenshot via CDP, builds canonical sent_link
- Screenshots saved to `~/.anticipy/v7/receipt_proof/<ts>.png`
- SMS body: `"Anticipy just sent {recipient} an email about {subject}. View: {sent_link}. Reply STOP to silence."`
- Self-email body embeds screenshot path + message_id + sent_link
- Endpoint: `POST /api/dispatch/with_receipt` (force-fire receipt)
- Env gate: `ANTICIPY_RECEIPT_ON_SUCCESS=1` for env-gated path

### Persistent task queue (commit 261eb768)
- `engine/app/task_queue/store.py`: TaskRecord dataclass, JSONL journal + index, enqueue/claim_next/complete/fail/reschedule/wait_for/cancel/get/list_tasks/scan_due/resume_after_restart
- `engine/app/task_queue/dispatcher.py`: background scanner thread 60s (`ANTICIPY_TASK_QUEUE_INTERVAL_SECONDS`), register_executor, schedule_engine_restart_recovery
- Exponential backoff: 1m / 5m / 30m / 2h / 12h then terminal fail
- Persistence: `~/.anticipy/v7/task_queue/queue.jsonl` (append-only) + `index.json` (cache)
- 5 HTTP endpoints: POST /api/task_queue/enqueue, GET /api/task_queue/list, GET /api/task_queue/{id}, POST /api/task_queue/{id}/cancel, POST /api/task_queue/scan
- Server startup hook: register_executor + schedule_engine_restart_recovery + start_scanner
- `/api/listen/inject` mirrors actionable transcripts into queue
- `/api/act` enqueues + marks done on success
- Smoke tests: 6/6 PASS (basic + restart + HTTP)

### Handoff (commit bc54a03e)
- `engine/app/anticipy/handoff.py` (NEW today, 209 lines): convenience layer
- Routes: GET /api/auth/handoff/session, POST /api/auth/handoff/exchange
- Caches non-sensitive record at `~/.anticipy/session.json` (tokens stay in keychain)
- Website still owns real Supabase round-trip: `src/lib/handoff-token.ts` + `src/app/api/auth/exchange/route.ts` + `src/app/api/auth/handoff/mint/route.ts`
- Tauri desktop calls website directly (`desktop/src-tauri/src/lib.rs:365`)
- Try/except unwrapped: future packaging regressions surface

### Proactive engine
- `engine/app/proactive/types.py`: NOTED/IN_APP/PUSH/SMS/VOICE channel ladder, urgency 1-5, EXECUTE/ASK/LOG/REFUSE decider
- `engine/app/proactive/notifier.py`: local_notify (osascript), twilio_sms, twilio_voice (all wired but partial channel-by-urgency routing)
- `engine/app/proactive/dispatcher.py`: LLM-driven dedup gate
- `engine/app/proactive_day/comms.py` (older): silent_queue + DEBOUNCE_S merge logic, needs porting to proactive/notifier.py
- `engine/app/proactive_day/timing.py`: understands "after the meeting/standup/sync"
- Calendar adapter: NOT wired (per-meeting busy detection missing)
- DeliveryRoutes.push/.sms/.voice slots wired
- Endpoint: POST /api/notify/test for local channel
- GAP: proactive_fires_unprompted not yet end-to-end. G9 gate exposes this.

### Bridge (Chrome control)
- `scripts/v7/anticipy_bridge_fallback_cdp.py`: HTTP on 127.0.0.1:7777, multiplexes CDP via WS to ws://localhost:9222/devtools/browser/<guid>
- Background tabs via Target.createTarget(background=true)
- Tab-ownership map (`_ANTICIPY_OWNED_TARGETS`, commit eb8e44ce): only Anticipy-spawned tabs may be reused; user tabs NEVER hijacked
- Chrome on 9222: user's real Chrome with `--remote-debugging-port=9222` against real user-data-dir (Chrome 136+ refuses `--remote-debugging-port` against default profile)
- Started by `~/Library/LaunchAgents/com.anticipy.chrome.plist`

### ASR (listening)
- parakeet_mlx in packaged sidecar
- Mic devices: enumerated (CHECK 11 PASS earlier today)
- Ambient mic UX on first launch (Item 7 done)
- MP3 upload at `/onboarding/audio` → `POST /api/onboarding/from_audio`
- Text inject: `POST /api/listen/inject` (primary test path)

### Onboarding (3 paths)
- Twilio voice call: `scripts/v7/twilio_onboarding_call.py` + `/api/onboarding/call_stub`. Uses INTERVIEW_SCRIPT in `engine/app/anticipy/onboarding.py`.
- MP3 audio: `/onboarding/audio` page
- In-app chat: `src/app/onboarding/chat/page.tsx` → `/api/onboarding/chat_complete`
- Tauri popover welcome: `desktop/src/popover.html` with TCC permissions explainer
- TODO: TCC walkthrough for screen recording / accessibility / automation (only mic covered today)

### Web side (anticipy.ai on Vercel)
- `src/app/` Next.js 14 App Router
- Pages: `/` (marketing), `/app` (post-install), `/app/download` (DMG redirect), `/flash`, `/onboarding/audio`, `/onboarding/chat`, `/admin`, `/analytics`
- API routes:
  - `/api/engine/model` (OpenRouter broker, rate-limited, Supabase user required) ← DeepSeek V4 Flash + Kimi K2.6 only
  - `/api/engine/session` (handoff)
  - `/api/auth/exchange` (real Supabase round-trip)
  - `/api/auth/handoff/mint`
  - `/api/twilio/sms-inbound` (NEW today, NOT YET DEPLOYED to Vercel)
  - `/api/engine-transfer-gate` (cross-device dossier)
- DMG: `/dl/Anticipy_1.0.0_aarch64.dmg` redirects to R2, len 2515666283
- Supabase: project "handlit" ref ogbxpqkmsdrcuilafycn
- Supabase tables: `anticipy_waitlist`, `anticipy_admin_users`, `engine_users`, `browser_profiles`, `engine_tasks`, `anticipy_sms_inbound` (NEW today)
- Stripe: account "Aevoy" (`acct_1T3RNiBMF3gCPOse`) for pre-orders

### Tauri desktop app
- `desktop/src-tauri/src/lib.rs`: menubar tray + 480x600 popover
- `desktop/src/popover.html` + main.js + styles.css
- Sidecar launch logic at lib.rs:1037 (short-circuits if 8731 already healthy)
- Build: `bash desktop/scripts/build-engine-sidecar.sh` (PyInstaller, ~70-120s, 164MB output)
- TODO: Apple polish pass (being built by aabb6378)

### Tests + harnesses
- `engine/tests/anticipy_acceptance.py`: 18 CHECKs (definition of acceptance: 14/15 PASS)
- `engine/tests/agent_reliability.py`: 30 scenarios (20 resolvable + 10 ambiguous) — currently 28/30
- `scripts/v7/z001_e2e_harness.py`: full install → handoff → inject → real Gmail draft
- `scripts/v7/stranger_flow.sh` (NEW today, 964 lines): wipe + cold-start + inject + verify + restore
- `scripts/v7/dress_rehearsal.sh` (NEW today): 3-scene demo verifier with append-only log at `state/demo/dress_rehearsal_log.json`
- `scripts/v7/universal_beyond_google.sh` (NEW today, 278 lines): G7 verify
- `scripts/v7/demo_scenarios.sh` (NEW today, being built): G8 verify
- `engine/scripts/task_queue_*.py`: 3 task queue smoke harnesses
- `engine/scripts/sms_inbound_relay_smoke.py`
- `engine/scripts/receipt_audit_trail_smoke.py`

### Active agents (8 in flight as of cycle 88-89)
| Agent ID | Mission | Files |
|---|---|---|
| a58b648e | G7 non-Google surfaces | scripts/v7/universal_beyond_google.sh |
| af9908989 | G8 real-world demo scenarios | scripts/v7/demo_scenarios.sh |
| a967fe7f | G10 channel-by-urgency router + voice call | engine/app/product/channel_router.py |
| aabb6378 | Apple polish on popover | desktop/src/popover.html, styles.css, lib.rs |
| a8bd1a31 | Calendar auto-prep | engine/app/product/calendar_prep.py |
| a52d4943 | G11 cost telemetry | engine/app/product/cost_telemetry.py |
| a4297114 | G12 failure recovery | engine/app/product/failure_recovery.py |
| ae49b8dc | Real-voice TTS | engine/app/product/tts.py |

### Memory files (saved guidance, future sessions auto-load)
- `feedback_scale_not_local.md`
- `feedback_harness_defaults.md`
- `feedback_research_rigor.md`
- `feedback_autonomy_halts.md` (5 valid halts)
- `feedback_no_em_dashes.md` (owner's #1 hate)
- `feedback_no_fabrication.md`
- `feedback_no_api_keys.md` (browser nav only, OpenRouter OK)
- `feedback_synthetic_adversarial.md`
- `feedback_reuse_frozen_risk.md`
- `feedback_no_100_million_percent.md` (don't claim done while red gates exist)
- `feedback_refund_discretion.md`
- `feedback_no_real_send_testing.md` (superseded by sms_pre_confirm + channel_by_urgency)
- `feedback_sms_pre_confirm.md`
- `feedback_persistent_follow_through.md`
- `feedback_channel_by_urgency.md` (phone/SMS/email/silent matrix)
- `feedback_apple_like_polish.md`
- `feedback_test_beyond_google.md` (must test ≥3 non-Google surfaces)
- `project_cost_ceiling_200_per_user_year.md`
- `project_anticipy_pricing_2026.md` ($199 retail, $149.99 pre-order)
- `project_codex_handoff.md`
- `project_fara_build_plan.md`
- `project_anticipy_goal_blocked.md`
- `reference_stripe_aevoy.md`

### Env vars in use
- `ANTICIPY_PORT=8731`
- `ANTICIPY_CDP_PORT=9222`
- `ANTICIPY_ACCOUNT_ID=anticipy-user`
- `ANTICIPY_ALLOW_REAL_SEND=1` (1 enables real send, 0 = drafts only; default 0 if unset)
- `ANTICIPY_USER_EMAIL=omarkebrahim@gmail.com`
- `ANTICIPY_RECEIPT_ON_SUCCESS=1`
- `ANTICIPY_INBOUND_SMS_POLL=0|1`
- `ANTICIPY_INBOUND_SMS_POLL_INTERVAL_SECONDS=10`
- `ANTICIPY_TASK_QUEUE_INTERVAL_SECONDS=60`
- `ANTICIPY_WINDOW_SECONDS=2`
- `SSL_CERT_FILE=/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages/certifi/cacert.pem`
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`
- `TWILIO_TEST_TO_REAL_NUMBER=1` (gate: requires explicit opt-in for real send)
- `TWILIO_TEST_TO_REAL_NUMBER_E164` (user's phone)
- `TWILIO_NOTIFY_TO`
- `TWILIO_MOCK=1` (returns mock SMS response in dev)
- `ANTICIPY_ENV_FILE` (path to .env.local)
- `ANTICIPY_NO_LOCAL_ENV=1`
- `ANTICIPY_WEBSITE_URL` (default https://www.anticipy.ai)
- `ELEVENLABS_API_KEY` (when ae49b8dc lands)
- `OPENROUTER_API_KEY` (LLM brain)
- `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`

### Cron infrastructure
- Job ID: `0639fc94`
- Cadence: every 3 minutes
- Lifetime: session-only, 7-day max
- Prompt: invokes CYCLE_PROCEDURE.md steps 1-8

### Critical paths (don't break)
- `/api/listen/inject` → planner → `/api/act` → action engine → confirm card / dispatch
- `/api/coldstart/start` → cdp_walker → auto_inhale → dossier writes
- `/api/trivia/recent` → trigger detection → cache lookup → TTS via deliver.py
- `/api/dispatch/with_receipt` → action + receipt
- `/api/sms/inbound` → reply parser → task resume
- `/api/task_queue/enqueue` → scheduler → executor
- `scripts/v7/z001_e2e_harness.py` → full E2E proof
- `scripts/v7/stranger_flow.sh` → install + use proof

## 6. Known gaps (truthful)

- G7 untested (script exists, agent iterating)
- G8 untested (script being built)
- G9 RED (no proactive discovery script yet)
- G10 RED (channel_router being built)
- G11 RED (cost telemetry being built)
- G12 RED (failure recovery being built)
- G5 flapping on dev (source uvicorn keeps winning port race; resolved on stranger Mac)
- Vercel deploy of `/api/twilio/sms-inbound` route NOT live yet
- Apple polish pass not done (being built)
- Real-voice TTS not done (being built)
- Memory consolidation deferred (4 impls still coexist, but planner unifies at read time)
- TCC permissions walkthrough only covers mic
- Calendar auto-prep being built
- Per-user multi-tenancy not built
- Speaker biometrics not built
- Telemetry from real installs not built
- Pendant hardware doesn't exist (V2 scope)

## 7. Recent commits (today's wave, in chronological order)

```
51d3c609 engine: replace V1+V2+V3 hardcoded violations with unified LLM intent extractor
a1d7b096 G1 install_under_5min: planner sees active dossier people
bc54a03e handoff: replace ghost import with real engine-side convenience routes
c2879c67 SMS pre-confirm gate before any irreversible action
9393d989 post-action receipt: document the wire-up that landed in c2879c67
666fd4b2 (in DEV-FINAL worktree) persistent task queue store + dispatcher
261eb768 P0 task 1: persistent task queue cross-repo deploy to V7 main
6603b4bb P0 task 2: inbound SMS webhook on website + engine poller
fc3a041f P0 task 3: audit-trail screenshots + verifiable identifiers in receipts
eb8e44ce bridge: fix tab hijack via _ANTICIPY_OWNED_TARGETS ownership map
81ab6b17 universal action loop module + /api/universal/run endpoint
```

## 8. How to read state

```bash
# Engine alive?
lsof -nP -iTCP:8731 -sTCP:LISTEN

# Which engine? (packaged vs source)
PID=$(lsof -nP -iTCP:8731 -sTCP:LISTEN | awk '/LISTEN/{print $2}' | head -1)
ps -p $PID -o command=

# Z-001 verdict
ls -t state/v7/z001_e2e_runs/*/result.json | head -1 | xargs jq -r .verdict

# Dossier people
jq -r '.people | length' ~/.anticipy/v7/dossiers/anticipy-user/dossier.json

# Stranger flow verdict
ls -t state/v7/stranger_flow_runs/ | head -1 | xargs -I{} jq -r .verdict state/v7/stranger_flow_runs/{}/result.json

# Dress rehearsal last 3
jq -r '.runs[-3:] | .[] | "\(.started_at) \(.verdict)"' state/demo/dress_rehearsal_log.json

# Trivia fires
curl -sS http://127.0.0.1:8731/api/trivia/recent | jq -r '.fires[0:3]'

# Task queue state
curl -sS http://127.0.0.1:8731/api/task_queue/list | jq -r '.tasks[] | "\(.task_id) \(.status) \(.instruction[0:60])"'

# Cron status
# (in this session: CronList tool)
```

## 9. Hard rules for new agents

- Read this file first.
- Read `HANDOFF_FOR_NEXT_AGENT.md` second.
- Read `NORTH_STAR_v2.md` third.
- Then check `ORCHESTRATOR.md` for current state.
- Never use em-dashes. Owner's #1 hate.
- Never claim done without running the verify command.
- Never break Z-001. Revert with `git reset --hard HEAD~1` if you do.
- Never edit frozen-ish files without understanding the seam (anticipy/, action_engine/, proactive_day/, verifier/ — these were "frozen" but owner unfroze on 2026-05-29 with "Just don't break it.")
- Drive Chrome only via the bridge at 127.0.0.1:7777 (which talks to user's real Chrome on :9222). Never use a fresh headless Chrome unless explicitly told.
- Browser actions go through Anticipy-owned tabs only. Use `_cdp_create_target` (NEW path) not `_cdp_navigate` with `prefer_in_place=True` (HIJACK risk).
- For sends/posts/submits: pre-action SMS confirm fires automatically via the gate in `/api/act` (commit c2879c67). Don't bypass.
- Cost: keep per-task LLM calls under 5 (planner + maybe 1-3 vision + final compose). Watch the running cost via `/api/cost/stats`.

## 10. Trust contract

- The orchestrator writes mechanical status to this file + ORCHESTRATOR.md every cycle.
- Owner can audit any time without asking a planner.
- Every GREEN claim is backed by a verify command that exits 0 on disk.
- No "I assure you it works" messages.
- Stagnation 3 cycles in a row = STUCK.json + notify owner.
- 12 gates GREEN simultaneously for 5 cycles + 3 full E2E tests PASS = DONE_v2.json.

That's everything that matters. Read this. Read the rules. Then act.
