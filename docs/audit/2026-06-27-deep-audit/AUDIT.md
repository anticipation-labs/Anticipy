# Anticipy Deep Audit - 2026-06-27

Branch audited: `factory/build`

Runtime audited:
- Repo: `/Users/omarebrahim/Anticipy`
- Engine: `http://127.0.0.1:8787`
- Engine log: `/tmp/eng.log`
- Static app: `/Users/omarebrahim/Anticipy/web/app.html`
- Repo extension: `/Users/omarebrahim/Anticipy/extension`
- Loaded Chrome extension: `/Users/omarebrahim/Desktop/0-ANTICIPY-EXTENSION-LOAD-ME`
- Source-of-truth document: `/Users/omarebrahim/.codex/attachments/e0e18a4b-bcbb-410a-a9ec-beb1ef328da2/pasted-text.txt`

## Verdict

Anticipy has a real internal skeleton. The engine can ingest owner text or files, create cards, write memory, classify safety/autonomy, create pending asks, talk to a connected Chrome extension, run a WebVoyager-style browser loop, text/call through Twilio when configured, and schedule follow-ups.

It is not yet the finished product described in the source-of-truth. The finished product is one continuous loop:

`listen -> infer -> real logged-in browser work -> warm check-in -> close loop -> remember -> improve over days`

The current system is closer to:

`typed/uploaded input -> proactive/card plumbing -> local memory -> some live Chrome/voice/API connections -> several separated browser/onboarding/proof paths`

The main failure pattern is not lack of plumbing. The problem is that the plumbing is split across multiple frontends, multiple browser runtimes, several proof systems, old "Gate" docs, demo recipes, mock defaults, and local-only assumptions. This makes it easy to prove a component and still not have a clean user-facing flow.

## Explain It Like I Am Five

Anticipy has many working parts on the table: a brain, a notebook, a browser hand, a phone/text line, and a board where it shows work.

But they are not yet one toy you can hand to a normal person. Some buttons go to one brain, some go to another page, some proofs are from practice runs, some browser actions use the real Chrome extension, and some use a separate browser. The user can see technical setup pages instead of one obvious "Start" path.

The fix is not "add more pipes." The fix is to pick one front door, one board, one browser hand, one onboarding state machine, and one proof ledger. Then test the whole thing like a real person would use it.

## Senior Architecture Read

The correct architecture is a product state machine wrapped around existing primitives:

1. `UserSurface`
   - One hosted first-run path.
   - One board after onboarding.
   - No local ports, owner tokens, provider names, or developer setup language in consumer flow.

2. `Identity + Device`
   - Per-user auth.
   - Paired browser extension/device identity.
   - All live browser jobs scoped to the signed-in user/device.

3. `Input Bus`
   - Typed, upload, live mic, Twilio call/SMS, and browser/onboarding events enter one event model.

4. `Control Core`
   - Triage, intent extraction, autonomy, safety wall, pending ask creation, memory writes, follow-up scheduling.

5. `Memory OS`
   - Profile, people, systems, open loops, history, derived facts, evidence.
   - Retention, redaction, deletion, and source attribution are first-class, not afterthoughts.

6. `Browser Runtime`
   - One canonical extension-driven runtime for user accounts.
   - Observe/read -> prepare -> ask if needed -> execute -> prove -> remember.
   - Final executor safety blocks irreversible/pay/send/credential actions even if the planner makes a mistake.

7. `Voice/Message Layer`
   - Warm calls/texts for check-ins and onboarding.
   - Inbound replies route to the same pending-ask resolver.

8. `Evidence Ledger`
   - Capability proof is not a "gate closed" doc.
   - Proof means real product path, durable result, independent readback, scope limits, and expiry.

## Source Of Truth Synthesis

The source-of-truth says Anticipy is "Donna from Suits": a proactive personal assistant that listens to the real day, catches commitments, ignores vents/sarcasm/hypotheticals, decides whether to act or ask, works through the same browser surfaces the user uses, remembers everything that matters, and asks before money or irreversible actions.

The onboarding target is layered:

