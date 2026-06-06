# 09 REPO FACTS — operational ground truth (read before you touch anything)

This file exists so you do not rediscover or guess what is already known. The single most authoritative source for the CURRENT code state is `CODEX_BRIEF.md` at repo root; this file adds everything around it. If anything here conflicts with what you observe live, trust your live observation and update this file.

Hard rule from this project's history: research the official docs before editing any config or running an unfamiliar command. Guessing formats cost this project tens of hours once. Never guess.

## Repo and run
- Working repo (this is the one the brief was generated on): `~/Desktop/Anticipy-executor-working`. Confirm with `pwd` plus the presence of `engine/`, `macapp/`, and `CODEX_BRIEF.md`. An older path `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL` appears in history; it is not the live one. Use executor-working.
- Work on branch `autopilot/build`. Commit per kept lap. Never push to origin (origin push triggers a Vercel rebuild).
- Engine: Python FastAPI, binds 127.0.0.1 only, on port 8787 (NOT 8000, which is taken by another local service).
- Start: `engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787`
- Health: `curl http://127.0.0.1:8787/health`
- Engine venv: Python 3.10 at `engine/.venv/`. Live observation on 2026-06-05:
  `engine/.venv-bu-311/` is not present, and the current embedder code imports
  `sentence-transformers` from `engine/.venv/`; that venv has sentence-transformers,
  torch, numpy, and sklearn installed.

## Live-mode env flags (in .env.local, gitignored). Engine MUST be restarted to pick up changes.
- `ANTICIPY_HANDS_MODE=live` (else MOCK hand)
- `ANTICIPY_MODEL_PROVIDER=openrouter` (else STUB planner)
- `ANTICIPY_MODEL_SMART=google/gemini-3.5-flash`
- `ANTICIPY_MODEL_CHEAP=google/gemini-3.1-flash-lite`
- `ANTICIPY_MEMORY_MODE=live` (real bge-small embedder; else hash stub)
- `ANTICIPY_CHANNELS_MODE=live` plus Twilio creds (real SMS; else mock)
- `ANTICIPY_ABSTAIN_FLOOR` overrides the memory abstention threshold (default 0.66)

## Keys (names only; real values live in .env.local on the machine, never write secrets into the repo)
- `OPENROUTER_API_KEY` (must be FUNDED or the real model path hard-fails)
- `ARCADE_API_KEY`, `ARCADE_USER_ID` (the user id must match the signed-in Arcade account)
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` (the phone line)
- `DEEPGRAM_API_KEY` (transcription; see the cost ceiling below)
- `TAVILY_API_KEY` (web search)
- Supabase project is named "handlit"; Stripe, Resend, Railway, Steel keys also exist. Most are unused by the engine today.
- If any required key is missing, unfunded, or failing, that is a human gate. Queue it in `PENDING_FOR_OMAR.md` and keep working on everything not blocked.

## Models
- Engine brain today: OpenRouter, smart = gemini-3.5-flash, cheap = gemini-3.1-flash-lite. Vision options seen in history: Kimi-VL, Qwen3-VL. A cheap text option discussed: DeepSeek V3.2.
- Before swapping any model, web-search current community leaderboards and production forums this week. Rankings shift monthly. Do not pick from memory.

## Browser extension (Manifest v3)
- CRITICAL deploy gotcha: Chrome loads the extension from DESKTOP COPIES, not the repo. After editing `extension/`:
  1. `rsync -a extension/ ~/Desktop/Anticipy-Browser-Hand/`
  2. `rsync -a extension/ ~/Desktop/Anticipy-Extension/`
  3. `curl -XPOST http://127.0.0.1:8787/ws/reload`
  Check connection: `curl http://127.0.0.1:8787/ws/state` should show connected true.
- Behaviors: CDP trusted clicks (isTrusted true via chrome.debugger), set-of-marks observe, 20s keepalive ping, auto-reconnect, chrome.storage state. Screenshot via CDP Page.captureScreenshot, NOT captureVisibleTab (that grabs the wrong tab). Works inside the "Anticipy" tab group. cdp() has a 12s timeout and auto-reattaches on failure.
- Reloading or rsyncing the extension is your job, never a human gate.

## macOS app
- Build: `bash macapp/scripts/build_app.sh` (SwiftPM, no Xcode) -> `macapp/dist/Anticipy.app`.
- A command-line-tools modulemap fix may be needed on the build Mac (a stale module.modulemap renamed to .bak; reversible). If the build fails on that, that is the cause.
- Screens today: Onboarding and Connect are INERT scaffolds. Main is the only wired surface: it polls `/glassbox` every 2s (live feed) and `/pending` (the Approve/Skip card POSTs `/resolve`). The "type a task" box is static text, not a real input. Record control is inert. M2 makes input real.

## Connector status (from the brief; re-verify before relying)
- INTENT_MAP lives in `engine/anticipy_engine/hands/api_hand.py` (around lines 33-46). Proof extraction `_proof_from` reads nested ids (around 148-170).
- Working and proven by real runs: GoogleCalendar CreateEvent / ListEvents / DeleteEvent (12/12 real events one night); Gmail SendEmail (real message id).
- Pending or broken: Gmail WriteDraftEmail (needs the gmail.compose scope tapped), Slack SendMessageToChannel (errors on authorize), GoogleDocs GetDocumentById (never authorized). These are human-gate taps when you reach them.
- The in-suite api-hand test is a STUB (fake Arcade client), so green there proves nothing real. Prove connectors by a real run plus opening the app.

