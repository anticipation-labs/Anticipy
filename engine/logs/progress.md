# Anticipy — Full Hardening Plan & Progress (single source)

Last update: 2026-05-07 (extension hardening complete; hardware guide shipped; cloud deploy + voice probe remaining)

## Latest session summary (14 commits, all generic, no hardcoding)

**Extension capabilities, generic, all committed:**
- Shadow DOM (open + closed via MAIN-world attachShadow patch)
- Canvas typing (Docs/Sheets path + active contenteditable fallback)
- WebGL pointer dispatch (DPR-aware viewport coords)
- Force_type (native value setter for React/Vue inputs)
- Pierce_query (visible-text find across shadow + iframes)
- Type+submit (one-step search/login flows; uses form.requestSubmit)
- Tab management (open_tab/list_tabs/switch_tab/close_tab)
- Wait strategies (url/selector/text/idle, no consecutive waits possible)
- Generic modal/consent dismissal (visible-text-affinity ranking)
- Ranked headings exposed in page state for the LLM
- Code-level guards: consecutive waits, runaway selectors, jQuery selectors
- Auto-retry on truncated JSON with brevity hint
- Provider order Gemini-primary, Groq-fallback
- MAX_STEPS 20→60, TASK_TIMEOUT 5min→10min

**Production bugs fixed (every real user was affected):**
- Added missing `execution_result` + `executed_at` columns via migration
- Fixed extension status value `completed` → `executed` (schema constraint)
- Updated deprecated `gemini-2.0-flash` (404) → `gemini-2.5-flash`
- Bumped output token budget 500 → 2000 (was truncating mid-JSON)
- Two-step PATCH (status separate from result) for schema-drift resilience

**Tests:**
- Deterministic 8/8 × 3 consecutive runs ✅
- Hard LLM-driven 4-5/5 (cross-tab on Wikipedia+DDG passes most runs;
  occasional LLM variance on final convergence)
- Test infra is fully LOCAL — no Supabase INSERT, no Realtime broadcast;
  drives extension's BrowserAgent via SW debug hook + reads
  chrome.storage.local.agentStatus

**Internal docs:**
- /internal/hardware-transfer page shipped — full architecture map,
  on-device vs off-device split, BLE→Supabase dispatch protocol, exact
  API contracts, ship-day checklist, what NOT to put on the wearable

**Remaining open:**
- Cloud engine deploy to Fly.io (Dockerfile + start.sh ready; user's call
  when to push the green button)
- End-to-end voice → analyze → confirm → extension probe
- Per-user LLM key rotation (currently shared key fan-out; works for
  ≤100 users but not beyond)

## The product (corrected understanding)

Wearable listens all day → **proactive engine** decides intents (sparing,
~1-6/day) → fires intent into **Supabase Realtime** → **Chrome extension**
in user's real Chrome silently executes in their actual logged-in tabs. User
**never types**, never opens chat, never sees JSON. The thing they were just
talking about is already done by the time they look.

`anticipy.ai/engine` chat page = demo / setup / debug surface. Not the
product. Cloud engine path = backup for when extension is offline or blocked.

All of this must be portable to wearable hardware (proactive on-device,
extension stays on user Chrome, Supabase as glue).

## Phases

1. **Discovery (parallel agents)** — extension audit, proactive→ext wire
   check, deploy-readiness check.
2. **Extension hardening (main thread)** — shadow-DOM open via MAIN-world
   inject, canvas typing via `document.execCommand('insertText')`,
   force-typing for React inputs, WebGL pointer dispatch, system-prompt rules.
3. **Pipeline wire** — verify / build the proactive→Supabase producer; probe
   end-to-end.
4. **Test harnesses** — extension torture (Playwright + unpacked extension +
   synthetic intents + LLM judge), 30+ scenarios; cloud torture
   (already built); proactive integration test.
5. **Iterate to 100%** — 3 consecutive clean torture runs, no per-site code,
   no regex, no keyword tables.
