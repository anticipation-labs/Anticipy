# Stage Matrix

This matrix uses the source-of-truth definition of done: a normal user can open hosted Anticipy, sign in, onboard, install/pair the browser helper, talk/upload/listen, watch the assistant work, approve risky steps, see memory/tasks, and have it follow through over days.

Verdicts:
- `LIVE_PRODUCT_PROVEN`: real product UI path, durable result, independent readback.
- `LIVE_ARM_PROVEN`: real external arm works, but not necessarily through product path.
- `INTEGRATION_PROVEN`: route/component works with controlled or mock assumptions.
- `CODE_ONLY`: implementation exists, not proven.
- `BLOCKED`: exact blocker remains.
- `RETIRED`: old or misleading proof.

## 0. Source Of Truth And Operating Context

Where we are:
- The pasted source document is the strongest source of truth.
- Several repo docs also claim source-of-truth status and conflict with each other.

What exists:
- `ANTICIPY_SOURCE_OF_TRUTH.md`
- `CURRENT_STATE.md`
- `SOURCE_OF_TRUTH.md`
- `WAKEUP_REPORT.md`
- `docs/agent_os/CURRENT_TRUTH.md`
- `docs/agent_os/RECEIPTS.md`
- old gate/cert docs

Separate or not wired:
- No single current evidence ledger governs claims.
- Old docs can still mislead future agents.

Isolation/demo:
- Gate/guarantee language often cites narrower harnesses as finish-line proof.

How it works:
- Future work currently depends on whoever reads the right doc.

Verdict:
- `BLOCKED` for evidence integrity until one live truth and one ledger replace gate language.

Baby step:
- Keep `ANTICIPY_SOURCE_OF_TRUTH.md` as canonical product truth.
- Mark older state docs as dated history unless they are raw receipts.

## 1. Front Door, Auth, And Signup

Where we are:
- There are several entry points, not one obvious hosted consumer path.

What exists:
- `web/index.html`: polished marketing page, canned demo.
- `web/auth.js`: Supabase auth with localhost bypass.
- `app/welcome/page.js`: guided first-run flow.
- `app/layout.js`: top nav to app/connect/download.
- `app/api/_engine.js`: local-open / token-gated proxy behavior.

Separate or not wired:
- Static auth and Next owner-token auth are different systems.
- Hosted path vs local engine path is unclear.
- Consumer auth is not clearly tied to extension pairing and per-user engine state.

Isolation/demo:
- Marketing request-access form is local/canned.

How it works:
- Static pages can use Supabase browser auth.
- Next APIs use owner token/cookie/local request checks.
- Local development often bypasses auth.

Verdict:
- `INTEGRATION_PROVEN`, not `LIVE_PRODUCT_PROVEN`.

Baby step:
- Pick one canonical front door.
- Hide provider/local terminology.
- Bind auth user -> engine user -> device/extension session.

## 2. Download And Browser Helper Setup

Where we are:
- The loaded Desktop extension matches repo extension right now.
- Public zip is stale and incomplete.
- Consumer download/setup is developer-shaped.

What exists:
- `extension/*`: current browser helper source.
- `/Users/omarebrahim/Desktop/0-ANTICIPY-EXTENSION-LOAD-ME`: loaded copy.
- `public/anticipy-chrome-extension.zip`: stale.
- `app/download/page.js`: download page with developer quickstart and placeholder repo.
- `app/api/download/*`: mac/download helper routes.

Separate or not wired:
- Repo extension and loaded copy can drift.
- Manifest host coverage does not cover all production domains.
- Pairing/heartbeat exists but extension WS still mostly binds through default local token/core flow.

Isolation/demo:
- Developer mode extension load is a local setup pattern, not five-year-old-proof.

How it works:
- Extension stores engine URL.
- It requests `/ws/token` and opens `/ws/extension`.
- It can observe/act/discover/deep-scrape.

