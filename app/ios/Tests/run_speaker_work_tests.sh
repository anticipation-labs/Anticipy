#!/bin/sh
set -eu
here=$(cd "$(dirname "$0")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
cp "$here/SpeakerWorkTests.swift" "$out/main.swift"
# Keep assert() AND the deterministic semaphore handshake inside it active.
# -O strips both and can make an untested ordering print a false PASS.
swiftc -Onone "$here/../Anticipy/Audio/VoiceRoster.swift" \
    "$here/../Anticipy/Audio/SpeakerTagger.swift" "$out/main.swift" -o "$out/speaker-work"
"$out/speaker-work"

# Optional negative control: compile only a generated temporary source with
# the epoch comparison removed. The real repository source stays untouched.
# An assertion failure is required, not merely any nonzero process exit.
if [ "${1:-}" = "--check-mutation" ]; then
    sed 's/guard let self, generation == self.deliveryGeneration else { return }/guard let self else { return }/' \
        "$here/../Anticipy/Audio/SpeakerTagger.swift" > "$out/SpeakerTagger-no-epoch.swift"
    swiftc -Onone "$here/../Anticipy/Audio/VoiceRoster.swift" \
        "$out/SpeakerTagger-no-epoch.swift" "$out/main.swift" -o "$out/speaker-no-epoch"
    if "$out/speaker-no-epoch" > "$out/mutation.log" 2>&1; then
        echo "FAIL: removing the account epoch did not fail the speaker regression"
        exit 1
    fi
    if ! grep -q 'Assertion failed: an account boundary must discard the old result' "$out/mutation.log"; then
        echo "FAIL: epoch mutation failed for a reason other than the required ownership assertion"
        exit 1
    fi
    echo "PASS: temporary no-epoch mutation fails the active account-ownership assertion"
fi

# The real tagger runtime test matters only if the session's actual account
# boundary calls its epoch invalidation and ordinary Stop does not.
python3 - "$here/../Anticipy" <<'PY'
from pathlib import Path
import sys
app = Path(sys.argv[1])
def source(relative):
    return '\n'.join(line for line in (app / relative).read_text().splitlines()
                     if not line.lstrip().startswith('//'))
def body(text, signature):
    opening = text.index('{', text.index(signature))
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == '{': depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0: return text[opening + 1:index]
    raise AssertionError(signature)
session = source('AnticipyApp.swift')
listener = source('Audio/PhoneListener.swift')
speaker = source('Audio/SpeakerTagger.swift')
tag = body(speaker, 'func tagForLatestUtterance(')
assert tag.index('let generation = deliveryGeneration') < tag.index('embeddingQueue.async')
assert tag.index('generation == self.deliveryGeneration') < tag.index('completion(nil)')
assert tag.index('generation == self.deliveryGeneration') < tag.index('self.roster.identify(')
assert 'speakerTagger.invalidatePendingDeliveries()' in body(session, 'private func clearSignedInSurface()')
for name in ('func signOut()', 'private func expireSession()'):
    boundary = body(session, name)
    assert 'clearSignedInSurface()' in boundary, name
normal_stop = body(listener, 'func stop()')
assert 'invalidatePendingDeliveries' not in normal_stop
assert 'deliver(tail, reason: .final, wordsAppearedAt: partingStartedAt,' in normal_stop
delivery = body(listener, 'private func deliver(')
assert delivery.index('speaker.tagForLatestUtterance') < delivery.index('onSpeaker(line, tag, wordsAppearedAt, now, continuesPrevious)')
for callback in ('listener.onLine =', 'listener.onSpeaker ='):
    callback_body = body(session, callback)
    assert callback_body.index('AccountWriteLeasePolicy.begin(') < callback_body.index('Task {')
    assert callback_body.index('AccountWriteLeasePolicy.isCurrent(') < callback_body.index('await self.heard(')
print('PASS: real account invalidation, pre-tag epoch, normal Stop tail and callback-Task lease are wired')
PY
