# Engine State — 2026-05-11 19:35 UTC

> Reconnaissance only. No application code was modified in this pass.
> Bucket key: DOES_NOT_EXIST · EXISTS_UNTESTED · RUNS_LOCALLY · RUNS_IN_PRODUCTION · PROVEN_END_TO_END.
> Evidence files in `recon/`.

## TL;DR

The chain is at best **RUNS_IN_PRODUCTION for individual hops, never PROVEN_END_TO_END**. The web app, the engine FastAPI on Railway, and the Supabase tables are all live and reachable. But **no end-to-end run has ever produced a confirmed real-world action through this stack** by the evidence available: 435 intents in production, 0 with `executed_at` set; 138 browser-agent trajectories, 129 fail / 9 pass (only Wikipedia lookups); the multi-agent endpoints that STATUS.md claims passed in production are now all returning HTTP 503 "disabled — Executor only"; the pendant-audio path described in VISION.md does not exist (audio capture only via `/engine` page MediaRecorder in a browser). The proactive cascade exists in code and unit-tests cleanly, but its Realtime channel (`anticipy-intents`) received 0 messages in a 30s listen window today. **The lowest hop in the chain — audio capture from a pendant — is `DOES_NOT_EXIST`. That puts the full product chain at `DOES_NOT_EXIST` regardless of what works above it.**

## The end-to-end chain

| # | Hop | Bucket | File:Line | Evidence |
|---|---|---|---|---|
| 1 | Audio capture (pendant) | **DOES_NOT_EXIST** | — | No firmware-to-server audio. `firmware/` has PCB/case design only (`platformio.ini`, `DESIGN.md`). No mic streaming code anywhere. |
| 1b | Audio capture (browser fallback) | RUNS_IN_PRODUCTION | `src/app/engine/page.tsx:759` (`getUserMedia`), `:893` (`new MediaRecorder`) | Wired in the `/engine` page; gated on Chromium + WebM support. |
| 2 | Audio transport | RUNS_IN_PRODUCTION | `src/app/engine/page.tsx:802` (wss to `api.deepgram.com`) | Direct from browser to Deepgram with an ephemeral key from `/api/engine/deepgram-key`. |
| 3 | Transcription (Deepgram) | RUNS_IN_PRODUCTION | `src/app/api/engine/transcribe/route.ts:58` writes to `anticipy_transcripts` | Newest row 2026-05-08, 40 rows total. Production path works; nothing written in the last 3 days. |
| 4 | Intent extraction (cascade) | RUNS_IN_PRODUCTION | `src/app/api/engine/analyze/route.ts:227` writes `anticipy_intents` | 435 intents; newest 2026-05-08. Live LLM cascade (Gemini/Groq/Kimi/Claude) wired. |
| 5 | Decision storage | RUNS_IN_PRODUCTION | `analyze/route.ts:227,261,290,702,783` | Table exists; 435 rows present. |
| 6 | Decision publish (Supabase Realtime) | RUNS_IN_PRODUCTION | `analyze/route.ts:851` `POST /realtime/v1/api/broadcast`, `engine/app/bridge_extension.py:94` (engine-side same path) | Endpoint reachable. Realtime subscribe succeeded; 0 messages in a 30s listen (no production traffic right now). |
| 7 | Extension subscribe | EXISTS_UNTESTED in prod | `extension/background.js:163` (`wss://...supabase.co/realtime/v1/websocket`), `:234` `new_intent`, `:237` `confirmed_intent` | Code is correct (the v1 extension); never observed receiving a real production broadcast in this session. The dist served at `/anticipy-extension.zip` (v1 layout, manifest version 2.0.0) IS this code. |
| 8 | Extension UI (popup) | EXISTS_UNTESTED in prod | `extension/popup.html:223–237`, `extension/popup.js:65` `POST anticipy.ai/api/extension/auth` | Auth endpoint live (`401 Invalid access code` on bad input). Real sign-in flow not exercised in this session. |
| 9 | Donna voice layer | EXISTS_UNTESTED in prod | `engine/app/proactive/donna_voice.py:94/109/136` | Code present, has unit tests (`test_donna_voice.py`), no evidence it has ever run in a production pendant flow because (1) is gone. |
| 10 | Browser action execution | RUNS_LOCALLY (Wikipedia only), **never PROVEN end-to-end** | `extension/agent.js:538`, `engine_trajectories` | 138 attempts in production logs; 129 fail (4-minute wall-clock timeouts), 9 pass — every pass is a `wikipedia.org` lookup task. No mail send, no calendar create, no reservation, no purchase. |
| 11 | Confirmation back to user | EXISTS_UNTESTED in prod | `src/app/api/engine/confirm/route.ts:284`, `src/lib/execute-action.ts` | Confirm endpoint and tier-1 (Gmail/Calendar) action path are wired. `anticipy_intents.executed_at` is **NULL on 435/435 rows** including the 16 marked `status=executed`. |

