// Executes the real view entry/run methods with controlled network responses.
// It is not a SwiftUI rendering or real-account/provider test.
import Foundation

struct ToolkitMeta: Equatable, Sendable { let slug: String }
struct OwnerId: Equatable, Sendable {
    let raw: String
    init?(_ raw: String) { guard raw.count == 15 else { return nil }; self.raw = raw }
}
enum ConnectOnboardingPolicy { struct AppKey { let toolkit: String } }
enum Haptics { static func engage() {} }

@MainActor final class FlowAccount {
    var accountID = "aaaa111bbbb222c"
    var authToken = "synthetic-first-token"
    var isSignedIn = true
    struct Backend { let authToken: String }
    var backend: Backend { Backend(authToken: authToken) }
}

enum FixtureError: Error { case unavailable }
@MainActor final class ConnectedAppsClient {
    var permissions: [CheckedContinuation<[String], Error>?] = []
    var links: [CheckedContinuation<URL, Error>?] = []
    var descriptions: [CheckedContinuation<[ToolkitMeta], Error>?] = []
    func describe(toolkits: [String], owner: OwnerId) async throws -> [ToolkitMeta] {
        try await withCheckedThrowingContinuation { descriptions.append($0) }
    }
    func permissionSentences(toolkit: String, owner: OwnerId) async throws -> [String] {
        try await withCheckedThrowingContinuation { permissions.append($0) }
    }
    func connectLink(toolkit: String, owner: OwnerId, attemptID: String) async throws -> URL {
        try await withCheckedThrowingContinuation { links.append($0) }
    }
    func connectLink(toolkits: [String], owner: OwnerId, attemptID: String) async throws -> URL {
        try await withCheckedThrowingContinuation { links.append($0) }
    }
    func permission(_ index: Int, fails: Bool = false) {
        guard permissions.indices.contains(index), let pending = permissions[index] else { return }
        permissions[index] = nil
        if fails { pending.resume(throwing: FixtureError.unavailable) }
        else { pending.resume(returning: ["Read synthetic items."]) }
    }
    func link(_ index: Int, fails: Bool = false) {
        guard links.indices.contains(index), let pending = links[index] else { return }
        links[index] = nil
        if fails { pending.resume(throwing: FixtureError.unavailable) }
        else { pending.resume(returning: URL(string: "https://anticipy.ai/c/synthetic_\(index)")!) }
    }
    func drain() {
        for index in descriptions.indices { describe(index, fails: true) }
        for index in permissions.indices { permission(index, fails: true) }
        for index in links.indices { link(index, fails: true) }
    }
    func describe(_ index: Int, fails: Bool = false) {
        guard descriptions.indices.contains(index), let pending = descriptions[index] else { return }
        descriptions[index] = nil
        if fails { pending.resume(throwing: FixtureError.unavailable) }
        else { pending.resume(returning: [ToolkitMeta(slug: "synthetic")]) }
    }
}

@MainActor class FlowFixture {
    let session = FlowAccount()
    let client = ConnectedAppsClient()
    let connect = ConnectSession()
    var connecting: ConnectFlow?
    var connectQueue: [ToolkitMeta] = []
    var connectTrouble = false
    var connectSelectionID: UUID?
    enum Step { case connect, other }
    var step = Step.connect
    var advances = 0
    func connectedAppsClient() -> ConnectedAppsClient { client }
    func advance() async { advances += 1 }
    func background() { connect.appMovedToBackground() }
    func launch() { fatalError("fixture must call a real view entry") }
}
@MainActor final class SettingsFlowFixture: FlowFixture {
    override func background() { super.background(); connectMovedToBackground() }
    override func launch() { startConnect(ToolkitMeta(slug: "synthetic")) }
}
@MainActor final class OnboardingFlowFixture: FlowFixture {
    override func background() { super.background(); connectMovedToBackground() }
    func select() { startConnecting([ConnectOnboardingPolicy.AppKey(toolkit: "synthetic")]) }
    override func launch() {
        connectQueue = [ToolkitMeta(slug: "synthetic")]
        connectStepMovesOn()
    }
}

