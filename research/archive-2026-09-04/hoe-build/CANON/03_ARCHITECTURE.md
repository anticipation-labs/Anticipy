<!-- CANON v1 · written 2026-07-02 by the HoE agent (post-Devin) · NEW documentation, not Devin's.
     On conflict with any doc outside CANON/ (except MISSION_LOCK.md for live mission status), THIS file wins. Fix errors HERE — never fork. -->

# 03 — ARCHITECTURE: the technical design of record

This is how Anticipy is actually built, verified against the code on 2026-07-02.
(The older `ANTICIPY_ARCHITECTURE.md` at repo root is the long historical deep-dive; this file supersedes it.)

## 1. THE PIECES

| Piece | Where | What it is |
|---|---|---|
| **Engine** | `engine/anticipy_engine/` | The brain. A Python FastAPI server (a web server the app talks to) on port **8787**. Holds memory, the proactive loop, the hands, the channels. Run: `engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787` |
| **App** | `app/` | The product UI. A Next.js website on port **3000**. Its `app/api/*` routes are thin proxies: they check owner auth then forward to the engine via `privateEngineRequest` (`app/api/_engine.js:122`). The UI never talks to the engine directly. |
| **Extension** | `extension/` | The real-Chrome hands. A Chrome extension in the OWNER's own browser. It pairs by fetching a token from engine `GET /ws/token` then opening the `WS /ws/extension` socket (`extension/background.js:52-56`). The engine sends it read/act jobs; it posts results back. |
| **Mac app** | `macapp/` | A native SwiftUI shell (`macapp/Sources/AnticipyApp/`) that wraps connect/onboarding views. A packaging convenience, not a separate brain. |
| **web/** | `web/` | **LEGACY** static HTML/JS app (pre-Next.js). Nothing routes to it. Rule of thumb: any engine endpoint whose only caller is `web/` is orphaned. |
| **Channels** | `engine/anticipy_engine/channels/` | Twilio voice + SMS: `text.py`, `call.py`, `conversation_relay.py` (live two-way call audio), `inbound.py` (polls replies). Mock unless `ANTICIPY_CHANNELS_MODE=live` AND Twilio creds present (`channels/call.py:33-38`). |
| **Memory** | `engine/anticipy_engine/live_memory/` + `memory/` | Four drawers — `profile` (stated facts), `derived` (inferred), `open_loops` (commitments), `history` (episodic) — read surface `GET /memory/drawers` (`main.py:721`). `live_memory/` is the capture→infer→inject pipeline plus the separate protected "remembered" table (`live_memory/remember.py`). |

## 2. THE SPINE (one paragraph)

Every real behavior is one flow: an **Event** arrives (typed line, MP3/live transcript, extension
page read, or an inbound Twilio text) → the capture layer writes what it heard into the memory
drawers → on each tick (every `ANTICIPY_TICK_SECONDS`, default 30s) the proactive loop builds **one
ContextPack** — a single typed bundle of "what memory knows that matters right now"
(`live_memory/context_builder.py`; the core deliberately has ONE builder, `core/control_core.py:884`)
— → the decision pipeline picks **act / ask / silent** (vents are never tasks; money is a hard stop)
→ an act goes to a hand (the browser via the extension is THE hand; the Arcade API hand survives
only as a subordinate read-only connector — browser-only, Omar 2026-07-04, §7) → the result is
**verified by read-back**, never assumed → the outcome is written back to memory and the glassbox
log, and the user is told through a channel. A piece that isn't on this spine isn't a feature — it's
an orphan, and Section 5 lists every one.

## 3. DIRECTORY GUIDE (top level, one line each)

| Dir | Tag | What |
|---|---|---|
| `engine/` | LIVE | The FastAPI engine (see §1). |
| `app/` | LIVE | The Next.js product UI + API proxies. |
| `extension/` | LIVE | The Chrome-hands extension. |
| `macapp/` | LIVE | SwiftUI Mac shell. |
| `shared/`, `lib/` | LIVE | Shared schema (`shared/SCHEMA.md`) and app helpers (`lib/phase-zero/`, `lib/supabase/`). |
| `scripts/` | LIVE | `run_suite.sh` (the test suite) and helpers. |
| `factory/` | MIXED | The forcing system, not the product. `factory/bin/` gates (suite/wiring/scans) are LIVE tooling; the nightly lap regime around them is dormant. |
| `overnight/` | LIVE | Milestone proof harnesses (`m1_battery.py`, `m2_copy_test.py`, `m3_integration_test.py`, …) — the PASS tests MISSION_LOCK cites. |
| `autopilot/` | LEGACY | An older self-run regime; superseded by MISSION_LOCK + PLANS. |
| `notes/` | ARCHIVE | Historical build notes. |
| `docs/` | ARCHIVE (mostly) | Old audits/specs, including Devin's `docs/handoff/` + `docs/build/`. `docs/agent_os/` is the old memory dock — superseded by CANON. |
| `realdays/`, `marketing/`, `demo/` | IRRELEVANT | Recorded day data / brand assets / demo props — not product code. |
| `web/` | LEGACY | Pre-Next.js static app (see §1). |
| the legacy `.md` docs (35 at root; ~238 repo-wide excl. deps) | ARCHIVE | Indexed in `CANON/99_SUPERSEDED_INDEX.md`; only CANON/ + `MISSION_LOCK.md` + `PLANS/` are living. |

## 4. THE ENDPOINT SURFACE (grouped)

The engine's HTTP surface, grouped by owner-facing purpose (all in `engine/anticipy_engine/main.py`).
**The authoritative, always-current enumeration is `factory/bin/check_wiring.py --list` — run that,
don't trust any hand-typed list (including this one) to stay complete.**

- **owner** — `/owner/ingest`, `/owner/ingest-file`, `/owner/cards`, `/owner/onboard`, `/owner/stop`, `/owner/autonomy_mode`
- **memory** — `/memory/history|drawers|context|forget-me|open-loops(+resolve)|remembered(+approve|dryrun|dryrun-day)`
- **onboard** — `/onboard/discover|scan|owner-scrape|deep-scrape|deep-read-hand|deep-scan|permissions|loop|status|complete`, `/onboarding/profile`
- **listen** — `/listen/start|stop|status`, `WS /listen/stream`
- **agent** — `/agent/act|run|reset|events|resume|judge`, `/anticipate/research`
- **ws (extension + browser link)** — `/ws/state|token|reload`, `WS /ws/extension`, legacy `/ws/browse|observe|act`
- **voice** — `/voice` (Twilio webhook), `WS /cr` (ConversationRelay)
- **infra** — `/health`, `/readiness`, `/status`, `/glassbox`, `/pending`, `/resolve`, `/trigger/tick`, `/scorecard`, `/gateway`, `/console`, plus legacy `/capture`, `/event`, `/hands/compose-email`

## 5. THE 13 SEAMS (verified 2026-07-02)

A **seam** = a place where something is built but not connected to the spine. This table is the
human-readable twin of `factory/wiring_allowlist.txt` (the wiring gate's exception list) — the two
must always agree; change them in the same commit. FIX-nn = plans on the `PLANS/00_OVERARCHING.md` board.

| # | Seam | What exists (path) | What happens today (2026-07-02) | Target wire | FIX plan |
|---|---|---|---|---|---|
| 1 | Deep onboarding scrape | `/onboard/owner-scrape` (deep CDP read of the owner's world, `main.py:1221`) + the four-layer `/onboard/loop` (`main.py:1335`) | The shipped UI calls only `/onboard/deep-scan` (`app/phase-zero/PhaseZeroApp.js:540`) — a shallow extension page-snapshot | Onboarding runs the deep scrape + loop through the paired extension | FIX-03 |
| 2 | Anticipatory person research | `proactive/anticipate.py` (+ `POST /anticipate/research` + an app proxy) | Nothing in the proactive tick calls it and no page fetches it — endpoint-only orphan | "Hear a name → research fires" inside the decide step, or delete | FIX-02 |
| 3 | Voice line | `/voice` webhook + `WS /cr` (`main.py:2149,2171`), `channels/call.py` | No frontend; `ANTICIPY_CR_WSS_URL` unset in `.env.local` (0 matches, 2026-07-02) so the live-call relay can't connect | Twilio number webhook → `/voice` → real two-way call | FIX-09 |
| 4 | Hands go live | `hands/api_hand.py` (subordinate read-only connector only — browser-only verdict, Omar 2026-07-04; the API-connect arm + `/connect` are deleted, §7) + the primary browser hand; code defaults to MOCK when `ANTICIPY_HANDS_MODE` is unset (`core/control_core.py:804`) | Suite forces mock; NOTE `.env.local` sets `live`, so a plainly-launched engine runs live hands | A deliberate, proven "hands live" flip (the L3 flip), never an env accident | go-live flip |
| 5 | Channels go live | `channels/text.py` + `call.py`; MOCK unless `ANTICIPY_CHANNELS_MODE=live` (`core/control_core.py:927`) | Suite forces mock; `.env.local` sets `live` + real Twilio creds | A deliberate "channels live" flip (the L2 flip) | go-live flip |
| 6 | Browser-agent UI | `/agent/act|run|events|judge|resume` (`main.py:1854+`) | No `app/api/agent/*` proxy exists; no Next.js page calls any of it | A Mission-Control view driving `/agent/run` and streaming `/agent/events` | FIX-12 |
| 7 | Profile page | `app/api/profile/route.js` | Reads/writes a local JSON store (`lib/phase-zero/store`), never engine memory | Profile backed by `GET /memory/drawers` | FIX-05 |
| 8 | Autonomy dial | UI dropdown (`PhaseZeroApp.js:1323`); engine `/owner/autonomy_mode` (`main.py:1728`) | Dropdown patches the local settings store; the engine's mode never changes | Dropdown → `POST /owner/autonomy_mode` | FIX-04 |
| 9 | Remembered approvals | `/memory/remembered/approve` + dryrun endpoints (+ app proxy route) | Zero UI callers | An approvals panel in the app | FIX-08 |
| 10 | Pending/ask queue | `GET /pending` + `app/api/pending/route.js` | No page ever fetches it | The ask-first queue surfaced in the app | FIX-06 |
| 11 | Deep read hand | `POST /onboard/deep-read-hand` (`main.py:1278`) | No caller anywhere (repo-wide grep, 2026-07-02) | Fold into the onboarding loop, or delete | FIX-10 |
| 12 | Old scaffold brain | `engine/anticipy_engine/brain.py` + `proactive/engine.py` ("proposals are always empty in the scaffold", its own docstring) | Nothing imports `brain.py`; the live core builds its own pipeline | Delete | FIX-01 (first phase) |
| 13 | Legacy/loose endpoints — verdicts split per `factory/wiring_allowlist.txt` (2026-07-02) | `/hands/compose-email` imports `hands/cdp_client`, a file that DOES NOT EXIST (`main.py:1400`; broken at call time) → **FIX-13**. Ledger surfaces `/scorecard`, `/goals/{id}`, `/gateway`, `/api/glassbox` → **FIX-14**. Browser control plane `/ws/state|reload|browse|observe|act`, `/api/browser/run` → **FIX-15**. `/api/download/anticipy-execute` (button unwired) → **FIX-16**. `/api/owner/session` (login UI never calls it) → **FIX-17**. `/api/trigger/tick` (no scheduler caller) → **FIX-18**. `/event` → **KEEP, permanent** (legacy scripted front door, by design). | No product caller found (2026-07-02) | Per-item verdicts as listed | FIX-13…18 |
| 14 | Onboarding + pairing UI callers | `/api/owner/onboard` + `/api/pairing/mint` (Next proxies to the engine) | `/connect` (their sole UI caller) was DELETED with the API-connect arm (browser-only, Omar 2026-07-04, §7); no UI page fetches them right now — declared `TODO(FIX-20)` debt in `factory/wiring_allowlist.txt` | The `/setup` onboarding reroute (`app/phase-zero/PhaseZeroApp.js`, concurrent) becomes the caller | FIX-20 |

## 6. CONFIG & DATA

The env vars that matter (env var = a named setting the process reads at start):

| Var | Default | Meaning (where read) |
|---|---|---|
| `ANTICIPY_MODEL_PROVIDER` | `stub` | Which LLM answers: `stub` / `openrouter` / `gemini` (`core/gateway.py:103`) |
| `ANTICIPY_HANDS_MODE` | `mock` | Real actions vs pretend (`core/control_core.py:804`) |
| `ANTICIPY_CHANNELS_MODE` | `mock` | Real Twilio calls/texts vs pretend (`core/control_core.py:927`) |
| `ANTICIPY_DATA_DIR` | `.anticipy-data` | Where memory + stores live on disk (`core/store.py:17`) |
| `ANTICIPY_TICK_SECONDS` | `30` | Proactive-loop heartbeat; `0` disables it for deterministic tests (`main.py:145`) |
| `ANTICIPY_ENGINE_URL` | `http://127.0.0.1:8787` | Where the app finds the engine (`app/api/_engine.js:1`) |
| `ANTICIPY_APP_OWNER_TOKEN` | unset | The app's owner gate. Unset = only same-machine requests get in; a public deploy without it is locked, not open (`app/api/_engine.js:53-63`) |

**`.env.local` (repo root, gitignored):** loaded by `core/env.py` with `override=False`, meaning
real shell exports always beat it. That is exactly how the suite stays safe: `scripts/run_suite.sh`
exports `stub/mock/mock` first (lines 14-16), so live keys never leak into tests. **Know this:** on
this Mac (2026-07-02) `.env.local` sets a live model provider, `ANTICIPY_HANDS_MODE=live`,
`ANTICIPY_CHANNELS_MODE=live`, and real Twilio creds — a plainly-launched engine is LIVE-armed.

**Data on disk:** `.anticipy-data/` (memory drawers, stores, glassbox — per `ANTICIPY_DATA_DIR`),
`logs/` (factory ledgers). Milestone batteries need a FRESH engine + FRESH `ANTICIPY_DATA_DIR`;
a reused data dir gives false failures (learned 2026-07-02, see `CLAUDE.md`).

## 7. REQUIRED-DECISION BOX — browser-only vs the API arm

**The docs contradict each other.** `DONE_DEFINITION.md` (2026-06-19) says **BROWSER-ONLY for every
action** ("Email is sent from the browser… Anything the product does happens in the browser", line 23).
Yet the code still carries a full **Arcade API hand** (`engine/anticipy_engine/hands/api_hand.py` —
Gmail/Calendar via API tokens), and `MISSION_LOCK.md` (locked 2026-07-01) plans a **browser-primary**
agent (M4 browser honesty, M9 trust bar) without ordering the API hand deleted.

**HoE recommendation (2026-07-02):** the browser is THE primary hand — every user-visible action must
have a browser path, because that is the product ("acts in your real Chrome like a human"). The API
hand survives only as a subordinate connector for cases where it is strictly better (bulk reads,
verification read-backs), and it is NEVER the reason a browser flow doesn't get built. This also kills
the calendar-spam class of failure, which came from the API arm acting invisibly.

**VERDICT — BROWSER-ONLY, signed off by Omar 2026-07-04.** Every user-visible action runs through the
browser hand (the Chrome extension dialing out to the cloud). The **API-connect arm is deleted**: the
user-facing "Connect calendar & email / Text & calls" checklist page (`app/connect/`), its Next proxy
(`app/api/connections/authorize/`), the engine route `POST /connections/authorize`, the
`authorize_connection_loop()` core helper (+ its `_connect_tool` / `_CONNECT_TOOL_BY_IDENTIFIER`
helpers and the "live connector mode is required to generate a connect URL" string), and the
`google_arcade` row of the readiness checklist are all gone — nothing advertises "connect your accounts
via OAuth/Arcade" anymore. **`engine/anticipy_engine/hands/api_hand.py` is KEPT** but only as a
subordinate, read-only connector (verification read-backs / bulk reads); it is NEVER a user-facing
connect flow and NEVER the reason a browser flow isn't built. This also kills the calendar-spam class
of failure, which came from the API arm acting invisibly. The `/readiness` checklist now reports only
the browser hand + comms line + signed-download rows (no API-connect row).
