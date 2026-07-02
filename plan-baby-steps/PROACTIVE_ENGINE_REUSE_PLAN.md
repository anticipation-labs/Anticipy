# Proactive Engine Reuse Plan

Primary source of truth:

`/Users/omarebrahim/.codex/attachments/e0e18a4b-bcbb-410a-a9ec-beb1ef328da2/pasted-text.txt`

Related baby-step tags:

- `ST-LISTEN-REAL-LIFE`
- `ST-ACTIVE-LISTENING`
- `ST-IGNORE-NOISE`
- `ST-ACT-ASK-SILENT`
- `ST-BROWSER-FIRST`
- `ST-MONEY-CONFIRM`
- `ST-FOLLOW-THROUGH`
- `ST-ONE-LOOP`
- `WB-PROACTIVE`
- `WB-BROWSER-REHAUL`
- `AUD-PLUMBING-NOT-PRODUCT`
- `OPS-BASIC-PLUMBING`

## Decision

Do not replace the current repo's proactive spine with an old copy.

The best running proactive system is already in the current repo:

- `/Users/omarebrahim/Anticipy/engine/anticipy_engine/core/proactive.py`
- `/Users/omarebrahim/Anticipy/engine/anticipy_engine/core/control_core.py`
- `/Users/omarebrahim/Anticipy/engine/anticipy_engine/proactive/triage.py`
- `/Users/omarebrahim/Anticipy/engine/anticipy_engine/proactive/decider.py`
- `/Users/omarebrahim/Anticipy/engine/anticipy_engine/proactive/harm.py`
- `/Users/omarebrahim/Anticipy/engine/anticipy_engine/main.py`

That is the product spine to keep.

The older V7 system is still valuable, but as source/spec material:

- `/Users/omarebrahim/.anticipy/engine/app/proactive`
- `/Users/omarebrahim/Developer/Anticipy-V7/engine/app/proactive`

Pull the typed contracts, layered-cascade idea, and eval harness concepts from V7. Do not copy the whole engine over this repo.

## Local Systems Found

### Current Repo

Path:

`/Users/omarebrahim/Anticipy`

What exists:

- The live FastAPI engine surface.
- The real proactive spine under `engine/anticipy_engine/core/proactive.py`.
- Owner intake under `engine/anticipy_engine/owner_mode.py`.
- Active listening endpoints under `/listen/start`, `/listen/stop`, `/listen/status`, and browser WebSocket paths.
- Owner task endpoints under `/owner/ingest`, `/owner/ingest-file`, `/owner/cards`, `/pending`, `/resolve`, `/trigger/tick`.
- Tests for messy proactive handoff, owner ingest, inbound YES/NO, pending persistence, and proactive scoring.

Why this wins:

- It is already wired to the currently running app.
- It has the strongest safety posture: money is terminally blocked, irreversible actions ask, pending asks are durable, and unread model decisions fail toward silence.
- It has the best follow-through mechanics currently in the repo: trigger tick, reminders, digest queue, follow-up check routing, and text/call channel support.

Main issue:

- Some UI still mixes seeded/demo cards with real engine cards, so the product surface can make real plumbing feel fake. Fixing that is a UI wiring baby step, not a reason to replace the engine.

### Older V7 / `.anticipy` Engine

Paths:

- `/Users/omarebrahim/.anticipy/engine/app/proactive`
- `/Users/omarebrahim/Developer/Anticipy-V7/engine/app/proactive`

What exists:

- A five-layer proactive cascade:
  - speaker/user chunk classification
  - salience
  - intent extraction
  - reversibility
  - urgency
  - Donna pass
  - deterministic route combiner
- Typed objects for transcript chunks, intents, decisions, confidence, urgency, notification channel, confirmation responses, and status events.
- Synthetic scenario generation and LLM-judge eval harness.
- A useful product idea: no raw audio in server contracts, only diarized transcribed chunks.

What exists separately and is not wired here:

