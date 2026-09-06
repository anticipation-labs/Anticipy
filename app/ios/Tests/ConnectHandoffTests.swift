// THE CONNECT HANDOFF AND THE CONNECT SESSION — what the app will and will not
// do between the owner's tap and another company's sign-in page.
//
//   sh app/ios/Tests/run_connect_handoff_tests.sh
//
// Compiled against the REAL production sources: `ConnectHandoff.swift`, which
// decides, and `ConnectSession.swift`, which performs. There is no copy of
// either here to drift from what ships.
//
// Four of these legs are compliance, not taste:
//
//   * THE PRESENTATION MAY NEVER BE AN EMBEDDED WEB VIEW. Google answers a
//     sign-in inside `WKWebView` or `SFSafariViewController` with
//     `disallowed_useragent` and the connect dies. The scan reads the
//     production source for the class names — and since 2026-09-05 it reads
//     `ConnectSession.swift`, `AnticipyApp.swift` and every file under
//     `Views/` as well. It used to read exactly one file: `ConnectHandoff`,
//     the one file in the app that never opens a URL. A ban checked only
//     where nothing opens anything is a ban on nothing, so the scan now
//     covers the code that actually opens things and asserts, positively,
//     that it does.
//   * THE DISCLOSURE IS A REAL TAP, PER ATTEMPT, SPENT ON USE. The Workspace
//     policy asks for an affirmative action immediately before each connect
//     flow. Before 2026-09-05 `DisclosureGate` had ZERO CALLERS and would
//     accept `disclosureShown(); acknowledge()` in one function body with
//     nothing drawn. The sheet must now carry sentences from the catalog, the
//     tap must land after a floor measured on the session's own clock, and
//     the consent that licenses it is a one-shot handle no other file can
//     make.
//   * THE DEEP LINK IS ATTACKER-REACHABLE. Any web page can open
//     `anticipy://connected/...`, so a callback with no attempt in flight, for
//     an app we did not start, for another attempt, for another owner, or
//     carrying NO STATE AT ALL must never come back `.connected`.
//   * EVERY LINK IS OURS. Only `https://anticipy.ai/c/{token}` opens, and only
//     the one token this attempt adopted.
//
// And the one the whole feature is shaped around: every attempt belongs to the
// owner signed into THIS phone. `spike/two-hands/src/connections/contract.ts`
// states it — the user id is the owner ROW id, always, and never a name —
// after one operator's own mailbox was connected by hand during the spike.
//
// THE CONTROL IS AS IMPORTANT AS THE GUARD. A gate that refuses everything is
// an outage, so every tightening below is paired with the case that still has
// to work: the ordinary connect opens, once, at the right URL, in a real
// browser, and the ordinary callback comes back connected.
//
// Plain executable, no XCTest: it runs in a second with no simulator, no
// signing and no network.
import Foundation

private var failures = 0

@MainActor
private func check(_ name: String, _ ok: Bool, _ detail: String = "") {
    print("\(ok ? "PASS" : "FAIL"): \(name)\(ok || detail.isEmpty ? "" : "  -> \(detail)")")
    if !ok { failures += 1 }
}

// ----------------------------------------------------------------- fixtures

/// Fifteen lowercase alphanumerics, the shape `ownerId()` in the server
/// contract enforces. Synthetic: a real owner id in a test file is one
/// copy-paste from being a constant in shipped code.
private let OWNER = "aaaa111bbbb222c"
private let SOMEONE_ELSE = "zzzz999yyyy888x"
/// What this phone's `ownerID` holds before there is an account at all.
private let DEVICE_UUID = "8F4C1A20-6B44-4A1E-9D31-2C7E5F0A9B11"

/// INVENTED SLUGS. No real app is named anywhere in this suite, and the runner
/// refuses one in either production file: names, logos and permission words
/// come from the catalog at run time, so an app nobody wrote Swift for has to
/// behave identically.
private let TOOLKIT = "fernwood"
private let OTHER_TOOLKIT = "harbour"
private let BRAND_NEW = "quokka7"

private let ATTEMPT_ID = "3f9c2ad1-0b77-4e5a-9c11-77aa3b0e1d42"
private let NOW = Date(timeIntervalSince1970: 1_788_000_000)
private let LINK = URL(string: "https://anticipy.ai/c/tok_9f2CQ4bX")!
/// A second link of OURS — same shape, different token. This is the one that
/// separates "is it ours" from "is it THIS attempt's".
private let OTHER_LINK = URL(string: "https://anticipy.ai/c/tok_44kLmZ1p")!
private let VENDOR_LINK = URL(string: "https://connect.composio.dev/link/ca_BNgvxQtJ703C")!

/// What the catalog generated from this app's own scopes. Three plain
/// sentences; the words are the catalog's, never this file's.
private let SENTENCES = ["It can read your recent items.",
                         "It never posts anything.",
                         "You can disconnect it any time."]

private func u(_ raw: String) -> URL { URL(string: raw)! }

private func attempt(owner: String = OWNER,
                     toolkit: String = TOOLKIT,
                     id: String = ATTEMPT_ID,
                     at: Date = NOW,
                     link: URL? = LINK) -> ConnectAttempt {
    let made = ConnectAttempt(id: id, owner: owner, toolkit: toolkit, startedAt: at)!
    guard let link else { return made }
    guard case .bound(let bound) = made.binding(to: link) else { return made }
    return bound
}

/// A gate with the disclosure shown AND tapped for `a` — the only state from
/// which anything opens. The tap lands a beat after the sheet, because that is
/// the only kind of tap the gate now counts.
@MainActor
private func satisfiedGate(_ a: ConnectAttempt, at: Date = NOW) -> DisclosureGate {
    var gate = DisclosureGate()
    gate.disclosureShown(for: a, sentences: SENTENCES, now: at)
    gate.acknowledge(a, now: at.addingTimeInterval(1))
    return gate
}

// -------------------------------------------------------------- the scanner

/// The scanner lives in the SUITE and not in the policy, for the obvious
/// reason: a file carrying the names it forbids would fail its own check.
private enum EmbeddedBrowserScan {
    /// Every way an in-app web view gets into an iOS file. Two class names and
    /// the two frameworks that carry them — an import is enough, because a
    /// file that has no business with either framework importing one is the
    /// change this leg exists to catch, whatever it went on to do with it.
    static let banned = [
        "WKWebView",
        "UIWebView",
        "SFSafariViewController",
        "import WebKit",
        "import SafariServices",
    ]

    static func problems(in source: String) -> [String] {
        banned.compactMap { source.contains($0) ? "the source names \($0)" : nil }
    }
}

// -------------------------------------------------------------- the doubles

/// WHAT WOULD HAVE OPENED. The seam exists so the suite can prove which of the
/// two openings was chosen, and at which URL, without a browser appearing.
@MainActor
private final class FakeOpener: ConnectOpener {
    var authSessionAvailable = true
    private(set) var signInURLs: [URL] = []
    private(set) var signInSchemes: [String] = []
    private(set) var browserURLs: [URL] = []
    private var waiting: (@MainActor (ConnectCallback) -> Void)?

    var opens: Int { signInURLs.count + browserURLs.count }

    func openAuthSession(url: URL,
                         callbackScheme: String,
                         whenDone: @escaping @MainActor (ConnectCallback) -> Void) {
        signInURLs.append(url)
        signInSchemes.append(callbackScheme)
        waiting = whenDone
    }

    func openSystemBrowser(url: URL) { browserURLs.append(url) }

    /// The sign-in sheet answers.
    func answer(_ back: ConnectCallback) {
        let pending = waiting
        waiting = nil
        pending?(back)
    }
}

/// A clock the suite winds by hand, so the dwell floor and the ten-minute link
/// are exercised rather than waited for.
private final class Wound: @unchecked Sendable {
    var now: Date
    init(_ start: Date) { now = start }
    func tick(_ seconds: TimeInterval) { now = now.addingTimeInterval(seconds) }
}