Verdict:
- `LIVE_ARM_PROVEN` for current local connection.
- `BLOCKED` for hosted consumer setup.

Baby step:
- Regenerate zip from current source.
- Remove Desktop-copy drift.
- Make extension pairing user/device-aware.
- Replace public download copy with one action and human status messages.

## 3. Onboarding

Where we are:
- Product-shaped onboarding shell exists.
- Source-of-truth onboarding does not exist end to end.

What exists:
- `web/onboard.html/js`: four-screen wizard, layer cards, dossier confirm.
- `app/welcome/page.js`: simpler guided flow.
- `app/onboarding/page.js`: technical local setup/status page.
- Engine routes: `/onboard/permissions`, `/onboard/scan`, `/onboard/discover`, `/onboard/deep-scrape`, `/onboard/deep-read-hand`, `/onboard/loop`, `/onboard/status`, `/onboard/complete`.
- Extension discover/deep-scrape routines.

Separate or not wired:
- No scrape -> Call 1 -> deeper scrape -> Call 2 -> optional Layer 3 -> final contract state machine.
- Call brain exists separately from the browser scrape loop.
- Onboarding complete can be true without proving the layered product flow.

Isolation/demo:
- Current "layers" are scrape layers, not call-guided adaptive investigation.
- Some copy mentions later calls, but not real call flow.

How it works:
- UI calls scan/loop.
- Extension can open service pages and collect login signals/metadata.
- Engine synthesizes onboarding profile-like state.

Verdict:
- `INTEGRATION_PROVEN` for scan/loop shell.
- `CODE_ONLY` or `BLOCKED` for source-of-truth onboarding.

Baby step:
- Implement UI state machine first:
  signed out -> helper ready -> permission/sign-in -> Layer 1 -> Call 1 -> Layer 2 -> Call 2 -> optional Layer 3 -> final confirm -> Board.
- Stub call states visually before adding more backend.

## 4. Main Board / Task Surface

Where we are:
- Two boards exist: static board is cleaner, Next board is more operational.

What exists:
- `web/app.html/js/css`: clean board with text/mic/card deck/autonomy dial.
- `app/page.js`: Next owner board with typed/paste/upload, memory, open loops, pending asks, settings.
- Engine `/owner/cards`, `/owner/autonomy_mode`, `/owner/ingest`, `/resolve`.

Separate or not wired:
- Static board and Next board are separate product choices.
- Some UI states can show done/proof even when proof is narrow or demo-shaped.
- MP3 upload exists through Next API, not clearly in static board.

Isolation/demo:
- Landing page demo cards are canned.

How it works:
- Board fetches cards.
- User submits transcript/input.
- Cards show ask/do/remember/blocked states.
- User can approve/deny pending asks.

Verdict:
- `INTEGRATION_PROVEN`.

Baby step:
- Pick one board.
- Make it the only post-onboarding destination.
- Require every card to show: what Anticipy heard, what it will do, whether it needs approval, live proof status, and next wake-up.

## 5. Input: Text, Upload, Mic, Ambient Listen

Where we are:
- Text and file input routes exist.
- Static mic uses browser Web Speech.
- Engine audio/Deepgram routes exist.
- Ambient "listen all day" product is not proven.

What exists:
- `/owner/ingest`
- `/owner/ingest-file`
- `/listen/start`
- `/listen/stop`
- `/listen/status`
- `/listen/stream`
- `app/api/owner/upload`
- `app/api/listen/stream`
- Web Speech in `web/app.js`

Separate or not wired:
- Static mic and engine live transcription are not one product path.
- MP3 upload is not consistently exposed in the cleanest UI.
- Voice transcripts can enter, but the full owner-call loop is not productized.

Isolation/demo:
- Some audio paths are local/dev.

How it works:
- Text/file becomes transcript input to `ControlCore.owner_ingest()`.
- Stream endpoint can send audio to Deepgram when configured.

Verdict:
- `INTEGRATION_PROVEN` for typed/upload.
- `CODE_ONLY` for ambient listen.

