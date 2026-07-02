# Plan Baby Steps

This folder is the working plan for rebuilding the full Anticipy UI end to end.

It is intentionally separate from old gate docs and old status docs. This is not a proof certificate. It is the build map for the next UI pass.

## Goal

Build one clean, normal-person UI that covers the whole product:

1. Welcome.
2. Sign up / sign in.
3. Browser helper setup.
4. Layered onboarding.
5. Active listening / upload MP3 / type / paste.
6. Active task board.
7. Task detail and approvals.
8. Browser work/proof viewer.
9. Memory.
10. Settings, privacy, autonomy, devices, and notifications.
11. Text/call mirror states for every ask and proof.
12. Original source-document use-case fixtures across the promised domains.

The first build does not need every backend feature to work. It does need the whole UI flow to exist, feel coherent, be openable on localhost, and include the basic backend contracts for auth, profile/settings, active listening, upload, intake, cards, comments, and read-only status.

## Build Principle

Start with the full UI shell plus minimal backend plumbing first, then wire each slice deeper one at a time.

This avoids the current failure mode where backend pieces exist but no single user path makes them feel like one product.

## Canonical Direction

Recommended framework:

- Use the existing Next `app/` as the future canonical product UI.
- Keep the static `web/` app as a design/reference source and temporary fallback.
- Build the first side-by-side UI preview at `app/plan-baby-steps/page.js`.
- Open it locally at `http://localhost:3000/plan-baby-steps`.

Why Next:

- It already has API proxies.
- It already has upload/listen routes.
- It can evolve into the hosted product.
- It avoids another split static frontend.

## Files In This Folder

- `FULL_UI_END_TO_END_PLAN.md`: the main build plan.
- `BABY_STEP_OPERATING_PLAN.md`: the slow, source-of-truth-anchored operating plan.
- `SOURCE_OF_TRUTH_TRACEABILITY.md`: the tag system that keeps every UI piece tied to the truth.
- `SCREEN_INVENTORY.md`: every screen/state/component the UI needs.
- `REUSE_MAP.md`: what existing code to reuse and what to retire.
- `BASIC_BACKEND_PLUMBING_PLAN.md`: the minimum backend contracts to build alongside the UI.
- `PROACTIVE_ENGINE_REUSE_PLAN.md`: the local proactive-engine audit, canonical spine decision, and one-slice-at-a-time pull plan.

## First Implementation Target

The first implementation target should be a non-destructive UI lab:

`/plan-baby-steps`

It should include the entire product journey with seeded state and the backend contract skeleton:

`Welcome -> sign -> setup -> onboarding -> great -> done -> active listen/upload/type -> go-to tasks -> task detail -> memory -> settings`

After the flow feels right, wire it to real endpoints and migrate the canonical routes.

## Non-Negotiable

Every screen, component, state, and route in the rebuild must point back to the source of truth.

Use the traceability tags from `SOURCE_OF_TRUTH_TRACEABILITY.md` before building. If a UI element cannot be traced to a product requirement, whiteboard requirement, user trust requirement, or operating requirement, it should not be in the first full-flow build.
