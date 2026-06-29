# ANTICIPY — MASTER BUILD PLAN (Devin)

> This is my durable context anchor. It survives context resets. On any fresh start I read
> this file + `PROGRESS_JOURNAL.md` first, then resume exactly where the journal says.
> Source of truth for the product = repo-root `THE_MISSION.md`, `ANTICIPY_SOURCE_OF_TRUTH.md`,
> and the holy-grail "More info" doc. This file is the *build* plan, not the product spec.

## The mission (one breath)
Anticipy = "Donna from Suits": listens to your real day (typed transcript / MP3 now), infers
the real tasks (vents/sarcasm are NOT tasks — acting on a vent is the cardinal sin), drafts +
asks like a human, **acts in your own logged-in Chrome via the extension**, remembers
everything and compounds, reaches you by voice/SMS, and follows through days later. Money +
irreversible always confirm. NOTHING is hardcoded — it is fully horizontal.

## How we build (Omar's rule)
- **One master plan, executed in baby-steps as small provable slices.** Not one-shot.
- **Reuse-first, never rebuild.** Before writing anything, find the best existing version on
  this Mac/repo and consolidate it. The live spine is `~/Anticipy` on `factory/build` (all
  20+ feature branches already merged in). I work in a VM copy on branch `devin/full-frontend-ui`.
- **No plumbing-only.** Nothing is "done" until I can *show it working on video*.
- **Coming-soon strategy:** build the whole UI now; every not-yet-wired button shows a
  "coming soon" tag; each later phase deletes its own "coming soon" as it lands.
- **Finish line:** ONE full end-to-end video of every use case working, delivered with all plans.

## Working model
- Build in the VM (`~/Anticipy`), run engine + UI on VM localhost, test in VM Chrome, pack/load
  the extension via computer-use. A separate system drives the browser during agent tests.
- Engine run cmd: `engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787`
- Front-end = vanilla static HTML/CSS/JS served by FastAPI `StaticFiles` at `/` (NO new framework
  — adding Next.js would be a 26th fork, the exact thing Omar hates). Supabase auth via the
  existing `web/auth.js` wrapper (project "handlit", anon key public by design).

## Phases (baby steps; hardest flagged)
1. **PHASE 1 — Full front-end UI** (15 pages) + Supabase auth/email. Coming-soon on unwired
   buttons. Clean + colorful, anticipy.ai brand. → record a UI walkthrough video. ← DOING NOW
2. **PHASE 2 — Proactive engine → 100%** (Omar: ~90%). Exemplar harness, port 264 V7 cases,
   strict `ProactiveBrainOutput` schema, zero false-action on vents. Remove proactive coming-soons.
3. **PHASE 3 — Browser agent rehaul** (HARDEST #1). DEEP research (Vy, Manus, Claude, Vercel,
   Codex, Chrome). Rip ALL hardcoding (Amazon recipe, cart, keyword→site map, owner-locale).
   General set-of-marks agent + proof + watch-it-work. Pack/load extension via computer-use.
4. **PHASE 4 — Memory + context management** (HARDEST #2, Omar: ~40%). DEEP research on
   life-scale memory: what to keep/save/archive/cache/forget, privacy/security. Through the
   gateway with provenance + a correction UI (keep/edit/forget/downgrade/never-remember).
5. **PHASE 5 — Connections / follow-through.** Proactive↔browser clean handoff with a guide;
   3-days-later durable follow-up (state machine, not in-memory waits); text-first mirror of
   every action (every in-app proof also goes out as SMS).
6. **PHASE 6 — Voice / MP3 / active-listening.** Call + text you and others; MP3 transcript
   intake through the same normalizer. (Voice may be verified "in theory" via transcripts.)
7. **PHASE 7 — Onboarding live end-to-end.** Layered scrape ⇄ phone calls (Twilio), producing
   the structured profile (people-who-matter, tools, open loops, comm-style, trust/rules).
8. **FINAL — Full E2E video** of every use case + deliver all plans.

## Design system (carry into every page)
- Background cream `#FBF9F4` / `#F5F1E8`; ink charcoal `#171615`; accent gold `#B8924A`.
- Fonts: DM Serif Display (headlines) + Inter (body). Film-grain overlay. Warm, calm, editorial.
- Wordmark: **ANTICIPY**. Tagline: "Vibe your life. Let the rest be handled." Domain: anticipy.ai.
