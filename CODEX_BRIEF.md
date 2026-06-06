# CODEX_BRIEF — Anticipy situation brief (READ-ONLY)

Method: read the code, ran the existing suite once to observe, and live-checked Arcade authorization
(read-only `authorize`, no execute). Every claim cites a file; a green test only counts as proof if it
exercises the REAL thing, not a mock. Where I can't prove it with a file + a real test, it says
UNVERIFIED. Labels: **REAL** = implemented AND exercised by a non-stub test/run (both cited).
**STUB** = placeholder/mock/canned. **ABSENT** = does not exist.

═══════════════════════════════════════════════════════════════════════════════
1. WHAT THE REPO ACTUALLY IS RIGHT NOW
═══════════════════════════════════════════════════════════════════════════════

- **Branch:** `overnight/real-progress`. **Last commit:** `888e275` "overnight Track C + bonus…".
  Recent stack: `888e275`, `995ad3c`, `cac129d` (overnight tracks) on top of `4e523c2` (Wave 2),
  `8bcf54a` (Wave 1). Working tree clean except two untracked items (`engine/scripts/live_connect.py`,
  `macapp/dist/`) — neither is wired into anything.
- **Top-level layout:** `engine/` (Python FastAPI brain, ~4,100 LOC), `extension/` (MV3 Chrome
  extension, ~425 LOC), `macapp/` (SwiftUI, ~530 LOC), `app/` (2-file Next.js placeholder), `shared/`
  (`SCHEMA.md`), `scripts/` (suite + loops), `overnight/` (last night's Track A/B/C work), `notes/`
  (logs + the prior `architecture_audit.md`), `STATUS.md`, `WAKEUP.md`, `README.md`.
- **How the engine runs (verified this session):**
  `engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787`
  Binds 127.0.0.1 only (`engine/anticipy_engine/main.py:52`). Run mode comes from `.env.local`
  (gitignored) via `core/env.py` `load_dotenv(override=False)`; it is currently set live
  (`ANTICIPY_MODEL_PROVIDER=openrouter`, `ANTICIPY_HANDS_MODE=live`) — confirmed by `GET /gateway`.
- **How the Mac app builds:** `macapp/scripts/build_app.sh` (SwiftPM, no Xcode) → `macapp/dist/Anticipy.app`
  per `macapp/Package.swift`. **UNVERIFIED this session** — I did not run the build; `macapp/dist/`
  exists from a prior build. The build Mac also needs the CLT modulemap fix (notes; out of scope to re-verify).
- **Test suite + real count:** `scripts/run_suite.sh` → **29 passed, 0 failed — SUITE GREEN** (ran it).
  CRITICAL: `run_suite.sh:9-13` force-exports `ANTICIPY_MODEL_PROVIDER=stub` + `ANTICIPY_HANDS_MODE=mock`,
  so **the suite deliberately tests the STUB/MOCK paths, never the live ones**. The "real" hand tests
  are stubs: `test_api_hand.py:52` runs `mode=MODE_LIVE` with `client=fake` (a fake Arcade client);
  `test_browser_hand.py:11` uses a `FakeLink`. So **29/29 green ≠ the product works** — it means the
  deterministic logic is intact. The real proofs live in separate manual/paid scripts (below).

═══════════════════════════════════════════════════════════════════════════════
2. THE SIX PIECES (file + the test that PROVES it, not a stub test)
═══════════════════════════════════════════════════════════════════════════════

**① Onboarding — ABSENT.**
- `macapp/Sources/AnticipyApp/OnboardingView.swift:4` comment "Inert", `:21` the "Begin" button body
  is `{}`. `ConnectView.swift:4` "Inert"; the app tiles' "Connect" is decorative text (`:42-44`) with
  no action/OAuth. `AnticipyApp.swift:29` calls the whole shell "Scaffold … the three (inert) screens".
- No flow learns the user, discovers their apps, drives OAuth, or fills memory. No test exists because
  there is nothing to test. **Proof of absence:** the files are static SwiftUI with no logic.

**② Memory — REAL (implementation + logic), with a weak confidence signal.**
- Real implementation: `engine/anticipy_engine/live_memory/inject.py:58-119` (hybrid
  semantic+keyword+recency+importance retrieval, `"stub":False`), `memory/store.py` (SQLite + cosine),
  `memory/embed.py` (real `BAAI/bge-small-en-v1.5` behind `ANTICIPY_MEMORY_MODE=live`).
- **Real (non-stub) test:** `engine/scripts/memory_eval.py --lme` against LongMemEval with the real
  embedder (recall_all@10 0.875 per `notes/`). **Caveat: that run is MANUAL, not in the 29-suite**; the
  in-suite `test_memory*.py` exercise the real retrieval *logic* deterministically with a stub embedder.
- **UNVERIFIED/weak:** the abstention/confidence signal — `inject.py:84-88` returns a real `top_relevance`
  signal, but its own docstring (`inject.py:28-35`) records it as weak (held-out TPR 0.75 → 0.30 on eval).
  So memory retrieval is REAL; "memory knows when it doesn't know" is REAL-but-weak.

**③ Proactive engine — REAL decider logic; the ANTICIPATORY half is UNWIRED.**
- Real deterministic decider: `proactive/triage.py:73-86` (bouncer, 0 smart calls), `proactive/harm.py:101-124`
  (detrimental-first act/ask), wired live in `core/proactive.py:71-116`.
- **Real (non-stub) tests:** `test_triage.py` (23/23 noise-drop, observed), `test_harmline.py`,
  `test_proactive.py` — deterministic, they exercise the real logic (not mocks). PLUS a fresh grade
  last night: `overnight/track_b/score_existing_engine.py` ran the SHIPPED triage+harm-line on a 60-line
  human key → **cardinal false-action = 0** (it won't catastrophically act on a vent) but it **over-asks
  on 9/30 noise lines** (e.g. "If I won the lottery I'd buy an island" → ASK). Cardinal-safe, but noisy.
- **UNWIRED piece (call it STUB-in-prod):** the time/anticipatory trigger `core/proactive.py:150`
  `trigger_tick` is **never called by the running engine** — `main.py`'s lifespan (`:40-46`) starts no
  scheduler (grep: only callers are tests). So "it proactively nudges you over time" does not run.

**④ Browser agent — REAL multi-step code EXISTS but is STRANDED; the task loop is OBSERVE/NAVIGATE-ONLY.**
- Real multi-step agent: `engine/anticipy_engine/agent/webvoyager.py:126` — a genuine
  observe→decide(vision)→act loop (plan, set-of-marks, anti-loop, purchase-guard, wall-handoff).
- **It is only constructed in `main.py`** (`/agent/run`, `/agent/resume`) — grep confirms it appears in
  no other engine file. It is NOT wired into `control_core.py`, the orchestrator, or `BrowserHand`. So the
  product's actual task loop cannot invoke it.
- The loop's real browse = `hands/browser_hand.py:34-59` `BrowserHand` = **single navigate + read +
  a DuckDuckGo search-fallback (`:21-31`)** — it does NOT click/type/add-to-cart/fill-forms.
- **Real test:** the multi-step agent's only real proof is the MANUAL live battery (`engine/scripts/_battery.py`,
  `_webvoyager_slice.py`) — paid, **not in the 29-suite**; the in-suite `test_browser_hand.py` is a
  `FakeLink` stub. **Verdict: multi-step is REAL but unwired + only manually proven; the loop is observe-only.**

**⑤ API hand + connectors — REAL hand; mesh = 2 working apps; the in-suite test is a STUB.**
- Real hand: `engine/anticipy_engine/hands/api_hand.py` (real Arcade authorize→execute, idempotency,
  proof validation, nested-id extraction `_proof_from:148-170`).
- **In-suite test is a STUB:** `test_api_hand.py:52` `mode=MODE_LIVE, client=fake` — green proves nothing real.
- **Real (non-stub) proof + live authorization (checked this session, `client.tools.authorize`):**

  | Connector (`INTENT_MAP`, api_hand.py:33-46) | live auth | proven by a real run? |
  |---|---|---|
  | `GoogleCalendar.CreateEvent` / `ListEvents` / `DeleteEvent` | **completed** | ✅ **12/12 real events** last night (`overnight/track_a/`, independent self-proved judge) |
  | `Gmail.SendEmail` | **completed** | ✅ real message id in Wave 2 (`notes/wave2_log.md`) |
  | `Gmail.WriteDraftEmail` | **pending** | ❌ needs the `gmail.compose` tap (path built, gated: `overnight/track_c/`) |
  | `Slack.SendMessageToChannel` | **errors on authorize** | ❌ not usable |
  | `GoogleDocs.GetDocumentById` | **pending** | ❌ never authorized/tested |

  **The "connector mesh" is 2 working apps (Calendar, Gmail-send), proven by real runs — NOT by the suite.**

**⑥ Glue / contract between pieces — REAL.**
- `core/bus.py:22-95` (in-process async pub/sub + correlated job queue) + the frozen worker contract
  (`handles()/handle(job)->Result`, proof-required) + `core/control_core.py:46-86` wiring.
- **Real (non-stub) proof:** real workers (`ApiHand`, `BrowserHand`) replace stubs with no loop rewrite,
  exercised end-to-end by `engine/scripts/journey_eval.py --realhands` (7/9, Wave 2) and last night's
  Track A (12/12). The contract genuinely holds under real hands.
- **Structural ceiling (REAL but single-tenant):** the bus runs **one job at a time** (`bus.py:73-94`),
  and `main.py:30` is **one global `core = ControlCore()`** → one user, one in-memory store, no auth, no
  concurrency. Sound for one local user; nothing for many.

═══════════════════════════════════════════════════════════════════════════════
3. THE MAC APP — what exists, what a user sees, and the dev↔stranger gap
═══════════════════════════════════════════════════════════════════════════════

- **Exists / what a user sees:** a 3-screen SwiftUI shell driven by a dev "rail" (`AnticipyApp.swift:30-56`,
  footer "scaffold · inert" `:85`). Screen 1 Onboarding and Screen 2 Connect are **inert** (§1). Screen 3
  **Main** is the only wired surface: `MainView.swift:22-33` polls `127.0.0.1:8787/glassbox` every 2s and
  renders the live feed; `:47-75` polls `/pending` and the Approve/Skip buttons POST `/resolve`. So a user
  on the same Mac can **watch what the engine is doing and approve/deny paused actions** — and nothing else.
- **REAL in the app:** the feed + the approve/deny round-trip. **INERT in the app:** Record controls
  (`MainView.swift:211-229`, no audio), and the "Tell Anticipy something…" box is a static `Text`, **not a
  `TextField`** (`MainView.swift:231-244`) — **a user cannot even type a task into the app.**
- **The exact dev↔stranger gap:** today it works only because a developer (a) hand-edits `.env.local` with
  live flags + API keys, (b) starts uvicorn by hand, (c) manually approves Arcade OAuth URLs per app, (d)
  hand-loads the Chrome extension (and rsyncs it to the desktop copy Chrome actually loads), (e) builds the
  unsigned app via a script, and (f) feeds tasks via `POST /event`/curl because the UI has no input. A
  stranger has: **no download** (`app/page.js:30` is a static "Vibe your life." placeholder — no app, no
  installer, no link), **no onboarding, no connect-apps UI, no input, no auth/transport off localhost.**
  The gap is essentially the entire product perimeter.

═══════════════════════════════════════════════════════════════════════════════
4. SETUP-DEBT LEDGER (every place it only works because of a manual/privileged step)
═══════════════════════════════════════════════════════════════════════════════

1. `.env.local` hand-set to live (`ANTICIPY_MODEL_PROVIDER=openrouter`, `ANTICIPY_HANDS_MODE=live`); else
   the whole engine is stub/mock. It is gitignored, so nothing in the repo reveals the running mode.
2. `OPENROUTER_API_KEY` must be funded or the real model path hard-fails (`gateway.py:64-65`).
3. `ARCADE_API_KEY` + `ARCADE_USER_ID` hand-set, and **each app authorized by a human pasting an OAuth URL**.
   Today: Calendar + Gmail-send authorized; Gmail-draft/Slack/Docs not.
4. Chrome extension loaded **unpacked by hand**; per `notes/` Chrome loads it from a **Desktop copy**, so every
   extension edit needs an `rsync` + `POST /ws/reload` or you debug code Chrome isn't running.
5. Engine started by hand (uvicorn); no installer/daemon/supervisor.
6. Mac app built by hand (`build_app.sh`), unsigned/unnotarized; build Mac needs the CLT modulemap fix.
7. Real SMS/voice (`channels/text.py:39` `_twilio_send`, `# pragma: no cover`) needs creds +
   `ANTICIPY_CHANNELS_MODE=live`; never exercised.
8. `run_suite.sh:9-13` force-stubs the suite so CI stays free — i.e. CI intentionally does not test live paths.
9. One global `ControlCore` = one person's data; no second user, no auth, no isolation.
10. Tasks must be fed via `POST /event`/curl — the app UI has no working input (`MainView.swift:231-244`).

═══════════════════════════════════════════════════════════════════════════════
5. ONE-SCREEN VERDICT
═══════════════════════════════════════════════════════════════════════════════

**Can a stranger download this today, onboard, connect their apps, and have it do real tasks? → NO.**

Three biggest reasons:
1. **No front door.** There is nothing to download (`app/page.js` is a static placeholder); the Mac app is
   an inert dev shell whose only live surface is watch-feed + approve/deny; onboarding and connect-apps are
   inert; there's no working task input. (§3)
2. **Connecting apps is a manual developer OAuth dance, and the mesh is 2 apps.** Only Calendar + Gmail-send
   are authorized+proven; drafts/Slack/Docs are pending/broken; every connection is a hand-pasted URL. (§2⑤, §4)
3. **The "do real tasks" engine is half-wired.** The proactive time-trigger never runs in prod, the only
   multi-step browser agent isn't connected to the task loop (the loop can read pages but not act on them),
   and it's single-user/in-memory/no-auth. (§2③④⑥)

**What IS real (so this is not nothing):** the decision spine genuinely works — triage→harm-line→orchestrator→
real hands→verified completion, proven on real Calendar (12/12 last night) and real Gmail-send, with a measured
cardinal-false-action of 0; real memory retrieval; and a real (if stranded) multi-step web agent. The engine is
real; the product around it — input, onboarding, search, the connector mesh, distribution — is mostly absent.
**Honest framing: a working engine, not yet a usable product.**

— End of brief. No fix plan; this is the situation as it actually is.
