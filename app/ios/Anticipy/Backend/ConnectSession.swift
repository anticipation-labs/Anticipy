import Combine
import Foundation

// THE TWO FRAMEWORKS THIS FILE IS ALLOWED TO OPEN A URL WITH, and no others.
//
// `AuthenticationServices` carries `ASWebAuthenticationSession` — a real
// browser, in a sheet, that hands the callback straight back to us. `UIKit`
// carries `UIApplication.open`, which is Safari itself.
//
// The two embedded-browser frameworks are absent on purpose, and their
// absence is checked rather than assumed: Google answers a sign-in inside
// either of the in-app browser classes with `disallowed_useragent` and the
// connect fails outright, with no error the owner can act on.
// `ConnectHandoffTests` holds the list of banned names — this file may not
// even write them down — and reads this file, `ConnectHandoff.swift`,
// `AnticipyApp.swift` and every file under `Views/` for them. Until
// 2026-09-05 that scan covered exactly one file: `ConnectHandoff.swift`, the
// one file in the app that never opens a URL. A ban checked only where
// nothing opens anything is a ban on nothing.
//
// Both are `canImport`-guarded so the DECISIONS in this file compile and run
// on a laptop under `swiftc` with no simulator. The half that only exists on
// the phone is typechecked against the iOS SDK by the runner, because a
// platform block nothing compiles is a platform block nobody has read.
#if canImport(AuthenticationServices)
import AuthenticationServices
#endif
#if canImport(UIKit)
import UIKit
#endif

/// THE CONNECT, AS IT ACTUALLY HAPPENS ON THE PHONE.
///
/// `ConnectHandoff` decides; this performs. It is the only place in the app
/// that turns a `ConnectPresentation` into an opened browser, and the only
/// place that holds a `DisclosureGate`.
///
/// Spec: "Connections: how Anticipy asks, learns, and never says Composio",
/// 2026-09-05, pages 20-31. Server contract:
/// `spike/two-hands/src/connections/contract.ts`.
///
/// ── THE ORDER, AND WHY IT IS THIS ORDER ─────────────────────────────────
///
///   1. `begin(owner:toolkit:sentences:)` — mints ONE attempt for the owner
///      signed in right now, puts the disclosure up with the sentences the
///      catalog generated from that app's own scopes, and publishes a
///      `DisclosurePrompt` carrying a one-shot `ConnectConsent`.
///   2. `adopt(link:)` — the server answers with OUR single-use link and the
///      attempt adopts it. The link is minted at the tap, never before: four
///      links minted ahead of time on 2026-09-05 all expired unused, because
///      the provider's own link also dies in ten minutes.
///   3. `ownerTapped(_:signedInOwner:)` — THE REAL TAP, and the only thing in
///      this app that opens a connect link. Acknowledging and opening are one
///      call precisely so they cannot be separated: there is no method here
///      that opens something already acknowledged, so no view can acknowledge
///      in one place and open in another.
///   4. `handleCallback(url:signedInOwner:)` — the answer, whether it came
///      back through the sign-in session or through the deep link.
///
/// ── WHAT "A REAL TAP" CAN AND CANNOT BE PROVEN TO BE ────────────────────
///
/// Google's Workspace policy wants the owner told what will be read, in
/// context, with an affirmative action, immediately before the flow. Until
/// 2026-09-05 `DisclosureGate` accepted an acknowledgement whenever
/// `disclosureShown` had been called, and `DisclosureGate` had ZERO CALLERS —
/// so the shipped app had no disclosure at all, and the type that was supposed
/// to be one could be satisfied by two calls in one function body having drawn
/// nothing.
///
/// Four things now stand between those two, and each names a way the weak
/// version could be satisfied without a human:
///
///   * THE SHEET MUST HAVE HAD SENTENCES ON IT. They come from the toolkit's
///     own scopes through the catalog, so an app the catalog says nothing
///     about produces no connect rather than a blank sheet somebody taps
///     through.
///   * THE CONSENT IS A ONE-SHOT HANDLE THIS CLASS MINTS. `ConnectConsent`
///     has no initialiser reachable from another file; the only one in
///     existence arrives on the published prompt, is bound to one attempt id,
///     and is spent the moment it is used. A second connect needs a second
///     one.
///   * THE CLOCK IS OURS. Both the moment the sheet went up and the moment
///     the tap arrived are stamped from this class's own clock, so a caller
///     cannot supply the interval; the tap must land at least
///     `DisclosureGate.minimumDwell` after the sheet, and a synchronous fake
///     takes no time at all.
///   * THE GATE IS PRIVATE, and the runner refuses any other production file
///     that constructs a `DisclosureGate` or calls `acknowledge`.
///
/// WHAT IS STILL NOT PROVEN, said out loud rather than implied: no code can
/// see pixels. A view that draws nothing, waits a third of a second and calls
/// `ownerTapped` would pass. What the four rules above buy is that every
/// cheap way to skip the disclosure is closed, that skipping it now takes
/// deliberate work in a file the runner watches, and that the sentences the
/// owner is owed exist and came from the catalog. The screen that draws them
/// is `Views/`, and its own suite owns whether they are on it.
///
/// ── THE WRONG-PERSON RULE ───────────────────────────────────────────────
///
/// Every entry point takes the CURRENTLY signed-in owner as an argument and
/// hands it to the handoff, which refuses when the attempt was minted for
/// somebody else. Nothing here caches an owner and trusts it later. During the
/// spike one operator's own mailbox was connected by hand; it was revoked and
/// deleted, and `contract.ts` carries the rule it produced.
@MainActor
final class ConnectSession: ObservableObject {

