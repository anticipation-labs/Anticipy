#!/bin/sh
# Execute the real refresh reconciliation block and production feed models.
# Synthetic events only: no account, storage, microphone or network.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
python3 - "$here/../Anticipy/AnticipyApp.swift" "$out/Reconcile.swift" <<'PY'
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
            if depth == 0: return source[start:i+1]
    raise AssertionError(signature)
start = source.index('            var serverLines = events')
end_text = '            if transcript != serverLines { transcript = serverLines }'
end = source.index(end_text, start) + len(end_text)
output = 'import Foundation\n'
output += declaration('struct TranscriptLine:') + '\n'
output += declaration('struct SessionLine:') + '\n'
output += 'extension EchoHarness { func reconcile(_ events: [FixtureEvent]) {\n'
output += source[start:end] + '\n} }\n'
Path(sys.argv[2]).write_text(output)
PY
swiftc -Onone -parse-as-library "$out/Reconcile.swift" \
  "$here/TranscriptEchoIdentityTests.swift" -o "$out/test"
"$out/test"
