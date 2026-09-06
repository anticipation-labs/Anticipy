// THE CONNECT HANDOFF — what the app will and will not do between the owner's
// tap and another company's sign-in page.
//
//   sh app/ios/Tests/run_connect_handoff_tests.sh
//
// Three of these legs are compliance, not taste:
//
//   * the presentation may never be an embedded web view. Google answers a
//     sign-in inside one with `disallowed_useragent` and the connect dies, so
//     the suite reads the production source itself and fails on either class
//     name appearing anywhere in it — the only form of that guarantee a
//     refactor cannot quietly delete;
//   * the disclosure is per ATTEMPT and spent on use, because the Workspace
//     policy asks for a real tap immediately before each connect flow and a
//     per-install flag is not that;
//   * the deep link is attacker-reachable — any web page can open
//     `anticipy://connected/...` — so a callback with no attempt in flight, or
//     for an app we did not start, or for an owner who is not the one signed
//     in, must never come back as `.connected`.
//
// And the one the whole feature is shaped around: every attempt belongs to the
// owner signed into THIS phone. `spike/two-hands/src/connections/contract.ts`
// states it — the user id is the owner ROW id, always, and never a name — after
// one operator's own mailbox was connected by hand during the spike.
//
// Plain executable, no XCTest, matching AnswerRoutePolicyTests.swift and
// CalendarHandPolicyTests.swift: it runs in a second with no simulator, no
// signing and no network.
import Foundation

var failures = 0
func check(_ name: String, _ ok: Bool) {
    print("\(ok ? "PASS" : "FAIL"): \(name)")
    if !ok { failures += 1 }
}

// ----------------------------------------------------------------- fixtures

/// Fifteen lowercase alphanumerics, the shape `ownerId()` in the server
/// contract enforces. Synthetic: a real owner id in a test file is one
/// copy-paste from being a constant in shipped code.
let OWNER = "aaaa111bbbb222c"
let SOMEONE_ELSE = "zzzz999yyyy888x"
/// What this phone's `ownerID` holds before there is an account at all.
let DEVICE_UUID = "8F4C1A20-6B44-4A1E-9D31-2C7E5F0A9B11"

let TOOLKIT = "notion"
let OTHER_TOOLKIT = "gmail"
/// An app nobody has written a line of Swift for. It must work identically —
/// that is the whole "no app is hardcoded" requirement, stated as a test.
let BRAND_NEW = "somethingnew7"

let ATTEMPT_ID = "3f9c2ad1-0b77-4e5a-9c11-77aa3b0e1d42"
let NOW = Date(timeIntervalSince1970: 1_788_000_000)
let LINK = URL(string: "https://anticipy.ai/c/tok_9f2CQ4bX")!

func u(_ raw: String) -> URL { URL(string: raw)! }

func attempt(owner: String = OWNER,
             toolkit: String = TOOLKIT,
             id: String = ATTEMPT_ID,
             at: Date = NOW) -> ConnectAttempt {
    ConnectAttempt(id: id, owner: owner, toolkit: toolkit, startedAt: at)!
}

/// A gate with the disclosure shown AND tapped for `a` — the only state from
/// which anything opens.
func satisfiedGate(_ a: ConnectAttempt, at: Date = NOW) -> DisclosureGate {
    var gate = DisclosureGate()
    gate.disclosureShown(for: a, now: at)
    gate.acknowledge(a, now: at)
    return gate
}

// =========================================================================
// 1. THE COMPLIANCE LEG: this file's own source names no embedded web view.
// =========================================================================

