// Runs the extracted, unmodified SystemConnectOpener class body against fake
// framework boundaries. This proves its retention/callback state machine,
// NOT Apple's presentation, cookie, callback-thread or device behavior.
import Foundation

@MainActor
private final class WeakSession {
    weak var value: ASWebAuthenticationSession?
    init(_ value: ASWebAuthenticationSession) { self.value = value }
}

@MainActor
private enum PlatformProbe {
    static var sessions: [WeakSession] = []
    static var completions: [(URL?, Error?) -> Void] = []
    static var starts = true
    static func reset() { sessions = []; completions = []; starts = true }
}

@MainActor
protocol ASWebAuthenticationPresentationContextProviding: AnyObject {
    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor
}
enum ASWebAuthenticationSessionError: Int { case canceledLogin = 1 }

@MainActor
final class ASWebAuthenticationSession {
    weak var presentationContextProvider: ASWebAuthenticationPresentationContextProviding?
    var prefersEphemeralWebBrowserSession = true
    init(url: URL, callbackURLScheme: String?,
         completionHandler: @escaping (URL?, Error?) -> Void) {
        PlatformProbe.sessions.append(WeakSession(self))
        PlatformProbe.completions.append(completionHandler)
    }
    func start() -> Bool { PlatformProbe.starts }
}

@MainActor class UIWindow: NSObject { var isKeyWindow = true }
typealias ASPresentationAnchor = UIWindow
enum SceneState { case foregroundActive, background }
@MainActor final class UIWindowScene: NSObject {
    var activationState = SceneState.foregroundActive
    var windows = [UIWindow()]
}
@MainActor final class UIApplication {
    static let shared = UIApplication()
    var connectedScenes: [AnyObject] = [UIWindowScene()]
    func open(_ url: URL, options: [String: String], completionHandler: ((Bool) -> Void)?) {}
}

@main @MainActor
private enum SystemConnectOpenerSuite {
    static var failures = 0
    static var checks = 0
    static func check(_ label: String, _ value: Bool) {
        checks += 1
        if !value { failures += 1 }
        print("\(value ? "PASS" : "FAIL"): \(label)")
    }
    // The actual body dispatches its completion onto MainActor. Await the
    // known callback task; bounded yields keep a broken callback from hanging.
    static func settle() async {
        for _ in 0..<20 { await Task.yield() }
    }
    static func main() async {
        let url = URL(string: "https://anticipy.ai/c/synthetic")!
        let done = URL(string: "anticipy://connected/synthetic?state=fixture")!
        let cancellation = NSError(domain: "synthetic", code: 1)
        for oldResult in 0..<3 {
            PlatformProbe.reset()
            let opener = SystemConnectOpener()
            var first: [ConnectCallback] = []
            var second: [ConnectCallback] = []
            opener.openAuthSession(url: url, callbackScheme: "anticipy") { first.append($0) }
            check("first sheet retained", PlatformProbe.sessions[0].value != nil)
            opener.openAuthSession(url: url, callbackScheme: "anticipy") { second.append($0) }
            check("replacement retained", PlatformProbe.sessions[1].value != nil)
            switch oldResult {
            case 0: PlatformProbe.completions[0](nil, cancellation)
            case 1: PlatformProbe.completions[0](nil, nil)
            default: PlatformProbe.completions[0](done, nil)
            }
            await settle()
            check("old completion \(oldResult) cannot release replacement",
                  PlatformProbe.sessions[1].value != nil)
            check("old completion \(oldResult) is not delivered", first.isEmpty && second.isEmpty)
            PlatformProbe.completions[1](done, nil)
            await settle()
            check("current completion is delivered once", second == [.returned(done)])
            check("current completion releases its own sheet", PlatformProbe.sessions[1].value == nil)
            PlatformProbe.completions[1](nil, cancellation)
            await settle()
            check("duplicate current completion is ignored", second == [.returned(done)])
        }
        PlatformProbe.reset()
        let opener = SystemConnectOpener()
        var outcomes: [ConnectCallback] = []
        PlatformProbe.starts = false
        opener.openAuthSession(url: url, callbackScheme: "anticipy") { outcomes.append($0) }
        check("failed start reports one actionable failure",
              outcomes == [.failed("auth_session_would_not_start")])
        check("failed start releases its sheet", PlatformProbe.sessions[0].value == nil)
        PlatformProbe.completions[0](nil, cancellation)
        await settle()
        check("late callback after failed start cannot report twice", outcomes.count == 1)
        PlatformProbe.starts = true
        opener.openAuthSession(url: url, callbackScheme: "anticipy") { outcomes.append($0) }
        PlatformProbe.completions[1](nil, cancellation)
        await settle()
        check("current dismissal remains a cancellation", outcomes.last == .dismissed && outcomes.count == 2)
        print("system opener actual-body: \(checks) checks, \(failures) failed (fake framework only)")
        exit(failures == 0 ? 0 : 1)
    }
}
