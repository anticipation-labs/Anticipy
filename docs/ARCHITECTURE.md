# Anticipy V7 Architecture

End-to-end map of how Anticipy actually works. Pulled from code, not memory.
Frozen paths called out per pillar. Recent session features summarized at the
bottom with commit SHAs.

## High-level flow

```
+--------------------+   anticipy://session   +-------------------------+
|  anticipy.ai/app   | -------token--------->  | /Applications/Anticipy.app |
|  (Next.js + Supabase)                       | Tauri shell + sidecar    |
+----------+---------+                        +----+----------------+----+
           | signup                                 | spawns               | spawns
           v                                        v                      v
+--------------------+   exchange         +---------------------+   +------------------+
| Supabase auth.users| <----token-------- | anticipy-engine     |   |  Real Chrome     |
| handoff_tokens (5m)|     /api/auth/     | FastAPI :8731       |   |  --remote-       |
+--------------------+     exchange       +----+------+---------+   |  debugging       |
                                               |      |             |  -port=9222      |
                                               | 7777 |             +---------+--------+
                                               v      |                       ^
                                          +---------------------------+       |
                                          | anticipy_bridge_fallback  |---9222|
                                          | CDP-first :7777           |       |
                                          +---------------------------+
```

## 1. Frontdoor

The public web surface lives in `src/app/` (Next.js App Router on
anticipy.ai/app via Vercel).

- `src/app/app/page.tsx:1-50` is the product surface. Real Supabase auth, real
  download, real engine round trip. `LOCAL_ENGINE = "http://127.0.0.1:8731"`.
- `src/app/api/auth/signup/route.ts:1-40` accepts `{email, password}` and uses
  the Supabase service-role key to call `auth.admin.createUser({email_confirm:
  true})`. No email send. Honest auth.users row.
- `src/app/api/auth/handoff/mint/route.ts:1-40` mints a single-use handoff
  token signed against the new session. Returns `{token, deep_link,
  expires_at}` (5-minute TTL).
- `src/app/api/auth/exchange/route.ts:1-40` swaps the handoff token for the
  real `{access_token, refresh_token, user}` payload. One use, then 410 Gone.
- The download route at `src/app/download/route.ts` serves the public R2 DMG at
  `https://pub-e97c6305fe2949d8a5d17885f7be2a0e.r2.dev/Anticipy_1.0.0_aarch64.dmg`.

After install, `/Applications/Anticipy.app` registers the `anticipy://` URL
scheme and handles `anticipy://session?token=...` on first launch.

```
[browser] /api/auth/signup ->  auth.users row
[browser] /api/auth/handoff/mint ->  {token, deep_link}
[user]    clicks anticipy://session?token=...
[macOS]   opens Anticipy.app
[app]     POST /api/auth/exchange ->  {access, refresh}
[app]     stores refresh_token in macOS Keychain
```

## 2. Engine

The PyInstaller-bundled binary at
`/Applications/Anticipy.app/Contents/MacOS/anticipy-engine` is a FastAPI app
mounted from `engine/app/product/server.py` (6780 lines, the unfrozen seam
where all V7 work lands).

Lifecycle (`engine/app/product/server.py:53`):
- `app = FastAPI(title="Anticipy", version="product-3")`.
- Default bind port `8731` (`server.py:323`,
  `desktop/src-tauri/src/lib.rs:96 DEFAULT_ENGINE_PORT = 8731`).
- The supervisor health loop launches the sidecar directly with
  `ANTICIPY_PORT=8731 nohup /Applications/Anticipy.app/Contents/MacOS/anticipy-engine`
  to avoid the random-port behavior of the GUI launcher
  (`tools/anticipy_supervisor.sh:33-46`).
- On boot the engine writes the resolved port to `~/.anticipy/engine.port`
  (`server.py:336-354`) so the Tauri shell can discover it
  (`desktop/src-tauri/src/lib.rs:984-1005`).
- Frozen wrappers used read-only: `app.anticipy.handoff` for token routes
  (`server.py:73`), `app.anticipy.memory` for dossier reads
  (`engine/app/product/dossier_active_loader.py:1-12`), and
  `app.listen.stream` for Deepgram Nova-3 streaming STT (`server.py:82`).

Routers are deferred-attached at the bottom of `server.py:6660-6770`. Each
unfrozen subsystem ships its own `*_endpoints.py` + `*_wire.py` and is
include-once-guarded so an in-flight edit cannot crash startup.

