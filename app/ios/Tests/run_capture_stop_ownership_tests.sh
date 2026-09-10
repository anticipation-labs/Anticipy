#!/bin/sh
# Real app Stop body and account lease, with no microphone or network.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
python3 - "$here/../Anticipy/AnticipyApp.swift" "$out/Stop.swift" <<'PY'
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
            if depth == 0:
                return source[start:i + 1]
    raise AssertionError(signature)
Path(sys.argv[2]).write_text('import Foundation\n'
    + declaration('enum AccountWriteLeasePolicy {')
    + '\n@MainActor extension StopSession {\n'
    + declaration('func stopListening()') + '\n'
    + declaration('private func discardListening()').removeprefix('private ') + '\n}\n')
# These actual call sites are privacy/storage boundaries, not user Stop.
assert 'discardListening()' in declaration('func forgetThisPhone() async')
assert 'discardListening()' in declaration('private func stageTranscript(')
assert 'listener.discardCapturedAudio()' in declaration('private func clearSignedInSurface()')
view = (Path(sys.argv[1]).parent / 'Views/ContentView.swift').read_text()
assert 'if session.listener.finalizationFailed {' in view
assert 'Text(HomeCopy.audioFinalizationFailed)' in view
PY
swiftc -Onone -parse-as-library "$out/Stop.swift" \
  "$here/CaptureStopOwnershipTests.swift" -o "$out/test"
"$out/test"