/// The scanner lives in the SUITE and not in the policy, for the obvious
/// reason: a policy carrying the names it forbids would fail its own check.
enum EmbeddedBrowserScan {
    /// Every way an in-app web view gets into an iOS file. Two class names and
    /// the two frameworks that carry them — an import is enough, because a file
    /// that has no business with either framework importing one is the change
    /// this leg exists to catch, whatever it went on to do with it.
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

// The scanner is checked against fixtures BEFORE it is pointed at the real
// file, so it cannot join the can't-fail tests this repo has found before: a
// scanner that matches nothing passes every source ever written.
check("the scanner passes a clean file",
      EmbeddedBrowserScan.problems(in: "enum X { static let y = 1 }").isEmpty)
for name in EmbeddedBrowserScan.banned {
    check("the scanner catches \(name)",
          !EmbeddedBrowserScan.problems(in: "let a = 1\n\(name)\nlet b = 2").isEmpty)
}
check("the scanner catches a class name buried in a comment",
      !EmbeddedBrowserScan.problems(in: "// we could just use a WKWebView here").isEmpty)

let args = CommandLine.arguments
guard args.count >= 2,
      let handoffSource = try? String(contentsOfFile: args[1], encoding: .utf8) else {
    FileHandle.standardError.write(Data("usage: connecthandofftests <ConnectHandoff.swift>\n".utf8))
    exit(2)
}

// An unreadable or renamed file must be loud. A source scan over an empty
// string is the purest can't-fail test there is.
check("the production source was found and is not empty",
      handoffSource.count > 2_000)
check("the file scanned is the handoff",
      handoffSource.contains("enum ConnectPresentation")
      && handoffSource.contains("struct DisclosureGate"))
check("it names the session it is allowed to use",
      handoffSource.contains("ASWebAuthenticationSession"))

for problem in EmbeddedBrowserScan.problems(in: handoffSource) {
    check("THE CONNECT WOULD FAIL: \(problem)", false)
}
check("the handoff names no embedded web view at all",
      EmbeddedBrowserScan.problems(in: handoffSource).isEmpty)

// NO APP IS HARDCODED. Names, logos and permission words come from the catalog
// at run time, so a slug in the decision layer is the wrong thing built.
for slug in ["gmail", "googlecalendar", "notion", "slack", "outlook", "dropbox"] {
    check("the handoff does not name \(slug)",
          !handoffSource.lowercased().contains("\"\(slug)\""))
}

// =========================================================================
// 2. WHOSE ATTEMPT IS THIS
// =========================================================================

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
      ConnectAttempt.begin(owner: OWNER, toolkit: "  Notion ", now: NOW)?.toolkit == "notion")
check("a real owner id is taken as it stands",
      ConnectAttempt.begin(owner: OWNER, toolkit: TOOLKIT, now: NOW)?.owner == OWNER)
check("two attempts do not share an id",
      ConnectAttempt.begin(owner: OWNER, toolkit: TOOLKIT, now: NOW)?.id
      != ConnectAttempt.begin(owner: OWNER, toolkit: TOOLKIT, now: NOW)?.id)
check("an attempt is fresh at ten minutes",
      attempt().isFresh(at: NOW.addingTimeInterval(600)))
check("an attempt is dead a second later",
      !attempt().isFresh(at: NOW.addingTimeInterval(601)))
check("an attempt is dead if the clock ran backwards",
      !attempt().isFresh(at: NOW.addingTimeInterval(-1)))

// =========================================================================
// 3. THE LINK IS OURS, OR IT DOES NOT OPEN
// =========================================================================

check("our own connect link is ours",
      ConnectHandoff.connectLinkIsOurs(url: LINK))
check("and it comes back with its token",
      ConnectHandoff.inspect(link: LINK) == .ours(token: "tok_9f2CQ4bX"))
check("the host is compared without case",
      ConnectHandoff.connectLinkIsOurs(url: u("https://ANTICIPY.AI/c/tok_9f2CQ4bX")))
check("a query on our own link does not disqualify it",
      ConnectHandoff.connectLinkIsOurs(url: u("https://anticipy.ai/c/tok_9f2CQ4bX?src=sms")))

// THE ONE THE SPEC'S FIRST RULE IS ABOUT. A raw provider link is what went
// into a text on 2026-09-05, and all four expired unused; the rule that came
// out of it is that every link is ours.
check("the provider's own connect link is refused",
      !ConnectHandoff.connectLinkIsOurs(
        url: u("https://connect.composio.dev/link/ca_BNgvxQtJ703C?next=1")))
check("and it is refused by name, so it can be reported",
      ConnectHandoff.inspect(link: u("https://connect.composio.dev/link/ca_BNgvxQtJ703C"))
      == .notOurs(.linkNotOurs))
check("a Google sign-in URL is refused",
      !ConnectHandoff.connectLinkIsOurs(
        url: u("https://accounts.google.com/o/oauth2/v2/auth?client_id=1&scope=email")))

check("a link in the clear is refused",
      !ConnectHandoff.connectLinkIsOurs(url: u("http://anticipy.ai/c/tok_9f2CQ4bX")))
check("a lookalike suffix host is refused",
      !ConnectHandoff.connectLinkIsOurs(url: u("https://anticipy.ai.example.net/c/tok_9f2CQ4bX")))
check("our host in somebody else's path is refused",
      !ConnectHandoff.connectLinkIsOurs(url: u("https://example.net/anticipy.ai/c/tok_9f2CQ4bX")))
