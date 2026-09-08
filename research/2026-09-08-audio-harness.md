# Audio-to-agent harness verification

## Scope and current verdict

The user asked whether the whole agentic/audio workflow works and requested
that the harness be ensured working. The story is: actual iPhone microphone
input → speech recognition → owner-bound durable capture → API event → brain
with conversation context and memory → permitted executor → verified receipt
and user-visible output. An uploaded app or green unit suite alone is not
this proof. The user has confirmed physical iPhone app version 1.1.1 (172)
and separately reports iOS **26.6.1**. This supports testing the newer analyzer
path (subject to its runtime selection/fallback), not assuming a legacy-only
device. No actual microphone trace from that device is established here.

No whole-harness success is established. Full-story verification stopped at
the first concrete source-level capture defect; no downstream live model,
provider, synthetic-account or shared-runtime probe was run in this pass.

## First broken boundaries: capture lifecycle

1. Build 172's `PhoneListener.start()` requests speech and microphone permissions without
   a start/cancellation identity. `stop()` does not invalidate their pending
   callbacks. A delayed grant can call `begin()` after Stop or account exit;
   a stale denial can also change authorization state after a newer attempt.
2. Build 172's watchdog supplies `task != nil` as recognition presence. The iOS 26
   analyzer path stores an `analyzerEngine`, not a legacy `task`, so a healthy
   analyzer is presented as absent. The 4-second tick chooses startRecognition,
   replacing the analyzer and resetting its transcript cursor/pending state.

These findings are from actual source wiring, not a claimed physical-device
reproduction. The unchanged build-172 full iOS baseline passed again, exit 0
(`work/ios-audio-baseline-2026-09-08.log`), demonstrating a coverage gap.

Repair scope: structural cancellation identity for both permission callbacks,
and actual presence of the selected speech engine for the watchdog. Preserve
normal Stop-tail ordering, account ownership, enrollment silence and honest
failure reporting. Add regressions exercising the real method bodies and
negative controls; do not replace tests with a proxy implementation. Source
build 173 is reserved in both project files; no upload is established here.

### Local repair evidence

The bounded patch now fences both permission completions against the current
start generation, invalidates that generation at Stop even before capture has
begun, and makes repeated Start during an active session a no-op. Permission
completion checks and mutations run on the main queue; existing session/UI
callers are main-actor isolated. The watchdog reads actual selected-engine
presence, not a legacy task pointer or an analyzer-mode flag alone.

The initial lifecycle runner compiles extracted production start/stop/watchdog/
recognizer/swap/enrollment bodies with the real watchdog policy and cursor.
It doubles OS/model/audio edges, begin, absorption, flushing, delivery and
recovery; it does not execute the entire ASR-to-delivery path. The
pre-fix source failed 8 of 22 checks. The repaired source passes 24 checks,
including two additional enrollment cases, plus actual account-exit caller
wiring checks. Removing the permission fences or restoring the legacy-only
watchdog makes the corresponding named behavioral checks fail. These are not
static string checks standing in for execution of the lifecycle bodies.

The full post-patch iOS logic suite passed with external outbound networking
denied, exit 0 (`work/ios-audio-173-full.log`). Full Xcode/iOS SDK compilation
and physical-device capture are separate gates, not established by this run.

### Independent review: further capture repairs required

Adversarial review found no introduced blocker in the permission/watchdog
patch, but identified additional existing failures in the same upstream path:

- Enrollment clears `enrolling` before Stop flushes the cursor, allowing a
  sample to become an ordinary transcript. Ambient enrollment also retains
  the same recognition request/cursor. The initial enrollment checks exercised
  permission cancellation and ambient-state retention, not sample exclusion.
