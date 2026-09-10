#!/bin/sh
# Actual PhoneListener lifecycle bodies, with controlled OS/recognizer edges.
# No microphone, model, network, simulator, or user defaults are touched.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
python3 - "$here/../Anticipy/Audio/PhoneListener.swift" "$out/ListenerUnderTest.swift" \
    "$here/../Anticipy/Audio/ListenJournal.swift" <<'PY'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
def declaration(signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == '{': depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0: return source[start:index + 1].removeprefix('private ')
    raise AssertionError(signature)
signatures = ['func start()', 'private func begin()', 'private func startWatchdog()',
              'private func startRecognition()', 'private func runAnalyzerRequest(',
              'private func swapRecognition(', 'func stop()',
              'func startForEnrollment()', 'func stopAfterEnrollment()',
              'private func absorbRecognized(', 'private func flushTail(',
              'private func deliver(', 'private func scheduleSilenceFlush()']
for signature in ('func stopAfterCurrentAudio(', 'private func stopCapture(',
                  'private func failFinalization(', 'private func completeFinalization(',
                  'private func discardFinalizations()', 'func discardCapturedAudio()'):
    if signature in source: signatures.append(signature)
# Optional only to let the pre-fix source execute and fail behaviorally.
if 'private var hasActiveRecognition:' in source:
    signatures.append('private var hasActiveRecognition:')
if 'private func discardEnrollmentRecognition()' in source:
    signatures.append('private func discardEnrollmentRecognition()')
output = 'import Foundation\nextension LifecycleListener {\n'
output += '\n'.join(declaration(signature) for signature in signatures)
# Execute the actual tap's locked routing block with model-free buffers. The
# deafen, scratch and speaker sinks stay outside this recognition-only seam.
tap = source.index('input.installTap(')
start = source.index('self.orphanLock.lock()', tap)
end = source.index('self.orphanLock.unlock()', start) + len('self.orphanLock.unlock()')
output += '\nfunc feedRecognitionAudio(_ buffer: Int) {\n' + source[start:end] + '\n}\n}\n'
source = Path(sys.argv[3]).read_text()
output += declaration('enum ListenEvent:') + '\n'
Path(sys.argv[2]).write_text(output)
PY
swiftc -Onone -swift-version 5 -parse-as-library \
    "$here/../Anticipy/Audio/ListenSessionFacts.swift" \
    "$here/../Anticipy/Audio/ListenWatchdogPolicy.swift" \
    "$here/../Anticipy/Audio/TranscriptCursor.swift" \
    "$here/../Anticipy/Audio/TranscriptFlushPolicy.swift" \
    "$here/CaptureLifecycleTests.swift" "$out/ListenerUnderTest.swift" \
    -o "$out/capture-lifecycle"
"$out/capture-lifecycle"

# Check the real declarations and account callers too: a working extracted
# body cannot vouch for a storage field or caller it does not execute.
python3 - "$here/../Anticipy/Audio/PhoneListener.swift" "$here/../Anticipy/AnticipyApp.swift" <<'PY'
from pathlib import Path
import re
import sys
def code(path):
    return '\n'.join(line for line in Path(path).read_text().splitlines()
                     if not line.lstrip().startswith('//'))
listener, session = map(code, sys.argv[1:])
assert re.search(r'private\s+var\s+listenStartGeneration\s*=\s*0\b', listener)
assert re.search(r'private\s+var\s+analyzerFailures\s*=\s*0\b', listener)
assert re.search(r'private\s+var\s+analyzerDisabledForSession\s*=\s*false\b', listener)
def body(source, signature):
    opening = source.index('{', source.index(signature))
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == '{': depth += 1
        elif source[index] == '}':
            depth -= 1
            if depth == 0: return source[opening + 1:index]
    raise AssertionError(signature)
for signature in ('func signOut()', 'private func expireSession()'):
    boundary = body(session, signature)
    assert boundary.index('listener.stop()') < boundary.index('clearSignedInSurface()'), signature
assert any(call in body(session, 'func stopListening(') for call in
           ('listener.stop()', 'listener.stopAfterCurrentAudio('))
begin = body(listener, 'private func begin()')
assert begin.index('guard !isListening') < begin.index('analyzerFailures = 0') < begin.index('startRecognition()')
for signature in ('private func startRecognition()', 'private func swapRecognition('):
    assert 'analyzerFailures = 0' not in body(listener, signature), signature
analyzer = code(Path(sys.argv[1]).with_name('SpeechAnalyzerEngine.swift'))
assert 'SpeechTranscriber(locale: supported, preset: .transcription)' in analyzer
assert 'volatileResults' not in analyzer
print('PASS: lifecycle storage/callers, new-session-only reset and final-only analyzer preset are wired')
PY

if [ "${1:-}" = "--check-mutations" ]; then
    python3 - "$out/ListenerUnderTest.swift" "$out" <<'PY'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
out = Path(sys.argv[2])
needle = 'self.listenStartGeneration == generation'
assert source.count(needle) == 2, 'permission fence mutation lost its two anchors'
(out / 'NoPermissionFence.swift').write_text(source.replace(needle, 'true'))
needle = 'hasTask: self.hasActiveRecognition'
assert source.count(needle) == 1, 'watchdog mutation lost its one anchor'
(out / 'LegacyOnlyWatchdog.swift').write_text(source.replace(needle, 'hasTask: self.task != nil'))
needle = 'if !wasListeningBeforeEnrollment { stop() }'
assert source.count(needle) == 1, 'enrollment exit mutation lost its anchor'
(out / 'EarlyEnrollmentExit.swift').write_text(source.replace(needle, 'enrolling = false\n' + needle))
needle = 'if self.enrolling {'
assert source.count(needle) == 1, 'enrollment audio fence mutation lost its anchor'
(out / 'NoEnrollmentAudioFence.swift').write_text(source.replace(needle, 'if false {'))
needle = '        discardEnrollmentRecognition()'
assert source.count(needle) == 3, 'enrollment retirement mutation lost its two enrollment and one explicit discard anchors'
# The first two declarations extracted above are the enrollment boundaries;
# leave the distinct explicit forget/storage discard method unchanged.
(out / 'NoEnrollmentRetirement.swift').write_text(source.replace(needle, '', 2))
needle = 'self.absorbRecognized(text, isFinal: false)'
assert source.count(needle) == 1, 'analyzer final mutation lost its anchor'
(out / 'AnalyzerFinalIsTaskLimit.swift').write_text(source.replace('text, _ in', 'text, isFinal in').replace(needle, 'self.absorbRecognized(text, isFinal: isFinal)'))
needle = '        analyzerFailures = 0\n        analyzerDisabledForSession = false'
assert source.count(needle) == 1, 'new-session reset mutation lost its anchor'
(out / 'StickyAnalyzerFailure.swift').write_text(source.replace(needle, ''))
needle = 'self.cursor.reset()'
assert source.count(needle) == 1, 'analyzer phrase cursor mutation lost its anchor'
(out / 'NoAnalyzerPhraseReset.swift').write_text(source.replace(needle, ''))
(out / 'LostAnalyzerSpeechClock.swift').write_text(source.replace(needle, needle + '\n                    self.lastPartialAt = nil'))
needle = '        orphanLock.lock()\n        enrolling = false\n        wasListeningBeforeEnrollment = false\n        orphanLock.unlock()'
assert source.count(needle) == 1, 'Stop enrollment-close mutation lost its anchor'
(out / 'StaleEnrollmentAfterStop.swift').write_text(source.replace(needle, ''))
needle = '        lastDelivered = nil\n        installObserversOnce()'
assert source.count(needle) == 1, 'new-session replay reset mutation lost its anchor'
(out / 'StaleReplayAcrossSessions.swift').write_text(source.replace(needle, '        installObserversOnce()'))
PY
    for mutation in NoPermissionFence LegacyOnlyWatchdog EarlyEnrollmentExit NoEnrollmentAudioFence NoEnrollmentRetirement AnalyzerFinalIsTaskLimit StickyAnalyzerFailure NoAnalyzerPhraseReset LostAnalyzerSpeechClock StaleEnrollmentAfterStop StaleReplayAcrossSessions; do
        swiftc -Onone -swift-version 5 -parse-as-library \
            "$here/../Anticipy/Audio/ListenSessionFacts.swift" \
            "$here/../Anticipy/Audio/ListenWatchdogPolicy.swift" \
            "$here/../Anticipy/Audio/TranscriptCursor.swift" \
            "$here/../Anticipy/Audio/TranscriptFlushPolicy.swift" \
            "$here/CaptureLifecycleTests.swift" "$out/$mutation.swift" \
            -o "$out/$mutation"
        if "$out/$mutation" > "$out/$mutation.log" 2>&1; then
            echo "FAIL: $mutation did not fail the lifecycle regression"
            exit 1
        fi
        case "$mutation" in
            NoPermissionFence) expected='FAIL: Stop fences a delayed speech grant' ;;
            LegacyOnlyWatchdog) expected='FAIL: healthy analyzer survives repeated watchdog ticks' ;;
            EarlyEnrollmentExit) expected='FAIL: fresh enrollment never delivers its recognized sample' ;;
            NoEnrollmentAudioFence) expected='FAIL: fresh sample audio is not held for a future transcript' ;;
            NoEnrollmentRetirement) expected='FAIL: enrollment retires the recognizer before sample' ;;
            AnalyzerFinalIsTaskLimit) expected='FAIL: analyzer finalization does not retire its request' ;;
            StickyAnalyzerFailure) expected='FAIL: a genuinely new session retries analyzer after prior fallback' ;;
            NoAnalyzerPhraseReset) expected='FAIL: two identical finalized phrases are both delivered' ;;
            LostAnalyzerSpeechClock) expected='FAIL: fresh final speech keeps an aged analyzer alive' ;;
            StaleEnrollmentAfterStop) expected='FAIL: old enrollment cleanup cannot stop a new session' ;;
            StaleReplayAcrossSessions) expected='FAIL: a fresh session preserves a phrase matching the prior session' ;;
        esac
        if ! grep -q "$expected" "$out/$mutation.log"; then
            echo "FAIL: $mutation failed without its required behavioral failure"
            exit 1
        fi
        echo "PASS: $mutation negative control fails its required behavioral check"
    done
fi
