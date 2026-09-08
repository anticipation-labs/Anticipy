# iOS actual-screen recovery and durable input — local evidence

Working tree: `cloudflare-backend`, 2026-09-08. No live accounts, network writes, commits, pushes, signing, or deployments were used in this work. The parent completed the mandatory pre-edit iOS suite before authorizing changes.

## Reproduced before changing behavior

- Actual Home rendered `.working` as prose and `.question` as prose. The existing `HandlingCard` Stop/Check stop and `AskCard` answer/reconciliation controls had no constructors. Ten new actual-caller assertions failed on the pre-fix source.
- The real `heard` function, extracted into a delayed in-memory transport harness, failed 13 ownership checks: successful old-owner completions could install a parent ID in the replacement session; failed completions could stamp old speech with the replacement account; signed-out callbacks could publish local echoes before the guard.
- Source tracing found the actual composer cleared before scheduling asynchronous `heard`, which attempted the first POST before persistence and had no stable external event ID. This specific crash/response-loss path was source-proven, not reproduced on a physical phone.
- Current source Settings did not expose `ContextGrants.reopen`; only dead legacy SettingsView did. The actual Home's `mayAsk` filter therefore kept a previously declined source unavailable.

## Changes in the actual path

1. `Views/ContentView.swift:1319` injects existing `HandlingCard` and `AskCard` into `ConversationDashboard`; the capture detail uses the same renderer as the thread. Actual job/event identity selects the controls. A transcript goal without a job stays prose, and historical closed questions do not become new answer requests. Existing reconciliation and consent methods remain the only write path.
2. `Views/SettingsAccessView.swift:166` exposes “Allow Anticipy to ask again.” This only clears the local decline; it never grants access, invokes an OS prompt, or reads facts.
3. `AnticipyApp.swift:1009,1024` captures the exact owner/token at both microphone callback boundaries and verifies it before the scheduled Task calls `heard`. `SpeakerTagger` already invalidates pending embedding deliveries on account changes; the callback fence covers the additional Task-scheduling gap.
4. `AnticipyApp.swift:1108–1158` synchronously stages a message before local acceptance. Each row includes original owner, text, source, capture start/end, continuation relationship and a stable UUID-based external ID. `acceptTyped` returns true only after the atomic write succeeds. The real composer clears after this synchronous result; two immediate taps cannot schedule the same draft twice, and network completion has no reference to a newer draft.
5. `CaptureOutboxPersistence` plus `readPendingLines`/`persistPendingLines` use atomic file replacement in the app's Application Support directory. iOS uses complete-until-first-authentication file protection. The previous UserDefaults queue migrates only after a successful file write. An unreadable or corrupt file is not an empty queue: staging and owner-scoped deletion throw/fail closed without overwriting it. Explicit whole-device Forget can erase the entire pending file, and failures are surfaced rather than claiming erasure.
6. `flushUnsent` is serialized and captures one authenticated backend/lease. An owned legacy row gets an external ID persisted before first retry. Before POST and after an uncertain response it reads the exact owner/kind/external identity. Every POST carries the same persisted ID, backed by `migration/d1/schema.sql:246`'s unique nonempty external-event index. A confirmed row is removed by that owned ID from a freshly read queue, never by matching text or a stale array index. Other-owner and unattributed rows stay sealed.
7. `Backend/AnticipyBackend.swift:976 transcriptEventID` validates decoded owner, transcript kind, exact external ID, single-row count, and a nonempty canonical row ID. Only a verified empty page means absent; malformed/foreign responses throw. Canonical row IDs preserve parent references after response loss.
8. Pending-message copy no longer claims queued words definitely never reached the server: response-loss rows may already be accepted. API task copy and recovery filtering use the structural API lane rather than telling connected-app work to open Chrome.

## Local verification

`sh app/ios/Tests/run_capture_account_race_tests.sh`: **101 passing checks** at this checkpoint.

The runner compiles extracted production `heard`, `acceptTyped`, `stageTranscript`, `flushUnsent`, composer `send`, exact backend reader, file helper and BufferedLine declaration. Transport/observable UI scaffolding is in-memory. A separate disk harness extracts production `readPendingLines`, `persistPendingLines`, ownership filtering and scoped/device clear implementations; only the filesystem location is redirected to a temporary directory. No app Application Support data is accessed by tests.

Cases include:

- Typed and phone-mic success/failure during sign-out, account switch and same-owner token replacement.
- Queue exists with stable owner/ID before POST; stale completion neither relabels it nor mutates the replacement session's parent pointer.
- Signed-out callbacks neither echo nor post.
- Read/write failure prevents typed acceptance and false echo; no POST is scheduled.
- Lost POST response and lost readback, codec round-trip representing relaunch, then canonical recovery without a second POST.
- Legacy optional-field decode and persisted ID before retry.
- Two synchronous composer taps, exact draft preservation on failed enqueue, newer draft survives late completion.
- Exact readback rejects foreign owner, wrong kind, wrong external ID, empty/missing row ID, duplicate rows and malformed JSON.
- Atomic file independent reopen; failed replacement preserves the legacy fallback.
- Real owner-scoped clear preserves foreign/unattributed rows and corrupt file bytes; only explicit whole-device Forget replaces corrupt storage.