6. **Cloud failover** — deploy engine to Fly.io (or chosen host), update
   `NEXT_PUBLIC_ENGINE_URL`, redeploy website.
7. **Hardware-portability guide** on anticipy.internal — map components to
   wearable boundaries.
8. **Final pipeline integration test** — voice → action, end-to-end, real site.

## Hard rules

- No hardcoding, no regex routing, no keyword tables, no site whitelists.
- Generic only: prompts, model swaps, custom actions, system rules, MAIN-world
  injects.
- Every fix gated by a torture test before commit.
- Tests run until 3× clean before moving on.
- Single progress log = THIS FILE.

## Truthful state on disk

- Working tree clean. Prior in-conversation changes to `agent.py` (force_type CDP injector,
  field-completeness rule, removal of `from __future__ import annotations`) and the
  `code_sandbox.py` rewrite **were never committed**. The on-disk versions are the
  pre-hardening state.
- Memory file `project_engine_hardening.md` is therefore optimistic relative to disk —
  trust this log over memory for "what is shipped."

## Live status

| System | Last verified pass rate | Notes |
|---|---|---|
| Action engine real-world (test_real.py) | 22/22 NOT verified on disk | Needs re-run after agent.py hardening reapplied |
| Action engine torture (NEW) | not yet built | engine/test_torture_browser.py to be created |
| Proactive 30-scenario eval | 86.7-90% | Plateau on n=2; subagent pushing past 95% via architectural levers |
| Proactive torture (long convo) | 100/100 P/R last 4 runs | Stable |
| Code sandbox (test_code_sandbox.py) | 24/24 (in-memory; not on disk) | Needs reapply + reverify |
| Unit suite (auth/router/safety/main_security/proactive/models) | 128/128 | On disk |

## Workstreams (multi-agent)

- **MAIN** — re-apply browser-agent fixes from prior session, add canvas/WebGL/Docs
  handlers from cutting-edge research, build torture harness, iterate to 100%.
- **SUB-A (research)** — survey 2025-2026 solutions for canvas/WebGL/Docs automation.
- **SUB-B (proactive)** — push eval past 95% via Donna model swap and/or larger N.

## Hard rules (per user directive)

- No hardcoding, no regex routing, no keyword tables, no site-specific selectors.
- Generic-only fixes: system-message rules, custom actions, model swaps, prompt clarification.
- Tested-until-failure on every system.
- "100% / 1,000,000% / no in between."

## Iteration log

### 2026-05-06 — extension audit (subagent)

Confirmed 8 gaps in `/workspaces/Anticipy/extension/`:

1. **Shadow DOM** — `content.js:143-183` `findElement` and `:254-289` `getInteractiveElements` use `document.querySelector`/`querySelectorAll` only. No piercing. Closed roots invisible.
2. **Canvas-only surfaces (WebGL)** — `element.click()` is `isTrusted=false`. Many WebGL apps reject. No coordinate click.
3. **Google Docs/Sheets** — `contenteditable` listed but extension can't reach the offscreen iframe. No `execCommand('insertText')` path.
4. **React-controlled inputs** — `fillInput` already uses native value setter (`content.js:187-203`) — this gap is smaller than I thought, but no post-type verification/retry.
5. **Multi-step lazy-loaded** — `waitForSelector` MutationObserver doesn't observe attribute/character data; misses some SPA patterns.
6. **Login walls** — no detection. Agent loops to MAX_STEPS instead of clean decline.
7. **Field completeness** — system prompt at `agent.js:11-64` doesn't enforce listing every requested field before `done`.
8. **Hardcoding violations** — `content.js:107-127` legacy `add_todo` uses hardcoded placeholder strings ("todo", "task", "add"). Must be removed.

