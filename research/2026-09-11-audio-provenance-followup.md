# Legacy speech provenance follow-up — September 11, 2026

## Outcome and scope

**There is no justified text-only patch that resolves the demonstrated residual
while preserving the existing no-replay contract.** The recognizer adapter
currently discards potentially useful audio timing, but Apple's public API does
not document a stable decoder-window ID or stable identity for each partial
segment. Treating a changed timestamp as proof of new speech would therefore
introduce an unverified assumption, not finish the repair.

This follow-up inspected the frozen candidate-175 cursor, legacy and Analyzer
callbacks, unchanged fuzzer, installed Apple SDK 26.5 headers, and primary Apple
documentation. It used `ecc:ai-regression-testing` to construct a small
actual-production-cursor counterexample rather than soften the failing oracle.
Root's instructions prohibited iOS product edits in this pass; none were made.
No microphone, real audio, device, credential, provider/model call, live API,
Git mutation, or deployment was used. Only public Apple documentation was
requested online. The frozen pending-provenance repair remains intact.

## What the current adapter actually knows

| Boundary/data | Current implementation | What it proves |
| --- | --- | --- |
| Request identity | `PhoneListener.swift:1175–1180`, closure captures `req` and requires `self.request === req` | A late callback from a superseded task cannot mutate the current cursor. It does not identify internal decoder windows within one task. |
| Legacy recognition callback | `PhoneListener.swift:1183–1185` forwards only `bestTranscription.formattedString` and `isFinal` | Segments and their audio positions never reach the cursor. |
| Text-only cursor | `TranscriptCursor.swift:243`, `PhoneListener.swift:1381` | `observe(_ text: String)` cannot distinguish different histories with the same sequence of strings. |
| Explicit request swap | `PhoneListener.swift:1151` resets the cursor; orphan audio may replay | The app knows a request boundary, but it is not a proof that replayed audio is new speech. |
| Analyzer settled phrase | `PhoneListener.swift:1477–1488` flushes and resets on engine finality | Repeated final phrases have a real phrase boundary already; the legacy residual is not a reason to remove this repair. |
| Capture envelope | `CaptureEnvelope.swift:38–50` uses callback arrival / flush dates | These are not audio sample offsets and must not be repurposed as segment identity. |

The final-row equality observed in earlier phone metadata cannot establish
sample timing or word identity. This pass did not read or re-query those rows.

## What Apple documents, and what it does not

