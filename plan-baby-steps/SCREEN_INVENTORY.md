# Screen Inventory

This is the full UI surface area to build.

The inventory below must cover both:

1. The user-requested baby-step route set: Welcome, Sign, Onboarding Basics, Onboarding 2-8, Great, Done, MP3, Go to, Settings.
2. The full original source-of-truth product loop: listen -> infer -> ignore noise -> prepare/act/ask -> browser work -> text/call check-in -> proof -> memory -> follow-up.

## 1. Welcome

Purpose:
- Make Anticipy understandable immediately.

Primary copy:
- "Hi, I am Anticipy. I listen, learn your day, and ask before anything important."

Elements:
- Brand.
- One primary `Start` button.
- Sign in/sign up state.
- Returning-user continue state.

States:
- Signed out.
- Signed in.
- Loading account.
- Error signing in.

Source anchors:
- `ST-DONNA`
- `ST-CLEAN-FRONTEND`
- `AUD-ONE-FRONTDOOR`
- `UX-FIVE-YEAR-OLD`

## 1A. Sign

Purpose:
- Let the user sign in or create an account with email/password.

Elements:
- Email field.
- Password field.
- Show/hide password.
- Sign in.
- Create account.
- Check-email confirmation state.
- Human auth errors.

States:
- Sign in.
- Sign up.
- Creating account.
- Check your email.
- Signed in.
- Invalid credentials.
- Email not confirmed.
- Network/auth unavailable.

Backend plumbing:
- Supabase browser client.
- Supabase server/session helper.
- `/auth/confirm` token exchange route.
- Route protection for app pages.

Source anchors:
- `WB-BACKEND-PLUMBING-WITH-UI`
- `OPS-BASIC-PLUMBING`
- `UX-FIVE-YEAR-OLD`

## 2. Setup Checklist

Purpose:
- Turn technical readiness into human setup steps.

Elements:
- Browser helper ready.
- Signed-in accounts readable.
- Text/call ready.
- Memory ready.

States:
- Ready.
- Needs action.
- Checking.
- Could not connect.
- Skipped for now.

## 3. Browser Helper Setup

Purpose:
- Install/pair the extension without developer language.

Elements:
- Download/open helper.
- Pair this browser.
- Connection status.
- Safe explanation of permissions.

States:
- Not installed.
- Installed but not paired.
- Pairing.
- Paired.
- Disconnected.
- Needs update.

## 4. Layered Onboarding

Purpose:
- Make the source-of-truth onboarding visible.

Screens/states:
- Layer 1 reading.
- Layer 1 findings.
- Call 1 scheduling/active/complete.
- Layer 2 reading.
- Layer 2 findings.
- Call 2 scheduling/active/complete.
- Optional Layer 3.
- Final confirmation call.
- Operating contract.

Elements:
- Progress stepper.
- Reading activity.
- Findings grouped by people/projects/tools/open loops/rules.
- Questions Anticipy needs answered.
- Call panel.
- Final contract summary.

User-requested route states:
- `/onboarding/basics`: hidden bootstrap/readiness checkpoint.
- `/onboarding/2`: visible simple profile form.
- `/onboarding/3`: hidden Layer-1 broad read.
- `/onboarding/4`: hidden warm Call 1.
- `/onboarding/5`: hidden Layer-2 deep read.
- `/onboarding/6`: hidden Call 2.
- `/onboarding/7`: hidden optional Layer-3 targeted read.
- `/onboarding/8`: hidden final call/contract.

Profile fields produced:
- People who matter.
- Role and context.
- Tools and systems inventory.
- Open loops with priority.
- Communication style model.
- Trust and rules config.
- Open questions.

Source anchors:
- `ST-ONBOARD-LAYERED`
- `ST-STRUCTURED-PROFILE`
- `WB-MEMORY-CONTEXT`
- `AUD-ONBOARDING-GAP`

## 5. Main Board

Purpose:
- Daily home.

Elements:
- Status strip.
- Listen button.
- Upload MP3 button.
- Type/paste input.
- Active work list.
- Needs your okay list.
- Done/recent list.
- Follow-up list.

States:
- Empty first day.
- Working.
- Waiting on user.
- Browser disconnected.
- Engine offline.
- Lots of tasks.

Source anchors:
- `ST-ACT-ASK-SILENT`
- `ST-FOLLOW-THROUGH`
- `ST-ONE-LOOP`
- `AUD-ONE-BOARD`

## 6. Input Dock

Purpose:
- One place for the user to give Anticipy material.

Modes:
- Listen.
- Upload MP3.
- Type.
- Paste transcript.

Elements:
- Mode segmented control.
- Recording state.
- Upload state.
- Transcript review.
- Submit.

States:
- Idle.
- Listening.
- Uploading.
- Transcribing.
- Review transcript.
- Submitted.
- Error.

Backend plumbing:
- Type/paste -> `/api/owner/ingest`.
- Upload -> `/api/owner/upload`.
- Browser mic stream -> `/api/listen/stream`.
- Local mic controls -> listen start/stop/status proxy.

