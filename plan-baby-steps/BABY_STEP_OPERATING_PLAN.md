# Baby Step Operating Plan

This is the slow plan. The point is not to rush into code. The point is to make every step traceable back to the source of truth, then build the full UI flow one small piece at a time.

Primary source of truth:

`/Users/omarebrahim/.codex/attachments/e0e18a4b-bcbb-410a-a9ec-beb1ef328da2/pasted-text.txt`

Supporting source packet:

- `/Users/omarebrahim/Anticipy/docs/audit/2026-06-27-deep-audit/AUDIT.md`
- `/Users/omarebrahim/Anticipy/docs/audit/2026-06-27-deep-audit/STAGE_MATRIX.md`
- `/Users/omarebrahim/Anticipy/docs/audit/2026-06-27-deep-audit/BABY_STEPS_PLAN.md`
- `/Users/omarebrahim/Anticipy/docs/audit/2026-06-27-deep-audit/CONTEXT_MANAGEMENT.md`
- `/Users/omarebrahim/Anticipy/docs/audit/2026-06-27-deep-audit/EVIDENCE_LEDGER.md`
- `/Users/omarebrahim/Anticipy/docs/audit/2026-06-27-deep-audit/whiteboards`

## Operating Rule

No UI gets built just because it seems useful.

Every UI piece must answer:

1. Which source-of-truth requirement does this serve?
2. Which user moment does this support?
3. Which state of the product loop does this represent?
4. What is functional now, seeded now, or coming soon?
5. How will this be verified later?

If those answers are not clear, stop and write them down before building.

## Phase 1: Go Through Everything

Goal:
- Inventory the entire product surface before building.

What to go through:
- Source-of-truth document.
- Whiteboards.
- Existing audit packet.
- Existing static `web/` screens.
- Existing Next `app/` screens.
- Existing engine endpoints.
- Extension setup and browser-hand UI needs.
- Memory, voice, active listening, onboarding, browser, tasks, settings, privacy, proof, and evidence flows.
- Existing listen plumbing: browser stream, local Mac mic start/stop/status, MP3/audio upload, and transcript ingestion.
- Original source-document use-case categories, treated as fixtures rather than examples.

Deliverables:
- Updated `SCREEN_INVENTORY.md`.
- Updated `REUSE_MAP.md`.
- Complete route map.
- Complete state map.
- Complete backend plumbing map.
- List of UI elements that must be tagged as `coming_soon`.

Done when:
- We can name every screen, every state, and every major component before coding it.

Do not:
- Start coding because one screen feels obvious.
- Build only onboarding or transcript.
- Skip settings, memory, proof, task detail, browser work, or error states.

## Phase 2: Understand Everything

Goal:
- Turn the inventory into one coherent product model.

Questions to answer:
- What does the user see before signup?
- What does the user see after signup but before setup?
- What does the user see when the extension is missing?
- What does the user see while Anticipy reads their world?
- What does the user see during Call 1 and Call 2?
- What does the user see after onboarding is complete?
- What does Anticipy show when it is listening?
- What does Anticipy show when browser mic permission is denied?
- What does Anticipy show when local Mac mic listening is enabled?
- What does Anticipy show when a transcript segment produces no task because it was noise/vent?
- What does Anticipy show when it catches a real task?
- What does Anticipy show when it ignores a vent?
- What does Anticipy show when it needs approval?
- What does Anticipy show while the browser hand is working?
- What does proof look like?
- What does memory look like?
- What does "stop" look like?
- What does "not connected" look like?

Deliverables:
- Single UI state machine.
- Single product journey map.
- Screen-by-screen acceptance criteria.
- Component list with ownership.

Done when:
- The product can be explained as one flow:

`welcome -> setup -> onboarding -> board -> input -> task -> approval -> browser work -> proof -> memory -> follow-up`

Do not:
- Let backend routes define the UI.
- Let old gate docs define the UI.
- Let technical setup language leak into consumer screens.

## Phase 3: Point Back To The Source Of Truth

Goal:
- Every screen and component gets a source anchor before implementation.

Use `SOURCE_OF_TRUTH_TRACEABILITY.md` for tags.

Required tag types:
- `ST-*`: source-of-truth document requirement.
- `WB-*`: whiteboard requirement.
- `AUD-*`: audit finding.
- `UX-*`: user-experience requirement.
- `SAFE-*`: safety/privacy/trust requirement.
- `OPS-*`: operating/evidence requirement.

