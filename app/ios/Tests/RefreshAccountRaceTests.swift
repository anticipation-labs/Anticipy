import Foundation

private var failures = 0

private func check(_ name: String, _ ok: Bool, _ detail: String = "") {
    print("\(ok ? "PASS" : "FAIL"): \(name)\(ok || detail.isEmpty ? "" : "  -> \(detail)")")
    if !ok { failures += 1 }
}

/// A deliberately delayed account-A refresh. The four arrays stand for the
/// four owner-visible surfaces the real poll publishes after yielding:
/// jobs, event-derived feed state, notifications, and browser-agent state.
private actor DelayedRefreshHarness {
    struct Snapshot: Equatable {
        let jobs: [String]
        let events: [String]
        let notifications: [String]
        let agents: [String]
    }

    private var generation = 0
    private var accountID = "account-A"
    private var isSignedIn = true
    private var jobs = ["A-before"]
    private var events = ["A-before"]
    private var notifications = ["A-before"]
    private var agents = ["A-before"]

    func beginARefresh() -> RefreshAccountPolicy.Lease {
        generation += 1
        return .init(generation: generation, accountID: accountID)
    }

    func signOutThenSignInB() {
        // clearSignedInSurface invalidation
        generation += 1
        isSignedIn = false
        accountID = ""
        jobs = []
        events = []
        notifications = []
        agents = []

        // signIn invalidation, then B's own canonical surface
        generation += 1
        accountID = "account-B"
        isSignedIn = true
        jobs = ["B-job"]
        events = ["B-event"]
        notifications = ["B-notification"]
        agents = ["B-agent"]
    }

    func finishDelayedA(_ lease: RefreshAccountPolicy.Lease) async {
        // The continuation of an A network read. Sleeping makes the lifecycle
        // transition happen between request and response every run.
        try? await Task.sleep(nanoseconds: 100_000_000)
        guard RefreshAccountPolicy.isCurrent(
            lease,
            generation: generation,
            accountID: accountID,
            isSignedIn: isSignedIn) else { return }
        jobs = ["A-job-leak"]
        events = ["A-event-leak"]
        notifications = ["A-notification-leak"]
        agents = ["A-agent-leak"]
    }

    func snapshot() -> Snapshot {
        Snapshot(jobs: jobs, events: events,
                 notifications: notifications, agents: agents)
    }
}

/// Models the ordering that `Notifier.post` has to survive: clear runs while
/// notification-center add is suspended, then add finishes after the clear.
private actor DelayedNotificationHarness {
    private var generation = 0
    private var accountID = "account-A"
    private var isSignedIn = true
    private var installed = Set<String>()

    func beginA() -> RefreshAccountPolicy.Lease {
        generation += 1
        return .init(generation: generation, accountID: accountID)
    }

    func signOutAndClearThenSignInB() {
        generation += 1
        isSignedIn = false
        accountID = ""
        installed.removeAll()
        generation += 1
        accountID = "account-B"
        isSignedIn = true
    }

    func finishDelayedAdd(_ lease: RefreshAccountPolicy.Lease) async {
        try? await Task.sleep(nanoseconds: 100_000_000)
        let identifier = "anticipy-job-A-secret"
        installed.insert(identifier) // add completes after clear
        let current = RefreshAccountPolicy.isCurrent(
            lease, generation: generation, accountID: accountID,
            isSignedIn: isSignedIn)
        if NotificationLeasePolicy.removeAfterAdd(stillCurrent: current) {
            installed.remove(identifier)
        }
    }

    func installedIDs() -> Set<String> { installed }
}