Source anchors:
- `ST-LISTEN-REAL-LIFE`
- `ST-ACTIVE-LISTENING`
- `WB-UPLOAD-LISTEN`
- `OPS-BASIC-PLUMBING`

## 6A. Active Listening

Purpose:
- Make ambient listening visible, controllable, and honest.
- Represent "real life" input as a first-class daily state, not just a one-time form.

Elements:
- Start listening.
- Stop listening.
- Live status dot.
- Mic permission explanation.
- Live transcript rail.
- Interim transcript.
- Final transcript segments.
- Speaker labels when available.
- Processing indicator.
- "Cards created" result.
- Quiet debug trace for ignored/no-task segments.
- Retention/privacy hint.

Listening modes:
- Browser-tab listening through `navigator.mediaDevices.getUserMedia` and `/api/listen/stream`.
- Local Mac mic listening through engine `/listen/start`, `/listen/stop`, `/listen/status`.
- Uploaded audio through MP3/upload.
- Future pendant/phone source as a not-yet-live device state.

States:
- Ready.
- Browser mic denied.
- Browser mic unsupported.
- Listening live.
- Speech detected.
- Segment finalized.
- Processing segment.
- Ingest result received.
- Card created.
- No task surfaced.
- Engine offline.
- Deepgram/key unavailable.
- Local mic unavailable.
- Stopped.

Rules:
- Mic starts only after a user action.
- Stop is always visible while listening.
- Normal UI does not celebrate ignored vents; it simply does not create cards.
- Debug/source drawer may expose ignored segments for verification.
- The UI must not imply browser-tab listening continues after the tab closes.

Backend plumbing:
- Reuse existing Next discovery route `/api/listen/stream`.
- Normalize WebSocket events: `transcript`, `utterance_end`, `processing`, `ingest_result`, `ingest_error`, `error`.
- Add/read listen status for local Mac mic.
- Route all accepted transcript chunks to the same owner intake/card refresh contract.

Source anchors:
- `ST-ACTIVE-LISTENING`
- `ST-IGNORE-NOISE`
- `SAFE-LISTENING-CONTROL`
- `SAFE-RETENTION`
- `AUD-LISTENING-UNDER-SPECED`

## 6B. MP3 / Audio Upload

Purpose:
- Let the user upload MP3/audio/transcript files and review the text before cards are created.

Elements:
- File drop/select.
- Accepted file type copy.
- Upload progress.
- Transcribing state.
- Transcript preview.
- Submit transcript.
- Clear/retry.

States:
- Idle.
- File selected.
- Uploading.
- Transcribing.
- Transcript ready.
- Cards created.
- Too large.
- Unsupported file.
- Transcription failed.

Backend plumbing:
- `/api/owner/upload` -> engine `/owner/ingest-file`.
- Audio route uses local transcriber if available.
- Text upload routes as text upload.

Source anchors:
- `ST-LISTEN-REAL-LIFE`
- `WB-UPLOAD-LISTEN`
- `OPS-BASIC-PLUMBING`

## 7. Task List

Purpose:
- Show every task in plain language.

Groups:
- Working now.
- Needs your okay.
- Scheduled.
- Done.
- Stopped.

Each card shows:
- What Anticipy heard.
- What it thinks it should do.
- Status.
- Risk level.
- Next action.
- Last update time.
- Text mirror status.
- Source/use-case fixture tag in debug mode.

Go-to route requirements:
- Approve.
- Deny.
- Sort by status/date/risk/source.
- Comment on a task.
- Show proof/readback.
- Show whether the same ask/proof was sent by text or is coming soon.

Source anchors:
- `ST-ACT-ASK-SILENT`
- `UX-TEXT-FIRST`
- `ST-HORIZONTAL`
- `OPS-USE-CASE-FIXTURES`

## 8. Task Detail

Purpose:
- Explain one task end to end.

Sections:
- Heard.
- Understood.
- Context used.
- Plan.
- Browser/account work.
- Approval.
- Text/call mirror.
- Proof.
- Memory writes.
- Follow-up.

States:
- Preparing.
- Needs approval.
- Running.
- Parked at final review.
- Done.
- Failed honestly.
- Stopped by user.

Source anchors:
- `ST-ONE-LOOP`
- `ST-NO-FAKE-DONE`
- `OPS-EVIDENCE`

## 9. Approval Panel

Purpose:
- Ask before meaningful real-world impact.

Elements:
- Plain ask.
- Why Anticipy is asking.
- What happens if approved.
- What will not happen.
- Approve.
- Not now.
- Change instructions.

Risk-specific states:
- Send message.
- Money/payment.
- Delete/cancel.
- Share private data.
- Permission change.
- Contact someone.

Mirrors:
- In-app ask.
- SMS/text ask.
- Call ask for onboarding or high-touch states.
- Comment/change-instructions path.

Source anchors:
- `SAFE-RISKY-CONFIRM`
- `SAFE-POINT-OF-RISK`
- `UX-TEXT-FIRST`

## 10. Browser Work Viewer

Purpose:
- Let the user understand browser work without seeing raw logs.