- V7 package layout is `app.*`, not `anticipy_engine.*`.
- The V7 `ProactiveEngine.on_transcript_chunk` facade is not used by the current FastAPI app.
- V7 Supabase publish paths are not current app routes.
- V7 eval harness is not wired into this repo's CI/test scripts.

What to pull:

- Contract language and data shapes.
- Eval categories and scenario-generation approach.
- Layered-cascade framing for future LLM-backed interpretation.
- The no-raw-audio contract.

What not to pull directly:

- Whole routing stack.
- Old daemon/installer copies.
- Old duplicate extension/runtime folders.
- Any route or package import that reintroduces the disabled `.anticipy` daemon as a second product spine.

### `Anticipy-executor-working`

Path:

`/Users/omarebrahim/Anticipy-executor-working`

What exists:

- A near-copy of current proactive code with some executor experiments.

Why it does not win:

- Its proactive diff weakens the current repo's hard money wall into a money prepare path.
- The current repo has safer behavior: terminal money block, digest queue, in-app ask suppression, call-channel reminders, and linked follow-up notifications.

Use it only as:

- A comparison source when looking for missing executor/browser ideas.

Do not:

- Copy its `core/proactive.py` or `harm.py` over the current repo.

### Desktop Verification Scripts

Path:

`/Users/omarebrahim/Desktop/Omar System Test/scripts`

What exists:

- Verification scripts for proactive/browser flows.

Use it for:

- Future full-story tests after the product path is clean.

Do not use it as:

- The engine source of truth.

## Current Product Flow

The current app already has this path:

`UI input/listen/upload -> Next API proxy -> FastAPI /owner/ingest or /owner/ingest-file -> ControlCore -> ProactiveEngine -> triage -> decider -> harm wall -> orchestrator/pending ask -> /owner/cards -> UI board -> /resolve`

Important implementation fact:

`engine/anticipy_engine/proactive/engine.py` is a stub. The real engine is `engine/anticipy_engine/core/proactive.py`.

## What Is Done Enough To Keep

- Owner text/transcript intake.
- MP3/transcript file ingestion route.
- Local and browser listening routes.
- Triage and ignore behavior for many messy speech shapes.
- Harm wall for money/irreversible actions.
- Durable pending asks.
- YES/NO inbound resolution.
- Reminder/follow-up tick.
- Readiness and status endpoints.
- `/owner/cards` as the UI's real task source.

## What Is Not Done

- The UI still needs to stop mixing fixture cards into the real board by default.
- V7-style typed transcript/decision contracts are not formalized in the current package.
- V7-style scenario categories are not imported into this repo's eval harness.
- The browser agent is not yet one clean product runtime with final-action safety tokens.
- The active listening UI needs to show one simple path from mic/transcript to real cards without developer wording.
- The memory lifecycle still needs visible user controls for retention, correction, archive, and deletion.

## Pull Strategy

Pull one thin slice at a time.

### Slice 1: Make The Current Spine Explicit

Goal:

- Stop future agents from looking at `engine/anticipy_engine/proactive/engine.py` and thinking the proactive engine is empty.

Implementation:

- Add/keep this plan.
- Update reuse docs to name `core/proactive.py` as canonical.
- Keep tests green.

Done when:

- A new agent can identify the running proactive engine in under two minutes.

### Slice 2: Pull V7 Contracts Into Current Package

Goal:

- Give active listening, browser handoff, cards, and future phone/pendant input one shared typed language.

Implementation:

- Create `engine/anticipy_engine/proactive/contracts.py`.
- Adapt from V7 `types.py`, but use current package naming.
- Include no raw audio fields.
- Include:
  - `TranscriptChunk`
  - `Intent`
  - `Decision`
  - `DecisionKind`
  - `Reversibility`
  - `Confidence`
  - `Urgency`
  - `NotificationChannel`
  - `ConfirmationResponse`
  - `EngineStatusEvent`
- Add a small test proving the contract serializes and contains no audio payload.

Done when:

- New intake code can speak through a shared contract without replacing the existing engine.

