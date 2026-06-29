# PHASE 1 — THE FULL FRONT-END UI (the perfect plan)

Goal: a complete, clean, colorful, 5-year-old-proof front-end for anticipy.ai covering all 15
pages Omar specified, with real Supabase auth/email, and a "coming soon" tag on every button
whose backend isn't wired yet. Runs on localhost now; fills in with real power each later phase.

## Stack decision (reuse-first)
- **Vanilla static HTML/CSS/JS served by FastAPI `StaticFiles`** — same as today. No new
  framework. One shared stylesheet (`web/anticipy.css`) + one shared head/boot script
  (`web/anticipy.js`) so all pages share the design system and the Supabase session.
- **Auth/email:** reuse `web/auth.js` (`window.Anticipy.auth`) → Supabase email/password +
  email-confirmation redirect. Settings/profile persisted via engine + Supabase.
- **Coming-soon:** a shared `data-soon` attribute + helper that renders a small gold "soon"
  pill and blocks the action with a friendly toast. A single registry (`COMING_SOON`) lists
  which features are live; flipping a flag to `true` removes its pill — that's how later phases
  "remove the coming-soon labels."

## Reuse note: localhost bypasses the sign-in gate
`auth.requireAuth()` returns immediately (no gate) on 127.0.0.1/localhost (single-user dev).
So the Welcome→Sign flow must be **testable** even locally: I add `?flow=1` (or a non-loopback
host) to force the full signed-out experience for the walkthrough video, while normal local
use still boots straight into the product.

## The 15 pages (route · purpose · reuse source · coming-soon)
1. **Welcome** `/` (`index.html`) — initial welcome / brand. Reuse existing marketing hero;
   simplify CTA to "Get started" → Sign. *Live.*
2. **Sign** `/sign.html` — sign-in / sign-up (email + password), email-confirm flow. Reuse
   `auth.js` + `auth-screen.js`/`auth.css`. *Live (Supabase).*
3. **Onboarding: Basics** `/onboard/basics` — hidden machine step (grant access / pair
   extension / Layer-1 scrape kickoff). Renders a tasteful "getting set up…" progress screen;
   user normally doesn't dwell. Reuse `/onboard/*` engine endpoints. *Scrape = coming soon.*
4. **Onboarding 2** `/onboard/you` — the one screen the user fills: **name, one-sentence
   summary of you, + a few good-stuff fields** (role, what matters, who matters, comm-style
   hint). Writes to profile. *Live (form → engine/Supabase).*
5–10. **Onboarding 3–8** `/onboard/step3..8` — hidden machine steps: Call 1, Layer-2,
   Call 2, Layer-3, final call, profile assembly. Render as elegant auto-advancing progress
   states ("listening to your inbox…", "on a quick call…"). Reuse `/onboarding/profile`,
   `/onboarding/clarify`. *Scrape/calls = coming soon (Phase 7).*
11. **Great** `/onboard/great` — "here's what I now know about you" mirror + last
    clarification questions. Reuse `/onboarding/clarify`. *Live shell; deep facts = coming soon.*
12. **Done** `/onboard/done` — onboarding complete, hand off to the product. Reuse
    `/onboard/complete`. *Live.*
13. **MP3** `/mp3.html` — upload an MP3 / paste a transcript → it gets normalized into the
    proactive engine. Reuse engine intake endpoint. *Upload UI live; transcription = coming soon.*
14. **Tasks** `/app.html` ("Go to") — the Board: approve / deny cards, sort, comment. Reuse
    existing `app.js`/`app.css` deck; add sort + comment affordances + the watch-it-work slot.
    *Card render live; live browser action = coming soon (Phase 3).*
15. **Settings** `/settings.html` — permissions + security/autonomy levels (Full-Send /
    Regular / Limited) + always-confirm rules + do-not-touch zones + memory viewer entry, all
    saved. Reuse `/onboard/permissions` + autonomy config. *Dial live; some toggles coming soon.*

## Cross-cutting
- **Text-first mirror:** every card/proof component is built so the same state can be emitted
  over SMS (Phase 5 wires the send; UI shows "also sent to your phone" affordance now, soon-tagged).
- **Nav:** signed-in shell has Tasks · MP3 · Settings; Settings exposes Memory + "what it's
  working on". 5-year-old-proof: plain words, one primary action per screen.

## Build order (slices, each ends runnable)
1. Shared `anticipy.css` (design tokens) + `anticipy.js` (boot, session, coming-soon helper, toast).
2. Welcome (polish existing) → Sign (reuse auth) → confirm Supabase sign-up/sign-in/email works.
3. Onboarding flow shell: pages 3–12 as a coherent stepped flow (hidden steps auto-advance,
   page 4 + page 11 interactive).
4. MP3 page. 5. Tasks page upgrades (sort/comment/watch-it-work slot). 6. Settings page.
7. Wire nav + coming-soon registry. 8. Run on localhost, walk every page in Chrome, record video.

## Done-when (Phase 1)
- All 15 routes load, look clean/colorful/on-brand, and are navigable end-to-end.
- Real Supabase sign-up → email → sign-in works (proven on a non-localhost host or forced flow).
- Every unwired button is clearly "coming soon" (no fake success anywhere).
- A recorded video walks the full flow Welcome → Sign → Onboarding → Great → Done → Tasks →
  MP3 → Settings.
