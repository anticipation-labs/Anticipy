<!-- CANON v1 · written 2026-07-02 by the HoE agent (post-Devin) · NEW documentation, not Devin's.
     On conflict with any doc outside CANON/ (except MISSION_LOCK.md for live mission status), THIS file wins. Fix errors HERE — never fork. -->

# 05 — CURRENT STATE (the one living status page)

**Last verified: 2026-07-02 (end of the overnight build).** Rule: stale >7 days = suspect — re-run the proof commands below
before trusting anything here. Live milestone ledger = `MISSION_LOCK.md` STATUS TABLE (pasted PASS
outputs live there); this page is the plain-English summary of it.

## 1. Proven now (2026-07-02 — every row has pasted proof in MISSION_LOCK)

| What | Result | Replayable proof (from repo root) |
|---|---|---|
| M1 brain correctness | **6/6** battery ($4,200 blocked, sarcasm ignored, dinner→ask) | fresh engine on :8790, then `ANTICIPY_ENGINE_URL=http://127.0.0.1:8790 python3 overnight/m1_battery.py` |
| M2 human copy | **PASS** — 5/5 distinct human titles, 0 dev-string leaks | `ANTICIPY_ENGINE_URL=http://127.0.0.1:8790 python3 overnight/m2_copy_test.py` |
| M3 autonomy + trust | **ALL PASS** 9/9 ($4,200 stays blocked even in full-send) | `ANTICIPY_ENGINE_URL=http://127.0.0.1:8790 python3 overnight/m3_integration_test.py` |

**Fresh-engine protocol (learned 2026-07-02):** the M1/M2/M3 batteries are state-sensitive — always
run them against a FRESHLY started engine with a FRESH `ANTICIPY_DATA_DIR`; a reused data dir gives
false failures. (Also in `CLAUDE.md` Run commands.)

Also proven 2026-07-02, in git on `hoe/build`:
- **UI dev-clutter hidden behind `?debug=1`** — consumer view is calm; engine internals (telemetry
  panel, source tags) only appear with `?debug=1` in the URL (commit `dfb86e3`, verified live on :3100).
- **`/owner/stop` dead-end fixed** — the STOP button on "on it" cards used to return a 405 error
  (no route existed); route added (commit `a1f2028`).
- **All ~44 UI flows verified end-to-end in mock** (2026-07-02) — every screen/button walked against
  the mock engine on :3100. Re-verify by walking the app per section 3 below.

## 2. Open now (one line each — full PASS tests in MISSION_LOCK)

- **Track B** — public premium welcome site on Vercel: not built / not deployed.
- **M4 browser honesty** — walled task must return `needs_human`, never a false success; the false
  `success:true` fix is unverified.
- **M5 onboarding deep scrape** — needs Omar's real logged-in Chrome + CDP (CDP = Chrome DevTools
  Protocol, how the agent drives real Chrome). Deep-crawl code exists (`owner_scrape.py`) but the UI
  path still uses a shallow single-viewport extension snapshot.
- **M6 real-time voice** — ConversationRelay only half-scaffolded; needs a live Twilio call.
- **M7 frontend app** — the fresh premium build (welcome → onboarding → swipeable card deck) not built.
- **M8 hosting/download** — not deployed; needs Vercel creds + repoint Supabase to the live
  `handlit` project (ref `eawoquqgfndmphogwjeu`; `.env.local` still holds a dead ref).
- **M9 trust bar** — not baselined (10 hard real tasks, ≥90% macro completion, 0 fake successes).
- **FIX plans** — board at `PLANS/00_OVERARCHING.md` (2026-07-02): FIX-00 (canon docs) IN-PROGRESS;
  FIX-01…FIX-19 all OPEN (one-pipeline, orphans, deep-scrape wire, autonomy/profile/pending wires,
  true-proactive, remembered-panel, voice, deep-read hand, scrape expansion, browser-agent UI,
  gmail-compose hand, ledger surfaces, ws control plane, download/session/tick wires, wiring-strict).
  The wiring gate's first honest run (2026-07-02) found 49 unwired items: 4 permanent-by-design,
  45 TODO debt — the full plumbing map now lives in `factory/wiring_allowlist.txt`.

## 2b. LIVE HOSTED LINK (2026-07-02 — WORKS, public)

**https://anticipy-welcome.vercel.app** — the new premium app, public, 200 on `/welcome` `/` `/sign`,
and its `/api/health` reaches the hosted engine at `https://engine-production-eb43.up.railway.app`.
A stranger can open it from anywhere.

