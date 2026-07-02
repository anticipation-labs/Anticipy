# Source Of Truth Traceability

Every UI piece in the Baby Steps rebuild must point back to this file.

Primary source:

`/Users/omarebrahim/.codex/attachments/e0e18a4b-bcbb-410a-a9ec-beb1ef328da2/pasted-text.txt`

Supporting source:

`/Users/omarebrahim/Anticipy/docs/audit/2026-06-27-deep-audit`

## Tag Format

Use these tag families:

- `ST-*`: source-of-truth product requirements.
- `WB-*`: whiteboard requirements.
- `AUD-*`: audit findings.
- `UX-*`: user experience rules.
- `SAFE-*`: safety, trust, privacy, and confirmation rules.
- `OPS-*`: operating model, evidence, and verification rules.

Example in future code/data:

```js
const screen = {
  id: "onboarding-layer-1",
  title: "I am reading your world",
  sourceAnchors: ["ST-ONBOARD-LAYERED", "WB-DEEP-ONBOARDING", "SAFE-READ-ONLY-FIRST"]
};
```

## Core Source Tags

| Tag | Requirement | UI implication |
| --- | --- | --- |
| `ST-DONNA` | Anticipy is a proactive personal assistant, "Donna from Suits." | UI voice is warm, capable, plain-English, and personal. |
| `ST-LISTEN-REAL-LIFE` | It listens to real life and catches commitments. | Listen/upload/type all route into one assistant intake. |
| `ST-ACTIVE-LISTENING` | Ambient listening is a core input: typed transcript / MP3 now, pendant later. | Active listening gets its own UI state, transcript rail, permission states, and backend contract. |
| `ST-IGNORE-NOISE` | It ignores vents, hypotheticals, sarcasm, and throwaway comments. | UI shows safe ignoring internally; it does not create fake task cards. |
| `ST-ACT-ASK-SILENT` | It chooses act, prepare-and-ask, or stay silent. | Every task card has a visible disposition. |
| `ST-BROWSER-FIRST` | It works through browser surfaces the user already uses. | Browser helper and browser work viewer are first-class UI. |
| `ST-NO-FAKE-DONE` | It never pretends a task is complete. | Proof states distinguish prepared, parked, done, failed, and needs user. |
| `ST-MONEY-CONFIRM` | Money and irreversible actions always need confirmation. | Approval panel is mandatory for risky action states. |
| `ST-MEMORY` | It remembers people, work, preferences, open loops, and style. | Memory is top-level, inspectable, editable, and source-linked. |
| `ST-ONBOARD-LAYERED` | Onboarding is Layer 1, Call 1, Layer 2, Call 2, optional Layer 3, final contract. | Onboarding state machine must include all steps. |
| `ST-WARM-CHECKIN` | Check-ins should feel human and warm. | Calls/texts appear as plain conversation states, not system logs. |
| `ST-FOLLOW-THROUGH` | It follows through over time. | Follow-up and scheduled wake states appear in task detail and board. |
| `ST-ONE-LOOP` | Listen, infer, browser work, text/call, proof, and memory are one loop, not stitched demos. | State machine carries one task across every surface. |
| `ST-HORIZONTAL` | The same product must work across professions and arbitrary logged-in systems. | Use-case fixtures cover every source-document category; no per-demo hardcoding. |
| `ST-STRUCTURED-PROFILE` | Onboarding produces people, role/context, tools, open loops, style, trust/rules, and questions. | Great/Memory/Settings must show these fields explicitly. |
| `ST-CLEAN-FRONTEND` | Done means clean, easy frontend. | Main UI hides ports, providers, tokens, and internal setup language. |

## Original Use-Case Tags

The source document's long profession sections are acceptance fixtures, not marketing copy. Each category must be represented by seeded cards and later regression fixtures.

| Tag | Requirement | UI implication |
| --- | --- | --- |
| `UC-FOUNDER` | Startup founder/CEO scenarios: fundraising, investor updates, hiring, vendors, churn, board prep. | Cards must support high-stakes business tasks, money asks, drafts, research, and follow-up. |
| `UC-LAWYER` | Legal practice scenarios: deadlines, offers, billing, filings, conflicts, trust funds. | Cards must show jurisdiction/deadline/proof, parked irreversible actions, and client-send approvals. |
| `UC-CLINICIAN` | Doctor/clinician scenarios: patient context, referrals, orders, labs, follow-up. | UI must support sensitive/private proof, pended clinical actions, and never-autonomous care decisions. |
| `UC-REALESTATE` | Real estate scenarios: listings, offers, inspection, referrals, MLS/transaction systems. | Browser work viewer must handle pro web systems and money/contract approvals. |
| `UC-SALES-OPS` | Sales/operator scenarios: CRM, renewals, proposals, travel, account risk. | Task cards need account context, CRM evidence, and follow-through. |
| `UC-RECRUITER` | Recruiting/talent scenarios: ATS, scheduling, offers, references, scorecards. | UI must handle candidate outreach drafts, scheduling, and irreversible offer/money checkpoints. |
| `UC-ACCOUNTANT` | Accountant/bookkeeper scenarios: QBO/CRA/payroll/tax/document requests. | UI must distinguish prep from filing/payment and show exact money/deadline proof. |
| `UC-HOUSEHOLD` | Parent/household scenarios: returns, school forms, appointments, purchases. | UI must stay simple and family-friendly while retaining approval gates. |
| `UC-EMPLOYEE` | Employee/admin scenarios: expenses, approvals, travel, SOWs, internal tools. | Cards must support internal approvals, expense limits, and work-system evidence. |
| `UC-FREELANCER` | Freelancer/creative scenarios: late invoices, scope changes, proposals, publishing. | UI must support client tone, drafts, staged publishes, and recurrence/follow-up. |
| `UC-STUDENT` | Student/researcher scenarios: portals, deadlines, grants, committees, IRB. | UI must support academic portals, deadline math, pended submissions, and recommender outreach. |