    // MARK: - What the screen sees

    /// The disclosure to draw, or nil when nothing is being asked. Nil is also
    /// what the screen gets the instant the browser opens: the sheet's job is
    /// done and the acknowledgement it carried is spent.
    @Published private(set) var prompt: DisclosurePrompt?

    /// What the connect ended as, once it ended. `.connected` is a HINT and
    /// not a record — the caller refreshes this owner's connections from the
    /// server and believes that. Nothing arriving through a URL writes a row.
    @Published private(set) var outcome: ConnectOutcome?

    /// The last refusal's journal code, for the diagnostics screen. It is a
    /// CODE and never a sentence: a refusal token may name the other company
    /// or its sign-in protocol, and the spec forbids the owner ever seeing
    /// those words. The screen writes its own sentence.
    @Published private(set) var lastRefusal: String?

    // MARK: - What nobody else may touch

    /// THE ONLY DISCLOSURE GATE IN THE APP. Private, because the two calls
    /// that satisfy it must not be reachable from a view: a view that could
    /// call both in one function body would be back to the version that had
    /// no disclosure in it at all.
    private var gate = DisclosureGate()

    /// The one connect in flight, if any.
    private var attempt: ConnectAttempt?

    /// The link the attempt adopted. Held beside the attempt, which keeps only
    /// the token: the handoff compares the two, so opening a link this attempt
    /// never fetched is a refusal rather than a silent success.
    private var adoptedLink: URL?

    /// What was drawn, kept so a refused tap can put the same sheet back up
    /// with a fresh consent instead of losing the owner's place.
    private var sentences: [String] = []

    /// The consent that has been minted and not yet spent.
    private var pendingConsent: ConnectConsent?

    private let opener: ConnectOpener
    private let clock: () -> Date
    private let mintID: () -> String

    /// `opener` defaults to nil rather than to `systemOpener()` because a
    /// default argument is evaluated outside the initialiser's actor and the
    /// real opener is main-actor work. Nil means "the one this platform has".
    init(opener: ConnectOpener? = nil,
         clock: @escaping () -> Date = Date.init,
         mintID: @escaping () -> String = { UUID().uuidString }) {
        self.opener = opener ?? ConnectSession.systemOpener()
        self.clock = clock
        self.mintID = mintID
    }

    /// The real opener on a phone; a refusing stub anywhere else. The stub can
    /// never ship: the iOS build has UIKit by definition, so the `#else` half
    /// exists only so this class's decisions can be run under `swiftc` on a
    /// laptop.
    static func systemOpener() -> ConnectOpener {
        #if canImport(UIKit) && canImport(AuthenticationServices)
        return SystemConnectOpener()
        #else
        return NoConnectOpener()
        #endif
    }

    // MARK: - 1. Ask