**Top-of-chain bucket is `DOES_NOT_EXIST`** because the spec defines the product as "pendant captures audio → action," and pendant-to-server audio capture has no code. The browser-page fallback at hop 1b changes the product shape (chatbot, not ambient) — see Architectural Questions.

## Components

### Audio capture (pendant) — DOES_NOT_EXIST
No code path receives audio from the firmware. `firmware/` contains hardware design and platformio.ini only; no audio streaming protocol, no daemon listening for audio bytes. To move one bucket: define a transport (BLE→phone→/api/engine/transcribe? direct WiFi?) and ship the firmware code.

### Audio capture (browser) — RUNS_IN_PRODUCTION
`src/app/engine/page.tsx` calls `getUserMedia` + `MediaRecorder`, opens a WS to Deepgram. Capability-detects mobile/Safari/Firefox and refuses with `unsupportedReason` rather than failing silently. To move to PROVEN: a tracked session where audio→intent→action→evidence completes.

### Audio transport — RUNS_IN_PRODUCTION
Browser↔Deepgram WS direct. Bypasses our server entirely; no audio is stored.

### Transcription — RUNS_IN_PRODUCTION
40 rows in `anticipy_transcripts`. Newest 2026-05-08T06:00:44Z (3 days stale). RLS allows the user's own rows only (anon key can't see rows with the session JWT we don't hold).

### Intent extraction (proactive cascade) — RUNS_IN_PRODUCTION
- Code: `engine/app/proactive/*.py` (L0..L6 cascade), `src/lib/intent-extract.ts`, `src/lib/intent-gates.ts`, `src/app/api/engine/analyze/route.ts`.
- Production data: 435 intents in `anticipy_intents`, newest 2026-05-08.
- Unit tests pass (sampled 121 in 7.94s across 7 files).
- Gemini, Groq, Kimi, Claude all wired; `/api/health` confirms supabase/deepgram/gemini/groq/resend env vars set on Vercel.

### Decision storage — RUNS_IN_PRODUCTION
Status histogram (service role count):
- pending: 410
- executed: 16 (but `executed_at` is **NULL on every row in the table**)
- failed: 4
- awaiting_user / accepted / rejected / expired: 0

The 16 "executed" rows date from 2026-04-10 and look like seeded test data ("call your mom for her birthday"). Nothing in `anticipy_intents` has ever been confirmed-end-state-completed.

### Decision publish (Realtime) — RUNS_IN_PRODUCTION
Realtime subscribe to `anticipy-intents` returned `SUBSCRIBED`; received 0 broadcasts in a 30s window. Code that publishes exists in two places: `analyze/route.ts:851` (Vercel) and `engine/app/bridge_extension.py:94` (Railway engine). `recon/realtime_listen.log` is the evidence.

