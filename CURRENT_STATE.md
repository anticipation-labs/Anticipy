# Anticipy — Current State (START HERE)

**Last updated: 2026-06-24.** This is the single authoritative status doc. The ~30 other `.md` files in
this repo are historical/stale — **trust this one** (newest dated wins). If you're an AI agent or a new
engineer doing an audit, read this top to bottom; it tells you where things are, what's proven, what's not,
and — critically — **why this project keeps failing at the seams**.

---

## 1. What Anticipy is
An always-listening assistant. You talk/type your messy day → it infers the real tasks (a vent/complaint is
NOT a task) → shows you swipeable cards (confirm/deny/allow/feedback) → and acts for you through a **browser
agent that drives your real, logged-in Chrome** (the "hands"), plus voice/SMS. **Money is the only hard
stop** (always confirm). **Acting on a vent is the cardinal sin** (never happens). The product is the
inference + the safe doing. "Browser-only" is a firm architecture decision (Omar): the agent works *inside
the systems you're already logged into* (Gmail, CRM, etc.) via the extension — NOT per-service OAuth, NOT a
cloud browser.

---

## 2. Architecture (as it actually runs today)
Two halves, by necessity:
- **Front-of-house = cloud.** The website (marketing + onboarding + the card "Board") is static HTML/JS in
  `web/`, deployed to **Vercel** (`anticipy-welcome.vercel.app`).