## Whiteboard Tags

| Tag | Requirement | UI implication |
| --- | --- | --- |
| `WB-BABY-STEPS` | Build UI, build flow, then build around it. | Seeded full UI flow comes before deeper wiring. |
| `WB-FULL-UI` | All work should happen from a good-looking frontend. | No important workflow should require terminal/docs. |
| `WB-PROACTIVE` | Proactive system needs product wiring. | Board must show active proactive work and follow-up. |
| `WB-BROWSER-REHAUL` | Browser agent needs a rehaul. | Browser runtime gets its own progress/proof UI and safety states. |
| `WB-MEMORY-CONTEXT` | Memory/context management is major. | Memory center is top-level and detailed. |
| `WB-VOICE-OUTPUT` | Voice/text/call output is core. | Call and SMS states appear in onboarding and task approvals. |
| `WB-UPLOAD-LISTEN` | User needs upload MP3 and listen. | Input dock includes both from the first full flow. |
| `WB-BACKEND-PLUMBING-WITH-UI` | Frontend build should also include basic backend plumbing. | First implementation includes auth, profile/settings, status, listen, upload, intake, card, and comment contracts. |

## Audit Tags

| Tag | Requirement | UI implication |
| --- | --- | --- |
| `AUD-ONE-FRONTDOOR` | Too many entry points exist. | New UI starts with one canonical front door. |
| `AUD-ONE-BOARD` | Static and Next boards are split. | New UI picks one canonical board. |
| `AUD-ONBOARDING-GAP` | Current onboarding is not the source-of-truth loop. | New onboarding includes call-guided layers. |
| `AUD-BROWSER-SPLIT` | Browser control paths are split. | UI labels the canonical browser helper and hides non-product paths. |
| `AUD-EVIDENCE-INTEGRITY` | Old gate proofs overclaim. | UI proof states and docs avoid "green/certified" language. |
| `AUD-HARDCODING` | Hardcoded local/provider details leak. | Consumer UI hides technical details. |
| `AUD-MEMORY-LIFECYCLE` | Memory needs lifecycle/privacy. | Memory UI includes source, edit, forget, archive. |
| `AUD-LISTENING-UNDER-SPECED` | Active listening existed in pieces but was not represented as a full UI/backend flow. | Listening has explicit permission, stream, transcript, ingest, error, and retention states. |
| `AUD-PLUMBING-NOT-PRODUCT` | Prior work exposed routes without usable product surfaces. | Every backend route wired in the plan has a matching screen state and acceptance test. |

## Safety Tags

| Tag | Requirement | UI implication |
| --- | --- | --- |
| `SAFE-RISKY-CONFIRM` | Confirm before money/send/delete/share/permissions. | Approval panel required. |
| `SAFE-POINT-OF-RISK` | Confirmation must happen at the moment of risk. | Browser proof viewer parks at final review. |
| `SAFE-READ-ONLY-FIRST` | Reading is safer than acting. | Onboarding and browser work distinguish read vs act. |
| `SAFE-REDACT-PROOF` | Proof can contain private data. | Proof viewer redacts sensitive details by default. |
| `SAFE-USER-CONTROL` | User can stop, correct, or override. | Stop/edit/forget controls exist in task and memory views. |
| `SAFE-LISTENING-CONTROL` | Listening must be obvious, controllable, and stoppable. | Mic starts only from a user action; UI shows recording/live status and stop controls. |
| `SAFE-RETENTION` | Captured audio/transcripts and proof can be sensitive. | Settings include retention, delete, and redaction states. |

## UX Tags

