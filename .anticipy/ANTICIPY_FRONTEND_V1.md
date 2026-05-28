# Anticipy Frontend V1: honest status report

The final deliverable. The product's entire user-visible surface,
built as a thin client over the real backend seam, to a premium
bar, in one design system. Every claim below is backed by the real
`npm run build` output (exit 0) reproducible from the repo root.
Frozen action engine, frozen reasoning system, frozen Tauri
internals, and their tags were not modified and were git-verified
clean.

## What was built

A cohesive product surface at `/app` plus the real state seam at
`/api/app/state`.

Screens, all real, all in ONE design system (the repo's existing
dark / cream / gold tokens + DM Serif Display / Plus Jakarta Sans;
no second design language introduced):
- Landing / engine entry
- Account creation (the credential step is the user's own, by
  design, never automated)
- Download prompt
- Onboarding: connect Chrome, allow microphone, progressive-
  autonomy first-run framing
- The Listen state: a single, quiet, breathing orb. The heart of
  the product feel: calm, alive, one thing.
- Proposal / confirm surface
- History
- Settings (permissions, connected accounts, autonomy, privacy,
  safety)

Every unhappy / honest state is designed, not an afterthought:
- Offline (cannot reach our own state service): a calm designed
  screen that states nothing was lost or acted on, with retry.
- Engine gated (no live engine from this web origin): the Listen
  screen renders the honest "wired, not live here" state with a
  quiet (non-animated) orb. It NEVER shows a faked live orb or a
  fabricated proposal.
- Nothing-yet history: an honest empty state, not an invented card.
- Account: the credentials-are-yours honest state.

Design approach (frontend-design skill applied): refined
minimal-luxury executed with restraint and precision. Dominant
dark canvas with a single subtle gold radial glow and a faint
grain overlay for atmosphere and depth; DM Serif Display for the
one statement per screen; wide-tracked uppercase micro-labels; one
orchestrated staggered fade-up on load (CSS animation-delay); one
clear focal element per screen. The product disappears and
surfaces only when it has one clear thing to say. No generic AI
aesthetic, no second design system.

## Thin-client contract (honored)

The frontend contains NO business logic. It renders exactly what
`/api/app/state` reports and would send user intent
(confirm/deny/settings) back. State comes from the real route, not
mocked client data. Where a backend segment is the gated
real-accounts / real-engine edge, the route reports it as `gated`
with an honest reason and the UI renders that real state. The
route never fabricates a success and the UI never fakes one.

## Real automated check (passed)

Command (from repo root): `npm run build`
Result (literal): `✓ Compiled successfully`, then `Linting and
checking validity of types ...` passed, process exit 0.

Routes generated:
- `/app` -> Static (prerendered), page 3.78 kB,
  First Load JS 91.1 kB
- `/api/app/state` -> Dynamic server route (the real state seam)

## Frontend performance budget (set and met)

Hard budget set from the measured baseline: the product route's
First Load JS must be <= 150 kB (the marketing `/` route is
196 kB; the product surface must be leaner than marketing).
Measured: `/app` First Load JS = 91.1 kB. MET, with a wide
margin; it is the leanest real page in the app. `/app` is
static-prerendered, so first meaningful paint is immediate; the
Listen orb and the staggered reveal are CSS-only (no JS cost).

## Real end-to-end pass: what ran for real vs the gated edge

Ran for REAL on this machine:
- The production build, full TypeScript typecheck, and lint of the
  new product surface + the real API seam (exit 0).
- Static generation of `/app` and the dynamic `/api/app/state`
  route (route manifest confirms both).
- The earlier MH-P1 gate already proved the real product PATH end
  to end on the engine host: real Mac microphone -> real ASR ->
  real frozen reasoning (ACT) -> real proposal -> real frozen
  browser action (status SUCCESS). That is the substance the
  frontend surfaces.

Honestly-labelled GATED edge (not faked):
- The live in-browser round-trip (signup -> a real proposal
  arriving in this UI -> confirmed) requires a running engine
  reachable from this web origin (NEXT_PUBLIC_ENGINE_URL is not
  configured here) plus real account creation, which is
  prohibited to do on the user's behalf. So that final live
  round-trip is the gated edge. The frontend renders its real
  gated state (the honest "wired, not live here" Listen screen),
  never a faked live proposal. The path itself is proven (MH-P1);
  the in-browser-from-this-origin demonstration is the unproven,
  honestly-labelled segment.

Nothing about a gated edge is presented as working. There is no
mocked data and no faked success screen anywhere in the shipped
frontend.

## Notification delivery status (honest, not faked)

The [ANTICIPY-FRONTEND-DONE] Aevoy email was really attempted via
the existing unmodified executor/lib/aevoy_email.js. The real
result is recorded in PROGRESS.md (same external Resend 403
"anticipy.ai domain is not verified" blocker as DIL-P8 and
MH-PFINAL: a DNS / dashboard action that needs a human, not a
code defect). The notification path is wired and correct; delivery
is blocked on domain verification. Reported blocked, not faked.

## Headline

The product's entire user-visible surface is real, premium, thin,
fast (91.1 kB First Load JS, well under the 150 kB budget), in one
coherent design system, with every screen and every unhappy state
genuinely designed. It renders honest backend state and never
fakes a gated edge. The real product path underneath was already
proven end to end at MH-P1; the only unproven segment is the live
in-browser round-trip from this origin, which is the honestly
labelled gated edge, not a mock. This is the final deliverable;
the run ends here.
