#!/bin/sh
# Compile and run the REAL heard body against a delayed in-memory transport.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
python3 - "$here/../Anticipy/AnticipyApp.swift" "$out/HeardUnderTest.swift" \
    "$here/../Anticipy/Backend/AnticipyBackend.swift" "$here/../Anticipy/Views/ConversationDashboard.swift" <<'PY'
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
            if depth == 0: return source[start:index + 1]
    raise AssertionError(signature)
parts = [declaration('func heard(_ line: String,'), declaration('func acceptTyped(_ line: String)'),
         declaration('private func stageTranscript('), declaration('private func flushUnsent()')]
output = ('import Foundation\n' + declaration('enum AccountWriteLeasePolicy {')
    + '\n' + declaration('enum CaptureOutboxPersistence {')
    + '\n' + declaration('enum PendingSpeechRetention {')
    + '\n' + declaration('private struct BufferedLine:').removeprefix('private ')
    + '\n@MainActor extension CaptureSession {\n'
    + '\n'.join(part.removeprefix('private ') for part in parts) + '\n}\n')
# Only the filesystem LOCATION is injected. Migration/codec/retention/clear
# implementations are the production bodies, operating on a temporary file.
disk_parts = [declaration(signature).removeprefix('private ').replace('CaptureOutboxPersistence.location()', 'queueURL')
              for signature in ('private func readPendingLines()', 'private func persistPendingLines(',
                                'private func pendingLinesOwnedByCurrentAccount(',
                                'private func clearPendingLinesOwned(', 'private func clearAllPendingLinesOnDevice()')]
output += '\n@MainActor extension DiskCaptureSession {\n' + '\n'.join(disk_parts) + '\n}\n'
source = Path(sys.argv[3]).read_text()
output += '\n@MainActor extension CaptureLookupBackend {\n' + declaration('func transcriptEventID(') + '\n}\n'
source = Path(sys.argv[4]).read_text()
output += '\n@MainActor extension ComposerHarness {\n' + declaration('private func send()').removeprefix('private ') + '\n}\n'
Path(sys.argv[2]).write_text(output)
PY
swiftc -parse-as-library "$here/../Anticipy/Audio/CaptureEnvelope.swift" \
    "$here/CaptureAccountRaceTests.swift" "$out/HeardUnderTest.swift" -o "$out/test"
"$out/test"