### Extension subscribe — EXISTS_UNTESTED in prod
The v1 extension (`extension/`, manifest `name="Anticipy"`, version 2.0.0) connects to `wss://ogbxpqkmsdrcuilafycn.supabase.co/realtime/v1/websocket` and filters on `event === "new_intent"` and `event === "confirmed_intent"`. Code reads correctly. We did not observe it receive a real production broadcast.

### Extension UI — EXISTS_UNTESTED in prod
Popup has access-code form (`popup.html:233`). `popup.js:65` POSTs to `https://www.anticipy.ai/api/extension/auth`. Endpoint live: bad code → `401 Invalid access code`. Did not exercise a real sign-in.

### Multiple competing extension versions
- `extension/` — name "Anticipy", v2.0.0, **Supabase Realtime model**. Has `agent.js` (2022 LOC) BrowserAgent. **This is what `/anticipy-extension.zip` serves.**
- `extension_v2/` — name "Anticipy Bridge", v2.0.0, connects `wss://anticipy-production.up.railway.app/ws/agent`. Live endpoint (returns "Invalid access code" on no-auth). Served as `/anticipy-extension-v2.zip`.
- `extension_v3/` — name "Anticipy Bridge v3", v3.0.0, same `wss://.../ws/agent`. Served as `/anticipy-extension-v3.zip`.
- `extension_v4/` — name "Anticipy Bridge v6", v6.0.0 (yes, v4 dir = v6 manifest), **native-messaging to a local Python daemon** (`native_host/anticipy_agent.py`). Served as `/anticipy-extension-v4.zip`, `/anticipy-extension-v5.zip`, `/anticipy-extension-v6.zip` (all identical files modulo bytes).

**Three incompatible architectures shipping in parallel.** See Architectural Questions.

### Donna voice layer — EXISTS_UNTESTED in prod
`engine/app/proactive/donna_voice.py` has `compose_ask_narrative`, `compose_completion_narrative`, `compose_refusal_narrative`. Unit tests pass. Not wired into the production `/engine` page (no references to "donna" or compose_* in `src/`). Currently dead-code w.r.t. production user-facing copy.

### Browser action execution — RUNS_LOCALLY (Wikipedia only)
`engine_trajectories`: 138 rows, 129 fail / 9 pass. The 9 passes are all `wikipedia.org` lookups. The latest pass (today, 2026-05-11T03:39Z): `"What year was Python first released? Use Wikipedia."` — 3 steps, 8.4s. The latest fail (today, 2026-05-11T04:19Z): `"What is the total height of the Eiffel Tower including antennas? Use Wikipedia."` — 240s wall-clock timeout, 0 steps recorded. Even the success class is Wikipedia-only and the failure mode (4-minute hang with zero recorded steps) suggests instability of the loop itself.

### User confirmation channel — EXISTS_UNTESTED in prod
`/api/engine/confirm` exists. `execute-action.ts` has Tier-1 (Resend email, Google Calendar, Twilio SMS) and Tier-2 (browser agent via `/execute-intent` on Railway). No row in `anticipy_intents` has `executed_at` set, so the success branch has never closed.

### Memory layer — EXISTS_UNTESTED (no production data)
Code: `engine/app/memory.py` with `InProcessMemoryBackend` and `SupabaseMemoryBackend`. The `memories` table **does not exist** in production Supabase (`404`). The code references it via `supabase_client`. So in production, anything that writes to the memory layer either silently 404s or falls back to in-memory storage that dies with the process. `delete` is explicitly logged as not-implemented on the Supabase backend (`memory.py:481`).

### Provider cascade with quota tracking — RUNS_IN_PRODUCTION (logic), unit-tested
`extension/agent.js` has `_isProviderBlocked`/`_markProvider429`/`_markProviderOk`. 12-test suite passes via `node --test extension/test_provider_quota.mjs`. **Today the cascade is configured for Kimi only** (per STATUS.md round 8); the popup still stores `cerebrasApiKey/groqApiKey/geminiApiKey/kimiApiKey/deepseekApiKey` (5-tier comment), so popup config and runtime config drifted apart.