Baby step:
- Put "Listen" and "Upload MP3" on the canonical board.
- Route both to the same ingest event schema.
- Label transcript source and confidence.

## 6. Brain / Proactive Engine

Where we are:
- Serious control skeleton exists.
- Product-real proactive autonomy is not fully proven.

What exists:
- `ControlCore.owner_ingest()`
- deterministic task extraction and guards
- `core/proactive.py`
- `proactive/harm.py`
- `proactive/autonomy_mode.py`
- `proactive/follow_up.py`
- scorecard/trust/pending asks
- `/trigger/tick`

Separate or not wired:
- Active proactive engine is `core/proactive.py`; `proactive/engine.py` is a stub.
- Autonomy classification exists in more than one layer.
- Follow-through can schedule, but multi-day owner operation is not proven.

Isolation/demo:
- Test suites often use stub model/mock hands/mock channels.

How it works:
- Ingested event is triaged.
- Memory context is read.
- Harm/safety wall decides ask/hold/suppress/act.
- Orchestrator starts goals or creates asks.
- Follow-up watcher can wake later.

Verdict:
- `INTEGRATION_PROVEN` and some `DETERMINISTIC_CONTRACT`.
- Not `LIVE_PRODUCT_PROVEN`.

Baby step:
- Build one full controlled product scenario through UI:
  input -> task card -> approval -> browser work -> proof -> follow-up -> memory readback.

## 7. Memory And Context Management

Where we are:
- Local memory primitives exist.
- Context lifecycle, privacy, retention, redaction, and user-facing memory controls are underbuilt.

What exists:
- SQLite memory store.
- Drawers: profile, open loops, history, derived.
- Live memory capture/infer/maintain/selfcheck.
- Board memory/open-loop views in Next app.
- Local `.anticipy-data` owner card records.

Separate or not wired:
- Onboarding, browser, voice, and proactive memory are not yet one clearly governed memory OS.
- No full retention/archive/delete/cache policy.
- Receipt proof can include sensitive browser data.

Isolation/demo:
- Memory tests prove classification/write behavior, not long-term personal context quality.

How it works:
- Events and tasks are captured into drawers.
- Similarity scan and readback support cards.
- Open loops can become reminders/follow-ups.

Verdict:
- `INTEGRATION_PROVEN` for local memory primitives.
- `BLOCKED` for privacy-grade life recorder.

Baby step:
- Define memory classes:
  raw transcript, extracted task, person profile, system map, open loop, sensitive artifact, receipt, expired cache.
- Add retention/default redaction before scaling capture.

## 8. Browser Hand / Action Runtime

Where we are:
- Local extension path is real and connected.
- Browser system is still split and needs rehaul.

What exists:
- Extension WS `/ws/extension`.
- `BrowserLink`.
- `WebVoyagerAgent`.
- `/ws/browse`, `/ws/observe`, `/ws/act`.
- `/agent/run`, `/agent/resume`.
- `/agent/act` browser-use path.
- Native bridge and browser-use fallback paths.

Separate or not wired:
- Owner-card action path and `/api/browser/run` use different runtimes.
- Onboarding scrape path is separate from task-action browser path.
- Extension executor lacks final pay/send/credential hard stops.
- WS extension does not reliably bind to signed-in user/device identity.

Isolation/demo:
- Amazon return recipe.
- Throwaway browser-use.
- Fake extension tests.
- Public/demo ecommerce receipts.

How it works:
- Engine asks browser to observe.
- Extension returns elements/text/screenshot.
- Agent plans action.
- Extension clicks/types/navigates.
- Result is persisted to card proof.

Verdict:
- `LIVE_ARM_PROVEN` for local connected Chrome.
- `BLOCKED` for horizontal safe product runtime.

Baby step:
- Make extension runtime canonical.
- Route all product browser tasks through one state machine.
- Move irreversible safety into extension executor.
- Retire browser-use as product proof.