## Where the real pieces are (and what is stranded)
- The real multi-step browser agent exists at `engine/anticipy_engine/agent/webvoyager.py` (genuine observe -> decide(vision) -> act loop, set-of-marks, anti-loop, purchase guard, wall-handoff). It is ONLY reachable via `/agent/run` and `/agent/resume`. It is NOT wired into `control_core.py`, the orchestrator, or `BrowserHand`. The product's real browse today is `hands/browser_hand.py` = single navigate + read + a DuckDuckGo search fallback. It does not click, type, or fill. M3 wires the real agent into the task loop.
- The proactive time trigger `core/proactive.py` `trigger_tick` is NEVER called in production; `main.py` lifespan starts no scheduler. So anticipation over time does not run yet. M4 schedules it.
- Memory: SQLite + on-device embedder bge-small-en-v1.5 (384-d, MIT) + hybrid retrieval (semantic + keyword + recency + importance) in `live_memory/inject.py`. Four drawers: profile, open_loops (exact ledger), history, derived. The abstention/confidence signal is REAL but WEAK (held-out recall about 0.30 against a 0.66 floor). When unsure, it must ask, not guess.
- Glue: `core/bus.py` (in-process async pub/sub + correlated job queue) + a frozen worker contract (handles() / handle(job) -> Result, proof required) + `core/control_core.py` wiring. Structural ceiling: one global ControlCore, one job at a time, one user, in-memory, no auth. Sound for one local user; real multi-user is later hardening, not now.

## Test suite reality
- `bash scripts/run_suite.sh` is 29/29 green, but it force-exports `ANTICIPY_MODEL_PROVIDER=stub` and `ANTICIPY_HANDS_MODE=mock` at the top. So the suite tests the deterministic logic on STUB paths only. Green here does NOT mean the product works. Real proof is a real artifact in a real app, checked by the judge.

## Proven dead-ends (do NOT burn laps retrying these blindly)
- Google Sheets and Google Docs canvas resist synthetic input: multi-cell commit fails via CDP. Navigation and extraction work; the editable canvas does not. Accept it, route around it, do not retry from scratch.
- Amazon.ca consistently blocks Playwright. Use web_search for prices and flag them approximate; do not fight it with more automation.
- For the residual roughly 1% of sites that flag the agent (captcha, Cloudflare challenge), defer with a clear tap-to-finish notification to the human. Do not escalate an anti-bot arms race.

## On-device transcription cost ceiling (HARD constraint, do not violate)
- Always-on cloud speech-to-text is economically fatal: Deepgram streaming is about $0.0077/min (~$0.46/hr), which is roughly $1,130/yr if you transcribe a full day continuously. That is about 4x the entire ~$300/yr subscription budget.
- Therefore: transcription must be on-device and gated to detected speech (Whisper-tiny or Parakeet class on the phone), and the raw audio is thrown away. Cloud STT, if used at all, is for short gated or batch segments only. Do not design always-on cloud transcription.

## Why API-first is the moat (the reliability evidence)
- Rabbit R1 and Humane made nearly the same "autonomous pendant that acts across your apps" promise and collapsed on the demo-to-reality gap. UI-mimicry agents drop from about 63% to 4% accuracy across app-version changes, with hallucination spiking about 5x.
- So the order is: app back door first (Arcade API or connector), and the browser agent (vision + CDP, the WebVoyager loop) ONLY when there is no back door. Never make pure UI-mimicry the primary path. This is the differentiator; protect it.

## iOS app and pendant (M8, deferred, listed so you do not redesign it wrong later)
- Pendant: low-power, BLE 5.3, MEMS mic, small LiPo, audio codec. It talks BLE to the phone (not Wi-Fi, not cellular). Firmware forks omi/Friend; audio over BLE GATT notifications, Opus codec around 16kbps.
- iOS background: use bluetooth-central background mode with state preservation; the peripheral must send data periodically because a backgrounded app cannot actively poll. Battery drain and occasional reconnects are known, accepted costs (same as Omi, Bee, Limitless). Force-quit breaks restoration. Do not promise always-on iOS without this caveat.
- Phone talks HTTPS to the cloud; cloud talks WebSocket to the active browser extension.
- Hardware BOM (context only, deferred): Seeed XIAO nRF52840 Sense dev board for the 10-unit prototype, Adafruit 350mAh LiPo, 3D-printed resin shell with a metal-look finish (a real metal enclosure blocks BLE). Flashing the pendant is a human gate.

## Distribution
- The download front door is `anticipy.ai/app`. Cloudflare R2 is already set up to serve the build from there. Today `app/page.js` is a static placeholder ("Vibe your life."). M1 publishes a real signed `.app` to R2 and replaces the placeholder.

## Voice for anything you write that the human will read
- No em-dashes, ever. Use periods, commas, or sentence breaks.
- No AI-slop: no parallel three-part lists as rhetoric, no four-noun fragments, no symmetric flips. Plain, specific, human.

## The execution lessons that are now law (full text in 02_LAWS.md)
- Never grade your own work; the separate judge does. Reality (a real artifact in a real app) is the only proof.
- Never shrink the goal. Never fake or game a check. Never touch tests or judge files to pass.
- After two honest tries, rip out cleanly, log the failure, pivot. Never leave half-working code. Never claim a fix works without a real end-to-end check that actually passed.
- Research official docs before editing config or running unfamiliar commands.
- Never route your own work to the human. Money is the only hard stop. Use computer use to verify.