### anticipy.ai/engine page — RUNS_IN_PRODUCTION
`GET https://www.anticipy.ai/engine` → 200, 12,966 bytes, title "Action Engine — Anticipy". Note: bare `https://anticipy.ai/...` returns 307 to `https://www.anticipy.ai/...` — anything that hits the apex domain needs `-L`.

### anticipy.ai/funded page — RUNS_IN_PRODUCTION
`GET https://www.anticipy.ai/funded` → 200, 42,736 bytes. Marketing page.

### Multi-agent endpoints (Planner/Verifier/Critic/Reflector) — DISABLED IN PRODUCTION
- `POST /api/agent/plan` → `503 {"error":"Planner disabled — Executor only"}`
- `POST /api/agent/verify` → `503 {"error":"Verifier disabled — Executor only mode"}`
- `POST /api/agent/critic` → `503 {"error":"Critic disabled — Executor only mode"}`
- `POST /api/agent/reflect` → `503 {"error":"Reflector disabled — Executor only mode"}`

`STATUS.md` (dated 2026-05-10) claims these were "5/5 pass validated in production" — code confirms they're now hard-disabled (e.g. `src/app/api/agent/plan/route.ts:101` returns 503). Round-8 architecture is **as deployed**, not as documented.

## Production surfaces

| URL | Status | Body excerpt |
|---|---|---|
| `https://anticipy.ai/` | 307 → `https://www.anticipy.ai/` | (redirect) |
| `https://www.anticipy.ai/` | 200, 54,548 bytes | Marketing site |
| `https://www.anticipy.ai/engine` | 200, 12,966 bytes | `<title>Action Engine — Anticipy</title>` (CSR) |
| `https://www.anticipy.ai/funded` | 200, 42,736 bytes | Funding/investor page |
| `https://www.anticipy.ai/api/health` | 200 | `{"ok":true,"env":{"supabase":true,"supabaseAdmin":true,"deepgram":true,"gemini":true,"groq":true,"resend":true}}` |
| `https://www.anticipy.ai/api/extension/auth` | 401 (with bad code) | `{"error":"Invalid access code"}` |
| `https://www.anticipy.ai/api/agent/{plan,verify,critic,reflect}` | 503 | `{"error":"<role> disabled — Executor only mode"}` |
| `https://www.anticipy.ai/api/engine/{transcribe,analyze,session,deepgram-key}` | 401 | `{"error":"Unauthorized"}` (require Supabase JWT) |
| `https://engine-production-eb43.up.railway.app/` | **404** | `{"status":"error","code":404,"message":"Application not found"}` |
| `https://anticipy-production.up.railway.app/` | 404 (no route) | — |
| `https://anticipy-production.up.railway.app/health` | 200 | `{"status":"ok"}` |
| `https://anticipy-production.up.railway.app/docs` | 200 | FastAPI Swagger UI: "Anticipy Action Engine" v1.0.0 |
| `https://anticipy-production.up.railway.app/auth/login` (POST {}) | 422 | Pydantic validation error (correct) |
| `https://anticipy-production.up.railway.app/proactive/events` | 401 | `{"detail":"Please sign in to continue."}` |
| `wss://anticipy-production.up.railway.app/ws/agent` | open then 4401 | `{"type":"error","message":"Invalid access code. Re-authenticate in the popup."}` |
| `wss://anticipy-production.up.railway.app/ws/task` | open | `{"type":"error","message":"I couldn't understand that request..."}` |
| `wss://anticipy-production.up.railway.app/ws/proactive` | HTTP 403 on WS upgrade | — |

The engine prompt referenced `engine-production-eb43.up.railway.app` — **that URL is dead**. The real engine is `anticipy-production.up.railway.app`. Worth checking which the production extension config still points at.

## Supabase

