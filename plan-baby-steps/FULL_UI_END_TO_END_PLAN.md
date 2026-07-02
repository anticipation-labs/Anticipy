# Full UI End-To-End Plan

This plan is subordinate to the source of truth:

`/Users/omarebrahim/.codex/attachments/e0e18a4b-bcbb-410a-a9ec-beb1ef328da2/pasted-text.txt`

Before implementing any screen from this plan, tag it with the anchors in:

`/Users/omarebrahim/Anticipy/plan-baby-steps/SOURCE_OF_TRUTH_TRACEABILITY.md`

The operating sequence for moving slowly is:

`Phase 1 go through everything -> Phase 2 understand everything -> Phase 3 point back -> Phase 4 incorporate every detail -> Phase 5 scale the source-truth operating system -> then build`

## Product Bar

The UI is done when a normal user can open Anticipy and understand the whole product without seeing engine words, ports, provider names, repo instructions, owner tokens, or developer setup.

The product being represented here is the original pasted source of truth, not a generic assistant UI:

- Ambient listening is a core first-class surface, not a later add-on.
- Typed transcript, pasted transcript, MP3/audio upload, browser-tab mic streaming, and local Mac mic listening all feed one intake.
- The intake result is always the same loop: listen -> infer real tasks -> silently ignore noise -> prepare/act/ask -> browser work -> warm check-in -> proof -> memory -> follow-up.
- Onboarding is not a settings wizard. It is the Layer-1 scrape, Call 1, Layer-2 scrape, Call 2, optional Layer-3 scrape, final confirmation call, and operating contract.
- The UI must support the full use-case library in the source document: founder/CEO, lawyer, clinician, real-estate agent, sales/operator, recruiter/talent, accountant/bookkeeper, parent/household, employee, freelancer/creative, and student/researcher. These are not copy examples only; they become acceptance fixtures for the card/task/proof model.
- Basic backend plumbing is built alongside the UI so the frontend is never a decorative shell. The first build still labels unfinished actions honestly, but auth, profile/settings storage, read-only status, upload/intake, active-listening status, and safe card refresh have real contracts.

The user path should feel like:

1. "Start."
2. "Install or pair the browser helper."
3. "Let Anticipy read my world."
4. "Take the warm onboarding call."
5. "Approve what Anticipy learned."
6. "Land on my assistant board."
7. "Talk, upload, or type."
8. "Watch Anticipy prepare work."
9. "Approve anything important."
10. "See proof, memory, and follow-up."

## Core Decision

Build the new UI as a side-by-side Next route first:

`app/plan-baby-steps/page.js`

Do not replace the current root UI until the full flow has been reviewed on localhost. The side-by-side route must still include basic backend plumbing adapters and source-tagged data contracts so promotion to the real routes is mechanical, not a rewrite.

Once approved, promote it into the real routes:

- `/`
- `/welcome`
- `/sign`
- `/onboarding/basics`
- `/onboarding/2`
- `/onboarding/3`
- `/onboarding/4`
- `/onboarding/5`
- `/onboarding/6`
- `/onboarding/7`
- `/onboarding/8`
- `/great`
- `/done`
- `/mp3`
- `/go-to`
- `/memory`
- `/settings`

The user-requested route set is preserved even while the lab route exists:

| Requested page | Final route | Product role |
| --- | --- | --- |
| Welcome | `/welcome` | First human front door. |
| Sign | `/sign` | Supabase email/password sign-in and sign-up. |
| Onboarding Basics | `/onboarding/basics` | Hidden bootstrap/readiness checkpoint. |
| Onboarding 2 | `/onboarding/2` | Visible simple profile: name, one-sentence summary, phone, timezone, trust dial, boundaries. |
| Onboarding 3 | `/onboarding/3` | Hidden Layer-1 broad read state. |
| Onboarding 4 | `/onboarding/4` | Hidden Call-1/warm intro state. |
| Onboarding 5 | `/onboarding/5` | Hidden Layer-2 deeper read state. |
| Onboarding 6 | `/onboarding/6` | Hidden Call-2/gap fill state. |
| Onboarding 7 | `/onboarding/7` | Hidden optional Layer-3 targeted read state. |
| Onboarding 8 | `/onboarding/8` | Hidden final confirmation call/contract state. |
| Great | `/great` | Shows what Anticipy learned and asks final clarifying questions. |
| Done | `/done` | Onboarding completion and next-step chooser. |
| MP3 | `/mp3` | Upload MP3/audio/transcript. |
| Go to | `/go-to` | Task board with approve/deny, sort, comment, proof, and text mirror. |
| Settings | `/settings` | Permissions, autonomy, privacy, memory, text/call, active listening, and data retention. |