Deliverables:
- Source tag list.
- Screen-to-source matrix.
- Component-to-source matrix.
- State-to-source matrix.
- `coming_soon` tag list for intentionally nonfunctional UI.

Done when:
- Every planned UI element can point to at least one tag.

Do not:
- Build untagged UI.
- Invent product claims not present in the source of truth.
- Hide `coming_soon` work as if it is functional.

## Phase 4: Incorporate Every Detail From The Source Of Truth

Goal:
- Make sure the source document's important details appear in the full UI plan.

Details that must be incorporated:
- Anticipy is "Donna from Suits": proactive, warm, human, competent.
- It listens to real life and catches commitments; active listening is a real product surface.
- Typed transcript, pasted transcript, MP3/audio upload, browser-tab mic, local Mac mic, and future pendant/phone input all map to one intake path.
- It ignores vents, hypotheticals, sarcasm, and throwaway comments.
- It can act, prepare-and-ask, or stay silent.
- It asks before money, sending, deleting, sharing, permissions, or irreversible actions.
- It works through browser surfaces, not as a generic OAuth dashboard.
- It remembers people, projects, tools, communication style, rules, open loops, and preferences.
- Onboarding is layered: Layer 1 read, Call 1, Layer 2 deeper read, Call 2, optional Layer 3, final operating contract.
- The "Great" screen must show the structured profile from onboarding: people, role/context, tools, open loops, style, trust/rules, and questions.
- The board must show work, asks, proof, memory, and follow-up.
- Every proof or approval must have an in-app state and a text/SMS mirror state.
- The original profession/use-case library must be represented as seeded fixtures and later tests.
- The UI must be clean enough for a normal person with no technical context.
- Proof must never fake done.
- Memory must be inspectable and correctable.
- Privacy and retention must be visible enough to earn trust.

Deliverables:
- Source detail checklist.
- UI copy checklist.
- Safety-state checklist.
- Memory-state checklist.
- Onboarding-state checklist.
- Active-listening state checklist.
- Backend-plumbing checklist.
- Use-case fixture checklist.

Done when:
- A reviewer can scan the UI plan and find every major source-of-truth detail represented somewhere.

Do not:
- Reduce the product to onboarding plus transcript.
- Treat browser work as a hidden black box.
- Treat memory as a backend-only feature.
- Treat voice/text as a later unrelated channel.

## Phase 5: Make Everything Point To That Truth And Scale The Operating System

Goal:
- Build a repeatable operating system around the baby-step plan.

At scale, the product needs a source-truth graph:

- Source requirement.
- User journey moment.
- Screen.
- Component.
- State.
- Endpoint.
- Data model.
- Safety rule.
- Evidence rule.
- Test.
- Receipt.
- Fixture category.
- Live/seeded/coming-soon mode.

Deliverables:
- Traceability matrix.
- Component registry.
- Route registry.
- State-machine registry.
- Evidence ledger.
- Decision log.
- Design token list.
- Copy dictionary.
- Verification checklist.

Done when:
- Any future agent can answer "why does this UI exist?" without guessing.

Do not:
- Let context live only in chat.
- Let screenshots be the only design source.
- Let a component exist without a source tag.
- Let a proof exist without saying what it does not prove.

## Phase 6: Build The Full Seeded UI Flow

Goal:
- Make the entire product visible on localhost with seeded state and basic backend contracts present.

Route:
- `http://localhost:3000/plan-baby-steps`

Build:
- Welcome.
- Sign.
- Setup.
- Browser helper.
- Layered onboarding.
- Calls.
- Great/profile review.
- Final contract.
- Done onboarding.
- Board.
- Active listening.
- Upload MP3/audio.
- Type/paste transcript.
- Task list.
- Go-to task approval/sort/comment screen.
- Task detail.
- Approval.
- Text mirror status.
- Browser work/proof.
- Memory.
- Settings.
- Internal debug drawer.
- Use-case fixture library.
- Backend plumbing skeleton for auth/profile/settings/listen/upload/intake/cards/comments.

