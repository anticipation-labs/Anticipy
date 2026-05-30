# Existing-code map. Anticipy V7

Reference doc, dense. File:line citations are absolute paths under `/Users/omarebrahim/Developer/Anticipy-V7/`. Last walked 2026-05-29.

## Table of contents

1. [Engine entry points](#1-engine-entry-points)
2. [Frozen paths (Omar's invariant)](#2-frozen-paths)
3. [Memory system](#3-memory-system)
4. [Browser bridge and CDP](#4-browser-bridge-and-cdp)
5. [Planner, intent extractor, action binder](#5-planner-intent-extractor-action-binder)
6. [Onboarding](#6-onboarding)
7. [Surface adapters](#7-surface-adapters)
8. [Acceptance tests](#8-acceptance-tests)
9. [Web side](#9-web-side)
10. [Abandoned / legacy code](#10-abandoned--legacy-code)
11. [Cron jobs, launchd, supervisors](#11-cron-launchd-supervisors)

---

## 1. Engine entry points

The shipped product binds **`app.product.server:app`** on `127.0.0.1:8731`. Everything else is legacy or test-only.

- **`engine/app/product/server.py:53`**. FastAPI `app = FastAPI(title="Anticipy", version="product-3")`. This is the file every entry point reaches. About 7900 lines; ~50 HTTP routes; all the state, runtime helpers, planner glue, listen loop, dossier endpoints, confirm-card flow.
- **`engine/app/product/main.py:56-61`**. desktop entry. `_serve()` calls `uvicorn.run(app, host="127.0.0.1", port=port)` with `port = 8731` (`main.py:68`). Threaded behind `webview.create_window("Anticipy", url, ...)` at line 170. Honors `ANTICIPY_PORT` and `ANTICIPY_HEADLESS` envs.
- **`engine/anticipy-engine.spec`**. PyInstaller spec. Entry script is `app/product/server.py` (line 14). This is the spec the packaged `Anticipy.app` build uses for the CLI sidecar.
- **`engine/Anticipy.spec`**. alt PyInstaller spec, entry `app/product/main.py` (line 26). Produces `Anticipy.app` bundled with webview.
- **`engine/Anticipy-win.spec`**. Windows variant. Not shipped.
- **`engine/start.sh:23`**. `exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`. Legacy Docker entry (`engine/Dockerfile`, `engine/fly.toml`). Targets `app.main:app` not `app.product.server:app`, so this would start the old Browser-Use engine, not the v-final product engine. Should not be used.
- **`engine/app/main.py`**. legacy FastAPI server (Browser Use wrapper). Kept for reference, not the shipped path. ~57 KB.
- **`engine/app/server.py:27`**. third FastAPI app, `phase2` build, exposes `/journey/run` calling `app.e2e.flow.run_flow`. Dead.
- **`engine/scripts/`**. assorted Python scripts; none are entry points.
- **`scripts/v6/dispatch_*.sh`**, **`scripts/v7/orchestrate_v7.sh`**. shell wrappers that start uvicorn inline for tests; not used by the packaged app.

**Canonical for shipped Mac app**: `app/product/main.py` → starts `uvicorn` against `app/product/server.py:app` on port 8731. The verifier and acceptance harness read `~/.anticipy/engine.port` or fall back to 8731 (`verifier/lib/engine.py:25-26`).

---

## 2. Frozen paths

Per CLAUDE.md and `engine/tests/anticipy_acceptance.py:946` (CHECK 17), the build-failing rule is `git diff --name-only -- engine/app/action_engine engine/app/proactive_day engine/app/anticipy` must be empty. `verifier/lib/base.py` is also called out as "Builders cannot edit this file" (line 10). Together these are the four frozen surfaces.

### 2a. `engine/app/anticipy/` (17 modules + `__init__.py`)

- `__init__.py`. package docstring only. The strict portability gate. `__all__ = []`.
- `platform_adapter.py` (526 lines). the ONLY module allowed environmental code. Implements `model_call` (OpenRouter DeepSeek V4 Flash, hard-pinned to `_PROVIDER_ROUTING = {"order":["deepseek"], "allow_fallbacks":True}`, line 126), `adversarial_model_call` (Kimi K2.6, line 371), `data_dir` (`~/.anticipy/system_v1`, line 70), `user_data_dir(user_id)` (line 84), `transcript_source` / `direct_command_source` injectors, `comms_send` / `comms_receive` (test bus), `action_engine_invoke` (the only path to the V4 action engine, set via `set_action_engine_impl`), `supabase_client(user_ctx)` / `service_role_client()`. `_DEFAULT_MODEL_BROKER_URL = "https://www.anticipy.ai/api/engine/model"` (line 99) so the engine can call the website model broker instead of needing a local OpenRouter key.
- `seams.py` (184 lines). typed dataclasses: `UserProfile`, `UserContext`, `InboundMessage`, `OutboundMessage`, `TranscriptLine`, `EngineDecision`. Literal types `Decision = "ACT" | "STORE_AS_LATENT" | "ASK" | "IGNORE"`, `InboundKind = "ambient" | "direct" | "reply"`, `Channel = "text" | "email" | "call"`.
- `spine.py` (173 lines). RLS-scoped SQLite at `data_dir() / "spine.sqlite3"`. `ScopedClient` is bound to one `user_id`; `CrossTenantError` raised on attempts to cross. `ServiceRoleClient` is separate. Used by `onboarding.py` to persist profiles.
- `memory.py` (345 lines). Mem0-style reconciliation primitive. `MemoryEntry` (mem_id, kind, key, value, evidence, ts, active). `kind ∈ {latent_intent, preference, aversion, contact, fact, anchor}`. Storage: `platform_adapter.user_data_dir(user_id) / "memory.jsonl"`. Functions: `seed`, `active_snapshot`, `add_latent`, `has_active_matching`, `delete_matching`, async `reconcile(user_id, candidate_kind, candidate_text)` (LLM-driven ADD/UPDATE/DELETE/NOOP), async `resolve_reference` (>= 0.70 confidence floor to resolve), `resolve_reference_sync`.
- `onboarding.py` (123 lines). `INTERVIEW_SCRIPT` constant + `run_intake(case_transcript, user_id) -> UserProfile` (line 83). Persists via `spine.scoped_client`. `profile_is_well_populated(prof)` at line 116.
- `addressee.py` (205 lines). `AddresseeResult` dataclass + async `resolve(transcript, wearer_label="WEARER")`. Classifies an utterance as `agent_direct | wearer_task_implied | boss_to_wearer | other_human | ambient`. Extracts the effective actionable text.
- `hedge.py` (208 lines). rewritten hedge filter, replaces old `engine/app/proactive/hedge_filter.py`. `Hedge` class with three-way trichotomy: `COMMIT | STORE_AS_LATENT | REFUSE`. `MemoryWriteSpec` carries the aversion-memory side effect.
- `proactive_engine.py` (426 lines). the head of the engine. `segment_units(transcript)`, `make_decide_fn(...)`, `decide(...)` orchestrates addressee → hedge → memory reconcile → autonomy threshold → final `EngineDecision`.
- `autonomy.py` (68 lines). progressive ACT threshold. `act_threshold(ctx)` returns 0.97 (cold start), 0.92 (onboarded), 0.85 (seasoned). `autonomy_state(ctx)` for reporting.
- `comms.py` (330 lines). Layer C. `classify_criticality` (text/email/call routing), `route_inbound`, `route_reply`, `apply_three_hour_rule`. Suspended-task matching by content + recency. Strict precision-skewed default (never call if unsure).
- `durable.py` (284 lines). event-sourced durable workflow runtime. SQLite-backed journal at `data_dir() / "durable.sqlite3"`. `register_workflow`, `start_workflow`, `deliver_event`. Deterministic replay; `ctx.journal_step`, `ctx.await_external`.
- `action_handoff.py` (262 lines). Layer B handoff. `contract_from_decision(decision)`, `handoff(...)`, `make_mock_action_engine`, `make_real_action_engine(cdp_port=9222, max_iters=12)`. This is what plugs `dsv4_skill_runner.DSv4SkillRunner` into `platform_adapter.set_action_engine_impl`.
- `compound.py` (173 lines). P9 whole-system compound workflow definition. End-to-end onboard → hedge → command → handoff → action → comms. Lives as a durable workflow.
- `trajectory.py` (133 lines). per-user JSONL decision log at `user_data_dir / "trajectory.jsonl"`. `log_decision`, `record_outcome`, `read_all`, `export_jsonl`. Best-effort, never blocks decisions.
- `grader.py` (275 lines). direction-aware adversarial grader. `grade_category`, `adversarial_check` (5% flag rate fails the build).
- `harness.py` (119 lines). generated-test harness. `run_category`, `run_suite`, `format_scoreboard`. Concurrency bounded for the 2 GB envelope.
- `taxonomy.py` (492 lines). fixed test taxonomy. `CategorySpec`, `accept_set`, `criterion_text`. Anti-gaming: counts and definitions hard-coded.

**Dependencies into frozen `anticipy/`**: `app.product.server` imports `app.anticipy.memory`, `app.anticipy.platform_adapter`, `app.anticipy.handoff` (referenced but file does NOT exist on disk. see `server.py:73` wraps the import in try/except). The acceptance harness checks for it implicitly. The frozen package depends on the non-frozen `app.proactive.demand_detection` via `proactive_engine.py` (line 22), which is a wart.

**Note on `handoff`**: `server.py:73` does `from app.anticipy.handoff import attach_to as _attach_handoff_routes`. No such file exists. Wrapped in `try/except: pass`, so the handoff routes are silently disabled in the shipping build. The handoff token round-trip therefore lives entirely on the website side (`src/lib/handoff-token-store.ts`, `src/lib/handoff-token.ts`, `src/app/api/engine/session/`).

### 2b. `engine/app/action_engine/` (7 modules)

- `__init__.py`. empty.
- `dsv4_skill_runner.py` (61 KB). the Ralph Loop. Structured task in, structured result out. Per-iteration: CDP screenshot → AX tree (40 lines max) → page text → V4 Flash completion check → V4 Flash decide action → humanlike CDP dispatch → settle → Kimi K2.6 vision verifier on before/after → log to `~/.anticipy/trajectories/<task_id>/`. Hard caps: 30 iters, no confirmation gates.
- `cdp_dispatcher.py` (12 KB). humanlike CDP dispatcher. Bezier mouse curves, Gaussian timing. Talks to `localhost:9222` (the LaunchAgent-managed real-clone Chrome). Coordinate cache keyed on per-skill landmark fingerprints. `RefusalSignal` for Fara-style safety refusals.
- `openrouter_client.py` (13 KB). thin OpenRouter wrapper. Vision support, primary→fallback routing, 429/5xx/timeout retries. Hard rule: `MIN_TOKENS = 256` floor; empty content with reasoning present → retry once at doubled budget. Constants `TEXT_MODEL = "deepseek/deepseek-v4-flash"`, `VISION_MODEL = "moonshotai/kimi-k2.6"`.
- `vision_verifier.py` (8 KB). Kimi K2.6 verifier. Fires on every state-changing action. `CERTIFIED | DIVERGED` plus one-sentence evidence + confidence. Mixed → DIVERGED conservatively.
- `humanlike.py` (4 KB). Bezier path + Gaussian-sampled inter-event delays. Deterministic with a fixed `numpy.random.Generator`.
- `gmail_compose.py` (6.5 KB). Gmail draft creation via CDP. `DraftRequest(to, subject, body)`, `DraftResult`. Used by the resolvable-people fast-path (`server.py:5351-5353` constructs the Gmail compose task string).
- `trajectory_logger.py` (6.8 KB). Supabase real-time logging. Tables `action_engine_tasks` and `action_engine_steps`. Migration `20260516_action_engine_trajectories.sql`. Silent no-op if Supabase creds absent.

**Consumers of frozen `action_engine/`**: `app.anticipy.action_handoff.make_real_action_engine` (line 228) imports `dsv4_skill_runner.DSv4SkillRunner` and wires it through `platform_adapter.set_action_engine_impl`. `server.py` does NOT import `dsv4_skill_runner` directly; it goes through the platform adapter seam.

### 2c. `engine/app/proactive_day/` (13 modules)

The "day-in-the-life" wrapper around the proactive engine. Layers A-I in `pipeline.py`.

- `__init__.py`. docstring describing the 7+ layers.
- `pipeline.py`. orchestrator. Imports `metrics`, `world`, all the layer files.
- `resolve.py`. Layer A. Resolves vague references against the wearer's life (recency + account match). Threshold-gated; below threshold → CONFIRM.
- `timing.py`. Layer B. Classifies a resolved action's time condition: now / deferred-to-condition / scheduled.
- `completion.py`. Layer C + D. Pre-execute satisfaction check (kill double-action) + ambient cancel (`never mind` retracts most-recent live queued action by same speaker).
- `comms.py`. Layer E + F. Channel routing (silent_queue | text | email | call | call2), debounce + compose batching, one-call-per-batch hard rate limit. Reuses frozen `comms.classify_criticality` read-only.
- `personalize.py`. Layer G. Wearer shorthand learning (the Thursday thing → resolved on second occurrence).
- `frontdoor.py`. Layer H. Clean onboarding + ProposalUI control surface (NOT the Tauri app).
- `loudroom.py`. Layer I. Adversarial corruption model + life-anchored single-token recovery for noisy ASR.
- `loudroom_v2.py`. MH-P12 frontier. Joint life-consistent beam recovery. Negative-enrollment inspired (arXiv 2502.16611).
- `metrics.py`. `ItemResult` dataclass. Outcome vocab: `ACTED | CONFIRMED | LIFE_LOG | DEFERRED | KILLED | CANCELLED`.
- `scenario.py`. fixed scripted-day generator. Anti-gaming `self_check` fails the build if the realized day is too easy.
- `world.py`. `SimWorld` simulated wearer life. Phone/SMS/call/email sink records but never sends.

**Dependencies**: `world.SimWorld` is the wiring point; the layers read and write through it. `comms.py` imports the frozen `app.anticipy.comms.classify_criticality`. Proactive day depends on frozen `anticipy/` but `anticipy/` does NOT import proactive_day.

### 2d. `verifier/` (5 modules)

- `__init__.py`. empty.
- `lib/__init__.py`. empty.
- `lib/base.py` (9 KB). `VerifierBase` class, `VerifierResult` dataclass, `vision_assert()`, `run_or_fail()`. Argparse + evidence dir + `result.json` writer. Each verifier script inherits.
- `lib/audio.py` (5.8 KB). BlackHole 2ch loopback capture for system audio. Tests the listening pipeline.
- `lib/engine.py` (7 KB). Engine helpers. `EngineHandle`, port discovery via `~/.anticipy/engine.port` (line 25) → fallback to 8731 (line 26). Launches `uvicorn engine.app.product.server:app` if no engine is running.
- `lib/mac_ui.py` (4.9 KB). `osascript` wrappers. `click_menu_bar_item`, `launch_app`, `quit_app`, `type_text`, `press_keystroke`.
- `personas/{david_pm,maya_founder,priya_solo}.json`. synthetic persona dossiers used by stranger-driver tests.
- `v6/trace_reader.py` (38 KB). V6-era trace inspector. Legacy.

---

## 3. Memory system

Multiple memory implementations coexist; they are NOT all live in the shipping engine.

### 3a. Frozen Mem0-style memory (the canonical product memory)

- **Location on disk**: `~/.anticipy/system_v1/users/<user_id>/memory.jsonl`
- **Code**: `engine/app/anticipy/memory.py`
- **Schema**: `MemoryEntry(mem_id, kind, key, value, evidence, ts, active)`. `kind ∈ {latent_intent, preference, aversion, contact, fact, anchor}`.
- **Primitive**: `reconcile(user_id, candidate_kind, candidate_text)` returns `ReconcileResult(op, mem_id, value, reason)` where `op ∈ {ADD, UPDATE, DELETE, NOOP}`.
- **Resolve**: `resolve_reference(user_id, reference_text, profile)` returns `ResolveResult(resolved, value, confidence, reason)` with 0.70 floor.
- **USER_ID**: `"anticipy-user"` (single-tenant), set in `server.py:110`.

### 3b. UserProfile / dossier (the onboarding-fed schema)

- **Code**: `engine/app/anticipy/seams.py:20` (UserProfile dataclass) and `engine/app/product/dossier_active_loader.py:139` (DossierLoader).
- **Disk paths (priority order, `dossier_active_loader.py:49-57`)**: `~/.anticipy/v7/dossiers/<account_id>/dossier.json`, `~/.anticipy/v7/dossier.json`, `~/.anticipy/dossier.json`. Env override `ANTICIPY_V7_DOSSIER_ROOT`.
- **UserProfile schema** (`seams.py:20-56`): `user_id, name, role_title, what_they_do, timezone, working_hours, people: dict[str, str], critical_software: dict[str, bool], connected_accounts: dict[str, dict], mandate, do_not_touch: list[str], autonomy_level, days_since_onboard, trajectory_confidence, comms_prefs, quiet_hours, voice_anchor`.
- **Active dossier Person schema** (`dossier_active_loader.py:60-86`): `name, role, email, pronouns, aliases: list[str], last_mentioned: float, tags: list[str]`. `gender_hint()` from pronouns.
- **DoNotTouchRule** (`dossier_active_loader.py:89-109`): `pattern, reason, surfaces: list[str]`.
- **Onboarding profile file** (separate path used by the product backend): `~/.anticipy/system_v1/product_profile.json`. Referenced by acceptance check 18 (line 961). Loaded into `_SESS["profile_obj"]` (`server.py:108-109`). Contains the same UserProfile JSON shape plus a `people: dict[name -> "Full Name <email>"]` dict-of-strings form.

### 3c. V7 scoped memory (account/device scoped, the canonical write surface)

- **Code**: `engine/app/product/scoped_memory.py:106` (`ScopedMemory` class).
- **Disk path** (`scoped_memory.py:43-47`): `~/.anticipy/v7/memory/<account_id>/<device_id>/memory.jsonl`. Env override `ANTICIPY_V7_MEMORY_ROOT`.
- **Schema**: `MemoryItem(item_id, account_id, device_id, kind, key, value, source, provenance, timestamp, confidence, active, extra: dict)`. Kinds: `person, preference, alias, do_not_touch, recipe, action_outcome, fact, latent_intent`.
- **Why this exists**: the frozen `app.anticipy.memory` is single-tenant (USER_ID = "anticipy-user"). ScopedMemory is the account/device-aware wrapper required for multi-device sync.

### 3d. Recents (audio transcripts ring buffer)

- **Code**: `engine/app/product/server.py:2537` (`_recent_transcripts(limit=8)`). In-memory list `_SESS["transcript"]` (`server.py:108`).
- **Not persisted across restarts**. Stored as plain `list[str]`. Drained by the planner at compose time (`server.py:5494`).

### 3e. Person resolver

- **Two implementations**, both live:
  - `engine/app/product/person_resolver.py:102` (`PersonResolver` class). Reads from `ScopedMemory` (account/device scoped). Reasons over `KIND_PERSON` and `KIND_ALIAS` items.
  - `engine/app/product/server.py:3551` (`_resolve_person_from_active_dossier`). Reads from `DossierLoader` (the onboarding dossier path).
- **The fast-path** at `server.py:5276` (`_fastpath_plan_from_memory`) and `server.py:5399` (`_fastpath_pronoun_resolve`) does its own deterministic person-matching against the onboarding profile WITHOUT calling either resolver. This is the actual code path used by CHECK 16.
- **Pronoun handling**: `_PRONOUN_GENDER` map duplicated in both `dossier_active_loader.py:26-30`, `scoped_memory.py:36-40`, and `person_resolver.py:15-18`. Three copies.
- **Nicknames**: `person_resolver.py:19-28` has a ~25-entry dictionary (Mike→Michael etc). The fast-path in server.py does NOT use this; it uses only first-name token match.

### 3f. Cloud sync

- **Code**: `engine/app/product/memory_cloud_sync.py`. Outbox at `~/.anticipy/v7/memory_outbox.jsonl` + ack at `~/.anticipy/v7/memory_outbox.ack.jsonl`. Background worker POSTs to Supabase PostgREST.
- **Kind → table map** (`memory_cloud_sync.py:36-44`): `preference → anticipy_preferences`, `profile / user_profile → anticipy_user_profile`, `dossier → dossiers`, default `anticipy_memory`.
- **Trigger**: silent no-op if `SUPABASE_URL` unset. `_MAX_RETRIES = 5`, exponential backoff. Quarantine on poisoned rows.

### 3g. Memory provenance (audit trail)

- **Code**: `engine/app/product/memory_provenance.py`. Tracks where each memory item came from (utterance hash, source mode, model used).

### 3h. memory_v2 (unused)

- `engine/app/memory_v2/draw.py`, `memory_v2/write.py`. Experimental. Not imported by the product server. Dead.

---

## 4. Browser bridge and CDP

Two distinct CDP paths exist. **The Z-001 / acceptance flow uses the V4 skill runner path, NOT the bridge.**

### 4a. The V4 skill runner CDP path (CANONICAL for browser actions)

- `engine/app/action_engine/cdp_dispatcher.py`. direct CDP via websockets to `http://localhost:9222`. Bezier motion. Used by `dsv4_skill_runner.py`. Wired through `app.anticipy.action_handoff.make_real_action_engine(cdp_port=9222)` → `platform_adapter.action_engine_invoke`. **This is what Gmail draft actions in CHECK 08-10 actually use.**
- Chrome is started by `~/Library/LaunchAgents/com.anticipy.chrome.plist` with `--remote-debugging-port=9222 --user-data-dir=/Users/omarebrahim/.anticipy/chrome-real-clone`. KeepAlive on crash.

### 4b. The loopback HTTP bridge (legacy surface runtime path)

- `scripts/v7/anticipy_bridge_fallback_cdp.py` (47 KB). CDP-first loopback bridge on `127.0.0.1:7777` exposing `/status`, `/surface-proof`, `/surface-command`. Probes `http://localhost:9222/json/version` on startup; falls back to AppleScript if 9222 is down. Used by:
  - `engine/app/product/surface_runtime.py` (`BRIDGE_PORT = 7777`, line 22)
  - `engine/app/product/universal_surface_runtime.py` (line 29)
  - `engine/app/product/surface_dom_extractor.py` (line 33)
  - `engine/app/product/surface_runtime_vision.py`
- The bridge is what Z-001 itself uses (`scripts/v7/z001_e2e_harness.py:50`: `BRIDGE = "http://127.0.0.1:7777"`). The Z-001 harness opens tabs and asserts tab leakage = 0 via the bridge, then drives the engine to inject + act.
- `engine/app/bridge.py`, `engine/app/bridge_extension.py`, `engine/app/ws_bridge.py`. older WebSocket bridge variants from the Browser Use era. Not used by the v-final product. Tests still reference (`test_bridge.py`, `test_bridge_extension.py`).

### 4c. Browser action recipe glue

- `engine/app/product/action_recipes.py` (12 KB). recipe definitions for specific surfaces.
- `engine/app/product/action_dispatcher.py` (10 KB). generic dispatcher; lazy-imports `action_planner.ActionPlanner` and calls primitives.
- `engine/app/product/action_planner.py` (11 KB). OpenRouter-driven planner that picks the next primitive given intent + live surface state. Cascade: `deepseek-v4-flash → kimi-k2.6 → gemini-3.5-flash`. Vision swap for canvas apps.
- `engine/app/product/action_engine_api.py` + `action_engine_api_wire.py`. wire actions into the FastAPI router.
- `engine/app/product/action_binder.py` (15 KB) + `action_binder_endpoints.py`. bind Intent → Binding the dispatcher executes. No-decline contract: missing slot → `ask_user` primitive.
- `engine/app/browser.py`. legacy Patchright browser manager. NOT used by the shipping path; kept for old test coverage. CLAUDE.md flags this explicitly: "legacy browser manager (kept for reference)".

**Which is the real current path**:
- Real browser **actions** (Gmail compose, calendar, etc) → V4 skill runner via `dsv4_skill_runner.py` over its own CDP at 9222.
- Real surface **probes / Z-001 harness / DOM extraction** → loopback bridge at 7777 forwarding to the same Chrome at 9222.
- Everything in `engine/app/browser.py`, `engine/app/bridge.py`, `engine/app/ws_bridge.py` is legacy from the Browser Use era.

---

## 5. Planner, intent extractor, action binder

The live planner call graph from a captured utterance is **`/api/listen/upload` or `/api/listen/inject` → window flush → memory write → fast-path → `_compose_task_from_memory` → optional `_finalize_plan` → `/api/act`**.

### 5a. The hot path inside `server.py`

1. **`/api/listen/upload`** (`server.py:4888`) or **`/api/listen/inject`** (`server.py:4564`). entry from ambient mic, MP3 upload, or paste. Pushes window text into `_SESS["transcript"]`.
2. **`_memory_draw(event_text)`** (`server.py:1366`). frozen pipeline hook. Reconciles the new window into Mem0 memory.
3. **`_recent_transcripts(limit=12)`** (`server.py:2537`). pulls the last N windows from `_SESS["transcript"]`.
4. **`_profile_json()`** (`server.py:369`). reads `~/.anticipy/system_v1/product_profile.json` or `_SESS["profile_obj"]`.
5. **`_fastpath_plan_from_memory(instruction, profile_obj)`** (`server.py:5276`). deterministic single-dossier-person match. If exactly one person's first-name OR alias appears in the utterance, emit `{mode: "act", person, thing, intent: "email_draft", task: "Open Gmail and create a draft...", _fastpath: true}`. Returns `None` if 0 or 2+ matches; the LLM path runs.
6. **`_fastpath_pronoun_resolve(instruction, profile_obj, recent_list)`** (`server.py:5399`). pronoun-only triggers ("send her the schedule"). If exactly one dossier person whose pronouns match was named in the last 3 recent windows, build act plan deterministically.
7. **`_compose_task_from_memory(instruction)`** (`server.py:5479`). main path. Calls `platform_adapter.model_call(_COMPOSE_SYS, user, 600, 0.0, True)` (which routes to OpenRouter DeepSeek V4 Flash via the website broker). 60-second cache keyed on `(text_hash, profile_hash, recent_hash)`. Up to 2 attempts with 1s backoff. On infra failure → `mode: "clarify"` with `_infra_fallback: true` flag.
8. **`_finalize_plan(instruction, plan)`**. runs dossier-resolution heuristics on the parsed plan to fill missing person/email even if the LLM left them blank.
9. **`/api/act`** (`server.py:6659`). takes the pending plan, runs it. For irreversible intents (`send_email`, `send_slack_message`, `send_text_message`, `pay`, `book_restaurant`, `book_appointment`, `cancel_subscription`. list at `engine/app/anticipy/irreversible_intents.json`, file path referenced at `server.py:5623-5625` though the file doesn't ship), pauses → emits `confirm_required` with `task_id` and 30s timer.
10. **`/api/act/confirm/<task_id>`** (`server.py:6782`). Approve / Reject. Default-to-reject expiry at `_expire_confirm`. Approve resumes the frozen action engine via `platform_adapter.action_engine_invoke`.

### 5b. V7 unified intent extractor (separate path, NOT in the hot path above)

- `engine/app/product/intent_extractor.py` (15 KB). `Intent` dataclass: `intent_id, summary, type ∈ {act, ask, remind, research, create, modify, delete, answer, ignore}, target_surface, target_person_refs, evidence_quotes, required_slots, missing_slots, risk_level ∈ {low, medium, high}, confidence, actionable_probability, is_third_party_want, is_hypothetical, model, error`.
- Cascade `deepseek-v4-flash → kimi-k2.6 → gemini-2.5-flash`.
- Wired into the FastAPI router at `server.py:7729` via `intent_extractor_endpoints`.
- **Not used by the listen/act path**; this is a separate REST surface (probably an extension or earlier UI). The CHECK suite does not exercise it.

### 5c. ActionPlanner

- `engine/app/product/action_planner.py:1`. picks next primitive given intent + live surface state. Cascade same as intent extractor. Vision fallback for canvas apps. Output `{primitive, args, why}`.
- Called by `engine/app/product/action_dispatcher.py:25`, which is invoked from action binder endpoints.

### 5d. Context attacher and risk assessor

- `engine/app/product/context_attacher.py` (13 KB). attaches recent context to an Intent.
- `engine/app/product/risk_assessor.py` (10 KB). answers `confirm_required` for the binder.
- `engine/app/product/login_wall_responder.py` (9 KB). detects login walls and notifies (`/api/action/login_wall_notify` at server.py:2032).

**Emission shape**: the canonical plan dict at the end of `_compose_task_from_memory` is `{mode: "act"|"clarify", person, thing, intent, task, question, _fastpath?, _infra_fallback?}`. The `task` field is the natural-language instruction handed to `DSv4SkillRunner` via `action_handoff`.

---

## 6. Onboarding

Three onboarding modalities, all converge to `~/.anticipy/system_v1/product_profile.json` and seed the frozen memory anchors.

### 6a. In-app conversational onboarding (the production path)

- **Engine**:
  - `engine/app/anticipy/onboarding.py`. `INTERVIEW_SCRIPT` + `run_intake(case_transcript, user_id) -> UserProfile`. Uses `spine.scoped_client` to persist.
  - `engine/app/product/server.py:1542` (`/api/onboarding/start`), `:1561` (`/api/onboarding/answer`), `:1763` (`/api/onboarding/chat_complete`).
- **Website chat UI**: `src/app/onboarding/chat/page.tsx`. Posts to local `http://127.0.0.1:8731` via `/api/onboarding/chat_complete`. Conversation state lives in the browser; broker LLM calls go through `/api/engine/model`. END_OF_INTAKE token signals dossier persistence. MIN 15, MAX 25 exchanges.
- **Acceptance**: CHECK 05 (`engine/tests/anticipy_acceptance.py:246`) seeds 8 turns and asserts ≥2 people-with-email + ≥1 do-not-touch.

### 6b. MP3 / audio onboarding

- **Engine**: `server.py:1920` (`/api/onboarding/from_audio`). Accepts audio body, ASRs via parakeet_mlx, then routes through `run_intake`.
- **Website UI**: `src/app/onboarding/audio/page.tsx`.
- **Acceptance**: CHECK 06 (`anticipy_acceptance.py:349`) generates a 30+ min `say`-voiced MP3, posts to `/api/onboarding/from_audio`, asserts ≥2 people extracted.

### 6c. Twilio voice onboarding (B-001)

- **Script**: `scripts/v7/twilio_onboarding_call.py` (30 KB). Three modes: `REAL_TWILIO_CALL`, `MOCK_TWILIO`, `LOCAL_FALLBACK` (macOS `say` through speakers). Friend-style interview (~10 minutes). Output: populated dossier.
- **Engine stub endpoints**: `server.py:1636` (`/api/onboarding/call_stub`), `:1716` (`/api/onboarding/call_stubs`).
- **Website route**: `src/app/api/engine/twilio/voice-callback/route.ts`. handles user response via DTMF/SpeechResult. Verifies Twilio signature. Reaches `src/lib/execute-action.ts`.
- **Acceptance**: CHECK 07 (`anticipy_acceptance.py:380`) verifies the call-stub log path exists.
- **Sister page**: `src/app/onboarding/call/page.tsx`.

### 6d. Popover welcome screen

- `desktop/src/popover.html` + `desktop/src/main.js` + `desktop/src/styles.css`. Tauri popover. Brand: charcoal `#0C0C0C`, cream `#F5F0EB`, gold `#C8A97E`. Includes TCC permissions explainer (mic/screen/automation pre-prompts) per recent commit `fcde9857`.
- `desktop/scripts/run-popover-e2e.mjs`. Playwright E2E for the popover.
- The Tauri layer at `desktop/src-tauri/src/lib.rs` + `main.rs` is the native shell. Cargo manifest at `desktop/src-tauri/Cargo.toml`.

### 6e. Web onboarding gate

- `src/app/api/engine-transfer-gate/route.ts`. passcode-gated transfer of profile/dossier from one device to another. Constant-time compare, 10 attempts/min/IP brute-force defense. Gate cookie at `src/lib/engine-transfer-gate.ts`.

---

## 7. Surface adapters

The places where Anticipy actually drives a specific app.

### 7a. Gmail

- `engine/app/action_engine/gmail_compose.py`. opens Gmail compose URL via CDP, fills `to/subject/body`, leaves as draft. `DraftRequest`, `DraftResult`. This is what the resolvable-people fast-path generates a `task` string for; the V4 skill runner then walks the DOM to fill the fields.
- `_gmail_compose_screenshot()` in `anticipy_acceptance.py` verifies the draft visually after CHECK 08-10.

### 7b. Native macOS surface

- `engine/app/product/native_action_macos.py` (20 KB). `osascript` + `cliclick` wrappers for Reminders, Notes, Messages, Calendar. Screenshots at `~/.anticipy/screenshots/native`. First-run triggers Automation consent.
- `engine/app/product/native_action_endpoints.py` + `native_action_wire.py`. FastAPI routes that wire native_action_macos into the server.
- `verifier/lib/mac_ui.py`. verifier-side osascript helpers (separate from production code).

### 7c. Generic surface runtime (Chrome/web)

- `engine/app/product/surface_runtime.py` (25 KB). generic primitives over the 7777 bridge. Click, type, navigate, screenshot, eval JS.
- `engine/app/product/universal_surface_runtime.py` (21 KB). newer unified API.
- `engine/app/product/surface_runtime_vision.py` (16 KB). vision-augmented primitives for canvas apps.
- `engine/app/product/surface_dom_extractor.py` (15 KB). DOM extraction over 7777.
- `engine/app/surface_runtime/{perception.py, proof.py, recipes.py, types.py}`. newer modular pieces.

### 7d. Browser action recipes (per-domain)

- `engine/app/product/action_recipes.py`. `action_binder.py` table at lines 24-32: `gmail, mail.google → "gmail"`, `calendar.google → "google_calendar"`, `docs.google → "google_docs"`, `sheets.google → "google_sheets"`, `drive.google → "google_drive"`, `opentable, doordash, ubereats, amazon, notion, linear.app, slack.com, zoom.us`. Native list (lines 33-38): `reminder → native_macos_reminders`, etc.

---

## 8. Acceptance tests

### 8a. `engine/tests/anticipy_acceptance.py` (CHECK 01-18, 47 KB)

Definition of done: 18/18 PASS. CHECKs:

| # | Function (line) | Validates |
|---|---|---|
| 01 | `check_01_site_live:137` | `GET https://www.anticipy.ai/api/app/state` returns `engine.status != gated` AND `mic.status != needs_user`. |
| 02 | `check_02_dmg_downloadable:151` | `curl -L` of `/download` ends at HTTP 200 with `x-apple-diskimage` or `octet-stream` content-type. |
| 03 | `check_03_install_path_terminal_only:162` | `install.sh` does NOT contain `open "/Applications/Anticipy.app"` (user opens it themselves). |
| 04 | `check_04_app_runs:174` | Local engine at 8731 responds `/health` and `/api/state` with `key_ok: true` within 30s. |
| 05 | `check_05_onboarding_chat:246` | Seed 8-turn intake via `/api/onboarding/chat_complete`; asserts ≥2 people-with-email AND ≥1 do-not-touch in profile. |
| 06 | `check_06_onboarding_audio:349` | Generate 30+ min `say` MP3, post to `/api/onboarding/from_audio`; assert ≥2 people extracted, transcript > 200 chars. |
| 07 | `check_07_onboarding_call_stub:380` | `/api/onboarding/call_stub` writes a row marked `is_stub=true` to the call log. |
| 08 | `check_08_input_paste:555` | Paste 2 inject lines naming Dana; pending plan must be `mode=act`; `/api/act` runs to SUCCESS; Gmail compose screenshot saves. |
| 09 | `check_09_input_mp3:587` | Upload `mp3_priya_strategy.mp3` to `/api/listen/upload`; resolves person=Priya; act SUCCESS; screenshot saves. |
| 10 | `check_10_input_mic:619` | `say` → BlackHole or speaker → mic → always-on listener; resolves and acts. 3 replay retries over 180s. |
| 11 | `check_11_audio_devices:755` | `/api/audio/devices` returns ≥1 builtin device. |
| 12 | `check_12_ambiguity_trap:769` | Inject 2 contender names, pronoun trigger; expect `mode=clarify` AND question naming both contenders AND Gmail drafts count unchanged. |
| 13 | `check_13_flash_page_live:798` | `/flash` HTML contains "Connect Pendant" button, `navigator.bluetooth`, `web-bluetooth-dfu`. |
| 14 | `check_14_flash_stub_log:820` | POST to `/api/flash/log` appends row with `is_stub=true`. |
| 15 | `check_15_brand_audit:855` | Playwright audit: background `rgb(12,12,12)`, color `rgb(245,240,235)`, no emoji in headings, no forbidden strings (`key_ok`, `8731`, `127.0.0.1`) leaked. Pages: `/`, `/app`, `/flash`, `/onboarding/chat`, `/onboarding/audio`. |
| 16 | `check_16_agent_reliability:913` | Subprocess `engine/tests/agent_reliability.py --no-act`; pass if resolvable ≥19/20 AND ambiguous = 10/10. |
| 17 | `check_17_frozen_paths_clean:946` | `git diff --name-only -- engine/app/action_engine engine/app/proactive_day engine/app/anticipy` MUST be empty. |
| 18 | `check_18_cleanup_passes:959` | Wipe profile, hard-kill engine on 8731 (SIGTERM then SIGKILL), relaunch from source, assert `onboarded=false`. Restores profile after. |

### 8b. `engine/tests/agent_reliability.py` (CHECK 16's child)

30 scenarios: 20 resolvable + 10 ambiguous. Required profile: Dana Bright, Priya Shah, Maya Chen (with `omarkebrahim+anticipy-*@gmail.com` test addresses). Pass = resolvable ≥18/20 AND ambiguous = 10/10 (or 19/20 for CHECK 16's stricter parse).

### 8c. `scripts/v7/z001_e2e_harness.py` (47 KB)

End-to-end harness per ANTICIPY_V2_PRD. ONE brand-new user signs up at `anticipy.ai/app`, captures deep-link handoff token, drives the already-installed engine to inject a sample utterance, confirms a real Gmail draft lands in `mail.google.com/drafts`. Uses BACKGROUND tabs only via the 7777 bridge. Asserts tab leakage = 0 by listing `/json` before/after. Exit 0 PASS / 1 FAIL. Assumes the engine is installed and running on 8731 (cleaner install path is V7.18's job).

### 8d. Other test files

- `engine/tests/test_phase10_acceptance.py`, `test_phase7_scenarios.py`, `test_phase9_watchdog.py`. phase-level integration tests.
- `engine/tests/test_proactive_pipeline.py`, `test_full_pipeline_e2e.py`, `test_middle_layer.py`. proactive_day pipeline tests.
- `engine/tests/test_cdp_dispatcher.py`, `test_dsv4_skill_runner.py`, `test_vision_verifier.py`, `test_openrouter_client.py`. action engine unit tests.
- `engine/tests/test_cascade_holdout.py`. cascade benchmark.
- `engine/tests/test_product_*.py`. product-server tests (asr normalization, mp3 intent guards, onboarding dossier fields, scheduler, surface runtime primitives, upload asr bounds, v7 inference artifacts).
- `engine/tests/audiostack/`, `dayinlife/`, `e2e/`, `integration/`, `fixtures/`, `anticipy/`. subdirectories with subsystem tests.
- `engine/test_*.py`. older test files at the engine root (test_real.py, test_extension_runner.py, test_master_benchmark.py, etc). These are the Browser Use era tests. Mostly still pass when run against the legacy `engine/app/main.py` server.

---

## 9. Web side

### 9a. App router pages (`src/app/`)

- `page.tsx`. marketing home.
- `app/page.tsx`. install/download landing.
- `download/route.ts`. 302 redirects to `/dl/Anticipy_1.0.0_aarch64.dmg`; HEAD returns DMG headers directly (so CHECK 02's `curl --head` sees the right content-type).
- `dl/Anticipy_1.0.0_aarch64.dmg`. the shipped DMG (2.5 GB). Served by Next.js static.
- `flash/page.tsx`. pendant flashing page; uses `navigator.bluetooth` + `web-bluetooth-dfu`.
- `onboarding/chat/page.tsx`, `onboarding/audio/page.tsx`, `onboarding/call/page.tsx`. three onboarding paths.
- `engine/page.tsx`. engine chat interface (legacy Browser Use UI, gated `access code: 123`).
- `engine-transfer/page.tsx`. passcode-gated cross-device transfer UI.
- `analytics/page.tsx`. password-gated dashboard.
- `admin/`, `waitlist/`, `pre-orders/`, `funded/`, `compare/`, `crm/`, `demo/`, `for/`, `guide/`, `internal/`, `privacy/`, `refund/`, `terms/`, `vs/`. marketing and admin pages.
- `ambient-intent/page.tsx`. recent product narrative page.

### 9b. API routes (`src/app/api/`)

- `api/app/state/route.ts`. single source of truth state JSON. Returns segment statuses (`ready | needs_user | gated | live`). The thin client renders it and posts intent back. NEVER fabricates a successful gated edge.
- `api/app/run/route.ts`. run requests.
- `api/engine/model/route.ts`. the **model broker**. POST proxies to OpenRouter with `Authorization: Bearer <server-side key>`. Allowed models: `deepseek/deepseek-v4-flash`, `deepseek/deepseek-v4-pro`, `moonshotai/kimi-k2.6`. Per-user rate-limited via `clientIp + rateLimit`. Requires Supabase user. This is what `platform_adapter.model_call` reaches when no local `OPENROUTER_API_KEY` is set (the `_DEFAULT_MODEL_BROKER_URL` constant).
- `api/engine/session/`, `api/engine/confirm/`, `api/engine/auto-proceed/`, `api/engine/trajectory/`, `api/engine/analyze/`, `api/engine/transcribe/`, `api/engine/deepgram-key/`. engine helper routes. Several are gated to "no providers" per the forbidden-provider policy (Deepgram returns 503; CLAUDE.md flags this).
- `api/engine/twilio/voice-callback/` + `voice-script/` (only `voice-callback` exists on disk) + `sms-reply/`. Twilio webhooks. Signature verification via `src/lib/twilio-verify.ts`.
- `api/engine-transfer-gate/route.ts`. passcode gate. Constant-time compare. 10 attempts/min/IP.
- `api/dossiers/upsert/`. write dossier from the website side.
- `api/auth/`, `api/admin/`, `api/agent/`, `api/analytics/`, `api/crm/`, `api/cron/`, `api/extension/`, `api/flash/`, `api/health/`, `api/internal-gate/`, `api/log/`, `api/pre-orders/`, `api/release-meta/`, `api/resolution-traces/`, `api/test-meta-monitor/`, `api/waitlist/`, `api/webhooks/`. supporting routes.

### 9c. Web lib (`src/lib/`)

- `handoff-token.ts`, `handoff-token-store.ts`. deep-link handoff token mint + exchange (used by `/api/engine/session/` + the engine).
- `engine-transfer-gate.ts`, `gate-cookie.ts`. gate cookie signing.
- `release-meta.ts`. releaseable build metadata.
- `supabase-admin.ts`, `require-auth.ts`. Supabase server-side helpers.
- `rate-limit.ts`. IP rate limiter (used by model broker + gate).
- `agent-llm.ts`, `cerebras.ts`, `gemini.ts`, `groq.ts`, `llm-cascade.ts`, `mistral.ts`. LLM provider wrappers.
- `execute-action.ts`, `intent-extract.ts`, `intent-gates.ts`, `intent-prompt.ts`. engine-style intent + action helpers (used by Twilio webhook).
- `memory-extract.ts`, `memory-recall.ts`, `preference-record.ts`, `preference-recall.ts`, `episode-recall.ts`. server-side memory helpers (used by older flows).

---

## 10. Abandoned / legacy code

CLAUDE.md flags some legacy paths explicitly (`engine/app/browser.py`, `engine/app/harness.py`, `engine/app/models.py` all "legacy kept for reference"). The full deprecated set:

### 10a. Browser Use era (the original engine architecture)

- `engine/app/main.py` (57 KB). original FastAPI server. Browser Use + Patchright. Has WebSocket task execution, rate limiting, bcrypt auth, admin stats. NOT used by the v-final product.
- `engine/app/agent.py` (67 KB). Browser Use integration wrapper. Comment line 3 explicitly: "Uses Browser Use framework for browser automation."
- `engine/app/browser.py`. Patchright browser manager.
- `engine/app/harness.py`. observation compression + prompt formatting. "The core IP. makes cheap models work well." Legacy.
- `engine/app/models.py` (31 KB). multi-provider LLM cascade with httpx. Legacy; the modern engine uses `platform_adapter.model_call` + `action_engine/openrouter_client.py`.
- `engine/app/orchestrator.py` (47 KB). old multi-step orchestrator. Dead.
- `engine/app/safety.py`, `engine/app/router.py`, `engine/app/planner.py` (16 KB). Browser Use era safety / routing / planning.
- `engine/app/captcha.py`, `engine/app/clarify.py`, `engine/app/critic.py`, `engine/app/embeddings.py`, `engine/app/end_state_verifier.py`, `engine/app/reflector.py`, `engine/app/code_sandbox.py`, `engine/app/llm_judge.py`, `engine/app/verifier.py`, `engine/app/vision.py`, `engine/app/trajectory_cache.py`, `engine/app/dynamic_budget.py`, `engine/app/cost_watch.py`. Browser Use era helpers. Dead, but their tests at `engine/test_*.py` still exist.
- `engine/app/ws_bridge.py`, `engine/app/bridge.py`, `engine/app/bridge_extension.py`. old WS bridges. Dead.
- `engine/app/server.py` (61 lines). old phase-2 `/journey/run` server. Dead.
- `engine/app/desktop_app.py`. older Tkinter desktop entry. Superseded by `app/product/main.py`.
- `engine/app/proactive_routes.py`. older proactive routes. The replacement is `proactive_day/` (frozen).
- `engine/app/proactive/`. older proactive engine. Still partially live: `proactive_engine.py` imports `app.proactive.demand_detection.DemandDetector` (a frozen → non-frozen dependency wart). Most of `proactive/` (donna.py, donna_voice.py, notifier.py, notes.py, dispatcher.py, etc.) is unused.
- `engine/app/memory.py` (25 KB). older memory implementation. Superseded by `app/anticipy/memory.py` + `app/product/scoped_memory.py`.
- `engine/app/memory_v2/`. never-shipped experiment.

### 10b. Old extensions and executor

- `_archive/legacy_extension_v1`, `_archive/legacy_extension_v2`, `_archive/legacy_extension_v3`. three older Chrome extension generations. Archived.
- `extension_v4/`. fourth-gen extension. The README in the archive points at it. Not part of the shipping Mac app.
- `executor/`. Node/Electron-based agent executor (an Electron experiment with `main.js`, `preload.js`, `renderer/`, `skills/`). Not used.
- `firmware/`. pendant firmware (out of scope per HANDOFF.md).

### 10c. Old scripts

- `scripts/v6/*`. V6-era dispatchers and probes. Some are still actively run by LaunchAgents (see section 11). The `dispatch_*` scripts and `mp3_*` probes are V6 stranger-driver tooling.
- `scripts/v7/probe_*`, `evaluate_stranger_*`, `generate_stranger_openrouter.py`, `parallel_stranger_workers.sh`, `run_batch_strangers.sh`. stranger-driver synthesis pipeline.
- `archive/2026-05-pre-overhaul/`, `archive/ax_skill_runner.py.bak`, `archive/fara_skill_runner.py.bak`. explicit backups from the pre-V4 overhaul. The skill runner went AX → Fara → DSv4; only DSv4 is live.

### 10d. Mixed status

- `engine/app/coldstart/`, `engine/app/middle/`, `engine/app/safetyx/`, `engine/app/costctl/`, `engine/app/observ/`, `engine/app/offline/`, `engine/app/recovery/`, `engine/app/authsec/`, `engine/app/audiostack/`, `engine/app/surface_runtime/`. newer modular packages. Mostly imported via `app.product.server` lazy try/except (so if missing, the route silently skips). Some are partially wired; some are wired but the code paths aren't exercised in CHECK 01-18.

---

## 11. Cron, launchd, supervisors

### 11a. Active LaunchAgents (`~/Library/LaunchAgents/com.anticipy.*.plist`)

- **`com.anticipy.chrome.plist`**. starts Chrome with `--remote-debugging-port=9222 --remote-allow-origins=http://localhost:* --user-data-dir=/Users/omarebrahim/.anticipy/chrome-real-clone --profile-directory=Default --no-first-run --no-default-browser-check --restore-last-session --disable-features=Translate`. `KeepAlive` on `Crashed=true, SuccessfulExit=false`. **This is the load-bearing Chrome agent that the entire CDP path depends on.**
- **`com.anticipy.claude-remote-control.plist`**. runs `claude remote-control --name Anticipy-MacBook --permission-mode bypassPermissions --spawn same-dir` from `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL`. Per user MEMORY.md "Harness defaults": this is the launchd daemon Omar explicitly consented to. Bypass permissions + max effort.
- **`com.anticipy.human-ready-loop.plist`**. runs `/Users/omarebrahim/Developer/Anticipy-V7/tools/anticipy_human_ready_loop.sh`. Plan-fix-test loop: verify → if regression revert → claude --print to replan → claude --print to fix → loop. Bounded by 8h wall clock, $10 OpenRouter, max 30 iterations. Logs to `state/v7/human_ready/`.
- **`com.anticipy.finish-overnight.plist`**. runs `/Users/omarebrahim/Developer/Anticipy-V7/tools/finish_overnight.sh`. ONE goal: get Z-001 to 9/9 against the live packaged engine. Each iteration: check for fresh DMG, install if new, restart engine on 8731 + CDP 9222, run `z001_e2e_harness.py`, score steps. 9/9 PASS → write `tasks/DONE.morning` and exit. Hard-stops after 8 hours.
- **`com.anticipy.content.broll.plist`**, **`com.anticipy.content.nudge.plist`**, **`com.anticipy.content.script.plist`**, **`com.anticipy.content.watcher.plist`**. these point at `/Users/omarebrahim/Anticipy-Content/` (a separate repo, NOT under Anticipy-V7). Content-generation pipeline (b-roll, scripts, watcher). Should be killed if those scripts no longer matter; otherwise leave alone. they don't touch the engine.

### 11b. Disabled LaunchAgents

- `ai.anticipy.watchdog.plist.disabled-by-claude-20260519-171413`. old watchdog, disabled.
- `ai.openclaw.gateway.plist.disabled`, `ai.openclaw.noor-bridge.plist.disabled`, `ai.openclaw.noor-chrome.plist.disabled`, `ai.openclaw.noor-imessage.plist.disabled`. openclaw experiment, killed.

### 11c. tools/ supervisors (the supervisor scripts the agents run)

- `tools/anticipy_human_ready_loop.sh`. see above.
- `tools/finish_overnight.sh`. see above.
- `tools/anticipy_supervisor.sh`. general supervisor.
- `tools/loops_status.sh`. status board for ralph_v7. PID, last cycle, gate counts, completion / stuck file pointers. Reads `state/v7/loop.pid`, `state/v7/loop_cycle.txt`, `state/check_done_v7.json`.
- `tools/ralph_v7.sh`, `tools/ralph_trillion.sh`. Ralph loop variants.
- `tools/finish_loop_prompt.md`. the prompt body the loops feed to `claude --print`.
- `tools/upload_dmg_to_r2.py`. uploads the built DMG to Cloudflare R2.

### 11d. scripts/v6/ dispatchers (active in V6, mostly stale in V7)

- `dispatch_planner.sh`, `dispatch_judge.sh`, `dispatch_worker.sh`, `dispatch_evaluator.sh`, `dispatch_stranger_driver.sh`, `dispatch_stranger_generator.sh`, `dispatch_common.sh`. V6 cascade dispatch. The current proof pipeline does NOT use these.
- `chrome_watchdog.sh`, `disk_hygiene.sh`, `state_hygiene.sh`, `provision_build_env.sh`, `refresh_local_engine_from_public.sh`, `ship_if_bundled.sh`. housekeeping scripts. Used ad-hoc.
- `probe_*` scripts. synthesis / scoring probes. V6-era.

### 11e. What should be killed

- The `ai.openclaw.*.disabled` plists are already disabled; safe to delete.
- The `ai.anticipy.watchdog.plist.disabled-by-claude-*` can be deleted.
- The 4 `com.anticipy.content.*.plist` agents are pointed at a separate `Anticipy-Content/` repo; verify that repo is still active before killing.
- `engine/app/main.py`, `engine/app/agent.py`, `engine/app/browser.py`, `engine/app/harness.py`, `engine/app/models.py`, `engine/app/orchestrator.py`, `engine/app/server.py`, the `ws_bridge.py / bridge.py / bridge_extension.py` triple, most of `engine/app/proactive/` (except `demand_detection.py` which the frozen `proactive_engine.py` still imports), `engine/app/memory.py`, `engine/app/memory_v2/`, `engine/app/desktop_app.py`, and the older test files at `engine/test_*.py` could all be moved to an `_archive/` directory without breaking the shipping path. The frozen `app.anticipy` package's lone non-frozen dependency is `app.proactive.demand_detection.DemandDetector`; that one file must stay.

### 11f. Hardcoded paths to watch (CLAUDE.md flagged scale bugs)

- `/Users/omarebrahim/.anticipy/chrome-real-clone`. appears in `com.anticipy.chrome.plist`, `anticipy_acceptance.py:1021`, `z001_e2e_harness.py`, and several others. Must become `~/.anticipy/chrome-real-clone` for scale.
- `/tmp/anticipy-omar-flow-home.EsPus7`. `anticipy_acceptance.py:200, 960, 1017`. Must be a generated temp dir.
- `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL`. referenced in `com.anticipy.claude-remote-control.plist`, the overnight script env files. Stale: canonical is `/Users/omarebrahim/Developer/Anticipy-V7` per HANDOFF.md.
- `omarkebrahim+anticipy-{dana,priya,maya}@gmail.com`. appears as test recipients in CHECK 05, 08, 09, 10 and in `agent_reliability.py`. These belong only in proof artifacts; CLAUDE.md flags them as scale bugs if they leak into shipping code.