### 2a. Intent extractor

`engine/app/product/intent_extractor.py:1-60`. Cheap-model cascade
(`TEXT_CASCADE = ["deepseek/deepseek-v4-flash", "moonshotai/kimi-k2.6",
"google/gemini-2.5-flash"]`, line 25-29). Hard-negative filters for
third-party wants, hypotheticals, jokes, satisfied wants. Single dataclass
`Intent` (line 37) crosses the wire.

HTTP surface: `engine/app/product/intent_extractor_endpoints.py:52-73`
exposes `POST /api/intent/extract` and `POST /api/intent/extract_batch`. Every
input mode (laptop mic, MP3, transcript paste, extension capture) converges
here before planning, risk scoring, or memory writes.

### 2b. Context attacher

`engine/app/product/context_attacher.py:1-60`. Gathers four things for the
planner: scoped memory, recent surface snapshots, learned recipes, and
resolved people. Lazy-imports each collaborator (`ScopedMemory`,
`RecipeStore`, `DossierLoader`, `PersonResolver`) so missing modules degrade
to empty defaults instead of crashing.

Per-step entry point: `ContextAttacher(account_id,
device_id).attach(intent, surface, history)` (line 55-60).

HTTP surface: `engine/app/product/context_attacher_endpoints.py:39` exposes
`POST /api/context/attach`.

### 2c. Action binder

`engine/app/product/action_binder.py:1-50`. Glue between
`intent_extractor` and `ActionDispatcher`. Resolves person refs, fills slots
from memory, picks a surface route, asks `risk_assessor` whether confirm is
required, seeds the planner with any learned recipe.

No-decline contract: if a slot is missing the `Binding.planned_primitives`
becomes `[{type: "ask_user", ...}]` (line 8-9). The dispatcher then asks the
user instead of declining.

Surface mapping table at line 24-48 maps domains to surface tokens
(`mail.google -> gmail`, `calendar.google -> google_calendar`, `notion ->
notion`, `figma -> vision`, `reminder -> native_macos_reminders`, etc.).

HTTP surface: `engine/app/product/action_binder_endpoints.py:43-59` exposes
`POST /api/action/bind` and `POST /api/action/bind_and_execute`.

### 2d. Risk assessor

`engine/app/product/risk_assessor.py:1-30`. Returns a `RiskAssessment` whose
`proceed_mode` is exactly one of `silent | notify | confirm | ask`. There is
no `decline` mode (line 4-5). Pure Python, no network. Word-class tables
for money verbs (line 17), irreversible verbs (line 24), third-party verbs
(line 30), routine verbs (line 35).

HTTP surface: `engine/app/product/risk_assessor_endpoints.py:53` exposes
`POST /api/risk/assess`. Mounted only when not already attached
(`server.py:6724`).

### 2e. Dossier loader (M1)

`engine/app/product/dossier_active_loader.py:1-12`. Wraps the frozen
`app.anticipy.memory` without editing it. Exposes people, preferences,
do_not_touch rules, pronoun_map, recent_topics, and
`as_context_block(...)` for prompt prepending.

Lookup priority (line 49-57):
1. `~/.anticipy/v7/dossiers/<account_id>/dossier.json`
2. `~/.anticipy/v7/dossier.json`
3. `~/.anticipy/dossier.json`

Test override via env `ANTICIPY_V7_DOSSIER_ROOT`.

HTTP surface: `engine/app/product/dossier_endpoints.py:123-222` exposes
`GET/POST /api/dossier/active`, `POST /api/dossier/refresh`,
`GET /api/dossier/context`.

### 2f. Person resolver (M2)

`engine/app/product/person_resolver.py:1-30`. Vague references to `Person +
confidence`. Pronoun-recency window (30 min). Confidence floor 0.70
(`CONFIDENCE_FLOOR = 0.70`, line 13). Built-in nickname map handles common
forms ("mike" -> "michael", "liz" -> "elizabeth").

HTTP surface: `engine/app/product/person_resolver_endpoints.py:42-49`
exposes `POST /api/person/resolve` and `POST /api/person/disambiguate`.

### 2g. Memory cloud sync (M3)

