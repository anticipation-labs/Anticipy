# WAKEUP — the loop's plain-English status (overwritten each build cycle)

_This is the canonical status the factory loop writes every cycle. The root `WAKEUP.md` is superseded._

## Where we are (2026-07-02, build cycle just finished — UI step 6)
- **done_gate:** legs 1–4 PASS, leg 5 (real person, real day) is the human finish line — not yet. Unchanged.
- **suite:** 113 passed / 9 failed (fail-set **byte-identical to baseline** — did NOT grow). **wiring debt:** 35 (unchanged, CLEAN). **premium-copy:** CLEAN.
- **This cycle built:** UI_SPEC **step 6 — Onboarding folds in the old "Great" screen** (commit `cae321c`). Before this, after you finished onboarding you were bounced to two extra dead-end screens (`/great` → `/done`) before reaching the app. Those are gone.
  1. **The final onboarding step now IS the "does this feel right?" mirror.** The last stage (`/onboarding/8`) renders the confirm-mirror that used to live on the standalone `/great` screen — your profile + what it learned + a one-line correction box + a **"Looks right"** button. Pressing it saves the durable "onboarding complete" marker (POST `/api/onboard/complete`) and drops you **straight onto Main (`/`)** — no more `/done` victory-lap screen.
  2. **Deleted the two dead screens:** `app/great/` and `app/done/` route folders, their components, their render branches, and their leftover nav entries. `/great` and `/done` now return **404**.
  3. **Cleaned two dev-leak tag strips** off the onboarding screens (the `ST-…` source tags on the onboarding hero + the "tell me three things" panel).
- **Proven (un-gameable):** on one clean dev server, `/welcome /sign /setup /connect /onboarding/2 /onboarding/7 /onboarding/8 /` all = **200**; `/great` & `/done` = **404**. Served `/onboarding/8` HTML shows "Does this feel right?" + "Looks right" + "last quiet check", **zero** `/great` links, **zero** `ST-` tag leaks, Back → `/onboarding/7`. The "Looks right" redirect in source = `window.location.href="/"`. Re-ran every gate: done_gate legs 1–4 PASS, suite 113/9 (fail-set == baseline), wiring CLEAN/35, premium-copy CLEAN. One commit, author "Anticipy HoE", proof in the message.
- **The onboarding flow is now self-contained end to end:** Setup → Connect → Onboarding (`/2…/8`) → **Main (`/`)**. No orphan screens between finishing setup and using the app.

## Honest caveats (environmental / pre-existing, not code regressions)
- **The `.next` dev front-door flake recurred at boot this cycle:** `/welcome` was 404 on a single stale listener (18461). Cleared with the decisive fix (kill :3100 listeners + `rm -rf .next` + ONE clean `next dev -p 3100`); single listener (24344) now serves all routes 200. Environmental (Next 15.5.19 dev chunk pruning), not a code regression. If it keeps flapping between cycles it may eventually need a real fix (pin/upgrade Next, or serve `/welcome` from a prod build).
- **A concurrent watchdog (pass #19) left `overnight/WATCHDOG.md` modified but uncommitted** — it saw my fresh lock and correctly did a read-only pass ("build cycle live: UI step 6"). That file is the watchdog's to commit, so I deliberately did **not** stage it; my commit contains only the 4 step-6 files.
- Every screen still logs an **SSR hydration mismatch** from UI step 1's `typeof window` guards — harmless to the gates.
- The app's `/api/*` proxy returns **503** in this dev env (engine bound at :8790) — environmental.

## Next buildable (order-of-attack, UI_SPEC build order)
- **Step 7 — Main:** rename `BoardScreen`→`MainScreen` (largely done in a prior cycle), build the single `OneInput` (merge `/mp3` upload), mount a compact `TaskBoard` (merge `/go-to` cards), then delete `app/mp3/` + `app/go-to/`. **Verify:** `/`=200, `/mp3`&`/go-to`=404.
- **Step 8 — Settings:** fold in the memory drawers + Forget-me + app-permissions; delete `ContextPackInspector` + `GatewayCircuit`; retire `/memory`.
- **Step 9 — Coming-soon registry:** add `app/phase-zero/capabilities.js` + `Capability`/`ComingSoonBadge`/`CapabilityRail`, mount on Main + Settings.
- **UI step 6 leftover polish (deferred, lower risk):** replace onboarding's full 8-step clickable timeline with a minimal "stage N of 4" dot, and drop `AccountReadStage`'s per-service consent toggles (consent now lives on `/connect`).
- Then the brain/memory/browser legs per THE_MAP §5.

## What needs Omar
See `overnight/HUMAN_QUEUE.md` — leg 5 (a real day on real accounts), load the extension in real Chrome, one fresh Twilio token. None are buildable autonomously.