1. Layer 1 broad browser/account scrape.
2. Phone Call 1 to confirm people, role, hard rules, autonomy, and gaps.
3. Layer 2 deeper adaptive reading of email/calendar/docs/tools.
4. Phone Call 2 to fill real gaps and priorities.
5. Optional targeted Layer 3.
6. Final confirmation call that states the operating contract.

The source-of-truth "done" bar is real owner use, not demo proof:

- Works through a clean frontend.
- Works in logged-in real systems.
- Survives multi-day operation.
- Reduces meaningful workload.
- Never acts on vents.
- Never fakes done.
- Confirms money, sending, deletion, permissions, and other irreversible actions at the point of risk.
- Remembers and improves.

## Whiteboard Synthesis

The whiteboards reinforce the same product shape:

- "Baby Steps" says: build the UI, define the flow, make the flow exist, then build around it.
- Proactive is expected to be close but needs product wiring and real use tests.
- Browser needs a rehaul, not more one-off recipes.
- Voice/input/output are core but should feel simple.
- Memory/context management is a major system, not a pile of saved text.
- The working software must be demonstrable through a good-looking frontend.
- The user sees welcome, setup/onboarding, upload/listen, live task board, memory/settings, and active tasks.

The board photos are preserved under:

`/Users/omarebrahim/Anticipy/docs/audit/2026-06-27-deep-audit/whiteboards`

## Live Runtime Findings

Read-only live checks on `2026-06-27` showed:

- `/health`: engine is alive.
- `/status`: extension connected, memory counts present, pending approvals present.
- `/ws/state`: `connected: true`.
- `/readiness`: overall still needs setup; Google/Arcade, Twilio, and browser bridge report live; Apple signing still needs setup.
- `/onboard/status`: onboarding marked complete.
- `/onboard/permissions`: Gmail, Calendar, Contacts, and LinkedIn allowed.
- `/owner/cards?limit=8`: board contains real card proof from a browser task and an approved task.

Important: live card proof can include sensitive browser/account details. Audit artifacts should not copy raw card JSON, order IDs, addresses, contact data, screenshots, or similar proof payloads. Receipts need redaction and access control before they become product evidence.

## What Exists And Is Wired

Engine:
- `engine/anticipy_engine/main.py` exposes health/status/readiness, ingest, memory, owner cards, onboarding, pending/resolve, browser, voice, and extension routes.
- `engine/anticipy_engine/core/control_core.py` is the real center: memory, owner mode, browser hand, API hand, channels, proactive engine, pending asks, cards, and follow-up.
- `engine/anticipy_engine/core/proactive.py` is the active proactive engine.
- `engine/anticipy_engine/memory/store.py` and `engine/anticipy_engine/live_memory/*` provide local durable memory primitives.
- `engine/anticipy_engine/agent/webvoyager.py` provides a real observe/act browser agent loop.

Frontend:
- `web/app.html` and `web/app.js` are the cleanest static board surface and call the real engine.
- `web/onboard.html` and `web/onboard.js` provide a product-shaped onboarding shell.
- `app/page.js` is a more operational Next owner board with upload, memory, open loops, settings, and owner APIs.
- `app/api/*` proxies many engine routes.

Extension:
- `extension/background.js` connects to `/ws/extension`, observes pages, acts through Chrome debugger/DOM fallbacks, discovers service logins, and runs shallow deep-scrapes.
- Loaded Desktop extension currently matches repo extension by `diff`.

Voice/text:
- Twilio outbound text/call can be live.
- `/voice` and `/cr` routes exist.

Evidence:
- Several deterministic safety and behavior harnesses exist.
- Some live receipts exist for narrow API/channel/browser cases.

## What Exists Separately Or Is Not Wired

