#!/bin/sh
# Production-body regression probes for analyzer lifecycle boundaries.
# Not a physical-device or live release proof. Exit 1 means behavioral
# failure; exit 2 means the probe could not run. No microphone/model/network.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
python3 - "$here" "$out" <<'PY'
from pathlib import Path
import sys
here, out = map(Path, sys.argv[1:])

def declaration(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == '{': depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0:
                return source[start:index + 1].removeprefix('private ')
    raise AssertionError(signature)

# Reuse the existing controlled OS edges, not a second implementation of the
# listener. The source bodies below are identical to the shipping bodies.
fixtures = (here / 'CaptureLifecycleTests.swift').read_text().split('@main struct CaptureLifecycleTests')[0]
(out / 'ListenerFixtures.swift').write_text(fixtures)
listener = (here / '../Anticipy/Audio/PhoneListener.swift').read_text()
signatures = ['func start()', 'private func begin()', 'private func startWatchdog()',
              'private func startRecognition()', 'private func runAnalyzerRequest(',
              'private func swapRecognition(', 'func stop()',
              'func startForEnrollment()', 'func stopAfterEnrollment()',
              'private func discardEnrollmentRecognition()',
              'private func absorbRecognized(', 'private func flushTail(',
              'private func deliver(', 'private func scheduleSilenceFlush()',
              'private var hasActiveRecognition:']
for signature in ('func stopAfterCurrentAudio(', 'private func stopCapture(',
                  'private func failFinalization(', 'private func completeFinalization(',
                  'private func discardFinalizations()', 'func discardCapturedAudio()'):
    if signature in listener: signatures.append(signature)
body = '\n'.join(declaration(listener, signature) for signature in signatures)
tap = listener.index('input.installTap(')
start = listener.index('self.orphanLock.lock()', tap)
end = listener.index('self.orphanLock.unlock()', start) + len('self.orphanLock.unlock()')
body += '\nfunc feedRecognitionAudio(_ buffer: Int) {\n' + listener[start:end] + '\n}'
journal = (here / '../Anticipy/Audio/ListenJournal.swift').read_text()
(out / 'ListenerBodies.swift').write_text('import Foundation\nextension LifecycleListener {\n' + body + '\n}\n' + declaration(journal, 'enum ListenEvent:'))

# The actual append/warmUp/makeStream/finish bodies execute. Apple model,
# PCM/conversion and results edges are controlled doubles in the Swift file.
engine = (here / '../Anticipy/Audio/SpeechAnalyzerEngine.swift').read_text()
signatures = ['func begin()', 'private func makeStream()', 'private func warmUp(',
              'func append(_ buffer:', 'func finish()']
# Start after the protocol declaration, which also declares append/finish.
engine = engine[engine.index('final class SpeechAnalyzerRequestEngine:'):]
for signature in ('private func reportFailure()', 'private func canCompleteSuccessfully()', 'func cancel()'):
    if signature in engine: signatures.append(signature)
body = '\n'.join(declaration(engine, signature) for signature in signatures)
(out / 'AnalyzerBodies.swift').write_text('import Foundation\nextension AnalyzerBoundaryEngine {\n' + body + '\n}\n')
speaker = (here / '../Anticipy/Audio/SpeakerTagger.swift').read_text()
(out / 'SpeakerBody.swift').write_text('import Foundation\nextension SpeakerFIFOProbe {\n'
    + declaration(speaker, 'func afterPendingDeliveries(') + '\n}\n')
PY
swiftc -Onone -swift-version 5 -parse-as-library \
    "$here/../Anticipy/Audio/ListenSessionFacts.swift" \
    "$here/../Anticipy/Audio/ListenWatchdogPolicy.swift" \
    "$here/../Anticipy/Audio/TranscriptCursor.swift" \
    "$here/../Anticipy/Audio/TranscriptFlushPolicy.swift" \
    "$out/ListenerFixtures.swift" "$out/ListenerBodies.swift" \
    "$out/AnalyzerBodies.swift" "$out/SpeakerBody.swift" "$here/AnalyzerLifecycleBoundaryTests.swift" \
    -o "$out/analyzer-boundaries"
"$out/analyzer-boundaries"

if [ "${1:-}" = "--check-mutations" ]; then
    python3 - "$out" <<'PY'
from pathlib import Path
import sys
out = Path(sys.argv[1])
listener = (out / 'ListenerBodies.swift').read_text()
engine = (out / 'AnalyzerBodies.swift').read_text()
speaker = (out / 'SpeakerBody.swift').read_text()

def mutation(name, source, needle, replacement, count=1):
    assert source.count(needle) == count, f'{name} lost its exact anchors'
    (out / f'{name}.swift').write_text(source.replace(needle, replacement))

mutation('NoDrainHandoff', listener,
         'self.finishingAnalyzers[ObjectIdentifier(engine)]?.result(text, isFinal)', '')
mutation('NoDeliveryLease', listener,
         'guard let self, let retiring, shouldDeliver(),\n                          self.finishingAnalyzers[identity]?.engine === retiring',
         'guard let self, let retiring,\n                          self.finishingAnalyzers[identity]?.engine === retiring')
mutation('NoReaderWait', engine, 'await resultsTask?.value', '')
# Only mutate the warm-up guard, not append or begin: this measures ownership
# of work resumed after the asset await, not ordinary append admission.
needle = 'guard let self, !self.finished else { return }\n            self.analyzer = analyzer'
mutation('WarmUpAfterFinish', engine, needle,
         'guard let self else { return }\n            self.analyzer = analyzer')
mutation('SilentOverflow', engine,
         'ListenJournal.shared.record(.buffersDropped(count: 1))\n                }\n                self.reportFailure()',
         'ListenJournal.shared.record(.buffersDropped(count: 1))\n                }')
mutation('UncancelledProvisioning', engine, 'self.provisioningTask?.cancel()', '', count=2)
mutation('UncancelledReader', engine, 'self.resultsTask?.cancel()', '')
mutation('NoSpeakerGeneration', speaker,
         'guard let self, generation == self.deliveryGeneration else { return }',
         'guard let self else { return }')
mutation('FailedResultStillFinishes', engine,
         'queue.sync { !cancelled && !failureReported }',
         'queue.sync { !cancelled }')
mutation('SilentUnderlyingCancellation', engine,
         'if !Task.isCancelled { self?.reportFailure() }', '', count=3)
PY
    for mutation in NoDrainHandoff NoDeliveryLease NoReaderWait WarmUpAfterFinish SilentOverflow UncancelledProvisioning UncancelledReader NoSpeakerGeneration FailedResultStillFinishes SilentUnderlyingCancellation; do
        listener_source="$out/ListenerBodies.swift"
        analyzer_source="$out/AnalyzerBodies.swift"
        speaker_source="$out/SpeakerBody.swift"
        case "$mutation" in
            NoDrainHandoff|NoDeliveryLease) listener_source="$out/$mutation.swift" ;;
            NoSpeakerGeneration) speaker_source="$out/$mutation.swift" ;;
            *) analyzer_source="$out/$mutation.swift" ;;
        esac
        swiftc -Onone -swift-version 5 -parse-as-library \
            "$here/../Anticipy/Audio/ListenSessionFacts.swift" \
            "$here/../Anticipy/Audio/ListenWatchdogPolicy.swift" \
            "$here/../Anticipy/Audio/TranscriptCursor.swift" \
            "$here/../Anticipy/Audio/TranscriptFlushPolicy.swift" \
            "$out/ListenerFixtures.swift" "$listener_source" \
            "$analyzer_source" "$speaker_source" "$here/AnalyzerLifecycleBoundaryTests.swift" \
            -o "$out/$mutation"
        if "$out/$mutation" > "$out/$mutation.log" 2>&1; then
            echo "FAIL: $mutation did not fail its lifecycle regression"
            exit 1
        fi
        case "$mutation" in
            NoDrainHandoff) expected='FAIL: same-session asynchronous finalization preserves its captured tail' ;;
            NoDeliveryLease) expected='FAIL: delivery rechecks account lease after speaker FIFO barrier' ;;
            NoReaderWait) expected='FAIL: finalizer return alone cannot retire the unread result stream' ;;
            WarmUpAfterFinish) expected='FAIL: finished engine cannot launch analyzer task after warm-up resumes' ;;
            SilentOverflow) expected='FAIL: warm-up overflow is retained or explicitly reported, never silently lost' ;;
            UncancelledProvisioning) expected='FAIL: completed provisioning cannot launch after stop (discard: false)' ;;
            UncancelledReader) expected='FAIL: privacy cancel fences and cancels every owned task' ;;
            NoSpeakerGeneration) expected='FAIL: production speaker barrier rejects a changed delivery generation' ;;
            FailedResultStillFinishes) expected='FAIL: results failure cannot signal successful finalization' ;;
            SilentUnderlyingCancellation) expected='FAIL: results-cancelled failure cannot signal successful finalization' ;;
        esac
        if ! grep -Fq "$expected" "$out/$mutation.log"; then
            echo "FAIL: $mutation failed without its required behavioral failure"
            exit 1
        fi
        echo "PASS: $mutation negative control fails its required behavioral check"
    done
fi