`engine/app/product/memory_cloud_sync.py:1-60`. Durable outbox for local
-> Supabase memory shipment. Items land in
`~/.anticipy/v7/memory_outbox.jsonl` (append-only). A background worker
ships them to Supabase PostgREST, acks to `memory_outbox.ack.jsonl`,
exponential-backoff to `_MAX_RETRIES = 5` (line 48). No new dependency:
HTTP is stdlib `urllib`. If `SUPABASE_URL` is unset the worker silently
no-ops, so local-only setups keep working.

Kind -> table map (line 36-44): `preference -> anticipy_preferences`,
`profile -> anticipy_user_profile`, `dossier -> dossiers`, default
`anticipy_memory`.

HTTP surface and auto-start: `engine/app/product/memory_cloud_sync_wire.py`
attaches the worker only when `SUPABASE_URL` is configured
(`server.py:6701-6710`).

### 2h. Memory provenance (M4)

`engine/app/product/memory_provenance.py:1-30`. Enforces eight required
fields on every `ScopedMemory` write: `account_id, device_id, source,
timestamp, confidence, kind, active, provenance` (line 18-21). Allowed
`source` values are an explicit allowlist of nine ingest channels
(line 22-26). Invalid writes are logged to
`~/.anticipy/v7/memory_validation_errors.jsonl` and never persisted
(line 5).

HTTP surface: `engine/app/product/memory_provenance_endpoints.py`
attached at `server.py:6670-6675`.

### 2i. Surface execution (universal runtime)

`engine/app/product/universal_surface_runtime.py:1-30`. The HANDS of
Anticipy. Drives the user's real Chrome via the loopback bridge
(`http://127.0.0.1:7777`, line 27-31) and falls back to `osascript` for
read primitives so Anticipy never returns "I cannot do X." Set-of-Mark
labels (`M1, M2, M3...`) derived from a System Events accessibility scan
when DOM/extension is unavailable (line 9-12).

Dispatcher contract: `engine/app/product/action_dispatcher.py:1-15`.
`MAX_STEPS = 20`, `SAME_PRIMITIVE_RETRY_CAP = 3`. Four terminal outcomes:
`success | ask_user | notify | in_progress`. Never returns `declined`.

DOM extraction: `engine/app/product/surface_dom_extractor.py:1-30` walks
the live DOM through the bridge's `/surface-command {command:"eval_js"}`
route. Vision adapter for canvas apps:
`engine/app/product/surface_runtime_vision.py:1-12` calls Kimi K2.6
multimodal (`PRIMARY_MODEL = "moonshotai/kimi-k2.6"`, line 39) with
Set-of-Mark overlay.

## 3. Bridge

`~/.anticipy/anticipy_bridge_fallback.py` (903 lines, copied from
`scripts/v7/anticipy_bridge_fallback_cdp.py`).

Boot probe (line 109-121): hits `http://localhost:9222/json/version`. If
9222 responds, every command routes through Chrome DevTools Protocol on
the user's already-running Chrome. If 9222 is dead, falls back to
AppleScript so existing tests keep passing.

CDP unlocks three things AppleScript cannot do safely (file header
line 16-25):

1. `Target.createTarget {background: true}` (line 201-216) opens new tabs
   without stealing OS focus. The car can navigate while the user types
   in another tab.
2. `Runtime.evaluate` (line 230-233) runs JS in any tab without requiring
   Chrome's `View > Developer > Allow JavaScript from Apple Events`
   accessibility toggle.
3. `Page.captureScreenshot` (line 254-258) returns base64 PNG of the
   actual rendered tab even when a different window is frontmost.

Library choice (line 35-39): `websockets.sync.client`, not
`websocket-client`. Chrome 148+ with `--remote-allow-origins=http://
localhost:*` rejects the Origin header the latter always sends.

HTTP surface (preserved from AppleScript bridge for backward-compat):
`GET /status`, `POST /surface-proof`, `POST /surface-command`.

## 4. Chrome

User's real Chrome profile cloned to `~/.anticipy/chrome-real-clone` on
first launch (`desktop/src-tauri/src/lib.rs:65-66`,
`CHROME_PROFILE_DIR_NAME = "chrome-real-clone"`,
`CHROME_REMOTE_DEBUG_PORT = 9222`).

Launch (`desktop/src-tauri/src/lib.rs:665-680`):
```
/Applications/Google Chrome.app/Contents/MacOS/Google Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=~/.anticipy/chrome-real-clone \
  --no-first-run \
  --no-default-browser-check \
  about:blank
```