@main @MainActor private enum FlowSuite {
    static var checks = 0
    static var failures = 0
    static func check(_ label: String, _ value: Bool) {
        checks += 1
        if !value { failures += 1 }
        print("\(value ? "PASS" : "FAIL"): \(label)")
    }
    static func settle() async { for _ in 0..<100 { await Task.yield() } }
    static func close(_ fixture: FlowFixture) async {
        fixture.connecting = nil
        fixture.connect.ownerChanged()
        fixture.client.drain()
        await settle()
        fixture.client.drain()
        await settle()
    }
    static func main() async {
        for onboarding in [false, true] {
            func make() -> FlowFixture { onboarding ? OnboardingFlowFixture() : SettingsFlowFixture() }
            let prefix = onboarding ? "onboarding" : "settings"
            do {
                let f = make()
                f.launch(); await settle()
                let oldID = f.connecting?.id
                f.launch(); await settle()
                check("\(prefix): same-app retry has a distinct identity", f.connecting?.id != oldID)
                check("\(prefix): both permission requests reached fake boundary", f.client.permissions.count == 2)
                f.client.permission(1); await settle()
                let active = f.connect.prompt
                f.client.permission(0); await settle()
                check("\(prefix): old permissions cannot replace current prompt", f.connect.prompt == active)
                check("\(prefix): superseded permissions mint no extra link", f.client.links.count == 1)
                f.client.link(0); await settle()
                check("\(prefix): current flow still adopts its link", f.connect.prompt?.linkReady == true)
                await close(f)
            }
            for staleFails in [false, true] {
                let f = make()
                f.launch(); await settle(); f.client.permission(0); await settle()
                f.launch(); await settle(); f.client.permission(1); await settle()
                let active = f.connect.prompt
                check("\(prefix): both link requests reached fake boundary", f.client.links.count == 2)
                f.client.link(0, fails: staleFails); await settle()
                check("\(prefix): old link success/error cannot alter replacement", f.connect.prompt == active)
                check("\(prefix): old link success/error cannot mark replacement ready/trouble",
                      f.connect.prompt?.linkReady == false && f.connecting?.stage == .asking)
                f.client.link(1); await settle()
                check("\(prefix): replacement survives old link \(staleFails)", f.connect.prompt?.linkReady == true)
                await close(f)
            }

            // SOMETHING ELSE MOVED THE SHEET, AND IT WAS NOT THIS VIEW.
            //
            // `ConnectSession` is ONE object for the whole app — a single root
            // `@StateObject` — and the ROOT mutates it behind whichever surface
            // is on screen: `onOpenURL` hands a callback to it, and a scene
            // phase change tells it the app left the foreground. Neither of
            // those touches this view's `connecting` or its account lease, so
            // `connectFlowIsCurrent` still says yes while the sheet in front of
            // the owner is a different attempt entirely. The flow id is not the
            // sheet's identity and cannot stand in for it.
            //
            // The arm below uses `begin` because it is the tightest available
            // construction of that state, not because two surfaces are mounted
            // at once — `switch route` mounts onboarding or home, never both.
            //
            // Everything still in flight under the abandoned attempt has to
            // die there. A late link must not be adopted onto the newer sheet
            // (the owner would see "ready" for a link minted for a connect they
            // walked away from, and a tap would open it), and a late failure
            // must not clear the newer sheet or report itself as the newer
            // attempt's trouble.
            for staleFails in [false, true] {
                let f = make()
                f.launch(); await settle(); f.client.permission(0); await settle()
                let flowID = f.connecting?.id
                let abandoned = f.connect.prompt?.attemptID
                guard let newer = f.connect.begin(owner: f.session.accountID,
                                                  toolkit: "synthetic",
                                                  sentences: ["Read other synthetic items."]) else {
                    check("\(prefix): the shared session can be moved to another attempt", false)
                    await close(f)
                    continue
                }
                check("\(prefix): the sheet moved and the flow did not",
                      abandoned != nil && newer.attemptID != abandoned
                          && f.connecting?.id == flowID && f.connect.prompt?.linkReady == false
                          // Without this the two checks below would hold for a
                          // reason that has nothing to do with the guard: if
                          // runConnect ever stopped requesting a link, `link(0)`
                          // is a silent no-op and nothing happens either way.
                          && f.client.links.count == 1)
                f.client.link(0, fails: staleFails); await settle()
                let outcome = staleFails ? "failure" : "success"
                check("\(prefix): abandoned attempt's link \(outcome) cannot reach the newer sheet",
                      f.connect.prompt?.attemptID == newer.attemptID)
                check("\(prefix): abandoned attempt's link \(outcome) cannot ready or trouble the newer sheet",
                      f.connect.prompt?.linkReady == false && f.connecting?.stage == .asking)
                await close(f)
            }
            for atLink in [false, true] {
                for change in ["owner", "token", "signedOut", "dismiss", "background"] {
                    let f = make()
                    f.launch(); await settle()
                    if atLink { f.client.permission(0); await settle() }
                    switch change {
                    case "owner": f.session.accountID = "zzzz999yyyy888x"; f.connect.ownerChanged()
                    case "token": f.session.authToken = "synthetic-new-token"; f.connect.ownerChanged()
                    case "signedOut": f.session.isSignedIn = false; f.connect.ownerChanged()
                    case "background": f.background()
                    default: f.connecting = nil; f.connect.ownerChanged()
                    }
                    if atLink { f.client.link(0) } else { f.client.permission(0) }
                    await settle()
                    check("\(prefix): \(change) while \(atLink ? "link" : "permissions") pending cannot resurrect prompt",
                          f.connect.prompt == nil)
                    check("\(prefix): invalidated response creates no later request",
                          f.client.links.count == (atLink ? 1 : 0))
                    await close(f)
                }
            }
            do {
                let f = make()
                f.launch(); await settle(); f.client.permission(0); await settle()
                f.client.link(0); await settle()
                check("\(prefix): unchanged owner/flow gets ready", f.connect.prompt?.linkReady == true)
                await close(f)
            }
        }
        do {
            let f = OnboardingFlowFixture()
            f.select(); await settle()
            f.select(); await settle()
            check("catalog: both requests reached fake boundary", f.client.descriptions.count == 2)
            f.client.describe(1); await settle()
            let current = f.connecting?.id
            f.client.describe(0); await settle()
            check("catalog: old selection cannot replace the newer flow", f.connecting?.id == current)
            check("catalog: old selection cannot start another permission request", f.client.permissions.count == 1)
            await close(f)
        }
        for change in ["owner", "token", "signedOut", "step", "background", "staleError"] {
            let f = OnboardingFlowFixture()
            f.select(); await settle()
            switch change {
            case "owner": f.session.accountID = "zzzz999yyyy888x"
            case "token": f.session.authToken = "synthetic-new-token"
            case "signedOut": f.session.isSignedIn = false
            case "step": f.step = .other
            case "background": f.background()
            default:
                f.select(); await settle()
                f.client.describe(1); await settle()
            }
            let prior = f.connecting?.id
            f.client.describe(0, fails: change == "staleError"); await settle()
            check("catalog: \(change) cannot publish stale success/failure",
                  f.connecting?.id == prior && !f.connectTrouble)
            check("catalog: \(change) has no extra downstream request",
                  f.client.permissions.count == (change == "staleError" ? 1 : 0))
            await close(f)
        }
        print("connect flow actual-method: \(checks) checks, \(failures) failed (fake network only)")
        exit(failures == 0 ? 0 : 1)
    }
}