    /// Put the disclosure up for ONE app, for the owner signed in right now.
    ///
    /// Returns nil, and publishes the code, when nothing may be asked: the
    /// identity on this phone is not an owner row id (a signed-out device
    /// cannot begin a connect at all), the catalog named the app in a shape we
    /// cannot carry, or the catalog produced no permission sentences — and a
    /// blank disclosure is not a disclosure.
    ///
    /// Beginning a second connect abandons the first. Only one connect is ever
    /// in front of the owner, and an attempt left behind is an attempt whose
    /// callback would be believed later.
    @discardableResult
    func begin(owner signedInOwner: String,
               toolkit: String,
               sentences: [String]) -> DisclosurePrompt? {
        abandon()
        guard let owner = ConnectHandoff.ownerRef(signedInOwner) else {
            return refuseToAsk(.notAnOwnerId)
        }
        guard let slug = ConnectHandoff.toolkitSlug(toolkit) else {
            return refuseToAsk(.toolkitNotNamed)
        }
        let now = clock()
        guard let started = ConnectAttempt.begin(owner: owner, toolkit: slug,
                                                 now: now, id: mintID()) else {
            // Both fields were canonicalised a line ago, so the only way left
            // to fail is an id this class minted badly. It is still checked:
            // an attempt that could not be built must not become a connect
            // that opens without one.
            return refuseToAsk(.notAnOwnerId)
        }
        if case .refused(let why) = gate.disclosureShown(for: started,
                                                         sentences: sentences,
                                                         now: now) {
            return refuseToAsk(why)
        }
        attempt = started
        self.sentences = sentences.filter {
            !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
        outcome = nil
        lastRefusal = nil
        return publishPrompt()
    }

    // MARK: - 2. Adopt the link

    /// OUR link — `https://anticipy.ai/c/{token}` — has arrived. The attempt
    /// adopts it, and from here only that one link opens under it.
    ///
    /// A provider's own link reaching this point is a defect upstream: the
    /// spec's first rule is that we own the ask, and a raw provider link went
    /// into a text once already. It is refused and reported by code rather
    /// than opened.
    @discardableResult
    func adopt(link: URL) -> Bool {
        guard let started = attempt else {
            lastRefusal = ConnectRefusal.noAttemptInFlight.code
            return false
        }
        switch started.binding(to: link) {
        case .refused(let why):
            lastRefusal = why.code
            return false
        case .bound(let bound):
            attempt = bound
            adoptedLink = link
            // The same sheet, now with a link behind it. The consent is NOT
            // re-minted and the sheet's timestamp is NOT re-stamped: the owner
            // is looking at the sheet they were already looking at, and
            // re-stamping would make the dwell floor measure the network
            // instead of the person.
            publishPrompt(consent: pendingConsent)
            return true
        }
    }

    // MARK: - 3. The tap

    /// THE OWNER TAPPED THE AFFIRMATIVE CONTROL. This is the only method in
    /// the app that opens a connect link.
    ///
    /// `signedInOwner` is read again HERE rather than trusted from `begin`,
    /// because a sign-out can happen between the two and an attempt that
    /// outlived one is dead.
    @discardableResult
    func ownerTapped(_ consent: ConnectConsent,
                     signedInOwner: String) -> ConnectOpening {
        // NOTHING TO TAP, AND NOTHING TAKEN AWAY EITHER. A tap arriving with
        // no sheet up is refused where it stands: the usual cause is a second
        // tap after the browser already opened, and abandoning the attempt
        // there would throw away the connect the owner is in the middle of —
        // a way to cancel somebody's connect by tapping twice.
        guard let started = attempt, let pending = pendingConsent else {
            return refuseToOpen(.disclosureNotShown, then: .leaveAlone)
        }
        // A handle that is not the one standing. Not re-armed: re-arming on an
        // unrecognised consent would let anything holding a stale handle reset
        // the owner's sheet under them.
        guard consent == pending, consent.attemptID == started.id else {
            return refuseToOpen(.disclosureIsForAnotherAttempt, then: .leaveAlone)
        }
        // THE LINK FIRST, AND THE CONSENT NOT YET SPENT. A tap that lands
        // while the server is still minting the link is early, not wrong: the
        // sheet stays up with the same consent and the same timestamp, so the
        // owner taps again a moment later and it works. Spending the consent
        // here would make a slow network cost a person their place.
        guard let link = adoptedLink else {
            lastRefusal = ConnectRefusal.linkNotBoundToAttempt.code
            return .refused(.linkNotBoundToAttempt)
        }
        // FROM HERE THE HANDLE IS DEAD, and it is not cleared on this line.
        // Every path below ends in exactly one of `handedOver`,
        // `sameSheetFreshConsent` (which mints a new one) or `abandon`, and
        // all three clear it — so a `pendingConsent = nil` here is a statement
        // no test can distinguish. It was written, mutation-tested on
        // 2026-09-05, found to change nothing, and removed rather than left as
        // an untested line that reads like a guarantee. What IS load-bearing
        // is the check above: mutating the consent comparison away turns three
        // cases red.
        let now = clock()
        if case .refused(let why) = gate.acknowledge(started, now: now) {
            return refuseToOpen(why, then: .sameSheetFreshConsent)
        }
        // `gate` goes in as `inout`: the handoff SPENDS the acknowledgement on
        // its way out, before the URL leaves, so whatever happens next — the
        // app backgrounds, the sheet is dismissed, the owner comes back an
        // hour later — the next connect starts from no acknowledgement at all.
        let decision = ConnectHandoff.presentation(for: link,
                                                   attempt: started,
                                                   signedInOwner: signedInOwner,
                                                   gate: &gate,
                                                   now: now,
                                                   authSessionAvailable: opener.authSessionAvailable)
        switch decision {
        case .authSession(let url, let scheme):
            // Preferred: the callback comes back to us directly, so a connect
            // that finishes while the app is on screen never travels through
            // the deep link — the half of the door anyone can knock on.
            handedOver()
            opener.openAuthSession(url: url, callbackScheme: scheme) { [weak self] back in
                self?.receive(back, signedInOwner: signedInOwner)
            }
            return .openedInSignInSession
        case .systemBrowser(let url):
            handedOver()
            opener.openSystemBrowser(url: url)
            return .openedInSystemBrowser
        case .refused(let why):
            // A refusal about WHO is signed in, or about an attempt that can
            // no longer be alive, is not retryable: the person this attempt
            // belonged to is not the person holding the phone, or the link
            // behind it is already dead at the server. Anything else leaves
            // the same sheet up so the owner can try again.
            let dead = why == .notAnOwnerId
                || why == .attemptIsForAnotherOwner
                || why == .attemptExpired
            return refuseToOpen(why, then: dead ? .abandonTheAttempt : .sameSheetFreshConsent)
        }
    }

    // MARK: - 4. Coming back

    /// The answer, from either road: the sign-in session hands it back to us,
    /// and the system browser sends it through `anticipy://connected/{toolkit}`
    /// — a URL any web page, any other app or a QR code on a poster can open.
    ///
    /// Returns the handoff's verdict so a caller (and the suite) can see the
    /// exact reason, and publishes only the three states that are the owner's
    /// business. An unreadable callback publishes NOTHING and clears NOTHING:
    /// a stranger's knock must not be able to cancel a connect the owner is in
    /// the middle of, which is what clearing the attempt on every URL would
    /// hand them.
    @discardableResult
    func handleCallback(url: URL, signedInOwner: String) -> ConnectDone {
        let done = ConnectHandoff.parseDone(url: url,
                                            attempt: attempt,
                                            signedInOwner: signedInOwner,
                                            now: clock())
        switch done {
        case .connected(let toolkit, let accountId):
            finish(.connected(toolkit: toolkit, accountId: accountId))
        case .cancelled:
            finish(.cancelled)
        case .failed(let reason):
            finish(.failed(reason: reason))
        case .unreadable(let why):
            lastRefusal = why.code
        }
        return done
    }

    // MARK: - Lifecycle

    /// THE APP LEFT THE SCREEN WITH A SHEET STILL UP. "Immediately before" is
    /// the whole of the requirement, so an acknowledgement — or an unspent
    /// sheet — found lying around afterwards is gone, and the attempt with it.
    /// The owner taps Connect again and gets a fresh sheet and a fresh link.
    ///
    /// A connect already handed over is NOT abandoned: by then the sheet is
    /// down, the acknowledgement is spent, and the backgrounding is the
    /// browser opening. That order is why the handoff spends the tap before
    /// the URL leaves rather than after.
    func appMovedToBackground() {
        gate.appMovedToBackground()
        guard prompt != nil else { return }
        abandon()
    }

    /// A different person is signed in, or nobody is. Nothing this class holds
    /// belongs to them — not the attempt, not the link, not the sheet.
    func ownerChanged() {
        gate.ownerChanged()
        abandon()
        outcome = nil
    }

    /// The screen has shown the outcome and is done with it.
    func clearOutcome() { outcome = nil }

    // MARK: - The plumbing

    @discardableResult
    private func publishPrompt(consent: ConnectConsent? = nil) -> DisclosurePrompt? {
        guard let started = attempt else { return nil }
        let handle = consent ?? ConnectConsent(nonce: mintID(), attemptID: started.id)
        pendingConsent = handle
        let made = DisclosurePrompt(attemptID: started.id,
                                    toolkit: started.toolkit,
                                    sentences: sentences,
                                    consent: handle,
                                    linkReady: adoptedLink != nil)
        prompt = made
        return made
    }

    private func refuseToAsk(_ why: ConnectRefusal) -> DisclosurePrompt? {
        lastRefusal = why.code
        abandon()
        return nil
    }

    /// What a refused tap costs. Three answers, because "try again", "this
    /// connect is over" and "that tap was not about anything standing" are
    /// three different things and a bool carries two of them.
    private enum AfterRefusal {
        /// The same sentences go back up with a NEW consent and a NEW
        /// timestamp. Honest rather than convenient: the dwell floor has to be
        /// met again, because the tap that just happened was not the one that
        /// counted.
        case sameSheetFreshConsent
        /// The attempt, the link and the sheet are gone.
        case abandonTheAttempt
        /// Report it and change nothing.
        case leaveAlone
    }

    private func refuseToOpen(_ why: ConnectRefusal,
                              then next: AfterRefusal) -> ConnectOpening {
        lastRefusal = why.code
        switch next {
        case .leaveAlone:
            break
        case .abandonTheAttempt:
            abandon()
        case .sameSheetFreshConsent:
            guard let started = attempt else { break }
            if case .refused = gate.disclosureShown(for: started,
                                                    sentences: sentences,
                                                    now: clock()) {
                abandon()
            } else {
                publishPrompt()
            }
        }
        return .refused(why)
    }

    /// The link is out. The sheet comes down and the consent is gone; the
    /// attempt lives on, because the callback is still owed to it.
    private func handedOver() {
        prompt = nil
        pendingConsent = nil
        sentences = []
    }

    private func finish(_ result: ConnectOutcome) {
        outcome = result
        abandon()
    }

    private func abandon() {
        attempt = nil
        adoptedLink = nil
        sentences = []
        pendingConsent = nil
        prompt = nil
        gate = DisclosureGate()
    }

    private func receive(_ back: ConnectCallback, signedInOwner: String) {
        switch back {
        case .returned(let url):
            handleCallback(url: url, signedInOwner: signedInOwner)
        case .dismissed:
            // They closed the sheet. Not a failure and not a decline — what a
            // back-out costs is the nudge state machine's decision and
            // nobody else's.
            finish(.cancelled)
        case .failed(let token):
            finish(.failed(reason: token))
        }
    }
}

// MARK: - What the screen is handed

/// THE ONE-SHOT PROOF THAT THE OWNER TAPPED.
///
/// Its fields are `fileprivate`, so the memberwise initialiser is too and no
/// other file can make one: the only consent in existence is the one
/// `ConnectSession` minted and published on a prompt. It names the attempt it
/// belongs to, so a handle kept from an earlier connect cannot license a later
/// one.
struct ConnectConsent: Equatable {
    fileprivate let nonce: String
    fileprivate let attemptID: String
}

/// WHAT THE DISCLOSURE SHEET DRAWS. Every word on it comes from the catalog —
/// the app's own name and the permission sentences generated from its scopes —
/// so a new app in the catalog is a new app in Anticipy with zero code. No app
/// is named in this file, and the runner checks it.
struct DisclosurePrompt: Equatable, Identifiable {
    /// The attempt this sheet is for. It is the identity of the sheet too: a
    /// second connect is a second prompt with a second id.
    let attemptID: String
    var id: String { attemptID }
    /// The catalog's slug. The view looks up the name and the logo with it and
    /// never prints it.
    let toolkit: String
    /// The permission sentences, generated from that app's scopes. Never
    /// empty: a sheet with nothing on it never becomes a prompt.
    let sentences: [String]
    /// Hand this back to `ownerTapped` from the affirmative control's action,
    /// and from nowhere else.
    let consent: ConnectConsent
    /// Our single-use link has arrived and the attempt has adopted it. The
    /// affirmative control may say so — a tap before this is early rather than
    /// wrong, and the sheet stays up for the next one.
    let linkReady: Bool
}

/// WHAT A TAP DID. Two openings, both of them a real browser the person can
/// see the address bar of, and a refusal that names its cause.
enum ConnectOpening: Equatable {
    case openedInSignInSession
    case openedInSystemBrowser
    case refused(ConnectRefusal)
}

/// HOW A CONNECT ENDED, in the owner's terms. `unreadable` is deliberately not
/// one of these: a callback we cannot read is a journal line, never a screen.
enum ConnectOutcome: Equatable {
    /// A HINT that the server now has something to tell us, not a record. The
    /// caller refreshes this owner's connections and believes that.
    case connected(toolkit: String, accountId: String)
    case cancelled
    /// `reason` is a token FOR THE JOURNAL and must never be put on screen: it
    /// is written by another company's server and may name that company, or
    /// its sign-in protocol, in words the spec forbids the owner from seeing.
    case failed(reason: String)
}

// MARK: - The seam

/// WHAT ACTUALLY OPENS A URL. A protocol, so every decision above can be run
/// under `swiftc` with no simulator, no signing and no network — and so the
/// suite can prove which of the two openings was chosen without a browser
/// appearing.
@MainActor
protocol ConnectOpener: AnyObject {
    /// Can the system sign-in session be anchored right now — is there a
    /// foreground window? The policy does not guess this; it is asked. False
    /// means the system browser, never an embedded one.
    var authSessionAvailable: Bool { get }
    func openAuthSession(url: URL,
                         callbackScheme: String,
                         whenDone: @escaping @MainActor (ConnectCallback) -> Void)
    func openSystemBrowser(url: URL)
}

/// What the sign-in session came back with.
enum ConnectCallback: Equatable {
    case returned(URL)
    /// The person closed the sheet.
    case dismissed
    /// A journal token. Never a sentence for the screen.
    case failed(String)
}

#if canImport(UIKit) && canImport(AuthenticationServices)

/// THE REAL ONE, and the only code in the app that opens a connect link.
///
/// Two openings and no third. `ASWebAuthenticationSession` first, because the
/// callback returns to us in-process instead of going out through the deep
/// link every app on the phone can imitate; Safari when there is no window to
/// anchor a sheet to.
@MainActor
final class SystemConnectOpener: NSObject, ConnectOpener,
                                 ASWebAuthenticationPresentationContextProviding {

    /// Held for exactly as long as it is on screen: an
    /// `ASWebAuthenticationSession` nobody retains is deallocated and the
    /// sheet closes itself the instant `start()` returns.
    private var live: ASWebAuthenticationSession?

    var authSessionAvailable: Bool { anchor != nil }

    func openAuthSession(url: URL,
                         callbackScheme: String,
                         whenDone: @escaping @MainActor (ConnectCallback) -> Void) {
        let session = ASWebAuthenticationSession(url: url,
                                                 callbackURLScheme: callbackScheme) { back, error in
            // Documented to arrive on the main thread; hopped explicitly
            // anyway, because a published property written off the main actor
            // is a crash in a release build and not a warning in this one.
            Task { @MainActor [weak self] in
                self?.live = nil
                if let back {
                    whenDone(.returned(back))
                } else if let error {
                    let code = (error as NSError).code
                    let cancelled = ASWebAuthenticationSessionError.canceledLogin.rawValue
                    whenDone(code == cancelled ? .dismissed : .failed("auth_session_error_\(code)"))
                } else {
                    whenDone(.failed("auth_session_said_nothing"))
                }
            }
        }
        session.presentationContextProvider = self
        // FALSE, deliberately. Ephemeral means a browser with no cookies: the
        // owner would have to type a password they are already signed in with,
        // on a phone, to connect an account the browser could have offered
        // them in one tap.
        session.prefersEphemeralWebBrowserSession = false
        live = session
        if !session.start() {
            live = nil
            whenDone(.failed("auth_session_would_not_start"))
        }
    }

    func openSystemBrowser(url: URL) {
        // Safari itself — a browser with its own address bar, outside this
        // app. Not the in-app browser class the suite bans, which Google
        // refuses to sign anyone in inside.
        UIApplication.shared.open(url, options: [:], completionHandler: nil)
    }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        anchor ?? ASPresentationAnchor()
    }

    /// A foreground-active window, or nothing. Nothing means the sign-in sheet
    /// has nowhere to sit and the answer is Safari.
    private var anchor: UIWindow? {
        UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first { $0.activationState == .foregroundActive }?
            .windows
            .first { $0.isKeyWindow }
    }
}

#else

/// THE LAPTOP'S OPENER. It exists so the decisions above compile and run under
/// `swiftc` with no UIKit; it cannot ship, because the iOS build has UIKit by
/// definition. It opens nothing and says so.
@MainActor
final class NoConnectOpener: ConnectOpener {
    var authSessionAvailable: Bool { false }
    func openAuthSession(url: URL,
                         callbackScheme: String,
                         whenDone: @escaping @MainActor (ConnectCallback) -> Void) {
        whenDone(.failed("no_browser_on_this_platform"))
    }
    func openSystemBrowser(url: URL) {}
}

#endif