check("a subdomain of ours is still not the connect host",
      !ConnectHandoff.connectLinkIsOurs(url: u("https://api.anticipy.ai/c/tok_9f2CQ4bX")))
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

// =========================================================================
// 4. THE DISCLOSURE, PER ATTEMPT AND SPENT ON USE
// =========================================================================

do {
    let a = attempt()
    var gate = DisclosureGate()
    check("a fresh gate presents nothing",
          !gate.canPresentConnect(a, now: NOW))
    check("and says the disclosure was never shown",
          gate.verdict(for: a, now: NOW) == .refused(.disclosureNotShown))

    check("a tap on a sheet that was never shown does not count",
          gate.acknowledge(a, now: NOW) == false)
    check("and the gate is unmoved by it",
          !gate.canPresentConnect(a, now: NOW))

    gate.disclosureShown(for: a, now: NOW)
    check("showing the sheet is not tapping it",
          !gate.canPresentConnect(a, now: NOW))
    check("and the gate says exactly that",
          gate.verdict(for: a, now: NOW) == .refused(.disclosureNotAcknowledged))

    check("a tap on the shown sheet counts",
          gate.acknowledge(a, now: NOW) == true)
    check("and only then may a connect be presented",
          gate.canPresentConnect(a, now: NOW))
}

do {
    // THE SECOND CONNECT NEEDS A SECOND TAP. This is the property a per-install
    // flag cannot have, and it is enforced by the handoff rather than by a view
    // remembering to reset anything: the acknowledgement is spent as the link
    // goes out.
    let first = attempt()
    var gate = satisfiedGate(first)
    let opened = ConnectHandoff.presentation(for: LINK, attempt: first, signedInOwner: OWNER,
                                             gate: &gate, now: NOW, authSessionAvailable: true)
    check("the first connect opens",
          opened == .authSession(url: LINK, callbackScheme: "anticipy"))
    check("and the acknowledgement is spent by opening it",
          !gate.canPresentConnect(first, now: NOW))
    check("a second connect on the same attempt is refused",
          ConnectHandoff.presentation(for: LINK, attempt: first, signedInOwner: OWNER,
                                      gate: &gate, now: NOW, authSessionAvailable: true)
          == .refused(.disclosureNotShown))

    let second = attempt(toolkit: TOOLKIT, id: "b17d0e6a-2c31-4d55-8f90-51ac9e2b7d10")
    check("and a fresh attempt for the same app is refused too",
          ConnectHandoff.presentation(for: LINK, attempt: second, signedInOwner: OWNER,
                                      gate: &gate, now: NOW, authSessionAvailable: true)
          == .refused(.disclosureNotShown))
    gate.disclosureShown(for: second, now: NOW)
    gate.acknowledge(second, now: NOW)
    check("until it is shown and tapped in its own right",
          ConnectHandoff.presentation(for: LINK, attempt: second, signedInOwner: OWNER,
                                      gate: &gate, now: NOW, authSessionAvailable: true)
          == .authSession(url: LINK, callbackScheme: "anticipy"))
}

do {
    // A tap on THIS app's sheet does not license THAT app's connect.
    let a = attempt()
    let other = attempt(toolkit: OTHER_TOOLKIT, id: "c98a1f04-77bd-4a2e-b3cc-0d5e8f1a2b34")
    var gate = satisfiedGate(a)
    check("an acknowledgement is for one attempt only",
          gate.verdict(for: other, now: NOW) == .refused(.disclosureIsForAnotherAttempt))
    check("a tap arriving for another attempt does not move the gate",
          gate.acknowledge(other, now: NOW) == false)
    check("and the first attempt is still the one that may present",
          gate.canPresentConnect(a, now: NOW))
}

do {
    // BACKGROUNDED. The disclosure is "immediately before"; an acknowledgement
    // found lying around after the app left the screen would let a connect
    // start that nobody watched begin.
    let a = attempt()
    var gate = satisfiedGate(a)
    gate.appMovedToBackground()
    check("an acknowledgement does not survive the app leaving the screen",
          !gate.canPresentConnect(a, now: NOW))
    check("and nothing opens on the way back",
          ConnectHandoff.presentation(for: LINK, attempt: a, signedInOwner: OWNER,
                                      gate: &gate, now: NOW, authSessionAvailable: true)
          == .refused(.disclosureNotShown))

    var shownOnly = DisclosureGate()
    shownOnly.disclosureShown(for: a, now: NOW)
    shownOnly.appMovedToBackground()
    check("a sheet that was on screen when the app left is gone too",
          shownOnly.verdict(for: a, now: NOW) == .refused(.disclosureNotShown))

    // And the order the view must use: spend, then open. Once spent, the
    // backgrounding that opening the browser causes has nothing left to clear,
    // which is why consuming the tap is inside `presentation` and not after it.
    var spent = satisfiedGate(a)
    _ = ConnectHandoff.presentation(for: LINK, attempt: a, signedInOwner: OWNER,
                                    gate: &spent, now: NOW, authSessionAvailable: false)
    let before = spent
    spent.appMovedToBackground()
    check("backgrounding after the link went out changes nothing",
          spent == before)
}