/// Ids in mint order, so a test can name the attempt the session made.
private final class Mint: @unchecked Sendable {
    private var n = 0
    func next() -> String { n += 1; return "mint-\(n)" }
}

@main
@MainActor
private enum ConnectHandoffSuite {

    /// THE SUMMARY AND THE EXIT CODE LIVE HERE, NOT AT THE END OF `body`.
    ///
    /// `body` is full of `guard let … else { check(…, false); return }` — the
    /// honest way to stop a block whose fixture could not be built. Every one
    /// of those returns used to land past the summary line, so a mutation that
    /// broke a fixture printed eleven FAILs and then exited ZERO: a suite that
    /// reports failures and passes anyway. It was found by mutation-testing
    /// this suite rather than the code (2026-09-05), which is the only way that
    /// shape ever gets found.
    static func main() {
        body()
        print(failures == 0 ? "all connect handoff checks passed" : "\(failures) FAILED")
        exit(failures == 0 ? 0 : 1)
    }

    private static func body() {

        // =================================================================
        // 1. THE COMPLIANCE LEG: no embedded web view, anywhere that opens
        // =================================================================

        // The scanner is checked against fixtures BEFORE it is pointed at real
        // files, so it cannot join the can't-fail tests this repo has found
        // before: a scanner that matches nothing passes every source ever
        // written.
        check("the scanner passes a clean file",
              EmbeddedBrowserScan.problems(in: "enum X { static let y = 1 }").isEmpty)
        for name in EmbeddedBrowserScan.banned {
            check("the scanner catches \(name)",
                  !EmbeddedBrowserScan.problems(in: "let a = 1\n\(name)\nlet b = 2").isEmpty)
        }
        check("the scanner catches a class name buried in a comment",
              !EmbeddedBrowserScan.problems(in: "// we could just use a WKWebView here").isEmpty)

        let args = CommandLine.arguments
        guard args.count >= 2 else {
            FileHandle.standardError.write(
                Data("usage: connecthandofftests <app/ios/Anticipy>\n".utf8))
            exit(2)
        }
        let root = args[1]
        let handoffPath = root + "/Backend/ConnectHandoff.swift"
        let sessionPath = root + "/Backend/ConnectSession.swift"
        let appPath = root + "/AnticipyApp.swift"
        let viewsDir = root + "/Views"

        func read(_ path: String) -> String {
            guard let text = try? String(contentsOfFile: path, encoding: .utf8) else {
                FileHandle.standardError.write(Data("cannot read \(path)\n".utf8))
                exit(2)
            }
            return text
        }

        // EVERY FILE THAT COULD OPEN A URL, not the one file that cannot. The
        // list is built from the tree rather than typed, so a new view is
        // scanned the day it lands.
        var scanned: [(String, String)] = [
            ("ConnectHandoff.swift", read(handoffPath)),
            ("ConnectSession.swift", read(sessionPath)),
            ("AnticipyApp.swift", read(appPath)),
        ]
        let views = ((try? FileManager.default
            .subpathsOfDirectory(atPath: viewsDir)) ?? [])
            .filter { $0.hasSuffix(".swift") }
            .sorted()
        for view in views { scanned.append(("Views/" + view, read(viewsDir + "/" + view))) }

        // A scan over an empty list is the purest can't-fail test there is, so
        // the count is asserted before the content.
        check("the scan found the views to read", views.count >= 5,
              "\(views.count) files under Views/")
        check("the scan covers the handoff, the session and the app root",
              scanned.count == views.count + 3)
        for (name, source) in scanned {
            check("\(name) was found and is not empty", source.count > 200,
                  "\(source.count) bytes")
        }

        for (name, source) in scanned {
            for problem in EmbeddedBrowserScan.problems(in: source) {
                check("THE CONNECT WOULD FAIL: \(name) — \(problem)", false)
            }
        }
        check("no file that can open a URL names an embedded web view at all",
              scanned.allSatisfy { EmbeddedBrowserScan.problems(in: $0.1).isEmpty })

        // POSITIVE CONTROLS. A ban proves nothing over a file that opens
        // nothing, so each scanned file is also asked to be the thing it is
        // supposed to be.
        let handoffSource = scanned[0].1
        let sessionSource = scanned[1].1
        let appSource = scanned[2].1
        check("the file scanned as the handoff is the handoff",
              handoffSource.contains("enum ConnectPresentation")
              && handoffSource.contains("struct DisclosureGate"))
        check("the session really is what opens a sign-in",
              sessionSource.contains("ASWebAuthenticationSession"))
        check("the session really is what opens the system browser",
              sessionSource.contains("UIApplication.shared.open"))
        check("the app root really routes the connect callback",
              appSource.contains("ConnectHandoff.callbackHost")
              && appSource.contains("handleCallback"))

        // NO APP IS HARDCODED. Names, logos and permission words come from the
        // catalog at run time, so a slug in either layer is the wrong thing
        // built.
        for slug in ["gmail", "googlecalendar", "notion", "slack", "outlook", "dropbox"] {
            check("the handoff does not name \(slug)",
                  !handoffSource.lowercased().contains("\"\(slug)\""))
            check("the session does not name \(slug)",
                  !sessionSource.lowercased().contains("\"\(slug)\""))
        }

        // =================================================================
        // 2. WHOSE ATTEMPT IS THIS
        // =================================================================

        check("an attempt cannot be minted for a signed-out device",
              ConnectAttempt.begin(owner: DEVICE_UUID, toolkit: TOOLKIT, now: NOW) == nil)
        check("an attempt cannot be minted for nobody",
              ConnectAttempt.begin(owner: "", toolkit: TOOLKIT, now: NOW) == nil)
        check("an attempt cannot be minted for an email",
              ConnectAttempt.begin(owner: "jose@anticipy.ai", toolkit: TOOLKIT, now: NOW) == nil)
        check("an attempt cannot be minted for a display name",
              ConnectAttempt.begin(owner: "omar", toolkit: TOOLKIT, now: NOW) == nil)
        check("an attempt cannot be minted for an app we cannot name",
              ConnectAttempt.begin(owner: OWNER, toolkit: "  ", now: NOW) == nil)
        check("an attempt for an app nobody hardcoded is ordinary",
              ConnectAttempt.begin(owner: OWNER, toolkit: BRAND_NEW, now: NOW)?.toolkit == BRAND_NEW)
        check("the slug is canonicalised, not interpreted",
              ConnectAttempt.begin(owner: OWNER, toolkit: "  Fernwood ", now: NOW)?.toolkit == TOOLKIT)
        check("a real owner id is taken as it stands",
              ConnectAttempt.begin(owner: OWNER, toolkit: TOOLKIT, now: NOW)?.owner == OWNER)
        check("two attempts do not share an id",
              ConnectAttempt.begin(owner: OWNER, toolkit: TOOLKIT, now: NOW)?.id
              != ConnectAttempt.begin(owner: OWNER, toolkit: TOOLKIT, now: NOW)?.id)
        check("a new attempt has adopted no link at all",
              ConnectAttempt.begin(owner: OWNER, toolkit: TOOLKIT, now: NOW)?.token == nil)
        check("an attempt is fresh at ten minutes",
              attempt().isFresh(at: NOW.addingTimeInterval(600)))
        check("an attempt is dead a second later",
              !attempt().isFresh(at: NOW.addingTimeInterval(601)))
        check("an attempt is dead if the clock ran backwards",
              !attempt().isFresh(at: NOW.addingTimeInterval(-1)))

        // =================================================================
        // 3. THE LINK IS OURS, OR IT DOES NOT OPEN
        // =================================================================

        check("our own connect link is ours",
              ConnectHandoff.connectLinkIsOurs(url: LINK))
        check("and it comes back with its token",
              ConnectHandoff.inspect(link: LINK) == .ours(token: "tok_9f2CQ4bX"))
        check("the host is compared without case",
              ConnectHandoff.connectLinkIsOurs(url: u("https://ANTICIPY.AI/c/tok_9f2CQ4bX")))
        check("a query on our own link does not disqualify it",
              ConnectHandoff.connectLinkIsOurs(url: u("https://anticipy.ai/c/tok_9f2CQ4bX?src=sms")))

        // THE ONE THE SPEC'S FIRST RULE IS ABOUT. A raw provider link is what
        // went into a text on 2026-09-05, and all four expired unused; the
        // rule that came out of it is that every link is ours.
        check("the provider's own connect link is refused",
              !ConnectHandoff.connectLinkIsOurs(url: VENDOR_LINK))
        check("and it is refused by name, so it can be reported",
              ConnectHandoff.inspect(link: VENDOR_LINK) == .notOurs(.linkNotOurs))
        check("a Google sign-in URL is refused",
              !ConnectHandoff.connectLinkIsOurs(
                url: u("https://accounts.google.com/o/oauth2/v2/auth?client_id=1&scope=email")))

        check("a link in the clear is refused",
              !ConnectHandoff.connectLinkIsOurs(url: u("http://anticipy.ai/c/tok_9f2CQ4bX")))
        check("a lookalike suffix host is refused",
              !ConnectHandoff.connectLinkIsOurs(url: u("https://anticipy.ai.example.net/c/tok_9f2CQ4bX")))
        check("our host in somebody else's path is refused",
              !ConnectHandoff.connectLinkIsOurs(url: u("https://example.net/anticipy.ai/c/tok_9f2CQ4bX")))
        // api.anticipy.ai IS a connect host now — the Worker mints there, because
        // it is the only hostname routed to it. This leg used to say the
        // opposite, and the change is deliberate, measured, and narrow.
        check("the host the Worker actually mints on is ours",
              ConnectHandoff.connectLinkIsOurs(url: u("https://api.anticipy.ai/c/tok_9f2CQ4bX")))
        // AND EVERY OTHER SUBDOMAIN IS STILL REFUSED, which is the half that
        // was doing the work. The allowlist is exact hostnames, so widening it
        // by one name did not widen it to a pattern: a subdomain somebody else
        // can obtain — a stale CNAME, a marketing page, a takeover — must never
        // be able to carry a link that binds an account.
        check("any other subdomain of ours is still not a connect host",
              !ConnectHandoff.connectLinkIsOurs(url: u("https://cdn.anticipy.ai/c/tok_9f2CQ4bX")))
        check("nor a subdomain that merely looks like the real one",
              !ConnectHandoff.connectLinkIsOurs(url: u("https://api-anticipy.ai/c/tok_9f2CQ4bX")))
        check("nor one nested under the host we do allow",
              !ConnectHandoff.connectLinkIsOurs(url: u("https://x.api.anticipy.ai/c/tok_9f2CQ4bX")))
        check("credentials in the authority are refused",
              !ConnectHandoff.connectLinkIsOurs(url: u("https://a:b@anticipy.ai/c/tok_9f2CQ4bX")))
        check("a port we never mint is refused",
              !ConnectHandoff.connectLinkIsOurs(url: u("https://anticipy.ai:8443/c/tok_9f2CQ4bX")))
        check("another path on our own site is refused",
              !ConnectHandoff.connectLinkIsOurs(url: u("https://anticipy.ai/connect/tok_9f2CQ4bX")))
        check("a deeper path under /c/ is refused",
              !ConnectHandoff.connectLinkIsOurs(url: u("https://anticipy.ai/c/tok_9f2CQ4bX/go")))
        check("our own link with no token reads as ours-and-empty",
              ConnectHandoff.inspect(link: u("https://anticipy.ai/c/")) == .notOurs(.linkTokenMissing))
        check("a token carrying characters ours never do is refused",
              ConnectHandoff.inspect(link: u("https://anticipy.ai/c/tok_9f2$CQ4bX"))
              == .notOurs(.linkTokenMissing))
        check("our own deep link is not a connect link",
              !ConnectHandoff.connectLinkIsOurs(url: u("anticipy://connected/\(TOOLKIT)")))

        // ---- ours is not enough: it has to be THIS attempt's ---------------
        //
        // Every link we mint is shaped alike, so "is it ours" cannot tell one
        // owner's link from another's, or this app's from the next app's. The
        // attempt adopts exactly one token when the server answers, and only
        // that one opens under it. `inspect` used to extract the token and
        // throw it away.
        do {
            let bare = ConnectAttempt.begin(owner: OWNER, toolkit: TOOLKIT, now: NOW,
                                            id: ATTEMPT_ID)!
            guard case .bound(let bound) = bare.binding(to: LINK) else {
                check("an attempt adopts our link", false); return
            }
            check("an attempt adopts our link", bound.token == "tok_9f2CQ4bX")
            check("adopting changes nothing else about the attempt",
                  bound.id == bare.id && bound.owner == bare.owner
                  && bound.toolkit == bare.toolkit && bound.startedAt == bare.startedAt)
            check("adopting the same link twice is not a failure",
                  bound.binding(to: LINK) == .bound(bound))
            check("a second, different link of ours is refused",
                  bound.binding(to: OTHER_LINK) == .refused(.linkIsForAnotherAttempt))
            check("a provider link is refused as adoption too",
                  bare.binding(to: VENDOR_LINK) == .refused(.linkNotOurs))
            check("and the refusal leaves the attempt unbound",
                  bare.token == nil)
        }

        // =================================================================
        // 4. THE DISCLOSURE: sentences, a real tap, per attempt, spent on use
        // =================================================================

        do {
            let a = attempt()
            var gate = DisclosureGate()
            check("a fresh gate presents nothing",
                  !gate.canPresentConnect(a, now: NOW))
            check("and says the disclosure was never shown",
                  gate.verdict(for: a, now: NOW) == .refused(.disclosureNotShown))

            check("a tap on a sheet that was never shown does not count",
                  gate.acknowledge(a, now: NOW) == .refused(.disclosureNotShown))
            check("and the gate is unmoved by it",
                  !gate.canPresentConnect(a, now: NOW))

            gate.disclosureShown(for: a, sentences: SENTENCES, now: NOW)
            check("showing the sheet is not tapping it",
                  !gate.canPresentConnect(a, now: NOW))
            check("and the gate says exactly that",
                  gate.verdict(for: a, now: NOW) == .refused(.disclosureNotAcknowledged))

            check("a tap on the shown sheet counts",
                  gate.acknowledge(a, now: NOW.addingTimeInterval(1)) == .counted)
            check("and only then may a connect be presented",
                  gate.canPresentConnect(a, now: NOW.addingTimeInterval(1)))
        }

        do {
            // A BLANK SHEET IS NOT A DISCLOSURE. The sentences are generated
            // from the toolkit's own scopes, so a catalog that says nothing
            // about an app must stop the connect rather than produce a sheet
            // with nothing on it that somebody taps through.
            let a = attempt()
            var empty = DisclosureGate()
            check("a sheet with no sentences on it is refused",
                  empty.disclosureShown(for: a, sentences: [], now: NOW)
                  == .refused(.disclosureHadNothingToShow))
            check("and the gate holds nothing afterwards",
                  empty.verdict(for: a, now: NOW) == .refused(.disclosureNotShown))
            check("a tap on it cannot be recorded",
                  empty.acknowledge(a, now: NOW.addingTimeInterval(1))
                  == .refused(.disclosureNotShown))

            var blank = DisclosureGate()
            check("sentences that are only whitespace are no sentences",
                  blank.disclosureShown(for: a, sentences: ["  ", "\n"], now: NOW)
                  == .refused(.disclosureHadNothingToShow))

            // THE CONTROL: one real sentence among blanks is still a
            // disclosure. A guard that refuses everything is an outage.
            var mixed = DisclosureGate()
            check("one real sentence among blanks still shows",
                  mixed.disclosureShown(for: a, sentences: ["", SENTENCES[0]], now: NOW)
                  == .counted)
            check("and can be tapped",
                  mixed.acknowledge(a, now: NOW.addingTimeInterval(1)) == .counted)
        }

        do {
            // THE FLOOR UNDER THE WORD "TAP". The gate's old contract —
            // "`disclosureShown` was called" — is satisfied perfectly by two
            // calls in one function body with nothing drawn, and that is the
            // exact shape the in-context-disclosure requirement is about. A
            // synchronous fake takes no time; a person takes seconds.
            let a = attempt()
            var instant = DisclosureGate()
            instant.disclosureShown(for: a, sentences: SENTENCES, now: NOW)
            check("a tap in the same instant the sheet appeared is not a gesture",
                  instant.acknowledge(a, now: NOW) == .refused(.disclosureTapWasNotAGesture))
            check("and nothing may be presented on it",
                  !instant.canPresentConnect(a, now: NOW))

            var early = DisclosureGate()
            early.disclosureShown(for: a, sentences: SENTENCES, now: NOW)
            check("a tap just under the floor is not a gesture either",
                  early.acknowledge(a, now: NOW.addingTimeInterval(0.24))
                  == .refused(.disclosureTapWasNotAGesture))

            var backwards = DisclosureGate()
            backwards.disclosureShown(for: a, sentences: SENTENCES, now: NOW)
            check("a tap before the sheet appeared is not a gesture",
                  backwards.acknowledge(a, now: NOW.addingTimeInterval(-5))
                  == .refused(.disclosureTapWasNotAGesture))

            // THE CONTROL: a quarter of a second IS a tap. The floor is far
            // below anyone reading three sentences and reaching for a button.
            var real = DisclosureGate()
            real.disclosureShown(for: a, sentences: SENTENCES, now: NOW)
            check("a tap at the floor counts",
                  real.acknowledge(a, now: NOW.addingTimeInterval(0.25)) == .counted)
        }

        do {
            // THE SECOND CONNECT NEEDS A SECOND TAP. This is the property a
            // per-install flag cannot have, and it is enforced by the handoff
            // rather than by a view remembering to reset anything: the
            // acknowledgement is spent as the link goes out.
            let first = attempt()
            var gate = satisfiedGate(first)
            let opened = ConnectHandoff.presentation(for: LINK, attempt: first,
                                                     signedInOwner: OWNER, gate: &gate,
                                                     now: NOW.addingTimeInterval(2),
                                                     authSessionAvailable: true)
            check("the first connect opens",
                  opened == .authSession(url: LINK, callbackScheme: "anticipy"))
            check("and the acknowledgement is spent by opening it",
                  !gate.canPresentConnect(first, now: NOW.addingTimeInterval(2)))
            check("a second connect on the same attempt is refused",
                  ConnectHandoff.presentation(for: LINK, attempt: first, signedInOwner: OWNER,
                                              gate: &gate, now: NOW.addingTimeInterval(3),
                                              authSessionAvailable: true)
                  == .refused(.disclosureNotShown))

            let second = attempt(id: "b17d0e6a-2c31-4d55-8f90-51ac9e2b7d10")
            check("and a fresh attempt for the same app is refused too",
                  ConnectHandoff.presentation(for: LINK, attempt: second, signedInOwner: OWNER,
                                              gate: &gate, now: NOW.addingTimeInterval(3),
                                              authSessionAvailable: true)
                  == .refused(.disclosureNotShown))
            gate.disclosureShown(for: second, sentences: SENTENCES, now: NOW.addingTimeInterval(3))
            gate.acknowledge(second, now: NOW.addingTimeInterval(4))
            check("until it is shown and tapped in its own right",
                  ConnectHandoff.presentation(for: LINK, attempt: second, signedInOwner: OWNER,
                                              gate: &gate, now: NOW.addingTimeInterval(4),
                                              authSessionAvailable: true)
                  == .authSession(url: LINK, callbackScheme: "anticipy"))
        }

        do {
            // A tap on THIS app's sheet does not license THAT app's connect.
            let a = attempt()
            let other = attempt(toolkit: OTHER_TOOLKIT,
                                id: "c98a1f04-77bd-4a2e-b3cc-0d5e8f1a2b34")
            var gate = satisfiedGate(a)
            check("an acknowledgement is for one attempt only",
                  gate.verdict(for: other, now: NOW.addingTimeInterval(1))
                  == .refused(.disclosureIsForAnotherAttempt))
            check("a tap arriving for another attempt does not move the gate",
                  gate.acknowledge(other, now: NOW.addingTimeInterval(1))
                  == .refused(.disclosureNotShown))
            check("and the first attempt is still the one that may present",
                  gate.canPresentConnect(a, now: NOW.addingTimeInterval(1)))
        }

        do {
            // BACKGROUNDED. The disclosure is "immediately before"; an
            // acknowledgement found lying around after the app left the screen
            // would let a connect start that nobody watched begin.
            let a = attempt()
            var gate = satisfiedGate(a)
            gate.appMovedToBackground()
            check("an acknowledgement does not survive the app leaving the screen",
                  !gate.canPresentConnect(a, now: NOW.addingTimeInterval(1)))
            check("and nothing opens on the way back",
                  ConnectHandoff.presentation(for: LINK, attempt: a, signedInOwner: OWNER,
                                              gate: &gate, now: NOW.addingTimeInterval(1),
                                              authSessionAvailable: true)
                  == .refused(.disclosureNotShown))

            var shownOnly = DisclosureGate()
            shownOnly.disclosureShown(for: a, sentences: SENTENCES, now: NOW)
            shownOnly.appMovedToBackground()
            check("a sheet that was on screen when the app left is gone too",
                  shownOnly.verdict(for: a, now: NOW) == .refused(.disclosureNotShown))

            // And the order the view must use: spend, then open. Once spent,
            // the backgrounding that opening the browser causes has nothing
            // left to clear, which is why consuming the tap is inside
            // `presentation` and not after it.
            var spent = satisfiedGate(a)
            _ = ConnectHandoff.presentation(for: LINK, attempt: a, signedInOwner: OWNER,
                                            gate: &spent, now: NOW.addingTimeInterval(1),
                                            authSessionAvailable: false)
            let before = spent
            spent.appMovedToBackground()
            check("backgrounding after the link went out changes nothing",
                  spent == before)
        }

        do {
            let a = attempt()
            let gate = satisfiedGate(a)
            check("an acknowledgement holds for two minutes",
                  gate.canPresentConnect(a, now: NOW.addingTimeInterval(121)))
            check("and not for two minutes and one second past the tap",
                  gate.verdict(for: a, now: NOW.addingTimeInterval(122))
                  == .refused(.disclosureIsStale))
            check("a clock that ran backwards does not revive it",
                  gate.verdict(for: a, now: NOW.addingTimeInterval(-1))
                  == .refused(.disclosureIsStale))

            var slow = DisclosureGate()
            slow.disclosureShown(for: a, sentences: SENTENCES, now: NOW)
            check("a tap on a sheet shown too long ago does not count",
                  slow.acknowledge(a, now: NOW.addingTimeInterval(121))
                  == .refused(.disclosureIsStale))
            check("and that sheet still presents nothing",
                  !slow.canPresentConnect(a, now: NOW.addingTimeInterval(121)))

            var handedOn = satisfiedGate(a)
            handedOn.ownerChanged()
            check("a change of owner clears the gate",
                  !handedOn.canPresentConnect(a, now: NOW.addingTimeInterval(1)))
        }

        // =================================================================
        // 5. HOW IT OPENS — two ways, both of them a browser
        // =================================================================

        let ONE_LATER = NOW.addingTimeInterval(1)

        do {
            let a = attempt()
            var gate = satisfiedGate(a)
            check("the preferred presentation is the system sign-in session",
                  ConnectHandoff.presentation(for: LINK, attempt: a, signedInOwner: OWNER,
                                              gate: &gate, now: ONE_LATER,
                                              authSessionAvailable: true)
                  == .authSession(url: LINK, callbackScheme: "anticipy"))

            var second = satisfiedGate(a)
            check("with no window to anchor on it is the system browser",
                  ConnectHandoff.presentation(for: LINK, attempt: a, signedInOwner: OWNER,
                                              gate: &second, now: ONE_LATER,
                                              authSessionAvailable: false)
                  == .systemBrowser(url: LINK))
        }

        do {
            // A provider link reaching the opener is refused in BOTH
            // presentations, and the tap that licensed the connect is not
            // spent on it.
            let a = attempt()
            for anchored in [true, false] {
                var gate = satisfiedGate(a)
                check("a provider link never opens (anchored: \(anchored))",
                      ConnectHandoff.presentation(for: VENDOR_LINK, attempt: a,
                                                  signedInOwner: OWNER, gate: &gate,
                                                  now: ONE_LATER,
                                                  authSessionAvailable: anchored)
                      == .refused(.linkNotOurs))
                check("and a refusal does not spend the tap (anchored: \(anchored))",
                      gate.canPresentConnect(a, now: ONE_LATER))
            }
        }

        do {
            // THE LINK IS THIS ATTEMPT'S OR IT IS NOBODY'S. Both halves: an
            // attempt that never adopted a link has nothing to compare, and
            // nothing to compare is not a match; and a different link of OURS
            // is somebody else's, or another app's, or a second link where the
            // first was acknowledged.
            let unbound = attempt(link: nil)
            var gate = satisfiedGate(unbound)
            check("an attempt that adopted no link opens nothing",
                  ConnectHandoff.presentation(for: LINK, attempt: unbound,
                                              signedInOwner: OWNER, gate: &gate,
                                              now: ONE_LATER, authSessionAvailable: true)
                  == .refused(.linkNotBoundToAttempt))
            check("and that refusal does not spend the tap either",
                  gate.canPresentConnect(unbound, now: ONE_LATER))

            let bound = attempt()
            var other = satisfiedGate(bound)
            check("another link of ours does not open under this attempt",
                  ConnectHandoff.presentation(for: OTHER_LINK, attempt: bound,
                                              signedInOwner: OWNER, gate: &other,
                                              now: ONE_LATER, authSessionAvailable: true)
                  == .refused(.linkIsForAnotherAttempt))
            check("and the tap survives that too",
                  other.canPresentConnect(bound, now: ONE_LATER))
        }

        do {
            let a = attempt()

            var gate = DisclosureGate()
            check("our own link does not open without the disclosure",
                  ConnectHandoff.presentation(for: LINK, attempt: a, signedInOwner: OWNER,
                                              gate: &gate, now: ONE_LATER,
                                              authSessionAvailable: true)
                  == .refused(.disclosureNotShown))

            var wrongPerson = satisfiedGate(a)
            check("an attempt does not open for the wrong signed-in owner",
                  ConnectHandoff.presentation(for: LINK, attempt: a,
                                              signedInOwner: SOMEONE_ELSE, gate: &wrongPerson,
                                              now: ONE_LATER, authSessionAvailable: true)
                  == .refused(.attemptIsForAnotherOwner))
            check("and the wrong person does not spend the right person's tap",
                  wrongPerson.canPresentConnect(a, now: ONE_LATER))

            var signedOut = satisfiedGate(a)
            check("nothing opens for a device with no account",
                  ConnectHandoff.presentation(for: LINK, attempt: a,
                                              signedInOwner: DEVICE_UUID, gate: &signedOut,
                                              now: ONE_LATER, authSessionAvailable: true)
                  == .refused(.notAnOwnerId))

            var stale = satisfiedGate(a, at: NOW.addingTimeInterval(590))
            check("an attempt older than the link it belongs to does not open",
                  ConnectHandoff.presentation(for: LINK, attempt: a, signedInOwner: OWNER,
                                              gate: &stale, now: NOW.addingTimeInterval(601),
                                              authSessionAvailable: true)
                  == .refused(.attemptExpired))

            // ORDER. Who this is for is asked before what is being opened, so
            // the journal names the wrong-person failure rather than the link.
            var both = satisfiedGate(a)
            check("the owner is checked before the link",
                  ConnectHandoff.presentation(for: VENDOR_LINK, attempt: a,
                                              signedInOwner: SOMEONE_ELSE, gate: &both,
                                              now: ONE_LATER, authSessionAvailable: true)
                  == .refused(.attemptIsForAnotherOwner))
        }

        // =================================================================
        // 6. COMING BACK — the deep link is reachable by anyone
        // =================================================================

        let a = attempt()

        func done(_ raw: String,
                  _ inFlight: ConnectAttempt? = a,
                  owner: String = OWNER,
                  now: Date = NOW.addingTimeInterval(30)) -> ConnectDone {
            ConnectHandoff.parseDone(url: u(raw), attempt: inFlight,
                                     signedInOwner: owner, now: now)
        }

        let callback = ConnectHandoff.callbackURL(for: a)
        check("the callback is our own deep link for this app",
              callback?.absoluteString == "anticipy://connected/\(TOOLKIT)?state=\(ATTEMPT_ID)")
        check("the callback carries no owner id to the other company",
              callback.map { !$0.absoluteString.contains(OWNER) } == true)
        check("the callback carries no link token to the other company",
              callback.map { !$0.absoluteString.contains("tok_9f2CQ4bX") } == true)

        let state = "state=\(ATTEMPT_ID)"
        check("the ordinary return says which account was attached",
              done("anticipy://connected/\(TOOLKIT)?\(state)&status=connected&connected_account_id=ca_BNgvxQtJ703C")
              == .connected(toolkit: TOOLKIT, accountId: "ca_BNgvxQtJ703C"))
        check("the scheme and host are compared without case",
              done("ANTICIPY://CONNECTED/\(TOOLKIT)?\(state)&status=connected&connected_account_id=ca_1")
              == .connected(toolkit: TOOLKIT, accountId: "ca_1"))
        check("the slug in the path is canonicalised before it is compared",
              done("anticipy://connected/FERNWOOD?\(state)&status=connected&connected_account_id=ca_1")
              == .connected(toolkit: TOOLKIT, accountId: "ca_1"))
        check("backing out is its own answer",
              done("anticipy://connected/\(TOOLKIT)?\(state)&status=cancelled") == .cancelled)
        check("a failure carries its reason for the journal",
              done("anticipy://connected/\(TOOLKIT)?\(state)&status=failed&reason=access_denied")
              == .failed(reason: "access_denied"))
        check("a failure with nothing said is still a failure",
              done("anticipy://connected/\(TOOLKIT)?\(state)&status=failed")
              == .failed(reason: "unspecified"))

        // ---- THE HOLE THIS SECTION EXISTS FOR ----------------------------
        //
        // `state` was optional-when-absent until 2026-09-05. Every other check
        // on this URL is something a stranger's URL satisfies for free while a
        // connect is genuinely in flight: the app is signed in, the attempt is
        // fresh, and the path names the app the owner just tapped. So
        // `anticipy://connected/{toolkit}?status=connected&connected_account_id=…`
        // — openable by any web page, any other app, or a QR code on a poster
        // — came back `.connected` carrying an account id the stranger chose.
        // The attempt id is the one thing in this URL only our own page knows.
        check("a callback that echoes no state marks nothing connected",
              done("anticipy://connected/\(TOOLKIT)?status=connected&connected_account_id=ca_1")
              == .unreadable(.callbackStateMissing))
        check("and a stranger cannot back a connect out either",
              done("anticipy://connected/\(TOOLKIT)?status=cancelled")
              == .unreadable(.callbackStateMissing))
        check("nor fail one",
              done("anticipy://connected/\(TOOLKIT)?status=failed&reason=x")
              == .unreadable(.callbackStateMissing))
        check("an empty state is not a state",
              done("anticipy://connected/\(TOOLKIT)?state=&status=connected&connected_account_id=ca_1")
              == .unreadable(.callbackIsForAnotherAttempt))

        check("a callback with nothing in flight marks nothing connected",
              done("anticipy://connected/\(TOOLKIT)?\(state)&status=connected&connected_account_id=ca_1", nil)
              == .unreadable(.noAttemptInFlight))
        check("a callback for an app we did not start is refused",
              done("anticipy://connected/\(OTHER_TOOLKIT)?\(state)&status=connected&connected_account_id=ca_1")
              == .unreadable(.callbackToolkitMismatch))
        check("a callback naming another attempt is refused",
              done("anticipy://connected/\(TOOLKIT)?state=someone-elses&status=connected&connected_account_id=ca_1")
              == .unreadable(.callbackIsForAnotherAttempt))
        check("a callback landing after somebody else signed in is refused",
              done("anticipy://connected/\(TOOLKIT)?\(state)&status=connected&connected_account_id=ca_1",
                   owner: SOMEONE_ELSE)
              == .unreadable(.attemptIsForAnotherOwner))
        check("a callback landing on a device with no account is refused",
              done("anticipy://connected/\(TOOLKIT)?\(state)&status=connected&connected_account_id=ca_1",
                   owner: DEVICE_UUID)
              == .unreadable(.notAnOwnerId))
        check("a callback for an attempt that can no longer be alive is refused",
              done("anticipy://connected/\(TOOLKIT)?\(state)&status=connected&connected_account_id=ca_1",
                   now: NOW.addingTimeInterval(601))
              == .unreadable(.attemptExpired))
        check("the widget's own doorbell is not a connect callback",
              done("anticipy://listen") == .unreadable(.callbackIsNotOurs))
        check("somebody else's scheme is not our callback",
              done("https://connected/\(TOOLKIT)?\(state)&status=connected&connected_account_id=ca_1")
              == .unreadable(.callbackIsNotOurs))
        check("a callback naming no app is unreadable",
              done("anticipy://connected?\(state)&status=connected&connected_account_id=ca_1")
              == .unreadable(.callbackShapeUnreadable))
        check("a callback with more path than we mint is unreadable",
              done("anticipy://connected/\(TOOLKIT)/extra?\(state)&status=connected&connected_account_id=ca_1")
              == .unreadable(.callbackShapeUnreadable))
        check("a slug that is not slug-shaped is unreadable",
              done("anticipy://connected/no%20tion?\(state)&status=connected&connected_account_id=ca_1")
              == .unreadable(.callbackShapeUnreadable))

        // A repeated key is not a typo: `status=cancelled&status=connected`
        // reads whichever way the reader happens to look. So it reads as
        // neither.
        check("a repeated status is unreadable rather than whichever comes first",
              done("anticipy://connected/\(TOOLKIT)?\(state)&status=cancelled&status=connected&connected_account_id=ca_1")
              == .unreadable(.callbackShapeUnreadable))
        check("a repeated account id is unreadable too",
              done("anticipy://connected/\(TOOLKIT)?\(state)&status=connected&connected_account_id=ca_1&connected_account_id=ca_2")
              == .unreadable(.callbackShapeUnreadable))
        check("a repeated state is unreadable too",
              done("anticipy://connected/\(TOOLKIT)?\(state)&state=x&status=cancelled")
              == .unreadable(.callbackShapeUnreadable))

        check("a status our own page never mints is unreadable",
              done("anticipy://connected/\(TOOLKIT)?\(state)&status=pending")
              == .unreadable(.callbackStatusUnknown))
        check("a callback with no status at all is unreadable",
              done("anticipy://connected/\(TOOLKIT)?\(state)&connected_account_id=ca_1")
              == .unreadable(.callbackStatusUnknown))
        check("connected with no account named is not connected",
              done("anticipy://connected/\(TOOLKIT)?\(state)&status=connected")
              == .unreadable(.callbackAccountIdMissing))
        check("connected with an empty account is not connected",
              done("anticipy://connected/\(TOOLKIT)?\(state)&status=connected&connected_account_id=")
              == .unreadable(.callbackAccountIdMissing))
        check("an account id we will not carry is not connected",
              done("anticipy://connected/\(TOOLKIT)?\(state)&status=connected&connected_account_id=ca_1/../ca_2")
              == .unreadable(.callbackAccountIdUnusable))
        check("an unbounded account id is not connected",
              done("anticipy://connected/\(TOOLKIT)?\(state)&status=connected&connected_account_id="
                   + String(repeating: "c", count: 129))
              == .unreadable(.callbackAccountIdUnusable))

        // The round trip: what we hand over is what we can read back.
        check("the callback we mint parses back to a connection",
              done(callback!.absoluteString + "&status=connected&connected_account_id=ca_BNgvxQtJ703C")
              == .connected(toolkit: TOOLKIT, accountId: "ca_BNgvxQtJ703C"))

        // An app nobody wrote code for behaves identically, end to end.
        do {
            let fresh = ConnectAttempt.begin(owner: OWNER, toolkit: BRAND_NEW, now: NOW,
                                             id: ATTEMPT_ID)!
            let back = ConnectHandoff.parseDone(
                url: u(ConnectHandoff.callbackURL(for: fresh)!.absoluteString
                       + "&status=connected&connected_account_id=ca_ZZ9"),
                attempt: fresh, signedInOwner: OWNER, now: NOW)
            check("an app nobody hardcoded connects the same way",
                  back == .connected(toolkit: BRAND_NEW, accountId: "ca_ZZ9"))
        }

        // =================================================================
        // 7. THE SESSION — the part that actually opens something
        // =================================================================

        /// One session, its fake opener, its wound clock and its mint.
        func newSession() -> (ConnectSession, FakeOpener, Wound, Mint) {
            let clock = Wound(NOW)
            let mint = Mint()
            let opener = FakeOpener()
            let session = ConnectSession(opener: opener,
                                         clock: { clock.now },
                                         mintID: { mint.next() })
            return (session, opener, clock, mint)
        }

        /// Begun and holding our link, with the clock NOT moved: the sheet is
        /// up and the tap that follows lands in the same instant it appeared.
        func standing(_ session: ConnectSession,
                      toolkit: String = TOOLKIT) -> DisclosurePrompt? {
            guard session.begin(owner: OWNER, toolkit: toolkit,
                                sentences: SENTENCES) != nil else { return nil }
            session.adopt(link: LINK)
            return session.prompt
        }

        /// The whole happy path in one place, so every guard below has a
        /// control to be measured against: sheet up, link adopted, and a beat
        /// gone by so the tap is a tap.
        func connected(_ session: ConnectSession, _ clock: Wound,
                       toolkit: String = TOOLKIT) -> DisclosurePrompt? {
            guard let prompt = standing(session, toolkit: toolkit) else { return nil }
            clock.tick(2)
            return prompt
        }

        do {
            // THE CONTROL, FIRST. One tap, one open, at our link, in a real
            // browser, and the callback comes back connected.
            let (session, opener, clock, _) = newSession()
            guard let prompt = connected(session, clock) else {
                check("the ordinary connect begins", false); return
            }
            check("the ordinary connect begins", true)
            check("the sheet carries the catalog's sentences and nothing typed here",
                  prompt.sentences == SENTENCES)
            check("the sheet names the app by slug only",
                  prompt.toolkit == TOOLKIT)
            check("and says the link has arrived", session.prompt?.linkReady == true)

            check("the tap opens the system sign-in session",
                  session.ownerTapped(prompt.consent, signedInOwner: OWNER)
                  == .openedInSignInSession)
            check("exactly one thing opened", opener.opens == 1)
            check("and it was our link",
                  opener.signInURLs == [LINK])
            check("carrying our callback scheme",
                  opener.signInSchemes == [ConnectHandoff.callbackScheme])
            check("the sheet comes down as the link goes out", session.prompt == nil)

            let attemptID = prompt.attemptID
            opener.answer(.returned(u("anticipy://connected/\(TOOLKIT)?state=\(attemptID)"
                                      + "&status=connected&connected_account_id=ca_77")))
            check("the sign-in session's own answer is believed",
                  session.outcome == .connected(toolkit: TOOLKIT, accountId: "ca_77"))
        }

        do {
            // NOTHING OPENS WITHOUT A TAP, and there is no method that opens
            // something already acknowledged — acknowledging and opening are
            // one call so a view cannot do the first somewhere the second is
            // not watched.
            let (session, opener, clock, _) = newSession()
            guard let prompt = connected(session, clock) else {
                check("a connect begins", false); return
            }
            check("beginning a connect opens nothing at all", opener.opens == 0)

            let stale = prompt.consent
            // A NEW connect, sheet up, link in hand, tapped in the same
            // instant the sheet appeared. Nobody reads three sentences in no
            // time; a view calling both in one function body takes exactly
            // that long.
            guard let instant = standing(session) else {
                check("a second connect begins", false); return
            }
            check("a tap in the same instant the sheet appeared is refused",
                  session.ownerTapped(instant.consent, signedInOwner: OWNER)
                  == .refused(.disclosureTapWasNotAGesture))
            check("and nothing opened", opener.opens == 0)
            check("a consent from the abandoned first attempt licenses nothing",
                  session.ownerTapped(stale, signedInOwner: OWNER)
                  == .refused(.disclosureIsForAnotherAttempt))
            check("and still nothing opened", opener.opens == 0)
        }

        do {
            // THE SHEET SURVIVES A REFUSED TAP, with a NEW consent. A person
            // who tapped too fast gets to tap again; the handle they tapped
            // with is dead.
            let (session, opener, clock, _) = newSession()
            guard let first = standing(session) else {
                check("a connect begins", false); return
            }
            _ = session.ownerTapped(first.consent, signedInOwner: OWNER)
            check("the tap was refused for its own reason",
                  session.lastRefusal == ConnectRefusal.disclosureTapWasNotAGesture.code)
            guard let again = session.prompt else {
                check("the sheet is still up after a refused tap", false); return
            }
            check("the sheet is still up after a refused tap", true)
            check("with the same sentences", again.sentences == SENTENCES)
            check("and a consent the refused tap cannot be replayed with",
                  again.consent != first.consent)
            check("the old handle is refused",
                  session.ownerTapped(first.consent, signedInOwner: OWNER)
                  == .refused(.disclosureIsForAnotherAttempt))
            check("nothing opened on any of that", opener.opens == 0)

            clock.tick(2)
            check("and the second tap, after a beat, opens",
                  session.ownerTapped(again.consent, signedInOwner: OWNER)
                  == .openedInSignInSession)
            check("once", opener.opens == 1)
        }

        do {
            // ONE TAP, ONE OPEN. Tapping again after the browser opened must
            // not open a second one — and must not throw away the connect the
            // owner is in the middle of either, which is what abandoning the
            // attempt on any stray tap would hand an attacker.
            let (session, opener, clock, _) = newSession()
            guard let prompt = connected(session, clock) else {
                check("a connect begins", false); return
            }
            _ = session.ownerTapped(prompt.consent, signedInOwner: OWNER)
            check("the second tap on a spent consent opens nothing",
                  session.ownerTapped(prompt.consent, signedInOwner: OWNER)
                  == .refused(.disclosureNotShown))
            check("still exactly one open", opener.opens == 1)

            let attemptID = prompt.attemptID
            check("and the connect that was in flight still comes back",
                  session.handleCallback(
                    url: u("anticipy://connected/\(TOOLKIT)?state=\(attemptID)"
                           + "&status=connected&connected_account_id=ca_9"),
                    signedInOwner: OWNER)
                  == .connected(toolkit: TOOLKIT, accountId: "ca_9"))
        }

        do {
            // THE LINK IS NOT THERE YET. A tap while the server is still
            // minting is early, not wrong: the sheet stays up with the SAME
            // consent, so the owner taps again a moment later and it works.
            let (session, opener, clock, _) = newSession()
            guard let prompt = session.begin(owner: OWNER, toolkit: TOOLKIT,
                                             sentences: SENTENCES) else {
                check("a connect begins", false); return
            }
            check("the sheet says the link has not arrived", prompt.linkReady == false)
            clock.tick(2)
            check("a tap before the link arrives opens nothing",
                  session.ownerTapped(prompt.consent, signedInOwner: OWNER)
                  == .refused(.linkNotBoundToAttempt))
            check("nothing opened", opener.opens == 0)
            check("and the owner keeps their place",
                  session.prompt?.consent == prompt.consent)

            check("a provider link is refused as the attempt's link",
                  session.adopt(link: VENDOR_LINK) == false)
            check("reported by code", session.lastRefusal == ConnectRefusal.linkNotOurs.code)
            check("and a tap still opens nothing",
                  session.ownerTapped(prompt.consent, signedInOwner: OWNER)
                  == .refused(.linkNotBoundToAttempt))
            check("nothing opened on a provider link", opener.opens == 0)

            check("our own link is adopted", session.adopt(link: LINK) == true)
            check("and the same tap now opens",
                  session.ownerTapped(prompt.consent, signedInOwner: OWNER)
                  == .openedInSignInSession)
            check("at our link", opener.signInURLs == [LINK])
        }

        do {
            // NO WINDOW TO ANCHOR ON: Safari, never an embedded browser. The
            // callback then comes back through the deep link.
            let (session, opener, clock, _) = newSession()
            opener.authSessionAvailable = false
            guard let prompt = connected(session, clock) else {
                check("a connect begins", false); return
            }
            check("with nowhere to anchor a sheet it is the system browser",
                  session.ownerTapped(prompt.consent, signedInOwner: OWNER)
                  == .openedInSystemBrowser)
            check("at our link", opener.browserURLs == [LINK])
            check("and no sign-in session was started", opener.signInURLs.isEmpty)
        }

        do {
            // THE WRONG PERSON. Signed out, or somebody else signed in between
            // the sheet and the tap: nothing opens and the attempt is over.
            let (session, opener, clock, _) = newSession()
            guard let prompt = connected(session, clock) else {
                check("a connect begins", false); return
            }
            check("a tap after somebody else signed in opens nothing",
                  session.ownerTapped(prompt.consent, signedInOwner: SOMEONE_ELSE)
                  == .refused(.attemptIsForAnotherOwner))
            check("nothing opened", opener.opens == 0)
            check("and the attempt is gone rather than left for them",
                  session.prompt == nil)

            let (out, outOpener, outClock, _) = newSession()
            guard let second = connected(out, outClock) else {
                check("a second connect begins", false); return
            }
            check("a tap on a signed-out phone opens nothing",
                  out.ownerTapped(second.consent, signedInOwner: DEVICE_UUID)
                  == .refused(.notAnOwnerId))
            check("nothing opened", outOpener.opens == 0)

            check("a connect cannot even be begun on a signed-out phone",
                  out.begin(owner: DEVICE_UUID, toolkit: TOOLKIT, sentences: SENTENCES) == nil)
            check("and it is reported by code",
                  out.lastRefusal == ConnectRefusal.notAnOwnerId.code)
        }

        do {
            // WHAT THE CATALOG OWES THE SHEET. No sentences means no connect,
            // and an app the catalog named in a shape we cannot carry is a
            // defect upstream reported by code.
            let (session, opener, _, _) = newSession()
            check("a connect with no permission sentences does not begin",
                  session.begin(owner: OWNER, toolkit: TOOLKIT, sentences: []) == nil)
            check("and says a blank sheet is not a disclosure",
                  session.lastRefusal == ConnectRefusal.disclosureHadNothingToShow.code)
            check("a connect for an app the catalog could not name does not begin",
                  session.begin(owner: OWNER, toolkit: "  ", sentences: SENTENCES) == nil)
            check("and says so in its own code",
                  session.lastRefusal == ConnectRefusal.toolkitNotNamed.code)
            check("nothing opened on either", opener.opens == 0)

            // THE CONTROL: an app nobody wrote a line of Swift for connects
            // exactly the same way.
            let (fresh, freshOpener, freshClock, _) = newSession()
            guard let prompt = connected(fresh, freshClock, toolkit: BRAND_NEW) else {
                check("an app nobody hardcoded begins a connect", false); return
            }
            check("an app nobody hardcoded begins a connect", prompt.toolkit == BRAND_NEW)
            check("and opens the same way",
                  fresh.ownerTapped(prompt.consent, signedInOwner: OWNER)
                  == .openedInSignInSession)
            check("once", freshOpener.opens == 1)
        }

        do {
            // THE DEEP LINK IS A KNOCK ANYONE CAN MAKE, and an unreadable one
            // must change NOTHING: it may not publish an outcome, and it may
            // not cancel the connect the owner is in the middle of.
            let (session, opener, clock, _) = newSession()
            guard let prompt = connected(session, clock) else {
                check("a connect begins", false); return
            }
            _ = session.ownerTapped(prompt.consent, signedInOwner: OWNER)
            let attemptID = prompt.attemptID

            check("a stranger's callback with no state is unreadable",
                  session.handleCallback(
                    url: u("anticipy://connected/\(TOOLKIT)?status=connected&connected_account_id=ca_evil"),
                    signedInOwner: OWNER)
                  == .unreadable(.callbackStateMissing))
            check("and nothing is shown for it", session.outcome == nil)
            check("a stranger's cancel is unreadable too",
                  session.handleCallback(
                    url: u("anticipy://connected/\(TOOLKIT)?status=cancelled"),
                    signedInOwner: OWNER)
                  == .unreadable(.callbackStateMissing))
            check("and the owner's connect is still in flight", session.outcome == nil)

            check("the real callback still lands",
                  session.handleCallback(
                    url: u("anticipy://connected/\(TOOLKIT)?state=\(attemptID)"
                           + "&status=connected&connected_account_id=ca_real"),
                    signedInOwner: OWNER)
                  == .connected(toolkit: TOOLKIT, accountId: "ca_real"))
            check("and it is the account our own page named",
                  session.outcome == .connected(toolkit: TOOLKIT, accountId: "ca_real"))
            check("a replay of the same callback finds nothing in flight",
                  session.handleCallback(
                    url: u("anticipy://connected/\(TOOLKIT)?state=\(attemptID)"
                           + "&status=connected&connected_account_id=ca_real"),
                    signedInOwner: OWNER)
                  == .unreadable(.noAttemptInFlight))
            check("nothing opened on any callback", opener.opens == 1)
        }

        do {
            // BACKING OUT, from either road.
            let (session, _, clock, _) = newSession()
            guard let prompt = connected(session, clock) else {
                check("a connect begins", false); return
            }
            _ = session.ownerTapped(prompt.consent, signedInOwner: OWNER)
            session.handleCallback(
                url: u("anticipy://connected/\(TOOLKIT)?state=\(prompt.attemptID)&status=cancelled"),
                signedInOwner: OWNER)
            check("a cancel through the deep link is a cancel",
                  session.outcome == .cancelled)

            let (sheet, sheetOpener, sheetClock, _) = newSession()
            guard let second = connected(sheet, sheetClock) else {
                check("a second connect begins", false); return
            }
            _ = sheet.ownerTapped(second.consent, signedInOwner: OWNER)
            sheetOpener.answer(.dismissed)
            check("closing the sign-in sheet is a cancel and not a failure",
                  sheet.outcome == .cancelled)
        }

        do {
            // THE APP LEFT THE SCREEN WITH THE SHEET UP. "Immediately before"
            // is the whole requirement, so the attempt goes with it — and the
            // CONTROL is the other half: a connect already handed over is not
            // abandoned by the backgrounding that opening the browser causes.
            let (session, opener, clock, _) = newSession()
            guard let prompt = connected(session, clock) else {
                check("a connect begins", false); return
            }
            session.appMovedToBackground()
            check("the sheet is gone", session.prompt == nil)
            check("and the tap the owner was about to make licenses nothing",
                  session.ownerTapped(prompt.consent, signedInOwner: OWNER)
                  == .refused(.disclosureNotShown))
            check("nothing opened", opener.opens == 0)

            let (live, liveOpener, liveClock, _) = newSession()
            guard let open = connected(live, liveClock) else {
                check("a second connect begins", false); return
            }
            _ = live.ownerTapped(open.consent, signedInOwner: OWNER)
            live.appMovedToBackground()
            check("a connect already handed over survives the browser opening",
                  live.handleCallback(
                    url: u("anticipy://connected/\(TOOLKIT)?state=\(open.attemptID)"
                           + "&status=connected&connected_account_id=ca_5"),
                    signedInOwner: OWNER)
                  == .connected(toolkit: TOOLKIT, accountId: "ca_5"))
            check("and it opened exactly once", liveOpener.opens == 1)
        }

        do {
            // A SECOND CONNECT ABANDONS THE FIRST. Only one is ever in front
            // of the owner, and an attempt left behind is an attempt whose
            // callback would be believed later.
            let (session, _, clock, _) = newSession()
            guard let first = connected(session, clock) else {
                check("a connect begins", false); return
            }
            let firstID = first.attemptID
            guard let second = session.begin(owner: OWNER, toolkit: OTHER_TOOLKIT,
                                             sentences: SENTENCES) else {
                check("a second connect begins", false); return
            }
            check("the second sheet is for the second app", second.toolkit == OTHER_TOOLKIT)
            // AND IT DOES NOT INHERIT THE FIRST APP'S LINK. Overwriting the
            // attempt is not enough on its own: the adopted link is held
            // beside it, so a second connect that kept it would put a sheet up
            // saying the link had arrived when nothing had been minted for
            // this app at all — and the tap that followed would be refused
            // after the owner had already been told it was ready.
            check("and it has no link yet", second.linkReady == false)
            check("the first attempt's callback is no longer believed",
                  session.handleCallback(
                    url: u("anticipy://connected/\(TOOLKIT)?state=\(firstID)"
                           + "&status=connected&connected_account_id=ca_1"),
                    signedInOwner: OWNER)
                  == .unreadable(.callbackToolkitMismatch))
            check("and the first consent opens nothing",
                  session.ownerTapped(first.consent, signedInOwner: OWNER)
                  == .refused(.disclosureIsForAnotherAttempt))

            // A CHANGE OF OWNER TAKES EVERYTHING.
            session.ownerChanged()
            check("a change of owner clears the sheet", session.prompt == nil)
            check("and the standing consent",
                  session.ownerTapped(second.consent, signedInOwner: OWNER)
                  == .refused(.disclosureNotShown))
        }

        // =================================================================
        // 8. THE CENSUS
        // =================================================================

        // No cause here carries an associated value, so this census is the
        // COMPILER's and cannot go stale in silence. The literal below is the
        // one thing a person must update, and the runner reads it.
        let REFUSAL_CODES = 23
        check("the census covers every cause the enum declares",
              ConnectRefusal.allCases.count == REFUSAL_CODES,
              "\(ConnectRefusal.allCases.count)")
        let codes = ConnectRefusal.allCases.map(\.code)
        check("every refusal cause has its own code",
              Set(codes).count == codes.count)
        check("every code is namespaced to the handoff",
              codes.allSatisfy { $0.hasPrefix("connect.") })

    }
}
