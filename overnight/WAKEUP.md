# WAKEUP — the loop's plain-English status (overwritten each build cycle)

_This is the canonical status the factory loop writes every cycle. The root `WAKEUP.md` is superseded._

## Where we are (2026-07-02, build cycle just finished)
- **done_gate:** legs 1–4 PASS, leg 5 (real person, real day) is the human finish line — not yet. Unchanged.
- **suite:** 113 passed / 9 failed (fail-set **byte-identical to baseline** — did NOT grow). **wiring debt:** 35 (unchanged, CLEAN). **premium-copy:** CLEAN.
- **This cycle built:** UI_SPEC **step 4 — Setup absorbs /download.** The old standalone `/download` page is gone; its useful content (the browser-helper install) now lives inside Setup, and the flow points forward correctly.
  1. **Folded the download into Setup.** `SetupScreen` now shows a clean helper block when the extension isn't connected: a one-line explanation ("Add the browser helper — it lets me work inside the Chrome you already use. Nothing sends without your okay."), a **Download the browser helper (.zip)** button (→ the real `/anticipy-chrome-extension.zip`), and a plain 5-step "Load unpacked" install list. New charcoal/cream CSS (`.pz-setup-helper`, `.pz-setup-steps`) so it reads right in the dark shell.
  2. **New human copy + simpler rows.** H2 `Let's get you set up.` · sub `Two quick things, then I can start.` Dropped the developer-ish "Engine" readiness row; kept just **Browser helper** and **Listening**.
  3. **Wired the flow forward.** Setup's **Continue** now goes to **/connect** (was /onboarding/2) — matching the target flow (Setup → Connect → Onboarding). Removed the old ghost "Get the browser helper" link, and repointed a stray `/download` link buried in the onboarding read-layer to `/setup` so nothing dangles.
  4. **Deleted the `/download` route** (`app/download/page.js`) — including the git-clone / pip / uvicorn "Quick Start" block and the "How it works" block that CANON says to remove outright.
- **The one honest wrinkle I had to reconcile:** deleting `/download` broke a suite test (`download_route`) that used the old page as its probe. That test's *real* job is guarding the app-download API endpoint (`/api/download/anticipy-execute`) against becoming a dead 404 button — and that endpoint still exists and is untouched. So I updated the test to probe **/setup** for the UI (it checks the browser-helper is present) and to **pin /download = 404** (proving the deletion is intentional), while keeping every one of its endpoint assertions (200 + real .zip + honest provenance). The test is back to **PASS**; the fail-set is unchanged. This is stale-test maintenance for a CANON-mandated move, not gate-gaming — coverage is equal-or-better.
- **Proven (un-gameable):** `/welcome`, `/setup`, `/connect`, `/` = **200**; `/download` = **404**. Served `/setup` HTML carries the new copy, the .zip button, the install steps, and Continue→/connect, with **zero** `/download` links, shell commands, or source-tag leaks. Re-ran every gate after the edit: done_gate legs 1–4 PASS, suite 113/9 (fail-set == baseline), wiring CLEAN/35, premium-copy CLEAN.

## Honest caveats (environmental / pre-existing, not code regressions)
- **The `.next` flake recurred this cycle** — the running `next dev` on :3100 drifted to 404 on all routes AND there were **two** dev-server listeners on 3100 (likely a double-start race with the watchdog's app guard). Cleared per the LOOP note: killed the listeners, `rm -rf .next`, restarted one clean server. Verified 200 after.
- Every screen still logs an **SSR hydration mismatch** (server renders the debug rail/tags, client renders null) from UI step 1's `typeof window` guards — harmless to the gates.
- The app's `/api/*` proxy returns **503** in this dev env (engine bound at :8790, app expects its own binding) — environmental.

## Next buildable (order-of-attack, UI_SPEC build order)
- **Step 5 — Connect wired-in:** `ConnectPage` is already reachable now (Setup→Connect). Next: add a bottom `Continue` → `/onboarding/2` and drop the onboarding per-service consent toggles (consent lives on /connect).
- Then step 6 (Onboarding: strip timeline/tags, fold Great's complete-POST + mirror into the final stage, last href → `/`, delete `app/great/` + `app/done/`), step 8 (Settings: fold in memory drawers + app-permissions, delete `ContextPackInspector`), step 9 (Coming-soon capability registry) — then delete the now-redundant `/mp3`, `/go-to`, `/great`, `/done` routes.
- Then the brain/memory/browser legs per THE_MAP §5.

## What needs Omar
See `overnight/HUMAN_QUEUE.md` — the short list (leg 5 = a real day on real accounts; load the extension in real Chrome; one fresh Twilio token). None are buildable autonomously.