do {
    let a = attempt()
    let gate = satisfiedGate(a)
    check("an acknowledgement holds for two minutes",
          gate.canPresentConnect(a, now: NOW.addingTimeInterval(120)))
    check("and not for two minutes and one second",
          gate.verdict(for: a, now: NOW.addingTimeInterval(121)) == .refused(.disclosureIsStale))
    check("a clock that ran backwards does not revive it",
          gate.verdict(for: a, now: NOW.addingTimeInterval(-1)) == .refused(.disclosureIsStale))

    var slow = DisclosureGate()
    slow.disclosureShown(for: a, now: NOW)
    check("a tap on a sheet shown too long ago does not count",
          slow.acknowledge(a, now: NOW.addingTimeInterval(121)) == false)
    check("and that sheet still presents nothing",
          !slow.canPresentConnect(a, now: NOW.addingTimeInterval(121)))

    var handedOn = satisfiedGate(a)
    handedOn.ownerChanged()
    check("a change of owner clears the gate",
          !handedOn.canPresentConnect(a, now: NOW))
}

// =========================================================================
// 5. HOW IT OPENS — two ways, both of them a browser
// =========================================================================

do {
    let a = attempt()
    var gate = satisfiedGate(a)
    check("the preferred presentation is the system sign-in session",
          ConnectHandoff.presentation(for: LINK, attempt: a, signedInOwner: OWNER,
                                      gate: &gate, now: NOW, authSessionAvailable: true)
          == .authSession(url: LINK, callbackScheme: "anticipy"))

    var second = satisfiedGate(a)
    check("with no window to anchor on it is the system browser",
          ConnectHandoff.presentation(for: LINK, attempt: a, signedInOwner: OWNER,
                                      gate: &second, now: NOW, authSessionAvailable: false)
          == .systemBrowser(url: LINK))
}

do {
    // A provider link reaching the opener is refused in BOTH presentations,
    // and the tap that licensed the connect is not spent on it.
    let a = attempt()
    let vendor = u("https://connect.composio.dev/link/ca_BNgvxQtJ703C")
    for anchored in [true, false] {
        var gate = satisfiedGate(a)
        check("a provider link never opens (anchored: \(anchored))",
              ConnectHandoff.presentation(for: vendor, attempt: a, signedInOwner: OWNER,
                                          gate: &gate, now: NOW,
                                          authSessionAvailable: anchored)
              == .refused(.linkNotOurs))
        check("and a refusal does not spend the tap (anchored: \(anchored))",
              gate.canPresentConnect(a, now: NOW))
    }
}

do {
    let a = attempt()

    var gate = DisclosureGate()
    check("our own link does not open without the disclosure",
          ConnectHandoff.presentation(for: LINK, attempt: a, signedInOwner: OWNER,
                                      gate: &gate, now: NOW, authSessionAvailable: true)
          == .refused(.disclosureNotShown))

    var wrongPerson = satisfiedGate(a)
    check("an attempt does not open for the wrong signed-in owner",
          ConnectHandoff.presentation(for: LINK, attempt: a, signedInOwner: SOMEONE_ELSE,
                                      gate: &wrongPerson, now: NOW, authSessionAvailable: true)
          == .refused(.attemptIsForAnotherOwner))
    check("and the wrong person does not spend the right person's tap",
          wrongPerson.canPresentConnect(a, now: NOW))

    var signedOut = satisfiedGate(a)
    check("nothing opens for a device with no account",
          ConnectHandoff.presentation(for: LINK, attempt: a, signedInOwner: DEVICE_UUID,
                                      gate: &signedOut, now: NOW, authSessionAvailable: true)
          == .refused(.notAnOwnerId))

    var stale = satisfiedGate(a, at: NOW.addingTimeInterval(590))
    check("an attempt older than the link it belongs to does not open",
          ConnectHandoff.presentation(for: LINK, attempt: a, signedInOwner: OWNER,
                                      gate: &stale, now: NOW.addingTimeInterval(601),
                                      authSessionAvailable: true)
          == .refused(.attemptExpired))

    // ORDER. Who this is for is asked before what is being opened, so the
    // journal names the wrong-person failure rather than the link.
    var both = satisfiedGate(a)
    check("the owner is checked before the link",
          ConnectHandoff.presentation(for: u("https://connect.composio.dev/link/x"),
                                      attempt: a, signedInOwner: SOMEONE_ELSE,
                                      gate: &both, now: NOW, authSessionAvailable: true)
          == .refused(.attemptIsForAnotherOwner))
}

