#!/bin/sh
# Actual app capture callbacks, staging and forget boundaries; fixture I/O only.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
python3 - "$here/../Anticipy/AnticipyApp.swift" "$out/Callbacks.swift" <<'PY'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text()
def declaration(signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 0
    for i in range(opening, len(source)):
        if source[i] == '{': depth += 1
        elif source[i] == '}':
            depth -= 1
            if depth == 0: return source[start:i + 1]
    raise AssertionError(signature)
top = ['enum AccountWriteLeasePolicy {', 'enum PendingSpeechRetention {',
       'private struct BufferedLine:', 'enum LineSource:',
       'struct SessionLine:', 'struct TranscriptLine:']
out = 'import Foundation\n' + '\n'.join(declaration(s).removeprefix('private ') for s in top)
out += '\n@MainActor extension CallbackSession {\nfunc installCallbacks() {\n'
out += declaration('listener.onLine = {') + '\n' + declaration('listener.onSpeaker = {') + '\n}\n'
for signature in ('func heard(_ line: String,', 'private func stageTranscript(',
                  'func stopListening()', 'private func discardListening()',
                  'func clearPendingLines()', 'private func clearPendingLinesOwned(',
                  'private func clearAllPendingLinesOnDevice()', 'func forgetThisPhone() async'):
    body = declaration(signature).removeprefix('private ')
    # Inject only the settings-storage location, never capture/lease guards.
    out += body.replace('UserDefaults.standard', 'FixtureDefaults.standard') + '\n'
surface = declaration('private func clearSignedInSurface()')
boundary = surface[surface.index('{') + 1:surface.index('lastTranscriptEventID = ""')]
out += 'func clearSignedInSurfaceBoundary() {\n' + boundary + '\n}\n}\n'
Path(sys.argv[2]).write_text(out)
PY
swiftc -Onone -parse-as-library "$out/Callbacks.swift" \
  "$here/CaptureCallbackGenerationTests.swift" -o "$out/test"
"$out/test"