- **Brain + hands = the engine.** A FastAPI app (`engine/anticipy_engine/`). It runs in TWO places:
  - **Cloud:** deployed to **Railway** at `https://engine-production-eb43.up.railway.app` (image:
    `engine/Dockerfile`, Hobby plan). Has the brain, accounts, per-user data. **Has NO browser** (the cloud
    can't reach a local Chrome) → no hands in the cloud yet.
  - **Local (your Mac):** `http://127.0.0.1:8787`. Same engine, PLUS the **hands** — it drives your real
    Chrome through the **Chrome extension** (the extension dials OUT to the engine over a WebSocket
    `/ws/extension`, so NAT/firewalls don't matter).
- **Plugged into:** OpenRouter/Gemini (the model), **Supabase** (`ogbxpqkmsdrcuilafycn` — accounts/auth),
  Twilio (voice/SMS), Arcade (Gmail/Calendar APIs, a secondary path), Steel (cloud-browser key present but
  **0 lines of code use it** — not built).

---

## 3. What is DONE (proven by running it, not claimed)
| Capability | Status | Proof |
|---|---|---|
| **Brain** (infer tasks, ignore vents, hold money, human copy, multi-task split) | ✅ done + live (cloud + local) | POST `/owner/ingest` "…pay the $4,200 invoice" → split cards, vent ignored, **$4,200 BLOCKED** |
| **Accounts + per-user sign-in** | ✅ done + live + proven | Supabase email auth; engine verifies the token (`core/auth.py`); user A's cards never appear for user B (tested live on the cloud) |
| **Per-user data isolation** | ✅ done | `core/registry.py` → `core_for(user_id)` → own data_dir; two-user isolation test green; suite 107/0 |
| **The hands (browser agent)** | ✅ WORKS locally | drove Omar's real Chrome and read his live Gmail: `Inbox (3,793) - omarkebrahim@gmail.com` |
| **Cloud engine** | ✅ live | `/health` 200, real model (gemini-2.5-flash) |
| **Voice** | ✅ built + a real call proven | ElevenLabs voice via Twilio ConversationRelay; warm `OnboardingCallBrain`; held OFF (mock) |

## 4. What is NOT done
- **Onboarding flow** — the 4-screen scrape is janky: opens tabs, falsely says "couldn't get into your
  accounts," doesn't behave smartly. **Do not demo it.**
- **The hands in the CLOUD, per-user** — the extension is local + connects with a shared token. The cloud
  `/ws/extension` is gated (401) and not wired per-user. (Task: re-point the extension to the cloud `wss://`
  with the user's Supabase token; key `BrowserLink` by user_id.)
- **Voice turned ON** — built + proven, but `ANTICIPY_CHANNELS_MODE=mock` everywhere (safety).
- **A clean, one-click, end-to-end flow** — install → sign in → onboard → use. The *pieces* work; the
  *seams* don't.
- **`hands/cdp_client.py`** — missing → `/hands/compose-email` 500s (but Arcade Gmail-send works).

## 5. WHY THINGS KEEP FAILING — read this, it's the root cause
**This project's failures are a SYSTEM problem (repo/environment chaos), not the model.** Concretely:
- **Wrong-tree trap.** For most of this session, port `:8787` was served by a STALE squatter engine from
  `~/Anticipy-executor-working` (auto-started by a tmux session `anticipy-engine` + launch agent
  `ai.anticipy.core.api`), NOT `~/Anticipy`. So fixes were committed to one tree while a different, older
  tree answered every request. **Always verify** `lsof -p $(lsof -ti :8787) -d cwd` is `~/Anticipy/engine`.
- **10+ extension copies.** `~/Anticipy/extension`, `~/Anticipy-executor-working/extension`, `~/Downloads/
  anticipy-extension (7)`, `~/Desktop/★ LOAD THIS …`, `~/Developer/Anticipy-DEV-FINAL/extension_v*`, etc. —
  divergent versions. Chrome loads whichever, so a fix to one copy doesn't fix the loaded one. **Canonical
  now: `~/Desktop/Anticipy-Extension` (v0.3.0, the page-load race bug fixed). Duplicates archived to
  `~/.anticipy-extension-graveyard-*`.**
- **Confusing names.** `~/Anticipy`'s git remote is `omize10/Anticipy-executor-working` (named after the
  squatter). Multiple `.anticipy-data*` dirs. Many stale docs. No single source of truth → this file fixes
  that.
- **In-memory vs disk.** The engine caches owner_cards in memory; deleting the JSON files doesn't clear the
  board without a restart.
- **Browser caching of the static app** caused a "flash/reload loop" — the local sign-in gate reloaded on
  every no-session event; fixed (owner/local mode skips the gate), but needs a hard reload (`Cmd+Shift+R`).

**The single highest-leverage fix for this project is ONE canonical tree, ONE engine, ONE extension — kill
the duplicates.** Most "it's not working" reports trace to running/loading the wrong copy.

## 6. How to run it
**Cloud (anyone):** open `https://anticipy-welcome.vercel.app` → sign in (email) → per-user brain. (No hands.)
**Local owner (full power, incl. hands):**
1. Engine is at `~/Anticipy/engine`. Start: `bash ~/Anticipy/overnight/restart_engine.sh` (model on,
   channels mock). It serves the app at `http://127.0.0.1:8787`.
2. Load the extension: Chrome → `chrome://extensions` → Developer mode → **Load unpacked** →
   `~/Desktop/Anticipy-Extension`. It dials into the engine; `GET /status` → `extension_connected:true`.
3. Use it: `http://127.0.0.1:8787/app.html` (the Board — paste a day → cards; Confirm a browser card → it
   acts in your Chrome). **Owner/local mode skips sign-in.** Hard-reload (`Cmd+Shift+R`) if the page flashes.
4. Prove the hands: `POST /ws/observe {"url":"https://mail.google.com/mail/u/0/"}` → reads your real inbox.

## 7. Honest scorecard
Brain **95%** · Accounts/per-user **95%** · Hands (work locally, not polished/not cloud) **~60%** ·
Voice **70%** · Cloud engine **90%** · Onboarding **40%** · Clean one-click end-to-end **~40%**.
**Not "1,000,000% done."** The hard cores are real; the seams are not.

## 8. History — what was locked/finished, in order
1. Local engine (`factory/build`) was the verified base: brain/memory/browser/voice, suite green.
2. This session (2026-06-24): deployed the engine to the **cloud (Railway)**; deployed the **site (Vercel)**;
   synced all keys; built **per-user sign-in + data isolation** (Supabase + `core/auth.py` + `core/registry.py`)
   — proven live; fixed many brain/safety items (money/vent/credential stops, MFA walls, scrape); proved the
   **hands** drive the real Chrome + read real Gmail; consolidated the extension; wrote `THE_BAR.md` (the
   definition of done) and ran multiple evidence-based audits.
3. **Locked decisions:** browser-ONLY (extension dials out, NOT Steel/OAuth); money is the only hard stop;
   per-user-INSTANCE was Omar's stated preference, but per-user-DATA-in-one-engine is what shipped (works for
   a demo; instance orchestration is a later scale choice).

## 9. Key files (where things are)
- Engine entry: `engine/anticipy_engine/main.py` · brain: `core/control_core.py`, `proactive/`, `owner_mode.py`
- Auth/per-user: `core/auth.py`, `core/registry.py` · hands: `core/browser_link.py` + the extension; also
  `agent/webvoyager.py`, `hands/browser_use_*`, `core/native_bridge_link.py`
- Voice: `channels/conversation_relay.py`, `channels/call.py`, `/cr` in `main.py`
- Web app: `web/` (`app.js`, `onboard.js`, `auth.js`, `auth-screen.js`)
- Cloud deploy: `engine/Dockerfile`, `.railwayignore`; deploy from a minimal `/tmp/anticipy-deploy/` via
  `railway up` (CLI at `~/.npm-global/bin/railway`). The definition of done: `THE_BAR.md`.

## 10. For the next auditor — the 3 gotchas that will waste your time
1. **Confirm which tree serves `:8787`** before trusting any live test (the squatter trap).
2. **Confirm which extension copy Chrome loaded** before debugging the hands (use `~/Desktop/Anticipy-Extension`).
3. **The suite (`bash scripts/run_suite.sh`) tests the LOCAL repo code directly; the live `:8787` and the
   cloud may run different/stale builds.** Reports are lies; running the right thing is truth.