- Static `web` and Next `app` are two product surfaces, not one clear canonical flow.
- Static onboarding, Next `/welcome`, Next `/onboarding`, `/connect`, and `/download` all represent different setup stories.
- `/api/browser/run` calls engine `/agent/act`, a browser-use path, not the owner-card extension/WebVoyager path.
- `/api/owner/stop` forwards to `/owner/stop`, but no matching FastAPI route was found, even though `ControlCore.stop_owner_card()` exists.
- `ControlCore.onboard_scan_api()` exists, but `/onboard/scan` uses extension scan behavior instead.
- `OnboardingCallBrain` exists, but not as the required scrape-call-scrape-call-final-contract onboarding loop.
- `/hands/compose-email` exists, but repo evidence says the expected CDP client file is missing or broken.
- API/Arcade hand paths remain wired even though the product direction says browser-first/no per-service OAuth for user-facing action.
- Pairing/heartbeat code exists in the extension, but the active extension socket mostly binds through `/ws/token` and default core behavior.

## What Exists In Isolation, Demo, Or Mock Mode

- `engine/anticipy_engine/proactive/engine.py` is a stub and not the active proactive runtime.
- `BrowserHand` and channel modes can default to mock.
- The general test suite forces stub model/mock hands/mock channels.
- Browser-use fallback runs in a throwaway browser and does not prove logged-in owner Chrome.
- Amazon return flow is deeply special-cased through env-gated demo card behavior, URL starts, selected quantity/reason/comment, and WebVoyager recipe logic.
- Marketing landing demo scenes are canned.
- Public extension zip is stale and does not reflect the current extension source.
- Many old "Gate" docs and guarantee certificates overstate product readiness.

## How The Current System Works

Primary owner input path:

1. User submits text or upload through frontend/API.
2. `/owner/ingest` or `/owner/ingest-file` enters the engine.
3. `ControlCore.owner_ingest()` parses and expands tasks.
4. Deterministic and model-assisted guardrails classify vent/sarcasm/hypothetical/money/action.
5. Memory is written/read back.
6. A durable owner card is created.
7. Safe simple tasks may go to proactive execution.
8. Browser-shaped tasks become pending asks.
9. User approves through UI/SMS/resolve.
10. `_run_browser_and_confirm()` runs extension/WebVoyager if connected, otherwise fallback.
11. Result is judged, written to card proof, and follow-up may be scheduled.

Onboarding path today:

1. UI calls permissions/scan/loop/complete.
2. Extension can discover service login state.
3. Extension can collect shallow page metadata from supported services.
4. Engine synthesizes profile/dossier-like data.
5. Onboarding can be marked complete.

This is not yet the layered scrape-call-deeper-scrape-call-final-contract flow.

Browser path today:

1. Extension connects to engine WebSocket.
2. Engine sends `browse_job` messages.
3. Extension observes page, returns text/elements/screenshot.
4. WebVoyager decides next action.
5. Extension acts.
6. Loop repeats until result/handoff/failure.

Safety is mostly planner-side and control-core-side. The final extension executor can still click/type if instructed, so it needs its own irreversible-action hard stop.

## Hardcoding And Product Seams

High-priority hardcoding/seams found:

- Static web hardcodes Railway engine fallback.
- Next API defaults to `http://127.0.0.1:8787`.
- Extension and popup hardcode local engine URL.
- Static auth hardcodes Supabase project URL/key.
- `/download` contains placeholder `github.com/your-org/anticipy.git`.
- `/onboarding` exposes local engine, memory ledger, and extension developer mechanics to users.
- Service discovery/permissions are fixed lists.
- Browser start URLs are hardcoded for retail/services.
- Amazon return recipe hardcodes a specific flow, quantity, reason, and comment.
- `ARCADE_USER_ID` and admin-email defaults create single-owner assumptions.
- Receipts and cards can persist raw sensitive browser proof.

Hardcoding is acceptable only when it is explicitly labeled as a test fixture, internal adapter, or seeded default. It is not acceptable in the core product path.

## Why We Keep Failing

1. We prove plumbing, then call it product.
   - A route returning 200 is not the assistant completing work.

2. We have multiple "truth" docs.
   - Source-of-truth, current-state, wakeup, gate, and guarantee docs conflict.

3. We use proxy proofs.
   - Mock browser tests, public demo sites, API Calendar proof, and throwaway browser tasks are useful but do not prove logged-in owner operation.

4. The frontend does not force the product shape.
   - Because setup, onboarding, board, download, and admin pages are fragmented, backend pieces can remain fragmented.