| Tag | Requirement | UI implication |
| --- | --- | --- |
| `UX-FIVE-YEAR-OLD` | Normal user should understand the flow. | No internal terms in primary UI. |
| `UX-STATUS-PLAIN` | System status should be human-readable. | Readiness becomes "Browser helper ready," not raw JSON. |
| `UX-COMING-SOON-HONEST` | Nonfunctional pieces must be labeled. | Seeded/lab states identify what is not wired. |
| `UX-NO-LANDING-ONLY` | Build the actual product, not just marketing. | `/plan-baby-steps` shows the app flow. |
| `UX-CLEAR-NEXT-ACTION` | Each blocked state needs one next action. | Empty/error/setup screens have one obvious action. |
| `UX-TEXT-FIRST` | Text is an equal interface to in-app actions. | Every ask/proof has a text mirror status and plain SMS copy state. |

## Operating Tags

| Tag | Requirement | UI implication |
| --- | --- | --- |
| `OPS-TRACEABILITY` | Every UI piece maps to source. | Components include source anchors. |
| `OPS-EVIDENCE` | Proof must say what it proves and does not prove. | Proof panel includes scope labels. |
| `OPS-SEED-FIRST` | Full flow can be seeded before wired. | UI lab can use safe mock data. |
| `OPS-LIVE-LATER` | Wire read-only before actions. | Status/cards before mutate routes. |
| `OPS-VERIFY-VISUAL` | UI must be tested visually on localhost. | Browser screenshot and responsive checks before promotion. |
| `OPS-BASIC-PLUMBING` | UI and backend contracts advance together. | First build includes minimal APIs/contracts for auth, profile, settings, listen, upload, cards, comments, and source-tagged fixtures. |
| `OPS-USE-CASE-FIXTURES` | The source examples become repeatable tests. | Seed data and later regression tests include each `UC-*` category. |

## Screen-To-Source Matrix

| Screen | Required tags |
| --- | --- |
| Welcome | `ST-DONNA`, `ST-CLEAN-FRONTEND`, `AUD-ONE-FRONTDOOR`, `UX-FIVE-YEAR-OLD` |
| Setup checklist | `ST-CLEAN-FRONTEND`, `UX-STATUS-PLAIN`, `AUD-HARDCODING` |
| Browser helper | `ST-BROWSER-FIRST`, `WB-BROWSER-REHAUL`, `AUD-BROWSER-SPLIT`, `SAFE-READ-ONLY-FIRST` |
| Layered onboarding | `ST-ONBOARD-LAYERED`, `WB-MEMORY-CONTEXT`, `AUD-ONBOARDING-GAP`, `SAFE-READ-ONLY-FIRST` |
| Calls/check-ins | `ST-WARM-CHECKIN`, `WB-VOICE-OUTPUT`, `UX-FIVE-YEAR-OLD` |
| Board | `ST-ACT-ASK-SILENT`, `ST-FOLLOW-THROUGH`, `AUD-ONE-BOARD`, `WB-PROACTIVE` |
| Input dock | `ST-LISTEN-REAL-LIFE`, `ST-ACTIVE-LISTENING`, `WB-UPLOAD-LISTEN`, `UX-CLEAR-NEXT-ACTION` |
| Active listening panel | `ST-ACTIVE-LISTENING`, `SAFE-LISTENING-CONTROL`, `AUD-LISTENING-UNDER-SPECED`, `OPS-BASIC-PLUMBING` |
| MP3/upload | `ST-LISTEN-REAL-LIFE`, `WB-UPLOAD-LISTEN`, `OPS-BASIC-PLUMBING` |
| Task detail | `ST-NO-FAKE-DONE`, `ST-FOLLOW-THROUGH`, `OPS-EVIDENCE` |
| Approval panel | `ST-MONEY-CONFIRM`, `SAFE-RISKY-CONFIRM`, `SAFE-POINT-OF-RISK` |
| Text mirror | `ST-WARM-CHECKIN`, `UX-TEXT-FIRST`, `WB-VOICE-OUTPUT` |
| Browser work viewer | `ST-BROWSER-FIRST`, `ST-NO-FAKE-DONE`, `SAFE-REDACT-PROOF` |
| Memory | `ST-MEMORY`, `AUD-MEMORY-LIFECYCLE`, `SAFE-USER-CONTROL` |
| Great profile review | `ST-STRUCTURED-PROFILE`, `ST-ONBOARD-LAYERED`, `UX-FIVE-YEAR-OLD` |
| Settings | `ST-MONEY-CONFIRM`, `SAFE-USER-CONTROL`, `SAFE-LISTENING-CONTROL`, `SAFE-RETENTION`, `UX-FIVE-YEAR-OLD` |
| Debug drawer | `OPS-EVIDENCE`, `OPS-TRACEABILITY`, `AUD-EVIDENCE-INTEGRITY` |
| Use-case fixture library | `ST-HORIZONTAL`, `OPS-USE-CASE-FIXTURES`, all `UC-*` tags |

## Code Rule For Future Implementation

When building `app/plan-baby-steps`, every screen object should include:

```js
sourceAnchors: ["..."]
```

Every visible `coming_soon` feature should include:

```js
mode: "seeded" // or "read_only", "live", "coming_soon"
```

Every task/proof state should include:

```js
proofScope: "what this proves and what it does not prove"
```

This is how the UI stays tied to the truth while we build slowly.