`SFTranscriptionSegment` supplies the recognized substring, its range in the
formatted string, confidence, alternatives, timestamp and duration. A segment
may represent more than one word; a whitespace word is not necessarily one
Apple segment. Array order follows spoken order. The installed SDK declares
no segment identifier or decoder-window identifier. See Apple's
[segment reference](https://developer.apple.com/documentation/speech/sftranscriptionsegment)
and installed `Speech.framework/Versions/A/Headers/SFTranscriptionSegment.h`.

The segment timestamp is measured from the start of the supplied audio content,
not the wall clock or callback time. Duration measures the segment's speech
span. Different **trusted** audio spans could distinguish a new occurrence from
a revision, but these values alone are not a documented immutable partial-result
ID. Do not infer that zero is invalid (speech can start at zero), that confidence
is an identity flag, or that an object pointer persists across result snapshots.
[Apple timestamp documentation](https://developer.apple.com/documentation/speech/sftranscriptionsegment/timestamp).

Apple explicitly guarantees that a final transcription does not change.
Its result documentation permits partial results to represent only part of the
audio. The examined contract provides no equivalent stability guarantee for
partial text, ranges or timing across revisions. This is a statement about the
documented contract, **not a claim that timestamps are always wrong on a device**.
[Apple result documentation](https://developer.apple.com/documentation/speech/sfspeechrecognitionresult),
[finality documentation](https://developer.apple.com/documentation/speech/sfspeechrecognitionresult/isfinal).

The task-delegate API provides an actual final-utterance notification,
`speechRecognitionTask(_:didFinishRecognition:)`, after which the delegate
should receive no more information for that utterance. It is a promising
explicit boundary for a final-result adapter, not proof that the current
result-handler API supplies a decoder-window ID. The separate
`didProcessAudioDuration` callback reports processed audio duration, not an
utterance identity. Final-utterance cadence and latency in continuous on-device
recognition remain untested here.
[Apple delegate documentation](https://developer.apple.com/documentation/speech/sfspeechrecognitiontaskdelegate/speechrecognitiontask%28_%3Adidfinishrecognition%3A%29).

## Minimal paired-history counterexample

Both histories expose these exact calls, including the same pause and finality:

```text
we                             [pause/flush]
we
we garage
we garage that
we garage that me
kind we garage that me          [final]
```

The actual frozen cursor outputs `we garage that me` in both cases.

- **History A — one window:** the recognizer inserts `kind` in front of the
  already-published `we`. The existing front-insertion/no-replay contract
  absorbs that revision instead of sending a one-word correction or replaying
  already-delivered speech. The actual output satisfies that contract.
- **History B — a hidden new window starts on the second `we`:** the committed
  source history is `we | kind we garage that me`. The second `we` can consume
  the fuzzer's one shared-prefix allowance, but `kind` is still missing. The
  observable input never told the cursor that the second callback began a new
  window; no algorithm operating on that input can satisfy both histories.

This does not prove every remaining fuzz red is an oracle error. It proves a
specific interface ambiguity also present in a printed seed-42 residual. The
unchanged fuzzer stores `Step.windowStart` (`TranscriptCursorFuzz.swift:439–441`)
but passes only text to the emitter (`:631`). It resets the oracle's
per-window committed-position baseline at that hidden flag (`:652–655`), while
shared-prefix allowance is computed separately (`:580–586`). Thus the oracle
can know an occurrence boundary the implementation was never given.

Changing that accounting, adding a word allowance, or injecting the hidden
window flag only into a test implementation would not prove the phone fixed.
The original seed-1234, 9001 and 42 fuzz results remain **RED**, as recorded in
`research/2026-09-11-audio-cursor-repair.md`.

## Smallest defensible next contract

The first change should be to the **recognizer-to-emitter observation contract**,
not another tolerance in sent-word alignment. A proposed observation includes:

```text
capture generation + request identity
callback sequence / documented final-utterance boundary
formatted text + segment character ranges
request-relative audio spans, explicitly provisional until final
request-to-capture audio-frame mapping, including orphan replay
```

Requirements before such data is allowed to discard or commit speech:

1. Keep capture/account identity fences. A new request does not imply new audio;
   map actual input frames so orphan replay is not silently double-counted.
2. Preserve partial text as a provisional preview. Do not assign stable token
   identity from timestamp equality, confidence, string similarity, or a
   minimum-gap guess. Missing, nonfinite, overlapping, moved or partial spans
   cannot authorize deleting a previously pending occurrence.
3. Use a documented final utterance/region as the publish-once boundary. Final
   text must reconcile with what was already emitted, or remain uncommitted
   until finalized; append-only output cannot retroactively insert words in
   front of a published span without a correction/revision protocol.
4. Preserve bounded Stop/finalization and privacy discard. The current legacy
   stop clears request identity immediately after `task.finish()`; changing
   legacy publication to final-only also requires a bounded, owner-fenced
   legacy drain. Reusing the Analyzer's finalization principle is appropriate;
   merely waiting forever for `isFinal` is not.
5. Make latency explicit. Current gap/ceiling policy publishes after a pause or
   eight seconds of waiting; waiting only for a long recognition task's final
   result changes that behavior. A bounded request-finalization/next-request
   handoff or a revision-aware downstream receipt design is a larger change
   that needs its own baseline, regression tests and physical timing checks.

Recommendation: retain the narrowly proven repair and keep the residual red.
Prototype the observation/finality adapter and a real on-device segment-timing
trace before selecting a new commit/discard policy. A two-line timestamp reset
is not supportable from the current evidence. No product implementation of
this proposed contract was attempted or represented as complete here.

## New offline evidence

Only two ignored investigation fixtures were added:

- `work/ben-audio-provenance-twins-20260911.swift`: compiles beside the actual
  frozen cursor; equal-observation and same-window assertions pass while it
  explicitly reports the hidden-window contract unresolved. Executable exit
  **0** proves the ambiguity fixture, not the product fuzz gate.
- `work/ben-audio-metadata-typecheck-20260911.swift`: accesses the actual Apple
  request/result/segment types, request identity, segment range/timestamp/
  duration and optional speech-start metadata. **Typecheck exit 0**. It never
  instantiates a recognizer or invokes a callback and proves no timing accuracy.

Commands from the product root, with no dotenv loading or network access:

```sh
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk \
PYTHON_DOTENV_DISABLED=1 \
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network-outbound)' \
swiftc -O -parse-as-library app/ios/Anticipy/Audio/TranscriptCursor.swift \
  work/ben-audio-provenance-twins-20260911.swift \
  -o work/ben-audio-provenance-twins-20260911

/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network-outbound)' \
  work/ben-audio-provenance-twins-20260911

SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk \
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network-outbound)' \
swiftc -typecheck -swift-version 5 -target arm64-apple-macos26.0 \
  work/ben-audio-metadata-typecheck-20260911.swift
```

The twin executable was rerun as a standalone command and returned actual
exit 0. Its first output is retained in
`work/ben-audio-provenance-twins-20260911.log`. No broad fuzz rerun was needed
because no product source or oracle changed in this pass. A fresh full iOS
baseline must precede any future product edits.

Rechecked SHA-256 identities:

```text
c0c4a64c54397cb971746fcee9a6e2a9ac760f5aac618f37cb24f0a953d2bf7c  app/ios/Anticipy/Audio/TranscriptCursor.swift
b2dd23d3bd8c6e0f7ed4295637eb6d111e453f1f03f4b6c39ce9621ea91d16b6  app/ios/Tests/TranscriptCursorTests.swift
5a94f21eb62ba11ec8e96ba949312429e59e0225416e8aa8ebae563dbc70587b  app/ios/Tests/TranscriptCursorFuzz.swift
a920f944b690ef8972230d5129e649d6e5775063e1894b6b17be6974666410a7  app/ios/Tests/run_cursor_tests.sh
ff30561ce66d444f63d16e1dbcc3f208383bf430d99d21c64a4f4815833c7ab4  work/ben-audio-provenance-twins-20260911.swift
0b95a21ef8752cf336fd78346014203093ceb4335502ce90dd73d9c14988a514  work/ben-audio-metadata-typecheck-20260911.swift
```
