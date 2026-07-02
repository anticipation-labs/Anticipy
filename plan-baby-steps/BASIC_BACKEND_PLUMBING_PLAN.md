# Basic Backend Plumbing Plan

This file exists because the Baby Steps UI build is not allowed to become a decorative frontend.

Primary source:

`/Users/omarebrahim/.codex/attachments/e0e18a4b-bcbb-410a-a9ec-beb1ef328da2/pasted-text.txt`

## Goal

While building the full UI, add the minimum backend contracts that let the UI become the real product one slice at a time.

This is not the full browser/proactive rebuild. It is the first clean product plumbing layer:

- Auth.
- Profile.
- Settings.
- Onboarding state.
- Active listening state.
- Upload/intake.
- Card refresh.
- Task comments.
- Text mirror status.
- Source/use-case fixtures.

Every route returns calm product-shaped data. Raw ports, provider names, owner tokens, stack traces, and vendor internals stay out of the consumer UI.

## Existing Pieces To Reuse

Current Next/engine pieces already present:

- `app/api/_engine.js`: engine URL, owner/local fallback, private engine proxy.
- `app/api/listen/stream/route.js`: returns the engine websocket URL for `/listen/stream`.
- `app/api/owner/upload/route.js`: stores upload temporarily and forwards to engine `/owner/ingest-file`.
- `app/api/owner/ingest/route.js`: forwards typed/pasted intake to engine `/owner/ingest`.
- `app/api/owner/cards/route.js`: forwards card refresh.
- `app/api/resolve/route.js`: approval/deny path.
- Engine `/owner/ingest-file`: transcribes audio/text uploads and routes to owner intake.
- Engine `/listen/start`, `/listen/stop`, `/listen/status`: local Mac mic listening.
- Engine `/listen/stream`: browser audio stream -> Deepgram -> transcript -> owner intake.
- Engine `/owner/cards`, `/pending`, `/memory/*`, `/readiness`, `/status`.

Current frontend behavior worth lifting:

- `app/page.js`: live listen websocket handling, upload handling, card grouping, pending asks.
- `web/auth.js` and `web/auth-screen.js`: Supabase auth flow and human error copy.
- `web/app.js`: board interaction tone and old active-listening copy.

## First Plumbing Contracts

### Auth

Build:

- Supabase browser client.
- Supabase server/client helpers.
- `/auth/confirm` for email confirmation.
- Route guard helpers.
- Sign-in/sign-up/sign-out actions.

Rules:

- Use publishable/anon public key only in the browser.
- No service-role or secret key in client code.
- User-facing routes accept Supabase sessions.
- Local owner-token mode remains a dev fallback, not the hosted-user path.

### Profile And Onboarding State

Build:

- Profile get/save.
- Onboarding-state get/save.
- "Great" profile-review data shape.

Minimum fields:

- Name.
- One-sentence summary.
- Phone.
- Timezone.
- Trust dial.
- Text-first preference.
- Do-not-touch zones.
- People.
- Role/context.
- Tools/systems.
- Open loops.
- Communication style.
- Open questions.

### Settings

Build:

- Settings get/save.
- Autonomy/security level.
- Confirm-before rules.
- Text/call preference.
- Active-listening preference.
- Retention/redaction preference.
- Browser helper/device status.

### Active Listening

Build:

- Read-only listen status adapter.
- Browser mic stream adapter.
- Local Mac mic start/stop/status adapter.
- Shared event normalizer for:
  - `transcript`
  - `utterance_end`
  - `processing`
  - `ingest_result`
  - `ingest_error`
  - `error`

UI contract:

- `ready`
- `permission_denied`
- `listening`
- `transcribing`
- `processing`
- `cards_created`
- `no_task_created`
- `stopped`
- `unavailable`

Safety:

- Mic starts only after a click.
- Stop is always visible.
- Transcript retention is explained in Settings.
- Browser-tab listening never claims to continue after the tab closes.

### Upload And Intake

Build:

- Typed/pasted transcript submit.
- MP3/audio/text upload submit.
- Transcript review state.
- Card refresh after intake.

Rules:

- Default to safe card creation; do not imply browser execution unless that route is live.
- Surface "prepared" and "needs approval" separately from "done."

### Cards, Comments, And Text Mirror

Build:

- Normalize engine cards into UI task cards.
- Save task comments.
- Save sort preference.
- Show text mirror status for every ask/proof:
  - `coming_soon`
  - `queued`
  - `sent`
  - `delivered`
  - `failed`

Do not fake SMS delivery. If Twilio is not live-wired, the UI says `Text mirror coming soon`.

### Source Fixtures

Build:

- Source-tagged seeded fixtures for each original use-case category:
  - founder
  - lawyer
  - clinician
  - real estate
  - sales/operator
  - recruiter
  - accountant
  - household
  - employee
  - freelancer
  - student/researcher

Each fixture must include:

- Heard text.
- Ignored noise/vent.
- Caught task.
- Browser work plan.
- Approval/check-in.
- Proof.
- Memory write.
- Follow-up.

## Verification

Before promotion out of `/plan-baby-steps`, verify:

- Supabase sign-in/sign-up/check-email/sign-out.
- Profile and settings save for the signed-in user.
- Read-only engine status.
- Listen status.
- Browser mic denied state.
- Browser mic unavailable state.
- MP3 upload happy/error states.
- Typed/pasted transcript creates a card.
- Seeded use-case library renders every category.
- Approval card shows both in-app and text mirror status.
- No consumer UI exposes ports, provider names, owner tokens, stack traces, or raw vendor errors.