## What "Full UI" Means

Full UI does not mean every backend action works on day one.

Full UI means every product surface exists, the navigation makes sense, all states are designed, and every nonfunctional part has an honest "not connected yet" state.

Required surfaces:

1. Public entry.
2. Auth.
3. Setup/readiness.
4. Browser helper pairing.
5. Layered onboarding.
6. Call/check-in states.
7. Main board.
8. Active listening.
9. Upload MP3/audio.
10. Type/paste transcript.
11. Active tasks.
12. Approval asks.
13. Task detail.
14. Browser progress/proof.
15. Follow-ups.
16. Memory.
17. People/context.
18. Settings/autonomy/privacy.
19. Devices/connections.
20. Text/call mirror for every proof or ask.
21. Empty/loading/error/offline states.

## Visual Direction

Anticipy should not look like a marketing SaaS landing page or a technical admin console.

It should feel like a calm personal operating room:

- Clean.
- Warm but not beige-heavy.
- Quiet.
- Obvious.
- Built for a nontechnical person.
- Dense enough for daily work, but not intimidating.
- Human copy first, technical diagnostics hidden.

Design tone:

- Main app is task-focused, not decorative.
- Cards are for repeated task items and modals only.
- Avoid nested cards.
- Avoid hero sections after signup.
- Use clear segmented controls, toggles, status dots, icons, and plain labels.
- The first screen should make the product obvious in one sentence.

Before final implementation, generate UI concepts for:

1. First-run welcome/setup.
2. Layered onboarding flow.
3. Main board.
4. Task detail/proof state.
5. Memory/settings.

Then implement faithfully from the accepted concept.

## Information Architecture

### First-run path

`/welcome`

Purpose:
- Welcome the user.
- Sign in or sign up.
- Start setup.

Primary states:
- Signed out.
- Signed in, not set up.
- Setup interrupted.
- Ready to continue onboarding.

### Setup path

`/setup` or inside `/welcome`

Purpose:
- Get the browser helper ready.
- Confirm phone/text readiness.
- Confirm Anticipy can read the user's signed-in world.

User-facing checklist:
- Browser helper ready.
- I can read your signed-in accounts.
- I can call/text you.
- I am learning your world.

Do not show:
- `127.0.0.1`
- `8787`
- Railway
- Supabase
- Twilio
- API hands
- owner token
- memory ledger
- developer mode

### Onboarding path

`/onboarding`

Purpose:
- Guide the source-of-truth onboarding loop.

Flow:

1. Layer 1 reading.
2. Call 1.
3. Layer 2 reading.
4. Call 2.
5. Optional Layer 3.
6. Final confirmation call.
7. Operating contract summary.
8. Enter board.

The UI should show what Anticipy is doing in plain language:

- "I am reading recent email and calendar."
- "I found the people and projects that seem important."
- "I need to ask you a few questions."
- "I am going deeper on these open loops."
- "Here is how I will work for you."

### Main app shell

`/`

Purpose:
- Daily Anticipy home.

Navigation:
- Board.
- Tasks.
- Memory.
- Settings.

Primary first screen:
- Welcome/status strip.
- Listen.
- Upload MP3.
- Type/paste.
- Active work.
- Pending asks.

### Active listening

`/` primary dock plus `/settings` controls

Purpose:
- Represent the original requirement that Anticipy's input is real life, not a todo form.
- Let the user start/stop listening, see what was heard, review live transcript segments, and understand what is being acted on versus silently ignored.

Listening modes:
- Browser-tab mic stream: frontend asks for microphone permission, streams audio to `/api/listen/stream`, receives transcript/ingest events, and updates cards.
- Local Mac mic: frontend controls `/listen/start`, `/listen/stop`, and `/listen/status` through Next proxy endpoints when the local engine supports it.
- Uploaded audio: `/mp3` and upload surfaces send files through `/api/owner/upload` -> engine `/owner/ingest-file`.
- Typed/pasted transcript: sends to `/api/owner/ingest`.

Required states:
- Not allowed by browser.
- Ready to listen.
- Listening live.
- Heard transcript segment.
- Processing segment.
- Real task created.
- No task created because it was vent/noise.
- Needs approval.
- Engine missing `DEEPGRAM_API_KEY` or local mic dependency.
- Stopped by user.

Rules:
- Mic access only starts after a human click.
- Browser mic UI must work on `https` and `localhost`; it must explain if the browser blocks mic access.
- The product never shows "ignored vent" as a celebratory event in normal UI; a debug/source drawer can show it for verification.
- The listen surface must never imply always-on background listening in the browser after the tab is closed. Local Mac mic and future pendant listening are separate device states.