/// Models Settings saves that return after their screen's owner has changed.
/// The server write remains correctly scoped to A by its snapped backend; the
/// lease protects the device-only mirrors that are now displaying B.
private actor DelayedProfileSaveHarness {
    struct Snapshot: Equatable {
        let phone: String
        let firstName: String
        let email: String
    }

    private var accountID = "account-A"
    private var authToken = "token-A"
    private var isSignedIn = true
    private var phone = "+16045550111"
    private var firstName = "Alice"
    private var email = "alice@example.com"

    func beginAWrite() -> AccountWriteLeasePolicy.Lease? {
        AccountWriteLeasePolicy.begin(
            accountID: accountID, authToken: authToken, isSignedIn: isSignedIn)
    }

    func signOutThenSignInB() {
        isSignedIn = false
        accountID = ""
        authToken = ""
        phone = ""
        firstName = ""
        email = ""
        accountID = "account-B"
        authToken = "token-B"
        isSignedIn = true
        phone = "+16045550222"
        firstName = "Bob"
        email = "bob@example.com"
    }

    func finishDelayedAPhone(_ lease: AccountWriteLeasePolicy.Lease) async {
        try? await Task.sleep(nanoseconds: 100_000_000)
        guard AccountWriteLeasePolicy.isCurrent(
            lease, accountID: accountID, authToken: authToken,
            isSignedIn: isSignedIn) else { return }
        phone = "+16045550999"
    }

    func finishDelayedADetails(_ lease: AccountWriteLeasePolicy.Lease) async {
        try? await Task.sleep(nanoseconds: 100_000_000)
        guard AccountWriteLeasePolicy.isCurrent(
            lease, accountID: accountID, authToken: authToken,
            isSignedIn: isSignedIn) else { return }
        firstName = "Alice late"
        email = "alice-late@example.com"
    }

    func snapshot() -> Snapshot {
        Snapshot(phone: phone, firstName: firstName, email: email)
    }
}

/// Destructive operations are even stricter: after A's server/browser request
/// yields, its continuation may remove A-stamped rows, but it may not wipe the
/// device, sign out B, publish an A notice, or rotate B's device identity.
private actor DelayedDestructiveHarness {
    struct Snapshot: Equatable {
        let accountID: String
        let authToken: String
        let signedIn: Bool
        let queuedOwners: [String]
        let notice: String
        let deviceID: String
        let signOuts: Int
    }

    private var accountID = "account-A"
    private var authToken = "token-A"
    private var isSignedIn = true
    private var queuedOwners = ["account-A", "account-B"]
    private var notice = ""
    private var deviceID = "device-original"
    private var signOuts = 0

    func beginA() -> AccountWriteLeasePolicy.Lease? {
        AccountWriteLeasePolicy.begin(
            accountID: accountID, authToken: authToken, isSignedIn: isSignedIn)
    }

    func signOutThenSignInB() {
        isSignedIn = false
        accountID = ""
        authToken = ""
        accountID = "account-B"
        authToken = "token-B"
        isSignedIn = true
    }

    func finishDelayedADelete(_ lease: AccountWriteLeasePolicy.Lease) async {
        try? await Task.sleep(nanoseconds: 100_000_000)
        // A's stamped rows may be removed after its server confirms deletion.
        queuedOwners.removeAll { $0 == lease.accountID }
        guard AccountWriteLeasePolicy.isCurrent(
            lease, accountID: accountID, authToken: authToken,
            isSignedIn: isSignedIn) else { return }
        queuedOwners.removeAll()
        signOuts += 1
        isSignedIn = false
        accountID = ""
        authToken = ""
    }

    func finishDelayedAForget(_ lease: AccountWriteLeasePolicy.Lease) async {
        try? await Task.sleep(nanoseconds: 100_000_000)
        guard AccountWriteLeasePolicy.isCurrent(
            lease, accountID: accountID, authToken: authToken,
            isSignedIn: isSignedIn) else { return }
        notice = "A was forgotten"
        signOuts += 1
        isSignedIn = false
        accountID = ""
        authToken = ""
        deviceID = "rotated-for-A"
    }

    func snapshot() -> Snapshot {
        Snapshot(accountID: accountID, authToken: authToken,
                 signedIn: isSignedIn, queuedOwners: queuedOwners,
                 notice: notice, deviceID: deviceID, signOuts: signOuts)
    }
}