// =========================================================================
// 6. COMING BACK — the deep link is reachable by anyone
// =========================================================================

let a = attempt()

func done(_ raw: String,
          _ inFlight: ConnectAttempt? = a,
          owner: String = OWNER,
          now: Date = NOW.addingTimeInterval(30)) -> ConnectDone {
    ConnectHandoff.parseDone(url: u(raw), attempt: inFlight, signedInOwner: owner, now: now)
}

let callback = ConnectHandoff.callbackURL(for: a)
check("the callback is our own deep link for this app",
      callback?.absoluteString == "anticipy://connected/\(TOOLKIT)?state=\(ATTEMPT_ID)")
check("the callback carries no owner id to the other company",
      callback.map { !$0.absoluteString.contains(OWNER) } == true)

check("the ordinary return says which account was attached",
      done("anticipy://connected/\(TOOLKIT)?state=\(ATTEMPT_ID)&status=connected&connected_account_id=ca_BNgvxQtJ703C")
      == .connected(toolkit: TOOLKIT, accountId: "ca_BNgvxQtJ703C"))
check("a return that echoes no state is still read against the attempt",
      done("anticipy://connected/\(TOOLKIT)?status=connected&connected_account_id=ca_BNgvxQtJ703C")
      == .connected(toolkit: TOOLKIT, accountId: "ca_BNgvxQtJ703C"))
check("the scheme and host are compared without case",
      done("ANTICIPY://CONNECTED/\(TOOLKIT)?status=connected&connected_account_id=ca_1")
      == .connected(toolkit: TOOLKIT, accountId: "ca_1"))
check("the slug in the path is canonicalised before it is compared",
      done("anticipy://connected/NOTION?status=connected&connected_account_id=ca_1")
      == .connected(toolkit: TOOLKIT, accountId: "ca_1"))
check("backing out is its own answer",
      done("anticipy://connected/\(TOOLKIT)?status=cancelled") == .cancelled)
check("a failure carries its reason for the journal",
      done("anticipy://connected/\(TOOLKIT)?status=failed&reason=access_denied")
      == .failed(reason: "access_denied"))
check("a failure with nothing said is still a failure",
      done("anticipy://connected/\(TOOLKIT)?status=failed") == .failed(reason: "unspecified"))

// ---- the attacker-reachable half ---------------------------------------

check("a callback with nothing in flight marks nothing connected",
      done("anticipy://connected/\(TOOLKIT)?status=connected&connected_account_id=ca_1", nil)
      == .unreadable(.noAttemptInFlight))
check("a callback for an app we did not start is refused",
      done("anticipy://connected/\(OTHER_TOOLKIT)?status=connected&connected_account_id=ca_1")
      == .unreadable(.callbackToolkitMismatch))
check("a callback naming another attempt is refused",
      done("anticipy://connected/\(TOOLKIT)?state=someone-elses&status=connected&connected_account_id=ca_1")
      == .unreadable(.callbackIsForAnotherAttempt))
check("a callback landing after somebody else signed in is refused",
      done("anticipy://connected/\(TOOLKIT)?status=connected&connected_account_id=ca_1",
           owner: SOMEONE_ELSE)
      == .unreadable(.attemptIsForAnotherOwner))
check("a callback landing on a device with no account is refused",
      done("anticipy://connected/\(TOOLKIT)?status=connected&connected_account_id=ca_1",
           owner: DEVICE_UUID)
      == .unreadable(.notAnOwnerId))
check("a callback for an attempt that can no longer be alive is refused",
      done("anticipy://connected/\(TOOLKIT)?status=connected&connected_account_id=ca_1",
           now: NOW.addingTimeInterval(601))
      == .unreadable(.attemptExpired))
check("the widget's own doorbell is not a connect callback",
      done("anticipy://listen") == .unreadable(.callbackIsNotOurs))