### Tasks

`/tasks`

Purpose:
- List everything Anticipy is doing, waiting on, done, blocked, or following up on.

Views:
- Working now.
- Needs your okay.
- Scheduled follow-up.
- Done.
- Stopped.

### Task detail

`/tasks/[id]`

Purpose:
- Show one task's full story.

Sections:
- What Anticipy heard.
- What Anticipy understood.
- What it checked.
- What it prepared.
- What it needs from you.
- Proof.
- Memory written.
- Follow-up plan.

### Memory

`/memory`

Purpose:
- Let the user inspect and correct what Anticipy knows.

Sections:
- About me.
- People.
- Projects.
- Tools and accounts.
- Preferences.
- Open loops.
- Recent learned facts.
- Archived or expired memory.

Controls:
- Edit.
- Forget.
- Archive.
- Mark as important.
- Explain why Anticipy knows this.

### Settings

`/settings`

Purpose:
- Autonomy, privacy, notifications, devices, and account.

Sections:
- Autonomy dial.
- Money/irreversible rules.
- Do-not-touch list.
- Voice/text settings.
- Browser helper/device.
- Data retention.
- Export/delete account.

## Full Flow State Machine

This is the core UI spine:

1. `signed_out`
2. `signed_in_needs_helper`
3. `helper_ready`
4. `permissions_ready`
5. `onboarding_layer_1`
6. `onboarding_call_1`
7. `onboarding_layer_2`
8. `onboarding_call_2`
9. `onboarding_layer_3_optional`
10. `final_contract`
11. `done_onboarding`
12. `board_ready`
13. `listen_ready`
14. `listening_live`
15. `listen_processing`
16. `input_received`
17. `transcript_review`
18. `task_created`
19. `working`
20. `needs_approval`
21. `approved`
22. `text_mirror_sent_or_queued`
23. `browser_preparing`
24. `parked_at_final_review`
25. `proof_ready`
26. `memory_updated`
27. `follow_up_scheduled`
28. `done`
29. `failed_honestly`

The UI should be built around this state machine even before the backend fully supports every transition.

## Component System

Build reusable components first:

- `AppShell`
- `TopBar`
- `SideNav`
- `StatusRail`
- `ReadinessChecklist`
- `OnboardingStepper`
- `CallPanel`
- `InputDock`
- `ActiveListeningPanel`
- `LiveTranscriptRail`
- `TranscriptReview`
- `TaskCard`
- `TaskList`
- `TaskDetail`
- `ApprovalPanel`
- `BrowserProgress`
- `ProofPanel`
- `TextMirrorBadge`
- `MemoryDrawer`
- `MemoryItem`
- `SettingsSection`
- `AutonomyDial`
- `DeviceCard`
- `EmptyState`
- `ErrorState`

No one giant page component.

## Basic Backend Plumbing To Build With The UI

These are part of the first real implementation, not a later "plumbing sprint":

- Supabase auth helpers for Next: browser client, server/client auth check, `/auth/confirm`, sign-in/sign-up/sign-out, and route protection.
- User-owned profile/settings/onboarding-state storage with RLS-ready contracts: profile summary, phone/timezone, trust dial, text-first preference, do-not-touch zones, active-listening preference, and onboarding progress.
- Next proxy auth bridge that accepts Supabase user sessions for user-facing routes and keeps owner-token/local mode as a dev fallback.
- Read-only status adapters for health/readiness/extension/listen status so the UI shows reality.
- Intake adapters for typed, pasted, uploaded, and listened input, initially with safe `execute_actions` defaults and visible mode labels.
- Card/task adapters that normalize engine cards into UI cards without leaking raw provider names or proof internals.
- Comment/settings save endpoints so "sort and comment" and permissions/settings are not fake controls.
- A source-tagged seed data library built from the original use cases, so every profession scenario can render as cards, approvals, browser work, proof, memory writes, and follow-up.
- A `coming_soon` registry attached to each action so the UI can remove labels one by one as the backend turns live.

## Build Phases

### Phase 1: UI lab plus plumbing skeleton

Build:
- `app/plan-baby-steps/page.js`
- `app/plan-baby-steps/ui-plan.css` or shared CSS/module
- Seeded local data file
- Full product journey in one route
- Shared route/state/component registries with `sourceAnchors`
- Supabase auth utilities and `/sign` UI contract
- Profile/settings/onboarding-state contracts
- Listen/status/intake adapter contracts

