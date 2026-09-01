#!/bin/sh
# An AskCard reply is an idempotent owner-scoped write, not a fire-and-forget
# POST. This gate executes its production state policy and scans the shipping
# backend/session/view seams that carry the durable identity.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
APP="$HERE/../Anticipy"
SESSION="$APP/AnticipyApp.swift"
BACKEND="$APP/Backend/AnticipyBackend.swift"
CONTENT="$APP/Views/ContentView.swift"
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT

awk '/^enum ActionWritePolicy \{/,/^\}/' "$SESSION" > "$OUT/ActionWritePolicy.swift"
awk '/^enum AppReplyWritePolicy \{/,/^\}/' "$SESSION" > "$OUT/AppReplyWritePolicy.swift"
if ! grep -q 'static func reconcile' "$OUT/AppReplyWritePolicy.swift" \
   || ! grep -q 'static func isVerifiedRefusal' "$OUT/ActionWritePolicy.swift"; then
    echo "could not extract app-reply production policies"
    exit 2
fi
{
    echo 'import Foundation'
    cat "$OUT/ActionWritePolicy.swift"
    cat "$OUT/AppReplyWritePolicy.swift"
    sed '1{/^import Foundation$/d;}' "$HERE/AppReplyWriteTests.swift"
} > "$OUT/main.swift"
swiftc -O "$OUT/main.swift" -o "$OUT/app-reply-write-tests"
"$OUT/app-reply-write-tests"

python3 - "$SESSION" "$BACKEND" "$CONTENT" <<'PY'
import pathlib
import re
import sys

session = pathlib.Path(sys.argv[1]).read_text()
backend = pathlib.Path(sys.argv[2]).read_text()
content = pathlib.Path(sys.argv[3]).read_text()

def body(source: str, signature: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise SystemExit(f"missing source seam: {signature}")
    opening = source.find("{", start)
    depth = 0
    for i in range(opening, len(source)):
        if source[i] == "{": depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0: return source[opening + 1:i]
    raise SystemExit(f"unterminated source seam: {signature}")

def ordered(haystack: str, *needles: str) -> bool:
    cursor = -1
    for needle in needles:
        cursor = haystack.find(needle, cursor + 1)
        if cursor < 0: return False
    return True

push = body(backend, "func pushEvent(kind: String")
lookup = body(backend, "func hasEvent(kind: String")
answer = body(session, "func answer(_ event: BrainEvent")
write = body(session, "private func writeAppReply(")
check_outcome = body(session, "func reconcileAnswer(_ event: BrainEvent")
ask = body(content, "struct AskCard: View")
sign_in = body(session, "func signIn(email: String, password: String) async")
resume = body(session, "func resumeSignedInAccount() async")
forget = body(session, "func forgetThisPhone() async")
delete = body(session, "func deleteEverythingOnServer() async")

checks = {
    "pushEvent transmits the client durable id":
        'body["external_event_id"] = externalEventID' in push,
    "exact lookup filters by owner, durable id, and app_reply kind":
        all(token in lookup for token in (
            'owner_ref=', 'external_event_id=', 'kind=',
            'readData(from: comps.url!)')),
    "exact lookup validates decoded ownership rather than trusting the filter":
        '$0.owner_ref == accountID' in lookup
        and '$0.external_event_id == externalEventID' in lookup,
    "answer derives one account/question pending identity":
        'AppReplyWritePolicy.pending(accountID: accountID' in answer,
    "unknown identity reaches disk before the POST leaves": ordered(
        write, 'rememberPendingAppReply(pending)',
        'try await b.pushEvent(kind: "app_reply"'),
    "the POST uses that exact external id":
        'externalEventID: pending.externalEventID' in write,
    "response loss reconciles the exact durable id": ordered(
        write, 'Task.sleep(', 'canonicalAppReplyRead(pending, backend: b)',
        'AppReplyWritePolicy.reconcile(read)'),
    "unique-index refusal is reconciled instead of misreported":
        'refusal.status == 400 || refusal.status == 409' in write
        and 'canonicalAppReplyRead(pending, backend: b)' in write,
    "Check outcome performs a canonical read without resending":
        'canonicalAppReplyRead(pending, backend: b)' in check_outcome
        and 'pushEvent' not in check_outcome,
    "unknown writes persist across restart":
        '@AppStorage(AppReplyWritePolicy.storageKey)' in session
        and 'restorePendingAppReplyState()' in sign_in
        and 'restorePendingAppReplyState()' in resume,
    "device Forget erases all pending reply identities":
        'clearAllPendingAppRepliesOnDevice()' in forget,
    "successful account deletion erases pending reply identities":
        'clearAllPendingAppRepliesOnDevice()' in delete,
    "AskCard offers a real Check outcome action":
        'await session.reconcileAnswer(event)' in ask
        and 'Text(unverified ? "Check outcome"' in ask,
    "Check remains enabled after restart with an empty text field":
        '.disabled(sending || (!unverified && empty))' in ask,
    "the old indefinite dead-end label is gone": 'Outcome unknown' not in ask,
}

for name, ok in checks.items(): print(("PASS: " if ok else "FAIL: ") + name)
failed = [name for name, ok in checks.items() if not ok]
if failed: raise SystemExit(f"app reply source contract: {len(failed)} failed")
print("app reply source contract: all passed")
PY
