#!/bin/sh
# A refresh response is account data. Prove that every yielded result is still
# owned by the session that started it before it can reach Home, notifications,
# or the browser status badge.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
APP="$HERE/../Anticipy"
SESSION="$APP/AnticipyApp.swift"
NOTIFIER="$APP/Notifier.swift"
PRIVACY="$APP/Views/SettingsPrivacyDataView.swift"
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT

awk '/^enum RefreshAccountPolicy \{/,/^\}/' "$SESSION" > "$OUT/RefreshAccountPolicy.swift"
awk '/^enum AccountWriteLeasePolicy \{/,/^\}/' "$SESSION" > "$OUT/AccountWriteLeasePolicy.swift"
awk '/^enum NotificationLeasePolicy \{/,/^\}/' "$NOTIFIER" > "$OUT/NotificationLeasePolicy.swift"
if ! grep -q 'static func isCurrent' "$OUT/RefreshAccountPolicy.swift"; then
    echo "could not extract RefreshAccountPolicy"
    exit 2
fi
if ! grep -q 'removeAfterAdd' "$OUT/NotificationLeasePolicy.swift"; then
    echo "could not extract NotificationLeasePolicy"
    exit 2
fi
if ! grep -q 'static func isCurrent' "$OUT/AccountWriteLeasePolicy.swift"; then
    echo "could not extract AccountWriteLeasePolicy"
    exit 2
fi

swiftc -O -parse-as-library \
    "$OUT/RefreshAccountPolicy.swift" \
    "$OUT/AccountWriteLeasePolicy.swift" \
    "$OUT/NotificationLeasePolicy.swift" \
    "$HERE/RefreshAccountRaceTests.swift" \
    -o "$OUT/refresh-account-race-tests"
"$OUT/refresh-account-race-tests"

python3 - "$SESSION" "$NOTIFIER" "$PRIVACY" <<'PY'
import pathlib
import sys

session = pathlib.Path(sys.argv[1]).read_text()
notifier = pathlib.Path(sys.argv[2]).read_text()
privacy = pathlib.Path(sys.argv[3]).read_text()

def body(source: str, signature: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise SystemExit(f"missing source seam: {signature}")
    opening = source.find("{", start)
    depth = 0
    for i in range(opening, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1:i]
    raise SystemExit(f"unterminated source seam: {signature}")

def ordered(haystack: str, *needles: str) -> bool:
    cursor = -1
    for needle in needles:
        cursor = haystack.find(needle, cursor + 1)
        if cursor < 0:
            return False
    return True

refresh = body(session, "func refresh() async")
guard = "guard refreshLeaseIsCurrent(lease) else { return }"
checks = {
    "refresh starts with an account/generation lease":
        "guard let lease = beginRefreshLease() else { return }" in refresh,
    "health response is guarded before health UI mutation": ordered(
        refresh, "let reachable = await b.isReachable()", guard,
        "backendReachable = reachable"),
    "queue flush yield is guarded before job read": ordered(
        refresh, "await flushUnsent()", guard,
        "try await b.fetchJobs(owner: requestedOwnerID)"),
    "job response is guarded before jobs mutation": ordered(
        refresh, "try await b.fetchJobs(owner: requestedOwnerID)", guard,
        "jobs = fetched.map"),
    "notification yield is guarded and receives live lease callback":
        "stillCurrent:" in refresh and ordered(
            refresh, "await notifier.announce", guard,
            "let fetchedEvents = try? await b.fetchEvents()"),
    "event response is guarded before transcript mutation": ordered(
        refresh, "let fetchedEvents = try? await b.fetchEvents()", guard,
        "transcript = serverLines"),
    "agent response is guarded before agent mutation": ordered(
        refresh, "let fetchedAgent = try? await b.fetchAgent(owner: requestedOwnerID)",
        guard, "agentPaired = agent.paired"),
    "all six refresh yields plus thrown job paths are guarded":
        refresh.count(guard) >= 8,
    "clear boundary invalidates refreshes":
        "invalidateRefreshes()" in body(session, "private func clearSignedInSurface()"),
    "sign-in boundary invalidates refreshes":
        "invalidateRefreshes()" in body(session, "func signIn(email: String, password: String) async"),
}

announce = body(notifier, "func announce(jobs: [AgentJob]")
post = body(notifier, "private func post(id: String")
checks.update({
    "notifier uses its refresh-validity callback": "stillCurrent()" in announce,
    "permission yield is rechecked before owner notification state": ordered(
        announce, "await askIfNeeded()", "guard stillCurrent(), authorized else { return }",
        "raised.insert(job.id)"),
    "notification posts recheck before any later state can survive":
        announce.count("await post(") == 2
        and announce.count("guard stillCurrent() else { return }") >= 4,
    "a stale add completion removes its exact pending and delivered request":
        ordered(post, "await centre.add(request)",
                "NotificationLeasePolicy.removeAfterAdd(stillCurrent: stillCurrent())",
                "removePendingNotificationRequests(withIdentifiers: [identifier])",
                "removeDeliveredNotifications(withIdentifiers: [identifier])"),
})

phone_save = body(session, "func saveOwnerPhone(_ raw: String) async")
details_save = body(session, "func saveOwnerDetails(first: String")
checks.update({
    "phone save captures one authenticated-session lease":
        "AccountWriteLeasePolicy.begin" in phone_save
        and "let requestedBackend = backend" in phone_save,
    "phone save rechecks its lease after the write and before its mirror": ordered(
        phone_save, "await requestedBackend.upsertOwnerPhone",
        "AccountWriteLeasePolicy.isCurrent", "ownerPhone = e", "return true"),
    "details save captures one authenticated-session lease":
        "AccountWriteLeasePolicy.begin" in details_save
        and "let requestedBackend = backend" in details_save,
    "details save rechecks its lease after the write and before every mirror": ordered(
        details_save, "await requestedBackend.upsertOwner",
        "AccountWriteLeasePolicy.isCurrent", "ownerFirstName = values.firstName",
        "ownerBirthday = values.birthday", "return true"),
})

delete = body(session, "func deleteEverythingOnServer() async")
forget = body(session, "func forgetThisPhone() async")
delete_view = body(privacy, "private func deleteServerData()")
checks.update({
    "server delete captures its original authenticated backend": ordered(
        delete, "AccountWriteLeasePolicy.begin", "let requestedBackend = backend",
        "try await requestedBackend.deleteAccount()"),
    "server delete rechecks ownership before device wipe and sign-out": ordered(
        delete, "clearPendingLinesOwned(by: lease.accountID)",
        "AccountWriteLeasePolicy.isCurrent", "guard stillCurrent || expiredSameAccount",
        "clearAllPendingLinesOnDevice()", "signOut()"),
    "device Forget captures its original authenticated backend": ordered(
        forget, "AccountWriteLeasePolicy.begin", "let requestedBackend = backend",
        "await requestedBackend.unpairAgent"),
    "device Forget rechecks ownership before notice, sign-out, and rotation": ordered(
        forget, "AccountWriteLeasePolicy.isCurrent",
        "guard stillCurrent || expiredSameAccount", "UserDefaults.standard.set",
        "signOut()", "ownerID = UUID().uuidString"),
    "the Privacy view schedules no unscoped delayed sign-out":
        "session.signOut()" not in delete_view and "Task.sleep" not in delete_view,
})

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(("PASS: " if ok else "FAIL: ") + name)
if failed:
    raise SystemExit(f"refresh account source contract: {len(failed)} failed")
print("refresh account source contract: all passed")
PY