Goal:
- Open localhost and click through the entire UI while seeing which pieces are seeded, read-only, live, or coming soon.

Done when:
- The user can see the whole product story.
- Every major state exists.
- It is honest about what is not wired.
- Sign/auth screens have real Supabase-ready code paths.
- Backend contracts exist for active listening, upload, typed intake, settings, and card refresh even if some are still seeded.

### Phase 2: Design approval and polish

Build:
- Responsive desktop/mobile states.
- Empty/loading/error/offline states.
- Final component hierarchy.

Goal:
- Make the UI feel like the product before wiring.

Done when:
- The UI no longer feels like a wireframe.

### Phase 3: Read-only wiring

Wire:
- `/api/health`
- `/api/status`
- `/api/readiness`
- `/api/owner/cards`
- memory/open loops, if exposed through proxy

Goal:
- Real status appears without actions.

Done when:
- The UI accurately reflects engine/extension/readiness state.

### Phase 4: Input and active-listening wiring

Wire:
- typed/paste to `/api/owner/ingest`
- upload to `/api/owner/upload`
- browser-tab active listening through `/api/listen/stream`
- local Mac mic controls through `/listen/start`, `/listen/stop`, `/listen/status` proxy adapters
- transcript review and live card refresh after `ingest_result`

Goal:
- User can create real cards from typed, pasted, uploaded, and listened input.

Done when:
- Input creates cards and the board updates.
- Active listening can be started/stopped from the UI, shows transcript segments, creates cards when the engine returns an ingest result, and shows a clear human error when microphone, Deepgram, or engine plumbing is unavailable.

### Phase 5: Approval and task detail wiring

Wire:
- pending asks.
- approve/deny to `/api/resolve`.
- task detail from card/proof records.

Goal:
- User can approve or deny work from the new UI.

Done when:
- Pending ask state changes correctly.

### Phase 6: Onboarding wiring

Wire:
- permissions.
- scan.
- deep read.
- loop.
- call state.
- complete.

Goal:
- Source-of-truth onboarding flow becomes real.

Done when:
- Onboarding ends in an operating contract and board entry.
- The "Great" page can show the structured profile fields required by the source document: people, role/context, tools/systems, open loops, communication style, trust/rules, and open questions.

### Phase 7: Browser work visibility

Wire:
- browser connected state.
- browser job progress.
- proof and readback.

Goal:
- User sees what the browser hand is doing without seeing technical logs.

Done when:
- A browser task shows observe/prepare/review/proof states.

### Phase 8: Memory and settings wiring

Wire:
- memory drawers.
- open loops.
- autonomy mode.
- privacy controls.
- device state.
- active listening preferences and retention controls.
- text-first notification preference.
- comments and sorting preferences for the `Go to` task screen.

Goal:
- User can inspect and change context.

Done when:
- Memory/settings stop being decorative.

### Phase 9: Promote canonical routes

Move the approved UI out of `/plan-baby-steps` into real routes:

- `/welcome`
- `/onboarding`
- `/`
- `/tasks`
- `/memory`
- `/settings`

Demote old setup/admin pages.

### Phase 10: Acceptance pass

Test:
- Desktop.
- Mobile.
- Clean first-run.
- Returning user.
- Supabase sign-in/sign-up/check-email/confirm.
- No extension.
- Extension connected.
- Engine offline.
- Browser mic denied.
- Browser mic live stream unavailable.
- Local Mac mic unavailable.
- MP3 upload.
- Typed/pasted transcript.
- Pending approval.
- Text mirror status on a proof/ask.
- Browser proof.
- Memory correction.
- Settings save.
- All source use-case fixture categories render at least one card/task/proof path.

Done when:
- A normal user can operate the UI without explanation.

## Localhost Plan

First preview URL:

`http://localhost:3000/plan-baby-steps`

Expected dev command:

`npm run dev`

If port 3000 is busy, use the next available port and report it.

The first localhost preview should not mutate real data unless explicitly switched from seeded mode to live mode.

## Open Decisions For Omar

1. Should the first visual direction be closer to the static `web/` pages or the current Next board?

   Recommendation: use the static `web/` tone, but the Next app structure.

2. Should the first implementation be a one-page UI lab or real routes immediately?

   Recommendation: one-page UI lab first, then promote routes.

3. Should onboarding be visually mandatory before the board, or can users skip to the board?

   Recommendation: allow "skip for now" in dev, but production should complete minimum setup first.

4. Should memory be a top-level nav item from day one?

   Recommendation: yes. Memory is core to trust.

5. Should technical diagnostics exist?

   Recommendation: yes, but hidden under an internal/debug drawer, never in the main consumer path.
