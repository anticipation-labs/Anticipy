# WAKEUP — the loop's plain-English status (overwritten each build cycle)

_This is the canonical status the factory loop writes every cycle. The root `WAKEUP.md` is superseded._

## Where we are (2026-07-02, build cycle just finished — UI step 8: Settings)
- **done_gate:** legs 1–4 PASS, leg 5 (real person, real day) is the human finish line — not yet. Unchanged.
- **suite:** 113 passed / 9 failed (fail-set **byte-identical to baseline** — did NOT grow). **wiring debt:** 35 (unchanged, CLEAN). **premium-copy:** CLEAN.
- **This cycle built:** UI_SPEC **step 8 — Settings (`/settings`) is now the single advanced surface** (commit `09ea8fc`). It absorbs the old `/memory` screen and gains an honest, real-data app-permissions group.
  1. **Two new groups on Settings.** "What each app can do" shows the SAME connect-your-accounts checklist the `/connect` page uses (read from `/api/readiness`): each app with a plain sentence of what it does and a **Connected / Not connected** badge — read-only here (you connect/change from the setup flow). "Memory" folds in the real memory drawers (facts, inferred, open loops, history) plus the **"Delete everything I know"** forget-me control that used to live on `/memory`.
  2. **Deleted the dev-only panels.** The "Live circuit" telemetry panel (`GatewayCircuit` — it was the last place the old `ST-*` source tags leaked) and the "What I'd see for a moment" context inspector (`ContextPackInspector`) are gone, along with the standalone `MemoryScreen`.
  3. **Retired `/memory`.** Going to `/memory` now quietly redirects to `/settings#memory` (old links never 404). The "Memory" entry was removed from the side menu; the memory lives inside Settings now.
  4. **Removed the dead plumbing behind the deleted inspector.** The inspector was the only thing that used the `/api/memory/context` proxy + its engine endpoint, so both were removed — otherwise the wiring gate would have flagged a new orphan. Nothing else calls that seam, so the wiring count stayed CLEAN at 35 debt.
- **Proven (un-gameable):** on one clean dev server (`:3100`, engine `:8790`): `/ /welcome /sign /setup /connect /onboarding/2 /onboarding/8 /settings` all = **200**; `/memory` = **307 → /settings#memory** (follows to 200). Served `/settings` HTML + a Playwright snapshot show the six groups including "What each app can do" (Permissions) and the open "Memory" group with the memory panel + "Delete everything I know"; **zero** "Live circuit" / `pz-gateway` / `pz-context-inspector` / "What I'd see for a moment" / "Show context" leaks; the side journey nav shows "Settings", not "Memory". Re-ran every gate: done_gate legs 1–4 PASS, suite 113/9 (fail-set == baseline; `wiring_gate` back to PASS), wiring CLEAN/35, premium-copy CLEAN, engine `main.py` compiles. One commit, author "Anticipy HoE", proof in the message.

## Honest caveats (environmental / pre-existing, not code regressions)
- **Mid-cycle wiring trip, then fixed:** deleting `ContextPackInspector` orphaned `/api/memory/context` and the suite's `wiring_gate` went red for one run. Resolved cleanly by deleting the dead proxy route + the engine's `@app.get("/memory/context")` endpoint (a seam that existed only to feed the deleted inspector). Wiring is CLEAN again; debt did NOT go up.
- **The `.next` dev-chunk flake recurred (cosmetic):** the Playwright console showed one 404 on a stale `/_next/static/chunks/app/settings/page.js`. The page still SSR-renders full content and serves 200 (curl + snapshot both confirm). This is the documented Next 15.5.x dev-chunk pruning flake, not a code regression. If a route ever serves 500/404 at boot, the fix is the decisive `.next` reset in LOOP.md.
- **A concurrent watchdog left `overnight/WATCHDOG.md` modified but uncommitted** — that file is the watchdog's to commit, so I did **not** stage it. My commit contains only the 6 step-8 files.
- The app's `/api/*` proxy returns **503** in this dev env (engine bound at :8790), so the app-permissions panel and memory drawers show their graceful loading/error copy in the screenshot rather than live data — environmental, the components render and degrade correctly.
- Every screen still logs an **SSR hydration mismatch** from UI step 1's `typeof window` guards — harmless to the gates.

## Next buildable (order-of-attack, UI_SPEC build order)
- **Step 9 — Coming-soon registry:** add `app/phase-zero/capabilities.js` + `Capability` / `ComingSoonBadge` / `CapabilityRail`; mount a collapsible "What I can do" strip on Main (collapsed, so the orb stays the focus) and an always-open group in Settings — every capability shown as a real button with a small "Coming soon" tag on the ~35 unwired seams. This is the honest-roadmap surface and the LAST UI_SPEC build-order step.
- **UI step 6 leftover polish (deferred, lower risk):** replace onboarding's full 8-step clickable timeline with a minimal "stage N of 4" dot, and drop `AccountReadStage`'s per-service consent toggles (consent now lives on `/connect`).
- Then the brain/memory/browser legs per THE_MAP §5 (recall under density, memory compounds, warm inputs/voice, browser to 60%).

## What needs Omar
See `overnight/HUMAN_QUEUE.md` — leg 5 (a real day on real accounts), load the extension in real Chrome, one fresh Twilio token. None are buildable autonomously.