Elements:
- Connected browser status.
- Current site/app.
- Step list.
- Prepared result.
- Parked-at-review status.
- Screenshot/proof summary, redacted where needed.

States:
- Waiting for browser helper.
- Reading.
- Preparing.
- Needs user login.
- Needs approval.
- Proof ready.
- Failed honestly.

Source anchors:
- `ST-BROWSER-FIRST`
- `ST-NO-FAKE-DONE`
- `AUD-BROWSER-SPLIT`

## 11. Memory

Purpose:
- Build trust by showing what Anticipy knows.

Sections:
- About me.
- People.
- Projects.
- Tools and accounts.
- Preferences.
- Open loops.
- Recent learned facts.
- Archived/expired.

Controls:
- Edit.
- Forget.
- Archive.
- Mark important.
- Explain source.

States:
- Empty.
- Needs review.
- Conflicting facts.
- Sensitive item.
- Deleted.

Must include structured profile:
- People who matter.
- Role/context.
- Tools and systems inventory.
- Open loops and priority.
- Communication style.
- Trust/rules.
- Open questions.

Source anchors:
- `ST-MEMORY`
- `ST-STRUCTURED-PROFILE`
- `AUD-MEMORY-LIFECYCLE`

## 12. People And Relationships

Purpose:
- Make the "Donna" context inspectable.

Elements:
- Important people.
- Relationship.
- Preferred channel.
- Current open loops.
- Notes and boundaries.

States:
- Learned from onboarding.
- User-confirmed.
- Needs clarification.

Source anchors:
- `ST-DONNA`
- `ST-MEMORY`
- `ST-STRUCTURED-PROFILE`

## 13. Great / Profile Review

Purpose:
- Show the user what Anticipy believes it learned and ask the last clarification questions before daily operation.

Elements:
- Facts I know about you.
- People who seem important.
- Tools and systems found.
- Open loops found.
- Communication-style read.
- Trust/rules summary.
- Clarifying questions.
- Edit/correct controls.
- Continue to Done.

States:
- No facts yet.
- Facts loaded.
- Needs clarification.
- User corrected a fact.
- Ready for final contract.

Backend plumbing:
- Reads onboarding-state/profile memory.
- Saves corrections to profile/settings/memory contract.

Source anchors:
- `ST-STRUCTURED-PROFILE`
- `ST-ONBOARD-LAYERED`
- `ST-MEMORY`

## 14. Done Onboarding

Purpose:
- Mark the transition from setup to living with the assistant.

Elements:
- Operating contract summary.
- Next actions: Listen, Upload MP3, Go to tasks, Settings.
- Text/call readiness status.
- Browser helper readiness.

States:
- Complete.
- Complete but text/call not ready.
- Complete but browser helper missing.
- Resume setup.

Source anchors:
- `ST-ONE-LOOP`
- `ST-WARM-CHECKIN`
- `UX-FIVE-YEAR-OLD`

## 15. Use-Case Fixture Library

Purpose:
- Make the original source document buildable and testable across all promised domains.

Fixture categories:
- Founder/CEO.
- Lawyer/legal practice.
- Doctor/clinician.
- Real estate agent.
- Sales/operator.
- Recruiter/talent.
- Accountant/bookkeeper.
- Parent/household manager.
- Employee/internal operator.
- Freelancer/creative.
- Student/academic/researcher.

Each fixture renders:
- Heard text.
- Caught task.
- Ignored vent/noise.
- Browser exploration plan.
- Approval/check-in.
- Proof.
- Memory write.
- Follow-up.

Source anchors:
- `ST-HORIZONTAL`
- `OPS-USE-CASE-FIXTURES`
- all `UC-*` tags.

## 16. Settings

Purpose:
- Control trust and privacy.

Sections:
- Autonomy.
- Confirm-before rules.
- Do-not-touch.
- Voice/text.
- Active listening.
- Browser helper.
- Data retention.
- Export/delete.
- Text-first mirror.
- Proof redaction.

States:
- Default.
- Limited mode.
- Full-send mode.
- Privacy review needed.
- Listening disabled.
- Listening enabled for this tab.
- Local Mac mic enabled.
- Retention change pending.

Backend plumbing:
- Saves autonomy/security/text-first/listening/retention settings.
- Reads listen status.
- Shows whether SMS/call is live or coming soon.

Source anchors:
- `SAFE-LISTENING-CONTROL`
- `SAFE-RETENTION`
- `UX-TEXT-FIRST`
- `OPS-BASIC-PLUMBING`

## 17. Internal Debug Drawer

Purpose:
- Keep technical truth available without exposing it to normal users.

Elements:
- Engine status.
- Extension status.
- Model/hands/channel mode.
- Raw route errors.
- Receipt links.

Rule:
- This drawer is hidden behind an internal toggle and never part of the main consumer path.

## 18. Global States

Every screen needs:
- Loading.
- Empty.
- Error.
- Offline.
- Permission denied.
- Needs sign in.
- Needs extension.
- Needs phone.
- Engine unavailable.
- Sensitive data redacted.