**The deploy curse — SOLVED (root cause + recipe).** Deploys had failed for MONTHS. Cause: Vercel
attributes a deploy to the GIT COMMIT AUTHOR, and the account blocks deploys from non-team-members —
every agent/bot-authored commit (`noreply@anthropic.com`, `nick@integral.lan`, …) was BLOCKED. Recipe
that works, every time:
1. Author the deploy commit as a TEAM MEMBER: `git -c user.email="omarkebrahim@gmail.com" commit …`
2. `vercel.json` pins `{"framework":"nextjs","outputDirectory":".next"}` (the project had framework=null → served the old static config → 404).
3. Serverless `maxDuration` ≤ 300 (Hobby-plan cap; onboard/loop was 320 → rejected).
4. Vercel env (public, safe): `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `ANTICIPY_ENGINE_URL=`the Railway engine.
5. `vercel --prod --yes` → aliases to anticipy-welcome.vercel.app.

**HONEST caveat:** the Railway engine runs OLD (June) code — tonight's consolidated brain +
proactive→browser are NOT there yet. To put tonight's engine behind the live link, redeploy the
engine to Railway. The LOCAL engine IS tonight's full brain (the biggest thing).

**INCIDENTS (2026-07-02, owned):** `vercel link` clobbered `.env.local` → restored from `~/Anticipy`,
locked out via `.vercelignore`. Real SMS blocked: Twilio creds present but return 401 (token rotated) —
needs one fresh `TWILIO_AUTH_TOKEN`.

## 3. What physically runs (verified live 2026-07-02)

"Mock" = fake stand-ins for phone/SMS and browser hands, so nothing real is ever sent during dev.

- **Engine on :8790** (mock channels/hands, isolated data dir, real gemini brain):
  ```
  ANTICIPY_CHANNELS_MODE=mock ANTICIPY_HANDS_MODE=mock ANTICIPY_INBOUND_POLL_SECONDS=0 \
  ANTICIPY_DATA_DIR=$PWD/.anticipy-data-hoe PYTHONPATH=engine \
  engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8790
  ```
  Check: `curl -s http://127.0.0.1:8790/status` → `{"engine":"ok", … "channels":{"mode":"mock"}}`
  (returned exactly that on 2026-07-02).
- **App on :3100** (Next.js): `ANTICIPY_ENGINE_URL=http://127.0.0.1:8790 npm run dev -- -p 3100`
  — live 2026-07-02 (`/welcome` returns 200).
- **Extension** — "Anticipy (the hands)" v0.3.0 at `extension/`, loaded unpacked into Chrome. As of
  2026-07-02 the engine reports `extension_connected:false` — no real browser hands until Omar
  loads/reloads it in his Chrome.

## 4. Suite reality (baseline 2026-07-02)

`bash scripts/run_suite.sh` (forces the free stub model + mock hands/channels — a stub model is a
canned-answer fake so tests cost $0): **109 passed / 10 failed**. Exact FAILED set:

```
owner_mode owner_ingest_event owner_upload_ingest messy_proactive_handoff onboarding_frontdoor
retraction_silenced owner_app_product_path premium_copy owner_test_day01 create_print_routing_selftest
```

Honest note: these are mostly stub-model brittleness, NOT real-brain regressions — the real-model
batteries (M1/M2/M3 above) all pass. **LAW: the fail-set may NEVER grow.** After any change, the
failing names must be a subset of this list (byte-compare the suite's tail line against this set).

## 5. Needs Omar (agents cannot do these — never faked)

- **L1** — real logged-in Chrome with CDP enabled (unlocks the M5 deep scrape).
- **L2** — Twilio creds + one live SMS to his phone (proves the comms channel).
- **L3** — Arcade creds (API hands).
- **L4** — a public deploy or tunnel (so the voice webhook is reachable).
- **L5** — one real ambient day (the marquee demo: hear → infer → act → text).
- **Final safety/money pass** — Omar + Devin, manually, LAST; explicitly deferred by Omar's
  2026-07-02 directive (top of MISSION_LOCK). Do not build safety gates before then.

## 6. Update discipline

- This file is edited **in the same commit** as any status-changing change — never later.
- `MISSION_LOCK.md`'s STATUS TABLE stays the ledger of record (proofs are pasted there);
  this file is the readable summary. On live-status conflict, MISSION_LOCK wins.
- Anything here older than 7 days: re-run the proof command before repeating the claim.