Rules:
- Seeded UI is allowed.
- Seeded UI must be labeled honestly.
- No real user data mutation unless the surface is explicitly in `live` mode and uses a safe backend contract.
- Every screen includes source tags in code/data.
- Every button declares `mode: "coming_soon"`, `mode: "seeded"`, `mode: "read_only"`, or `mode: "live"`.
- All active-listening controls have visible stop/error/privacy states.

Done when:
- The full product story can be clicked through locally.
- The plan-baby-steps UI can show the full source-document loop and every use-case category with seeded data.
- Auth/profile/settings/listen/upload/intake/card/comment contracts exist even if most actions still show `coming soon`.

## Phase 7: Design Concepts And Design System

Goal:
- Turn the seeded flow into a polished product UI.

Do:
- Generate/review concepts for the major surfaces.
- Extract tokens:
  - color
  - type
  - spacing
  - radii
  - borders
  - shadows
  - motion
  - icon style
- Build reusable components from those tokens.

Done when:
- The UI has one consistent visual language.

## Phase 8: Read-Only Live Wiring

Goal:
- Let the UI reflect reality without taking action.

Wire:
- health
- status
- readiness
- extension connected
- listen status
- owner cards
- pending asks
- memory/open loops if available
- Supabase session state
- profile/settings read state

Done when:
- The UI tells the truth about the running system.

## Phase 9: Action Wiring

Goal:
- Let the UI do safe product work through the same contracts used by the seeded flow.

Wire:
- typed input
- upload
- browser-tab active listen stream
- local Mac mic start/stop/status
- transcript review
- approve/deny
- task comments
- sort preferences
- onboarding scan/read/complete
- autonomy settings
- memory correction
- text mirror state, initially coming soon unless Twilio is live-wired

Done when:
- The UI can create and resolve real work without exposing technical plumbing.
- Active listening can produce transcript segments and card refreshes without the user leaving the app.
- Settings/profile/comment saves are real for signed-in users.

## Phase 10: Full Product Verification

Goal:
- Verify the whole loop, not just isolated plumbing.

Test:
- new user
- returning user
- Supabase auth
- missing extension
- connected extension
- browser mic allowed
- browser mic denied
- local Mac mic unavailable
- MP3 upload
- typed/pasted transcript
- engine offline
- pending approval
- text mirror coming-soon/live state
- browser proof
- memory correction
- settings change
- each original use-case category as a seeded fixture
- mobile viewport
- desktop viewport

Done when:
- A normal person can use it without explanation.

## Research Applied

The operating model follows several proven patterns:

- GOV.UK Service Manual uses staged delivery from discovery to alpha, beta, live, and retirement. That maps to this plan's inventory, seeded alpha UI, live wiring, and promotion phases.
- NN/g journey mapping practice says to capture the user's bigger picture, touchpoints, needs, and gaps. That maps to the full Anticipy journey instead of isolated onboarding/transcript screens.
- Atlassian design tokens describe tokens as a single source of truth for design decisions. That maps to Anticipy's need for one design system, not one-off screen styling.
- IBM Carbon shows how scalable design systems separate foundations, components, guidelines, and working code. That maps to a reusable Anticipy component registry.
- Material Design frames design systems as adaptable foundations, components, and tools. That maps to Anticipy's need to support full app surfaces consistently.
- USWDS emphasizes starting with real user needs, accessibility, and shared principles. That maps to hiding technical setup and building for normal users first.
- GSA/18F de-risking guidance emphasizes lowering risk through staged, user-centered delivery and clear oversight. That maps to small baby steps with evidence instead of "gate green" claims.

Research links:

- https://www.gov.uk/service-manual/agile-delivery
- https://www.nngroup.com/articles/journey-mapping-101/
- https://atlassian.design/tokens/design-tokens
- https://carbondesignsystem.com/
- https://m3.material.io/foundations
- https://designsystem.digital.gov/design-principles/
- https://www.gsa.gov/blog/2024/09/11/a-revised-and-expanded-guide-for-derisking-government-technology-projects

## Immediate Next Baby Step

The next actual build step is not full wiring.

It is:

1. Create the traceability tags.
2. Create the seeded state machine.
3. Create the backend plumbing skeleton for auth/profile/settings/listen/upload/intake/cards/comments.
4. Create `app/plan-baby-steps/page.js`.
5. Render the full flow with source tags attached.
6. Include active listening as a visible first-class state.
7. Include every original source-document use-case category in the seeded fixture set.
8. Open it on localhost.
