# Anticipy Engine — Technical Audit & BLE-Pendant Integration Plan
*Read-only audit · target `~/Desktop/Anticipy-executor-working` → `~/Anticipy` · branch `factory/build` (HEAD 2f9d152) · 2026-06-15 · senior-engineer → senior-engineer*

## EXECUTIVE SUMMARY (read in 30 seconds)
1. **The target is the ENGINE, not the product you described.** `~/Desktop/Anticipy-executor-working` is a symlink to `~/Anticipy` — a Python inference-and-action engine. The **DeepSeek/Kimi/Ralph-Loop/Tauri/port-3424/Deepgram** stack from the prompt **does not exist here**; that's the *sibling* repo `~/Developer/Anticipy-DEV-FINAL` (out of scope). Verified by `git grep` (ralph/tauri/src-tauri = 0 files) and this repo's own `logs/journal.md:108`.
2. **Running now:** FastAPI engine on `127.0.0.1:8787` (OpenRouter → Gemini, *not* DeepSeek), Next.js on `:3000`, Chrome CDP on `:9222`. **No `:3424`** ("3424" is log-timestamp noise).
3. **The spine:** `POST /owner/ingest` (or `/event`) → proactive brain (`triage → decider → harm-line`) → `act / ask / silent`. It infers *unspoken* tasks from messy speech; **money is a hard stop**, acting on a vent is the cardinal sin.
4. **Hands:** Arcade API mesh (Gmail/Calendar/Slack/Docs), a browser arm (extension WS **+** browser-use vision over CDP `:9222`, via `POST /agent/act`), and Twilio voice/SMS incl. two-way `/cr`.
5. **Front doors:** a **Swift** menubar app (`macapp/`) and a Next.js owner dashboard (`app/`) — both thin HTTP clients of the engine. (No Tauri.)
6. **To trigger a task today (canonical):** `POST http://127.0.0.1:8787/owner/ingest` with `{"source","text","execute_actions"}` — the engine's *own* brain parses the natural language; no pre-parse LLM needed.
7. **The pendant hook already exists:** `capture/pendant_phone.py` is a reserved, intentionally-empty `CaptureSource` ("only this file gains a body — the engine does not change"); `capture/transcribe.py` is local Whisper — so for omi (which already Deepgram-transcribes) the bridge forwards **text only**.
8. **Pendant integration = a tiny ADDITIVE sibling bridge** that takes the omi transcript and `POST`s it to `/owner/ingest`. **Zero changes to the engine.** Observe via the glass-box + `/pending` + `/owner/cards`.
9. **Honest broken/half-built:** Gmail scope ungranted, onboarding scrape live-fire blocked on a stale Chrome extension, and the engine is **LIVE with real Twilio/Arcade** — a careless POST sends a real SMS / makes a real event. Test against a **mock-channel** instance.
10. **Verify first:** *how the omi macOS app exposes its live transcript* (local socket / file / stdout / IPC). That is the only real unknown — everything engine-side is ready.


---

## SECTION 1: WHAT THIS SYSTEM IS

This repo is the **Python "engine"** of Anticipy: a local-first FastAPI service that ingests a person's messy day (typed transcript or uploaded audio), infers the *unspoken* tasks, decides whether to act / ask / stay silent, and — when it decides to act — executes for real through API connectors, a browser, and a phone line. When the engine runs (`engine/anticipy_engine/main.py`, bound to `127.0.0.1:8787` per `main.py:11` and launched via `python -m uvicorn ... --port 8787`, confirmed from the live process command line and `macapp/Resources/boot.sh:14-17`), it exposes an HTTP/WS surface (route table in `main.py:572-1422`). The product spine runs on every ingested event: `POST /owner/ingest` / `POST /event` (`main.py:713-724`) hand the line to the **proactive engine** (`engine/anticipy_engine/core/proactive.py`), which is a three-room pipeline — **triage** (Room 1, cheap/local bouncer, `proactive/triage.py`) → **decider** (Room 1.5, "did the person actually commit?", `proactive/decider.py`) → **harm-line** (Room 2, deterministic, money/destroy/post-public are HARD STOPS, `proactive/harm.py`) — producing one of `act` / `ask` / `silent` (`core/proactive.py:1-21`). The model calls route through a provider-agnostic gateway (`core/gateway.py:90`, provider `openrouter`; the hardcoded default is `gpt-4o-mini`/`gpt-4o` at `gateway.py:101-102`, but the *running* instance is overridden to `google/gemini-2.5-flash-lite` / `gemini-2.5-flash` per `.env.local:101-108`).

End to end, the user-visible behavior is: a day's speech goes in; the engine silently drops the ~99% that isn't a real task, drafts (never auto-sends) emails or proposes calendar events for the safe middle, and **asks first** before anything irreversible or money-moving. Its hands are three real arms — (a) a **per-person API mesh via Arcade** for Gmail / Calendar / Slack / Docs (`hands/api_hand.py`, `hands/token_vault.py`); (b) a **browser arm with two transports**: a connected Chrome **extension** over `WS /ws/extension` (`main.py:1422`, `core/browser_link.py`, `extension/`) and a **"browser-use" vision agent** driving the user's own logged-in Chrome via CDP on `:9222` (`POST /agent/act`, the proven action arm, `main.py:1214`; `core/native_bridge_link.py:237-238` reads `ANTICIPY_CDP_PORT=9222`); and (c) a **Twilio voice/SMS** loop that closes the circle — outbound SMS/calls (`channels/text.py`, `channels/call.py`), inbound reply polling (`channels/inbound.py`, scheduled at `main.py:113`), and the two-way ConversationRelay voice socket `WS /cr` that answers a real phone call with the *same* decider brain (`main.py:1335`). A Next.js web app on `:3000` (`app/`) and a Swift menubar app (`macapp/`) are the owner-facing front doors. I confirmed `:8787` python, `:3000` node (next-server v15.5.19), and `:9222` Chrome CDP are live, and that **nothing listens on :3424** (`lsof -i :3424` → empty).