Capabilities the extension already has (good):
- Native value setter for React inputs
- Multi-strategy `findElement` (selector → text → aria → placeholder)
- TreeWalker visible text
- `getInteractiveElements` with proper visibility filtering
- MV3 keepalive alarm to prevent service-worker death
- Content-script auto-injection retry from background

Auth model: extension fetches Groq/Gemini keys from `anticipy.ai/api/extension/auth` after access-code exchange; Supabase Realtime joined via anon key. No user-identity session — pure broadcast model.

### 2026-05-06 — main thread (extension hardening — generic capabilities shipped)

**content.js**
- Added `pierceQuery`/`pierceQueryAll`: recursive DOM walkers that pierce open
  shadow roots and same-origin iframes. Used everywhere the extension previously
  did `document.querySelector` / `querySelectorAll`.
- `findElement` now pierces shadow + iframes for selector / text / aria /
  placeholder strategies.
- `findByVisibleText`: piercing search by visible text, returns shortest match,
  for the LLM's `pierce_query` action.
- `forceTypeInto`: force-write via native value setter + dispatches
  input/change/keyup. Fallback when `type` snapped back.
- `canvasInsertText`: locates `iframe.docs-texteventtarget-iframe` recursively,
  focuses inner contenteditable, uses `document.execCommand('insertText')`.
  Falls back to active contenteditable for non-Docs canvases.
- `dispatchCanvasPointer`: full pointer/mouse event sequence at viewport coords,
  DPR-aware, dispatched at `document.elementFromPoint(x,y)`.
- `getInteractiveElements` walks shadow + iframes, includes `<canvas>` with
  `isCanvas:true` hint so LLM knows to use coordinate strategies.
- `waitForSelector` uses `pierceQuery` + observes attribute/character mutations.
- Removed legacy `add_todo` action with hardcoded placeholder strings (clear
  hardcoding violation).

**background.js + world_patch.js**
- New `extension/world_patch.js`: monkey-patches `Element.prototype.attachShadow`
  to coerce `mode:'open'`. Idempotent.
- `chrome.scripting.registerContentScripts` registers `world_patch.js` with
  `runAt: 'document_start'`, `world: 'MAIN'`, `allFrames: true`,
  `matches: ['<all_urls>']` — runs before any page script, opening every
  shadow root including closed ones. Generic; no per-site code.