Engine-side guardrail: when the running engine reports
`chrome_user_data_dir` containing `chrome-real-clone` AND
`ANTICIPY_ENABLE_LEGACY_CLONE_CDP` is unset, the V7.10 check
(`scripts/v7/check_done.sh:96-106`) flips the
`real_chrome_user_surface_no_clone` gate red. The shipped configuration
prefers `installed_chrome_extension`, `chrome_extension_native_messaging`,
`chrome_extension_debugger`, or `real_chrome_applescript_visible_surface`.
The clone path stays as legacy-on-toggle (`server.py:118-120`,
`server.py:295-307`).

## 5. Surfaces

The universal runtime (Agent L work) is the read-act-verify abstraction
all surfaces hit through.

- DOM-aware path: `engine/app/product/surface_dom_extractor.py`. Compact
  accessibility-tree extractor at `MAX_NODES = 200`,
  `DEFAULT_MAX_CHARS = 15000`. Inline JS walker selects elements with
  `[role]`, `button`, `input`, `a`, `textarea`, `select`,
  `[contenteditable]`, or `[tabindex]:not([tabindex="-1"])`.

- Vision path: `engine/app/product/surface_runtime_vision.py`. For Figma,
  Canva, Adobe Express, native windows: capture screenshot, ask Kimi K2.6
  multimodal to enumerate clickable bboxes, overlay numeric Set-of-Mark
  labels, expose description-based lookup. Frozen
  `engine/app/action_engine/` is never imported.

- Native macOS path:
  `engine/app/product/native_action_macos.py` (Calendar, Reminders, Notes,
  Finder, Messages) attached at `server.py:6712-6716`.

- Confirm card surface: `engine/app/product/confirm_card.py` (349 lines).
  Money and irreversible plans surface a card the user approves or denies
  from `/app` instead of being flat-declined.

## 6. Memory

Storage layout (`engine/app/product/scoped_memory.py:1-10`):
```
~/.anticipy/v7/
  dossiers/<account_id>/dossier.json        (M1 loader)
  memory/<account_id>/<device_id>/memory.jsonl (scoped writes)
  memory_outbox.jsonl                       (M3 outbox)
  memory_outbox.ack.jsonl                   (M3 acks)
  memory_validation_errors.jsonl            (M4 rejects)
```

The frozen `app.anticipy.memory` uses a static `USER_ID` and is not
account/device scoped. `ScopedMemory` is the canonical V7 wrapper that
adds the eight provenance fields. The class lives at
`engine/app/product/scoped_memory.py:106`. Kind constants at line 25-32
(`KIND_PERSON`, `KIND_PREFERENCE`, `KIND_ALIAS`, `KIND_DO_NOT_TOUCH`,
`KIND_RECIPE`, `KIND_ACTION_OUTCOME`, `KIND_FACT`, `KIND_LATENT_INTENT`).

Cross-key resolution: the partition fix from this session (commits 349f0241
and 1f15360e) translates `user_id <-> account_id` at every dossier and
scoped-memory route in `engine/app/product/dossier_endpoints.py` and
`engine/app/product/scoped_memory_endpoints.py` via a `_resolve_partition()`
helper. The four cross-key paths round-trip the same data
(`state/v7/memory_partition_fix.md:1-30`).

## 7. Strangers

Self-evaluation harness. `scripts/v7/run_one_stranger.sh:1-50` is the
single-run driver:
1. Validate `persona.json` + `script.json` against the V6 contract.
2. Synthesize audio from `spoken_reference_text` via macOS `say` ->
   AIFF -> ffmpeg MP3.
3. POST audio to `/api/listen/upload`.
4. Capture surface receipts.
5. Write `driver_result.json` + `trace.json` + evaluator `verdict.json`.

Generator + evaluator both use OpenRouter:
`scripts/v7/generate_stranger_openrouter.py` (724 lines),
`scripts/v7/evaluate_stranger_openrouter.py:49-53` cascade is
`deepseek/deepseek-v4-flash -> moonshotai/kimi-k2.6 ->
google/gemini-2.5-flash`.

The supervisor's stranger loop cycles 24 verb categories
(`scripts/v7/run_until_100.sh:23-49`), spanning email-draft, task-add,
notes-create, recipe-plan, health-log, expense-track, web-research,
file-search, phone-text, code-run, plus per-SaaS declines for Asana,
Jira, Airtable, Salesforce, Zendesk, Trello, Canvas, Figma, Amazon,
Shopify, OpenTable. 46 successful interactions across 20 verb categories
verified at last measurement (`state/stranger_breadth.json`).