@main
private enum RefreshAccountRaceTests {
    static func main() async {
        let valid = RefreshAccountPolicy.Lease(generation: 7, accountID: "A")
        check("a matching signed-in account accepts its own response",
              RefreshAccountPolicy.isCurrent(valid, generation: 7,
                                             accountID: "A", isSignedIn: true))
        check("sign-out invalidates a response even before generation changes",
              !RefreshAccountPolicy.isCurrent(valid, generation: 7,
                                              accountID: "A", isSignedIn: false))
        check("an account switch invalidates the old response",
              !RefreshAccountPolicy.isCurrent(valid, generation: 7,
                                              accountID: "B", isSignedIn: true))
        check("a newer same-account refresh invalidates the old response",
              !RefreshAccountPolicy.isCurrent(valid, generation: 8,
                                              accountID: "A", isSignedIn: true))

        let harness = DelayedRefreshHarness()
        let leaseA = await harness.beginARefresh()
        async let delayedA: Void = harness.finishDelayedA(leaseA)
        await harness.signOutThenSignInB()
        await delayedA

        let snapshot = await harness.snapshot()
        let expected = DelayedRefreshHarness.Snapshot(
            jobs: ["B-job"], events: ["B-event"],
            notifications: ["B-notification"], agents: ["B-agent"])
        check("delayed A response cannot overwrite B jobs/events/notifier/agent",
              snapshot == expected, "\(snapshot)")

        let notifications = DelayedNotificationHarness()
        let notificationLeaseA = await notifications.beginA()
        async let delayedAdd: Void = notifications.finishDelayedAdd(notificationLeaseA)
        await notifications.signOutAndClearThenSignInB()
        await delayedAdd
        check("an A notification added after sign-out clear is removed on completion",
              await notifications.installedIDs().isEmpty)

        let phoneSave = DelayedProfileSaveHarness()
        guard let phoneLeaseA = await phoneSave.beginAWrite() else {
            check("account A can begin a phone save", false)
            exit(1)
        }
        async let delayedPhone: Void = phoneSave.finishDelayedAPhone(phoneLeaseA)
        await phoneSave.signOutThenSignInB()
        await delayedPhone
        let b = DelayedProfileSaveHarness.Snapshot(
            phone: "+16045550222", firstName: "Bob", email: "bob@example.com")
        check("a delayed A phone save cannot repaint B's phone mirror",
              await phoneSave.snapshot() == b)

        let detailsSave = DelayedProfileSaveHarness()
        guard let detailsLeaseA = await detailsSave.beginAWrite() else {
            check("account A can begin a details save", false)
            exit(1)
        }
        async let delayedDetails: Void = detailsSave.finishDelayedADetails(detailsLeaseA)
        await detailsSave.signOutThenSignInB()
        await delayedDetails
        check("delayed A details cannot repaint B's identity mirrors",
              await detailsSave.snapshot() == b)

        let deletion = DelayedDestructiveHarness()
        guard let deletionLeaseA = await deletion.beginA() else { exit(1) }
        async let delayedDeletion: Void = deletion.finishDelayedADelete(deletionLeaseA)
        await deletion.signOutThenSignInB()
        await delayedDeletion
        let protectedB = DelayedDestructiveHarness.Snapshot(
            accountID: "account-B", authToken: "token-B", signedIn: true,
            queuedOwners: ["account-B"], notice: "",
            deviceID: "device-original", signOuts: 0)
        check("a delayed A deletion removes A rows but cannot wipe or sign out B",
              await deletion.snapshot() == protectedB)

        let forgetting = DelayedDestructiveHarness()
        guard let forgetLeaseA = await forgetting.beginA() else { exit(1) }
        async let delayedForget: Void = forgetting.finishDelayedAForget(forgetLeaseA)
        await forgetting.signOutThenSignInB()
        await delayedForget
        let untouchedB = DelayedDestructiveHarness.Snapshot(
            accountID: "account-B", authToken: "token-B", signedIn: true,
            queuedOwners: ["account-A", "account-B"], notice: "",
            deviceID: "device-original", signOuts: 0)
        check("a delayed A device-forget cannot sign out or rotate B",
              await forgetting.snapshot() == untouchedB)

        if failures > 0 {
            print("RefreshAccountRaceTests: \(failures) failed")
            exit(1)
        }
        print("RefreshAccountRaceTests: all passed")
    }
}