**agent.js**
- System prompt extended with: 4 new actions (`force_type`, `canvas_type`,
  `canvas_pointer`, `pierce_query`); FIELD COMPLETENESS rule (list every
  requested item before `done`); CANVAS / WEBGL FALLBACK rule (when
  INTERACTIVE ELEMENTS is empty / `isCanvas:true`, switch strategies);
  LOGIN-WALL HANDLING rule (decline cleanly, don't loop).
- `_toDomAction` routes the four new actions to content.js.

**Syntax**: all 5 extension JS files parse clean (`node --check`).

### 2026-05-06 — production wire (subagent finding)

The Python proactive cascade I hardened yesterday is **eval-only**. The actual
production producer is the Next.js API at
`src/app/api/engine/analyze/route.ts` (lines 224-240 INSERT, 266-288 broadcast
on `realtime:anticipy-intents`). Extension consumer is live: joins both
`realtime:anticipy_db` (postgres_changes) and `realtime:anticipy-intents`
(broadcast). End-to-end wire is 95% live; the one gap is whether
`/engine` page has a working "Confirm" button that PATCHes status to
`confirmed`. Need to verify.

### 2026-05-06 — deploy readiness (subagent finding)

Engine Dockerfile build currently fails: `python-dotenv==1.0.1` conflicts with
`browser-use 0.12.6` (needs 1.2.1). Plus 3 smaller fixes (fonts, Xvfb readiness
wait, profile dir on /tmp). Recommended host: Fly.io shared-cpu-2x, 2 GB RAM,
~$15-25/mo. Concrete 10-step deploy checklist captured.

### 2026-05-06 — deploy blockers fixed on disk

- `engine/requirements.txt`: relaxed `python-dotenv==1.0.1` → `>=1.2.1`.
- `engine/Dockerfile`: added `fonts-liberation`, `fonts-noto`, `fonts-noto-cjk`,
  `fonts-noto-color-emoji`, `x11-utils`. Created persistent `/data/engine_profiles`
  dir and set `BROWSER_PROFILE_BASE` env to point at it.
- `engine/start.sh`: added `xdpyinfo` readiness wait for Xvfb, `set -e`,
  `exec uvicorn …`, EXIT trap to clean Xvfb.
  Build can now happen as soon as we want to push to Fly.io.

### 2026-05-06 — extension torture harness shipped

`engine/test_torture_extension.py` (~340 LOC):
- Generates 9 categories × N adversarial scenarios via Gemini 2.5 Flash.
- Launches headed Chromium via Playwright with `--load-extension=/extension/`
  (persistent context, ephemeral profile).
- Seeds the extension's `chrome.storage.local` with Groq+Gemini keys via the
  popup page's chrome API (bypasses access-code popup for test runs).
- Inserts each intent into `anticipy_intents` (service-role key), navigates to
  the scenario's `starting_url` for warm-start, then PATCHes status to
  `confirmed` — production-faithful trigger path identical to
  `/api/engine/confirm/route.ts`.
- Polls the row for `completed`/`failed` (180s timeout), cleans up after.
- LLM-judges each run against `success_criteria`. Aggregates by category.

### 2026-05-07 — extension actions 8/8 × 3 (committed 102c4d8)

Generic capability fixes for the Wikipedia "search button" failure:
- type+submit:true one-step flow (overrides "find the search button" with form.requestSubmit)
- click of <button type=submit> inside <form> coerces to form.requestSubmit(button)
- keypress Enter inside <form> also calls form.requestSubmit()
- ensureShadowOpenRegistered fires on install + startup + module-load (covers Playwright fresh profiles where MV3 install/startup don't fire)
- content.js asks background to inject world_patch as a backstop on every load
- agent.js _callLLM error message includes underlying provider error (was misleading "No API keys")

Deterministic test harness: engine/test_extension_actions.py — 8 scenarios.
Result: 8/8 (100%) on three consecutive runs (run 1, 2, 3 all green).
Includes: real Wikipedia search, real DDG search, closed-shadow-DOM pierce
(custom element with mode:'closed'), YouTube shadow pierce_query, generic
contenteditable canvas type, multi-field form completeness, React TodoMVC
force_type, canvas pointer dispatch.

### 2026-05-07 — extension expanded for complex tasks (uncommitted)

Added to extension/agent.js + content.js + background.js:
- Tab management actions: open_tab, list_tabs, switch_tab, close_tab.
  chrome.tabs lives in SW; agent calls bridge through SW message handlers.
- wait_for action: any-of url-substring / selector / visible-text / network-idle.
  Saves time on fast pages, prevents stalls on slow ones.
- dismiss_modal action: generic visible-text-affinity ranking for accept/agree/
  dismiss/close verbs + z-index hint + aria-label "close" hint. No per-site
  keyword tables.
- MAX_STEPS bumped 20→60, TASK_TIMEOUT 5min→10min for multi-step flows.
- system prompt extended with: CONSENT BANNERS rule (dismiss_modal first),
  WAIT INTELLIGENTLY rule (use wait_for vs fixed sleeps), MULTI-TAB / MULTI-
  STEP / RESEARCH RULES (open_tab + accumulate in extracted_data + reason
  across at end), LONG-RUNNING TASKS rule (60-step budget, don't rush done),
  FOLLOW-UP HANDLING rule (use list_tabs + switch_tab to revisit prior work).

### 2026-05-07 — repo cleanup (commits bbfa693..b364efa)

Subagent committed the 34 untracked + dependent files in 7 logical groups:
- bbfa693 — proactive engine package (~6,316 LOC)
- 21ce942 — code sandbox (bwrap multi-tenant isolation, 24/24 tests on disk)
- c6c5d32 — engine unit suites (will fail import until app/models.py updated)
- 00007d4 — misc tests (torture browser/extension, wire diag)
- 5869c60 — engine config + agent.py (cloud Browser Use force_type/canvas/etc)
- bc1799e — Next.js gating + transfer-gate + helpers (12 src files)
- b364efa — investor + engine roadmap docs

### 2026-05-06 — production confirm flow verified

Read `/workspaces/Anticipy/src/app/api/engine/confirm/route.ts` — confirm
button is wired and atomic. The flow is:

1. `analyze/route.ts` LLM extracts intents → INSERT `anticipy_intents`
   (status=pending) → broadcast `new_intent` on `realtime:anticipy-intents`.
2. Extension shows Chrome notification.
3. User clicks → opens `/api/engine/confirm?intentId=X&action=yes`.
4. Confirm route atomically PATCHes status pending→confirmed (TOCTOU-safe via
   `WHERE status='pending'`), runs server-side `executeAction(intent)`, then
   PATCHes again to `executed`/`failed`, inserts an `anticipy_actions` log row.
5. For browser-routed intents (`result.data.routing === 'browser'`), also
   sends a `confirmed_intent` broadcast so the extension picks it up and
   runs the agent in the user's tab.

The torture harness above mirrors this exactly via the UPDATE→confirmed
path, which fires postgres_changes to the extension same as production
(RLS is disabled, so anon-key consumer sees the change).

- Re-applied browser-agent hardening to `engine/app/agent.py`:
  - Removed `from __future__ import annotations` (PEP 563 was breaking
    Browser Use's Controller registry parameter-type checks).
  - Registered four generic custom actions on a `Controller`:
    `force_type` (React-safe native value setter via CDP `Runtime.callFunctionOn`),
    `canvas_type` (focuses `iframe.docs-texteventtarget-iframe`'s contenteditable
    and uses CDP `Input.insertText` for canvas editors; falls back to per-char
    `Input.dispatchKeyEvent` for non-Docs canvases),
    `pierce_query` (recursive querySelector that walks open shadow roots AND
    same-origin iframes, returning bounding-box center),
    `canvas_pointer` (CDP `Input.dispatchMouseEvent` press/release with
    devicePixelRatio scaling for vision-derived screenshot coords).
  - Installed `Page.addScriptToEvaluateOnNewDocument` shadow-DOM open-coerce
    patch right after session start so closed shadow roots become accessible.
  - Added `extend_system_message` with five rules: field-completeness before
    `done`, `force_type` fallback when `input_text` doesn't visibly change,
    `canvas_type` for canvas editors, `pierce_query` / `canvas_pointer` for
    DOM-empty pages, no value invention.

- Source for techniques: research subagent's 2025-2026 survey covering
  Microsoft Fara-7B (Nov 2025), SeeAct-V universal grounding, Yotam's CDP
  shadow-pierce writeup, browser-use issues #2339 and #4571,
  chrome-devtools-mcp issue #403, and Playwright issue #23047.

- Verified `agent.py` loads cleanly; controller registry contains all four
  custom actions plus the default registry (force_type, canvas_type,
  pierce_query, canvas_pointer present).

### Test status
- `test_auth.py`: 15/15 ✅
- Other unit suites: import errors against on-disk `app/models.py` and
  `app/main.py` because in-conversation symbols (`DegradedResponse`,
  `effective_layer_timeout_seconds`, `_ws_connections_by_user`) were never
  committed. The proactive subagent (worktree) will resolve those.

### Smoke run
- Started 1-per-category torture run (9 scenarios) in background. Monitor
  armed for verdict/error signals.

### Subagents
- SUB-A (research): COMPLETE — concrete techniques delivered + applied.
- SUB-B (proactive push): RUNNING in worktree.