## 8. Supervisor

`tools/anticipy_supervisor.sh` (189 lines). Five concurrent loops, restart
on death (line 172-183):

| Loop            | Lines     | Cadence | Job                                       |
| --------------- | --------- | ------- | ----------------------------------------- |
| `loop_health`   | 27-65     | 60s     | Relaunch engine on :8731 or bridge on :7777 if dead. Hit Chrome :9222 health. |
| `loop_strangers`| 67-80     | 30s gap | Run `run_until_100.sh` until 100 successes, then idle 600s. |
| `loop_v7_gates` | 82-88     | 60s gap | Run `tools/ralph_v7.sh` repeatedly. |
| `loop_autocommit`| 90-117   | 300s    | Stage allowlisted files, refuse secrets, refuse >50 MiB blobs, push to `origin/main`. |
| `loop_status`   | 119-152   | 30s     | Write `state/v7/supervisor_status.json` with engine PID, breadth, gate counts, deploy parity. |

The autocommit loop explicitly resets
`state/v7/clean_room_public_install_runs/` from the index before commit
(line 100) because that directory holds 1-2 GiB DMG copies that once
triggered the GitHub > 2 GiB blob limit.

## 9. Verification gates

`scripts/v7/check_done.sh` (415 lines). 20 mechanical gates writing
`state/check_done_v7.json`. The script writes `state/COMPLETE.md` only
when every gate is true (line 401-411).

| Gate     | Name                                            |
| -------- | ----------------------------------------------- |
| V7.1     | public_app_loads                                |
| V7.2     | public_dmg_installs                             |
| V7.3     | installed_user_device_engine_current            |
| V7.4     | deploy_parity_green                             |
| V7.5     | public_dmg_sha_green                            |
| V7.6     | mp3_input_passes                                |
| V7.7     | text_transcript_input_passes                    |
| V7.8     | computer_mic_input_passes                       |
| V7.9     | external_mic_input_passes                       |
| V7.10    | real_chrome_user_surface_no_clone               |
| V7.11    | 100_stranger_successes (relaxed: >= 25 + 90% last-20) |
| V7.12    | 20_successful_verb_categories                   |
| V7.13    | 5_hard_categories                               |
| V7.14    | last_20_interactions_pass (relaxed: 90%)        |
| V7.15    | 3_consecutive_mp3_evals_pass                    |
| V7.16    | transcript_wer_under_5_percent                  |
| V7.17    | cost_under_ceiling                              |
| V7.18    | 3_clean_room_public_installs (relaxed: theory check) |
| V7.19    | inference_schema_data_eval_exercised            |
| V7.20    | no_fake_receipts_backdoors_stale_proofs         |

Relaxations recorded per owner sign-off:

- V7.11 + V7.14: "if it works 46 times there's no issue" (`check_done.sh:130-141`).
- V7.18: theory check (URL serves 200 + SHA matches manifest + installed
  binary executable + engine `/health` returns ok) instead of three real
  fresh installs (`check_done.sh:268-284`).

## Frozen paths

These directories MUST NOT be edited by builder agents
(`AGENTS.md` frozen-paths block, `CLAUDE.md` rule 1):

- `engine/app/anticipy/` (proactive engine, handoff contract, memory,
  onboarding spine)
- `engine/app/action_engine/` (frozen DSv4SkillRunner CDP driver)
- `engine/app/proactive_day/` (proactive day pipeline)
- `verifier/` (verification harness; edits require explicit Omar sign-off)

All V7 work lives in unfrozen modules under `engine/app/product/*` and
attaches to the frozen pieces only through documented seams (e.g.
`app.anticipy.handoff.attach_to(app)` at `server.py:73`).

## Features delivered this session

### M1 dossier loader (commit ff0e1e2e)

`engine/app/product/dossier_active_loader.py` (366 lines) wraps frozen
`app.anticipy.memory` without editing it. Loads dossier from
`~/.anticipy/v7/dossiers/<account_id>/dossier.json` and exposes
`as_context_block()` for prompt prepending. Endpoints in
`dossier_endpoints.py`: `GET/POST /api/dossier/active`,
`POST /api/dossier/refresh`, `GET /api/dossier/context`.

### M2 person resolver (commit 87eadbb7)

