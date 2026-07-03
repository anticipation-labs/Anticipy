# WAKEUP — the loop's plain-English status (overwritten each build cycle)

_This is the canonical status the factory loop writes every cycle. The root `WAKEUP.md` is superseded._

## Where we are (2026-07-02, build cycle just finished — UI step 7 finish)
- **done_gate:** legs 1–4 PASS, leg 5 (real person, real day) is the human finish line — not yet. Unchanged.
- **suite:** 113 passed / 9 failed (fail-set **byte-identical to baseline** — did NOT grow). **wiring debt:** 35 (unchanged, CLEAN). **premium-copy:** CLEAN.
- **This cycle built:** UI_SPEC **step 7 finish — the Main screen (`/`) is now the ONE place you talk / type / drop a recording, and the two old standalone screens are gone** (commit `7d1b33f`). The functional merge (the single "OneInput" and the compact review board) had already landed on Main in an earlier cycle; this cycle deleted the now-orphan screens so there is exactly one input and one review board, not three places.
  1. **Deleted the two dead screens:** `app/mp3/` (the old "Drop in the messy thing" upload page) and `app/go-to/` (the old "Pick one thing" review page) route folders, plus their four now-unused components (`Mp3Screen`, `GoToScreen`, `FileUpload`, `TranscriptInput`) and their render branches. `/mp3` and `/go-to` now return **404**.
  2. **Removed the last stray link:** the old `Upload` link that pointed at `/mp3` lived inside the deleted `TranscriptInput`, so it's gone too.
  3. **Pruned the menus:** `/mp3` and `/go-to` are removed from the drawer nav (`NAV_ITEMS`), the screen-title map, and the debug journey rail — no dead menu entries.
- **What Main does now (unchanged, still working):** one calm orb + one state word (Listening / Thinking / Acting / Resting), and one input row: a **mic** (tap to talk), a **textarea** (type it), and a **paperclip** (drop an MP3 or transcript file) → one **Send**. Below it, when there are cards, a compact review board. The whole "hear it three different ways" surface is one thing.
- **Proven (un-gameable):** on one clean dev server (`:3100`, engine `:8790`), `/ /welcome /sign /setup /connect /onboarding/2 /onboarding/8 /settings` all = **200**; `/mp3` & `/go-to` = **404**. Served `/` HTML has the one input (mic + paperclip + Send + hidden file field), the placeholder "Say it, type it, or drop a recording", the one-word state, and the collapsed-main layout; **zero** `/mp3`/`/go-to`/`Upload` link leaks; the old dead-screen copy ("Drop in the messy thing.", "Pick one thing.", "What should I handle?") is gone; no compile error. No `Mp3Screen`/`GoToScreen`/`/mp3`/`/go-to` references remain anywhere in code or tests. Re-ran every gate: done_gate legs 1–4 PASS, suite 113/9 (fail-set == baseline), wiring CLEAN/35, premium-copy CLEAN. One commit, author "Anticipy HoE", proof in the message.

## Honest caveats (environmental / pre-existing, not code regressions)
- **The `.next` dev front-door flake recurred at boot this cycle:** `/` was 500 on a stale listener at start. Cleared with the decisive fix (kill :3100 listeners + `rm -rf .next` + ONE clean `next dev -p 3100`); all routes then served correctly. Environmental (Next 15.5.x dev chunk pruning), not a code regression. Deleting the two route dirs did NOT re-trigger it — `/mp3`/`/go-to` recompiled cleanly to 404.
- **A concurrent watchdog left `overnight/WATCHDOG.md` modified but uncommitted** — that file is the watchdog's to commit, so I deliberately did **not** stage it; my commit contains only the 4 step-7 files (2 deletions + PhaseZeroApp.js + sourceData.js).
- Every screen still logs an **SSR hydration mismatch** from UI step 1's `typeof window` guards (JourneyRail/SourceTagList/SourceTruthStrip) — harmless to the gates.
- The app's `/api/*` proxy returns **503** in this dev env (engine bound at :8790) — environmental.

## Next buildable (order-of-attack, UI_SPEC build order)
- **Step 8 — Settings:** fold in the memory drawers (`LearnedMemoryPanel` + `ForgetMePanel`) + an app-permissions group sourced from `/api/readiness`; delete `ContextPackInspector` + `GatewayCircuit`; retire `/memory` (redirect to `/settings#memory`). **Verify:** `/settings`=200, no context-inspector.
- **Step 9 — Coming-soon registry:** add `app/phase-zero/capabilities.js` + `Capability`/`ComingSoonBadge`/`CapabilityRail`, mount a collapsible "What I can do" strip on Main and an always-open group in Settings (unwired seams tagged "Coming soon"). This is the honest-roadmap surface for the ~35 unwired seams.
- **UI step 6 leftover polish (deferred, lower risk):** replace onboarding's full 8-step clickable timeline with a minimal "stage N of 4" dot, and drop `AccountReadStage`'s per-service consent toggles (consent now lives on `/connect`).
- Then the brain/memory/browser legs per THE_MAP §5 (recall under density, memory compounds, warm inputs/voice, browser to 60%).

## What needs Omar
See `overnight/HUMAN_QUEUE.md` — leg 5 (a real day on real accounts), load the extension in real Chrome, one fresh Twilio token. None are buildable autonomously.