check("somebody else's scheme is not our callback",
      done("https://connected/\(TOOLKIT)?status=connected&connected_account_id=ca_1")
      == .unreadable(.callbackIsNotOurs))
check("a callback naming no app is unreadable",
      done("anticipy://connected?status=connected&connected_account_id=ca_1")
      == .unreadable(.callbackShapeUnreadable))
check("a callback with more path than we mint is unreadable",
      done("anticipy://connected/\(TOOLKIT)/extra?status=connected&connected_account_id=ca_1")
      == .unreadable(.callbackShapeUnreadable))
check("a slug that is not slug-shaped is unreadable",
      done("anticipy://connected/no%20tion?status=connected&connected_account_id=ca_1")
      == .unreadable(.callbackShapeUnreadable))

// A repeated key is not a typo: `status=cancelled&status=connected` reads
// whichever way the reader happens to look. So it reads as neither.
check("a repeated status is unreadable rather than whichever comes first",
      done("anticipy://connected/\(TOOLKIT)?status=cancelled&status=connected&connected_account_id=ca_1")
      == .unreadable(.callbackShapeUnreadable))
check("a repeated account id is unreadable too",
      done("anticipy://connected/\(TOOLKIT)?status=connected&connected_account_id=ca_1&connected_account_id=ca_2")
      == .unreadable(.callbackShapeUnreadable))
check("a repeated state is unreadable too",
      done("anticipy://connected/\(TOOLKIT)?state=\(ATTEMPT_ID)&state=x&status=cancelled")
      == .unreadable(.callbackShapeUnreadable))

check("a status our own page never mints is unreadable",
      done("anticipy://connected/\(TOOLKIT)?status=pending") == .unreadable(.callbackStatusUnknown))
check("a callback with no status at all is unreadable",
      done("anticipy://connected/\(TOOLKIT)?connected_account_id=ca_1")
      == .unreadable(.callbackStatusUnknown))
check("connected with no account named is not connected",
      done("anticipy://connected/\(TOOLKIT)?status=connected")
      == .unreadable(.callbackAccountIdMissing))
check("connected with an empty account is not connected",
      done("anticipy://connected/\(TOOLKIT)?status=connected&connected_account_id=")
      == .unreadable(.callbackAccountIdMissing))
check("an account id we will not carry is not connected",
      done("anticipy://connected/\(TOOLKIT)?status=connected&connected_account_id=ca_1/../ca_2")
      == .unreadable(.callbackAccountIdUnusable))
check("an unbounded account id is not connected",
      done("anticipy://connected/\(TOOLKIT)?status=connected&connected_account_id="
           + String(repeating: "c", count: 129))
      == .unreadable(.callbackAccountIdUnusable))

// The round trip: what we hand over is what we can read back.
check("the callback we mint parses back to a connection",
      done(callback!.absoluteString + "&status=connected&connected_account_id=ca_BNgvxQtJ703C")
      == .connected(toolkit: TOOLKIT, accountId: "ca_BNgvxQtJ703C"))

// An app nobody wrote code for behaves identically, end to end.
do {
    let fresh = ConnectAttempt.begin(owner: OWNER, toolkit: BRAND_NEW, now: NOW, id: ATTEMPT_ID)!
    let back = ConnectHandoff.parseDone(
        url: u(ConnectHandoff.callbackURL(for: fresh)!.absoluteString
               + "&status=connected&connected_account_id=ca_ZZ9"),
        attempt: fresh, signedInOwner: OWNER, now: NOW)
    check("an app nobody hardcoded connects the same way",
          back == .connected(toolkit: BRAND_NEW, accountId: "ca_ZZ9"))
}

// =========================================================================
// 7. THE CENSUS
// =========================================================================

// Unlike CalendarHandPolicy.Refusal, no cause here carries an associated
// value, so this census is the COMPILER's and cannot go stale in silence. The
// literal below is the one thing a person must update, and the runner reads it.
let REFUSAL_CODES = 17
check("the census covers every cause the enum declares",
      ConnectRefusal.allCases.count == REFUSAL_CODES)
let codes = ConnectRefusal.allCases.map(\.code)
check("every refusal cause has its own code",
      Set(codes).count == codes.count)
check("every code is namespaced to the handoff",
      codes.allSatisfy { $0.hasPrefix("connect.") })

print(failures == 0 ? "all connect handoff checks passed" : "\(failures) FAILED")
exit(failures == 0 ? 0 : 1)