`engine/app/product/person_resolver.py` (323 lines). Resolves vague
references ("Maya", "the boss", "him") to a `Person + confidence` with
pronoun-recency window (30 min) and do-not-touch awareness. Endpoints:
`POST /api/person/resolve`, `POST /api/person/disambiguate`.

### M3 memory cloud sync (commit 9c14e59b)

`engine/app/product/memory_cloud_sync.py` (387 lines). Durable
local-to-Supabase outbox. Items append to
`~/.anticipy/v7/memory_outbox.jsonl`. Worker ships via stdlib `urllib` to
Supabase PostgREST tables (`anticipy_memory`, `anticipy_preferences`,
`anticipy_user_profile`, `dossiers`). Exponential backoff to 5 attempts,
then quarantine. Worker auto-starts only when `SUPABASE_URL` is set.

### M4 memory provenance (commit 69deee6a)

`engine/app/product/memory_provenance.py` (249 lines). Validator
rejects any `ScopedMemory` write missing one of `account_id, device_id,
source, timestamp, confidence, kind, active, provenance`. Allowed
`source` values restricted to nine channels. Rejected items logged to
`~/.anticipy/v7/memory_validation_errors.jsonl` and never persisted.

### Partition fix (commit 349f0241, code in 1f15360e)

Closed a write/read split: dossier loader partitioned by `account_id`,
legacy server endpoints partitioned by `user_id`. The engine could not
see its own dossier. Fix lives in `engine/app/product/dossier_endpoints.py`
and `engine/app/product/scoped_memory_endpoints.py`: every route now
accepts `user_id` as a synonym for `account_id` via a `_resolve_partition()`
helper, and `POST /api/dossier/active` was added so write/read round-trips
through the API surface. All four cross-key paths
(`account_id->account_id`, `account_id->user_id`, `user_id->user_id`,
`user_id->account_id`) round-trip the same data
(`state/v7/memory_partition_fix.md`).

### Decline-killer (commits 89fb56bd + 69deee6a + 54ecb619)

All six competent-decline templates in `engine/app/product/server.py`
rewritten to dispatch via `app.product.action_dispatcher.ActionDispatcher`
and the confirm-card surface for money/irreversible work. Frozen
`engine/app/anticipy/`, `engine/app/action_engine/`,
`engine/app/proactive_day/` contained zero user-facing declines; no
patches required there. Risk assessor enforces the no-decline contract:
`proceed_mode` is exactly one of `silent | notify | confirm | ask`
(`engine/app/product/risk_assessor.py:4-5`).

### Bridge CDP rewrite (commit 67f656bd)

`scripts/v7/anticipy_bridge_fallback_cdp.py` (903 lines, copied to
`~/.anticipy/anticipy_bridge_fallback.py`). Replaces the AppleScript-only
bridge. CDP-first via WebSocket at `localhost:9222`, AppleScript fallback
when 9222 is dead. Uses `websockets.sync.client` (NOT `websocket-client`)
because Chrome 148+ rejects the Origin header the latter sends. Opens
tabs `background: true` so navigating does not steal user focus. Same
HTTP contract preserved (`/status`, `/surface-proof`, `/surface-command`).

### Tab spam fix (commit d2e707d1)

`scripts/v7/probe_real_surface_extension.py` was leaking +1 Chrome tab
per supervisor cycle. The probe now closes the tab it created after the
proof artifact is captured. 33-line addition that stopped Chrome from
accumulating hundreds of background tabs over the multi-day supervisor
run.

### Resolution trace (commit 330a42a6)

`POST /api/inference/trace/{ingest_id}` returns the per-step resolution
trace for a recent inject (`server.py:4301`). Buffer instrumentation in
`dossier_active_loader.py` and `person_resolver.py` captures which
dossier entries and which alias candidates were considered for each
intent extraction. Backs the V7.19 "inference schema + data + eval
exercised" gate.

### Rich test dossier (commit 3cbfc571)

`scripts/v7/load_rich_test_dossier.py` seeds account
`e2e_rich_test_2026_05_28` with 10 contacts (relationships, work
context, communication patterns), 5 ongoing projects (status, blockers,
stakeholders), 3 recurring patterns, 5 preferences, 3 named places, 5
do-not-touch hard rules, 14 alias mappings. Used by the e2e
hard-transcript harness (commit b4b6f652, 20/20 transcripts processed,
memory used by name).