Project ref `ogbxpqkmsdrcuilafycn` (from `extension/background.js:8`). Service-role probe:

| Table | Exists | Rows | RLS visible to anon | Newest row |
|---|---|---|---|---|
| `engine_users` | yes | 3 | yes (own) | 2026-05-05 |
| `browser_profiles` | yes | 4 | yes | (no `created_at` column) |
| `engine_tasks` | yes | 0 | — | — |
| `engine_trajectories` | yes | 138 | filtered | 2026-05-11 (today) — 129 fail / 9 success |
| `anticipy_transcripts` | yes | 40 | filtered | 2026-05-08 |
| `anticipy_intents` | yes | 435 | filtered | 2026-05-08; 410 pending, 16 executed (executed_at NULL on all), 4 failed |
| `anticipy_waitlist` | yes | 9 | RLS hides from anon | 2026-05-?? |
| `anticipy_admin_users` | yes | 0 | — | — |
| `crm_contacts` | yes | 4 | filtered | 2026-05-06 |
| `crm_decisions` | yes | 1 | filtered | 2026-05-06 |
| `crm_todos` | yes | 3 | filtered | — |
| `crm_users` | yes | 2 | filtered | — |
| `memories` | **404** | — | — | — |
| `proactive_decisions` | **404** | — | — | — |
| `anticipy_episodes` | **404** | — | — | — |
| `anticipy_memories` | **404** | — | — | — |
| `crm_voice_sessions` | **404** | — | — | — |

Critical: tables the code expects (`memories`, `proactive_decisions`, `anticipy_episodes`) do not exist in production. The proactive-engine memory writes will silently fail or no-op.

Realtime listen on channel `anticipy-intents` (anon key, subscribe to `confirmed_intent` broadcast + postgres_changes on `anticipy_intents`): subscribed cleanly, 0 messages in 30 seconds. Log: `recon/realtime_listen.log`.

## Cop-outs found

Total matches for cop-out grep across app code: **99** (excluding tests). Of those, the meaningful ones:

1. `engine/app/end_state_verifier.py:353` — hardcoded `https://mail.google.com/mail/u/0/#sent` for the verifier's "did the email actually send?" check.
2. `engine/app/end_state_verifier.py:399` — hardcoded `https://calendar.google.com` for calendar-event verification.
3. `engine/app/planner.py:330,433` — hardcoded `https://www.google.com/search?q=…` as a starting URL (legacy planner; main path may have replaced it).
4. `engine/app/agent.py:1326` — special-case check for whether `start_url` is a google.com/search URL.
5. `engine/app/memory.py:481` — `logger.info("delete not implemented for SupabaseMemoryBackend")`.
6. `engine/app/proactive/urgency.py:16` — "ONLY hardcoded part: the score-to-channel mapping."
7. `src/app/api/agent/plan/route.ts:101` — Planner returns 503; comment: "Disabled — saves 1 Cerebras call per task. Re-enable when we have a separate quota pool for the planner." (See cop-out #23 in COP_OUTS.md: "the next session will fix it" deferral.)
8. `engine/app/main.py:207` — broad `except (NotImplementedError, RuntimeError)`.
9. `engine/app/memory.py:380` — comment notes a stub supabase client whose `update_rows` is a no-op (legitimate test affordance, not a runtime cop-out).
10. 0 hardcoded `/home/codespace/` or `/Users/*/` paths found in app code (cop-out #7 stayed fixed).

Full lists: `recon/copouts_general.txt`, `recon/copouts_sitespecific.txt`, `recon/copouts_paths.txt`.

## Tests

85 test files total in the repo. Classification by content:

- **Unit (mocked dependencies, no network):** ~70 files in `engine/test_*.py`, all `extension/test_*.mjs`, `__tests__/dedup.test.mts`, `native_host/test_protocol.py`. Sampled 121 tests across 7 unit files: **121/121 pass** in 7.94s.
- **Integration (real Supabase, real LLM, or fastapi TestClient with real cascade):** `test_chain_smoke.py`, `test_ws_agent_e2e.py`, `test_verifier_e2e.py`, `test_memory_e2e.py`, `test_extension_actions.py`, `test_extension_runner.py`, `test_bridge_extension.py`. **53/54 pass, 1 fail**: `test_chain_smoke.py::test_verifier_overrides_agent_silent_done` failed — bridge_extension warned `anticipy_intents upsert returned None for <id> — broadcast will still fire` and zero agent-completion events fired.
- **E2E (real browser + real internet):** `test_real_internet.py`, `test_real_machine.py`, `test_real.py`, `test_e2e_voice_action.py`, `test_torture_*.py`, `test_extension_brutal.py`. Gated on `ENGINE_REAL_BROWSER=1` + Xvfb. **TIME_BOXED_OUT** in this session — would require launching Chromium under Xvfb and is exactly what STATUS.md acknowledges as "Patchright codespace harness is unreliable."

Other:
- `__tests__/dedup.test.mts` via `node --test`: 35 pass, 0 fail.
- `extension/test_agent_diff_signals.mjs` + `extension/test_provider_quota.mjs`: 2 files, both pass.

Output log: `recon/test_output.log`.

## What I did NOT verify

Per the rules, I'm explicit about claims I could not confirm from this session:

- STATUS.md round-8 claim: "5-agent team deployed: `/api/agent/{plan,verify,critic,reflect}` live on Vercel production." **Refuted.** All four return 503 disabled.
- STATUS.md: "Multi-agent BRAIN validated in production (5/5 pass)" via `test_multi_agent_brain.py`. Refuted by current endpoint state.
- STATUS.md: "Full pipeline validated end-to-end on real internet (2026-05-09 21:02): … wiki_python_year PASS in 52.6s." Partially supported — `engine_trajectories` shows a 2026-05-09 21:30 Japan-population success and a 21:24 France-capital success; the 21:02 wiki_python_year entry is from 2026-05-11 03:39. The success class is real, narrow (Wikipedia lookups), and the trajectory schema does NOT capture whether Vercel's agent-team endpoints fired (they may have been disabled by then).
- STATUS.md: "501 unit tests passing." I ran a sample of ~121 tests, not the full set. The sample passed; the 501 figure I did not verify.
- STATUS.md: "Real Supabase Realtime broadcast wire is alive. REAL_BROADCAST_OK= True." Code reads correctly; in a 30-second listen I observed zero traffic on the channel.
- STATUS.md: "Memory layer wired and unit-tested." Unit tests yes; production tables (`memories`, `anticipy_memories`, `anticipy_episodes`) do not exist — production writes will fail.
- CLAUDE.md: "engine_users, browser_profiles, engine_tasks." All exist. `engine_tasks` is empty (0 rows). Not refuted; just no live traffic.
- VISION.md: "Wearer wears a pendant. Pendant captures audio. The system listens, understands, decides on its own when something needs to happen, and acts." Pendant→audio→server path **does not exist**. The current product takes audio from a browser MediaRecorder on the `/engine` page after a user clicks Record. That is a chatbot product shape, not the ambient product VISION.md describes.
- COP_OUTS.md #19: "Localhost-as-access-port. The previous Python access port connects to http://localhost:8000." Code shows `engine/access_port.py` is still untracked/orphan (in git status) and `engine/_chain_real.py` is also untracked. Whether the new path is truly off localhost was not validated end-to-end.

## Architectural questions for Omar

The code reflects multiple competing architectures shipping side by side. Pick one for each of these before any more engineering, or be explicit that you're shipping all of them.

1. **What is the production audio path?** VISION.md says pendant-captures-audio. The deployed code only captures audio when the user opens `/engine` in Chrome and clicks Record. No pendant transport exists. **(a)** Build pendant→server audio (BLE→phone→API? direct WiFi?) and remove the browser-record flow; **(b)** keep the browser as the official input and rewrite VISION.md to match; or **(c)** ship both and document which is canonical.

2. **Which extension is the real one?** Three architectures shipped in `public/`:
   - v1 (`/anticipy-extension.zip`): Supabase Realtime model. Listens directly to the Realtime channel and acts in-browser.
   - v2 / v3 (`/anticipy-extension-v{2,3}.zip`): thin relay; agent brain on Railway via `wss://…/ws/agent`.
   - v4 / v5 / v6 (`/anticipy-extension-v{4,5,6}.zip`): native messaging to a local Python daemon (`native_host/anticipy_agent.py`).
   
   STATUS.md says round 8 picked v1 + Realtime. The Engine page (`/engine`) links to `/anticipy-extension.zip`. The README docs for v4/v6 still ship. **Pick one and delete the others' code paths, or document which is canonical and which are experiments.**

3. **Where do API keys live?** Three current answers in code:
   - The extension popup stores `cerebrasApiKey/groqApiKey/geminiApiKey/kimiApiKey/deepseekApiKey` in `chrome.storage.local` after fetching them from `/api/extension/auth`. Server hands user-scoped keys to the extension — keys reach the user's machine.
   - The Railway engine has its own server-side keys for the proactive cascade.
   - Vercel API routes have their own server-side keys for `/api/engine/analyze`.
   
   Three copies of the same secrets in three trust domains. Is "extension holds keys directly" the long-term answer, or is it a workaround until `/api/extension/llm-proxy` covers everything?

4. **What is `anticipy.ai/engine` supposed to be in the V1 product?** Today it's a sign-in + record-audio + see-intents chat page. If the product is pendant-driven and ambient, `/engine` is a debugging surface, not a user surface. Or is it the marketing-time demo? STATUS.md does not say.

5. **Why are the multi-agent endpoints disabled in production?** STATUS.md claims they're the core architecture. Production returns 503. Either re-enable them (and own the cost), or update STATUS.md to "Executor-only mode" and explain why.

6. **The 16 "executed" intents have `executed_at = NULL`.** Were they ever actually executed? The 4 "failed" rows would tell us, but the broader question: does the confirmation feedback (executor → status='executed' + timestamp) actually work, or is it a partial implementation? Until a single real-world action records `executed_at`, the chain has never closed end-to-end. **Pick a single test scenario, drive it through, and assert the row updates in Supabase.** That's the minimum bar to move "Browser action execution" to PROVEN_END_TO_END.

7. **Missing tables.** Code expects `memories`, `proactive_decisions`, `anticipy_episodes`. Supabase returns 404. Either apply the migrations (`supabase/migrations/` exists in the repo) or rip the code paths that depend on them.

8. **Stale Railway URL in the prompt.** You handed me `engine-production-eb43.up.railway.app`, which is dead. The live one is `anticipy-production.up.railway.app`. Is `engine-production-eb43` a previous deployment that was decommissioned, or a name that exists in production config somewhere? Worth grepping production secrets.

9. **What counts as a "real" test on your Mac?** Per `feedback_no_code_review.md` (auto-memory): "stop auditing wired-vs-scaffolded; only metric is hard real tasks (not 'open a website' easy) passing on his actual Mac." None of the 9 successful trajectories meets that bar — they're all "look up X on Wikipedia." Pick the first three hard tasks you actually want to validate (e.g. "book Carbone Friday 7pm OpenTable," "draft email to Alex re: Q2 plan in Gmail," "add lunch with Sarah to my calendar") and we measure against those, not Wikipedia lookups.

10. **The `extension_v4` directory has manifest `name="Anticipy Bridge v6"` and `version: "6.0.0"`.** The dir name says v4. Renaming or moving will break the installer (`installer/install.sh` hardcodes `extension_v4` paths). Worth documenting before more numbering drift.