**Repo-vs-described mismatch (important):** the stack the prompt was originally framed around — DeepSeek V4 Flash (text), Kimi K2.6 (vision), a "Ralph Loop", a **Tauri** desktop shell, **port 3424**, and **Deepgram** ASR — does **not** substantively exist in *this* repo. `git grep` finds **zero** "ralph"/"tauri"/"src-tauri" files; "deepseek"/"deepgram" appear only as commented options in `.env.example`. Those technologies belong to a **sibling product repo, `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL`** (which actually contains `desktop/src-tauri/` + Parakeet ASR; referenced from this repo's `logs/journal.md` and `logs/verdicts/*`), and that repo is **out of scope / hands-off**. In *this* repo the desktop shell is a **Swift menubar app** (`macapp/Package.swift`, `Sources/AnticipyApp/*.swift`), not Tauri; the model layer is **OpenRouter → Gemini**, not DeepSeek/Kimi; ASR is the engine's own `capture/transcribe.py`, not Deepgram; and the loop is the **`factory/` nightly forcing system**, not a "Ralph Loop". Read this repo as the inference-and-action *engine*; the Tauri/DeepSeek/Deepgram product is the sibling.

---

## SECTION 2: REPOSITORY TOPOLOGY

`tree` is **not installed** on this machine (`tree -L 3` → command absent). The structure below was reconstructed from `git ls-tree -r` (tracked) + `find -maxdepth 1` (to surface untracked dirs). I trimmed: `node_modules/`, `.venv/`, `.next/`, `.git/`, `__pycache__/`, the eight Python sub-packages' `__init__.py` files, and the per-persona `days/` leaf folders under `factory/personas/` (12 personas, each with a `days/` dir of transcript fixtures). **Untracked** dirs (present on disk, not in git) are marked `‡`.

```
/Users/omarebrahim/Anticipy/
├── engine/                         ← THE SPINE (Python FastAPI). All product logic.
│   └── anticipy_engine/
│       ├── main.py                 HTTP/WS surface, binds 127.0.0.1:8787 (route table L572–1422)
│       ├── brain.py                top-level reasoning entry
│       ├── owner_mode.py owner_onboarding.py
│       ├── core/                   ← engine hub / wiring
│       │   ├── control_core.py     ControlCore: composes proactive+glassbox+hands+browser (L18–35)
│       │   ├── proactive.py        ★ THE REAL DECIDER spine (triage→decider→harm→act/ask/silent)
│       │   ├── gateway.py          ModelGateway, provider=openrouter (L26,90; defaults L101–102)
│       │   ├── browser_link.py     Chrome-extension WS transport (token-gated)
│       │   ├── native_bridge_link.py  Chrome CDP :9222 driver (L237–238)
│       │   ├── voice.py glassbox.py scorecard.py store.py bus.py orchestrator.py
│       │   ├── envelopes.py env.py navwall.py worker.py control_core.py
│       │   └── workers/            browser.py channel.py connector.py memory.py scriptable.py
│       ├── proactive/              ← THE BRAIN (per-room logic)
│       │   ├── triage.py           Room 1 — cheap/local bouncer
│       │   ├── decider.py          Room 1.5 — "did they actually commit?"
│       │   ├── harm.py             Room 2 — deterministic harm-line (money=HARD STOP)
│       │   ├── engine.py           ⚠ STUB ("no real deciding yet", L1–5) — NOT the live spine
│       │   ├── agent_reply.py budget.py debounce.py trigger.py
│       ├── hands/                  ← REAL-WORLD ACTION ARMS
│       │   ├── api_hand.py         Arcade API mesh (Gmail/Calendar/Slack/Docs)
│       │   ├── token_vault.py      per-person OAuth token broker
│       │   ├── browser_hand.py browser_use_link.py browser_use_runner.py  browser-use vision arm
│       ├── agent/                  ← browser-use WebVoyager vision agent
│       │   ├── webvoyager.py       the see-locate-act loop
│       │   ├── form_prepare.py handoff.py proof.py site_hints.py
│       ├── channels/               ← Twilio voice/SMS
│       │   ├── text.py call.py     outbound SMS / voice
│       │   ├── inbound.py          inbound SMS reply poller
│       │   ├── conversation_relay.py  /cr two-way voice brain
│       │   ├── app.py base.py
│       ├── capture/                ← intake / ASR
│       │   ├── intake.py transcribe.py mac_mic.py base.py
│       │   ├── pendant_phone.py    ⚠ EMPTY future slot (reserved socket, L1–7) — see §9
│       ├── actions/                action layer + gate (base/browser/connector/gate/layer.py)
│       ├── live_memory/            ← "remember everything" (brain/capture/infer/inject/remember/…)
│       ├── memory/                 embeddings store (embed.py store.py)
│       ├── model/                  client.py (thin model client)
│       ├── onboarding/             clarify.py connection_scan.py profile_builder.py
│       ├── shared/                 task schemas (invoice_draft, slotbooking, schema, …)
│       └── data/                   site_hints_seed.json
├── app/                            ← APP SHELL: Next.js web UI (:3000)
│   ├── page.js layout.js globals.css
│   ├── api/                        route handlers: owner/, memory/, onboarding/, connections/,
│   │                               glassbox/, status/, readiness/, trigger/, download/, pending/
│   ├── connect/  download/
├── extension/                      ← APP SHELL/GLUE: Chrome extension (browser transport)
│   ├── manifest.json background.js engine_client.js popup.{html,js} scripts/ test/
├── macapp/                         ← APP SHELL: Swift menubar app (NOT Tauri)
│   ├── Package.swift  Sources/AnticipyApp/*.swift (5 views)  Resources/boot.sh
│   ├── dist/Anticipy.app/…         built artifact (committed)
│   └── scripts/build_app.sh sign_and_notarize.sh
├── shared/                         glue (shared module, thin)
├── scripts/                        ← GLUE: run_suite.sh, realday.sh, *_loop.sh, package_app.sh,
│                                     test_owner_app_*.sh, test_download_route.sh
├── factory/                        ← BUILD SYSTEM (current nightly forcing loop, NOT product)
│   ├── bin/  config/  gates/  prompts/
│   └── personas/{dev,dev_v2}/<persona>/days/   12 personas (days/ trimmed)
├── autopilot/                      ← DEAD: retired build loop (00_START_HERE…09, loop.sh, judge)
├── overnight/                      ← LEFTOVER experiment: track_a/b/c (run_laps/worker/judge.py)
├── logs/                           ledgers: factory/ (handoffs, RECEIPTS, scoreboard), verdicts/
├── notes/                          scratch: proactive_room1–7.md, wave1_log.md, agent_recipes.md
├── realdays/                       README only (real-Omar-day fixtures live elsewhere)
├── demo/ ‡                         UNTRACKED: anticipy_workings.html (single demo page)
├── tests/ ‡                        UNTRACKED: tests/realday (scratch test dir)
├── .anticipy-data/ ‡               UNTRACKED: browser-agent run artifacts (guitarcenter, lego,
│                                     newegg, gamestop, ulta… — captured agent runs, NOT code)
├── .playwright-mcp/ ‡  .vercel/ ‡  __pycache__/ ‡   tooling/build caches
├── .env.example  .env.local        config (.local has the live openrouter+gemini override)
├── README.md STATUS.md PRODUCT_STATUS.md PENDING_FOR_OMAR.md WAKEUP.md
├── AGENTS.md CODEX_BRIEF.md CLAUDE.md 00_AMENDMENT_NEVER_STALL.md
└── package.json next.config.mjs    (Next.js web app config)
```

### Annotated folder roles

**THE SPINE — the action/proactive engine (everything product-real lives here):**
- `engine/anticipy_engine/` (Python) — the whole product. The HTTP surface (`main.py`), the hub (`core/control_core.py` composes proactive + glassbox + hands + browser at `control_core.py:18-35`), the **decider brain** (`core/proactive.py` + `proactive/{triage,decider,harm}.py`), the **hands** (`hands/` = Arcade API mesh + browser-use; `agent/` = the vision agent; `channels/` = Twilio), memory (`live_memory/`, `memory/`), intake (`capture/`), and task schemas (`shared/`).
- **Spine caveat #1:** `proactive/engine.py` is a labeled **STUB** ("No real deciding yet… proposals are always empty in the scaffold", `engine.py:1-5`). The *live* engine is `core/proactive.py` — don't confuse the two.
- **Spine caveat #2:** `capture/pendant_phone.py` is an **intentionally empty reserved slot** ("intentionally unimplemented in the scaffold", `pendant_phone.py:1-7`) — directly relevant to Section 9.

**APP SHELL (owner-facing front doors):**
- `app/` (JavaScript / Next.js 15.5.19, running on `:3000`) — the web UI + a parallel set of `app/api/*` route handlers that mirror engine endpoints (owner ingest, memory, onboarding, status, download).
- `macapp/` (Swift / SwiftPM) — a **menubar app** (`Package.swift`, 5 SwiftUI views), with a committed built `dist/Anticipy.app` and a `boot.sh` that brings up the engine (`:8787`) and web app (`:3000`). This is the desktop shell — **not Tauri**.
- `extension/` (JavaScript / Chrome MV3) — the browser-extension transport that the engine talks to over `WS /ws/extension`.

**GLUE:**
- `scripts/` (bash + a little Python) — launchers and test harnesses: `run_suite.sh` (the 29-test suite), `realday.sh`, the `*_loop.sh` dev loops, `package_app.sh`, and the owner-app integration tests.
- `shared/` — thin shared glue module.
- `logs/` — the durable ledgers the foreman reads (`logs/factory/` handoffs + RECEIPTS + scoreboard; `logs/verdicts/` are the cross-repo verdicts that reference the **sibling DEV-FINAL** repo).

**BUILD/FORCING SYSTEM (NOT the product):**
- `factory/` (Python + YAML + bash) — the **current** nightly forcing loop: `bin/` runners, `gates/`, `prompts/`, `config/`, and `personas/{dev,dev_v2}/` (12 persona day-fixtures). This is the active CI-style harness, not shipped code.

**DEAD CODE / LEFTOVER EXPERIMENTS / ORPHANED DIRS:**
- `autopilot/` — **RETIRED** build loop. Numbered docs `00_START_HERE`→`09_REPO_FACTS`, `loop.sh`, `build_lap`/`judge_lap`. Superseded by `factory/`. (Note: `factory/build` = `autopilot/build` + ~225 commits; the *branch* lineage is live, but the *directory* is a stale predecessor of `factory/`.)
- `overnight/` — **leftover experiment**: `track_a/b/c`, each a self-contained `run_laps.py`/`worker.py`/`judge.py`/`results.json`. The current decider prompt was *seeded* from `overnight/track_b/decider.py` (per `proactive/decider.py:8`), but the dir itself is no longer wired into anything.
- `demo/` ‡ — untracked single HTML demo page (`anticipy_workings.html`).
- `tests/realday/` ‡ — untracked scratch test directory (the tracked suite lives under `scripts/run_suite.sh` + engine-internal tests).
- `.anticipy-data/` ‡ — untracked **runtime artifacts** from past browser-agent runs (per-site captures: guitarcenter, lego, newegg, gamestop, ulta, etc.). Data, not code; safe to treat as scratch output. (These lap-id timestamps like `…T183424Z` are the source of the bogus "3424" signal — it is a timestamp, not a port.)
- `notes/`, `realdays/` — scratch markdown / README-only stubs.
- `.playwright-mcp/`, `.vercel/`, `__pycache__/` ‡ — tooling/build caches.

ASCII view of how the spine, shells, and glue relate at runtime:

```
        OWNER FRONT DOORS                      THE SPINE (engine, :8787)                 REAL-WORLD HANDS
  ┌──────────────────────────┐        ┌──────────────────────────────────────┐    ┌─────────────────────────┐
  │ macapp/ (Swift menubar)  │        │ main.py  (FastAPI, 127.0.0.1:8787)    │    │ hands/api_hand.py       │
  │ app/ (Next.js  :3000)    │──HTTP─▶│   /owner/ingest /event /agent/act     │──▶ │   → Arcade (Gmail/Cal/   │
  │ extension/ (Chrome MV3)  │──WS───▶│   /cr  /ws/extension                  │    │      Slack/Docs)        │
  └──────────────────────────┘        │            │                          │    ├─────────────────────────┤
                                       │   core/control_core.py (hub)         │    │ agent/ + hands/browser_  │
   PHONE  ──Twilio /cr, SMS──────────▶ │            │                          │──▶ │  use_*  → Chrome CDP:9222│
                                       │   core/proactive.py  (THE DECIDER)   │    ├─────────────────────────┤
                                       │   triage → decider → harm-line       │    │ channels/ → Twilio       │
                                       │     ↓act     ↓ask        ↓silent      │──▶ │  voice / SMS  (the 2:45) │
                                       │   core/gateway.py → OpenRouter/Gemini │    └─────────────────────────┘
                                       └──────────────────────────────────────┘
   BUILD-ONLY (not product): factory/ (nightly loop)   |   DEAD/ORPHAN: autopilot/, overnight/, demo/‡, .anticipy-data/‡
```

---

# SECTION 3: PROCESS MODEL AT RUNTIME

This section maps every process the Anticipy stack spins up on this Mac, how each is launched, the protocol it speaks, and who talks to whom — all grounded in live `lsof`/`ps` output and the code that starts each process. Where a process only starts under specific env, that is called out.

## 3.0 Live evidence (the ground truth)

`lsof -nP -iTCP -sTCP:LISTEN` (loopback set, app-relevant rows only):

```
Google     8835 omarebrahim  53u IPv4  TCP 127.0.0.1:9222 (LISTEN)   <- Chrome CDP
python3.1  8862 omarebrahim   7u IPv4  TCP 127.0.0.1:7777 (LISTEN)   <- native bridge
python3.1 66506 omarebrahim  11u IPv4  TCP 127.0.0.1:8787 (LISTEN)   <- FastAPI engine
node      22303 omarebrahim  12u IPv6  TCP *:3000        (LISTEN)    <- Next.js (next-server)
```

One ESTABLISHED app connection at capture time proves a live edge:

```
Google     3885 ... TCP 127.0.0.1:57301->127.0.0.1:8787 (ESTABLISHED)   (Chrome -> engine)
python3.1 66506 ... TCP 127.0.0.1:8787->127.0.0.1:57301 (ESTABLISHED)   (engine <- Chrome)
```

That is the Chrome extension's WebSocket (`/ws/extension`) talking to the engine — confirmed independently by the live `GET /status` showing `"extension_connected": true`.

`ps -ww` full command lines for the four PIDs:

```
66506  PPID 1     engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787
22303  PPID 22285 next-server (v15.5.19)        [22285 = "npm start", PPID 22283]
 8835  PPID 1     /Applications/Google Chrome.app/.../Google Chrome --remote-debugging-port=9222
                   --remote-allow-origins=http://localhost:* --user-data-dir=/Users/omarebrahim/.anticipy/chrome-real-clone
                   --profile-directory=Default --no-first-run --no-default-browser-check --disable-features=Translate
 8862  PPID 1     /Users/omarebrahim/.anticipy/venv/bin/python /Users/omarebrahim/.anticipy/anticipy-bridge.py
```

### THERE IS NO :3424

`lsof -i -P -n | grep ':3424'` returns **nothing** — no listener, no connection:

```
=== :3424 anywhere in lsof? ===
NO :3424 LISTENER OR CONNECTION
```

The only ports this stack opens are **8787, 3000, 9222, and 7777**. As the audit brief notes, "3424" in the repo is log-timestamp noise (e.g. lap id `20260609T183424Z`); it is never a port. No process binds it; nothing connects to it. The same goes for the user's described stack pieces (Tauri shell, Deepgram, "Ralph Loop", DeepSeek/Kimi) — none are running here, and `--app-dir engine anticipy_engine.main:app` is a Python FastAPI engine, not a Tauri/Rust app.

---

## 3.1 The FastAPI engine — `127.0.0.1:8787` (PID 66506)

| | |
|---|---|
| **Runtime** | CPython (`engine/.venv/bin/python`), Uvicorn ASGI server hosting a FastAPI app |
| **Entry point** | `engine/anticipy_engine/main.py` → module-level `app = FastAPI(...)` (`main.py:126`) |
| **Launch command** | `python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787` |
| **Bind address** | `127.0.0.1:8787` (loopback only) — the app docstring states this explicitly: *"The engine is local-first: it binds to 127.0.0.1 only."* (`main.py:11`, and the FastAPI `description`, `main.py:129`). Uvicorn's default host is `127.0.0.1`, and no `--host 0.0.0.0` is passed, so the listener is loopback — matching the live `lsof` row. |
| **Protocol** | HTTP/1.1 (REST JSON) + WebSocket upgrades on the same port |

**How it is launched.** The canonical launcher is `macapp/Resources/boot.sh:14-18`, invoked by the Swift menubar app (`macapp/`, see §3.2). It only starts the engine if it isn't already up:

```bash
# macapp/Resources/boot.sh:14
if ! curl -s -m2 http://127.0.0.1:8787/readiness >/dev/null 2>&1; then
  ANTICIPY_HANDS_MODE=mock ANTICIPY_CHANNELS_MODE=live PYTHONPATH="$REPO/engine" \
    nohup "$REPO/engine/.venv/bin/python" -m uvicorn --app-dir "$REPO/engine" \
    anticipy_engine.main:app --port 8787 >/tmp/anticipy_engine.log 2>&1 &
fi
```

Note the env this launcher bakes in: `ANTICIPY_HANDS_MODE=mock` and `ANTICIPY_CHANNELS_MODE=live`. The *currently running* PID 66506 has `PPID 1` (re-parented to launchd — the `nohup &`'d process outlived its launching shell), and its live `/status` reports `api_hands` live + `channels.mode:"live"`, so the actually-running instance was **not** started with the `boot.sh` mock-hands defaults; it was launched with live hands/channels env (most likely by a watchdog launch agent — `com.anticipy.engine-watchdog.plist` exists in `~/Library/LaunchAgents/` — or a manual run). I cannot determine the exact launcher of *this specific* PID from code alone; the command line and PPID=1 only prove it is the same uvicorn entry, detached.

**Lifespan-managed background tasks** (`main.py:104-123`, `lifespan()`), started inside the engine process — these are **asyncio tasks on the event loop, not separate OS processes**:

1. **Tick scheduler** — `_trigger_scheduler()` (`main.py:82-90`). Created only if `interval_s > 0`; interval from `ANTICIPY_TICK_SECONDS` (default `"30"`). `ANTICIPY_TICK_SECONDS=0` disables it (deterministic tests drive `POST /trigger/tick` by hand). It calls `core.proactive.trigger_tick()` forever — this is "the clock that makes the engine anticipatory." A tick exception is logged to glassbox and the loop survives (`main.py:89`).

2. **Inbound SMS poller** — `_inbound_scheduler(InboundPoller(core), inbound_s)` (`main.py:93-101, 112-114`). **Env-gated and live-gated**: created only if `ANTICIPY_INBOUND_POLL_SECONDS > 0` (default `"15"`) **AND** `InboundPoller.live_ready()` is true (`inbound.py:81`) — i.e. real Twilio creds + live channel mode. The deterministic suite, stub, and mock runs never construct a transport, so this task does not exist there. On *this* running engine it **is** active: live `/status` shows `"inbound":{"status":"live_ready",...,"poll_seconds":15.0}`. It polls Twilio for owner SMS replies (YES/NO resolves asks; speech ingests).

**Who talks to :8787 (inbound):**
- **Next.js server (`:3000`)** — proxies browser/app requests to the engine via `app/api/_engine.js:1`: `ENGINE_URL = process.env.ANTICIPY_ENGINE_URL || "http://127.0.0.1:8787"`. `boot.sh:23` starts Next with `ANTICIPY_ENGINE_URL=http://127.0.0.1:8787`.
- **Chrome extension** — opens an authenticated WebSocket to `/ws/extension` (`main.py:1422`), gated by a token (`core.browser_link.check_token`, `main.py:1424`). This is the live `127.0.0.1:57301->8787` ESTABLISHED connection.
- **Swift menubar app** — polls `http://127.0.0.1:8787/glassbox?limit=40` (`macapp/Sources/AnticipyApp/MainView.swift:20`) and uses `base = "http://127.0.0.1:8787"` for actions (`MainView.swift:50`).
- **Twilio (external)** — on a public deploy, attaches to the `/cr` WebSocket (ConversationRelay voice loop, `main.py:1335`) and the inbound webhook surface. Authenticated by Twilio request-signature or owner token (`_owner_ws_authorized`, `main.py:208`). Not reachable on this loopback-only local bind without a tunnel.

**What :8787 talks to (outbound):**
- **OpenRouter** (the model gateway) — `core.gateway` and `gateway_agent` (`main.py:75-79`), provider `PROVIDER_OPENROUTER` (per the brief, overridden to gemini models via `.env.local`). External HTTPS.
- **Arcade** — the per-person API mesh (Gmail/Calendar/Slack/Docs) via `core.api_hand`. Live `/readiness` shows `google_arcade: live`.
- **Twilio REST** — outbound SMS/voice via `channels/`. Live (`channels.mode:"live"`).
- **The native bridge on `:7777`** and **Chrome CDP on `:9222`** — for the browser arm (see §3.3, §3.4).

---

## 3.2 The Next.js web app — `:3000` (PID 22303)

| | |
|---|---|
| **Runtime** | Node.js — `next-server (v15.5.19)`, the **production** Next.js server (`next start`, not `next dev`) |
| **Entry / source** | `app/` (Next.js app dir). API routes proxy to the engine through `app/api/_engine.js` |
| **Launch chain** | `boot.sh:23` → `npm start` (PID 22285) → `next-server` (PID 22303). The live `ps` PPID chain confirms this: `22303 ← 22285 (npm start) ← 22283`. |
| **Bind** | `*:3000` (IPv6 wildcard per `lsof`; reachable as `127.0.0.1:3000`). Live check returns **HTTP 200**. |
| **Protocol** | HTTP/1.1 (serves the owner UI + Next.js API routes) |

**How it is launched** (`macapp/Resources/boot.sh:20-24`), again idempotent:

```bash
# macapp/Resources/boot.sh:21
if ! curl -s -m2 http://127.0.0.1:3000 >/dev/null 2>&1; then
  [ -f "$REPO/.next/BUILD_ID" ] || ANTICIPY_ENGINE_URL=http://127.0.0.1:8787 npm run build >/tmp/anticipy_web_build.log 2>&1
  ANTICIPY_ENGINE_URL=http://127.0.0.1:8787 nohup npm start >/tmp/anticipy_web.log 2>&1 &
fi
```

The comment at `boot.sh:20` is explicit that this is the **production** server ("PRODUCTION server (stable; no dev hot-reload cache corruption)"), which matches the live `next-server` process name (a `next dev` instance would also appear as `next-server`, but the launcher uses `npm start`).

- **Who talks to :3000:** the Swift app's embedded WebView points at `http://127.0.0.1:3000` (`macapp/Sources/AnticipyApp/WebApp.swift:12`, `UI_URL`), and any local browser the owner opens.
- **What :3000 talks to:** the engine at `:8787` only, via `_engine.js` (`fetch(url, ...)`, `_engine.js:99`). `_engine.js:34` restricts the proxy target host to loopback (`localhost`/`127.0.0.1`/`::1`) — it will not proxy to an arbitrary host.

---

## 3.3 The native bridge — `127.0.0.1:7777` (PID 8862) — NOT in the brief's port list, found live

This is a real, running process the audit brief's port enumeration did not pre-list. It is the browser arm's HTTP-over-loopback transport to Chrome.

| | |
|---|---|
| **Runtime** | CPython at `/Users/omarebrahim/.anticipy/venv/bin/python` (a *separate* venv from the engine's) |
| **Script** | `/Users/omarebrahim/.anticipy/anticipy-bridge.py` (installed under `~/.anticipy/`, outside the repo) |
| **Bind** | `127.0.0.1:7777` — `HOST=ANTICIPY_TRIGGER_HOST` default `127.0.0.1`, `PORT=ANTICIPY_TRIGGER_PORT` default `7777` (bridge script lines 75-79); served via an async `server.serve_forever()` (line 1266) |
| **Protocol** | HTTP/1.1 JSON: `GET /status`, `POST /surface-proof`, `POST /surface-command` (bridge docstring line 6; engine adapter calls these at `native_bridge_link.py:783, 901, 1078`) |

**How it is launched.** The engine *autostarts* it on demand. `NativeBridgeLink._start_bridge_once()` (`native_bridge_link.py:795-815`) spawns it as a detached subprocess:

```python
# native_bridge_link.py:801-813
script = Path(os.environ.get("ANTICIPY_NATIVE_BRIDGE_SCRIPT",
                             "~/.anticipy/anticipy-bridge.py")).expanduser()
py = Path.home() / ".anticipy" / "venv" / "bin" / "python"
self._started_process = subprocess.Popen([exe, str(script)],
    stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL, start_new_session=True)
```

The autostart is gated by `ANTICIPY_NATIVE_BRIDGE_AUTOSTART` (default true, `native_bridge_link.py:259`). The running PID 8862 has `PPID 1` (the `start_new_session=True` detaches it and it re-parents to launchd). It is wired into `ControlCore` at `control_core.py:193-196` (`self.native_bridge_link = NativeBridgeLink()`), so it is one of the engine's two browser transports.

- **Who talks to :7777:** the engine process (`:8787`) only, via `NativeBridgeLink._request_json()` (`native_bridge_link.py:1080`), reaching `http://127.0.0.1:7777`.
- **What :7777 talks to:** Chrome's CDP endpoint on `:9222` — the bridge docstring (lines 11-14) says it probes `http://localhost:9222/json/version` on startup and, if absent, launches Chrome with `--remote-debugging-port=9222 --remote-allow-origins=http://localhost:*`. So the bridge is *also* a launcher of the §3.4 Chrome process.

A subtlety worth recording: the engine has **two independent paths to Chrome CDP**. (1) The native bridge (`:7777`) proxies to CDP. (2) `NativeBridgeLink` *also* attaches to CDP `:9222` **directly** (bypassing the bridge) for proof/click/scroll — `_direct_cdp_proof_async`, `_trusted_cdp_click_async`, `_direct_cdp_scroll_async` open `ws://localhost:9222/devtools/...` themselves (`native_bridge_link.py:438, 910, 581`), each gated by a `_bool_env` flag (`ANTICIPY_NATIVE_BRIDGE_DIRECT_CDP_PROOF`/`..._TRUSTED_CLICK`/`..._DIRECT_CDP_SCROLL`, all default true). So the bridge is partly a fallback/launcher and partly bypassed by the engine's own direct CDP calls.

---

## 3.4 Chrome with CDP — `127.0.0.1:9222` (PID 8835)

| | |
|---|---|
| **Runtime** | Google Chrome 149.0.7827.103 (confirmed via live `GET /json/version`) |
| **Bind** | `127.0.0.1:9222` (loopback) — the DevTools/CDP remote-debugging endpoint |
| **Protocol** | Chrome DevTools Protocol: HTTP discovery (`/json/version`, `/json/list`) + per-target WebSockets (`ws://127.0.0.1:9222/devtools/...`) |
| **Profile** | `--user-data-dir=/Users/omarebrahim/.anticipy/chrome-real-clone --profile-directory=Default` — a dedicated cloned profile, **not** the user's primary Chrome data dir |

**How it is launched.** Two code paths can start this exact command line, and both match the live `ps` flags character-for-character:
1. The native bridge script (per its docstring, lines 11-14), when it finds `:9222` not responding at startup.
2. The engine's `NativeBridgeLink._ensure_cdp_chrome()` (`native_bridge_link.py:817-857`), gated by `ANTICIPY_NATIVE_BRIDGE_CDP_AUTOSTART` (default true). It builds the identical argv (`native_bridge_link.py:836-845`):

```python
[chrome, f"--remote-debugging-port={self.cdp_port}",   # 9222
 "--remote-allow-origins=http://localhost:*",
 f"--user-data-dir={user_data}",                       # ~/.anticipy/chrome-real-clone
 "--profile-directory=Default", "--no-first-run",
 "--no-default-browser-check", "--disable-features=Translate"]
```

The user-data dir defaults to `~/.anticipy/chrome-real-clone` (`native_bridge_link.py:888`), the CDP port to `ANTICIPY_CDP_PORT` default `9222` (`native_bridge_link.py:238`). The running PID 8835 has `PPID 1` (detached `start_new_session=True`). There is also a `com.anticipy.chrome.plist` launch agent in `~/Library/LaunchAgents/` that may alternatively own it — I cannot determine from code alone which of the three actually started *this* PID, only that they all produce the same argv.

**Who attaches to :9222:**
- The **native bridge** (`:7777`) for CDP-backed commands (its docstring, lines 11-14, 42).
- The **engine** (`:8787`) directly, via `NativeBridgeLink`'s direct-CDP methods (§3.3) — it GETs `http://localhost:9222/json/list` (`native_bridge_link.py:438`) to pick a page target, then opens a CDP WebSocket to drive `Input.dispatchMouseEvent`, `Runtime.evaluate`, `Page.captureScreenshot`, etc.
- The **browser-use vision agent** (`/agent/act`, `main.py:1214`) when invoked with `cdp_url` — it ATTACHES to this already-running Chrome instead of a throwaway browser (`browser_use_link.py:151-160`). A hard guard restricts `cdp_url` to loopback only (`_cdp_is_loopback`, `browser_use_link.py:54-57`), and a **money hard-stop** *refuses to run ACTIONS* in this logged-in Chrome over CDP (`browser_use_link.py:209-213`) — read-only there; actions go to a throwaway browser.

---

## 3.5 The other (non-product) processes seen in `lsof`

For completeness, the remaining listeners in the live capture are **macOS / dev infrastructure, not Anticipy runtime**:
- `rapportd` `:49152/:58749/:58750`, `ControlCe` (Control Center / AirPlay) `:7000/:5000` — macOS system services, unrelated to this stack.

And one launch agent is active but separate from the four runtime processes: `launchctl list` shows `com.anticipy.factory` loaded — that is the **nightly build/forcing Factory** (`factory/bin/loop.sh --nightly`), a build-time system, **not** a runtime product process. It spawns bounded builder sessions on a schedule; it does not serve any port in this capture.

---

## 3.6 Runtime process graph (ASCII)

```
 EXTERNAL                          LOCAL MACHINE (all binds 127.0.0.1 / loopback)
 ────────                          ───────────────────────────────────────────────

                          ┌──────────────────────────────────────────────────────┐
                          │  macOS launchd / Swift menubar app (macapp/)           │
                          │  -> runs macapp/Resources/boot.sh (idempotent)         │
                          └───────────────┬───────────────────────┬───────────────┘
                                          │ starts (if down)       │ starts (if down)
                                          v                        v
                       ┌─────────────────────────┐     ┌──────────────────────────┐
   Swift WebView ─────>│  Next.js  next-server    │     │  FastAPI ENGINE          │
   (WebApp.swift)      │  Node 15.5.19            │     │  uvicorn anticipy_engine │
   browser  ─────────> │  PID 22303  *:3000       │     │   .main:app              │
                       │  npm start (PID 22285)   │     │  python  PID 66506       │
                       │                          │     │  127.0.0.1:8787          │
                       │  app/api/_engine.js      │────>│  HTTP REST + WS          │
                       │  ANTICIPY_ENGINE_URL ----│ ───>│                          │
                       └─────────────────────────┘ HTTP│  lifespan asyncio tasks: │
                                                        │   * tick scheduler       │
   Twilio (voice/SMS) ··· WS /cr, inbound webhook ·····>│     (ANTICIPY_TICK_SECONDS>0)
   [only on public deploy; not                          │   * inbound SMS poller   │
    reachable on this loopback bind]                    │     (live+env-gated;     │
                                                        │      RUNNING here)       │
   Chrome EXTENSION ── WS /ws/extension (token) ───────>│                          │
   (live 57301->8787)                                   │  outbound:               │
                                                        │   OpenRouter (models)    │
                                                        │   Arcade (Gmail/Cal/...) │──> external HTTPS
                                                        │   Twilio REST            │
                                                        └───────┬───────────┬──────┘
                                                                │           │ direct CDP
                                            HTTP /surface-* JSON│           │ (ws + /json/list)
                                                                v           │
                                              ┌─────────────────────────┐   │
                                              │ NATIVE BRIDGE            │   │
                                              │ python ~/.anticipy/      │   │
                                              │   anticipy-bridge.py     │   │
                                              │ PID 8862  127.0.0.1:7777 │   │
                                              │ (engine autostarts it;   │   │
                                              │  separate ~/.anticipy    │   │
                                              │  venv)                   │   │
                                              └───────────┬──────────────┘   │
                                                          │ CDP              │
                                                          v                  v
                                              ┌──────────────────────────────────┐
                                              │ GOOGLE CHROME (CDP)                │
                                              │ PID 8835  127.0.0.1:9222           │
                                              │ --remote-debugging-port=9222       │
                                              │ profile: ~/.anticipy/              │
                                              │          chrome-real-clone         │
                                              │ (bridge OR engine autostarts it)   │
                                              └────────────────────────────────────┘

   browser-use agent (/agent/act, in-engine) ── attaches to :9222 via cdp_url
        (loopback-only guard; ACTIONS refused over cdp_url — money hard stop)

   ╳ NO :3424 anywhere (verified: lsof grep ':3424' -> empty). Ports in use: 8787, 3000, 9222, 7777.
```

## 3.7 Summary table

| Port | PID | Process | File that starts it | Runtime | Protocol | Talks to | Talked to by | Conditional? |
|------|-----|---------|---------------------|---------|----------|----------|--------------|--------------|
| **8787** | 66506 | FastAPI engine (`anticipy_engine.main:app`) | `macapp/Resources/boot.sh:14-18` (also watchdog/launch agent) | CPython + Uvicorn | HTTP REST + WS (loopback) | OpenRouter, Arcade, Twilio, bridge `:7777`, Chrome CDP `:9222` | Next.js `:3000`, Chrome extension (WS), Swift app, Twilio (`/cr`, public only) | Always (the hub) |
| **3000** | 22303 | Next.js `next-server` | `boot.sh:20-24` → `npm start` | Node 15.5.19 | HTTP | engine `:8787` only (loopback-restricted proxy) | Swift WebView, local browser | Always |
| **9222** | 8835 | Google Chrome (CDP) | `native_bridge_link.py:836-845` `_ensure_cdp_chrome()` OR the bridge script | Chrome 149 | CDP (HTTP + WS) | (driven target) | bridge `:7777`, engine direct-CDP, browser-use agent | Autostart gated by `ANTICIPY_NATIVE_BRIDGE_CDP_AUTOSTART` (default on) |
| **7777** | 8862 | Native bridge `anticipy-bridge.py` | `native_bridge_link.py:795-815` `_start_bridge_once()` | CPython (`~/.anticipy/venv`) | HTTP JSON (`/status`,`/surface-proof`,`/surface-command`) | Chrome CDP `:9222` | engine `:8787` (`NativeBridgeLink`) | Autostart gated by `ANTICIPY_NATIVE_BRIDGE_AUTOSTART` (default on) |
| ~~3424~~ | — | **does not exist** | — | — | — | — | — | Never present |

**In-process (not separate PIDs):** the **tick scheduler** and **inbound SMS poller** are asyncio tasks created in the engine's FastAPI `lifespan` (`main.py:104-123`). Tick is gated by `ANTICIPY_TICK_SECONDS>0` (default 30s). Inbound poll is gated by `ANTICIPY_INBOUND_POLL_SECONDS>0` (default 15s) **and** `InboundPoller.live_ready()` (live Twilio creds) — confirmed running here by live `/status`: `"inbound":{"status":"live_ready","poll_seconds":15.0}`.

---

# SECTION 4: THE ACTION ENGINE — INTERNALS

This is the heart of the running stack: a Python 3.10 FastAPI engine on `127.0.0.1:8787` (confirmed live: `lsof` shows `python3.1 66506 ... TCP 127.0.0.1:8787 (LISTEN)`, process `engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787`). Everything below is read from source at the cited `file:line`.

**Up front — the user's stack description does not match this repo.** There is no "DeepSeek V4 Flash", no "Kimi K2.6", no "Ralph Loop", no Tauri, no Deepgram, no port 3424 in this codebase. The real brain calls **OpenRouter** (default `openai/gpt-4o`/`gpt-4o-mini`, configured to **Google Gemini** in `.env.local`), and the closest thing to a "Ralph loop" is the **WebVoyager observe→decide→act Task-State Controller** (`agent/webvoyager.py`) plus the **browser-use** vision agent. I name each real component with evidence as I go.

---

## 4a. Brain stack — which models, called how

### The single entry point: `ModelGateway.think()`

All model calls funnel through one gateway: `engine/anticipy_engine/core/gateway.py`. Signature (`gateway.py:113`):

```python
async def think(self, task: str, tier: str, caller: str, image: Optional[str] = None,
                json_mode: bool = False, temperature: Optional[float] = None,
                max_tokens: Optional[int] = None) -> str:
```

**Call pattern is single-shot text-in / text-out** (returns a `str`; callers parse JSON themselves). There is no streaming, no tool-calling/function-calling API, no multi-turn message array — `think()` builds a one-message body `{"role":"user","content": ...}` (`gateway.py:151`). Vision is supported by passing `image=` (a data-URL or http URL), which switches `content` to the OpenAI multimodal array `[{type:text},{type:image_url}]` (`gateway.py:141-144`).

**Tiers (the cost ladder).** Two tiers, `CHEAP="cheap"` / `SMART="smart"`, with a notional cost table `COST = {CHEAP: 0.0005, SMART: 0.02}` (`gateway.py:21-23`). The model chosen per call (`gateway.py:140`):

```python
model = self.smart_model if tier == SMART else self.cheap_model
```

**SMART is access-controlled.** Only three callers may request SMART (`gateway.py:91-92`, enforced `gateway.py:116-117`):

```python
SMART_CALLERS = frozenset({"gate", "plan", "agent"})
...
if tier == SMART and caller not in self.SMART_CALLERS:
    raise PermissionError(f"smart tier not allowed from caller '{caller}'")
```

So `decider` (the act/ask/silent verdict) and other callers are CHEAP-only by construction; the web-agent (`agent`), the proactive gate (`gate`), and the orchestrator planner (`plan`) may escalate.

**Provider precedence** (`gateway.py:98`): explicit arg → `ANTICIPY_MODEL_PROVIDER` env → `"stub"` (default). The default is a deterministic in-process stub (`default_stub`, `gateway.py:318-397`) that keyword-matches the prompt to produce gate/decider/plan JSON with zero network — this is what keeps the test suite free and reproducible. The real provider is **OpenRouter** (`PROVIDER_OPENROUTER="openrouter"`, `gateway.py:26`), an OpenAI-compatible chat-completions endpoint.

### Which models actually run

**Default models in code** (`gateway.py:101-102`):
```python
self.cheap_model = ... or "openai/gpt-4o-mini"
self.smart_model = ... or "openai/gpt-4o"
```

**The web-agent's own gateway** is constructed separately in `main.py:75-79` (kept apart from the core gateway so engine/hands tests stay deterministic):
```python
gateway_agent = ModelGateway(
    provider=PROVIDER_OPENROUTER,
    cheap_model="google/gemini-3.1-flash-lite",   # routine see-and-locate steps
    smart_model="google/gemini-3.5-flash",        # planning / recovery / stuck / judge
)
```

**Live override in `.env.local`** (read verbatim, keys redacted) — this is what the running engine uses:
```
ANTICIPY_MODEL_PROVIDER=openrouter
ANTICIPY_OPENAI_BASE_URL=https://openrouter.ai/api/v1/chat/completions
ANTICIPY_MODEL_CHEAP=google/gemini-2.5-flash-lite
ANTICIPY_MODEL_SMART=google/gemini-2.5-flash
```

I cannot reconcile the exact Gemini version from code alone: `main.py` hardcodes `gemini-3.1-flash-lite`/`gemini-3.5-flash` for the agent gateway, while `.env.local` sets `gemini-2.5-flash-lite`/`gemini-2.5-flash`. Note that `main.py`'s `gateway_agent` is built with literals, so `ANTICIPY_MODEL_CHEAP/SMART` env vars do **not** override the agent gateway — only the *core* gateway (built inside `ControlCore`) reads those env vars (`gateway.py:101-102`). The browser-use runner has its own default `google/gemini-2.5-flash` (`browser_use_runner.py:39`) and reads `ANTICIPY_MODEL_SMART` (`browser_use_runner.py:194-197`). **Net: the live brain is Google Gemini Flash served through OpenRouter — never DeepSeek/Kimi.**

### Where the API key is read (env name only)

`gateway.py:109-110`:
```python
self._key = (os.environ.get("ANTICIPY_MODEL_API_KEY")
             or os.environ.get("OPENROUTER_API_KEY"))
```
If unset, `_openrouter()` raises `RuntimeError("no model API key: set ANTICIPY_MODEL_API_KEY (or OPENROUTER_API_KEY)")` (`gateway.py:136-137`). The browser-use runner reads `OPENROUTER_API_KEY` from env or `.env.local` (`browser_use_runner.py:184`). I did not read any secret value.

### Retry / rate-limit / caching logic

This is the most engineered part of the gateway — built around a starved free-tier brain (the comments call it out explicitly, `gateway.py:29-38`). There is **no caching** anywhere; every `think()` is a fresh HTTP POST.

`_openrouter()` runs **up to 4 attempts** (`gateway.py:166`):
- **429**: calls `_retry_hint_seconds(resp)` (`gateway.py:44-87`) which mines the server's own stated wait, in priority order: the `Retry-After` header → Gemini's `google.rpc.RetryInfo.retryDelay` proto Duration (handling the OpenAI-compat one-element-array wrapper, `gateway.py:61-62`) → a "retry in Ns" phrase in the message. If the hint ≤ `RETRY_HINT_INLINE_CAP_S = 8.0` (`gateway.py:39`), it sleeps `hint + 0.25` margin and retries inline; if longer, it **returns `""` immediately** so the caller's UNAVAILABLE→defer path owns the wait rather than burning quota (`gateway.py:171-179`). No hint → blind backoff `1.5*(attempt+1)`.
- **5xx** (500/502/503/504): blind backoff, retry (`gateway.py:181-183`).
- **Empty content** (provider intermittently returns empty under load): brief backoff `1.0*(attempt+1)`, retry (`gateway.py:185-189`).
- **Transport/HTTPStatus errors**: backoff, retry (`gateway.py:190-191`).

`json_mode=True` sets `response_format={"type":"json_object"}` (`gateway.py:152-153`); `temperature` and `max_tokens` (or `ANTICIPY_MODEL_MAX_TOKENS`) are passed through when present (`gateway.py:154-158`). Every call is appended to `self.calls` with tier/caller/cost (`gateway.py:118`), and 429 hints get stamped onto the call record for postmortems (`gateway.py:174`). `total_cost()` (`gateway.py:130-131`) sums the notional cost table — this is a **synthetic accounting number, not real billing.**

### Who calls SMART vs CHEAP (the cost discipline in practice)

- **Orchestrator planner** → `caller="plan"`, SMART, `json_mode=True`, with **one bounded re-ask** if the plan JSON won't parse (`orchestrator.py:458-465`).
- **WebVoyager per-step decider** → `caller="agent"`, **CHEAP by default, escalates to SMART only when stuck** (`webvoyager.py:2181-2182`): `escalate = (sub_stuck >= 1) or (forbid is not None)`. The plan/reflect/judge calls are always SMART.
- **Proactive gate** → `caller="gate"` (SMART-eligible). **Decider** → `caller="decider"` (CHEAP-only by the `SMART_CALLERS` rule).

---

## 4b. The browser stack — how Chrome is reached

There are **TWO transports** and **TWO agent loops**, wired together. Confirmed running: `lsof` shows Google Chrome listening on `127.0.0.1:9222` with `--user-data-dir=/Users/omarebrahim/.anticipy/chrome-real-clone --remote-debugging-port=9222`.

```
                          ┌─────────────────────────────────────────────┐
   /agent/run  ──────────▶│ WebVoyagerAgent  (agent/webvoyager.py)      │
   /agent/resume          │  observe → decide → act  Task-State loop    │
                          └───────────────┬─────────────────────────────┘
                                          │ send_browse(intent, args)
                                          ▼
                 ┌────────────────────────────────────────────┐
                 │ TRANSPORT (duck-typed BrowserLink iface)    │
                 ├──────────────────────┬─────────────────────┤
                 │ (a) BrowserLink WS    │ (b) NativeBridgeLink │
                 │ core/browser_link.py  │ core/native_bridge_  │
                 │ extension over        │     link.py          │
                 │ /ws/extension         │ HTTP :7777 + CDP     │
                 │                       │ direct on :9222      │
                 └──────────┬────────────┴──────────┬──────────┘
                            ▼                        ▼
                  Chrome extension          Chrome --remote-debugging-port=9222
                  (extension/)              (CDP WebSocket: Input.dispatch*, 
                                             Runtime.evaluate, Page.captureScreenshot)

   /agent/act  ──────────▶ browser-use vision agent (SEPARATE 3.11 process)
                           hands/browser_use_link.py → browser_use_runner.py
                           throwaway Chromium OR cdp_url attach (reads only)
```

### (a) The connected extension over WebSocket — `core/browser_link.py`

`BrowserLink` owns a per-session token (`secrets.token_urlsafe(24)`, `browser_link.py:36`) and the single extension WS. The extension connects to `/ws/extension` presenting that token; `check_token` uses `secrets.compare_digest` (`browser_link.py:42-43`), and the route rejects a bad token (`main.py:1424`). One connection at a time, last-writer-wins (`attach`, `browser_link.py:46-52`).

Jobs are dispatched via `send_browse(job_id, intent, args, timeout)` (`browser_link.py:72-103`): it correlates the result by `job_id` through an `asyncio.Future` in `self._pending`, sends `{"type":"browse_job", ...}` over the socket, and awaits with timeout. The **hard navigation wall** runs *here at the transport* (so it covers both transports' callers): `_walled_nav_url` (`browser_link.py:17-31`) extracts the target URL from any navigating intent (`observe`/`navigate`/`read_page`/`browse_task`/`prepare_form`), and `nav_block_reason` (DNS-bounded, run off the event loop, `browser_link.py:84-85`) denies private/metadata/non-http(s)/banking hosts **before** the job reaches Chrome (`browser_link.py:79-93`).

### (b) The native bridge + CDP `:9222` — `core/native_bridge_link.py`

This is a duck-typed `BrowserLink` replacement (same `send_browse` contract, `native_bridge_link.py:282`) used **when the extension socket is not connected**. It speaks two things: a local HTTP bridge on `127.0.0.1:7777` (`ANTICIPY_TRIGGER_PORT`, `native_bridge_link.py:233`) and, increasingly, **CDP directly on `:9222`**.

**How CDP `:9222` is attached:**
- `_ensure_cdp_chrome()` (`native_bridge_link.py:817-857`) auto-starts Chrome if `:9222` isn't up: it launches `/Applications/Google Chrome.app/.../Google Chrome` with `--remote-debugging-port=9222 --remote-allow-origins=http://localhost:* --user-data-dir=~/.anticipy/chrome-real-clone --profile-directory=Default` (`native_bridge_link.py:835-845`). `_cdp_up()` probes `http://localhost:9222/json/version` (`native_bridge_link.py:859-867`). **This exactly matches the live process** seen in `ps`.
- `_cdp_page_ws_url()` (`native_bridge_link.py:436-455`) GETs `http://localhost:9222/json/list`, picks the page target (by tracked `_cdp_target_id`, else by URL prefix, else last page), and returns its `webSocketDebuggerUrl`.

**observe / act over CDP:**
- `_observe` (`native_bridge_link.py:316-361`) navigates (with the same `nav_block_reason` wall, `native_bridge_link.py:326-328`) then calls `_proof()`. `_direct_cdp_proof_async` (`native_bridge_link.py:920-1071`) opens a CDP WebSocket and runs `Runtime.evaluate` to (1) read `location.href`/`document.title`, (2) execute a large in-page snapshot script that builds a **set-of-marks** element list — actionable elements (`a,button,input,[role=button]...`), visibility-filtered, priority-ranked (in-view > "add to cart"-ish > product-ish > search-ish), tagged with `data-anticipy-native-idx` attributes for stable selectors (`native_bridge_link.py:947-1031`) — plus (3) `document.documentElement.outerHTML` and (4) `Page.captureScreenshot` (PNG → data-URL). So the agent gets URL+title+text+element-list+screenshot per observe.
- `_act` (`native_bridge_link.py:363-417`) supports `navigate` / `scroll` / `click` / `type`. Clicks use `_trusted_cdp_click_async` (`native_bridge_link.py:457-572`): it re-finds the element in-page (re-validating role/name/href so a shifted DOM doesn't mis-click), scrolls it into view, computes center coords, and dispatches a **real trusted mouse gesture** via `Input.dispatchMouseEvent` (mouseMoved→mousePressed→mouseReleased), with a JS `.click()` fallback (`native_bridge_link.py:545-570`). Scroll uses `Input.dispatchMouseEvent` mouseWheel with JS fallbacks (`native_bridge_link.py:591-667`).

`fresh_probe()` (`native_bridge_link.py:268-280`) returns an independent observer sharing the same Chrome/CDP but with no cached selectors/target — this is what powers the **independent cart read-back** (so the proof doesn't depend on the agent's own tab state).

### The plan/observe/act loop — what it's actually called (NOT "Ralph Loop")

The bespoke loop is **`WebVoyagerAgent` — "a Task-State Controller around observe → decide → act"** (`webvoyager.py:1`, class at `webvoyager.py:1388`). There is no "Ralph Loop" by that name anywhere (git grep: 0 hits). Its documented machinery (`webvoyager.py:4-15`):

- **PLAN** (`_plan`, `webvoyager.py:1491-1502`): SMART model writes a 3–6 subgoal checklist (`PLAN_SYS`, `webvoyager.py:34-36`); for a remembered-item cart task it uses a fixed 4-subgoal plan.
- **The main loop** (`run`, `webvoyager.py:2118-2297`): up to `max_steps` (default 28). Each step: observe (`_observe_ready` re-looks until the page is actionable, `webvoyager.py:1413-1428`), build the per-step prompt (`_build_act_prompt`, `webvoyager.py:255-301`), call the model (CHEAP→SMART escalation, `webvoyager.py:2183`), parse one JSON action `{action: click|type|scroll|navigate|answer, index, text, ...}`, then `_act`.
- **PROGRESS labeling** (`webvoyager.py:2259-2266`): a page-signature diff labels each act `PROGRESS` / `NO_CHANGE` / `REGRESSION`.
- **ANTI-LOOP / COMMIT** (`webvoyager.py:2277-2295`): on `NO_CHANGE`/`REGRESSION`, increment `sub_stuck`, **forbid the repeated (action,index)** next step, run a one-line `_reflect` (SMART). 3 stuck or per-subgoal budget exceeded → fail the subgoal. Once a target is chosen it's `committed` so it won't re-pick.
- **Handoff** on a wall (`_handoff`, `webvoyager.py:1597-1603`): pause → text the human → return `needs_human/paused` with a `resume_token`; never types passwords or solves captchas (`agent/handoff.py`).

There is also a deterministic **commerce recipe** (`_try_commerce_recipe`, `webvoyager.py:1605-2116`) that runs *before* the general loop for "find X and add to cart" tasks — a ~500-line search→product→add→**durable cart read-back** state machine that falls through to the general loop (`return None`) when it can't find a product.

### The money / checkout HARD STOP guards

Money is the cardinal hard stop, and there are **multiple defense-in-depth layers**:

1. **`PURCHASE_GUARD` regex** (`webvoyager.py:68-82`) — blocks clicks on final-pay *labels*: "place order", "buy now", "complete purchase", "pay now", "Pay $\d", "submit order/payment", "confirm order/payment", "place bid", etc. Deliberately **excludes** bare "submit"/"checkout" and all cart/nav controls so legit add-to-cart works (tested in `engine/scripts/test_purchase_guard.py`). Enforced at click time (`webvoyager.py:2236-2241`) and inside `_pick_button`/`_pick_add_button` (`webvoyager.py:808, 878`).
2. **`CHECKOUT_URL_RE` context guard** (`webvoyager.py:88-97`) — the stronger, label-independent stop. Before **any** money-capable action (`click`/`type`/`navigate`/`submit`), if the current URL **or** the navigate target is a checkout/payment/order-submit URL, the agent stops and parks for the human (`webvoyager.py:2228-2234`): *"STOPPED at a checkout/payment page — did NOT place the order or pay."* This closes the type+enter-submit, navigate-to-pay, out-of-list-index, and generic-label holes the label guard misses.
3. **browser-use (`/agent/act`) action guard** — for the throwaway-browser action agent, money is a **prompt-level** hard stop (`_ACTION_GUARD`, `browser_use_runner.py:61-68`): "do NOT place an order, pay, check out, or enter any payment/card details... Money is the hard stop."
4. **The critical money backstop on the CDP path** — because the browser-use action guard is *only a prompt*, actions are **refused entirely when attached to the logged-in Chrome** (`cdp_url`). This is enforced **twice**: in the engine client (`browser_use_link.py:209-214`) and again in the runner (defense-in-depth, also catching the `ANTICIPY_BROWSERUSE_CDP_URL` env backdoor, `browser_use_runner.py:205-214`). Reads may attach; **actions run only on a throwaway browser with no saved cards** — so money cannot be spent even if the model misbehaves. The comment is explicit (`browser_use_link.py:201-208`): *"no code-level money guard there yet — money is the hard stop."*

### OAuth / popup / wall handling

No automated OAuth — by design. On a login/captcha/anti-bot wall the agent **does not auth itself**: `BLOCK_MARKERS` (`webvoyager.py:98-100`) and `LOGIN_URL_RE` (`webvoyager.py:101`) detect the wall, `classify_wall` (`handoff.py:31-38`) categorizes it (captcha/login/block), and `_handoff` pauses, texts the user `ask_message` (`handoff.py:41-53`), and stops observing so it never screenshots what the user types (`webvoyager.py:1597-1603`). Resume is a stub seam (`/agent/resume`, `main.py:1270-1287`) — it re-runs from the now-unblocked URL; exact mid-plan state restoration is an acknowledged TODO (`main.py:1276-1278`).

### The third arm: browser-use vision agent — `hands/browser_use_link.py` + `browser_use_runner.py`

`/agent/act` (`main.py:1214-1234`) drives the **MIT open-source `browser-use` 0.13.1** agent in a **separate Python 3.11 subprocess** (the engine is 3.10; browser-use needs ≥3.11, so they never share an interpreter — `browser_use_link.py:1-11`). The engine shells out (`subprocess.run` with a hard timeout, `browser_use_link.py:229-236`), passing one JSON line on stdin and parsing one sentinel-tagged JSON line back (`__ANTICIPY_BU_RESULT__`, `browser_use_link.py:42, 130-142`). The runner builds a `browser_use.Agent` with `use_vision=True` for actions (`browser_use_runner.py:288-296`), a throwaway temp Chromium profile (`browser_use_runner.py:251-270`) or a CDP attach, a host-scoped navigation wall via `allowed_domains` (`browser_use_runner.py:129-163`), and a prompt-injection fence (`_INJECTION_GUARD`, `browser_use_runner.py:78-88`). Honest-by-construction: `success` mirrors browser-use's own `is_done()` AND a non-empty result; any blocker → `success=False` with a clear `error`, never a faked success (`browser_use_runner.py:313-323`; `browser_use_link.py:268-269`).

---

## 4c. Task lifecycle — from "task arrives" to "completes / fails"

### The objects (in memory and on disk)

`core/envelopes.py` defines the frozen contract:
- **`Job`** (`envelopes.py:78-83`): a transient bus message `{intent, args, risk, goal_id}`.
- **`Result`** (`envelopes.py:86-95`): `{job_id, status∈{success,failed,needs_human}, output, proof, cost, error}`. **`proof` is the load-bearing field** — "On success this MUST be present and truthy" (`envelopes.py:91-93`).
- **`Step`** (`envelopes.py:99-105`): `{intent, args, risk, state, attempts, result}` — the orchestrator's unit.
- **`Goal`** (`envelopes.py:108-119`): the **persisted** unit `{id, intent, description, steps[], state∈{planning,running,waiting,done,failed}, proof, created_at, updated_at}`.

There is no separate "card"/"job" object in this module; the **owner CARD** is a higher-level construct persisted under `.anticipy-data/owner_cards/` (33 entries on disk) and surfaced via glassbox `owner_card_resolved` summaries (`glassbox.py:101-103`) — out of scope for the orchestrator's step machine but part of the same data dir.

### The control loop — `core/orchestrator.py` ("the boss")

`start_goal` (`orchestrator.py:448-478`):
1. Set `planning`, persist, log `goal_planning`.
2. Pull memory context (if a `memory_context` callable is wired, `orchestrator.py:454`).
3. **Deterministic plan first** (`_deterministic_plan`, `orchestrator.py:576-593`): tries slot-booking, note-task, fully-grounded calendar event (`_calendar_event_step`, `orchestrator.py:167-212`), then memory-resolved browser step (`_memory_resolved_browser_step`, `orchestrator.py:352-404`). If none match → fall to the model planner (SMART, `json_mode`, **one bounded re-ask** on bad JSON, `orchestrator.py:458-465`).
4. Empty plan → `failed`, record, return (`orchestrator.py:467-473`).
5. Else `running` → `_drive`.

`_drive` (`orchestrator.py:488-509`): iterates steps, **persisting after EVERY step** (`orchestrator.py:495`) so a restart resumes (already-`done` steps are skipped, `orchestrator.py:492`). On a step that ends `needs_human` → goal `waiting`; `failed` → goal `failed`; both return early. All steps verified → collect per-step proof into `goal.proof` (`orchestrator.py:503`), set `done`, log `goal_done`.

`_run_step` (`orchestrator.py:511-531`): high-risk steps (`needs_confirm`/`ask_human`) go through `self.approver.approve()` first (`orchestrator.py:513-518`). Then `_dispatch_with_retry` (`max_retries=2`, `orchestrator.py:533-553`): submit the `Job` on the bus, and on `success` require `_verify(result)`; `needs_human` short-circuits (rerouting wouldn't help); a `non_retryable_real_mutation` flag stops retries (so a fired-but-unconfirmed write is never re-fired). Exhausted retries → **reroute** to an alternate intent (default `{"create_event": "browse_task"}`, `orchestrator.py:444`); still failing → `Step.failed`.

### How success is determined — the read-back proof discipline

`Orchestrator._verify` (`orchestrator.py:555-573`) is the gate: **no proof → not done**, and crucially:
```python
if isinstance(proof, dict) and proof.get("self_attested") is True \
        and not proof.get("verified_by_read"):
    return False
```
A proof that admits it's self-attested **without an independent read-back is rejected** — "the actor grading its own homework."

The real read-back lives in **`hands/api_hand.py`** (the Arcade per-person mesh hand). After a LIVE write succeeds, `_readback_or_fail` (`api_hand.py:446-505`) issues a **second, independent** `client.tools.execute` against a read tool (`READ_BACK` map, `api_hand.py:65-79`: `create_event`→`GoogleCalendar.ListEvents`, `send_email`→`Gmail.ListEmails`, `send_email_draft`→`Gmail.ListDraftEmails`), and only succeeds if the just-written id is re-observed via `confirm_stable_artifact` across `READ_BACK_READS` (≥2, `api_hand.py:35`) reads. The write's own echo is never trusted (`api_hand.py:419-426`). Proof is stamped `self_attested:False, readback:True, verified_by_read:<tool>` (`api_hand.py:493-501`) — exactly the shape `_verify` requires. If no verified read tool exists for an intent → **fail closed** to `needs_human` (`api_hand.py:451-457`), never invent a tool name. The browser agent has the analogous discipline: `confirm_stable_artifact` (`agent/proof.py:40-84`) requires **every delayed read** to verify (returns the first failed read on rejection), powering the durable cart proof.

**Idempotency / no double-send** (`api_hand.py`): a concurrency guard (`_idem_lock`, `_inflight`, `_fired`, `api_hand.py:113-120`) ensures two concurrent presses of the same line never both fire a real write; a fired-but-unconfirmed write **re-verifies, never re-executes** (`_reverify_fired`, `api_hand.py:334-360`).

### Failure handling & logs

Failure is explicit at each tier: worker → `Result(status=failed/needs_human, proof=None, error=...)`; step → `StepState.failed`/`needs_human`; goal → `GoalState.failed`/`waiting`. `_on_error` (`api_hand.py:571-597`) maps Arcade HTTP codes: 401 → loud `NotFundedError`, 403 → `needs_human` with a connect URL, 429/5xx → retryable `failed`.

**Logs → `core/glassbox.py`** — an append-only JSONL at `<data>/glassbox.jsonl` (live file is 6.7 KB; `GlassBox.log`, `glassbox.py:30-34`). Every goal/job/result/decision/approval/reroute is written with a `ts/kind/data` envelope and a human-readable `summaries()` row for the app feed (`glassbox.py:82-137`). It is **byte-capped** (8 MB default, `_DEFAULT_MAX_BYTES`, `glassbox.py:20`) with atomic head-drop rotation — a comment notes it once hit 21 GB and filled the disk (`glassbox.py:17-18`); logging never raises into the caller (`glassbox.py:72-73`).

### Persisted vs ephemeral

- **Persisted**: `Goal` JSON, one file per goal under `<data>/goals/*.json` (`core/store.py:29-31`) — **10,224 files on disk**. `glassbox.jsonl` (capped, semi-durable). Token vault under `<data>/vault/`. Memory in `<data>/memory.db` (SQLite, 54 MB). `pending_asks.json` (115 KB), `scorecard.jsonl` (7.7 MB), `owner_cards/`.
- **Ephemeral (lost on crash)**: the in-flight `asyncio.Future` job correlations in `BrowserLink._pending` (set to `ConnectionError` on detach, `browser_link.py:60-63`); `ApiHand._idem`/`_inflight`/`_fired` in-memory dicts; `ModelGateway.calls`; the entire WebVoyager run state (subgoals/history/`visited`/`committed`) lives only in the `run()` frame — a crash mid-browser-task loses it (the goal store persists the *Step*, not the agent's intra-step progress).

---

## 4d. The vision auditor / judge

There are **two distinct verifiers**, both vision-aware:

**1. The general task judge — `judge()`** (`webvoyager.py:2308-2322`). Called from `/agent/run` and `/agent/resume` (`main.py:1257-1258, 1285-1286`).
- **Input**: the task, the agent's `answer`, the `final_url`, **and the final-page screenshot attached as the image** (`image=shot`, `main.py:1254`). The screenshot is judged in-process and deliberately **not shipped over HTTP** (`main.py:1254`).
- **What it grades**: "does the answer, corroborated by what is visible in the final screenshot, satisfy what the task asked for?" — on correctness/substance, not phrasing, same standard for every site; an instructed stop counts as success (`webvoyager.py:2313-2315`).
- **Returns**: `{"success": bool, "reason": str}` (`webvoyager.py:2321-2322`).
- **How it feeds the next step**: it does **not** drive further actions — it's a terminal grader. It runs at SMART tier with `temperature=0` for a deterministic, re-grade-stable verdict (`webvoyager.py:2317-2319`), and is **skipped entirely** for safety stops and wall handoffs (those are already correct outcomes, `main.py:1257`). Result is attached as `result["judgment"]`.

**2. The in-loop vision verifier (the "auditor" that feeds the next step).** Within the WebVoyager loop, the per-step model call *is* fed the live screenshot (`raw1 = await _think(..., image=shot, ...)`, `webvoyager.py:2183`) — vision drives every decision. The deterministic verifiers `_cart_verified` / `_cart_page_verified` / `_product_item_evidence` (`webvoyager.py:1104-1208`) grade page state from text+elements+URL (not pixels) and gate whether the recipe may claim done. The durable cart proof (`_observe_durable_cart_confirmation`, `webvoyager.py:1481-1489`) is the code-level auditor that must pass across repeated independent fresh-probe reads before success. There is no separate `agent/judge*.py` file — the judge is the `judge()` function in `webvoyager.py` plus these deterministic graders.

---

## 4e. State + storage

**Data dir resolution**: `ANTICIPY_DATA_DIR`, default `.anticipy-data` (repo-relative, expanded), read identically in `core/store.py:17`, `core/control_core.py:43`, `memory/store.py:35`, `hands/token_vault.py:183`. The live dir is `/Users/omarebrahim/Anticipy/.anticipy-data/`.

**On-disk artifacts (verified via `ls` / read-only `sqlite3`):**

| Artifact | Path | Kind / size | Role |
|---|---|---|---|
| Goal store | `goals/*.json` | JSON, **10,224 files** | Persisted `Goal` objects; resume across restart (`store.py`) |
| Memory | `memory.db` | **SQLite, 54 MB** | The brain's memory; tables: `items`, `remembered_lines`, `remembered_enrichment`, `remembered_approval` (schema below) |
| Glass-box | `glassbox.jsonl` | JSONL, 6.7 KB (8 MB cap) | Append-only activity log (`glassbox.py`) |
| Scorecard | `scorecard.jsonl` | JSONL, 7.7 MB | Run metrics |
| Pending asks | `pending_asks.json` | JSON, 115 KB | Awaiting-human queue |
| Token vault | `vault/<sha256(user)[:32]>.json` | JSON, AES-style sealed | One encrypted file per user, app→sealed token + clear metadata (`token_vault.py:182-230`) |
| Owner cards | `owner_cards/` | dir, 33 entries | Owner-action cards |
| Misc | `history.json`, `open_loops.json`, `profile.json`, `inbound_seen.json` | small JSON | scratch/index state |
| Lap snapshots | `20260609T*/`, `m3-lap-*/`, `build-*/` | per-lap copies (each with its own `memory.db`/`glassbox.jsonl`/`scorecard.jsonl`) | factory-loop artifacts |

**SQLite usage**: the **only** SQLite in the engine is the memory store (`grep` confirms `memory/store.py` is the sole `import sqlite3`). Read-only schema (`sqlite3 'file:...?mode=ro'`):
```sql
CREATE TABLE items(id, kind, text, fields, people, timestamp, updated_at,
                   provenance, confidence, importance, status, embedding);
CREATE INDEX idx_kind ON items(kind);
CREATE TABLE remembered_lines(id, text, ts, source, people);
CREATE TABLE remembered_enrichment(line_id, task, people, due_phrase, confidence, enriched_ts);
CREATE TABLE remembered_approval(line_id, goal_id, decision, state, receipt_json, approved_ts);
```
Embeddings are stored as a TEXT column (serialized vectors), so semantic search is an in-process scan, not a vector index — I cannot confirm the exact retrieval algorithm from the schema alone; that lives in `memory/store.py` (outside this section's scope).

**Token vault at-rest** (`token_vault.py`): one file per user under `vault/`, filename = `sha256(user_id)[:32]` (`_safe_id`, `token_vault.py:191-194`); **only the token value is encrypted**, metadata (route/scopes/expiry) stays clear for routing; files are `chmod 0o600`, atomic-replace writes (`token_vault.py:215-225`); AAD binds each record to `user\x00app` so a record can't be relocated undetected, and an HMAC integrity check rejects tampered/wrong-owner records (`token_vault.py:170-177`). The live `vault/` dir is currently empty (no user has connected an app on this machine).

**In-memory state that loses work on crash**: as in 4c — `BrowserLink._pending` job futures, `ApiHand` idempotency/inflight/fired dicts, `ModelGateway.calls`, and the entire WebVoyager `run()` frame (subgoal/history/visited/committed). The persisted boundary is the **Step** in the goal JSON; intra-step browser progress is **not** checkpointed, so a crash mid-cart-task restarts that step from scratch (idempotent on the money side because no checkout ever fires, and on the API side because of the `_fired` re-verify guard).

---

# SECTION 5: THE APP SHELL

> **Reconciliation up front (correcting the prompt's premise):** there is **no Tauri** in this repo. `git grep` for `tauri`/`src-tauri` returns nothing in source; those terms live only in `logs/` references to the *sibling* `Anticipy-DEV-FINAL` repo (out of scope). The shell that ships from **this** repo is two distinct, loosely-coupled things:
> 1. **`macapp/`** — a **SwiftUI / Swift Package Manager** desktop app (`AnticipyApp`), and
> 2. **`app/`** — a **Next.js 15.5.19 App Router** web app (React 19) served on `:3000`.
>
> The macapp is **not** the UI. Its entire job is to *launch* the Next.js web app and open it in the user's default browser. The real interface is the Next.js app. There are **zero `#[tauri::command]` handlers** anywhere — the Swift↔engine and browser↔engine boundaries are plain HTTP. Verified runtime: `node` on `*:3000`, `python3.1` on `127.0.0.1:8787`, `Google [Chrome]` on `127.0.0.1:9222`; **no `:3424`** (`lsof -i :3424` → no listener).

```
        ┌─────────────────────── macapp/ (SwiftUI launcher) ───────────────────────┐
        │  AnticipyApp.swift → WindowGroup → WebRoot (WebApp.swift)                  │
        │    Booter.boot():                                                          │
        │      1. probe http://127.0.0.1:3000  (reachable?)                          │
        │      2. if not: Process /bin/bash Resources/boot.sh   ── starts ──┐        │
        │      3. poll :3000 up to 60s, then NSWorkspace.open(:3000) ──┐    │        │
        └─────────────────────────────────────────────────────────────│────│────────┘
                                                                       │    │
                          default browser opens ─────────────────────► │    ▼
                                                                       │  boot.sh also brings up:
   ┌──────────────── app/ (Next.js App Router, :3000) ────────────────▼─┐  uvicorn engine :8787
   │  Server components + "use client" dashboard (page.js)              │  npm start (this same :3000)
   │  app/api/*  route handlers ── privateEngineRequest() ──► _engine.js │
   │     owner-gate + proxy to ENGINE_URL (127.0.0.1:8787)              │
   └───────────────────────────────────────────────────────────────────┘
                                   │  HTTP (x-anticipy-owner-token)
                                   ▼
                    Python FastAPI ENGINE  127.0.0.1:8787
                    (also hit DIRECTLY by macapp MainView.swift, bypassing Next)
```

---

## 5a. The `macapp/` Swift app (`Package.swift` + `Sources/AnticipyApp/*.swift`)

### What it is
A SwiftUI executable built by **Swift Package Manager**, not Xcode (`macapp/Package.swift:1` `// swift-tools-version:5.9`, `platforms: [.macOS(.v13)]`, a single `.executableTarget` named `AnticipyApp`). The bundle is assembled by `macapp/scripts/build_app.sh` into `macapp/dist/Anticipy.app`; `Info.plist` sets `CFBundleIdentifier ai.anticipy.execute`, version `0.2.0`, `LSMinimumSystemVersion 13.0`, and `NSAllowsLocalNetworking true` (so the sandboxed app may talk to `127.0.0.1`).

### It is NOT a menubar app (correcting both the prompt and the macapp README)
- The prompt calls it a "Swift menubar app"; `macapp/README.md:1` calls it a "menubar app" too. **The code contradicts that.** `grep` for `MenuBarExtra`, `NSStatusBar`, `statusItem` across `macapp/Sources/` returns **nothing** (exit 1, no matches).
- The actual entry point is a normal windowed app: `AnticipyApp.swift:7-12` declares `var body: some Scene { WindowGroup("Anticipy Execute") { WebRoot() ... } }`, and `AppDelegate.applicationDidFinishLaunching` calls `NSApp.setActivationPolicy(.regular)` (`AnticipyApp.swift:19`) — i.e. a regular foreground Dock app, explicitly *not* a `.accessory` (menubar) policy. **It is a single-window launcher app.** I'd state in the audit that the "menubar" label is documentation drift.

### What it actually DOES at runtime: launch the web app, then step aside
The window's root view is `WebRoot` (`WebApp.swift:66`), driven by a `Booter` object (`WebApp.swift:14-64`). On appear (`WebApp.swift:89`) it runs `boot()`:
1. `WebApp.swift:24` — probe `UI_URL = "http://127.0.0.1:3000"` (`WebApp.swift:12`). If already reachable → `ready()`.
2. `WebApp.swift:25-31` — otherwise locate the bundled `boot.sh` (`Bundle.main.url(forResource:"boot",withExtension:"sh")`) and run it via `Process` / `/bin/bash`, blocking on `waitUntilExit()`.
3. `WebApp.swift:32-36` — poll `:3000` once a second for up to 60s; on success → `ready()`.
4. `ready()` (`WebApp.swift:45-49`) flips phase, and `openInterface()` (`WebApp.swift:40-42`) calls `NSWorkspace.shared.open(URL("http://127.0.0.1:3000"))` — **the real UI opens in the default browser, not inside the app.** The window itself only ever shows a status line ("…your interface is open in your browser") and an "Open interface" button (`WebApp.swift:66-91`).

The honesty caveat is in-code: `WebApp.swift:8-10` — "An embedded native webview would need full Xcode/WebKit; this machine has only the Command Line Tools, so the interface opens in the browser." So the macapp is a **bootstrapper/shim**, not a host for the UI.

### `boot.sh` — what the app starts (`macapp/Resources/boot.sh`)
This is where the macapp wires the whole local stack (and it is a **dev launcher tied to a hardcoded repo path**, not a self-contained bundle):
- `boot.sh:10` — `REPO="${ANTICIPY_REPO:-/Users/omarebrahim/Anticipy}"` (hardcoded default = this repo).
- `boot.sh:14-18` — if `curl :8787/readiness` fails, start the **engine**: `ANTICIPY_HANDS_MODE=mock ANTICIPY_CHANNELS_MODE=live ... uvicorn anticipy_engine.main:app --port 8787`. Note `HANDS_MODE=mock` (browser/API hands stubbed) but **`CHANNELS_MODE=live`** (Twilio text/call live) when launched this way.
- `boot.sh:21-24` — if `curl :3000` fails, `npm run build` (once, if no `.next/BUILD_ID`) then `npm start` — the **production** Next.js server, with `ANTICIPY_ENGINE_URL=http://127.0.0.1:8787` passed through.
- `boot.sh:27-32` — wait up to 120s for `:3000`, print `ready`.

`macapp/README.md:24-31` and `boot.sh:5-8` both flag the remaining packaging gap honestly: today it boots from the repo on *this* Mac; a distributable would bundle a frozen Python runtime + prebuilt UI inside the `.app` and Apple-sign/notarize it (Omar-gated).

### The Swift→engine HTTP calls (there are no `tauri::command`s — these URLSession calls are the bridge)
The only Swift view that talks to the engine directly is **`MainView.swift`**, and it does so over `URLSession` straight to `127.0.0.1:8787` — **bypassing Next.js entirely** (no owner token sent). Important nuance: `MainView` is part of the older **inert scaffold** (`RootView` in `AnticipyApp.swift:29-55`) and is **not** on the live `WebRoot` path the shipping app shows — but the HTTP code is real and worth documenting:

| Swift call site | Method | Endpoint (port 8787) | Purpose |
|---|---|---|---|
| `MainView.swift:20`, `:22-26` | `GET` | `http://127.0.0.1:8787/glassbox?limit=40` | `FeedModel.refresh()` — live "what I'm doing / did" glass-box feed; decoded into `GlassEntry[]`, reversed newest-first |
| `MainView.swift:50`, `:54-56` | `GET` | `http://127.0.0.1:8787/pending` | `PendingModel.refresh()` — pending detrimental actions awaiting approve/deny (`PendingItem` = `{ask_id, action, reason, category}`) |
| `MainView.swift:64-70` | **`POST`** | `http://127.0.0.1:8787/resolve` | `PendingModel.resolve(askId, approved)` — body `{"ask_id":…, "approved":bool}`; this is the **only mutating Swift call**, it approves/denies a paused goal (the same round-trip the SMS/voice loop uses) |

`MainView.swift:80` drives a 2-second `Timer.publish` to re-poll `/glassbox` + `/pending` (`MainView.swift:118-119`). `RecordControls` ("MP3"/"Transcript"/"Record") and `SideDoor` ("Tell Anticipy something…") are explicitly **inert** placeholders (`MainView.swift:211-244`). `OnboardingView` ("Begin", `OnboardingView.swift:21` `// inert`) and `ConnectView` (8 app tiles, `ConnectView.swift:4` `// Inert`) are pure scaffold with no network calls. `DesignSystem.swift` is the shared dark/champagne (`0xC8A96A`) token set; no behavior.

> **Net for the audit:** the Swift layer ships as a launcher that opens the browser UI; the richer native `MainView` (glass-box feed + approve/deny against `:8787`) exists and is wired, but is the retired scaffold, not the surface a user sees today. If you want the native panel back, `WebRoot` → `RootView` is the one-line swap in `AnticipyApp.swift:9`.

---

## 5b. The Next.js web app (`app/`) — how it talks to the engine

### The proxy: `app/api/_engine.js`
Every server-side route funnels through this module rather than letting the browser hit `:8787`. Key facts (`app/api/_engine.js`):
- `ENGINE_URL` = `process.env.ANTICIPY_ENGINE_URL || "http://127.0.0.1:8787"` (`_engine.js:1`).
- `engineRequest(path, options)` (`_engine.js:96-120`) does `fetch(\`${ENGINE_URL}${path}\`, {cache:"no-store", headers: engineHeaders(...)})`, parses the body, and re-emits it with the engine's status. On connection failure it returns a structured **503 `engine_unreachable`** (`_engine.js:110-119`) — the UI degrades honestly instead of throwing.
- `engineHeaders()` (`_engine.js:12-18`) attaches `x-anticipy-owner-token: <ANTICIPY_OWNER_API_TOKEN>` to the *upstream* engine call when that env var is set — so the engine can enforce its own owner check even though the call originates server-side.

### The owner-gate (default-secure, two-layer)
There are **two separate tokens** and a same-machine carve-out — the audit-relevant subtlety:
- `configuredOwnerToken()` (`_engine.js:4-6`) reads `ANTICIPY_APP_OWNER_TOKEN || ANTICIPY_OWNER_API_TOKEN` — this gates the **Next app's own** routes.
- `ownerAccessGranted(request)` (`_engine.js:53-63`):
  - **No token configured** → grant **only same-machine** requests (`isLocalRequest`: host `localhost`/`127.0.0.1`/`::1`/empty, `_engine.js:32-35`). The in-code comment (`_engine.js:56-59`) calls this the fix for a prior "owner gate off by default" hole: a *public* deploy with no token is **denied**, not wide open.
  - **Token configured** → require it via `x-anticipy-app-token`, `Authorization: Bearer …`, or the `anticipy_owner_session` cookie (`_engine.js:61-62`).
- `privateEngineRequest(request, path, options)` (`_engine.js:122-126`) is the guarded wrapper: it runs `requireOwnerRequest` (401 `owner_auth_required` on failure, `_engine.js:75-84`) **before** proxying. Session login is `POST /api/owner/session` with `{token}` → sets an `HttpOnly; SameSite=Strict` cookie (`app/api/owner/session/route.js:21-41`, cookie minted at `_engine.js:86-89`); `DELETE` clears it (lock).

I verified the local carve-out is live: a tokenless `curl http://127.0.0.1:8787/status` returned full owner data (`{"engine":"ok",…,"open_loop_count":21,"pending_count":3,…}`) — consistent with "same-machine is trusted when no token is set."

### The route map (all of `app/api/*`) — every private route is a thin proxy
| Route | Verb | Gate | Forwards to engine |
|---|---|---|---|
| `api/health` | GET | **public** (`engineRequest`) | `/health` |
| `api/status` | GET | private | `/status` |
| `api/readiness` | GET | private | `/readiness` (connect-accounts checklist) |
| `api/pending` | GET | private | `/pending` |
| `api/resolve` | POST | private | `/resolve` (approve/deny paused goal) |
| `api/glassbox` | GET | private | `/glassbox?limit=` |
| `api/trigger/tick` | POST | private | `/trigger/tick` (proactive scan) |
| `api/owner/ingest` | POST | private | `/owner/ingest` (typed/transcript day-dump) |
| `api/owner/upload` | POST | private | writes temp file → `/owner/ingest-file` then `rm -rf` (`owner/upload/route.js:35-67`); 100 MB cap (`:8`) |
| `api/owner/cards` | GET | private | `/owner/cards?limit=` |
| `api/owner/onboard` | POST | private | `/owner/onboard` (save memory profile) |
| `api/onboarding/profile` | POST | private | `/onboarding/profile` (read-only profile scrape) |
| `api/connections/authorize` | POST | private | `/connections/authorize` (unlock a hand) |
| `api/memory/open-loops` | GET | private | `/memory/open-loops?limit=` |
| `api/memory/resolve-loop` | POST | private | `/memory/open-loops/resolve` |
| `api/memory/remembered` | GET | private | `/memory/remembered?limit=` (display-only) |
| `api/memory/remembered/approve` | POST | private | `/memory/remembered/approve` ({line_id}; the one press-go write) |
| `api/memory/remembered/dryrun` | POST | private | `/memory/remembered/dryrun` (preview, executes nothing) |
| `api/memory/remembered/dryrun-day` | GET | private | `/memory/remembered/dryrun-day?limit=` |
| `api/download/anticipy-execute` | GET | **public** | serves `macapp/dist/Anticipy.app` as a zip, or an honest 200 text notice if unbuilt (`download/anticipy-execute/route.js:63-104`) — never a 404, never a fake binary |
| `api/glassbox/route`, `api/owner/session`, … | — | — | (session handled in-route, no proxy) |

**Example engine-ward request path** (typed day-dump, owner authenticated):
```
Browser  ──fetch POST /api/owner/ingest {text, source, execute_actions}──►  Next route handler
  app/api/owner/ingest/route.js:3-8  →  privateEngineRequest(request, "/owner/ingest", {POST})
    _engine.js:122  requireOwnerRequest(request)            # 401 owner_auth_required if not granted
    _engine.js:96   fetch("http://127.0.0.1:8787/owner/ingest",
                          headers: { x-anticipy-owner-token: $ANTICIPY_OWNER_API_TOKEN })
  ◄── engine JSON re-emitted with engine's status (or 503 engine_unreachable) ──
```
The browser **never** sees `:8787`; it only ever calls same-origin `/api/*`. The token-to-engine hop happens server-side.

---

## 5c. Frontend — framework, state, routes, behavior

- **Framework:** Next.js **15.5.19** App Router, **React 19.0.0** (`package.json`: `"next":"15.5.19"`, `"react":"19.0.0"`, scripts `next dev|build|start`). Running now as `node` on `*:3000` (`lsof` confirmed). Global shell is `app/layout.js` — a top nav with three links (`Owner` `/`, `Connect accounts` `/connect`, `Download` `/download`, `layout.js:33-38`), Inter from Google Fonts, CSS variables in `app/globals.css`. The **macapp is SwiftUI**; only this web layer is React.
- **State management:** plain React hooks, **no Redux/Zustand/Context library.** The dashboard (`app/page.js`, 1390 lines, a single `"use client"` `Home` component) holds ~25 `useState` slices (`page.js:362-409`: `cards`, `pending`, `loops`, `remembered`, `events`, `access`, `engine`, `memoryForm`, `approveResults`/`previewResults`, …), derives buckets with `useMemo` (`page.js:412-433`), and uses one `useRef` for the Web Speech recognizer (`page.js:410`). `connect/page.js` and `download/page.js` keep their own local state (or none).

### Routes that exist (App Router pages)
| Route | File | Type | Behavior |
|---|---|---|---|
| `/` | `app/page.js` | client | **Owner dashboard** — the real cockpit |
| `/connect` | `app/connect/page.js` | client | **Connect-your-accounts** readiness checklist |
| `/download` | `app/download/page.js` | **static server** | Download front-door |

**`/` — Owner dashboard (`app/page.js`):**
- **Boot + polling:** on mount, `boot()` (`page.js:556-570`) calls `refreshAccess()` then `loadStatus()`, then re-polls **every 5 s** via `setInterval(loadStatus, 5000)`. `loadStatus()` (`page.js:501-554`) fan-outs six parallel `GET`s with `Promise.allSettled`: `/api/status`, `/api/pending`, `/api/glassbox?limit=20`, `/api/owner/cards?limit=50`, `/api/memory/open-loops?limit=50`, `/api/memory/remembered?limit=50`. If any returns 401 it aborts and shows the gate (`page.js:510-513`, `447-451`).
- **Owner gate UI:** three render states (`page.js:870-905`) — "Checking owner access" while `!access.checked`; a password-field **unlock form** (`POST /api/owner/session`, `page.js:465-490`) when `access.required && !authenticated`; otherwise the dashboard with a **Lock** button (`page.js:923-927`, `DELETE` session).
- **Actions (all owner-fetch, `credentials:"same-origin"`, `page.js:436-438`):** ingest typed text or an uploaded file (`runIngest`/`runUpload` → `/api/owner/ingest` | `/api/owner/upload`, `page.js:745-784`); approve/deny a pending detrimental ask (`resolveAsk` → `/api/resolve`, `page.js:784`); save the memory profile (`/api/owner/onboard`); build a profile from URLs (`/api/onboarding/profile`); resolve/connect an open loop (`/api/memory/resolve-loop`, `/api/connections/authorize`); press-go / preview a remembered line (`/api/memory/remembered/approve` | `/dryrun`); run a proactive scan (`scanLoops` → `POST /api/trigger/tick`).
- **Layout/components:** `TaskCard`, `PendingAsk`, `MemoryLoop`, `ProfileView`, `MemoryField` (`page.js:189-360`); a top status strip showing engine online/loops/waiting/memory-recovered plus a readiness-pill grid (`page.js:917-938`); an Input panel with Reset (`page.js:941-955`).
- **Voice input:** `startListening()` (`page.js:840-868`) uses the **browser-native `webkitSpeechRecognition`** (continuous, interim results) to dictate into the text box — note this is *browser* ASR, unrelated to any engine/pendant transcription path.

**`/connect` (`app/connect/page.js`):** client component; on mount `load()` fetches `GET /api/readiness` (`connect/page.js:135-154`), renders an "X of N connected" capability checklist via `StatusBadge`/`CapabilityRow` (`connect/page.js:29-128`). Copy is deliberately consumer-framed ("Nothing here spends a cent or sends anything; it only unlocks the hands," `connect/page.js:177-182`).

**`/download` (`app/download/page.js`):** a **static server component** (no client state, `:1-3`). Single CTA `href = NEXT_PUBLIC_ANTICIPY_DOWNLOAD_URL || "/api/download/anticipy-execute"` (`:16-17`, `:49-64`). When `NEXT_PUBLIC_ANTICIPY_DOWNLOAD_SIGNED !== "1"` it renders a **"Developer preview — not Apple-notarized, right-click → Open"** banner (`:18`, `:70-88`) — matching the unsigned-zip contract the download route enforces server-side.

---

### What I could not determine from code alone
- **Whether the live shipping macapp ever surfaces the native `MainView` feed.** The code path is `WebRoot` only (`AnticipyApp.swift:9`); `RootView`/`MainView` are present and wired but unreferenced by `@main`. I'd need to run `dist/Anticipy.app` to confirm the user never sees the native panel — but the `@main` scene is unambiguous in source.
- **The macapp README's "menubar" claim is contradicted by code** (no `MenuBarExtra`/`NSStatusBar`; `setActivationPolicy(.regular)`). This is a documentation/source mismatch worth a finding, not a runtime question.

---

# SECTION 6: THE PUBLIC SURFACE — HOW DO YOU TRIGGER A TASK TODAY

## TL;DR for a new dev (the one-line answer)

**The canonical, supported way to make Anticipy infer-and-act on a task is `POST /owner/ingest` with `{"text": "...", "execute_actions": true}` against `http://127.0.0.1:8787`.** That is the single shared "Action Engine" door for typed transcript, MP3 upload, browser-mic listening, and inbound SMS (`engine/anticipy_engine/main.py:718-722`, docstring "One shared Action Engine intake for typed transcript, MP3, listening, and pay-to-try"). Everything below is either a feeder into that door, a lower-level/legacy variant of it, or a read-only surface.

Two important caveats a new dev *must* internalize:

1. **`execute_actions` defaults to `false`.** `class OwnerIngestIn` sets `execute_actions: bool = False` (`main.py:318-322`). A plain `POST /owner/ingest` with no `execute_actions` only *captures and previews* cards (it runs `card_for_line`, not `_spine_card`); it does **not** run the proactive spine, does **not** create real calendar events, and does **not** raise asks. To actually drive act/ask/silent you must pass `execute_actions: true`.
2. **The engine is LIVE right now.** Confirmed listeners: `127.0.0.1:8787` (python engine), `*:3000` (Next.js), `127.0.0.1:9222` (Chrome CDP). There is **no port 3424** (verified via `lsof`). A real `POST /owner/ingest` with `execute_actions: true` against this process can send a real SMS, create a real calendar event, or drive the browser. **Every curl below that mutates state is illustrative — do not run it against the running engine.**

```
                       THE ONE DOOR (canonical)
                       =========================
  typed text ─┐
  MP3 upload ─┤   POST /owner/ingest        ControlCore.owner_ingest(...)
  web "Listen"┤   POST /owner/ingest-file ─►  observe → capture → card_for_line
  inbound SMS ┘   (InboundPoller calls           │
                   owner_ingest directly)        ▼ (execute_actions=true)
                                              _spine_card → proactive spine
                                              (triage → decider → harm-line)
                                                     │
                                          ┌──────────┼───────────┐
                                          ▼          ▼           ▼
                                         ACT        ASK        SILENT
                                      (hands)   (/pending →   (memory only)
                                                /resolve)
```

---

## 6a. Every HTTP endpoint in `engine/anticipy_engine/main.py`

Binds `127.0.0.1` only (`app = FastAPI(..., description="Local-first hub for Anticipy. Binds to 127.0.0.1 only.")`, `main.py:126-131`; uvicorn `--port 8787` per `CLAUDE.md`).

### The two middlewares every request passes through

1. **Owner-token gate** — `owner_api_auth` (`main.py:234-249`). If `ANTICIPY_OWNER_API_TOKEN` is **set**, every path except `/health` (`PUBLIC_PATHS = {"/health"}`, `main.py:51`) requires the token, presented as header `x-anticipy-owner-token: <tok>` **or** `Authorization: Bearer <tok>` (`_owner_api_authorized`, `main.py:138-143`, constant-time `secrets.compare_digest`). On failure → **401** `{"error":"unauthorized","message":"Anticipy owner API token required."}` with `WWW-Authenticate: Bearer`. If the token is **unset** (the default local-dev posture, and the posture of *this* running engine — `/readiness` reports `owner_api: "local"`), **all routes are open to anyone who can reach the port**, which is loopback-only by bind.
2. **Body-size cap** — `request_size_cap` (`main.py:271-300`). POST/PUT/PATCH bodies over `ANTICIPY_MAX_REQUEST_BYTES` (default 1 MiB, ceiling 64 MiB) get **413** `{"error":"payload_too_large","message":"Request body exceeds N bytes.","limit":N}`. Exempt: `/owner/ingest-file` (`REQUEST_SIZE_EXEMPT_PATHS`, `main.py:69`) because it streams from disk.

### Endpoint table

Legend — **Trigger** = can cause an act/ask/side-effect; **Feeder** = becomes a trigger only with a flag; **Read** = safe GET; **Dev/diag** = experimental or diagnostic.

| Method | Path | Class | Backed by | Notes |
|---|---|---|---|---|
| GET | `/health` | Read (public) | `health()` `main.py:580` | only path exempt from token gate |
| GET | `/readiness` | Read | `_connect_readiness` `main.py:572` | connect-your-accounts checklist |
| GET | `/status` | Read | `status()` `main.py:585` | counts + channels + readiness |
| POST | `/capture` | **Trigger (legacy)** | `core.feed` `main.py:601` | proactive spine, no card board |
| GET | `/memory/history` | Read | `main.py:608` | |
| GET | `/memory/open-loops` | Read | `main.py:613` | `?limit=` |
| GET | `/memory/remembered` | Read | `main.py:618` | inert remember-list |
| POST | `/memory/remembered/approve` | **Trigger** | `core.approve_remembered` `main.py:637` | default-deny press-go; executes ONLY whitelisted reversible intents |
| POST | `/memory/remembered/dryrun` | Read-ish | `core.dryrun_remembered` `main.py:653` | plans, never executes |
| GET | `/memory/remembered/dryrun-day` | Read-ish | `main.py:673` | whole-day dry run |
| POST | `/memory/open-loops/resolve` | Mutate (memory) | `core.resolve_memory_loop` `main.py:688` | marks a loop done; 400 on failure |
| POST | `/connections/authorize` | Mutate (memory) | `core.authorize_connection_loop` `main.py:696` | 400 on failure |
| POST | `/extension/hello` | Diag | `main.py:704` | sets `extension_hello_seen` |
| **POST** | **`/event`** | **Trigger (low-level)** | `core.feed` `main.py:713` | spine directly; persona/realday harness path |
| **POST** | **`/owner/ingest`** | **Trigger (CANONICAL)** | `core.owner_ingest` `main.py:718` | needs `execute_actions:true` to act |
| **POST** | **`/owner/ingest-file`** | **Trigger (canonical, file)** | `core.owner_ingest` `main.py:724` | reads a staged file, transcribes audio, then same path |
| GET | `/owner/cards` | Read | `core.owner_cards` `main.py:776` | |
| POST | `/owner/onboard` | Mutate (memory) | `core.owner_onboard` `main.py:782` | writes people/prefs/apps |
| POST | `/onboard/discover` | Mutate (memory) | `core.onboard_discover` `main.py:793` | ingests a Chrome connection scan |
| POST | `/onboard/scan` | **Trigger (browser)** | `core.browser_link.discover_connections` `main.py:806` | tells the extension to scan Chrome |
| POST | `/onboarding/profile` | **Trigger (browser, read-only)** | `_build_onboarding_profile` `main.py:983` | drives read-only browser arm over public URLs (SSRF-gated) |
| GET/POST | `/onboarding/clarify` | **Trigger (browser, read-only)** | `main.py:1018` | builds profile + plans clarify-call questions |
| POST | `/trigger/tick` | **Trigger (clock)** | `core.proactive.trigger_tick` `main.py:1083` | fires due reminders/watchers deterministically |
| GET | `/glassbox` | Read | `main.py:1090` | live activity feed; `?limit=` |
| GET | `/pending` | Read | `core.pending_asks` `main.py:1095` | the "needs you" asks |
| POST | `/resolve` | **Trigger (completes ask)** | `core.resolve` `main.py:1101` | YES/NO → runs/declines the paused goal |
| GET | `/scorecard` | Read | `main.py:1107` | |
| GET | `/goals/{goal_id}` | Read | `main.py:1112` | |
| GET | `/gateway` | Read | `main.py:1118` | model/cost + run-mode |
| GET | `/ws/state` | Read | `main.py:1134` | browser link connected? |
| GET | `/ws/token` | Read (sensitive) | `main.py:1139` | returns the WS pilot token |
| POST | `/ws/reload` | Dev/diag | `main.py:1146` | "dev-only hot-reload trigger" |
| POST | `/ws/browse` | **Trigger (browser, diag)** | `main.py:1159` | comment: "Transport diagnostic only. M3 evidence must use /event" |
| POST | `/ws/observe` | **Trigger (browser, read)** | `main.py:1184` | SSRF-gated navigate |
| POST | `/ws/act` | **Trigger (browser, act)** | `main.py:1192` | low-level click/type/navigate over the extension link |
| **POST** | **`/agent/act`** | **Trigger (browser — PROVEN arm)** | `browser_use_link.browse_act` `main.py:1214` | the proven vision action arm; money/checkout/login are HARD STOPS in the runner guard |
| POST | `/agent/run` | **Trigger (browser, experimental)** | `WebVoyagerAgent` `main.py:1244` | bespoke WebVoyager loop; SSRF-gated |
| POST | `/agent/resume` | **Trigger (browser, experimental)** | `main.py:1270` | continue after a human cleared a wall; docstring marks it a STUB seam |
| POST | `/agent/judge` | Dev/diag | `main.py:1296` | LLM judge of an answer |
| WS | `/cr` | **Trigger (voice)** | `conversation_relay` `main.py:1335` | Twilio ConversationRelay two-way voice turns |
| WS | `/ws/extension` | Transport | `ws_extension` `main.py:1422` | the Chrome extension's pilot socket |

---

### The key task-trigger endpoints, precisely

#### `POST /owner/ingest` — CANONICAL ✅

- **Request model** `OwnerIngestIn` (`main.py:318-322`): `text: str` (required), `source: str = "transcript"`, `meta: dict = {}`, `execute_actions: bool = False`.
- **Real example (illustrative — do not POST to the live engine):**
  ```bash
  curl -s http://127.0.0.1:8787/owner/ingest \
    -H 'content-type: application/json' \
    -d '{"text":"Wife says can you pick up the kids at 3 today, I've got the dentist. Also order more beakers for the lab.",
         "source":"transcript",
         "execute_actions":true,
         "meta":{"ui":"owner_mode"}}'
  # If ANTICIPY_OWNER_API_TOKEN is set, add:  -H "x-anticipy-owner-token: $TOK"
  ```
- **Response shape** = `OwnerIngestResult.model_dump()` (`control_core.py:630-636`; model at `owner_mode.py:49-53`):
  ```json
  {
    "source": "transcript",
    "observed_lines": [ { "line_no": 0, "text": "Wife says can you pick up the kids ...", "...": "..." } ],
    "cards": [
      {
        "id": "ab12...", "source": "transcript", "line_no": 0,
        "source_text": "Wife says can you pick up the kids at 3 today...",
        "title": "Pick up the kids at 3", "disposition": "ask",
        "route": "calendar", "action": "...", "args": {},
        "confidence": 0.75, "reason": "...", "status": "open",
        "proof": [], "execution": {"decision":"ask","goal_id":"...","ask_id":"...","goal_state":"waiting"}
      }
    ],
    "ignored_line_count": 1
  }
  ```
  (Card fields enumerated from `OwnerTaskCard`, `owner_mode.py:30-46`. `execution` is `None` until a path runs the card; populated `{decision, goal_id, ask_id, goal_state}` when `execute_actions=true`.)
- **Errors:** 401 (token gate), 413 (oversized body), 422 (Pydantic validation if `text` missing).

#### `POST /owner/ingest-file` — canonical, file variant

- **Request model** `OwnerFileIngestIn` (`main.py:325-330`): `path: str`, `filename: str = ""`, `source: str = "upload"`, `meta`, `execute_actions: bool = False`.
- The `path` must live under the upload staging root (`ANTICIPY_UPLOAD_ROOTS`/`ANTICIPY_UPLOAD_ROOT`, default `$TMPDIR/anticipy-owner-uploads`); otherwise **403** "uploaded file path is outside the Anticipy upload staging area" (`main.py:728-729`). Audio files are transcribed via `transcribe_audio` (`capture/transcribe.py`); non-audio is read as UTF-8. Then it calls the same `core.owner_ingest`. Errors: 404 (not found), 413 (over `ANTICIPY_MAX_UPLOAD_BYTES`, default 100 MiB), 422 (transcription failed), 400 (no usable text). The file is deleted after read (`_cleanup_upload`, `main.py:388-399`).
- **Illustrative:**
  ```bash
  curl -s http://127.0.0.1:8787/owner/ingest-file \
    -H 'content-type: application/json' \
    -d '{"path":"/var/folders/xx/anticipy-owner-uploads/note.m4a","execute_actions":true}'
  ```
  Same `OwnerIngestResult` response shape.

#### `POST /event` — low-level spine trigger (test/harness lane)

- **Request model** `EventIn` (`main.py:312-315`): `text: str`, `source: str = "app"`, `meta: dict = {}`. Calls `core.feed` directly → triage → gate → act/ask (`control_core.py:433-449`).
- **Response** = `proactive.on_event(...)` dict (`proactive.py:276-278`):
  ```json
  {"decision":"ask","category":"unclassified","reason":"cannot confirm safe -> fail-safe ask",
   "detrimental":true,"memory_forced":false,"decider":"ask",
   "goal_id":"6268de00...","ask_id":"6268de00..."}
  ```
  (or `{"decision":"ignore","triaged":false,"goal_id":null,...}` for noise — `proactive.py:149,157`.)
- This is the pipe **`scripts/realday.sh` and the persona harness use** (see 6b/6d): `http("POST","/event",{"text":line,"source":"app","meta":meta})` (`realday.sh:195`). It runs the spine but does **not** write the owner card board, so it's the right surface for *evaluation*, not the product UI. **`/owner/ingest` is the product door; `/event` is the harness/low-level door.**

#### `POST /agent/act` — the PROVEN browser action arm

- **Request model** `AgentActIn` (`main.py:1207-1211`): `task: str`, `start_url: str`, `max_steps: int = 16`, `cdp_url: Optional[str] = None`. With `cdp_url` set (e.g. `http://127.0.0.1:9222`) it drives the user's *own logged-in Chrome*. `start_url` is SSRF-gated to public http(s) (`_assert_public_agent_url`, `main.py:1221`); money/checkout/login are hard stops in the runner guard (docstring `main.py:1214-1220`).
- **Response** (`main.py:1225-1234`): `{"success","answer","steps","final_url","actions","allowed_domains","error","agent":"browser-use"}`.
- **Illustrative (DO NOT run — drives a real browser):**
  ```bash
  curl -s http://127.0.0.1:8787/agent/act \
    -H 'content-type: application/json' \
    -d '{"task":"add a 5-pack of 250ml beakers to the cart, stop at the review step",
         "start_url":"https://www.example-lab-supply.com","cdp_url":"http://127.0.0.1:9222"}'
  ```
- `/agent/run` and `/agent/resume` are the **experimental** bespoke WebVoyager loop (`AgentRunIn`/`AgentResumeIn`, `main.py:1199-1268`); `/agent/resume`'s docstring calls itself a "STUB seam." Prefer `/agent/act`.

#### `POST /trigger/tick` — the clock trigger

- No body. Returns `{"fired": <int>}` (`main.py:1083-1087`). Runs one `TriggerWatcher` pass — the same thing the background scheduler does every `ANTICIPY_TICK_SECONDS` (default 30s; `0` disables, `main.py:108-109`). This is how due reminders / anticipatory nudges fire deterministically in tests and gates.
  ```bash
  curl -s -X POST http://127.0.0.1:8787/trigger/tick   # -> {"fired":0}
  ```

#### `GET /pending` + `POST /resolve` — the approval round-trip

- `GET /pending` → `{"pending":[{ask_id, action, reason, category, goal_id}, ...]}` (`control_core.py:965-970`). **Real live response from this engine right now:**
  ```json
  {"pending":[{"ask_id":"6268de006bb7430a8d646354b1ae4c2e",
    "action":"Follow up on your commitment: Wife says can you pick up the kids at 3 today...",
    "reason":"cannot confirm safe -> fail-safe ask","category":"unclassified",
    "goal_id":"6268de006bb7430a8d646354b1ae4c2e"}, ...]}
  ```
- `POST /resolve` — `ResolveIn` (`main.py:333-335`): `{"ask_id": "...", "approved": true}`. Runs or declines the real paused goal (`core.resolve` → `resolve_ask`). Response (`proactive.py:462-495`): on approve `{"ask_id","approved":true,"goal_id","state":"done"}`; on a blocked (money) ask `{"ask_id","approved":false,"blocked":true,...}`; on decline `{"ask_id","approved":false,"goal_id","declined_action":"..."}`; unknown id `{"ask_id","resolved":false,"reason":"unknown or already-resolved ask"}`.
  ```bash
  # Illustrative — this APPROVES and RUNS a real paused goal:
  curl -s -X POST http://127.0.0.1:8787/resolve \
    -H 'content-type: application/json' \
    -d '{"ask_id":"6268de006bb7430a8d646354b1ae4c2e","approved":true}'
  ```

#### `POST /onboard/discover` and `POST /onboard/scan`

- `/onboard/scan` — `ScanIn` (`main.py:802-803`): `{"services":[{"name":"...","url":"..."}]}` (empty → extension defaults). **Triggers** the connected Chrome extension to scan logged-in services; returns `{"triggered": <bool>, "note": "..."}` (`main.py:806-815`). `triggered:false` (no error) when no extension is attached.
- `/onboard/discover` — `DiscoverConnectionsIn` (`main.py:788-789`): `{"discovered":[...],"source":"chrome_scrape"}`. Ingests the scan results the extension POSTs back, writing the per-person mesh (memory mutation).

#### WebSocket `/cr` — the two-way voice trigger

- Twilio ConversationRelay connects here via `<Connect><ConversationRelay url=...>` TwiML (`main.py:1335-1419`). **Auth before `accept()`**: `_owner_ws_authorized` (`main.py:208-231`) — a valid `X-Twilio-Signature` always passes; else if a token is configured it must be presented (`?token=`/header/bearer, `_ws_owner_token_supplied` `main.py:146-158`); else (tokenless) only loopback/TestClient. Reject → `ws.close(1008)`. Frames: in `{type:"setup"|"prompt"|"interrupt"|"dtmf"}`, out `{type:"text",token,last}` streamed + `{type:"end",handoffData}`. Per-call caps: `CR_MAX_TURNS=200`, `CR_MAX_CALL_SECONDS=3600` (`main.py:58-59,1366-1367`). The brain is the **same decider** the proactive engine runs (`_relay_brain`, `main.py:1301-1312`) — words only; the real act/ask still flows through the ambient transcript.

#### WebSocket `/ws/extension` — the Chrome pilot transport

- `ws_extension` (`main.py:1422-1450`). Auth: `core.browser_link.check_token(ws.query_params.get("token"))` — the token from `GET /ws/token`; bad token → `close(1008)`. Carries `ping/pong` + browser commands. This is **transport, not a task trigger** — but it is what `/ws/observe`, `/ws/act`, `/onboard/scan` ride on.

---

## 6b. CLI commands that trigger a task

| Command | What it triggers | Evidence |
|---|---|---|
| `bash scripts/realday.sh [days...]` | Health-checks the engine, then POSTs each transcript line to **`/event`** (`source:"app"`), then GETs `/glassbox` + `/scorecard`. Writes a replayable trace. This is the product's *evaluation* driver, not `/owner/ingest`. | `realday.sh:182,195,209,213`; `http()` at `realday.sh:59` |
| `engine/.venv/bin/python factory/bin/persona_run.py --bank ... --lap ...` | For each persona day, shells out to `scripts/realday.sh` (`subprocess.run(["bash", REPO/"scripts/realday.sh", day])`) — i.e. drives `/event` per line. The nightly gate's task driver. | `persona_run.py:8,141` |
| `engine/scripts/owner_test.py`, `demo_day.py`, `brain_loop_part1/2.py`, `journey_eval.py`, `live_*.py`, etc. | Various eval/probe harnesses under `engine/scripts/` that drive the engine. (No single canonical "trigger" CLI; these are test rigs.) | `ls engine/scripts/` |

**There is NO `capture/transcribe.py` CLI.** I grepped: `transcribe.py` has **no `if __name__ == "__main__"` block** and no argparse/`sys.argv` entry point (verified `grep '__main__' ... → NO __main__ in transcribe.py`). It is an importable library (`is_audio_file`, `transcribe_audio`) consumed by `/owner/ingest-file` and by `scripts/realday.sh` (`from anticipy_engine.capture.transcribe import ...`). To transcribe-and-trigger from disk, the supported path is `POST /owner/ingest-file`, not a transcribe CLI.

---

## 6c. macapp / web controls that trigger a task

### Swift menubar app (`macapp/`, NOT Tauri — `Package.swift` + `Sources/AnticipyApp/*.swift`)

It talks to the engine at `http://127.0.0.1:8787` (`MainView.swift:50`). Its **only mutating trigger** is the approval tap:

- `PendingModel.resolve(askId, approved)` → `POST http://127.0.0.1:8787/resolve` with body `{"ask_id":askId,"approved":approved}` (`MainView.swift:64-70`). It polls `GET /pending` (`MainView.swift:55`) and reads `GET /glassbox?limit=40` (`MainView.swift:20`). The Swift app does **not** itself POST `/owner/ingest` — `WebApp.swift` embeds the Next.js UI at `http://127.0.0.1:3000` (`WebApp.swift:12`), so the ingest/Listen surface is the web app.

### Next.js web app (`app/`, served on `:3000`)

Triggers, all routed through `app/api/*` Next routes that re-issue to the engine via `privateEngineRequest`, which injects the owner token header when `ANTICIPY_OWNER_API_TOKEN` is set (`app/api/_engine.js:12-16`, `engineHeaders` adds `x-anticipy-owner-token`):

| Web control | Web route → engine | Evidence |
|---|---|---|
| **"Go" / ingest button** (`runIngest`) | `POST /api/owner/ingest` → **`POST /owner/ingest`** with `{text, source, execute_actions, meta:{ui:"owner_mode"}}` | `page.js:760-768`; route `app/api/owner/ingest/route.js:5` |
| **File upload** (`runUpload`) | `POST /api/owner/upload` → **`POST /owner/ingest-file`** | `page.js:745-753`; route `app/api/owner/upload/route.js:41` |
| **"Listen" button** (browser mic) | `startListening()` uses `window.webkitSpeechRecognition`, sets `source="start_listening"`, and feeds the transcript to the same `runIngest` → **`/owner/ingest`** | `page.js:840-854,990-991`; source label `page.js:29` |
| **Approve/Deny** (`resolveAsk`) | `POST /api/resolve` → **`POST /resolve`** `{ask_id, approved}` | `page.js:637,788`; route `app/api/resolve/route.js:5` |
| **Tick** (proactive nudge) | `POST /api/trigger/tick` → **`POST /trigger/tick`** | `page.js:732`; route `app/api/trigger/tick/route.js:4` |
| Pending list / resolve-loop | `GET /api/pending`, `POST /api/memory/resolve-loop` | `page.js:504`; routes under `app/api/` |

So in the UI, the **Go button, the Listen button, and the file upload all converge on `/owner/ingest` (or `/owner/ingest-file`)** — confirming the canonical door.

---

## 6d. Other entry points (background drivers, no human in the loop)

| Entry point | What it triggers | Evidence |
|---|---|---|
| **Tick scheduler** (in-process) | On engine startup, `_trigger_scheduler` loops every `ANTICIPY_TICK_SECONDS` (default 30s) calling `core.proactive.trigger_tick()` — the anticipatory clock that fires due reminders/watchers. `=0` disables it (tests use `POST /trigger/tick`). | `main.py:82-90,104-114` |
| **InboundPoller** (in-process, live-gated) | On startup, *if* `InboundPoller.live_ready()` (Twilio creds + live mode) and `ANTICIPY_INBOUND_POLL_SECONDS>0` (default 15s), `_inbound_scheduler` polls Twilio. For each inbound SMS **from the owner's number** (`OWNER_PHONE`): a `YES <code>`/`NO <code>` reply → `core.resolve(ask_id, approved)` (`inbound.py:143`); any other text → `core.owner_ingest("sms", body, {...}, execute_actions=True)` (`inbound.py:118-119`). **This is a real, hands-off task trigger** — an SMS from the owner drives the same canonical door with `execute_actions=True`. | `main.py:93-114`; `inbound.py:69-127,143` |
| **launchd `com.anticipy.factory`** | Nightly nerve loop. The plist runs `caffeinate -i /bin/bash /Users/omarebrahim/Anticipy/factory/bin/loop.sh --nightly` (`StartCalendarInterval`, 22:30→07:00). This is the **build/forcing system, not the product** — each lap eventually drives `factory/bin/persona_run.py` → `scripts/realday.sh` → `POST /event`. So the cron path's task-trigger is `/event`, via the persona harness, against a freshly-built engine. | `~/Library/LaunchAgents/com.anticipy.factory.plist` (ProgramArguments shown); `verify_gate.sh:39`, `persona_run.py:141` |
| **Chrome extension callback** | After `POST /onboard/scan` tells the extension to scan, the extension POSTs results back to `POST /onboard/discover` over plain HTTP (`onboard_scan` note: "results arrive via /onboard/discover", `main.py:814-815`). The extension also holds the `/ws/extension` socket as the pilot transport for `/ws/observe` and `/ws/act`. | `main.py:806-815,1422-1450` |
| **File watchers / MCP** | I found **no file-watcher or MCP-server entry point inside this engine** that triggers tasks. The MCP tools listed in this session belong to *Claude's* environment, not the Anticipy engine's HTTP surface. The only "upload watch" is the explicit, request-driven `/owner/ingest-file` staging-dir read — not a daemon watcher. (I cannot find a watcher in code; if one exists it is outside `engine/anticipy_engine/main.py` and the lifespan handler, which only start the tick + inbound schedulers — `main.py:104-123`.) |

---

### Bottom line for the new dev

- **Make Anticipy do a task today:** `POST /owner/ingest` with `execute_actions:true` (or its file twin `/owner/ingest-file`). The web "Go"/"Listen"/upload buttons and inbound owner-SMS all funnel here.
- **Resolve an ask it raised:** `GET /pending` → `POST /resolve {ask_id, approved}`.
- **Drive the browser for real:** `POST /agent/act` (proven arm; `cdp_url:http://127.0.0.1:9222` to use the live Chrome).
- **Tick the anticipatory clock by hand:** `POST /trigger/tick`.
- **`/event` is the harness/low-level door** (what `realday.sh` and the nightly factory use), not the product UI door — don't confuse the two.
- **Token posture:** this running engine has no `ANTICIPY_OWNER_API_TOKEN` set (`/readiness` → `owner_api:"local"`), so every route is open on loopback; in a public deploy set the token and send `x-anticipy-owner-token`.

---

## SECTION 7: DEPENDENCIES, ENV, AND SECRETS

This section is grounded in the files actually present in `/Users/omarebrahim/Anticipy`. Where the user's mental model (DeepSeek/Kimi/Deepgram/Tauri) appears, it shows up only as *unused option strings* in `.env.example` / `.env.local` — none of those providers are imported or called by the engine code (verified: no `import deepseek`, no `deepgram` import, no `kimi` client anywhere in `engine/anticipy_engine/`). The live model path is OpenRouter → Gemini (see 7a / 7b).

---

### 7a. Full dependency list with versions

There are **two separate Python virtualenvs** under `engine/`, by design — this is the single most important dependency fact in the repo:

| venv | Python | Purpose | Declared by |
|---|---|---|---|
| `engine/.venv` | **3.10.14** | the FastAPI engine + the local ML stack (whisper transcription, sentence-transformers embeddings) | `engine/requirements.txt` |
| `engine/.bu-venv` | **3.11.12** | the open-source `browser-use` vision agent, run as a **subprocess** out-of-band from the main engine | no pinned requirements file in repo (installed ad-hoc; see flag below) |

The split exists because `browser-use==0.13.1` pulls a heavy, conflicting tree (playwright/patchright, anthropic, google-genai, mcp) that the engine must not share. The engine shells out to `.bu-venv`'s python via `ANTICIPY_BROWSERUSE_PYTHON` (`hands/browser_use_link.py:69`).

#### Python — `engine/.venv` (the engine), `pip freeze`
Declared pins in `engine/requirements.txt`:
```
fastapi>=0.115,<1.0
uvicorn[standard]>=0.30
httpx>=0.27
arcadepy>=1.0
websockets>=12.0
python-dotenv>=1.0
openai-whisper>=20250625
```
Actually installed (selected, full freeze captured):
```
fastapi==0.136.3          uvicorn==0.48.0        starlette==1.2.1
httpx==0.28.1             httpcore==1.0.9        websockets==16.0
arcadepy==1.10.0          python-dotenv==1.2.2   pydantic==2.13.4
openai-whisper==20250625  tiktoken==0.13.0
torch==2.12.0             numpy==2.2.6           numba==0.65.1 / llvmlite==0.47.0
transformers==5.10.1      tokenizers==0.22.2     safetensors==0.7.0
sentence-transformers==5.5.1  scikit-learn==1.7.2  scipy==1.15.3
huggingface_hub==1.17.0   hf-xet==1.5.0          sympy==1.14.0
```
> **Flags:**
> - **`torch==2.12.0` is the heavyweight.** It is pulled in transitively by `openai-whisper` (transcription) and `sentence-transformers` (memory embeddings, `memory/embed.py:29` default model `ANTICIPY_EMBED_MODEL`). This is the single largest install in the repo and the reason the engine venv is on Python 3.10. Notably **there is no `openai` SDK and no `anthropic` SDK in the engine venv** — the gateway speaks raw OpenAI-compatible HTTP via `httpx` directly (`core/gateway.py:138,168`). The "openai/anthropic" packages live only in `.bu-venv`.
> - `requirements.txt` is **under-specified vs. reality**: it lists 7 packages but the venv has 50+. `torch`, `transformers`, `sentence-transformers`, `scikit-learn` are all unpinned/undeclared (arrive transitively). A clean rebuild from `requirements.txt` alone would not reproduce this environment deterministically.
> - **Versions are implausibly future-dated** (`fastapi==0.136.3`, `transformers==5.10.1`, `torch==2.12.0`, `certifi==2026.5.20`). I cannot determine from the repo whether these are real upstream releases or a synthetic/mirrored index; flagging because it affects reproducibility and supply-chain review. What I *can* confirm: these are the versions resolved in the venv on disk.

#### Python — `engine/.bu-venv` (the browser-use arm), `pip freeze`
No requirements file is committed for this venv (`.bu-venv/` is gitignored, `.gitignore:67`). Installed (selected):
```
browser-use==0.13.1       browser-use-sdk==3.4.2   cdp-use==1.4.5
playwright==1.60.0        patchright==1.60.1       pyee==13.0.1
anthropic==0.76.0         openai==2.16.0           google-genai==1.65.0   groq==1.0.0   ollama==0.6.1
google-api-python-client==2.188.0  google-auth-oauthlib==1.2.4
mcp==1.26.0               pydantic==2.12.5         pydantic-settings==2.14.1
cryptography==49.0.0      pyotp==2.9.0 / PyJWT==2.13.0
pillow==12.2.0  pypdf==6.10.2  python-docx==1.2.0  reportlab==4.4.9  markdownify==1.2.2
```
> **Flag:** this venv ships **four LLM SDKs** (`anthropic`, `openai`, `google-genai`, `groq`, plus `ollama`) and the full Google API client stack. Because it has **no committed lockfile**, this whole arm is non-reproducible from the repo — it must be reconstructed by hand. `pyotp`/`PyJWT` here suggest the browser agent is expected to handle TOTP / token flows during web automation.

#### Node — Next.js web app (`app/`, served on :3000)
`package.json` (root):
```json
{ "name": "anticipy-executor-working", "dependencies": {
    "next": "15.5.19", "react": "19.0.0", "react-dom": "19.0.0" } }
```
> **Flag — no lockfile.** There is **no `package-lock.json` / `yarn.lock` / `pnpm-lock.yaml`** anywhere outside `node_modules` (the only `package.json` files found are the root one and two generated ones under `.next/`). So the Node app is also not reproducibly pinned; only three direct deps, all on bleeding-edge majors (Next 15.5, React 19). The app is deliberately thin — it's an API-proxy shell to the engine (`app/api/_engine.js`), not a heavy SPA.

#### Node — browser **extension** (`extension/`)
No `package.json` exists in `extension/` (it's a raw MV3 content/background bundle, not an npm project) — confirmed by the package.json search returning only root + `.next`. So there are **no Node dependencies for the extension**; it's vanilla JS loaded unpacked into Chrome and talks to the engine over `/ws/extension` (`core/browser_link.py`).

#### Swift — macOS menubar app (`macapp/Package.swift`)
```swift
// swift-tools-version:5.9
let package = Package(
    name: "AnticipyApp", platforms: [.macOS(.v13)],
    targets: [ .executableTarget(name: "AnticipyApp", path: "Sources/AnticipyApp") ])
```
> **Zero external Swift package dependencies** — no `dependencies:` array, no `Package.resolved`. It's a pure-SwiftUI/AppKit menubar app that just renders two local engine URLs: `http://127.0.0.1:3000` (`WebApp.swift:12`) and `http://127.0.0.1:8787/glassbox` (`MainView.swift:20,50`). Confirms the audit-prompt claim: this is a Swift app, **not Tauri**, and it carries no secrets or tokens (grep for `token|secret|Authorization` in `macapp/Sources` returned only those plain `127.0.0.1` URLs).

---

### 7b. Every environment variable the system reads

All names below are read via `os.environ.get` / `os.environ[...]` (Python) or `process.env.*` (Node), with the literal call site. The Swift app reads **no** env vars (grep for `ProcessInfo|getenv|environment[` in `macapp/Sources` returned nothing). Engine env loading is centralized: `core/env.py:17-19` does `load_dotenv(.env.local, override=False)`, invoked from `control_core.py:155` — so **a real shell-exported var always wins over `.env.local`** (this is the CI safety property that keeps the suite in stub/mock even with a live `.env.local`).

#### A. Secrets / credentials (the ones that matter)

| Var | Read at (file:line) | If missing |
|---|---|---|
| **`OPENROUTER_API_KEY`** | `core/gateway.py:110`; `hands/browser_use_runner.py:184` | fallback after `ANTICIPY_MODEL_API_KEY`; if both unset the OpenRouter path raises `RuntimeError("no model API key…")` at `gateway.py:136-137`. Browser-use runner returns `{"error":"OPENROUTER_API_KEY missing…"}` (`:191`). |
| **`ANTICIPY_MODEL_API_KEY`** | `core/gateway.py:109` | primary key; falls back to `OPENROUTER_API_KEY`. |
| **`ARCADE_API_KEY`** | `hands/api_hand.py:141` | raises `NotFundedError("ARCADE_API_KEY NOT SET / NOT FUNDED")` (`:143`) → the API-mesh hand is treated as unfunded, not crashed. |
| **`ARCADE_USER_ID`** | `core/control_core.py:180` | falls back to `ADMIN_EMAIL`, then to literal `"omar@anticipy.ai"`. |
| **`ANTICIPY_VAULT_KEY`** | `hands/token_vault.py:121` (const `_ENV_MASTER_KEY` `:51`) | **Loud fail by design.** `_master_key()` raises `VaultError("ANTICIPY_VAULT_KEY NOT SET — the vault refuses to store/read tokens without a master key (no plaintext-at-rest fallback)")`. No silent fallback. |
| **`ANTICIPY_OWNER_API_TOKEN`** | `main.py:135` (const `TOKEN_ENV` `:49`); Node side `app/api/_engine.js:13` | **Fail-OPEN if unset** — see security note below. |
| **`ANTICIPY_APP_OWNER_TOKEN`** | `app/api/_engine.js:5` | Next-side token, falls back to `ANTICIPY_OWNER_API_TOKEN`. |
| **`TWILIO_ACCOUNT_SID`** | `channels/text.py:26,43`, `call.py:33,99`, `inbound.py:83,255` | part of `configured()` gate; if any of SID/TOKEN/FROM missing, channel is **not "configured"** → stays mock. |
| **`TWILIO_AUTH_TOKEN`** | same files; also `main.py:196`, `inbound.py:84` | as above; also used to verify Twilio request signatures on the `/cr` WS upgrade (`main.py:196`, header const `:54`). |
| **`TWILIO_FROM`** | `channels/text.py:28,46`, `call.py:35,102`, `inbound.py:85,257` | part of `configured()`. |
| **`OWNER_PHONE`** | `control_core.py:293,310`, `channels/inbound.py:91` | falls back to `ALERT_PHONE` → `TWILIO_TO` → literal `"+10000000000"` (`control_core.py:31`). |
| `ALERT_PHONE`, `TWILIO_TO`, `TWILIO_FROM` | various above | secondary notify targets / fallbacks. |

> The following secrets are **declared in `.env.local` but NOT read by any engine/app code** I could find via grep: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`, `CEREBRAS_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `KIMI_API_KEY`, `DEEPSEEK_API_KEY`, `DEEPGRAM_API_KEY`, `TAVILY_API_KEY`, `CAPSOLVER_API_KEY`/`TWOCAPTCHA_API_KEY`, `SCRAPERAPI_KEY`/`STEEL_API_KEY`, `HETZNER_API_TOKEN`, all `R2_*`, all `STRIPE_*`, all `SUPABASE_*`, `RESEND_API_KEY`, `GOOGLE_OAUTH_*`, `ENCRYPTION_KEY`/`JWT_SECRET`/`PROFILE_ENCRYPTION_KEY`/`SECRET_KEY`/`ENGINE_INTERNAL_TOKEN`, `GMAIL_TEST_PASSWORD`, `DEMO_PASSCODE`. These are aspirational/option keys (or belong to the sibling DEV-FINAL product / the Next deploy surface). I cannot find a code path in this repo that consumes them; if you want certainty, the missing-consumer list is what to confirm against the deploy target. (`GEMINI_API_KEY` in particular is **not** how Gemini is reached here — Gemini is reached *through* OpenRouter using `OPENROUTER_API_KEY`; see 7c note.)

#### B. Model / gateway flags
`ANTICIPY_MODEL_PROVIDER` (`gateway.py:98`, default `stub`) · `ANTICIPY_MODEL_CHEAP` (`:101`, default `openai/gpt-4o-mini`) · `ANTICIPY_MODEL_SMART` (`:102`, default `openai/gpt-4o`; also `browser_use_runner.py:194`) · `ANTICIPY_OPENAI_BASE_URL` (`:108`, default OpenRouter URL) · `ANTICIPY_MODEL_MAX_TOKENS` (`:156`, optional cap) · `ANTICIPY_MODEL_ENDPOINT` (`core/control_core.py:162`, `model/client.py:27`) · `ANTICIPY_AGENT_MAX_TOKENS` (`agent/webvoyager.py:38`) · `ANTICIPY_EMBED_MODEL`/`ANTICIPY_EMBED_DEVICE` (`memory/embed.py:29,59`) · `ANTICIPY_WHISPER_MODEL` (`capture/transcribe.py:76`, default `tiny.en`).

#### C. Hands / browser / mode flags
`ANTICIPY_HANDS_MODE` (`control_core.py:178`, default `MODE_MOCK`) · `ANTICIPY_BROWSER_HAND_MODE` (`:207`) · `ANTICIPY_NATIVE_BRIDGE_FALLBACK` (`:192`, default on) · `ANTICIPY_BROWSE_TIMEOUT` (`:197`, "30") · `ANTICIPY_AGENT_MAX_STEPS` (`:199`/`browser_hand.py:130`, "18") · `ANTICIPY_AGENT_TIMEOUT` (`:200`/`browser_hand.py:131`, "240") · CDP/native-bridge: `ANTICIPY_TRIGGER_HOST/PORT/SECRET` (`native_bridge_link.py:232-235`), `ANTICIPY_NATIVE_BRIDGE_TIMEOUT` (`:236`), `ANTICIPY_CDP_HOST/PORT` (`:237-238`), `ANTICIPY_NATIVE_BRIDGE_SCRIPT` (`:801`), `ANTICIPY_CHROME_USER_DATA_DIR` (`:880`) · browser-use subprocess: `ANTICIPY_BROWSERUSE_PYTHON` (`browser_use_link.py:69`), `ANTICIPY_BROWSERUSE_CDP_URL` (`:209`/`browser_use_runner.py:204`), `ANTICIPY_BU_CHROME_BIN` (`browser_use_runner.py:199`), `ANTICIPY_ENV_PATH` (`browser_use_runner.py:181`, default hard-coded `/Users/omarebrahim/Anticipy/.env.local`) · cart durability `ANTICIPY_CART_DURABILITY_READS/DELAY_SECONDS` (`webvoyager.py:129-130`) · `ANTICIPY_API_READBACK_READS` (`api_hand.py:35`).

#### D. Channels / voice flags
`ANTICIPY_CHANNELS_MODE` (`control_core.py:292,307`; `channels/{text,call,inbound}.py`; default `mock`) · `ANTICIPY_OWNER_INGEST` (`control_core.py:299`, default off) · `ANTICIPY_INBOUND_POLL_SECONDS` (`main.py:112`/`control_core.py:313`, "15") · `ANTICIPY_CALL_VOICE` (`channels/call.py:52`) · `ANTICIPY_CR_WSS_URL` (`main.py:197`, `call.py:84`) · `ANTICIPY_CR_MAX_TURNS`/`ANTICIPY_CR_MAX_CALL_SECONDS` (`main.py:1319,1329`, hard-floored at 200 turns / 3600 s).

#### E. Engine core / memory / safety flags
`ANTICIPY_DATA_DIR` (`core/store.py:17`, `control_core.py:43`, `token_vault.py:183`, `memory/store.py:35`; default `.anticipy-data`) · `ANTICIPY_TICK_SECONDS` (`main.py:108`) · `ANTICIPY_MAX_REQUEST_BYTES` (`main.py:256`, hard-ceilinged) · `ANTICIPY_MAX_UPLOAD_BYTES` (`main.py:732`) · `ANTICIPY_UPLOAD_ROOT(S)` (`main.py:376`) · `ANTICIPY_MEMORY_MODE` (read in 8+ places: `live_memory/{selfcheck,infer,maintain,capture,inject}.py`, `memory/embed.py:36`, `proactive/triage.py:638`) · `ANTICIPY_ABSTAIN_FLOOR` (`live_memory/inject.py:40`) · `ANTICIPY_DECISION_WALL_S` (`core/proactive.py:168`) · `ANTICIPY_TIEBREAK_TIMEOUT_S` (`triage.py:995`) · `ANTICIPY_NAVWALL_ALLOW_PRIVATE` (`core/navwall.py:121`) · `ANTICIPY_GLASSBOX_MAX_BYTES`/`KEEP_LINES` (`core/glassbox.py:44,48`) · audio pipeline: `ANTICIPY_AUDIO_PAD_SECONDS`, `_MERGE_GAP_SECONDS`, `_MIN_SPEECH_SECONDS`, `_CHUNK_SECONDS`, `_CHUNK_OVERLAP_SECONDS`, `_SILENCE_NOISE`, `_MIN_SILENCE_SECONDS`, `ANTICIPY_REALDAY_AUDIO_MAX_SECONDS` (all `capture/transcribe.py:60-159`).

#### F. Next.js app (`app/`) env (`process.env.*`)
`ANTICIPY_ENGINE_URL` (`app/api/_engine.js:1`) · `ANTICIPY_OWNER_API_TOKEN` + `ANTICIPY_APP_OWNER_TOKEN` (`_engine.js:5,13`) · `NODE_ENV` (`:87,92`) · `ANTICIPY_UPLOAD_ROOT` + `ANTICIPY_MAX_UPLOAD_BYTES` (`app/api/owner/upload/route.js:7,8`) · `NEXT_PUBLIC_ANTICIPY_DOWNLOAD_URL` + `NEXT_PUBLIC_ANTICIPY_DOWNLOAD_SIGNED` (`app/download/page.js:17,18`). The many `NEXT_PUBLIC_SUPABASE_*` / `STRIPE_*` / `R2_*` keys in `.env.example` are **not referenced by any file under `app/` in this repo** — they belong to the broader product's web surface, not this checkout.

> ### Security note — two fail-open observations (read code, not run)
> 1. **Owner-API token is fail-OPEN over HTTP.** `main.py:243`: `if token and request.url.path not in PUBLIC_PATHS and not _owner_api_authorized(...)` → 401. The guard only engages **when the token is set**. With `ANTICIPY_OWNER_API_TOKEN` unset (the documented local default, `main.py:238-240`), **every** owner/private route is unauthenticated. This is intentionally mitigated by the engine binding **127.0.0.1 only** (`main.py:11,129`) and the WS local-peer check (`_ws_is_local`, `main.py:161-185`). The risk surface is therefore "anything that can reach loopback" (other local processes, an SSRF that lands on 127.0.0.1:8787) — not the open internet. Token comparison itself is correct: constant-time `secrets.compare_digest` (`main.py:143`).
> 2. **Channel live-gating uses `ANTICIPY_CHANNELS_MODE`, NOT `TWILIO_MOCK`.** The actual live test is `os.environ.get("ANTICIPY_CHANNELS_MODE") == "live" and configured()` (`channels/text.py:30-31`, mirrored in `call.py`/`inbound.py`). The `TWILIO_MOCK` var in `.env.example`/`.env.local` is **not read by any engine code** (grep confirms zero hits in `engine/`). So in the live `.env.local`, `TWILIO_MOCK=false` is a no-op; what actually keeps SMS/voice in mock is `ANTICIPY_CHANNELS_MODE=mock`. This is a footgun: an operator who sets `TWILIO_MOCK=false` expecting it to enable/disable live sends is editing a dead variable.

---

### 7c. Where credentials live at runtime

```
                    ┌─────────────────────────────────────────────┐
   .env.local  ───► │ core/env.py: load_dotenv(override=False)     │
 (gitignored,       │  → populates os.environ for the engine proc  │
  ~60 keys)         └──────────────┬──────────────────────────────┘
                                   │ real shell exports WIN (override=False)
                                   ▼
        ┌──────────────────────────────────────────────────────────────┐
        │ os.environ  (process memory, plaintext while running)         │
        │  • OPENROUTER_API_KEY → Bearer header, gateway.py:146         │
        │  • ARCADE_API_KEY     → Arcade(api_key=...), api_hand.py:145  │
        │  • TWILIO_AUTH_TOKEN  → HTTP Basic auth, text.py:49           │
        │  • ANTICIPY_VAULT_KEY → KDF master key (never written to disk)│
        └───────────────┬──────────────────────────────────────────────┘
                        │ ANTICIPY_VAULT_KEY (scrypt KDF)
                        ▼
   ┌────────────────────────────────────────────────────────────────────┐
   │ TOKEN VAULT  —  <ANTICIPY_DATA_DIR>/vault/<sha256(user)[:32]>       │
   │ token_vault.py: one encrypted file per user. Per-OAuth-token:      │
   │   scrypt(master,salt,N=2^14) → enc_key+mac_key  (independent)      │
   │   encrypt-then-MAC (HMAC-CTR keystream + HMAC-SHA256 tag)          │
   │   AAD = user_id|app  (record can't be moved between users/apps)    │
   │   ONLY the token value is encrypted; route/scopes/expiry stay clear│
   │   plaintext reachable ONLY via SecretToken.reveal() at HTTP auth   │
   └────────────────────────────────────────────────────────────────────┘
```

**1. `.env.local` (gitignored).** Confirmed not tracked (`git ls-files --error-unmatch .env.local` → "did not match any file(s)") and ignored at `.gitignore:18` (`git check-ignore .env.local` → match). Loaded by `core/env.py:17-19` with `override=False`. It currently holds **real, populated** values — I verified set-status without printing any plaintext:

| Key | Status |
|---|---|
| `OPENROUTER_API_KEY` | SET (73 chars) |
| `ARCADE_API_KEY` | SET (59 chars) |
| `ANTICIPY_VAULT_KEY` | SET (64 chars) |
| `TWILIO_AUTH_TOKEN` | SET (32 chars) |
| `GEMINI_API_KEY` | SET (39 chars) |

Live engine config in `.env.local` (non-secret flag values, safe to quote):
```
ANTICIPY_MODEL_PROVIDER = openrouter
ANTICIPY_OPENAI_BASE_URL = https://openrouter.ai/api/v1/chat/completions
ANTICIPY_MODEL_SMART = google/gemini-2.5-flash
ANTICIPY_MODEL_CHEAP = google/gemini-2.5-flash-lite
ANTICIPY_HANDS_MODE = live
ANTICIPY_CHANNELS_MODE = mock        ← SMS/voice still mocked
TWILIO_MOCK = false                  ← dead var (engine never reads it; see 7b note 2)
```
> This confirms the audit's reconciliation: Gemini is the live model, but it is reached **through OpenRouter** (provider=`openrouter`, base URL `openrouter.ai`, models `google/gemini-2.5-flash*`) using `OPENROUTER_API_KEY` — the standalone `GEMINI_API_KEY` in `.env.local`, though populated, is **never read by engine code**. Hands are `live` (real Arcade/browser) but channels are `mock` (no real Twilio sends).

**2. The token vault (`hands/token_vault.py`) — encrypted at rest.** Per-user OAuth tokens (Gmail/GoogleCalendar/Slack/GoogleDocs via Arcade) are stored under `<ANTICIPY_DATA_DIR>/vault/`, **one encrypted file per user**, filename = `sha256(user_id)[:32]` so an email never becomes a readable path (`token_vault.py:186-189`). Encryption: stdlib-only authenticated encryption — `scrypt(N=2¹⁴,r=8,p=1)` derives **independent** enc/mac subkeys per record (`:130-134`), then encrypt-then-MAC with the salt+nonce+ct+**AAD(user|app)** bound into the HMAC-SHA256 tag (`:148-158`), verified constant-time **before** decrypt (`:173`). The master key is `ANTICIPY_VAULT_KEY` from the env — **never persisted to disk**; if unset the vault refuses to operate (`:122-126`). Decrypted tokens are wrapped in `SecretToken`, whose `__str__`/`__repr__`/`__format__`/`__reduce__` all redact, so a token can't leak into a prompt, log, f-string, JSON dump, or pickle — `.reveal()` (`:91-96`) is the only escape and is called only by the non-LLM connector at the moment of the real auth handshake. This is a genuinely careful design; the **only** weakness is that vault security collapses to the strength/secrecy of `ANTICIPY_VAULT_KEY`, which lives in plaintext in `.env.local` and in process env — i.e. **not in macOS Keychain**.

**3. Keychain / OS secret store — NOT used.** I found no Keychain, `security`, `SecItem`, or credential-manager usage anywhere (the Swift app reads no secrets; the engine reads everything from env/`.env.local`). All credential security rests on: (a) `.env.local` being gitignored + filesystem perms, (b) the vault master key in env, (c) the engine binding loopback-only. There is no hardware/OS-backed secret storage in this repo.

**4. Other gitignored secret-bearing paths (confirmed ignored):** `engine/.venv`, `engine/.bu-venv` (`.gitignore:63-68`), and `.anticipy-data/` (`.gitignore:81`, where the vault and DBs live) — all returned matches from `git check-ignore`, so neither the venvs nor the encrypted vault/data dir can be committed accidentally.

> **What I could not determine from code alone:** whether the future-dated dependency versions (`torch==2.12.0`, `fastapi==0.136.3`, `certifi==2026.5.20`, etc.) correspond to real upstream releases or a private/mirror index — this needs the resolving index URL / `pip config` to verify supply-chain provenance. And whether the unused `.env.local` keys (Stripe/Supabase/R2/OAuth/the alt-LLM keys) are consumed by the **deploy** target (Vercel `app/` build) rather than this engine — that requires the deploy config, not this checkout.

---

# SECTION 8: WHAT'S BROKEN OR HALF-BUILT TODAY

This section is brutal and evidence-based. Every claim is cited to `file:line` in the audit target `/Users/omarebrahim/Anticipy` (branch `factory/build`, HEAD verified running). Where the project's own dated handoffs are now stale against the code, I say so explicitly. The headline: **the inference core ("the middle") is genuinely solid and tested; nearly everything that touches a real external account or a real user's logged-in browser is wired-but-unproven or fails-closed-by-design, and the single biggest product promise — onboarding that scrapes your logged-in Chrome into a per-person mesh — is half-built (the transport exists; nothing autonomously triggers it and nothing turns the result into a live connection).**

---

## 8.0 Process model confirmed (so the rest is grounded)

`lsof -i -P -n | grep LISTEN` shows exactly three listeners, matching the audit brief and contradicting the user's assumed stack:

```
python3.1 66506 ... 127.0.0.1:8787 (LISTEN)   # FastAPI engine (uvicorn anticipy_engine.main:app)
node      22303 ... *:3000          (LISTEN)   # Next.js (next-server v15.5.19)
Google     8835 ... 127.0.0.1:9222  (LISTEN)   # Chrome CDP
```

**No `:3424`. No Tauri. No Deepgram/DeepSeek/Kimi/Ralph process.** Confirmed.

---

## 8.1 Tests: where, how many, do they pass

**The suite is fully offline/stub/mock — I confirmed the guarantee before running it.** `scripts/run_suite.sh:14-16` force-exports the safe modes, and the comment at `:9-13` explains *why* this is load-bearing for safety:

```bash
export ANTICIPY_MODEL_PROVIDER=stub
export ANTICIPY_HANDS_MODE=mock
export ANTICIPY_CHANNELS_MODE=mock
```

> "ANTICIPY_CHANNELS_MODE=mock is load-bearing for SAFETY: without it, a live .env.local makes the channels/inbound tests place REAL Twilio calls/SMS in CI." (`run_suite.sh:11-12`)

I ran it. **Result: 87 passed, 0 failed — `SUITE GREEN`.** Note this *exceeds* every status doc: `HANDOFF_2026-06-15.md:72,149` still says **76/76**, `PENDING_FOR_OMAR.md:14` says **75/75**, `STATUS.md` references **29/29**. The suite has grown ~15% beyond what the newest handoff claims — a benign staleness, but it shows the docs lag the code.

The 87 tests are the per-module `engine/scripts/test_*.py` list at `run_suite.sh:29` (≈70 unit tests including `safety_mega_eval`, `proactive`, `harmline`, `api_hand`, `token_vault`, `browser_safety_loop`, `purchase_guard`), plus 3 shell tests (`owner_app_auth`, `owner_app_product_path`, `download_route`, lines 33-35), 5 self-test instruments (lines 38-42), and 4 boot integration tests (lines 45-48). **The safety floor (`safety_mega_eval.py`) and the P5 owner-test runner are both in the gate and both pass.**

**Honest caveat the suite itself carries:** every test runs on the **stub model + mock hands + mock channels**. As `HANDOFF_2026-06-15.md:266` admits: *"the assembled demo runs on STUB model + MOCK hands (proves plumbing composes, not that live inference is right)."* Green here proves the *plumbing and the deterministic safety floor*, not that a live OpenRouter call decides correctly or that a live Arcade/Twilio/browser call works. That is the central honesty boundary of this whole repo.

---

## 8.2 TODO / FIXME / XXX / HACK census

```
git grep -nE "TODO|FIXME|XXX|HACK" -- engine/ app/ macapp/ extension/
```

After filtering test scaffolding (`mktemp -t anticipy-XXXXXX` is *not* a code smell — it's a temp-dir template, appearing in ~6 `test_*.sh` files) and the `_ID_KEYS` tuple, the **real** markers are few and concentrated. There are **zero** `FIXME`/`HACK` in product code. The substantive TODOs:

| File:line | Theme | What it means |
|---|---|---|
| `engine/anticipy_engine/hands/api_hand.py:61` | **Fail-closed sentinels** | Unverified Arcade read-back tools left as `None` so the live path *fails closed* rather than inventing a tool name |
| `api_hand.py:77` | **Slack read-back missing** | `# message (Slack): no verified Slack read tool. TODO(slice-1): confirm name.` |
| `api_hand.py:452` | **Slack write unverifiable** | `# ... no read-back tool wired ... (TODO(slice-1): wire the verified read tool.)` |
| `engine/anticipy_engine/main.py:1277` | **Browser resume is a stub** | `# Restoring the exact mid-plan state ... is the TODO; for now we continue the task from the now-unblocked page` |
| `live_memory/{capture,infer,inject,maintain,selfcheck}.py` (5 files) | **Model-enrichment never runs** | Each has `# TODO(live): ... never hit in tests` — the cheap/smart-model enrichment paths in live-memory are placeholders that fall through to deterministic behavior |

**The TODO theme is unusually disciplined:** they are honest "this fails closed until verified" markers, not abandoned half-work. The `live_memory/*` TODOs are the one place where a whole class of behavior (model-driven memory enrichment, relevance scoring, reflection) is stubbed `pass` and **only the cold/deterministic path actually runs in production** — richer memory inference is aspirational.

Broader stub census (`grep -i "stub|placeholder|not implemented|NotImplemented"`): the `actions/` package (`browser.py:18`, `connector.py:20`, `base.py:14`) is an **entire stub adapter layer** marked "Stub for the scaffold" — superseded by the real `hands/`, but still present as dead scaffold. `channels/app.py:1` (in-app delivery to the SwiftUI app) is `"Stub: nothing surfaced yet."` `capture/mac_mic.py` is "still a stub" (no real audio).

---

## 8.3 The defining build gap: onboarding Chrome-scrape → per-person mesh is HALF-BUILT

This is the product's signature promise (`HANDOFF_2026-06-15.md:46-49`: *"onboarding scrapes your logged-in Chrome to build a per-person mesh"*) and the **#1 NOT-done item** (`HANDOFF:98-101`). The reality is more nuanced than "unbuilt" — the pieces exist but the chain is not closed end-to-end:

```
   [user's logged-in Chrome]
          │
   (1) extension scrape ✅ BUILT
   extension/background.js:142 doDiscoverConnections()
   reads only a logged-in-vs-signin signal, POSTs to /onboard/discover
          │
   (2) engine trigger ✅ BUILT but ⚠️ MANUAL-ONLY
   main.py:806 POST /onboard/scan → browser_link.discover_connections()
   browser_link.py:114 sends the {"type":"discover_connections"} frame
          │  ↑ NOTHING in any autonomous/onboarding flow calls this.
          │    It is an HTTP endpoint a human/script must POST. No UI button,
          │    no onboarding step, no autopilot calls /onboard/scan.
          │
   (3) scan → mesh mapping ✅ BUILT (pure/deterministic)
   onboarding/connection_scan.py:38 scan_to_onboarding()
   maps each logged-in service to OwnerConnectionIn{status: needs_auth|connected}
          │
   (4) ACTUAL CONNECTION ❌ ABSENT
   The mapping emits "needs_auth" cards. NOTHING then performs the OAuth /
   token issuance to move needs_auth → connected. The mesh is a TO-DO LIST,
   not a live connection.
```

**Evidence the trigger is endpoint-only (not autonomous):** `grep discover_connections` across the engine finds it *defined* in `browser_link.py:106`, *exposed* at `main.py:812`, and *exercised* only by `test_onboard_scan.py`. The test's own docstring is the smoking gun (`engine/scripts/test_onboard_scan.py:1-4`):

> *"The onboarding scan TRIGGER — the wiring the 'scrapes you' step was missing. The extension already handles a `discover_connections` message + POSTs results to /onboard/discover; **what was missing is the engine TELLING it to scan.**"*

So the transport was patched in, but no product surface *invokes* it. The audit brief's framing is correct in spirit and now sharpened: the handler exists on both ends; **what's missing is (a) any live caller of `/onboard/scan` in a real onboarding flow, and (b) the needs_auth → connected closing step.** And `PENDING_FOR_OMAR.md:31-32` itself flags this honestly: *"Onboarding scrape is UNBUILT ... no code reads your logged-in Chrome to build the per-person API mesh — connections are hand-typed today. This is a real build gap."*

**One caveat on the extension-predates-handler claim in the brief:** I can confirm from code that the *loaded* extension at `extension/background.js:86` **does** handle `discover_connections` today, so the source-of-truth extension is current. Whether the *Chrome-loaded copy* in the running browser predates it I **cannot determine from code alone** — that depends on when the user last reloaded the unpacked extension, which lives in Chrome's runtime, not the repo.

---

## 8.4 Wired-but-not-working-live: the API arm (Arcade)

The per-person API mesh is architecturally complete and **fails closed**, but **has never executed a real write on a real account through the live path** in the current wiring. Several distinct sub-gaps:

**(a) Gmail draft/read gated on an ungranted scope.** `STATUS.md:23-27` (tested via `client.tools.authorize`): `GoogleCalendar.*` = **completed** (live), but `Gmail.WriteDraftEmail` and `Gmail.ListDraftEmails` = **pending** — they need the `gmail.compose` scope, *"which is NOT yet granted."* The code is ready (`api_hand.py:43` maps `send_email_draft → Gmail.WriteDraftEmail`, `:76` wires the `ListDraftEmails` read-back) but the whole path is connect-gated. `PRODUCT_STATUS.md:37`: *"Gmail draft auth still depends on `gmail.compose`."*

**(b) Slack write is structurally unverifiable → fails closed.** `api_hand.py:45` maps `message → Slack.SendMessageToChannel`, but `READ_BACK["message"] = None` (`:78`) because there is no confirmed Slack read tool. The consequence at `api_hand.py:446-453`: a Slack write returns `status=needs_human` with `"unverified_write": True` — *"wrote via {tool} but cannot independently verify it."* So **Slack sends can never be marked done**; this is correct fail-closed behavior, but it means the Slack write arm is effectively a dead end until `TODO(slice-1)` lands a read-back tool.

**(c) Live API arm has never run — VAULT_KEY + OAuth unset.** `PENDING_FOR_OMAR.md:26-28`: *"Today a live call would raise NotFunded/Vault errors. The read-back-gated create_event/draft path has never run on a real account."* `api_hand.py:138-143`: `_client_or_build()` raises `NotFundedError("ARCADE_API_KEY NOT SET / NOT FUNDED")` if the key is absent.

**(d) The per-person token mesh is built and NOW wired — but always falls back to the shared key.** This corrects a stale claim. `HANDOFF_2026-06-15.md:204-206` (§10A) asserts *"`control_core.py:180` builds `ApiHand(user_id=…)` with no broker, so it always uses the shared key."* **That is no longer true in the current code:** `control_core.py:188-189` now passes `broker=TokenBroker(self.token_vault)`. *However*, the practical outcome is the same — at `api_hand.py:164-186`, `_live_client()` consults the broker, but with no per-user vault token ever issued (no OAuth-token-issuance path populates `TokenVault`), every call hits the `:184` branch: *"no broker, or this user hasn't connected the app -> shared-key path (legacy)."* So the mesh's *wiring* is done but its *value* (per-user short-lived tokens) is inert: there is one global key for one global user. Single-tenant ceiling confirmed (`HANDOFF:266`: *"single-tenant ceiling (one global ControlCore, no real multi-user)"*).

---

## 8.5 Wired-but-not-working-live: the browser arm (two transports, both with gaps)

There are genuinely **two** browser arms and they are in different states — and the docs disagree with each other about which is "the proven one," so I traced the code directly:

**Arm A — extension/WebVoyager (the user's real logged-in Chrome).** This is what **cards actually route to**: `control_core.py:64` catches `intent == "browse_task"`, and `:226` reroutes `post_to_x / create_event / message` alternates to `browse_task`. The `/agent/run` and `/agent/resume` endpoints (`main.py:1245,1280`) construct `WebVoyagerAgent`. The handoff calls this loop *"flakier"* (`HANDOFF:155`) and *"the homegrown loop"* (`HANDOFF:163`).

**Arm B — browser-use vision agent (`/agent/act`).** `main.py:1214-1233` calls `browser_use_link.browse_act(...)` and returns `"agent": "browser-use"`. **This endpoint is orphaned from card execution:** `grep "/agent/act|browser_use"` in `control_core.py` and `app/` returns **nothing** — no card-execution path POSTs to it. `HANDOFF:108-110` admits this is the **#4 NOT-done item**: *"Wire `/agent/act` into the card-execution flow (it's a standalone endpoint)"* and *"attach browser-use to the user's logged-in Chrome via CDP (today it uses its own fresh browser → no logins)."*

**The honest net:** the arm that runs in the *real logged-in Chrome* (Arm A) is the flaky homegrown loop; the *more reliable* arm (Arm B) runs a **throwaway logged-out browser** and isn't wired to cards. So "act on YOUR Amazon cart" is not achievable today by either path as wired. Add the standing caveat from `HANDOFF:161-164`: *"The browser ACTION arm on arbitrary sites is genuinely NOT solved by anyone."*

**Browser resume is a stub** (`main.py:1276-1278`): after a human clears a login/captcha wall, restoring exact mid-plan state is *"the TODO; for now we continue the task from the now-unblocked page"* — i.e., it loses subgoal/history context on resume.

---

## 8.6 Wired-but-not-fully-proven: the voice/text loop

`PENDING_FOR_OMAR.md:22-25` and `HANDOFF:86-88` agree on the live gap: outbound SMS/call legs are individually proven by Twilio read-back, but **the full inbound round-trip (Omar texts → engine auto-composes → replies) has never run**, and the formal `gate_P3.sh` has never been run green. `.env.local` is held at `ANTICIPY_CHANNELS_MODE=mock` and live is opt-in per-launch (`HANDOFF:122-124`).

**A critical honesty note this section must carry:** `HANDOFF:76-79` documents that an *earlier* version of this very doc **fabricated** the "voice is LIVE & verified" claim with invented SIDs (`SM59e0…/CA38e2…`) *"that existed nowhere but this doc."* This is the canonical example of the repo's named recurring failure — **over-claiming a live success that wasn't verified** (`HANDOFF:21,160`). It was caught and corrected, but it is the single most important "don't trust a green light without read-back" datapoint in the whole codebase.

The fallback when the brain is keyless/stub/errors is **canned phrasing**, not silence (`conversation_relay.py:36,109-121`; `gateway.py:230-235`) — fine as a degraded mode, but it means a starved/keyless brain will *speak deterministic lines*, not real inference.

---

## 8.7 Honest ABSENT inventory (from the repo's own docs + code)

These are explicitly not-built, per the most current sources:

- **Pendant capture: `NotImplementedError`.** `capture/pendant_phone.py:17,20` — both `start()` and `stop()` raise *"PendantPhoneSource is wired in a later chunk."* The socket is reserved; there is no body. (Highly relevant to any "pendant" claim.)
- **"Start Listening" is a ~29-line stub.** `HANDOFF:265`: *"Start Listening = ~29-line STUB (absent)."* In code it's a UI source label (`app/page.js:29,840-851`, `owner_mode.py:20`) with no real always-on capture behind it; `capture/mac_mic.py:21` — *"Stub: no real audio yet."*
- **The 5-day Owner Test (P5): 0 of 5.** `HANDOFF:102` — *"His literal finish line."* The *scorer* and a single-day *runner* exist and self-test green (`run_suite.sh:41-42`), but no real multi-day trial has happened (`PRODUCT_STATUS.md:39`).
- **Notarization: one human-only Omar step** (`HANDOFF:103-106`) — the download is signed but not notarized.
- **In-app (SwiftUI) delivery channel:** `channels/app.py:1` — *"Stub: nothing surfaced yet."*

---

## 8.8 The ratchet/treadmill problem (factory-control-plane framing)

The "ratchet problem" is real and documented, but it's a **measurement/forcing-system pathology, not a product bug** — worth stating so it isn't mistaken for broken product code.

`logs/factory/RATCHET.json` holds best-ever metrics and `phases_closed`. The pathology: it and `product_scoreboard.csv` are **tracked-but-uncommitted** files updated *between* lap commits, so a lap's revert (`git reset --hard <base>`) can **destroy the ratchet record**. `FAILURE_MODES.md:340-369,415-433` documents this happening live: a wall-capped lap reverted, and *"treadmill impossibly went 4->2, phantom 'movement' re-fired"* (`:417-418`); the P1 `phases_closed` record was wiped so *"TARGET's stage check reads RATCHET phases_closed, which now says P1 never closed."* This also caused a **false P2 closure** that a foreman had to manually void (`RATCHET.json:16`; `ESCALATIONS/20260611T003810-c17-d23-false-p2-closure.md`).

The deeper treadmill trap (`product_scoreboard.csv:11`, `FAILURE_MODES.md:432-442`): once `catch_rate_worst` hits its **ceiling of 1.0** and P1 is already in `phases_closed`, **honest live work is mechanically invisible to the stub scoreboard** — so real progress *"burns treadmill"* and the K=5 detector fires on genuine work. This is *why* `factory/` exists and was re-aimed repeatedly (`TARGET.md` v3→v8.1). `RATCHET.json:24` currently shows `treadmill_count: 2`. The framing the audit asks about is present and accurate: the factory's whole point is to escape grinding, and the ratchet itself has been one of its leakiest joints.

---

## 8.9 Abandoned directions / dead scaffold / large stubs

- **`actions/` package — superseded stub layer.** `actions/{base,browser,connector}.py` ("Stub for the scaffold," `:14,:18,:20`) is the original adapter abstraction, replaced by `hands/`. Still in the tree, imported nowhere load-bearing — dead scaffold.
- **`overnight/` — the per-recipe / one-off-track treadmill the factory was built to escape.** `overnight/track_{a,b,c}/` are standalone scripts (the real-calendar laps, a parallel decider, the Gmail-draft track) referenced throughout `STATUS.md:44-113`. `track_b/score_existing_engine.py` even grades the shipped decider but is *"Not wired in (future supervised change)"* (`STATUS.md:105`). These are exactly the kind of side-built graders/parts the CONSTITUTION's anti-staging law warns against (`HANDOFF:217-219`: *"never build graders/parts/'the machine that builds' instead of a touchable product"*).
- **`demo/` — a single static `anticipy_workings.html`** (one file), not a live product path.
- **`autopilot/` — the explicitly RETIRED loop** (per the audit brief), superseded by `factory/`. Still present as historical control-plane.
- **`notes/proactive_room{1..7}.md`, `wave{1,2}_log.md`, `agent_recipes.md`** — design-iteration logs from earlier waves; `agent_recipes.md` is the per-store recipe direction the factory exists to move *past*.

---

## 8.10 Bottom line (brutal, evidence-based)

| Area | State | Hardest evidence |
|---|---|---|
| Inference core / safety floor | ✅ **Real & proven** | Suite 87/87 green; `safety_mega_eval` in-gate; mega-eval 0 breaches |
| Money hard-stop | ✅ Real (safe by *absence*) | No payment hand exists; `WRITE_INTENTS` has none (`api_hand.py:31`); guard is at the action layer |
| Voice/text | ⚠️ Legs proven, **round-trip + gate_P3 unproven**; once **fabricated** | `HANDOFF:76-88` |
| API arm (Calendar) | ⚠️ Authorize=completed, but **no live write proven in current wiring** | `STATUS.md:21`; `PENDING:26-28` |
| API arm (Gmail draft / Slack) | ❌ Gmail draft **scope-gated** (`gmail.compose` pending); Slack write **fails closed** (no read-back) | `STATUS.md:24`; `api_hand.py:77,452` |
| Per-person token mesh | ⚠️ **Wired now** (handoff stale) but **inert** — always shared-key fallback | `control_core.py:188`; `api_hand.py:184` |
| Browser arm | ⚠️ Real Chrome arm = flaky loop; reliable arm = **orphaned + logged-out** | `main.py:1214`; `HANDOFF:108-110,202-205` |
| Onboarding Chrome-scrape → mesh | ⚠️ **Half-built**: transport done both ends, **no autonomous trigger, no needs_auth→connected step** | `connection_scan.py`; `test_onboard_scan.py:1-4`; `PENDING:31` |
| Pendant / Start Listening / SwiftUI delivery | ❌ Stubs (`NotImplementedError` / ~29 lines / "nothing surfaced") | `pendant_phone.py:17`; `HANDOFF:265`; `channels/app.py:1` |
| 5-day Owner Test (the finish line) | ❌ 0 of 5 | `HANDOFF:102` |

**The pattern is consistent and, to the repo's credit, honestly self-documented:** the deterministic *middle* is bulletproof and the safety floor genuinely holds; everything that requires a live external credential or the user's real logged-in browser is either fail-closed-by-design, wired-but-never-fired, or one orphaned endpoint away from working. The two things I'd flag as most at-odds with the project's own narrative are (1) the **token-mesh "no broker" claim in the master handoff is stale** — the broker is wired, it's just starved of per-user tokens — and (2) the **onboarding scrape is more built than "UNBUILT" implies** (both transport halves exist), but is **not closed end-to-end** (no live trigger, no connection step), which is the more precise and more useful truth.

---

# SECTION 9: INTEGRATING A BLE-STREAMING PENDANT — THE PLAN

## 9.0 The one-paragraph answer

You do **not** modify this engine to add the omi pendant. The action door already exists, is already typed for a pendant source, and already does NL→task inference behind it. The omi macOS app already does BLE + Opus decode + Deepgram transcription on this Mac. So the entire integration is **one new, additive sibling process** — call it `pendant-bridge/` — that watches the omi app's transcript output and, for each finalized utterance, makes one HTTP call: `POST http://127.0.0.1:8787/owner/ingest` with `{"text": "<transcript>", "source": "pendant_phone", "execute_actions": true}`. The engine's own proactive brain (triage → decider → harm-line) infers the task, asks before money, and stays silent on vents. **Zero engine files change.** I verify each of these claims below with `file:line`.

---

## 9.0a What the brief got right, and the one thing that's already true in code

The audit reconciliation said Deepgram/Tauri/etc. don't exist *in this repo*. That holds — but the **pendant scenario is different from the user's earlier "stack" claims**: here Deepgram lives in the **omi desktop app** (external, third-party, BasedHardware/omi), which is a legitimate upstream we integrate *with*, not a phantom inside this engine. The omi app is the transcription producer; this engine is the action consumer. They are correctly decoupled.

And the decisive clue the brief flagged is real and stronger than expected:

**The engine is already typed for the pendant.** `engine/anticipy_engine/owner_mode.py:20`:

```python
OwnerSource = Literal["pay_to_try", "start_listening", "mp3", "transcript",
                      "typed", "app", "mac_mic", "pendant_phone"]
```

`"pendant_phone"` is already a first-class accepted `source`. The capture seam is reserved too — `engine/anticipy_engine/capture/pendant_phone.py` is a deliberate empty socket (more on it in 9.0b). So the engine authors *designed the front door to accept this exact input*; the bridge just has to knock on it.

---

## 9.0b What the two existing capture files actually are (and whether they're the fit)

I read both in full.

**`engine/anticipy_engine/capture/pendant_phone.py`** — a 21-line **reserved stub**, not a working path. Its entire body:

```python
class PendantPhoneSource(CaptureSource):
    name = "pendant_phone"
    def start(self) -> None:
        raise NotImplementedError("PendantPhoneSource is wired in a later chunk")
    def stop(self) -> None:
        raise NotImplementedError("PendantPhoneSource is wired in a later chunk")
```

Its docstring (`pendant_phone.py:1-7`) states the design intent verbatim: *"pendant -> phone -> this engine. It is intentionally unimplemented... it exists so the socket is reserved and proven to share the exact `CaptureSource` interface. When the pendant chunk lands, only this file gains a body — the engine does not change."* It subclasses `CaptureSource` (`capture/base.py:19`), whose `_emit(text)` builds a `CaptureEvent(source=self.name, text=text)` and pushes it to an in-process `EventSink` (`base.py:35-39`).

**Is it the fit?** It is the *officially blessed in-process* fit — but it is **not the surgical one for the omi scenario**, and here is the precise reason. `CaptureSource` is an **in-process** abstraction: a sink callback inside the engine's own Python process (`base.py:16` `EventSink = Callable[[CaptureEvent], None]`). To use it you would have to (a) write a real body for `PendantPhoneSource`, (b) get the omi app's transcripts *into the engine process*, and (c) register and `start()` the source somewhere in the engine lifespan. That is **editing engine files** and **coupling the engine to omi's IPC** — exactly what 9d says to avoid. The stub is a fine *eventual* home if the pendant audio ever flows through the engine itself, but the omi app already owns capture+ASR, so the engine never needs to see audio at all — only finished text. The HTTP door (`/owner/ingest`) is the decoupled equivalent of the `EventSink`, reachable from a *separate* process. **Recommendation: leave `pendant_phone.py` untouched; use the HTTP door from a sibling bridge.** (If a purist later wants the capture-seam version, the bridge can be ported into a `PendantPhoneSource.start()` body with no contract change — same `source="pendant_phone"`, same text — which is the whole point of the reserved socket.)

**`engine/anticipy_engine/capture/transcribe.py`** — a generic **local audio-file → timestamped text** transcriber (`transcribe_audio(path)`, `transcribe.py:32`). It is the MP3/upload path's engine: it probes duration with `ffprobe`, runs `ffmpeg silencedetect` to find speech intervals (`_detect_silence`, `:157`), chunks them, and transcribes each chunk with a **local Whisper model** (`_load_whisper_model`, default `tiny.en`, `:76,132-135`), emitting `[hh:mm:ss-hh:mm:ss] text` lines (`:99`). It is wired only into `/owner/ingest-file` (`main.py:747-760`), which transcribes a *staged audio file on disk* then calls the same `owner_ingest`.

**Is it the fit?** **No, and it must be bypassed entirely.** It assumes a finite file at rest, shells out to ffmpeg/Whisper, and is built for batch realday MP3s — it is the wrong tool for a live BLE stream, and it would *duplicate* the transcription the omi app already did with Deepgram. The pendant scenario's transcript is **already text** by the time it reaches us; running it back through `transcribe.py` would be redundant and wrong. So the bridge sends **text** to `/owner/ingest` (not audio to `/owner/ingest-file`). `transcribe.py` stays for the MP3 upload feature; the pendant path never touches it.

---

## 9a. Where does new code live? → A new sibling bridge process (`pendant-bridge/`)

**Decision: an additive sibling process — a small Python (or Swift) daemon in a new top-level folder `pendant-bridge/` — that watches the omi app's transcript output and POSTs to the engine. It is launched separately (its own launchd plist), and the engine never imports it.** Justification, grounded in Sections 3–6:

| Option | Verdict | Why (from §3–§6) |
|---|---|---|
| **Patch the Swift menubar shell** (`macapp/`) | ✗ | `macapp/` only *boots and supervises* the engine (`boot.sh:14-18` curls `/readiness`, then `nohup`s uvicorn). It is not an intake path. The pendant producer is the **omi** Swift+Rust app, a *different* application we don't own; bolting transcript-forwarding into our menubar app couples two unrelated shells. No leverage. |
| **New engine module + wire `PendantPhoneSource`** | ✗ (avoid) | Requires editing engine files (a real `start()` body, lifespan registration), and forces omi→engine IPC *inside* the engine process. §3.1 shows the engine runs background work as **asyncio tasks on its own loop** (tick at `main.py:82-90`, inbound poller at `:93-101`); adding a BLE/omi consumer task means new failure modes inside the one process that must never crash (it holds the proactive brain, the WS to Chrome, the Twilio loops). Forking the engine for an input source it already exposes over HTTP is strictly worse. |
| **Additive sibling bridge → HTTP** ✅ | **Chosen** | §6 establishes `POST /owner/ingest` as *"the single shared Action Engine door"* and §3.0 proves the engine is a loopback HTTP server (`127.0.0.1:8787`). A separate process that just does `omi-transcript → HTTP POST` is the smallest possible surface: it can crash, restart, be version-pinned, and be tested in isolation **without ever risking the engine**. It mirrors how the engine *already* takes input from out-of-process producers — e.g. the Chrome extension over WS (`/ws/extension`, §3.0 ESTABLISHED edge) and the InboundPoller pulling Twilio SMS (§3.1) — both feed the same brain from outside. The bridge is just one more outside producer. |

**Don't fork the engine** because the engine is the single trusted custodian of the safety floor (harm-line, money wall, cardinal-sin vent guard — `control_core.py:611` calls out the "persist-side cardinal-sin guard"). Every input must pass *through* that floor, not around it. A sibling that can only reach the engine via the public door **cannot bypass the floor even if it has a bug** — the worst a buggy bridge can do is send too much or too little text, which the triage/decider/harm-line then judge. That containment is the entire architectural argument.

```
pendant-bridge/                 # NEW, additive, never imported by engine
  bridge.py                     # watch omi transcripts -> POST /owner/ingest
  config.toml                   # engine URL, owner token (if set), source tag
  com.anticipy.pendant-bridge.plist   # its own launchd agent (optional)
```

---

## 9b. The bridge↔engine contract (the real endpoint, real JSON)

**Use `POST /owner/ingest`. Not `/event`, not `/agent/act`.** Justified against the actual §6 surface:

- **`/owner/ingest`** (`main.py:718-722`) is *"One shared Action Engine intake for typed transcript, MP3, listening, and pay-to-try."* It runs the **full proactive spine** (triage → decider → harm-line) when `execute_actions:true` (`control_core.py:595-596` calls `_spine_card`), which is exactly the act/ask/silent brain with the money-asks-first and vent-silent guarantees. This is the door designed for messy human speech. **✓ chosen.**
- **`/event`** (`main.py:713-715` → `core.feed`) is the lower-level spine entry used by the persona/realday *test harness*. It bypasses the owner-card board (no `OwnerTaskCard` persistence, no dedupe via `_existing_owner_card`). It would *work* for safety (same spine) but you lose the durable owner-card record and the "shared door" semantics §6 calls canonical. **✗ not the product door.**
- **`/agent/act`** (`main.py:1214` → `browse_act`) is the **browser vision arm**, not an intake — it expects a *concrete browser task*, not a raw transcript, and it has no triage/decider/vent guard in front of it. Sending raw pendant speech here would skip the entire act/ask/silent brain and the cardinal-sin floor. **✗ would be a safety regression — never do this.**

**The request the bridge sends** (per `OwnerIngestIn`, `main.py:318-322`):

```http
POST /owner/ingest HTTP/1.1
Host: 127.0.0.1:8787
Content-Type: application/json
x-anticipy-owner-token: <token>        # ONLY if ANTICIPY_OWNER_API_TOKEN is set; this engine has it UNSET
                                        # (live /readiness => owner_api:"local"), so the header is omitted today

{
  "text": "remind me to email coach Dave before practice tomorrow",
  "source": "pendant_phone",
  "meta": { "device": "omi-xiao-nrf52840", "utterance_id": "u-8831", "ts": "2026-06-15T15:21:04Z" },
  "execute_actions": true
}
```

Two load-bearing fields:

- **`source": "pendant_phone"`** — already an accepted literal (`owner_mode.py:20`), so it routes/labels correctly with no engine change.
- **`execute_actions": true`** is **mandatory** to actually act. It defaults to `False` (`main.py:322`); §6 is explicit that a plain ingest only *previews* cards (`card_for_line`) and does **not** run the spine. To get act/ask/silent you must pass `true` (`control_core.py:595`). For an always-on pendant you want `true`; for a "dry-run while I trust it" rollout you can ship the bridge with `false` first and read `/owner/cards` to watch what it *would* do, then flip to `true`.

**The response** the bridge gets back is an `OwnerIngestResult` (`owner_mode.py:49-53`, returned via `result.model_dump(mode="json")` at `control_core.py:632-634`). Shape, with the fields that matter for the bridge to log:

```json
{
  "source": "pendant_phone",
  "observed_lines": [ { "line_no": 0, "text": "remind me to email coach Dave before practice tomorrow" } ],
  "cards": [
    {
      "id": "c_a1b2c3",
      "source": "pendant_phone",
      "line_no": 0,
      "source_text": "remind me to email coach Dave before practice tomorrow",
      "title": "Email coach Dave before practice",
      "disposition": "ask",            // do | ask | remember | blocked  (owner_mode.py:21)
      "route": "voice_text",           // api | browser | voice_text | memory
      "action": "...",
      "args": { },
      "confidence": 0.75,
      "reason": "...",
      "status": "open",
      "proof": [ ],
      "execution": { "decision": "ask", "goal_id": "g_...", "ask_id": "a_...", "goal_state": "..." }
    }
  ],
  "ignored_line_count": 0
}
```

Per-card field meanings are from `OwnerTaskCard` (`owner_mode.py:30-46`): `disposition` is the brain's verdict, `execution` (`:44-46`) is *"what the engine actually DID with this card — {decision, goal_id, ask_id, goal_state}; None until an execution path runs it."* A **vent** produces **no card** — it is counted in `ignored_line_count` and the persist-side cardinal-sin guard ensures nothing durable is written (`control_core.py:610-616`). So the bridge can treat "spoke a frustrated sentence → `cards:[]`, `ignored_line_count:1`" as the *correct, safe* outcome, not an error.

**The bridge needs no understanding of any of this.** Its entire job is: assemble the JSON above, POST it, log the response. The brain is on the engine side of the wall.

---

## 9c. Transcript → task: forward raw text, let the engine's brain parse

**Yes — the engine already parses natural language into tasks. The bridge must NOT pre-parse.**

The whole point of `/owner/ingest` is that it takes *messy human speech* and infers structured cards. Inside `owner_ingest` (`control_core.py:576-617`):
1. `self.owner_mode.observe(text)` splits the raw stream into `OwnerObservedLine`s (`:576`),
2. each line goes through `card_for_line` / `_spine_card` → triage → decider → harm-line (`:589-596`),
3. the regex+LLM router in `owner_mode.py` (the `_TIMEISH`/`_REMEMBER`/`_SEND`/`_BROWSER`/`_MONEY`/`_VENT_OR_JOKE` matchers at `:56-89`, then the model gate/decider) is what turns "remind me to email Dave" into an `ask` card on the `voice_text` route.

So **the bridge forwards the raw transcript string verbatim** and gets task inference for free. This is also the safest design: a pre-parse step in the bridge would be a *second, untested* place where vents could be misread as tasks — re-implementing the cardinal-sin judgment outside the safety floor. Don't.

**Concretely, the bridge does no LLM call at all.** Its transform is:

```python
# pendant-bridge/bridge.py  (illustrative; lives ONLY in the sibling folder)
import httpx
ENGINE = "http://127.0.0.1:8787"

async def on_final_utterance(text: str, meta: dict) -> None:
    text = text.strip()
    if not text:
        return                       # omi sometimes emits empty/partial finals — drop
    try:
        r = await httpx.AsyncClient(timeout=30).post(
            f"{ENGINE}/owner/ingest",
            json={"text": text, "source": "pendant_phone",
                  "meta": meta, "execute_actions": True},
            headers=_owner_headers(),    # {} unless ANTICIPY_OWNER_API_TOKEN is set
        )
        r.raise_for_status()
        result = r.json()            # OwnerIngestResult — log cards & ignored_line_count
        log_locally(text, result)    # bridge-side observability (see 9e)
    except Exception as exc:
        # FAIL-OPEN on the BRIDGE side only: never crash, never retry-storm.
        # The engine is the source of truth; a dropped utterance is acceptable,
        # a duplicated ACTION is not -> do NOT blindly retry POSTs that may have acted.
        log_locally(text, {"error": f"{type(exc).__name__}: {exc}"})
```

**The only judgment the bridge needs** is *utterance boundaries*: omi/Deepgram emit interim (partial) and final results. Forward **only finals** (and optionally debounce a short trailing silence so "email Dave… before practice tomorrow" arrives as one line, not two). That is a transcription-segmentation concern, not task parsing — and getting it slightly wrong is harmless because the engine's `observe()` re-splits the stream anyway (`control_core.py:576`).

**If (later) you *do* want a pre-filter** — e.g. to suppress obvious noise before spending an engine round-trip — keep it dumb and fail-open: a length/keyword gate, never a task decision. Suggested shape if asked for one:

```
prompt (cheap, optional): "Is the following a complete spoken sentence worth recording? Answer Y/N only.\n\n<text>"
fail-open rule: on timeout / error / non-Y-N output  -> FORWARD ANYWAY (treat as Y).
```

The fail-open direction is deliberate: a bridge bug should *over*-forward to the engine (which then safely judges), never *suppress* a real task. The engine, not the bridge, owns "is this a task vs a vent."

---

## 9d. Repo changes vs additive — strongly additive, zero engine edits

**Required engine-file changes: none.** I checked every dependency:

- The endpoint exists (`main.py:718`). ✓
- The source literal exists (`owner_mode.py:20`). ✓
- The brain, harm-line, vent guard, and owner-card persistence all already run behind it (`control_core.py:563-634`). ✓
- The token gate already allows an unauthenticated loopback caller when `ANTICIPY_OWNER_API_TOKEN` is unset (§6; live `/readiness` → `owner_api:"local"`). ✓

So everything new is a **new top-level `pendant-bridge/` folder** + its own optional launchd plist. Nothing under `engine/`, `macapp/`, `factory/`, or `personas/` is touched.

**The one thing I'd flag as *not* code but *configuration*:** if you later set `ANTICIPY_OWNER_API_TOKEN` (recommended once the bridge is always-on, so a random loopback process can't drive the brain), the bridge must read that same token and send it as `x-anticipy-owner-token` (`main.py:138-143`). That is a shared-secret config item, not an engine edit — the gate already supports it. Until then, on *this* machine, no header is needed.

**Anything that would force an engine edit? Only one hypothetical:** if you decided the pendant path must run *through the in-process capture seam* (`PendantPhoneSource`) instead of HTTP, you'd write a body in `capture/pendant_phone.py` and register the source in lifespan. That is the *blessed-but-heavier* route the stub reserves. I recommend against it for v1 precisely because it's the only design that touches engine files; revisit only if you ever need the engine to own the BLE stream itself.

---

## 9e. Observability — where transcript→parsed→engine-called→result is visible

Four layers, in order of "closest to the truth":

1. **The glassbox JSONL (the engine's append-only activity ledger).** Confirmed live path on *this* machine: **`/Users/omarebrahim/Anticipy/.anticipy-data/glassbox.jsonl`** (constructed at `control_core.py:159` as `GlassBox(base / "glassbox.jsonl")`, where `base = ANTICIPY_DATA_DIR or .anticipy-data`, `control_core.py:42-43`; I verified the file exists and is being written, 6732 bytes, mtime 15:16 today). Every ingest writes an `owner_ingest` event with `{source, lines, cards, ignored, execute_actions}` (`control_core.py:627-631`). The decider/harm-line write their own events (`suppressed`, `ask_held`, `decider_deferred`, etc. — `proactive.py:249-259`). It is append-only JSONL (`glassbox.py:30-33`), byte-capped at 8 MB with old-head drop (`glassbox.py:36-60`). **Read it with `tail -f` (read-only) for the live "what did it just do" feed.**
2. **`GET /glassbox`** (`main.py:1090`, `?limit=`) — the same feed over HTTP, safe GET. Use this if you don't want to touch the file.
3. **`GET /owner/cards`** (`main.py:776` → `owner_cards`) — the durable owner-card board: every card the ingest produced, with `disposition`, `route`, `status`, and the `execution` outcome (`owner_mode.py:30-46`). This is where you confirm "the pendant utterance became an `ask` card with goal_id g_…". Cards persist to disk under `${data_dir}/owner_cards/<id>.json` (`control_core.py:726`), surviving restarts.
4. **`GET /pending`** (`main.py:1095` → `pending_asks`) and **`GET /status`** (`main.py:585`) — `/pending` lists asks awaiting YES/NO (an `ask` card lands here); `/status` shows live counts (`pending_count`, `open_loop_count`) and channel readiness. The live `/status` already reports `pending_count:3`, so you can watch that number tick after a pendant utterance that produces an ask.

Plus **bridge-side logging** (its own `log_locally` in 9c): keep a small `pendant-bridge/bridge.log` of `{utterance, http_status, cards, ignored, error}` so you can prove the bridge *sent* what it heard, independent of the engine. The two logs together give end-to-end traceability: bridge.log shows transcript→POST, glassbox shows POST→parse→action.

```
visibility chain:
  omi transcript ──▶ pendant-bridge/bridge.log  (heard + POSTed)
                         │
                         ▼ POST /owner/ingest
  engine ──▶ .anticipy-data/glassbox.jsonl  (owner_ingest, decider, harm-line)   ◀── GET /glassbox
        ├──▶ .anticipy-data/owner_cards/<id>.json                                  ◀── GET /owner/cards
        ├──▶ pending asks                                                          ◀── GET /pending
        └──▶ counts                                                               ◀── GET /status
```

---

## 9f. End-to-end test plan (SAFE first — no real SMS / calendar / browser)

The currently-running PID 66506 is **LIVE** (`channels.mode:"live"`, real Twilio configured — confirmed in live `/status`). **Do not test against it** — a successful ingest could place a real call/SMS. Stand up a **separate, sandboxed engine on a different port with mock channels and mock hands**, exactly the posture `scripts/run_suite.sh:15-16` uses for safety (`ANTICIPY_HANDS_MODE=mock`, `ANTICIPY_CHANNELS_MODE=mock` — the comment at `run_suite.sh:11` is explicit that mock channels is *"load-bearing for SAFETY: without it, a live .env.local makes the channels tests place REAL Twilio calls/SMS"*).

**Step 0 — launch a safe engine on a spare port (8788), mock everything, isolated data dir:**

```bash
cd /Users/omarebrahim/Anticipy
ANTICIPY_MODEL_PROVIDER=stub \
ANTICIPY_HANDS_MODE=mock \
ANTICIPY_CHANNELS_MODE=mock \
ANTICIPY_DATA_DIR=/tmp/anticipy-pendant-test \
ANTICIPY_TICK_SECONDS=0 \
PYTHONPATH=engine \
engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8788
```

- `ANTICIPY_MODEL_PROVIDER=stub` → the deterministic in-process gate/decider (§4), zero paid API calls.
- `mock` hands/channels → no real Gmail/Calendar/Twilio side effects.
- separate `ANTICIPY_DATA_DIR` → its own glassbox + owner_cards, doesn't touch the live ledger.
- `ANTICIPY_TICK_SECONDS=0` → no background clock firing reminders; you drive everything by hand.
- Different port (8788) → cannot collide with the live 8787 engine.

Confirm it's the sandbox and not live: `curl -s http://127.0.0.1:8788/status` should show `channels.mode:"mock"`.

**Step 1 — simulate a pendant transcript WITHOUT hardware (the core proof):** just `curl` the chosen door with a sample utterance. This is the same JSON the bridge would send.

```bash
curl -s http://127.0.0.1:8788/owner/ingest \
  -H 'Content-Type: application/json' \
  -d '{"text":"remind me to email coach Dave before practice tomorrow",
       "source":"pendant_phone",
       "meta":{"device":"omi-sim","utterance_id":"t1"},
       "execute_actions":true}' | python3 -m json.tool
```

Expect an `OwnerIngestResult` with one card, `disposition` `ask`/`remember`, and (because hands are mock) a safe simulated `execution`. **No SMS is sent — channels are mock.**

**Step 2 — prove the vent floor (the cardinal-sin test):** send a frustrated non-task and assert it produces **no card**.

```bash
curl -s http://127.0.0.1:8788/owner/ingest \
  -H 'Content-Type: application/json' \
  -d '{"text":"ugh I swear this stupid printer is going to kill me",
       "source":"pendant_phone","execute_actions":true}' | python3 -m json.tool
```

Expect `"cards": []` and `"ignored_line_count": 1` — the vent guard (`control_core.py:610-616`) refused to act. This is the single most important pass for a pendant: ambient speech is mostly *not* tasks.

**Step 3 — prove the money wall (ask-before-spend):**

```bash
curl -s http://127.0.0.1:8788/owner/ingest \
  -H 'Content-Type: application/json' \
  -d '{"text":"order me lunch from the usual place",
       "source":"pendant_phone","execute_actions":true}' | python3 -m json.tool
```

Expect a card whose `disposition` is `ask`/`blocked` and route `browser` — money never auto-executes (`_MONEY` matcher `owner_mode.py:76`; the runner's hard stop `browser_use_runner.py:63-66`). Then `curl -s http://127.0.0.1:8788/pending` to see the human-gate ask.

**Step 4 — read the result back (observability proof), all read-only:**

```bash
tail -n 20 /tmp/anticipy-pendant-test/glassbox.jsonl          # owner_ingest + decider events
curl -s http://127.0.0.1:8788/owner/cards | python3 -m json.tool   # the durable cards
curl -s http://127.0.0.1:8788/pending     | python3 -m json.tool   # the asks awaiting YES/NO
curl -s http://127.0.0.1:8788/status                                # counts moved
```

You should see the `owner_ingest` glassbox line with `"source":"pendant_phone"` matching each curl, the cards on the board, and `pending_count` incremented by the ask.

**Step 5 — close the loop with the real hardware (only after Steps 1–4 pass):** run the omi macOS app + flashed XIAO nRF52840 pendant, start the bridge pointed at the sandbox engine (`ENGINE=http://127.0.0.1:8788`), speak *"remind me to email coach Dave before practice tomorrow"* into the pendant, and watch `tail -f /tmp/anticipy-pendant-test/glassbox.jsonl` plus the bridge's own `bridge.log`. Success = the spoken sentence appears in bridge.log as a POST, then a matching `owner_ingest` event with `source:"pendant_phone"` appears in the glassbox, then a card shows in `/owner/cards`. Only after this is green against the sandbox do you point the bridge at the live `:8787` engine.

**Why this proves "speak → action":** Step 5 exercises the full physical chain; Steps 1–4 prove the engine half deterministically and safely *without* hardware, so when Step 5's transcript matches Step 1's curl result you've shown the bridge is a faithful, side-effect-free transport and the brain did the inference.

---

## 9g. The full data-flow diagram

```
 ┌─────────────────────┐   BLE (Opus audio frames)   ┌──────────────────────────────────────┐
 │  Seeed XIAO          │ ──────────────────────────▶ │  omi macOS desktop app (Swift + Rust) │
 │  nRF52840 Sense      │   GATT notify, advertise    │  • BLE central, Opus decode           │
 │  (omi firmware)      │                             │  • Deepgram streaming ASR  ──────┐    │
 └─────────────────────┘                             └──────────────────────────────────┼────┘
                                                                                         │ final transcript text
                                                          (interim results dropped;      │ (string + ts)
                                                           only FINAL utterances cross)  ▼
                                                      ┌───────────────────────────────────────┐
                                                      │  pendant-bridge/  (NEW sibling proc)  │  ← additive, never imported by engine
                                                      │  • debounce -> 1 final = 1 line       │
                                                      │  • NO task parsing, NO LLM            │
                                                      │  • bridge.log (heard + POSTed)        │
                                                      └───────────────┬───────────────────────┘
                                                                      │ POST /owner/ingest
                                                                      │ {text, source:"pendant_phone",
                                                                      │  execute_actions:true}
                                                                      ▼  HTTP loopback 127.0.0.1:8787
 ╔══════════════════════════════════════════════════════════════════════════════════════════════╗
 ║  FastAPI ENGINE  (engine/anticipy_engine/main.py, 127.0.0.1:8787)  — UNCHANGED                 ║
 ║                                                                                                ║
 ║   /owner/ingest ─▶ ControlCore.owner_ingest()  (control_core.py:563)                           ║
 ║        observe(text)  ─▶  per line ─▶ _spine_card()  ─▶  PROACTIVE SPINE                        ║
 ║                                            triage ──▶ decider ──▶ harm-line                     ║
 ║                                                            │                                   ║
 ║                         ┌──────────────────┬───────────────┼───────────────┐                   ║
 ║                         ▼                  ▼               ▼                ▼                   ║
 ║                       ACT                ASK            SILENT           BLOCKED                ║
 ║                   (api/browser/      (/pending →      (vent: no       (money: never            ║
 ║                    voice_text hands)  /resolve YES)    card, counted   auto-executes)          ║
 ║                                                        in ignored)                             ║
 ║                         │                                                                      ║
 ║   writes ──▶ .anticipy-data/glassbox.jsonl   +   owner_cards/<id>.json   +   pending asks      ║
 ╚══════════════════════════════════════════════════════════════════════════════════════════════╝
                                                                      │
                          observability (all read-only) ◀─────────────┘
                          GET /glassbox · GET /owner/cards · GET /pending · GET /status
                          tail -f /Users/omarebrahim/Anticipy/.anticipy-data/glassbox.jsonl
```

**Bottom line:** the pendant integration is *one sibling process and zero engine edits*. The engine authors already reserved the `pendant_phone` source (`owner_mode.py:20`) and the capture socket (`capture/pendant_phone.py`), and already built the messy-speech action door (`/owner/ingest`, `control_core.py:563`) with the safety floor behind it. The omi app already does BLE + Deepgram. The only missing 50 lines are a transport that carries omi's finished transcript text to that door — and because it can only reach the engine through the public, floor-protected endpoint, even a buggy bridge cannot commit the cardinal sin or spend money on its own.

---

## SECTION 10: RISKS AND OPEN QUESTIONS

This section catalogs what code-reading alone cannot settle, the single most dangerous assumption a pendant integration would rest on, the one thing to verify before writing any integration code, and a short list of decision-shaped questions only Omar can answer.

---

### 10.1 What I could NOT fully determine from code-reading

| # | Question | Why code can't answer it | What I'd need |
|---|----------|--------------------------|---------------|
| R1 | **Is there a working "audio in → transcript out" path that produces a live stream?** | The only transcriber, `engine/anticipy_engine/capture/transcribe.py:32` (`transcribe_audio`), is **batch, file-oriented** — it `ffprobe`s a whole file, silence-detects, chunks, and runs on-device Whisper (`tiny.en`, `transcribe.py:76`). It cannot accept a live socket/stream. The *streaming* capture sources are all **stubs** (see R2). So a transcript exists for *recorded MP3s on disk*, not for *a pendant talking in real time*. | Confirmation of whether the pendant emits finished audio files (→ existing batch path works) or a live stream (→ no path exists). |
| R2 | **Does any real capture source exist, or are they all empty?** | `PendantPhoneSource.start()` literally `raise NotImplementedError("PendantPhoneSource is wired in a later chunk")` (`capture/pendant_phone.py:17`). `MacMicSource` is also a stub — `start()` just sets `self._running = True` with the comment "*Stub: no real audio yet*" (`capture/mac_mic.py:20-25`); only `emit_stub(text)` injects a fake utterance. The `Intake` sink (`capture/intake.py`) is an **in-process Python list**, not an HTTP/socket endpoint. The capture seam is *designed* (clean `CaptureSource`/`EventSink` ABC in `capture/base.py`) but **unbuilt**. | Nothing more from code — the conclusion is firm: **no source emits real audio today.** |
| R3 | **Is the omi / pendant macOS app's transcript exposed locally (socket/file/stdout)?** | That app is **not in this repo.** Per the audit's verified reconciliation, the Tauri/Parakeet desktop shell lives in the sibling, out-of-scope `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL` (referenced from `logs/journal.md`, `logs/verdicts/*`), not here. I cannot read its IPC surface. | Omar to tell me the pendant app's local output contract (named pipe? file tail? localhost WS? BLE?), or permission to read DEV-FINAL. |
| R4 | **What does `core.owner_ingest` actually *do* downstream — and is the proactive brain reliable enough to trust with raw pendant text?** | The route is thin (`main.py:718-721`); the substance is in `core/proactive.py` + `proactive/`. I read the contract (triage→decider→harm-line→act/ask/silent) but did **not** trace every branch, nor measure the false-positive rate on messy real speech. The CLAUDE.md history itself flags "10 real breaches after a 'converged' claim" (`memory/safety-mega-eval-gate.md`). | The persona/safety-eval numbers against *pendant-grade* (noisy, run-on, mis-transcribed) input — not clean typed transcripts. |
| R5 | **Will whisper `tiny.en` transcription quality be good enough that the brain's inference isn't garbage-in?** | `transcribe.py:76` hardcodes `tiny.en` as the default model with aggressive drop-heuristics (`_drop_segment`, `transcribe.py:294` drops on `no_speech_prob ≥ 0.85`, `avg_logprob ≤ -1.25`). `tiny.en` mis-hears names/numbers badly — exactly the tokens that drive task inference. | A real transcription-accuracy measurement on pendant audio. |
| R6 | **Does `/agent/act` / the Arcade hand have a *real* money/vent stop, or just an asserted one?** | The docstring claims "money/checkout/login as HARD STOPS in the runner's action guard" (`main.py:1216-1218`), but I read the route, not the guard implementation in `hands/browser_use_runner.py`. The cardinal-sin (acting on a vent) and money-stop are *the* product invariants; trusting the docstring is unsafe. | A read of the actual guard + a live (sandboxed) test of a vent + a payment URL. |
| R7 | **Why does `.env.local` disagree with the running process, and which is authoritative?** | The on-disk file says `ANTICIPY_CHANNELS_MODE=mock`, but the **live PID 66506 was launched with `ANTICIPY_CHANNELS_MODE=live`** (`ps eww` on the running engine) and `/status` reports `channels.mode: "live"`, `twilio_configured: true`. The file is **stale/misleading** relative to runtime. I cannot tell from code which launch wrapper set the override or whether a restart would flip it back to mock. | Omar to confirm the canonical launch command / which mode the engine *should* run in. |

---

### 10.2 The riskiest assumption a pendant integration would rest on

> **"There is a live transcript pipeline that can reach the engine."**
> **There is not.** This is the load-bearing falsehood.

Concretely, a pendant integration silently assumes a chain that is **broken at both ends inside this repo**:

```
 pendant mic ──▶ [omi/Parakeet app] ──▶ ??? ──▶ engine intake ──▶ proactive brain
   (hardware)      (NOT in this repo;        (NO real-time           (REAL, running
                    DEV-FINAL, hands-off)     wire exists)            on :8787)

 GAP 1: capture sources are stubs        GAP 2: Intake is an in-process list,
 PendantPhoneSource.start() raises        not a network endpoint. The only HTTP
 NotImplementedError                      door is POST /owner/ingest, and it takes
 (capture/pendant_phone.py:17)            finished TEXT, not audio
                                          (main.py:718, OwnerIngestIn.text:319)
```

The engine is real and listening; the *brain* is real; but the **"audio → text → engine" transport is the part that does not exist.** Any integration that assumes "the transcript just shows up" will compile, will look wired (the `CaptureSource` ABC is clean), and will do **nothing**, because nothing calls a real `start()` and nothing turns a live audio stream into `CaptureEvent`s. The realistic path is **not** through the dormant capture seam at all — it is to POST already-finished transcript text to `/owner/ingest` (`main.py:718`), which means the *pendant side* owns transcription.

**Second-riskiest assumption: "the engine is a safe sandbox to poke."** It is the opposite. The live process (PID 66506) reports via `/status` and `/readiness`:
- `channels.mode: "live"`, `twilio_configured: true`, `call: "live_ready"`, inbound polling active;
- Arcade Google (Calendar + Gmail) = **live**; Browser hand into the user's real Chrome (CDP :9222) = **live**;
- `ANTICIPY_HANDS_MODE=live` in the running env.

And the owner-token gate is **OFF**: `ANTICIPY_OWNER_API_TOKEN` is unset (absent from `.env.local`; the middleware at `main.py:243` only enforces *when the token is set*), so **any localhost POST is unauthenticated.** Therefore a careless `POST /owner/ingest` with `execute_actions=true`, or any `POST /agent/act`, can send a **real SMS, place a real call, create a real calendar event, or drive the real browser.** The one mercy: `execute_actions` **defaults to `False`** (`main.py:322`), so a *default* ingest is plan-only — but that safety is one boolean away from off, and `/agent/act` has no such default brake.

---

### 10.3 The single highest-leverage thing to verify before writing integration code

> **Stand up the integration against a FRESH engine instance launched in mock/dry mode — and prove the transcript-text → brain path on `/owner/ingest` with `execute_actions=false` — before ever touching the running :8787 process.**

Rationale: this one move simultaneously (a) sidesteps the dormant capture seam (you POST text, you don't fix stubs), (b) neutralizes the "live engine sends real things" risk, and (c) tells you within minutes whether the brain produces sane act/ask/silent on *your* transcript shape. The launch contract to copy is in CLAUDE.md:

```
engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port <NOT 8787>
# with ANTICIPY_CHANNELS_MODE=mock  ANTICIPY_HANDS_MODE=dry  TWILIO_MOCK=true
# and NO ANTICIPY_OWNER_API_TOKEN needed for local
```

If instead you must use the running engine, the highest-leverage check is narrower: **confirm `execute_actions` stays `false` on every pendant POST** and **never call `/agent/act` from the bridge** until the money/vent guard (R6) is independently verified.

---

### 10.4 Concrete questions for Omar (decision-shaped, answerable)

1. **Ingest target:** Should the pendant bridge POST to **`/owner/ingest`** (`main.py:718` — proactive, safe, plan-only by default, asks before money) or to **`/agent/act`** (`main.py:1214` — direct browser action, no `execute_actions` brake)? I recommend `/owner/ingest`; confirm, and confirm whether the bridge may ever set `execute_actions=true` autonomously or only after a human tap.

2. **Who transcribes?** The pendant app (omi/Parakeet in DEV-FINAL) clearly already produces text. Should the bridge send **finished transcript text** to `/owner/ingest` (recommended — sidesteps the unbuilt capture seam and the `tiny.en` quality problem), or do you want me to send **audio** and rely on the in-repo batch `transcribe_audio` (`transcribe.py:32`), which is file-based and `tiny.en`-quality?

3. **Where is the pendant's transcript exposed locally?** Is the omi/macOS app's transcript available on a **local socket, a file we can tail, stdout, or BLE/HTTP** — and what's the exact contract (one line per utterance? JSON? partial vs final)? This is R3, which I cannot read from this repo. (If yes, may I read `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL` to find it?)

4. **Live engine or fresh mock instance?** Do I build and test against the **running live :8787** (Twilio live, Arcade live, real Chrome — real side effects) or spin up a **fresh engine in mock/dry mode on another port**? I strongly recommend the fresh mock instance for all development; confirm.

5. **Runtime mode truth:** Your `.env.local` says `ANTICIPY_CHANNELS_MODE=mock`, but the live process is actually running `live` (and `/status` agrees). Which is the intended default, and should I treat `.env.local` as stale and fix it, or leave it? (This affects whether a restart silently arms or disarms real SMS.)

6. **Owner-token gate:** `ANTICIPY_OWNER_API_TOKEN` is unset, so every local POST is unauthenticated. For a pendant that streams all day into a live engine, do you want the bridge to **set and present an owner token** (closing the open door at `main.py:243`), or is loopback-only trust acceptable for now?

7. **Batching cadence:** Should the bridge forward **every finalized utterance** as its own `/owner/ingest` call (cheap, chatty, more model calls), or **batch into time/topic windows** before ingesting? This trades latency-to-action against model cost and the brain's context quality — your call given the model-budget constraints noted in `memory/brain-middle-and-starved-brain.md`.

---

**Evidence anchors (file:line):** capture stubs `capture/pendant_phone.py:17`, `capture/mac_mic.py:20`; in-process intake `capture/intake.py:18`; batch-only transcriber `capture/transcribe.py:32,76`; ingest door `main.py:718-721`, schema default `main.py:322`; agent action arm `main.py:1214-1234`; owner-token gate `main.py:234-249` (enforced only when token set); live runtime confirmed via `ps eww 66506` (`ANTICIPY_CHANNELS_MODE=live`, `ANTICIPY_HANDS_MODE=live`) and `GET /status` (`channels.mode: "live"`, `twilio_configured: true`) + `GET /readiness` (Arcade Google, Twilio, Browser hand all `live`).