5. Browser control is split.
   - Extension/WebVoyager, browser-use, native bridge, onboarding scrape, API hands, and old CDP paths all coexist with different safety semantics.

6. Memory is a ledger, not yet a lifecycle.
   - There is storage and retrieval, but not enough policy for retention, deletion, redaction, source confidence, decay, and user inspection.

7. Proof artifacts leak or overclaim.
   - Receipts often omit whether they used live/mocks, which path was used, what they do not prove, and when they expire.

## External Research Applied

Computer-use systems converge on the same pattern:

- Anthropic computer use documents a sandboxed environment, agent loop, prompt-injection risk, human confirmation for meaningful real-world consequences, and careful handling of sensitive data: https://docs.anthropic.com/en/docs/build-with-claude/computer-use
- OpenAI computer use guidance emphasizes treating on-screen/web/email content as untrusted, confirming at the point of risk, and protecting sensitive data before typing/submitting/sharing: https://developers.openai.com/api/docs/guides/tools-computer-use
- Stagehand/Browserbase splits browser automation into `observe`, `act`, `extract`, and `agent`, which is the right shape for Anticipy: use agentic exploration for unknown pages, but deterministic primitives for critical actions: https://docs.stagehand.dev/v3/first-steps/introduction
- Vercel AI SDK agent docs emphasize reusable tool-loop agents, stop conditions, approval stops, and controlled loops: https://ai-sdk.dev/docs/agents/loop-control
- Vercel Sandbox docs emphasize isolated execution, snapshots/persistence, and egress controls for agent workloads: https://vercel.com/docs/sandbox
- Browser-use and Vercel agent-browser show the useful runtime pattern: real browser harness, persistent session, compact observations, refs, recovery loops, and explicit command history: https://github.com/browser-use/browser-use and https://github.com/vercel-labs/agent-browser
- Manus context-engineering guidance and browser-agent practice point toward persistent task state, compressed history, file-backed memory, and resume discipline instead of relying on raw long context: https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus
- NIST Privacy Framework frames privacy as lifecycle risk management: identify, govern, control, communicate, protect: https://www.nist.gov/privacy-framework
- FTC business privacy guidance says sensitive data should be kept only as long as there is a business reason and disposed of securely afterward: https://www.ftc.gov/business-guidance/resources/protecting-personal-information-guide-business
- OWASP LLM guidance treats prompt injection and sensitive information disclosure as application-level risks, not just prompt-writing problems: https://genai.owasp.org/llmrisk/llm01-prompt-injection/

Implication for Anticipy: do not clone a browser agent wholesale and hope it becomes Donna. Keep the extension/browser runtime, but refactor around a single state machine with explicit observe/read/prepare/confirm/execute/prove/remember steps, final executor safety, and durable evidence.

## Current Completion Estimate

These are product-real estimates, not code-volume estimates:

- Clean consumer UI and canonical flow: 25-35%
- Static/Next frontend pieces combined: 50-60%
- Proactive brain/control skeleton: 60-70%
- Proactive product loop over real days: 25-35%
- Browser hand local extension plumbing: 45-55%
- Browser hand horizontal/reliable/safe product runtime: 20-30%
- Memory capture/retrieval primitives: 40-50%
- Memory/context lifecycle/privacy/retention: 15-25%
- Audio upload/transcription/input plumbing: 30-40%
- Voice/SMS outbound: 50-60%
- Voice/SMS two-way product channel: 20-30%
- Per-user hosted setup/device identity: 20-30%
- Evidence integrity: 25-35%

The "proactive system should be about 90 done" can be true only if it means internal triage/control primitives. It is not 90% done as a clean, hosted, multi-day consumer product.

## Audit Artifacts

Read in this order:

1. `AUDIT.md` - this file.
2. `STAGE_MATRIX.md` - per-stage current state and gaps.
3. `BABY_STEPS_PLAN.md` - practical sequence to cross off.
4. `CONTEXT_MANAGEMENT.md` - how future agents should resume without losing the system.
5. `EVIDENCE_LEDGER.md` - replacement for "Gate N green" proof language.