### Slice 3: Adapt Current Owner Cards To The Contract

Goal:

- Let the UI and browser hand know whether each item is `act`, `ask`, `silent`, `blocked`, `prepared`, or `done` in one consistent vocabulary.

Implementation:

- Add an adapter from `OwnerTaskCard` and `ProactiveEngine` decision results into the contract types.
- Keep `/owner/cards` response backward-compatible.
- Add contract metadata to each card:
  - source mode
  - disposition
  - risk
  - proof scope
  - text/call mirror state
  - source anchors

Done when:

- The UI can render real proactive work without guessing from strings.

### Slice 4: Port V7 Eval Categories

Goal:

- Test the source-of-truth behavior: catch real commitments, ignore vents, ask before money/irreversible actions, follow through.

Implementation:

- Add V7 scenario categories into the current eval harness.
- Keep deterministic self-test as the default.
- Add optional LLM judge mode behind an explicit flag.
- Add source-use-case fixture groups from `SOURCE_OF_TRUTH_TRACEABILITY.md`.

Done when:

- The current engine is scored against source-truth behavior, not just a small handpicked day.

### Slice 5: UI Real-Card Mode

Goal:

- Stop making the product look fake when the engine is real.

Implementation:

- Default the task board to live `/owner/cards`.
- Show seeded fixtures only in an explicit demo/library mode or when the engine is unreachable.
- Every card says one of:
  - Live
  - Seeded
  - Read-only
  - Coming soon
- Every approval/proof says whether text/SMS mirror is live or coming soon.

Done when:

- A real transcript creates a real card and the UI does not bury it under demo cards.

### Slice 6: Browser Runtime Safety Handoff

Goal:

- Connect proactive decisions to browser action without letting browser action outrun the safety model.

Implementation:

- The proactive engine produces an action plan and risk class.
- The browser hand can prepare reversible work.
- The browser hand must stop before final send/pay/delete/share/permission/submit.
- Final action requires a fresh confirmation token scoped to that exact action.
- Browser proof gets read back independently and attached to the card.

Done when:

- A proactive card can drive browser prep, park at risk, get approved, execute, and return proof.

## Next Immediate Baby Step

Do Slice 1 now, then Slice 2.

Why:

- Replacing the engine would regress safety.
- Writing the canonical map prevents more duplicate plumbing.
- Pulling contracts gives us a clean seam for active listening, browser handoff, and UI cards without disturbing the currently passing spine.

Verification for Slice 1:

- `engine/scripts/test_proactive.py`
- `engine/scripts/test_messy_proactive_handoff.py`
- `engine/scripts/test_owner_ingest_event.py`
- `engine/scripts/test_inbound.py`
- `engine/scripts/test_pending_persistence.py`
- `engine/scripts/proactive_eval.py --selftest`

## 2026-06-28 Gateway Implementation Slice

Implemented the first Plan Baby Steps gateway slice in the live repo while keeping
the current runtime canonical.

Added:

- Canonical `ProactiveGatewayEnvelope` and lane records in `engine/anticipy_engine/proactive/contracts.py`.
- Append-only gateway ledger in `engine/anticipy_engine/proactive/gateway.py`.
- Engine read surface: `GET /proactive/gateway/recent`.
- Next proxy: `GET /api/proactive/gateway`.
- Mirror writes from owner ingest, memory/card persistence, browser result landing,
  approval resolution, listening status, and ConversationRelay voice turns.
- Phase Zero UI circuit panel for board, upload, review, memory, and settings.
- Separate lab inventory at `/Users/omarebrahim/Anticipy-proactive-lab`.

What this means:

`input -> gateway event -> owner card -> memory/browser/voice/text proof -> UI circuit`

is now a real observable path, not just a plan. Existing behavior stays backward-compatible;
the gateway is an additive ledger and contract layer first.

Verification:

- `engine/scripts/test_proactive_contracts.py`
- `engine/scripts/test_proactive_gateway.py`