`sh app/ios/Tests/run_actual_home_recovery_tests.sh`: **13 passing source-caller checks**. These prove constructors, shared renderer, API-lane help, environment-object ancestry, synchronous composer acceptance and the current Settings reopen action. They are not rendered UI tests.

`python3 app/ios/Tests/ConsumerExperienceContractTests.py app/ios`: passed after updating stale setter/by-value-delete assertions to the new throwing store/stable-identity path. Ownership, retention, failure reporting and real caller checks were retained, not removed.

`.venv/bin/python -m pytest -q tests/test_signed_out_privacy.py`: **7 passed**. Tests now follow the real staging guard and captured delivery lease, not the removed literal guard in the old live-POST function.

`swiftc -frontend -parse` over the six changed app-source files and `git diff --check`: passed.

`sh app/ios/Tests/run_all.sh`: **exit 0**, “iOS logic gate: all suites passed,” on the root-coordinated build-172 working tree. Existing source contracts were updated to follow the new store and exact-ID path, with ownership, corruption refusal, retention and erase-failure coverage retained. This gate explicitly reports that no iOS SDK is available; it is not a full SwiftUI build.

Independent review by `browser_handoff` accepted the local patch after rerunning the 101 capture/outbox checks, 13 actual Home checks, 7 signed-out privacy tests and ConsumerExperienceContract. No further source objection was found; installed-device and live-journey limitations remain.

### Final pre-tagging account-boundary regression

The root requested a concrete check of a still-earlier interval: A's audio is already waiting for asynchronous voice embedding, but `onSpeaker` has not yet invoked the session callback when B signs in.

No new application defect reproduced. Existing `Audio/SpeakerTagger.swift:117–133` snapshots `deliveryGeneration` **before** dispatching embedding, then checks it on the main queue **before** either nil-tag completion or roster identification. `clearSignedInSurface` invalidates this generation for sign-out/expiry. This precedes the new exact-owner callback-Task fence; the two protect different intervals.

`SpeakerWorkTests.swift` now uses a semaphore-controlled embedder with the real production SpeakerTagger. It proves A's embedding actually began, performs account invalidation and B sign-in, then releases A. Both valid-embedding and nil-embedding branches deliver only B's words. A separate normal-Stop case keeps the account unchanged, queues the final tail behind a blocked earlier utterance, and proves both arrive in order. The runner pins actual `PhoneListener.deliver → tagForLatestUtterance → onSpeaker`, account-clear invalidation, callback-before-Task lease capture and ordinary Stop's tail delivery with **no** blanket invalidation.

The first run used the runner's pre-existing `swiftc -O`, which strips Swift `assert` and even the semaphore wait inside an assertion. That first success report did **not** establish the claimed runtime invariants. Final review caught this; the runner now explicitly uses `-Onone` so assertions and handshakes execute.

Corrected evidence: `sh app/ios/Tests/run_speaker_work_tests.sh --check-mutation` **exited 0** with active assertions (existing ordered/responsive checks plus four new pre-tag/Stop/source-wiring checks). Its negative control compiles a generated temporary copy with the generation guard removed and requires the exact account-ownership assertion to fail. That mutant failed as required; repository application source was never changed. `run_capture_account_race_tests.sh` uses no optimizing flag and explicit check counters/nonzero exits, not stripped assertions; all 101 checks passed again.

Only tests changed for this final audit; normal Stop behavior was not altered. This remains a real-tagger/local-buffer regression plus source wiring, not physical microphone or installed-iOS evidence.

## What remains unproven / unchanged

- No iOS SDK is installed here. SwiftUI type-check/build, actual screen rendering, iOS file-protection behavior, TestFlight installation, speech/audio permissions, lock-screen/background behavior, and external browser/calendar/vendor results are not verified by these checks.
- Existing legacy rows which may already have reached the server without an external ID cannot be retrospectively deduplicated. Newly assigned IDs protect future attempts only.
- The existing retention policy still keeps the newest 2,000 rows and journals overflow. It is not unlimited memory retention or a guarantee against data loss in arbitrarily long outages.
- An atomic write returning successfully establishes recoverable local storage under the filesystem API; no power-loss/hardware-fault guarantee was tested. A platform filesystem failure leaves the draft, stops unstorable speech capture, and requires storage recovery.
- A confirmed external-event row proves input persistence, not that the brain made the correct decision, a hand completed work, or an external effect happened exactly once. Those require downstream receipts and controlled live journeys.
- Whole-device Forget stops future retries but cannot unsend a request already accepted/in flight. Pending deletion copy now says so. A failed scoped erase after a delayed server deletion is reported as partial cleanup; other owners remain untouched.
- Supervised-read fact veto still has its pre-existing fire-and-forget failure gap. This patch does not make offline memory forgetting reliable.
- Question openness follows the existing Home policy; this work does not introduce a new semantic question/task classifier or solve arbitrary old unanswered-question history.

Release still requires signed-build and controlled installed-device verification. The replacement exemplars remain inspiration for real journeys, never literal meaning rules or evidence that those journeys shipped.