- The analyzer forwards its phrase-level `isFinal` into legacy task-limit
  handling, replacing the recognizer even though the stream can continue.
  This contradicts the existing adapter contract. Apple documents a result
  as a phrase/passage and finalization as an audio-range property, not stream
  termination ([Result](https://developer.apple.com/documentation/speech/speechtranscriber/result),
  [resultsFinalizationTime](https://developer.apple.com/documentation/speech/speechmoduleresult/resultsfinalizationtime)).
- Analyzer failure counters/disabled mode persist across new listening
  sessions despite the claimed session-only fallback.

The local full suite above preceded these findings. The patch is reopened for
structural enrollment isolation, correct analyzer-final adaptation and a true
new-session fallback reset. These changes need expanded actual-body tests and
another full gate; nothing has been uploaded as build 173.

The expanded intermediate version passed 49 actual-body checks, seven named
mutation controls and the full iOS suite (exit 0,
`work/ios-audio-173-expanded-full.log`). Independent review still rejected it:

1. Discarding analyzer finality while retaining a legacy cumulative cursor
   conflated distinct identical phrases. Two finalized "yes please" phrases
   with a gap flush between them produced only one delivered line. Preserve
   the phrase boundary without ending the analyzer request.
2. Fresh enrollment → Stop → new granted Start → old enrollment cleanup left
   the new session in enrollment mode, then stopped it. Stop must retire the
enrollment state after protecting the sample tail, before a new session.

Both were reproduced using the actual extracted bodies, with network denied,
before any commit or release. The intermediate green checks are explicitly not
acceptance of those sequences; regressions and fixes are being added.

The bounded analyzer repair keeps the existing `.transcription` preset. Apple
documents that preset with volatile reporting disabled and ordered phrase
results ([preset configurations](https://developer.apple.com/documentation/speech/speechtranscriber/preset)).
Each finalized phrase must flush and retire its cursor identity, not the
engine; engine-lifetime clocks and failure budget must remain intact. This
does not claim support for arbitrarily overlapping progressive result ranges.
Enrollment retirement belongs at the end of Stop, after its guarded sample
tail handling, so delayed cleanup cannot stop a subsequent ordinary session.

### Final bounded repair and adversarial review

The final source implements both review corrections. Expanded actual-body
tests had 11 failures before these last two repairs; afterward **62 checks
pass**. Ten negative controls each have to fail their named behavioral check:
permission fencing, selected-engine presence, enrollment exit ordering,
enrollment audio exclusion, enrollment request retirement, analyzer-final
task-limit confusion, sticky session fallback, lost phrase cursor reset, lost
speech clock, and stale enrollment state after Stop.

The final runner now executes extracted production begin, absorption,
flush/delivery, silence scheduling and the locked tap-routing block as well as
the original lifecycle methods. OS permissions, engine/model/buffers,
configuration/recovery/observers, speaker embedding and the journal sink remain
controlled doubles. Actual policies and transcript cursor execute. No real
microphone, model, user defaults or customer storage is used.

Independent final review reproduced the previously failing sequences against
the repaired bodies, including three identical finalized phrases queued before
the main queue drains. All three deliver with one analyzer. Its independent
62-check/10-mutation run exited 0 under full network denial. No remaining
blocker was found in the bounded capture repair. This approval explicitly does
not cover the real analyzer engine limitations below or physical capture.

After that final review, the complete iOS logic suite passed again against the
frozen source, exit 0, with external outbound networking denied
(`work/ios-audio-173-reviewed-full.log`). The nine scoped files contain no
recognized credential-like patterns in the targeted scan. The test runner is
registered in `run_all.sh`; no CI upload or production deployment is implied.

The nine-file candidate was committed as
`27c9562180ee79566aca6c8d79229fb37b0f7b7c` and pushed only to
`cloudflare-backend`. The post-commit build-number gate passed: 173 names the
committed iOS source. [Compile-only iOS CI](https://github.com/anticipation-labs/Anticipy/actions/runs/34286751213)
was triggered by that exact push without a ship marker. Its final verdict was
**success**: the complete iOS logic gate and actual Xcode simulator build both
succeeded on `27c95621`. The signing-key, archive, export/upload and Apple
processing steps were all explicitly skipped. This pass did not upload or
distribute build 173; no 173 device installation has been confirmed. The last
confirmed installed app build is 172.

## What the audio input actually means

The phone sends recognized text and capture provenance to Anticipy. The legacy
Apple recognizer requires on-device processing only where it is supported;
the app's permission disclosure explicitly allows Apple-service fallback.
Do not claim raw audio can never leave the device. The iOS 26 analyzer is a
different recognition engine and must be tested as such.

Two additional capture limitations remain: the Stop-tail test covers words
already in the transcript cursor, not words still internal to Apple's model.
The analyzer finalizes asynchronously after Stop, but its cleared identity
means late results are rejected. Also, the analyzer's 600-buffer warm-up hold
silently drops additional buffers; the outer orphan-queue telemetry does not
measure that inner loss. Neither limit is fixed by the bounded lifecycle patch
or proven harmless on a device. A pause before Stop is a controlled test step,
not evidence that immediate Stop preserves every last spoken word.

The real analyzer's asynchronous provisioning is another unresolved seam:
Stop can mark it finished before assets/stream exist; resumed initialization
can still start untracked analyzer/results tasks. The warm-up queue's finished
guard does not guard those tasks. This is a resource/liveness risk; it is not
evidence that the stopped microphone resumed capturing new audio. The fake
engine in the lifecycle tests cannot establish real provisioning cancellation.

The pendant lane is not working capture: `startPendantTranscription()` sets
`pendant.onOpusFrame = nil`; its on-device Opus decoder remains absent. The
generated-Opus/Deepgram proof bypasses that missing app path and must not stand
in for a working pendant.

## Brain and harness limits discovered in source review

- Current tracked brain source hash for candidate `24af7506` is
  `8c77ddcb1d93bfe3e5215ccd45c91362db560c27c444eb3a64f817218a08aa8b`, using
  the runtime's exact algorithm over 39 Python/Markdown files. The actual
  running owner container hash has not been observed. API release identity
  does not establish brain identity, nor does cached supervisor state.
- A narrowly scoped control-plane metadata read on 2026-09-08 found active
  brain deployment `d775ce58-caae-496e-8532-061dbcfc80b5`, created
  `2026-09-08T01:19:37.694204Z`, serving version
  `77a02e72-2625-4876-aec5-a9111a5ee7ff` at 100%. Its validated commit tag is
  `cb2010957877eec0a8c67138b57060dc1bef3110`; declared runtime source hash is
  `8d54551681dcd736b2744de07f5763575812a78f257a8205f5324207e20978d8`.
  That is not the candidate hash above. This proves a control-plane mismatch,
  not the actual running owner's bytes. Only deployments and its referenced
  immutable version metadata were read; no customer data/runtime call occurred.
  Local reconstruction of `cb201095` reproduces that exact declared hash.
  Ten brain files differ from candidate `24af7506`: the candidate includes
  owner-scoped connected-app discovery, delivered-revision SMS approval
  binding/conditional writes, current-sender validation, truthful failed-queue
  acknowledgement, ranked memory recall/deferred consolidation, and refusal to
  boot an empty memory when an existing checkpoint is missing. Those source
  improvements are not established live by the newer API or iPhone release.
- `OwnerBrain.ensure()` is not a health-only operation: it can start or
  replace a runtime. It is excluded from read-only verification. No existing
  API gives a strictly owner-scoped, non-starting runtime-health projection.
- Legacy meaning rules remain in `anticipy_core.py`: correction/new-task/
  replacement/retraction regexes can decide amendment, merge and cancellation
  behavior. This violates the stated harness laws; it is not made compliant
  by being pre-existing. After senses are verified, the proposed direction is
  contextual, independent, four-state model decisions—not additional patterns.
- Brain certification begins with prepared text and a real model but an
  in-memory backend/fake notification. Browser certification can start a real
  extension and model against environment-selected backends. Neither is
  automatically an offline or real-phone proof.
- Existing production E2E scripts inject transcript rows, create accounts or
  cancel work. They are not used for this owner-controlled verification.
- `harness_map_report.py` contains historical hardcoded findings. Its output
  must not be treated as a fresh measurement of this candidate.

## Safe next evidence, after capture repair

Use one deliberate phone-microphone utterance and a narrow UTC window. Inspect
only that owner's new event metadata through the collection LIST endpoint
with explicit `fields`; the individual-record endpoint ignores field projection.
Require `phone_mic`, the confirmed installed build, matching capture timestamps
and an owner-bound external event ID. An old queued upload is not fresh capture.

Pin the exact event ID for processing/decision measurements; follow exact
`jobs.source_event_ids` membership rather than matching time or prose. A quiet
decision can be correct; a missing task alone does not prove a failure. Receipt
content and existing transcript/history are not needed for initial arrival
checks and must not be dumped. No microphone event means capture→upload is
still unresolved, not that the brain is necessarily down.

The shared brain rollout has not been authorized by a specific answer to the
restart-scope question. No runtime restart, main change, production reset,
credential change or unrelated customer-data access is part of this repair.

The normal brain workflow is not a safe owner-only probe: its actual command
uses `--containers-rollout immediate` despite a stale "gradual" comment,
changes the shared expected source, and defaults the owner capacity to one.
Expected-source reconciliation can stop mismatched served containers after
checking recent nonempty snapshots; lowering capacity can stop excluded
owners. A release must preserve verified live operational capacity/settings
and have explicit shared-restart approval. Do not run the default workflow to
turn this report green.