## 9. Voice, SMS, Calls, And Check-Ins

Where we are:
- Outbound Twilio can be live.
- Inbound reply polling was disabled in live status.
- Product check-in loop is incomplete.

What exists:
- `channels/text.py`
- `channels/call.py`
- `channels/inbound.py`
- `/voice`
- `/cr`
- pending asks and resolve path
- Twilio readiness status

Separate or not wired:
- Onboarding calls are not the orchestrating control plane.
- Inbound SMS/call replies are not clearly always tied to pending asks.
- The user-visible settings/call flow is not five-year-old-proof.

Isolation/demo:
- Voice/text receipts prove outbound delivery more than two-way product behavior.

How it works:
- ControlCore can send text/call through Twilio env.
- Pending asks can be resolved by route/SMS-like paths.
- `/cr` is a call relay route.

Verdict:
- `LIVE_ARM_PROVEN` for outbound.
- `BLOCKED` for two-way product check-ins.

Baby step:
- Turn inbound reply path on in a controlled way.
- Use calls/texts in onboarding state machine first.

## 10. Connections, APIs, And Per-User Hosted System

Where we are:
- Local engine has more hands than cloud.
- API hands exist but conflict with browser-first direction.
- Per-user hosted path is not finished.

What exists:
- Supabase auth helpers.
- Owner token gate.
- Token vault / Arcade / API hand.
- Google/Arcade readiness.
- local engine plus Railway references.

Separate or not wired:
- Cloud has no browser hand equivalent.
- Extension pairing does not yet define one hosted per-user control plane.
- API/OAuth remains exposed in UI and engine despite source-of-truth browser-only action direction.

Isolation/demo:
- API Calendar proof is real but not proof of browser-only product.

How it works:
- App proxies local/cloud engine.
- API hand can use Arcade when funded/configured.
- Extension drives local browser.

Verdict:
- `INTEGRATION_PROVEN` for local/single owner.
- `BLOCKED` for hosted normal-user product.

Baby step:
- Decide: browser-first for user tasks, APIs only as internal optional accelerators with explicit labeling.
- Bind cloud app user to local extension/device tunnel or a secure browser runtime.

## 11. Follow-Through And Multi-Day Autonomy

Where we are:
- Follow-up scheduling exists.
- Multi-day owner outcome is not proven.

What exists:
- follow-up planner.
- trigger watcher.
- open loops.
- `/trigger/tick`.
- proactive loop armed every 30s in live status.

Separate or not wired:
- The system can wake, but "wake up three days later and finish the real thing" is not proven.
- Follow-ups and browser tasks are not yet one durable task state machine.

Isolation/demo:
- Tick receipts that fire nothing prove no crash, not product follow-through.

How it works:
- Cards/open loops can schedule reminders.
- Ticks scan due items and send/check/react.

Verdict:
- `INTEGRATION_PROVEN`.
- Not `LIVE_PRODUCT_PROVEN`.

Baby step:
- Add one end-to-end acceptance task with a real delayed wake-up and independent readback.

## 12. Evidence, Tests, And Receipts

Where we are:
- Many tests exist.
- Evidence language overstates readiness.

What exists:
- deterministic safety evals.
- browser safety loops.
- API live proofs.
- Twilio proofs.
- owner runner.
- overnight harness.
- guarantee/gate docs.

Separate or not wired:
- No capability ledger with verdict/expiry/what-it-does-not-prove.
- Raw receipts are mixed with summaries and claims.

Isolation/demo:
- Mock/stub test suite.
- Browser-use public site demos.
- self-referential guarantee certificates.

How it works:
- Test scripts write receipts/docs, but claims are not normalized.

Verdict:
- `DETERMINISTIC_CONTRACT` in many places.
- `BLOCKED` for product proof discipline.

Baby step:
- Replace gate language with `EVIDENCE_LEDGER.md`.
- A proof must say path, mode, user involvement, durable artifact, independent readback, and limits.

