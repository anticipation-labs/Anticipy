import Combine
import CryptoKit
import SwiftUI

@main
struct AnticipyApp: App {
    @StateObject private var pendant = PendantManager()
    @StateObject private var session = AnticipySession()
    /// THE CONNECT IN FLIGHT, held at the root for one reason: the callback
    /// comes back through `onOpenURL`, which only the App has. A connect
    /// started on a Settings screen and finished in Safari would otherwise
    /// return to nobody — the connect completes at the other end, the browser
    /// hands the URL to the app, and the app drops it because the object that
    /// knows an attempt is in flight was destroyed when the screen went away.
    @StateObject private var connect = ConnectSession()
    /// Read for one thing only: an unspent disclosure does not survive the app
    /// leaving the screen. Google's Workspace policy asks for the disclosure
    /// to be "immediately before" the connect, and an acknowledgement found
    /// lying around after a trip to another app would let a connect start that
    /// nobody watched begin. `ConnectSession` decides what that costs; this
    /// only tells it the app went away.
    @Environment(\.scenePhase) private var scenePhase
    /// WHOSE first run this is, not merely whether one happened. The key is
    /// declared in FirstRunOwnership because the account lifecycle clears it
    /// and two copies of the string would be a clear that clears nothing.
    @AppStorage(FirstRunOwnership.flagKey) private var hasOnboarded = false
    /// WHETHER THIS PERSON HAS BEEN INTRODUCED TO THE PRODUCT YET. Also
    /// declared in FirstRunOwnership, and cleared beside the tour flag on the
    /// same `.replay` decision — but only where `introSurvivesReplay` says the
    /// introduction on this phone cannot have been this person's own, which is
    /// what stops a brand-new sign-up watching it twice. So the two flags do
    /// part company in one known case; see the note beside `introKey`.
    @AppStorage(FirstRunOwnership.introKey) private var hasSeenIntro = false
    /// LIGHT UNLESS YOU CHOSE DARK. This line used to read
    /// `.preferredColorScheme(.dark)` a few lines down, which is why the app
    /// was dark for everybody with no way out of it.
    ///
    /// The system setting is deliberately not followed. The app opens the same
    /// way for everyone — the first thing a new owner sees should not depend on
    /// a switch in iOS Settings they set for a different reason. Dark is one tap
    /// away in Settings and remembered from then on.
    @AppStorage(AppTheme.key) private var themeChoice = AppTheme.light.rawValue
    /// The celebration, held OUTSIDE the routing decision. Transient on
    /// purpose: if the app dies mid-animation the person is already onboarded
    /// and lands on Home, because the flag was written before this was set.
    @State private var celebrating = false
    /// The three tips and the coach mark that play over Home once the
    /// celebration has finished. Durable, so an app killed mid-tip does not
    /// replay them; transient `showHomeTips` is what is on screen right now.
    @AppStorage(AppPreferences.homeTipsSeenKey) private var homeTipsSeen = false
    @State private var showHomeTips = false
    /// The opening plays once per cold launch, and only in front of first
    /// run — `LaunchIntro.plays(route:)` keeps it off Home. Cleared by the
    /// intro itself when it ends or is tapped through, and by `onAppear`
    /// when the launch lands on Home, so a later sign-out does not replay it.
    @State private var introPlaying = true

    var body: some Scene {
        WindowGroup {
            Group {
                // THE DOOR NO LONGER COMES FIRST, and that is the change.
                // It used to: a stranger typed an email, a password AND a
                // phone number before the product had produced one single
                // thing of its own. The two beats that ask for nothing —
                // the introduction and how she works — happen in front of
                // it now, and the two that need an account stay behind it.
                //
                // The microphone primer is one of the two that stay, and
                // that is a safety property rather than a preference:
                // `heard` attempts a live push before it ever queues, so a
                // microphone running before an account exists would post a
                // stranger's room to the server. FirstRunRoute's header
                // argues it in full; nothing here may move `.mic` forward.
                //
                // Which screen, for which of the six states, is decided by
                // a pure type so the states nobody can reach by tapping —
                // force-quitting between the second beat and the door, a
                // second person signing in on a handed-on phone — are
                // walked by run_first_run_route_tests.sh instead of by
                // somebody with a simulator and a hunch.
                let route = FirstRunRoute.decide(hasSeenIntro: hasSeenIntro,
                                                 isSignedIn: session.isSignedIn,
                                                 hasOnboarded: hasOnboarded)
                if introPlaying && LaunchIntro.plays(route: route) {
                    // THE OPENING. Four seconds of ink on cream — a seed, a
                    // wavefront, the mark — in front of a stranger's first
                    // run and never in front of Home. It is the only thing
                    // on screen while it plays: the beat beneath mounts when
                    // it ends, so the welcome's own reveals happen in front
                    // of the person rather than behind a curtain.
                    IntroView { introPlaying = false }
                        .transition(.opacity)
                } else {
                    switch route {
                    case .intro:
                        // Pre-auth. Nothing durable about an ACCOUNT may be
                        // written from here — there is no account — so this
                        // closure records the one fact that did happen and
                        // stops. The route flips to `.door` on the next frame
                        // because `hasSeenIntro` is what it reads.
                        OnboardingView(segment: .intro, onFinished: {
                            hasSeenIntro = true
                        })
                        .transition(.opacity)
                    case .door:
                        AuthView()
                            .transition(.opacity)
                    case .home:
                        HomeView()
                            .transition(.opacity)
                    case .tour(let segment):
                        OnboardingView(segment: segment, onFinished: {
                            // Order matters, and it is the whole fix: write the
                            // durable fact FIRST, then decorate. The old code did
                            // it the other way round — the flag was the last line
                            // of a 2.4s animation — so an interrupted animation
                            // meant doing all five steps again.
                            //
                            // Both flags, because `.whole` is a journey through
                            // the introduction as well as the tour: a person who
                            // walked all four beats behind the door has been
                            // introduced, and leaving `hasSeenIntro` false would
                            // send them back through the two pre-auth beats the
                            // next time they signed out. Idempotent in `.rest`.
                            hasSeenIntro = true
                            hasOnboarded = true
                            celebrating = true
                        })
                        .transition(.opacity)
                    }
                }
            }
            .onAppear {
                if !LaunchIntro.plays(route: FirstRunRoute.decide(hasSeenIntro: hasSeenIntro,
                                                                  isSignedIn: session.isSignedIn,
                                                                  hasOnboarded: hasOnboarded)) {
                    introPlaying = false
                }
            }
            .overlay {
                if celebrating {
                    // THE TWO FACTS ARE THE POINT OF THIS CALL. `OnboardingFinale`
                    // picks one of three closing sentences, and passing neither
                    // fact collapsed all three into "Give me a day. You'll see."
                    // — said to the person who had tapped "Not right now" on the
                    // microphone a minute earlier, and to the person iOS had
                    // refused on their behalf. Home contradicts that promise on
                    // the very next screen.
                    //
                    // Read off `isListening`, the owner's standing wish, rather
                    // than `capturing`: a phone call holding the microphone for
                    // four seconds at this exact moment would otherwise make the
                    // app call somebody a decliner in the one breath it has to
                    // thank them.
                    OnboardingFinale(listening: session.listener.isListening,
                                     micBlocked: session.micBlocked) {
                        celebrating = false
                        if !homeTipsSeen { showHomeTips = true }
                    }
                }
            }
            // The tips over Home, positioned off the anchor Home reports for
            // its listen control. A Home that reports none gets the three
            // cards and no coach mark, never a bubble pointing at a guess.
            .overlayPreferenceValue(ListenControlAnchorKey.self) { anchor in
                if showHomeTips {
                    GeometryReader { geo in
                        HomeTipsOverlay(listenFrame: anchor.map { geo[$0] },
                                        listening: session.listener.isListening,
                                        micBlocked: session.micBlocked) {
                            homeTipsSeen = true
                            showHomeTips = false
                        }
                    }
                    .ignoresSafeArea()
                    .transition(.opacity)
                }
            }
            .animation(Theme.springSlow, value: showHomeTips)
            // The opening leaves the way the finale does: a breath, not a cut.
            .animation(Theme.springSlow, value: introPlaying)
            // The finale leaves the way it arrived: a breath, not a cut.
            .animation(Theme.springSlow, value: celebrating)
            // The three biggest state changes in the product used to hard-cut.
            .animation(Theme.springSlow, value: session.isSignedIn)
            .animation(Theme.springSlow, value: hasOnboarded)
            // The fourth of them now: clearing the second pre-auth beat is a
            // whole-screen change like the other three, and a hard cut there
            // would be the one hard cut left in first run.
            .animation(Theme.springSlow, value: hasSeenIntro)
            // THE WIDGET'S DOORBELL. A Lock Screen or home tile taps through
            // the anticipy scheme — the constant lives in the widget target —
            // and the answer is the same start the feed's button uses:
            // permission prompts, the account gate, everything the ordinary
            // path does, just without the walk to the app first. A URL this
            // app does not recognise is ignored, like any door knocked on by
            // mistake. `startListening` guards its own state (already
            // listening, mic denied), so the widget can never double-start
            // her.
            //
            // THE CONNECT CALLBACK IS THE SECOND KNOCK ON THIS DOOR, and it is
            // the one anyone can make: `anticipy://connected/{toolkit}` is
            // openable by any web page, any other app, or a QR code on a
            // poster. So nothing here reads it. It goes to `ConnectSession`,
            // which hands it to `ConnectHandoff.parseDone` along with the
            // attempt this phone believes is in flight and the owner signed in
            // AT THIS MOMENT — and a callback with no attempt, for an app we
            // did not start, for another attempt, or after somebody else
            // signed in comes back unreadable and changes nothing.
            //
            // Until this branch existed the host was ignored: a connect that
            // finished in the system browser reached nobody and the phone sat
            // on a spinner with no error anywhere. run_connect_handoff_tests.sh
            // printed that as a note for a day; it is a hard leg now.
            .onOpenURL { url in
                guard url.scheme?.lowercased() == ConnectHandoff.callbackScheme else { return }
                let host = url.host?.lowercased() ?? ""
                if host == "listen" {
                    // THE DOORBELL IS NOT A BACK DOOR. This scheme is openable
                    // by any web page, any QR code and any other app, so it may
                    // only do what the listen control on Home does — and that
                    // control does not exist until first run is over. Ungated it
                    // was the one path that could start a microphone before an
                    // account existed: `heard` pushes live before it queues, so
                    // a stranger's room would have been posted to the server by
                    // a link. The route switch above argues the same rule for
                    // the primer; this is the same rule for the doorbell.
                    if FirstRunRoute.decide(hasSeenIntro: hasSeenIntro,
                                            isSignedIn: session.isSignedIn,
                                            hasOnboarded: hasOnboarded) == .home {
                        session.startListening()
                    }
                } else if host == ConnectHandoff.callbackHost {
                    // `session.accountID` is the owner ROW id — the same id
                    // `contract.ts` binds every connection to. NOT `ownerID`,
                    // which is this device's pre-accounts UUID and would bind
                    // one phone's connections to no account at all.
                    connect.handleCallback(url: url, signedInOwner: session.accountID)
                }
            }
            // A connect belongs to the person who started it. A sign-out, or a
            // second person signing in on a handed-on phone, takes the attempt
            // and the sheet with it rather than leaving them for the next
            // owner to tap through.
            .onChange(of: session.accountID) { _ in
                connect.ownerChanged()
            }
            .onChange(of: scenePhase) { phase in
                if phase != .active { connect.appMovedToBackground() }
            }
            .environmentObject(pendant)
            .environmentObject(session)
            .environmentObject(connect)
            // Pinning the scheme is also what makes every Theme token resolve:
            // they are dynamic UIColors, so they read this trait rather than
            // being decided once at launch. One line themes the whole app.
            .preferredColorScheme(AppTheme(rawValue: themeChoice).colorScheme)
            .tint(Theme.accent)
            // Tell her what time it is where you are — and therefore where
            // you are — on every launch, so it follows you when you travel.
            // Only once signed in: there is no profile to write to before
            // that. Costs no permission prompt and no typing.
            .task(id: session.isSignedIn) {
                if session.isSignedIn { await session.resumeSignedInAccount() }
            }
            .task(id: session.isSignedIn ? pendant.state.rawValue : "signed-out") {
                if session.isSignedIn && pendant.state == .connected {
                    await session.startPendantTranscription(pendant)
                } else {
                    session.stopPendantTranscription(pendant)
                }
            }
        }
    }
}

/// WHO THIS PHONE THINKS YOU ARE — the device-local mirrors of the account
/// holder, named in one place.
///
/// Five UserDefaults keys hold a copy of the person so a booking form can be
/// filled without a round trip. Sign-out took the credentials and left all
/// five, and cable install is the only way this app gets onto a device, so the
/// phone having passed through somebody else's hands is the normal case rather
/// than the edge one (FirstRunOwnership argues the same thing at more length).
/// What that cost: the second person to open a handed-on phone met the door
/// already carrying the FIRST person's email address, under the title "Welcome
/// back."; read their first name in the tour; and reached the number beat with
/// their number already ticked as confirmed — so the new account's
/// confirmations would have been texted to the old owner's handset.
///
/// The keys live here, rather than being written out at each site, because the
/// LIST is the part that drifts: `forgetMeOnThisPhone` in SettingsView has
/// always cleared all five while `signOut` cleared none, and nothing in the
/// repo could see the difference. A sixth mirror added to the session and not
/// to `keys` is caught by app/ios/Tests/run_owner_mirror_tests.sh.
///
/// `ownerID` is deliberately NOT one of these. It is this device's
/// pre-accounts identity — the `legacy_uuid` that `claimLegacy` hands the
/// server so rows made before there were accounts can be adopted rather than
/// orphaned — so clearing it on sign-out would strand the very rows it is the
/// only pointer to. Forgetting the person and rotating the device are
/// different acts; only Settings' "Forget me on this phone" does the second.
enum OwnerMirror {
    static let phone = "ownerPhone"
    static let firstName = "ownerFirstName"
    static let lastName = "ownerLastName"
    static let email = "ownerEmail"
    static let birthday = "ownerBirthday"

    /// Every mirror above. Adding a constant without adding it here is the
    /// exact drift this type exists to stop, and is what the gate reads.
    static let keys = [phone, firstName, lastName, email, birthday]

    /// One complete account answer. Rehydration replaces this value whole; it
    /// never merges non-empty fields into the handset's previous answer. That
    /// distinction is what lets a canonical empty clear an old value and what
    /// prevents account B from inheriting any field account A happened to have.
    struct Values: Equatable {
        let phone: String
        let firstName: String
        let lastName: String
        let email: String
        let birthday: String

        static let empty = Values(phone: "", firstName: "", lastName: "",
                                  email: "", birthday: "")

        func replacing(with canonical: Values) -> Values { canonical }
    }

    /// Text reachability learned from the account record, never inferred from
    /// an old @AppStorage value. `unknown` means the read has not succeeded.
    enum PhoneState: Equatable {
        case unknown
        case none
        case invalid
        case valid
    }

    static func phoneState(forCanonicalPhone phone: String,
                           isValid: Bool) -> PhoneState {
        if phone.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return .none
        }
        return isValid ? .valid : .invalid
    }

    /// Forget whoever this phone was last used by.
    ///
    /// Removing the key rather than writing "" reads identically everywhere it
    /// is read — @AppStorage falls back to its declared default, and
    /// AnticipyVocabulary's `string(forKey:)` goes nil — and it leaves nothing
    /// on disk to be found later.
    static func clear(in defaults: UserDefaults = .standard) {
        for key in keys { defaults.removeObject(forKey: key) }
    }
}

/// The one queue rule that is intentionally wider than an account. Ordinary
/// pending-speech controls remove only the signed-in person's rows; a device
/// Forget promise must also erase sealed rows from prior accounts and legacy
/// rows whose account stamp is nil. Generic so the production queue and the
/// three-account regression fixture execute this same implementation.
enum PendingSpeechRetention {
    static func afterDeviceForget<Element>(_ rows: [Element]) -> [Element] { [] }

    /// The most unsent lines the phone will hold before it starts losing them.
    ///
    /// There was no bound at all until this existed. The queue is one JSON
    /// array serialised into a single `UserDefaults` string, so an outage long
    /// enough — a weekend abroad, a backend down overnight — grew a plist value
    /// without limit, and every append re-encoded the whole array. Neither end
    /// of that has a failure mode anyone would notice until it was already bad.
    ///
    /// 2000 lines is about a hundred kilobytes of transcript, which comfortably
    /// covers the longest outage anyone has actually had, and is still small
    /// enough that the re-encode stays cheap. It is a bound on a BUFFER, not a
    /// judgement about speech: nothing here reads the words.
    static let queueLimit = 2000

    /// Bound the queue, keeping the NEWEST rows, and report what fell off.
    ///
    /// THE OLDEST GO, and the direction is the whole decision. The newest line
    /// is the one still worth acting on; the oldest is already past the six
    /// hours after which the brain will remember a line but never act on it, so
    /// dropping from that end costs memory rather than action. Dropping the
    /// newest instead would throw away the owner's most recent thought to
    /// preserve stale ones, which is the same trade backwards.
    ///
    /// THE COUNT IS RETURNED RATHER THAN SWALLOWED, and that is the half that
    /// matters. A bounded queue that quietly discards is a smaller version of
    /// the bug it fixes — this product's own principle is that silent data loss
    /// is a product bug, and `overnight/are_the_ears_live.py` exists because
    /// thirty hours of it went unnoticed. The caller is obliged to write the
    /// number down.
    static func bounded<Element>(
        _ rows: [Element],
        limit: Int = queueLimit
    ) -> (kept: [Element], dropped: Int) {
        guard limit > 0 else { return ([], rows.count) }
        guard rows.count > limit else { return (rows, 0) }
        return (Array(rows.suffix(limit)), rows.count - limit)
    }
}

/// Translate `/me/delete` evidence into copy without claiming an incremental
/// operation was atomic. The endpoint can remove several tables before one
/// fails, and a lost HTTP response leaves the client unable to know whether the
/// account closed at all.
enum AccountDeletionPolicy {
    struct Outcome: Equatable {
        let ok: Bool
        let message: String
    }

    private struct Payload: Decodable {
        let ok: Bool?
        let message: String?
        let deleted: [String: Int]?
        let failed: [String]?
        let accountDeleted: Bool?
        let memoryPurge: String?

        enum CodingKeys: String, CodingKey {
            case ok, message, deleted, failed
            case accountDeleted = "account_deleted"
            case memoryPurge = "memory_purge"
        }
    }

    static let unverified = Outcome(
        ok: false,
        message: "I couldn't verify how far deletion got. Sign in again if the account still exists, then check what's left before trying again."
    )

    static func outcome(status: Int, body: String) -> Outcome {
        let payload = body.data(using: .utf8)
            .flatMap { try? JSONDecoder().decode(Payload.self, from: $0) }
        let purge = (payload?.memoryPurge ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        // Closing the account and deleting PocketBase rows are not the last
        // physical effect. The worker owns a private per-account memory file,
        // so the endpoint first records a durable purge request and reports
        // whether it is scheduled (the production response) or already done.
        // A 200 missing either proof is unknown, never "gone".
        let success = status == 200 && payload?.ok == true
            && payload?.accountDeleted == true
            && (purge == "scheduled" || purge == "purged")
        var message: String
        if success && purge == "purged" {
            message = "Your account, records, and private memory are gone."
        } else if success {
            message = "Your account is closed and its records are deleted. The final private-memory purge is scheduled and may finish shortly."
        } else if let returned = payload.flatMap({ $0.message })?
                    .trimmingCharacters(in: .whitespacesAndNewlines),
                  !returned.isEmpty {
            message = returned
        } else if status == 401 || status == 403 {
            message = "I couldn't prove it was you. Sign out, sign back in, and check again."
        } else {
            message = "I couldn't verify that everything was deleted. Sign in again if the account still exists, then check what's left before trying again."
        }

        let removed = (payload?.deleted ?? [:])
            .filter { $0.value > 0 }
            .sorted { $0.key < $1.key }
            .map { "\($0.key) (\($0.value))" }
        if !success && !removed.isEmpty {
            message += " Already removed: " + removed.joined(separator: ", ") + "."
        }
        let failed = (payload?.failed ?? [])
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .sorted()
        if !failed.isEmpty {
            message += " Still needs deletion: " + failed.joined(separator: ", ") + "."
        }
        return Outcome(ok: success, message: message)
    }
}

/// A PATCH can reach PocketBase even when its HTTP response never reaches the
/// phone. Decide retry safety from a canonical read of that exact job, not from
/// the transport error that happened after the request left.
enum ActionWritePolicy {
    enum Reconciliation: Equatable {
        case accepted
        case safeToRetry
        case unverified
    }

    static func isVerifiedRefusal(status: Int) -> Bool {
        (400..<500).contains(status) && status != 408
    }

    static func reconcile(originalStatus: String,
                          expectedStatus: String,
                          observedStatus: String?) -> Reconciliation {
        guard let observedStatus else { return .unverified }
        if observedStatus == expectedStatus { return .accepted }
        // Exact unchanged state wins before the post-approval list below:
        // `needs_user` can be both the original status and a later status, and
        // treating the unchanged original as progress would hide a card whose
        // PATCH did nothing.
        if observedStatus == originalStatus { return .safeToRetry }
        // Approval can be claimed and advance again before the canonical read
        // returns. Any ordinary post-approval state proves retrying the same
        // approval would be unsafe even though `queued` was never observed.
        if expectedStatus == "queued",
           ["running", "done", "failed", "cancelled", "needs_user"]
            .contains(observedStatus) {
            return .accepted
        }
        return .unverified
    }
}

/// An asynchronous poll belongs to the account and refresh generation that
/// started it. Network calls yield the main actor; during that yield the owner
/// can sign out, another owner can sign in, or a newer manual refresh can
/// supersede the poll. A response is publishable only while all three facts
/// still match.
enum RefreshAccountPolicy {
    struct Lease: Equatable {
        let generation: Int
        let accountID: String
    }

    static func isCurrent(_ lease: Lease,
                          generation: Int,
                          accountID: String,
                          isSignedIn: Bool) -> Bool {
        isSignedIn
            && !lease.accountID.isEmpty
            && lease.generation == generation
            && lease.accountID == accountID
    }
}

/// A settings write belongs to the exact authenticated session that started
/// it. The backend instance already snapshots that session for the request;
/// this lease prevents a delayed account-A success from repainting account B's
/// device mirrors after a sign-out/sign-in occurs during the network yield.
enum AccountWriteLeasePolicy {
    struct Lease: Equatable {
        let accountID: String
        let authToken: String
    }

    static func begin(accountID: String, authToken: String,
                      isSignedIn: Bool) -> Lease? {
        guard isSignedIn, !accountID.isEmpty, !authToken.isEmpty else { return nil }
        return Lease(accountID: accountID, authToken: authToken)
    }

    static func isCurrent(_ lease: Lease, accountID: String,
                          authToken: String, isSignedIn: Bool) -> Bool {
        isSignedIn
            && lease.accountID == accountID
            && lease.authToken == authToken
    }
}

/// Idempotency and restart state for an in-app answer. The durable id is a
/// function of the authenticated account and the exact question row, so the
/// same tap keeps the same identity across response loss, retries, and process
/// death. Only the identity is persisted; the person's answer text is not.
enum AppReplyWritePolicy {
    static let storageKey = "pendingAppReplyWritesV1"

    struct Pending: Codable, Equatable {
        let accountID: String
        let eventID: String
        let externalEventID: String
    }

    enum CanonicalRead: Equatable {
        case present
        case absent
        case unknown
    }

    enum Reconciliation: Equatable {
        case accepted
        case safeToRetry
        case unverified
    }

    static func externalEventID(accountID: String, eventID: String) -> String? {
        let account = accountID.trimmingCharacters(in: .whitespacesAndNewlines)
        let event = eventID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !account.isEmpty, !event.isEmpty else { return nil }
        return "app-reply:\(account):\(event)"
    }

    static func pending(accountID: String, eventID: String) -> Pending? {
        guard let external = externalEventID(accountID: accountID,
                                             eventID: eventID) else { return nil }
        return Pending(accountID: accountID, eventID: eventID,
                       externalEventID: external)
    }

    static func upserting(_ pending: Pending,
                           in records: [Pending]) -> [Pending] {
        records.filter {
            !($0.accountID == pending.accountID && $0.eventID == pending.eventID)
        } + [pending]
    }

    static func removing(_ pending: Pending,
                          from records: [Pending]) -> [Pending] {
        records.filter {
            !($0.accountID == pending.accountID && $0.eventID == pending.eventID)
        }
    }

    static func eventIDsToRestore(accountID: String,
                                  from records: [Pending]) -> Set<String> {
        Set(records.filter { $0.accountID == accountID }.map(\.eventID))
    }

    static func reconcile(_ read: CanonicalRead) -> Reconciliation {
        switch read {
        case .present: return .accepted
        case .absent: return .safeToRetry
        case .unknown: return .unverified
        }
    }
}

/// App-level state: transcript, agent jobs, backend health. Polls the backend
/// so the proactive feed stays live while the app is open.
@MainActor
final class AnticipySession: ObservableObject {
    @Published var transcript: [TranscriptLine] = []
    @Published var sessionLines: [SessionLine] = []
    @Published var anticipySays: [BrainEvent] = []
    @Published var jobs: [AgentJob] = []
    /// The only way this product can reach someone whose phone is in their
    /// pocket. See Notifier — until it existed, a booking waiting on an OK
    /// reached its owner only if they happened to open the app.
    let notifier = Notifier()
    @Published var backendReachable = false
    @Published var agentOnline = false
    @Published var agentLastSeenSeconds: Int?   // nil = never seen
    @Published var agentPaired = false
    /// The extension version Chrome is actually running, when it is older
    /// than this build expects. He asked "am I on the right version?" twice,
    /// and a whole retest cycle once ran against a stale extension while
    /// everyone assumed the fixes were live. The product should answer that
    /// question itself rather than making him ask a person.
    @Published var staleExtensionVersion: String? = nil

    /// The extension version this build of the app needs. A mismatch is a
    /// fact, not a guess — but the number is hand-maintained, and on
    /// 2026-08-24 it was found still reading 0.8.3 while the extension had
    /// shipped 0.11.0. Three minor versions of silent drift, because the
    /// failure mode here is silence: staleExtension() speaks only when Chrome
    /// is BEHIND this literal, so a pin left in the past cannot fire at all,
    /// and a whole fleet on 0.9.x looks identical to a fleet that is current.
    /// tests/test_extension_version_pin.py now reads extension/manifest.json,
    /// this literal, and the mirror in Tests/StaleExtensionTests.swift, and
    /// goes red when any of the three disagree. Bump all three together.
    static let expectedExtensionVersion = "0.15.0"

    /// The extension reports itself as "Chrome/128.0.0.0 ext/0.8.2" in the
    /// agent record's browser field. Returns what Chrome is running when it
    /// is BEHIND what this app expects, and nil when it is level or ahead —
    /// nagging someone who is already up to date is its own kind of noise.
    static func staleExtension(_ browser: String?) -> String? {
        guard let browser,
              let range = browser.range(of: "ext/") else { return nil }
        let running = String(browser[range.upperBound...])
            .prefix(while: { $0.isNumber || $0 == "." })
        guard !running.isEmpty else { return nil }
        func parts(_ v: some StringProtocol) -> [Int] {
            v.split(separator: ".").map { Int($0) ?? 0 }
        }
        let have = parts(running), want = parts(expectedExtensionVersion)
        for i in 0..<max(have.count, want.count) {
            let a = i < have.count ? have[i] : 0
            let b = i < want.count ? want[i] : 0
            if a != b { return a < b ? String(running) : nil }
        }
        return nil
    }
    @Published var pendantCapturing = false

    /// What the screen is allowed to claim. Before this, "still loading",
    /// "you're offline", "the server refused me" and "you genuinely have
    /// nothing yet" all rendered as the same confident empty state — so a
    /// stranger in airplane mode was told "Live your day. I've got the watch"
    /// by an app that had never reached its own server.
    enum Connection: Equatable {
        case loading          // first probe hasn't answered yet
        case ready            // a read actually succeeded
        case offline          // the server is unreachable
        case refused(Int)     // reached it; it said no (403, 500…)
    }
    @Published var connection: Connection = .loading
    /// How many spoken lines are still waiting for a network.
    @Published var pendingCount = 0

    @AppStorage("backendURL") var backendURLString = "https://api.anticipy.ai"
    @AppStorage("ownerID") var ownerID = ""
    /// Listening is a STANDING state, not a per-open chore: once you turn it
    /// on, she keeps it on — across backgrounds and relaunches — until you
    /// turn it off. This is "knowing when to start" without ever surprising
    /// you: the only hand on the switch is yours.
    @AppStorage("keepListening") var keepListening = false

    private var pollTask: Task<Void, Never>?
    private var bag = Set<AnyCancellable>()
    private var seenDoneJobIDs = Set<String>()
    /// Invalidated by every new refresh and every account boundary. It is not
    /// persisted: this is a lifetime token for in-flight work, not user state.
    private var refreshGeneration = 0
    let listener = PhoneListener()
    /// NO PENDANT TRANSCRIBER. `TranscriberClient` was deleted with this
    /// change: it opened a websocket to a speech vendor and streamed the
    /// pendant's raw Opus frames to it, which is design/LOCAL-FIRST.md rule 1
    /// broken in the first line of the list — "RAW AUDIO NEVER LEAVES A
    /// DEVICE. Not to Deepgram, not to anyone."
    ///
    /// There is no replacement field here on purpose. `LocalTranscriber` is
    /// the intended home and cannot be wired yet (see
    /// `startPendantTranscription`), and a nil-able `transcriber` property
    /// sitting here would be a socket-shaped hole waiting to be refilled.

    /// Words spoken with no network used to live in a plain in-memory array.
    /// If iOS reclaimed the app before it reconnected, they were gone — from a
    /// product whose whole promise is remembering. Now they survive a relaunch.
    /// `Equatable` so a delivered row can be removed from the persisted queue
    /// BY VALUE. An index cannot serve: `unsent` is written by four other
    /// places (a live push failing, sign-out filtering an account out of the
    /// middle, device-forget clearing it, and the bound trimming the front),
    /// and this class is `@MainActor`, so every `await` inside the flush is a
    /// point where any of them can run. A position captured before a network
    /// round trip is a position that may not mean the same row afterwards.
    private struct BufferedLine: Codable, Equatable {
        let text: String
        let explicit: Bool
        let speaker: String?
        /// WHICH microphone produced this line, carried through the offline
        /// queue. Without it a line spoken on the pendant, buffered in a
        /// tunnel and flushed an hour later arrives claiming nothing — and
        /// the buffered lines are exactly the ones a capture comparison
        /// cares about, because they are the ones a radio dropped.
        /// Optional so a queue written by the previous build still decodes.
        var source: String? = nil
        /// WHOSE words these are. The queue is @AppStorage: it survives
        /// relaunch AND sign-out by design, while pushEvent stamps owner_ref
        /// from whoever is signed in AT FLUSH TIME. So one person's private
        /// speech, buffered while offline or while their token was expiring,
        /// was posted into the NEXT person's account the moment they signed
        /// in on the same phone — a path the sign-up flow explicitly allows.
        var account: String?
        /// WHEN THE WORDS WERE SPOKEN, carried through the queue untouched.
        /// Without it a line buffered in a tunnel and flushed an hour later
        /// told the brain it was said the moment the signal came back, and the
        /// brain sorts a person's day by exactly this field.
        /// Optional so a queue written by the previous build still decodes.
        var capturedAt: Date? = nil
        /// WHEN THE FLUSH PRODUCED THE LINE, which is not when the words
        /// started. Without it the two ends of a buffered line collapse onto
        /// one instant at re-send and the brain measures every silence
        /// flush-to-flush — the same defect the live path had, arriving by the
        /// one road that survives a relaunch.
        ///
        /// Optional so a queue written by the previous build still decodes,
        /// and it has to be: the getter answers a failed decode with `?? []`,
        /// so a required field here would silently DELETE everything a person
        /// said while offline on the first launch after the update.
        var endedAt: Date? = nil
        /// Whether the 8s ceiling cut this line out of the middle of a
        /// sentence. Kept as the FACT and not as a parent id, because the line
        /// it carries on from may still be sitting in this same queue with no
        /// server id of its own; the flush rebuilds the chain in order.
        var continuesPrevious: Bool? = nil
    }
    @AppStorage("unsentLines") private var unsentStore = ""
    private var unsent: [BufferedLine] {
        get {
            guard !unsentStore.isEmpty else { return [] }
            let data = Data(unsentStore.utf8)
            if let current = try? JSONDecoder().decode([BufferedLine].self, from: data) {
                return current
            }
            // One-release migration from the old string-only queue. Those
            // rows were microphone speech because typed intent did not yet
            // survive buffering.
            return ((try? JSONDecoder().decode([String].self, from: data)) ?? [])
                .map { BufferedLine(text: $0, explicit: false, speaker: nil,
                                    account: nil) }
        }
        set {
            // BOUNDED HERE, in the setter, rather than at the two call sites
            // that grow the queue. `heard` appends on a failed push and
            // `flushUnsent` prepends what it could not deliver; a bound applied
            // at one of them and not the other is the same as no bound, and
            // nothing would have failed to compile to say so.
            let (kept, dropped) = PendingSpeechRetention.bounded(newValue)
            if dropped > 0 {
                ListenJournal.shared.record(.speechDropped(count: dropped))
            }
            unsentStore = (try? JSONEncoder().encode(kept))
                .flatMap { String(data: $0, encoding: .utf8) } ?? ""
            pendingCount = pendingLinesOwnedByCurrentAccount(in: kept).count
        }
    }

    /// A persisted queue can contain rows from an earlier account. They stay
    /// account-stamped so they can never be delivered to, or inspected by,
    /// whoever signs in next. Legacy rows without an account are deliberately
    /// not claimed: guessing ownership of private speech would be worse than
    /// leaving an unattributable row unread.
    private func pendingLinesOwnedByCurrentAccount(
        in queue: [BufferedLine]
    ) -> [BufferedLine] {
        guard !accountID.isEmpty else { return [] }
        return queue.filter { $0.account == accountID }
    }

    private func refreshPendingCount() {
        pendingCount = pendingLinesOwnedByCurrentAccount(in: unsent).count
    }

    // The five device-local mirrors of the account holder. Keyed through
    // OwnerMirror so the list that clears them cannot drift away from the list
    // that declares them; see that type for what the drift cost.
    @AppStorage(OwnerMirror.phone) var ownerPhone = ""
    @AppStorage(OwnerMirror.firstName) var ownerFirstName = ""
    @AppStorage(OwnerMirror.lastName) var ownerLastName = ""
    @AppStorage(OwnerMirror.email) var ownerEmail = ""
    @AppStorage(OwnerMirror.birthday) var ownerBirthday = ""
    /// The server-derived reachability answer for the currently signed-in
    /// account. This is deliberately not persisted: after a process launch the
    /// account must be read before any screen promises that texts can arrive.
    @Published private(set) var canonicalOwnerPhoneState: OwnerMirror.PhoneState = .unknown
    private var canonicalOwnerRefreshGeneration = 0

    private var currentOwnerMirror: OwnerMirror.Values {
        OwnerMirror.Values(phone: ownerPhone,
                           firstName: ownerFirstName,
                           lastName: ownerLastName,
                           email: ownerEmail,
                           birthday: ownerBirthday)
    }

    /// Full replacement is intentional. Assigning every field, including an
    /// empty string, is the difference between rehydration and a lossy merge.
    private func replaceOwnerMirror(with canonical: OwnerMirror.Values) {
        let replacement = currentOwnerMirror.replacing(with: canonical)
        ownerPhone = replacement.phone
        ownerFirstName = replacement.firstName
        ownerLastName = replacement.lastName
        ownerEmail = replacement.email
        ownerBirthday = replacement.birthday
    }

    private func applyCanonicalOwner(_ owner: AnticipyBackend.Owner) {
        replaceOwnerMirror(with: OwnerMirror.Values(
            phone: owner.phone,
            firstName: owner.firstName,
            lastName: owner.lastName,
            email: owner.email,
            birthday: owner.birthday))
        canonicalOwnerPhoneState = OwnerMirror.phoneState(
            forCanonicalPhone: owner.phone,
            isValid: e164(owner.phone) != nil)
    }

    /// Read the complete canonical profile for this account. A failed request
    /// changes nothing; a successful request replaces all five mirrors even
    /// when one or more canonical values are explicitly empty.
    @discardableResult
    func refreshCanonicalOwner() async -> Bool {
        guard isSignedIn else {
            canonicalOwnerPhoneState = .unknown
            return false
        }
        let requestedAccount = accountID
        canonicalOwnerRefreshGeneration += 1
        let generation = canonicalOwnerRefreshGeneration
        guard let owner = try? await backend.fetchOwner(id: requestedAccount),
              isSignedIn, accountID == requestedAccount,
              generation == canonicalOwnerRefreshGeneration else { return false }
        applyCanonicalOwner(owner)
        return true
    }

    var backend: AnticipyBackend {
        AnticipyBackend(
            baseURL: URL(string: backendURLString) ?? URL(string: "https://api.anticipy.ai")!,
            // Build-stamped so production events reveal WHICH build spoke —
            // "are you sure it's updated?" gets answered by the data.
            deviceID: "iphone-b\(Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "?")",
            // A real signed-in session outranks the shared secret, and the
            // guard accepts either — which is what lets the app move onto
            // accounts without a flag day.
            authToken: authToken,
            accountID: accountID
        )
    }

    init() {
        // MIGRATION 2026-09-05: backend moved off Railway to the Cloudflare
        // Worker at api.anticipy.ai. Installs still holding the old Railway
        // default are moved automatically; a user's own custom override is kept.
        if UserDefaults.standard.string(forKey: "backendURL") == "https://backend-production-61e0a.up.railway.app" {
            UserDefaults.standard.set("https://api.anticipy.ai", forKey: "backendURL")
        }
        if ownerID.isEmpty { ownerID = UUID().uuidString }
        if isSignedIn { restorePendingAppReplyState() }
        // Seed from disk. The count is otherwise only written by the `unsent`
        // setter, so a relaunch with lines still queued reported "0 waiting"
        // until the next failed push — and the screens that reassure you your
        // words survived read exactly this number.
        refreshPendingCount()
        listener.onLine = { [weak self] line, startedAt, endedAt, continues in
            Task { await self?.heard(line, from: .phoneMic, at: startedAt,
                                     endedAt: endedAt,
                                     continuesPrevious: continues) }
        }
        // The on-device voice check rides with each line. It only engages
        // when a model is present AND he has enrolled; otherwise every line
        // travels bare, exactly as before.
        listener.speaker = speakerTagger
        listener.onSpeaker = { [weak self] line, tag, startedAt, endedAt, continues in
            Task { await self?.heard(line, speaker: tag, from: .phoneMic,
                                     at: startedAt, endedAt: endedAt,
                                     continuesPrevious: continues) }
        }
        // Re-render views observing the session when the listener changes.
        listener.objectWillChange
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in self?.objectWillChange.send() }
            .store(in: &bag)
        startPolling()
    }

    /// A line Anticipy heard — phone mic, pendant, or typed. Pushed to the
    /// backend where the brain worker ingests it (memory + triage + jobs).
    /// The line is ALSO kept locally until the server view contains it, so
    /// spoken words never visually disappear, even if a push fails or lags.
    /// The on-device voice check. Owns the roster (his voiceprint and the
    /// people he talks to) — all of it local to this phone.
    let speakerTagger = SpeakerTagger()

    /// Where a line came from. The ack used to be decided by
    /// `!listener.isListening` — the PHONE mic's state standing in for "a
    /// person typed this". It is not the same thing: with a pendant connected
    /// and the phone mic off, every finalized ambient sentence buzzed the
    /// phone all day, which is precisely the twitching the ack rule exists to
    /// prevent; and a line typed while the phone mic was running got no ack at
    /// all. Every call site already knows which of the three this is.
    ///
    /// A `String`-RAW ENUM, so the wire names are compile-time constants of the
    /// type rather than the return values of a `switch` nothing enforces. It
    /// was the latter, and a fifth-pass review named it: `rawValue` on a raw
    /// enum cannot silently gain a fourth spelling or lose one, while a
    /// computed property returning literals can be edited to return anything at
    /// all. Same three words on the wire either way — deliberately NOT
    /// `String(describing:)`, because renaming a Swift case must never
    /// re-label a year of history.
    ///
    /// `ListenEvent.Origin` carries these same three spellings into the
    /// journal, and `CaptureSourcePolicy` matches them coming back off the
    /// wire; `run_journal_tests.sh` checks all three agree.
    enum LineSource: String {
        case typed
        case phoneMic = "phone_mic"
        case pendant

        var wireName: String { rawValue }
    }

    /// The id of the last transcript row this session created, so a line the
    /// clock cut in half can say what it carries on from.
    ///
    /// Deliberately not persisted: a parent from a previous launch is a
    /// sentence nobody is still speaking, and linking onto it would chain two
    /// unrelated conversations into one.
    private var lastTranscriptEventID = ""

    /// `at` is when the words STARTED, which is not when this runs for
    /// anything the phone buffered. `endedAt` is when the flush produced the
    /// line — nil for a typed line, which has no speaking duration to measure,
    /// and the two together are the only thing downstream can subtract to get
    /// a real silence. `continuesPrevious` is true only when the ceiling cut a
    /// sentence in half.
    func heard(_ line: String, speaker: String? = nil,
               explicit: Bool = false,
               from source: LineSource = .typed,
               at capturedAt: Date = Date(),
               endedAt: Date? = nil,
               continuesPrevious: Bool = false) async {
        // A typed line deserves an instant felt ack. Ambient capture does
        // NOT — buzzing on every finalized utterance all day is a phone that
        // won't stop twitching; the meaningful buzz is the act-verdict one.
        if source == .typed { Haptics.tap() }
        sessionLines.append(SessionLine(text: line))
        // Stamped locally too, not only on the wire: the line is in the feed
        // for the ~3s until the server echoes it, and a badge that appears a
        // poll late looks like a glitch in exactly the moment someone is
        // watching to see which ear caught the line.
        transcript.append(TranscriptLine(id: "local-\(UUID().uuidString)", text: line,
                                         decision: nil, source: source.wireName))
        // No owner, no capture. A forced sign-out (an expired token 401s and
        // calls signOut) used to leave the microphone running and every line
        // pushed, 403'd, and queued — the room transcribed behind a sign-in
        // door, then posted into whoever signed in next.
        guard !accountID.isEmpty else { return }
        // Only a cut names a parent, and only a parent that exists: the first
        // line of a session has nothing to carry on from.
        let parent = continuesPrevious ? lastTranscriptEventID : ""
        // ONE construction rule for the live push and the offline flush alike.
        // Two paths building envelopes two ways is how a buffered line and a
        // live line come to mean different things, and the buffered ones are
        // exactly the rows the boundary work exists for.
        let capture = CaptureEnvelope.of(startedAt: capturedAt, endedAt: endedAt)
        do {
            let id = try await backend.pushEvent(kind: "transcript", text: line,
                                        speaker: speaker, explicit: explicit,
                                        source: source.wireName,
                                        capture: capture,
                                        parentLine: parent)
            if !id.isEmpty { lastTranscriptEventID = id }
            ListenJournal.shared.record(
                .posted(ok: true, detail: .sentLive(from: .init(wireName: source.wireName))))
        } catch {
            // A dropped push used to vanish into try? — the line then sat at
            // the top of the feed saying "Thinking…" forever while the brain
            // had never seen it. Queue it (on disk) and keep trying.
            ListenJournal.shared.record(
                .posted(ok: false,
                        detail: .shelved(again: false, failure: Self.postFailureShape(error))))
            // Both ends go to disk. Storing only the start would rebuild a
            // one-instant envelope at flush time and put the buffered path
            // back where the live path just left.
            unsent = unsent + [BufferedLine(text: line, explicit: explicit,
                                            speaker: speaker,
                                            source: source.wireName,
                                            account: accountID,
                                            capturedAt: capturedAt,
                                            endedAt: endedAt,
                                            continuesPrevious: continuesPrevious)]
        }
    }

    /// What went wrong, in a form that is safe to write down.
    ///
    /// A status code, or an error's domain and code. Never a message:
    /// `BackendError` carries the server's own sentence, and a PocketBase error
    /// body is built from a request whose payload is the words the owner just
    /// said. The journal is exportable from Settings, so anything put in it
    /// leaves the phone on a person's tap (`design/LOCAL-FIRST.md`).
    /// A `ListenEvent.PostFailure` rather than a `String`, since 2026-08-25.
    /// The words it goes to disk as are chosen inside `ListenJournal`, from two
    /// Ints and a closed set of five error domains — so this function can no
    /// longer be the place a sentence gets in, whatever it is handed.
    static func postFailureShape(_ error: Error) -> ListenEvent.PostFailure {
        if let refusal = error as? AnticipyBackend.BackendError {
            return .http(status: refusal.status)
        }
        let ns = error as NSError
        return .system(domain: .init(name: ns.domain), code: ns.code)
    }

    /// Re-push anything the network ate, oldest first. A row leaves the disk
    /// only once the server has confirmed it.
    ///
    /// THE QUEUE IS NOT CLEARED UP FRONT, and that is the whole of this
    /// function's correctness. It used to open with `unsent = []`, which is a
    /// synchronous write of an empty array into `@AppStorage` — the durable
    /// queue was emptied BEFORE a single row had been posted, and the loop then
    /// awaited a network round trip per row with the only surviving copy in a
    /// local. iOS suspending or killing a backgrounded app anywhere in that
    /// loop is not an edge case; docs/BRIEF.html names it the largest source of
    /// user-visible capture gaps there is. Every unposted row died there, with
    /// no counter and no journal line — silent capture loss, which this
    /// product's own principle calls a product bug.
    ///
    /// So the flush now iterates a SNAPSHOT for its ordering and its parent
    /// chain, and mutates the persisted queue only by removing rows the server
    /// has acknowledged. A crash mid-flush loses exactly the rows that were
    /// already delivered — which is to say, nothing.
    private func flushUnsent() async {
        guard backendReachable, !unsent.isEmpty, !accountID.isEmpty else { return }
        let queue = unsent
        // The parent of a queued cut is the row posted immediately before it
        // IN THIS FLUSH, and nothing else. `lastTranscriptEventID` cannot
        // serve: it may hold a line posted live AFTER these words were spoken,
        // which would link a sentence to its own future. A skipped row (a
        // foreign account) and a failed row both break the chain outright, so
        // both clear it rather than letting the next line inherit a parent it
        // never followed. A cut whose parent went up live carries no parent at
        // all: the queue never recorded that id, so there is nothing honest to
        // point at.
        var previousInThisFlush = ""
        for line in queue {
            // Never post one person's words into another person's account.
            // A line with no recorded owner predates this field and cannot be
            // attributed. Keep foreign/unattributed rows sealed under their
            // existing stamp instead of sending them or deleting them merely
            // because another account happened to reconnect first.
            guard line.account == accountID else {
                previousInThisFlush = ""
                // Skipped, NOT stalled, and left exactly where it is. A sealed
                // row is never deliverable by this account and never will be,
                // so treating it as a blocking head would mean one foreign line
                // silently stops delivery for every line behind it, forever.
                continue
            }
            let parent = line.continuesPrevious == true ? previousInThisFlush : ""
            do {
                let id = try await backend.pushEvent(kind: "transcript", text: line.text,
                                            speaker: line.speaker,
                                            explicit: line.explicit,
                                            source: line.source,
                                            capture: CaptureEnvelope.of(
                                                startedAt: line.capturedAt,
                                                endedAt: line.endedAt),
                                            parentLine: parent)
                if !id.isEmpty { lastTranscriptEventID = id }
                // An unreadable id is a broken link, not a guessable one.
                previousInThisFlush = id
                // WHICH EAR, carried through the queue: the buffered line kept
                // its source on disk for the wire, and the journal now keeps
                // it too, so the day's per-ear count survives an outage. A
                // queue entry written before the source was stored has none,
                // and `Origin(wireName: "")` is `.unrecognised` — reported as
                // an ear nobody recorded, never guessed at.
                ListenJournal.shared.record(.posted(ok: true, detail: .sentFromQueue(from: .init(wireName: line.source ?? ""))))
                // CONFIRMED, so now it may leave the disk — and not one
                // instant earlier.
                dropDeliveredLine(line)
            }
            catch {
                ListenJournal.shared.record(
                    .posted(ok: false,
                            detail: .shelved(again: true, failure: Self.postFailureShape(error))))
                previousInThisFlush = ""
                // Nothing to do. The row was never removed, so it is still on
                // disk in its original position and the next flush will try it
                // again. The old code had to carry it in `retained` and put it
                // back at the end, which is the step a crash used to skip.
            }
        }
    }

    /// Remove ONE delivered row from the persisted queue, by value, against
    /// whatever the queue holds right now.
    ///
    /// Re-read rather than closed over: the flush awaits between rows, and on
    /// this actor that is where a new line can be appended, an account can be
    /// signed out from under it, or the bound can trim the front. `firstIndex`
    /// removes a single occurrence, so two identical lines legitimately queued
    /// twice are retired one confirmed post at a time rather than both at once.
    private func dropDeliveredLine(_ line: BufferedLine) {
        var current = unsent
        guard let index = current.firstIndex(of: line) else { return }
        current.remove(at: index)
        unsent = current
    }

    /// Anticipy's latest spoken line, only while it's actually fresh — a
    /// remark from an hour ago rereading itself forever feels haunted.
    /// An unparseable date shows the line rather than silently killing the
    /// feature on a backend format drift; only a parsed-and-stale date hides it.
    var freshAnticipyEvent: BrainEvent? {
        guard let ev = anticipySays.first,
              let text = ev.text, !text.isEmpty else { return nil }
        if let date = Self.parsePBDate(ev.created),
           Date().timeIntervalSince(date) >= 15 * 60 { return nil }
        return ev
    }

    func startPolling() {
        pollTask?.cancel()
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                try? await Task.sleep(nanoseconds: 3_000_000_000)
            }
        }
    }

    private func beginRefreshLease() -> RefreshAccountPolicy.Lease? {
        guard isSignedIn else { return nil }
        refreshGeneration &+= 1
        return RefreshAccountPolicy.Lease(generation: refreshGeneration,
                                          accountID: accountID)
    }

    private func invalidateRefreshes() {
        refreshGeneration &+= 1
    }

    private func refreshLeaseIsCurrent(
        _ lease: RefreshAccountPolicy.Lease
    ) -> Bool {
        RefreshAccountPolicy.isCurrent(
            lease,
            generation: refreshGeneration,
            accountID: accountID,
            isSignedIn: isSignedIn)
    }

    func refresh() async {
        guard let lease = beginRefreshLease() else { return }
        let b = backend
        let requestedOwnerID = ownerID
        let reachable = await b.isReachable()
        guard refreshLeaseIsCurrent(lease) else { return }
        backendReachable = reachable
        guard reachable else {
            agentOnline = false
            connection = .offline
            return
        }
        await flushUnsent()
        guard refreshLeaseIsCurrent(lease) else { return }
        // /api/health is NOT behind the guard hook, so "reachable" says nothing
        // about whether our reads are allowed. Only a real read can promote us
        // to .ready — otherwise the app reports itself perfectly healthy while
        // every read is being refused.
        do {
            let fetched = try await b.fetchJobs(owner: requestedOwnerID)
            guard refreshLeaseIsCurrent(lease) else { return }
            jobs = fetched.map { job in
                guard let held = confirmedStatus[job.id] else { return job }
                switch ActionWritePolicy.reconcile(
                    originalStatus: held.original,
                    expectedStatus: held.expected,
                    observedStatus: job.status) {
                case .accepted:
                    // The confirmed state arrived or already advanced. Never
                    // pin `queued` over a worker that has reached running/done.
                    confirmedStatus.removeValue(forKey: job.id)
                    return job
                case .safeToRetry:
                    // This is the one legitimate stale read: PocketBase's
                    // collection query still shows the pre-write state even
                    // though the PATCH response already confirmed acceptance.
                    return job.withStatus(held.expected)
                case .unverified:
                    // A different canonical state wins over a local overlay;
                    // keeping the overlay here can make a card lie forever.
                    confirmedStatus.removeValue(forKey: job.id)
                    return job
                }
            }
            connection = .ready
            // Raised from the poll on purpose: the app keeps running while it
            // listens (background audio), so a local notification from here
            // reaches a locked screen without a push server.
            await notifier.announce(jobs: jobs, stillCurrent: { [weak self] in
                guard let self else { return false }
                return self.refreshLeaseIsCurrent(lease)
            })
            guard refreshLeaseIsCurrent(lease) else { return }
        } catch let e as AnticipyBackend.BackendError {
            guard refreshLeaseIsCurrent(lease) else { return }
            connection = .refused(e.status)
            if e.status == 401 || e.status == 403 {
                // A signed-in session that is being refused is over — the
                // account was deleted, or the token expired (PocketBase issues
                // 7-day tokens). Put them back at the door rather than leaving
                // them staring at "Anticipy won't let me in" with no way
                // forward. Seen for real in the simulator: an account removed
                // server-side left the app in a permanent refused state.
                if !authToken.isEmpty {
                    expireSession()
                    return
                }
            }
        } catch {
            guard refreshLeaseIsCurrent(lease) else { return }
            connection = .offline
        }
        let fetchedEvents = try? await b.fetchEvents()
        guard refreshLeaseIsCurrent(lease) else { return }
        if let events = fetchedEvents {
            // Server view of the stream: heard lines with the brain's verdict,
            // plus everything Anticipy said/texted back.
            var serverLines = events
                .filter { $0.kind == "transcript" }
                .reversed()
                .map { TranscriptLine(id: $0.id, text: $0.text ?? "",
                                      decision: ($0.decision?.isEmpty == false) ? $0.decision : nil,
                                      goal: ($0.goal?.isEmpty == false) ? $0.goal : nil,
                                      // Same empty-string-is-nothing normalisation the
                                      // two fields above already use: PocketBase sends
                                      // "" for an unset text column, and "" must mean
                                      // ungrouped, not a segment named "".
                                      segmentID: ($0.segment?.isEmpty == false) ? $0.segment : nil,
                                      created: $0.created,
                                      // Same normalisation again: "" from an
                                      // unset column must read as "no verdict
                                      // about which microphone", not as a
                                      // fourth kind of ear.
                                      source: ($0.source?.isEmpty == false) ? $0.source : nil) }
            // Reconcile one-to-one by CONSUMING matches: saying the same
            // sentence twice used to mark both local copies received off a
            // single server row, and inherit the older row's verdict.
            // Oldest-first so the first utterance claims the first row.
            var unclaimed = serverLines
            for i in sessionLines.indices {
                guard let hit = unclaimed.firstIndex(where: { $0.text == sessionLines[i].text })
                else { continue }
                let match = unclaimed.remove(at: hit)
                sessionLines[i].received = true
                if let decision = match.decision, sessionLines[i].decision == nil {
                    sessionLines[i].decision = decision
                    // Being acted on is the one verdict worth feeling.
                    if decision == "act" { Haptics.engage() }
                }
            }
            // Never let a just-spoken line vanish: local lines the server
            // hasn't echoed yet stay in the feed, marked as still in flight.
            let serverTexts = Set(serverLines.map(\.text))
            serverLines.append(contentsOf: transcript.filter {
                $0.id.hasPrefix("local-") && !serverTexts.contains($0.text)
            })
            transcript = serverLines
            anticipySays = events.filter { $0.kind == "anticipy_says" || $0.kind == "anticipy_text" }
            // His replies, so a question that is already settled stops
            // offering a box to settle it again. Both lanes: he may answer the
            // same question by text or in here, and either one closes it.
            ownerReplies = events.filter {
                $0.kind == "sms_reply" || $0.kind == "app_reply"
            }
        }
        // A quiet buzz the moment finished work lands.
        let doneIDs = Set(jobs.filter { $0.status == "done" }.map(\.id))
        if !seenDoneJobIDs.isEmpty, !doneIDs.subtracting(seenDoneJobIDs).isEmpty {
            Haptics.success()
        }
        seenDoneJobIDs = doneIDs
        // Connection health from the extension's heartbeat, not guesswork.
        let fetchedAgent = try? await b.fetchAgent(owner: requestedOwnerID)
        guard refreshLeaseIsCurrent(lease) else { return }
        if let agent = fetchedAgent {
            agentPaired = agent.paired ?? false
            staleExtensionVersion = Self.staleExtension(agent.browser)
            if let seen = agent.last_seen, let date = Self.parsePBDate(seen) {
                let secs = max(0, Int(Date().timeIntervalSince(date)))
                agentLastSeenSeconds = secs
                agentOnline = secs < 30
            } else {
                agentLastSeenSeconds = nil
                agentOnline = false
            }
        } else {
            agentPaired = false
            agentLastSeenSeconds = nil
            agentOnline = false
            staleExtensionVersion = nil
        }
    }

    /// Normalize what a human typed into the E.164 the SMS layer needs.
    /// Returns nil when it isn't a complete, dialable number yet.
    ///
    /// IT NEVER INVENTS A COUNTRY, and that is the whole of this function.
    /// It used to read `if digits.count == 10 { return "+1" + digits }`, so a
    /// stranger in London typing the ten digits of their own number —
    /// 2079460958 — had `+12079460958` written to their account at minute two
    /// of sign-up. A text is the ONLY channel this product has outside the
    /// app, nothing downstream validates the number, and Twilio's rejection
    /// reaches a print() on worker stdout and nowhere else. They would have
    /// finished a whole week without one message and without one error.
    ///
    /// The two lines under it were the same bug wearing national dress: the
    /// UK, France, Germany and most of the world write their own numbers with
    /// a leading trunk 0 — "020 7946 0958" — and `"+" + digits` turned that
    /// into `+02079460958`. No country code in E.164 begins with 0, so that
    /// number cannot be dialled from anywhere on earth.
    ///
    /// So: a country code or nothing. `+` is the country code the person
    /// typed; `00` is how most of the world writes `+` on paper. A bare
    /// national number is refused, because guessing which of 200 countries it
    /// belongs to is what broke it. The refusal is not a dead end — the field
    /// arrives with THIS phone's own dialling code already in it
    /// (`DiallingCode.forThisPhone`), visible and editable, so the country is
    /// something the person can see and correct rather than something the app
    /// decides behind them.
    nonisolated func e164(_ raw: String) -> String? {
        var digits = raw.filter(\.isNumber)
        if !raw.hasPrefix("+") {
            // "00" is the international prefix everywhere it is not "011",
            // and it is how people write a foreign-qualified number down.
            guard digits.hasPrefix("00") else { return nil }
            digits = String(digits.dropFirst(2))
        }
        // E.164 is at most 15 digits including the country code, and no
        // country code starts with 0 — a leading 0 here is a trunk prefix
        // somebody left on, not a country.
        guard digits.count >= 8, digits.count <= 15,
              !digits.hasPrefix("0") else { return nil }
        return "+" + digits
    }

    /// Tell the brain what time it is where you are, and therefore WHERE you
    /// are. Reported, never asked for.
    ///
    /// Two things were wrong without it, and both were invisible while there
    /// was exactly one user. Her clock was a single server-wide constant, so
    /// anyone onboarding outside Vancouver was told the wrong time of day and
    /// had her night-time quiet hours land in their afternoon. And nothing
    /// anywhere told her the CITY, which is how "book dinner" became a
    /// reservation in Seattle for somebody who lives in Vancouver.
    ///
    /// An IANA identifier carries both. It needs no permission prompt, no
    /// location services and no typing — iOS already knows it. Sent on every
    /// launch so it follows you when you travel.
    func reportTimeZone() async {
        let zone = TimeZone.current.identifier
        guard !zone.isEmpty else { return }
        _ = await backend.upsertOwner(ownerID: ownerID, fields: ["timezone": zone])
    }

    /// Reconcile account state on every signed-in launch, not only inside the
    /// sign-in button. A phone already signed in before an app update never
    /// calls `signIn` again, so its legacy jobs stayed permanently unclaimed:
    /// production contained 33 rows whose legacy UUID exactly matched the
    /// account, while the account-scoped feed could see zero of them. The
    /// claim endpoint is idempotent; repeating it is the recovery mechanism.
    func resumeSignedInAccount() async {
        guard isSignedIn else { return }
        adoptLocalPersonStateOnAuthenticatedLaunch(for: accountID)
        restorePendingAppReplyState()
        refreshPendingCount()
        // THE PRE-UPGRADE FLAG. A phone updating to this build has
        // hasOnboarded = true and no owner recorded, because the owner key did
        // not exist when it was written. That state is unambiguous: the tour
        // can only be completed from behind the sign-in door, so the only
        // account that could have earned it is the one signed in now. Stamping
        // it is a fact, not a guess — and clearing it instead would make every
        // existing owner redo first run for a bug that was never theirs.
        switch FirstRunOwnership.resuming(account: accountID,
                                          onboardedAccount: onboardedAccount,
                                          hasOnboarded: hasOnboarded) {
        case .keep:
            break
        case .adopt:
            onboardedAccount = accountID
        case .replay:
            // AND THE INTRODUCTION WITH IT — but only when this phone already
            // carries somebody's first run. `arriving` answers `.replay` for a
            // brand-new sign-up too (an empty owner id is not the id just
            // minted), and clearing the intro flag there would walk every new
            // customer through the welcome typewriter and the how-it-works
            // cards a second time, forty seconds after the first. Read BEFORE
            // the two lines below overwrite what it is reading.
            if !FirstRunRoute.introSurvivesReplay(onboardedAccount: onboardedAccount,
                                                  hasOnboarded: hasOnboarded) {
                hasSeenIntro = false
            }
            hasOnboarded = false
            onboardedAccount = accountID
        }
        await backend.claimLegacy(legacyUUID: ownerID)
        await reportTimeZone()
        await refresh()
        // Re-read the WHOLE profile on every authenticated launch. A cached
        // non-empty value is not evidence that the account still says it, and
        // an empty canonical value must be able to clear an older handset
        // mirror. The helper leaves all five values untouched when the read
        // itself fails, so a tunnel is never mistaken for a profile update.
        await refreshCanonicalOwner()
    }

    /// Save the owner's number where the brain can read it, so texting works
    /// without anyone hand-editing a server variable.
    func saveOwnerPhone(_ raw: String) async -> Bool {
        guard let e = e164(raw),
              let lease = AccountWriteLeasePolicy.begin(
                accountID: accountID, authToken: authToken, isSignedIn: isSignedIn)
        else { return false }
        let requestedBackend = backend
        guard await requestedBackend.upsertOwnerPhone(ownerID: ownerID, phone: e),
              AccountWriteLeasePolicy.isCurrent(
                lease, accountID: accountID, authToken: authToken,
                isSignedIn: isSignedIn) else { return false }
        ownerPhone = e
        canonicalOwnerPhoneState = .valid
        return true
    }

    /// Remove the SMS route while keeping results available in the app. The
    /// authenticated endpoint clears every account/profile copy atomically,
    /// then this reads through the same canonical path used by sign-in. The UI
    /// reports success only after the stale signup number did not reappear.
    func removeOwnerPhone() async -> Bool {
        guard isSignedIn,
              await backend.removeOwnerPhone(),
              await refreshCanonicalOwner() else { return false }
        return canonicalOwnerPhoneState == .none
            && ownerPhone.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    /// Her one record of who you are — used to fill the name/email/phone that
    /// every booking form asks for. Payment details are never stored here.
    func saveOwnerDetails(first: String, last: String, email: String, birthday: String = "") async -> Bool {
        guard let lease = AccountWriteLeasePolicy.begin(
            accountID: accountID, authToken: authToken, isSignedIn: isSignedIn)
        else { return false }
        let values = OwnerMirror.Values(
            phone: ownerPhone,
            firstName: first.trimmingCharacters(in: .whitespaces),
            lastName: last.trimmingCharacters(in: .whitespaces),
            email: email.trimmingCharacters(in: .whitespaces),
            birthday: birthday.trimmingCharacters(in: .whitespaces))
        let requestedBackend = backend
        guard await requestedBackend.upsertOwner(ownerID: ownerID, fields: [
            "first_name": values.firstName,
            "last_name": values.lastName,
            "email": values.email,
            "birthday": values.birthday,
        ]), AccountWriteLeasePolicy.isCurrent(
            lease, accountID: accountID, authToken: authToken,
            isSignedIn: isSignedIn) else { return false }
        ownerFirstName = values.firstName
        ownerLastName = values.lastName
        ownerEmail = values.email
        ownerBirthday = values.birthday
        return true
    }

    // MARK: - Day zero: the two things that live on this phone

    /// Say yes to a source, then read it once and send only what was concluded.
    ///
    /// The order is the whole point. Our own screen asks first and states the
    /// reason; iOS is only ever asked after the person has already agreed on a
    /// surface that could explain itself. `design/CONSUMER-READINESS-2026-08-03.md`
    /// T4 records the opposite as the canonical anti-pattern: "The literal
    /// first interaction with the product is a system alert."
    ///
    /// Returns false when iOS refused, so the caller can show a recovery route
    /// rather than leaving a dead switch — B1 in the same audit.
    @discardableResult
    func grantContext(_ source: ContextSource) async -> Bool {
        // ON-DEVICE sources only reach the OS. A supervised browser read has no
        // iOS permission to request - the thing being read is not on this phone -
        // so asking for one would be a round-trip to nowhere, and refusing for
        // want of an answer would make the source permanently ungrantable.
        guard source.isOnDevice else {
        // A NEW GRANT IS A NEW DELIVERY. `context.sent.<source>` records that
        // this source's facts reached the server; it is not cleared by
        // `revoke`, because it is a delivery receipt rather than a permission.
        // Without this line it outlives the grant it belongs to: revoke, then
        // re-grant while offline, and `sendContextFacts` returns without
        // setting it - but it is ALREADY true from the first grant, so
        // `flushPendingContext` skips the source forever and no fact ever
        // arrives, with no error anywhere. That is exactly the permanent silent
        // loss the `return`-instead-of-`break` fix below was written to stop,
        // re-entering through a different door.
        UserDefaults.standard.removeObject(forKey: Self.sentKey(source))
            ContextGrants().grant(source)
            // Deliberately no sendContextFacts: LifeContext.facts is empty for
            // anything not on the device, and posting nothing is not a fact.
            // Facts from a supervised read arrive from the browser, one pass,
            // while the person watches.
            return true
        }
        let osOK: Bool
        switch source {
        case .calendar: osOK = await LifeContext.requestCalendar()
        case .contacts: osOK = await LifeContext.requestContacts()
        // Unreachable: the guard above removed every source that is not on the
        // device, and both on-device sources are handled. It is spelled out
        // rather than left to `default:` silently returning false, because a new
        // on-device source added without a request here would otherwise be
        // permanently ungrantable with no error anywhere.
        default:
            assertionFailure("on-device source \(source.rawValue) has no OS request")
            osOK = false
        }
        guard osOK else { return false }
        // A NEW GRANT IS A NEW DELIVERY. `context.sent.<source>` records that
        // this source's facts reached the server; it is not cleared by
        // `revoke`, because it is a delivery receipt rather than a permission.
        // Without this line it outlives the grant it belongs to: revoke, then
        // re-grant while offline, and `sendContextFacts` returns without
        // setting it - but it is ALREADY true from the first grant, so
        // `flushPendingContext` skips the source forever and no fact ever
        // arrives, with no error anywhere. That is exactly the permanent silent
        // loss the `return`-instead-of-`break` fix below was written to stop,
        // re-entering through a different door.
        UserDefaults.standard.removeObject(forKey: Self.sentKey(source))
        // Record the grant only once iOS has actually agreed, so our gate can
        // never claim access the system will refuse.
        ContextGrants().grant(source)
        await sendContextFacts(source)
        return true
    }

    /// A skip is a "no for now" and nothing else. It is never written down as a
    /// fact about the person (`design/briefs/08-day-zero.md:29-33`).
    func declineContext(_ source: ContextSource) {
        ContextGrants().decline(source)
    }

    /// Read on the device; send the conclusions.
    ///
    /// Posted as `kind: "profile"` — NOT as a transcript. A transcript goes
    /// through triage and could mint an errand, and "Dinner with Priya,
    /// Thursday" is a thing she should KNOW, not a thing she should start
    /// doing. `kind` is a free text column so this needs no migration.
    func sendContextFacts(_ source: ContextSource) async {
        guard ContextGrants().granted(source) else { return }
        let facts = LifeContext.facts(for: source)
        guard !facts.isEmpty else { return }
        for fact in facts {
            do {
                try await backend.pushEvent(kind: "profile", text: fact,
                                            source: source.rawValue)
            } catch {
                // Stop, but do NOT mark delivered — the next foreground retries
                // the whole set. This used to `break` and return silently with
                // the grant already recorded, and because this function has one
                // caller that made the loss permanent: grant underground or on
                // a dead connection and zero facts ever arrived, with no error
                // and no route back short of reinstalling. LOCAL-FIRST.md rule
                // 4 is explicit that a device must keep working offline, and
                // spoken lines already store-and-forward.
                return
            }
        }
        // Only now. remember_fact merges restatements, so a retry that
        // duplicates a fact costs nothing; a fact that never arrives costs the
        // whole feature.
        UserDefaults.standard.set(true, forKey: Self.sentKey(source))
    }

    static func sentKey(_ source: ContextSource) -> String {
        "context.sent.\(source.rawValue)"
    }

    /// Re-send anything a granted source never managed to deliver. Called on
    /// foreground, which is the one moment a connection is most likely to be
    /// back and the person is present to benefit from it.
    func flushPendingContext() async {
        let grants = ContextGrants()
        for source in ContextSource.allCases
        where grants.granted(source)
            && !UserDefaults.standard.bool(forKey: Self.sentKey(source)) {
            await sendContextFacts(source)
        }
    }

    // MARK: - Day zero: the supervised read, and the lease that makes it true

    /// The lane every supervised read runs in. Spelled once here; the server
    /// spells it in `research_lane.pb.js` and `guard.pb.js`, and the extension
    /// in its claim filter. Three copies is already one too many — a fourth,
    /// inline, is how a lane clause drifts (background.js:60-73).
    static let supervisedLane = "supervised_read"

    /// How long one heartbeat buys.
    ///
    /// The screen pushes a new one every ten seconds, so two may be lost to a
    /// bad connection before anything happens — and the read stopping on the
    /// third is the CORRECT outcome, not a failure to paper over. Thirty
    /// seconds is also the worst case for "she stops when you look away": lock
    /// the phone and the server refuses her next claim within half a minute.
    static let watchLeaseSeconds: TimeInterval = 30

    /// Start a supervised read of one source, and say which job it became.
    ///
    /// `ContextSource.mail.promises` opens with "You open it. I read it once,
    /// in the front window, while you watch." This is where that stops being a
    /// sentence: the job is born with `watching_until` already set, and the
    /// extension may not claim it — nor keep running it — unless that stamp is
    /// still in the future (`research_lane.pb.js`). Nothing but a foregrounded
    /// app can keep it there.
    ///
    /// The first lease is set HERE rather than left to the first heartbeat.
    /// Ten seconds of an unclaimable job reads as a dead screen, and the
    /// obvious fix for a dead screen is a flag, which is the one thing this
    /// mechanism exists to avoid (`side_trip.js:194-198`).
    ///
    /// Returns nil rather than throwing, for every reason: no grant, no
    /// connection, a server that refused. The caller shows a plain "I can't
    /// reach my side" and does not retry — a read nobody could start is not a
    /// read that half-happened.
    func startSupervisedRead(source: ContextSource) async -> String? {
        // GATE 1 of `design/day-zero.md` §4: no read without a stored
        // per-source grant. Deterministic code, never the model
        // (`CLAUDE-ONBOARDING.md:19-20`) — the prompt never gets to run,
        // because the job is never created.
        guard ContextGrants().granted(source) else { return nil }
        // Calendar and contacts are read ON THIS PHONE by `LifeContext`; there
        // is no browser tab to watch and nothing for the extension to claim.
        // Queueing one would be a job that sits forever, so it is refused here
        // and loudly in debug, where a new source wired to the wrong reader is
        // a mistake somebody can still fix.
        guard !source.isOnDevice else {
            assertionFailure("\(source.rawValue) is read on the device, not in a browser")
            return nil
        }
        do {
            return try await backend.queueJob(
                // Her words, because this goal is what the feed would show if
                // it ever showed it: short, a contraction's worth of warmth,
                // and it names the specific thing (`CLAUDE-ONBOARDING.md:27-33`).
                goal: "Read \(source.label.lowercased()) once, while you watch.",
                // `params.source` is the SOURCE NAME here ("mail"), not the
                // sentence that provoked the errand, which is what it carries
                // on a triaged job. The read loop keys off it; nothing else
                // reads a supervised read's params.
                params: ["source": source.rawValue],
                lane: Self.supervisedLane,
                // Read-only is the whole consequence class. The action
                // vocabulary narrowing lives in the extension; this is what
                // says so on the row, where an audit can see it.
                consequence: "read_only",
                watchingUntil: Date().addingTimeInterval(Self.watchLeaseSeconds))
        } catch {
            return nil
        }
    }

    /// Push the watch lease out another thirty seconds. Cheap, idempotent,
    /// safe to call every ten.
    ///
    /// SILENT ON PURPOSE. A missed heartbeat is ordinary — a lift, a tunnel, a
    /// slow server — and the read stopping because of it is the mechanism
    /// working, not an error to report or retry. Logging it would train
    /// somebody to ignore the one signal that means "she stopped".
    ///
    /// The caller owns the only thing that matters: this must be called ONLY
    /// while the read is on screen and the scene phase is `.active`. Nothing
    /// here can check that, and nothing here should pretend to.
    func holdWatchLease(jobID: String) async {
        guard !jobID.isEmpty else { return }
        try? await backend.setJobFields(id: jobID, fields: [
            "watching_until": ISO8601DateFormatter.anticipyUTC.string(
                from: Date().addingTimeInterval(Self.watchLeaseSeconds)),
        ])
    }

    /// Stop the read NOW, rather than within the half-minute the last
    /// heartbeat already bought.
    ///
    /// Letting the lease run out is the passive stop — it is what happens when
    /// the phone is locked or the app is backgrounded, and it is what makes
    /// supervision structural. But a person who taps Stop means now: without
    /// this, the extension may keep reading for up to thirty more seconds and
    /// whatever it finds in that window lands in the store having never
    /// appeared on screen, which quietly falsifies "I kept what you watched me
    /// find."
    ///
    /// A stamp in the past rather than a cleared field, so the row still
    /// records WHEN she was stopped; both read as "nobody is watching" to
    /// every guard.
    func dropWatchLease(jobID: String) async {
        guard !jobID.isEmpty else { return }
        try? await backend.setJobFields(id: jobID, fields: [
            "watching_until": ISO8601DateFormatter.anticipyUTC.string(
                from: Date().addingTimeInterval(-1)),
        ])
    }

    /// What she has said and concluded on this read so far, oldest first.
    ///
    /// The narration travels as ordinary events — `read_line` for one short
    /// sentence in her voice, `read_fact` for one distilled fact — stamped with
    /// the job id in `goal`. NOTHING ELSE COMES BACK. No page text, no subject
    /// line, no message body is ever written as an event or stored server-side
    /// (`design/LOCAL-FIRST.md:9-11`: only conclusions travel), and the server
    /// refuses any other kind from a browser credential (`guard.pb.js`).
    ///
    /// Filtered on the job id alone and split by kind here, because a filter
    /// containing `||` is refused outright for an account list
    /// (`guard.pb.js:38-43`).
    func supervisedLines(jobID: String) async -> (lines: [String], facts: [String]) {
        guard !jobID.isEmpty else { return ([], []) }
        guard let events = try? await backend.fetchEvents(
            limit: 120, matching: "goal=\"\(jobID)\"", oldestFirst: true) else {
            // Unreachable, not empty. The caller keeps whatever it has already
            // shown rather than blanking a log somebody is reading.
            return ([], [])
        }
        var lines: [String] = []
        var facts: [String] = []
        for event in events {
            let text = (event.text ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else { continue }
            switch event.kind {
            case "read_line": lines.append(text)
            case "read_fact": facts.append(text)
            // Any other kind on this job is not narration. Dropped rather than
            // rendered: the log says only what she said.
            default: continue
            }
        }
        return (lines, facts)
    }

    /// She got one wrong — throw it away, and say so where it can be acted on.
    ///
    /// `design/day-zero.md` §3: "Every fact is vetoable. A tap deletes it and
    /// marks it never-re-derive." The tap has already removed it from the
    /// screen; this is the half that has to reach the server, posted as
    /// `read_veto` carrying the fact's own text and the job it came from.
    ///
    /// Fire-and-forget and silent, like the heartbeat: the local removal is
    /// what the person sees, and a veto that failed to send is retried by
    /// nothing — it is one line, and she will offer it again rather than
    /// pretend it was forgotten.
    func forgetSupervisedFact(jobID: String, fact: String) async {
        let text = fact.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        // The row's id is discarded deliberately: nothing ever names a veto as
        // the line it carries on from. `_ =` because `try?` makes the returned
        // id an Optional, which @discardableResult no longer covers.
        _ = try? await backend.pushEvent(kind: "read_veto", text: text,
                                         goal: jobID, source: "supervised_mail")
    }

    // MARK: - The interview

    /// One answer, in her words about them, straight into the profile layer.
    ///
    /// Posted as `kind: "profile"` for the same reason the imports are: a
    /// transcript gets triaged, and "I run product at a design studio" is
    /// something she should KNOW, not an errand to start. `remember_fact`
    /// merges restatements, so answering the same question twice cannot
    /// duplicate the fact.
    ///
    /// Returns whether it landed, so the view can keep the question open rather
    /// than telling somebody she remembered a thing she dropped on the floor.
    @discardableResult
    func sendInterviewAnswer(_ question: InterviewQuestion, answer: String) async -> Bool {
        let text = answer.trimmingCharacters(in: .whitespacesAndNewlines)
        // A skip records NOTHING. Never an empty fact, never a "they declined"
        // fact — the absence of an answer is not information about a person
        // (design/briefs/08-day-zero.md:30).
        guard !text.isEmpty else { return false }
        do {
            try await backend.pushEvent(kind: "profile",
                                        text: question.fact(text),
                                        importance: question.importance,
                                        source: "interview")
            InterviewProgress().markAnswered(question.id)
            return true
        } catch {
            return false
        }
    }

    /// Ask the server to forget everything, and say honestly what happened.
    ///
    /// `POST /me/delete` clears every owner-scoped table, schedules the purge of
    /// the per-owner memory file, and closes the account. It answers 409 when
    /// the rows went but the account survived, and 500 when something was left
    /// behind — both of which must reach the person as "not done", because the
    /// whole point of this endpoint is that "deleted" can be believed.
    func deleteEverythingOnServer() async -> (ok: Bool, message: String) {
        guard let lease = AccountWriteLeasePolicy.begin(
            accountID: accountID, authToken: authToken, isSignedIn: isSignedIn)
        else { return (false, "Sign in before asking Anticipy to delete an account.") }
        let requestedBackend = backend
        do {
            let (status, body) = try await requestedBackend.deleteAccount()
            let outcome = AccountDeletionPolicy.outcome(status: status, body: body)
            // A successful server deletion is also a device-forget boundary.
            // Erase sealed prior-account and unstamped legacy speech before
            // this method signs out and removes Settings from the navigation
            // tree. The view must never schedule a later, unscoped sign-out.
            if outcome.ok {
                // This is safe even when another account arrived: remove only
                // rows whose durable owner stamp is the deleted account.
                clearPendingLinesOwned(by: lease.accountID)
                clearPendingAppRepliesOwned(by: lease.accountID)

                let stillCurrent = AccountWriteLeasePolicy.isCurrent(
                    lease, accountID: accountID, authToken: authToken,
                    isSignedIn: isSignedIn)
                // Deleting the account can make the regular poll expire this
                // exact session before the DELETE response returns. That is
                // still A's boundary, provided no explicit sign-out or new
                // account replaced its retained local-person stamp.
                let expiredSameAccount = !isSignedIn && accountID.isEmpty
                    && authToken.isEmpty && localPersonAccountID == lease.accountID
                guard stillCurrent || expiredSameAccount else {
                    return (true, "The original account was deleted. This iPhone changed accounts before local cleanup finished, so the current account was left untouched.")
                }
                clearAllPendingLinesOnDevice()
                clearAllPendingAppRepliesOnDevice()
                signOut()
            }
            return (outcome.ok, outcome.message)
        } catch {
            return (AccountDeletionPolicy.unverified.ok,
                    AccountDeletionPolicy.unverified.message)
        }
    }

    func startListening() {
        // keepListening is only armed once the mic is actually ours. Setting it
        // first meant a refused permission was remembered as "she should be
        // listening", so every foreground re-fired a start iOS instantly denies.
        listener.start()
        keepListening = true
    }

    /// THE PENDANT IS MUTE, and this function is where that is true.
    ///
    /// It used to fetch a 60-second vendor JWT and open a websocket that
    /// streamed the pendant's raw Opus frames, undecoded, to a third party.
    /// design/LOCAL-FIRST.md rule 1, first in the list and quoted in full
    /// because it names the vendor itself:
    ///
    ///     "RAW AUDIO NEVER LEAVES A DEVICE. Not to Deepgram, not to anyone.
    ///      If a capability needs better ears, find a better local model."
    ///
    /// WHAT CLOSING IT COST: nothing that worked. Measured against production
    /// on 2026-08-25 before the server half was removed — events with
    /// source="pendant" is ZERO, ever, and the phone microphone had 229. This
    /// lane never delivered one row in its life.
    ///
    /// -- Why there is no token fetch left to fail ---------------------------
    ///
    /// `/transcription/token` answers 410 GONE now
    /// (`backend/pb_hooks/transcription_token.pb.js`), and the old catch block
    /// called `schedulePendantRetry` on ANY error — so a permanent refusal
    /// would have spun a three-second reconnect loop forever against a
    /// connected pendant, spending battery and radio on a decision that is
    /// never going to change.
    ///
    /// The fix is not a status check in front of the retry. A 410 is not an
    /// outage to be handled gracefully, it is this product refusing to do the
    /// thing, so the request is GONE rather than guarded: nothing here asks,
    /// so nothing here has to decide whether the answer was permanent. (If a
    /// remote transcription lane is ever legitimate again, the rule it needs is
    /// written down and not re-derived: 410 is a decision, 5xx and a dropped
    /// connection are outages, and only the second kind may be retried.)
    ///
    /// -- What this does instead --------------------------------------------
    ///
    /// Drops the frames at the source. `onOpusFrame` is left nil so the BLE
    /// layer's audio goes nowhere at all — not into a queue, not into a buffer
    /// that something later decides what to do with. Audio that is never held
    /// cannot later be sent.
    ///
    /// -- What would make it speak ------------------------------------------
    ///
    /// An on-device transcriber. `Audio/LocalTranscriber.swift` is the
    /// intended home and its ENGINE side is now ready: it selects Apple's
    /// iOS 26 SpeechTranscriber where the device has it (2.12% word error
    /// against the legacy recognizer's 9.02%, still entirely on device) and
    /// accepts the same 16 kHz mono PCM buffers, gap skips included. What is
    /// still missing is unchanged and is the real work: the pendant emits
    /// Opus `Data`, this target has no Opus decoder, and nothing here may
    /// ship raw audio off the phone to have someone else's decoder do it.
    /// Until that decoder exists the pendant is a battery with a microphone
    /// nobody reads, and the app says so on both screens that mention it
    /// rather than showing a Listening label over silence. The gap law is
    /// live regardless: `onGap` reports airtime the radio lost, and the feed
    /// carries the mark.
    func startPendantTranscription(_ pendant: PendantManager) async {
        // Not a guard on `isSignedIn` or the pendant's state: there is nothing
        // to start under any condition, and a version of this that returned
        // early on some paths would leave `onOpusFrame` set on the others.
        pendant.onOpusFrame = nil
        // The gap law starts HERE, even though the frames themselves are
        // dropped at the source: the assembler still measures the airtime
        // the radio lost, and the feed still says so. A pendant that lost a
        // minute is shown as having lost a minute — never as a silence the
        // transcript politely glosses over.
        pendant.onGap = { [weak self] seconds in
            self?.recordPendantGap(seconds)
        }
        pendantCapturing = false
    }

    func stopPendantTranscription(_ pendant: PendantManager) {
        pendant.onOpusFrame = nil
        pendant.onGap = nil
        pendantCapturing = false
    }

    /// The hole, made visible. A gap line never goes through the transcript
    /// push path — the brain must never be asked to triage dead air — and it
    /// is formatted by GapMarker so the wording is one decision, tested,
    /// not three strings typed in three places.
    ///
    /// The journal IS written here now, and the follow-up this comment used to
    /// declare is what closed it: `ListenEvent.airtimeLost` rather than a
    /// reused `sessionStopped`, because journaling a hole as a stopped session
    /// is how a journal starts hiding the stops that were real. That is one
    /// case, one describe line, one parse case and one tally fold — and it is
    /// the difference between a loss the owner can read tomorrow and a loss
    /// that died with the process. The feed marker is per-session UI; the
    /// journal is the durable half, and `ListenTally` folds a day of these into
    /// the two numbers that separate a failing radio from a quiet room.
    ///
    /// ROUNDED, NOT TRUNCATED, and floored at one. The assembler's gap is a
    /// whole number of 10 ms packets, so this conversion is normally exact; the
    /// floor exists so that a gap small enough to round to zero is still
    /// recorded as a gap. `airtimeGaps` is a count of holes, and a hole
    /// reported as zero milliseconds is still a hole — dropping it entirely
    /// would let a continuously-stuttering link report nothing at all.
    private func recordPendantGap(_ seconds: TimeInterval) {
        let marker = GapMarker.text(seconds)
        let milliseconds = max(1, Int((seconds * 1000).rounded()))
        ListenJournal.shared.record(.airtimeLost(milliseconds: milliseconds))
        DispatchQueue.main.async { [weak self] in
            self?.sessionLines.append(SessionLine(text: marker))
        }
    }

    /// True when iOS has already been told no and will not ask again — the app
    /// must send them to Settings rather than pretending another tap will work.
    var micBlocked: Bool { listener.permissionDenied }

    // ---------------------------------------------------------------- login
    /// The signed-in account, if any. Empty means this phone is still running
    /// on the pre-accounts identity.
    @AppStorage("authToken") private var authToken = ""
    @AppStorage("accountID") var accountID = ""
    /// The account that owns device-only voice, interview, and consent state.
    /// It survives an expired token so re-authenticating as the same person
    /// does not erase their setup, while a genuinely different account gets a
    /// clean device boundary before any of that state can be shown.
    @AppStorage("localPersonAccountID") private var localPersonAccountID = ""
    var isSignedIn: Bool { !accountID.isEmpty && !authToken.isEmpty }

    /// THE TOUR FLAG AND ITS OWNER. Same two keys AnticipyApp routes on — see
    /// FirstRunOwnership, which owns both the strings and the decision.
    ///
    /// Written from here rather than from the view because sign-in is where the
    /// person holding the phone can change, and the view has no idea that
    /// happened. AnticipyApp's own @AppStorage observes the same keys, so
    /// clearing the flag here re-routes the app to the tour on the next frame.
    @AppStorage(FirstRunOwnership.flagKey) private var hasOnboarded = false
    @AppStorage(FirstRunOwnership.ownerKey) private var onboardedAccount = ""
    /// AND WHETHER THE PERSON HOLDING IT HAS BEEN INTRODUCED. Cleared on the
    /// same `.replay` decision as the tour flag, at both sites — a different
    /// person is about to use this phone, and the two pre-auth beats are part
    /// of what they have not been shown. BEHIND `introSurvivesReplay`, though,
    /// not on the bare line below it: `.replay` is also the arm a brand-new
    /// sign-up takes, and an unconditional clear there replays the
    /// introduction to the person who has just this second walked it.
    @AppStorage(FirstRunOwnership.introKey) private var hasSeenIntro = false

    /// Make an account. The device's existing `ownerID` rides up as
    /// `legacy_uuid`, so everything already stamped with it — jobs, profile,
    /// segments — belongs to this account instead of being orphaned the moment
    /// accounts arrived. Returns nil on success, or a sentence to show.
    func signUp(email: String, password: String, phone: String) async -> String? {
        let e164 = self.e164(phone)
        do {
            try await backend.createAccount(email: email, password: password,
                                            phone: e164, legacyUUID: ownerID)
        } catch let err as AnticipyBackend.CreateAccountError where err.phoneTaken {
            return "That phone number is already on an account. Sign in to it instead, or if you forgot the password, tap \"Text me a code\" below and I'll get you back in."
        } catch let err as AnticipyBackend.CreateAccountError where err.deviceTaken && !err.emailTaken {
            // This device's pre-accounts identity already belongs to an earlier
            // account. A second account from the same phone is still legitimate:
            // give this one a fresh identity and try again.
            let fresh = UUID().uuidString
            do {
                try await backend.createAccount(email: email, password: password,
                                                phone: e164, legacyUUID: fresh)
                ownerID = fresh
            } catch {
                return "I couldn't set that up just now. Try again in a moment."
            }
        } catch let err as AnticipyBackend.CreateAccountError where err.emailTaken {
            return "That email already has an account. Sign in instead, or use another address."
        } catch let err as AnticipyBackend.CreateAccountError where (400..<500).contains(err.status) {
            return "Something about those details didn't go through. Check the email and try again."
        } catch {
            return "I couldn't reach my side to set that up. Check your connection and try again."
        }
        if let e164 { ownerPhone = e164 }
        return await signIn(email: email, password: password)
    }

    func signIn(email: String, password: String) async -> String? {
        do {
            let (token, id) = try await backend.authWithPassword(email: email, password: password)
            // Any poll that crossed the authentication request belongs to the
            // session that existed before this account arrived. Invalidate it
            // before publishing the new credentials.
            invalidateRefreshes()
            authToken = token
            accountID = id
            prepareLocalPersonStateForSignIn(for: id)
            restorePendingAppReplyState()
            refreshPendingCount()
            // WHOSE TOUR FLAG IS ON THIS PHONE? This is the ONE moment the
            // person holding it can change, and sign-UP reaches it too
            // (signUp ends in signIn).
            //
            // Synchronous, and deliberately with no `await` between it and the
            // line above: `AnticipyApp.task(id: session.isSignedIn)` fires
            // `resumeSignedInAccount` the moment accountID lands, and resuming
            // would ADOPT a flag this call is about to clear.
            //
            // Cable install is the only way onto a device today, so a phone
            // that somebody else has opened is the normal case, not the edge
            // one. Before this, the stranger's sign-up landed straight on the
            // feed: no microphone primer, listening never started, nothing
            // heard all week.
            switch FirstRunOwnership.arriving(account: id,
                                              onboardedAccount: onboardedAccount,
                                              hasOnboarded: hasOnboarded) {
            case .keep:
                break
            case .adopt:
                onboardedAccount = id
            case .replay:
                // AND THE INTRODUCTION WITH IT — but only when this phone already
                // carries somebody's first run. `arriving` answers `.replay` for a
                // brand-new sign-up too (an empty owner id is not the id just
                // minted), and clearing the intro flag there would walk every new
                // customer through the welcome typewriter and the how-it-works
                // cards a second time, forty seconds after the first. Read BEFORE
                // the two lines below overwrite what it is reading.
                if !FirstRunRoute.introSurvivesReplay(onboardedAccount: onboardedAccount,
                                                      hasOnboarded: hasOnboarded) {
                    hasSeenIntro = false
                }
                hasOnboarded = false
                onboardedAccount = id
            }
            // The account email is already a verified fact from the auth
            // boundary. Carry it straight into onboarding/profile defaults;
            // otherwise a new customer sees the literal placeholder
            // "you@example.com" after signing up with their real address.
            ownerEmail = email.trimmingCharacters(in: .whitespaces).lowercased()
            // Replace every device mirror with the account/profile record, not
            // merely the phone. The provisional auth email above keeps a useful
            // default if this first read fails; a successful read is canonical
            // and writes through empty fields as well as populated ones.
            await refreshCanonicalOwner()
            // Adopt this device's pre-accounts rows onto the account before the
            // first refresh, so the feed is already theirs when it paints.
            await backend.claimLegacy(legacyUUID: ownerID)
            await refresh()
            return nil
        } catch let err as AnticipyBackend.BackendError where err.status == 400 {
            return "That email and password don't match anything I have."
        } catch {
            return "I couldn't reach my side just then. Try again in a moment."
        }
    }

    func signOut() {
        authToken = ""
        accountID = ""
        listener.stop()
        clearSignedInSurface()
        purgeLocalPersonState()
        localPersonAccountID = ""
    }

    /// A refused/expired credential ends the authenticated session, but it is
    /// not evidence that the person asked us to delete device-only enrollment,
    /// consent, or interview progress. Keep those under their account stamp so
    /// a same-account re-auth restores them; the interactive sign-in boundary
    /// purges them if the next successful sign-in belongs to somebody else.
    private func expireSession() {
        authToken = ""
        accountID = ""
        listener.stop()
        clearSignedInSurface()
    }

    /// Clear anything that could render or act after authentication has ended.
    /// This is shared by explicit sign-out and token expiry; neither path may
    /// keep listening, display the previous account's words, or leave its
    /// errands on the lock screen.
    private func clearSignedInSurface() {
        // A network response already on its way back must not repopulate this
        // screen (or its lock-screen notifications) after the account leaves.
        invalidateRefreshes()
        // CLOSE THE EARS. signOut cleared the credentials and nothing else:
        // the AVAudioEngine tap stayed installed and the room kept being
        // transcribed behind the sign-in door. The views that normally stop
        // the microphone are torn down the instant isSignedIn flips, so
        // nothing was left to do it. keepListening stays as the person's
        // standing preference — it is honoured again when they sign back in.
        // And forget which row the last line was. Sign out, sign in as someone
        // else in the same launch, speak past the ceiling before anything
        // posts, and the first cut line went up with the new owner_ref and the
        // previous account's parent_line — a cross-account edge in a column
        // the link scoring reads. No speech crosses here, but the pointer did.
        lastTranscriptEventID = ""
        // And take their errands off the lock screen with them. A notification
        // outlives the session that raised it, so without this the next person
        // to pick up the phone reads what the last one was asked to approve.
        notifier.clearAll()
        // And forget the PERSON, not just their session. The fourth catch of
        // this same class in this one function — the ears kept transcribing,
        // the parent_line pointer crossed accounts, the notifications outlived
        // the session, and all along the five owner mirrors outlived the owner.
        // Nothing here is a credential, which is exactly why it was missed:
        // they are the answers to "who are you", and the next person to open
        // this phone was shown them as if they were their own. The list lives
        // in OwnerMirror so this line cannot fall behind the one in Settings.
        OwnerMirror.clear()
        canonicalOwnerPhoneState = .unknown
        canonicalOwnerRefreshGeneration += 1
        // Raw and derived account state is just as identifying as the profile
        // mirrors. In particular, Developer Speech Stream makes these arrays
        // inspectable; retaining them across a sign-in boundary would let the
        // next account read the previous person's words whenever its first
        // refresh was offline.
        transcript = []
        sessionLines = []
        anticipySays = []
        jobs = []
        ownerReplies = []
        failedWrites = []
        unverifiedWrites = []
        pendingJobWrites = [:]
        inFlight = []
        confirmedStatus = [:]
        seenDoneJobIDs = []
        agentPaired = false
        agentOnline = false
        agentLastSeenSeconds = nil
        staleExtensionVersion = nil
        backendReachable = false
        connection = .loading

        UserDefaults.standard.removeObject(forKey: AppPreferences.developerModeKey)
        refreshPendingCount()
    }

    /// Remove person-owned state that has no server round-trip. Called for an
    /// explicit sign-out/forget and before a different account adopts the
    /// device, never merely because a seven-day token expired.
    private func purgeLocalPersonState() {
        speakerTagger.roster.forgetEverything()
        InterviewProgress().reopenAll()
        ContextGrants().resetAll()
        for source in ContextSource.allCases {
            UserDefaults.standard.removeObject(forKey: Self.sentKey(source))
        }
        UserDefaults.standard.removeObject(forKey: "interview.declined")
        UserDefaults.standard.removeObject(forKey: "browserOfferDeferred")
        UserDefaults.standard.removeObject(forKey: "firstOpenedAt")
    }

    /// One-time migration for installs that predate `localPersonAccountID`.
    /// Reaching this path means the app launched with a valid authenticated
    /// account already on disk, so an empty stamp can safely be adopted by that
    /// account. This exception must not be shared with the sign-in path below.
    private func adoptLocalPersonStateOnAuthenticatedLaunch(for account: String) {
        guard !account.isEmpty else { return }
        if localPersonAccountID.isEmpty {
            localPersonAccountID = account
            return
        }
        if localPersonAccountID != account {
            clearSignedInSurface()
            purgeLocalPersonState()
        }
        localPersonAccountID = account
    }

    /// A successful interactive sign-in is not the one-time launch migration.
    /// An empty stamp here may be stale data left after an older build signed
    /// out, so it is purged before the new account is allowed to own the phone.
    /// A retained stamp equal to `account` is the token-expiry case and keeps
    /// voice enrollment, consent, and interview progress intact.
    private func prepareLocalPersonStateForSignIn(for account: String) {
        guard !account.isEmpty else { return }
        if localPersonAccountID != account {
            clearSignedInSurface()
            purgeLocalPersonState()
        }
        localPersonAccountID = account
    }

    /// Ask for a reset code by text. Deliberately returns nothing to report:
    /// the server answers identically whether or not the account exists, so
    /// that this cannot be used to discover who has an account.
    func requestPasswordReset(email: String) async {
        try? await backend.requestPasswordReset(email: email)
    }

    func confirmPasswordReset(email: String, code: String, newPassword: String) async -> String? {
        do {
            try await backend.confirmPasswordReset(email: email, code: code, password: newPassword)
            return nil
        } catch let err as AnticipyBackend.MessageError {
            return err.message
        } catch {
            return "I couldn't reach my side just then. Try again in a moment."
        }
    }

    /// Throw away the words still waiting for a network. Owned here because the
    /// queue's storage key is private: Settings was reaching into UserDefaults
    /// with a copy of the key string, so renaming it would have left a delete
    /// button that silently deleted nothing.
    func clearPendingLines() {
        guard !accountID.isEmpty else { return }
        clearPendingLinesOwned(by: accountID)
    }

    private func clearPendingLinesOwned(by ownerAccount: String) {
        guard !ownerAccount.isEmpty else { return }
        unsent = unsent.filter { $0.account != ownerAccount }
    }

    private func restorePendingAppReplyState() {
        guard isSignedIn else { return }
        unverifiedWrites.formUnion(
            AppReplyWritePolicy.eventIDsToRestore(
                accountID: accountID, from: pendingAppReplies))
    }

    private func rememberPendingAppReply(_ pending: AppReplyWritePolicy.Pending) {
        pendingAppReplies = AppReplyWritePolicy.upserting(
            pending, in: pendingAppReplies)
    }

    private func removePendingAppReply(_ pending: AppReplyWritePolicy.Pending) {
        pendingAppReplies = AppReplyWritePolicy.removing(
            pending, from: pendingAppReplies)
    }

    private func pendingAppReply(eventID: String) -> AppReplyWritePolicy.Pending? {
        pendingAppReplies.first {
            $0.accountID == accountID && $0.eventID == eventID
        }
    }

    private func clearAllPendingAppRepliesOnDevice() {
        pendingAppReplies = []
        unverifiedWrites = []
    }

    private func clearPendingAppRepliesOwned(by ownerAccount: String) {
        guard !ownerAccount.isEmpty else { return }
        let removedEventIDs = Set(pendingAppReplies.lazy
            .filter { $0.accountID == ownerAccount }
            .map(\.eventID))
        pendingAppReplies.removeAll { $0.accountID == ownerAccount }
        unverifiedWrites.subtract(removedEventIDs)
    }

    /// Device-wide erasure for the two operations whose copy promises this
    /// handset is forgotten. Unlike `clearPendingLines`, this must include
    /// nil-stamped legacy rows and sealed speech from every prior account.
    private func clearAllPendingLinesOnDevice() {
        unsent = PendingSpeechRetention.afterDeviceForget(unsent)
    }

    /// The words waiting for a network, exposed read-only for Privacy & Data.
    /// The storage envelope stays private so no view can rewrite ownership,
    /// timestamps, or delivery flags around the queue.
    var pendingSpeechLines: [String] {
        pendingLinesOwnedByCurrentAccount(in: unsent).map(\.text)
    }

    /// Remove this account from the handset while leaving its server data
    /// intact. Browser disconnect is verified before the credentials are
    /// dropped; the Bool lets Settings say when the local forget succeeded but
    /// Chrome could not be reached to complete its half.
    func forgetThisPhone() async -> Bool {
        guard let lease = AccountWriteLeasePolicy.begin(
            accountID: accountID, authToken: authToken, isSignedIn: isSignedIn)
        else { return false }
        let requestedBackend = backend
        stopListening()
        clearAllPendingLinesOnDevice()
        clearAllPendingAppRepliesOnDevice()
        let oldIdentity = ownerID
        let browserDisconnected = await requestedBackend.unpairAgent(owner: oldIdentity)
        let stillCurrent = AccountWriteLeasePolicy.isCurrent(
            lease, accountID: accountID, authToken: authToken,
            isSignedIn: isSignedIn)
        let expiredSameAccount = !isSignedIn && accountID.isEmpty
            && authToken.isEmpty && localPersonAccountID == lease.accountID
        // A completion from an old Settings task cannot sign out the next
        // person or rotate the identity underneath their freshly paired app.
        guard stillCurrent || expiredSameAccount else { return false }
        let notice = browserDisconnected
            ? "This iPhone was forgotten. Its local profile and speech queue are gone, and the browser link is disconnected."
            : "This iPhone was forgotten locally, but Anticipy could not verify that every browser link was disconnected. Remove the Anticipy extension in Chrome before pairing again."
        // Settings disappears as soon as signOut flips the app route. Persist
        // the outcome first so the Auth screen that replaces it can show the
        // browser failure instead of writing into a view that no longer exists.
        UserDefaults.standard.set(notice, forKey: AppPreferences.postSignOutNoticeKey)
        signOut()
        ownerID = UUID().uuidString
        return browserDisconnected
    }

    /// Open this app's page in iOS Settings. The whole app had no route there.
    func openSystemSettings() {
        guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
        UIApplication.shared.open(url)
    }

    func stopListening() {
        keepListening = false
        listener.stop()
    }

    /// Called on launch and on returning to foreground: if listening was on
    /// when we left, pick it right back up.
    ///
    /// This used to read `if keepListening, !listener.isListening` and do
    /// NOTHING after a phone call, because no interruption anywhere in the app
    /// clears `isListening` — the guard was false exactly when it mattered. The
    /// decision now lives in `ListenResumePolicy`, where it can be shown to
    /// fail with swiftc alone; this body only carries the answer out.
    func resumeListeningIfWanted() {
        switch ListenResumePolicy.decide(wantsListening: keepListening,
                                         isListening: listener.isListening,
                                         suspended: listener.suspended) {
        case .start: listener.start()
        case .retakeMicrophone: listener.retakeMicrophone()
        case .nothing: break
        }
    }

    /// Why a pairing attempt didn't work — so the UI never blames someone for
    /// a code that was right. This used to collapse every thrown error into
    /// `false`, i.e. "wrong code", including no network.
    enum PairOutcome: Equatable {
        case paired
        case noMatch          // the six digits genuinely matched nothing
        case unreachable      // couldn't reach Anticipy at all
    }

    /// Pair with the browser agent using the extension's 6-digit code.
    func pairAgent(code: String) async -> PairOutcome {
        do {
            let matched = try await backend.pairAgent(code: code, owner: ownerID)
            if matched { await refresh() }
            return matched ? .paired : .noMatch
        } catch {
            return .unreachable
        }
    }

    /// Pure string→Date; nothing about it touches session state, and a view
    /// needs it to put a clock time on a card.
    nonisolated static func parsePBDate(_ s: String) -> Date? {
        // PocketBase dates: "2026-07-21 04:55:00.123Z" or ISO8601.
        let fmt = DateFormatter()
        fmt.locale = Locale(identifier: "en_US_POSIX")
        fmt.timeZone = TimeZone(identifier: "UTC")
        for pattern in ["yyyy-MM-dd HH:mm:ss.SSS'Z'", "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'", "yyyy-MM-dd HH:mm:ss'Z'"] {
            fmt.dateFormat = pattern
            if let d = fmt.date(from: s) { return d }
        }
        return ISO8601DateFormatter().date(from: s)
    }

    /// Jobs whose last write failed, so the card can say so and offer Retry
    /// instead of buzzing success and leaving the card sitting there.
    @Published var failedWrites: Set<String> = []
    /// Requests whose transport ended without a trustworthy server verdict.
    /// These are deliberately separate from refused writes: retrying one can
    /// duplicate an action the server already accepted.
    @Published private(set) var unverifiedWrites: Set<String> = []
    /// Unknown app-reply writes survive a process restart as owner-scoped
    /// identities. No answer text is written here; the exact server lookup
    /// needs only the idempotency id.
    @AppStorage(AppReplyWritePolicy.storageKey) private var pendingAppReplyStore = ""
    private var pendingAppReplies: [AppReplyWritePolicy.Pending] {
        get {
            guard !pendingAppReplyStore.isEmpty else { return [] }
            return (try? JSONDecoder().decode(
                [AppReplyWritePolicy.Pending].self,
                from: Data(pendingAppReplyStore.utf8))) ?? []
        }
        set {
            pendingAppReplyStore = (try? JSONEncoder().encode(newValue))
                .flatMap { String(data: $0, encoding: .utf8) } ?? ""
        }
    }
    private struct PendingJobWrite {
        let originalStatus: String
        let expectedStatus: String?
    }
    private var pendingJobWrites: [String: PendingJobWrite] = [:]
    /// Statuses the server has ALREADY ACCEPTED, held over the feed until a
    /// fetch agrees with them.
    ///
    /// Not optimism about a write in flight - that would be the dishonesty
    /// `write` exists to prevent. This is only ever populated AFTER the server
    /// returned success, and it answers a different problem: `fetchJobs` is a
    /// separate round-trip that can legitimately return a pre-write row
    /// (PocketBase gives no read-after-write guarantee across requests), so
    /// without this the card visibly snaps back to "waiting for your OK" for one
    /// poll after she was told yes.
    private struct ConfirmedJobStatus {
        let original: String
        let expected: String
    }
    private var confirmedStatus: [String: ConfirmedJobStatus] = [:]
    /// Jobs with a write in flight — the card disables itself, so a tap that
    /// looks like it did nothing can't be tapped again into a double send.
    @Published var inFlight: Set<String> = []
    /// HIS OWN turns, either lane, newest first. This is how the app knows
    /// whether a question she asked is still OPEN.
    ///
    /// Without it there is no way to tell an unanswered question from one he
    /// settled by text an hour ago, and a card offering to answer a closed
    /// question is an invitation to answer it twice. Server truth on purpose:
    /// a local "I answered this" set would forget on reinstall and would not
    /// know about anything he said from his phone's Messages app.
    @Published var ownerReplies: [BrainEvent] = []

    private enum WorkflowWriteError: Error { case malformed, unsafeRetry }

    private func jsonString(_ value: Any) throws -> String {
        let data = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
        guard let text = String(data: data, encoding: .utf8) else {
            throw WorkflowWriteError.malformed
        }
        return text
    }

    private func workflowDigest(_ value: [String: Any]) throws -> String {
        let data = try JSONSerialization.data(withJSONObject: value,
                                              options: [.sortedKeys])
        // JSONSerialization escapes "/" as "\/"; Python (ensure_ascii=False,
        // compact) and JS do not. The digests happened to agree until now
        // only because no goal contained a slash — the first URL or "24/7"
        // in a plan would make every app-minted digest diverge from the
        // brain's recomputation. Normalize to the canonical form.
        let canonical = String(decoding: data, as: UTF8.self)
            .replacingOccurrences(of: "\\/", with: "/")
        return SHA256.hash(data: Data(canonical.utf8))
            .map { String(format: "%02x", $0) }.joined()
    }

    private func humanApprovalScope(_ workflow: [String: Any],
                                    fallbackGoal: String) -> String {
        let goal = (workflow["goal"] as? String ?? fallbackGoal)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let source = (workflow["authority_text"] as? String ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !source.isEmpty else { return goal }
        return "Task: \(goal)\nYour exact words: \(source)"
    }

    /// Build the complete, version-bound approval patch. The model never gets
    /// to turn a button tap into authority: the app binds the owner's actual
    /// gesture to the exact digest the brain placed on this immutable version.
    private func approvalFields(for job: AgentJob,
                                ownerAnswer: String? = nil) throws -> [String: Any]? {
        guard let planID = job.workflow_id, !planID.isEmpty else { return nil }
        guard job.workflow_state == "awaiting_approval" || job.workflow_state == "needs_user"
        else { throw WorkflowWriteError.unsafeRetry }
        var params = (try? JSONSerialization.jsonObject(with: Data(job.params.utf8)))
            as? [String: Any] ?? [:]
        guard var workflow = params["_workflow"] as? [String: Any],
              workflow["plan_id"] as? String == planID,
              let version = job.workflow_version,
              (workflow["version"] as? Int) == version,
              let scope = job.scope_digest, !scope.isEmpty,
              workflow["scope_digest"] as? String == scope
        else { throw WorkflowWriteError.malformed }

        let now = ISO8601DateFormatter.anticipyUTC.string(from: Date())
        let answer = ownerAnswer?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        // THE PHONE CITES THE ROW, NEVER A CONSTANT. Audit #90, correction (E).
        //
        // What was here until 2026-09-05: `ownerWords` was the sentence
        // "I checked the site; the action did not happen. Try again." for
        // every uncertain row, and the `reconciliation` written below carried
        // conclusion "not_applied" and evidence "owner explicitly checked the
        // destination before retry" — whether or not anyone had checked
        // anything. That is exactly what the DB guard's retry leg reads
        // (backend/pb_hooks/workflow_guard.pb.js, the effect_uncertain block),
        // so a crash plus a tap re-sent the submission. The extension now
        // looks (extension/reconcile.js) and writes `params._reconciliation`
        // in four states; this reads it, and `RetryReconciliationPolicy` is
        // the floor: a retry needs a positive not_applied, or it does not
        // leave the phone.
        let reconciliation = RetryReconciliationPolicy.read(params)
        let ownerWords: String
        if job.effect_uncertain == true {
            guard RetryReconciliationPolicy.mayRetry(reconciliation) else {
                throw WorkflowWriteError.unsafeRetry
            }
            // The gesture, named as a gesture — the same shape "Tapped
            // “Approve”." takes below. Not a sentence he never said.
            ownerWords = "Tapped “I checked, try again”."
        } else {
            ownerWords = job.status == "needs_user" ? answer : "Tapped “Approve”."
        }
        if job.status == "needs_user" && job.effect_uncertain != true && ownerWords.isEmpty {
            throw WorkflowWriteError.malformed
        }

        var approvedVersion = version
        var approvedScope = scope
        var approvedEffect = job.effect_key ?? ""
        if job.status == "needs_user" && job.effect_uncertain != true {
            approvedVersion += 1
            let asked = job.result ?? ""
            var facts = workflow["facts"] as? [String: Any] ?? [:]
            // Answers ACCUMULATE, question-scoped. One shared owner_answer
            // slot destroyed the contact-details answer the moment the next
            // answer ("No u don't") arrived — live, 2026-08-15.
            // Zero-padded so numeric-aware (Darwin .sortedKeys) and
            // code-point (Python/JS) key ordering agree: at v10+ the keys
            // owner_answer_v2 / owner_answer_v10 sort differently on the
            // two sides and every digest diverges (hunt find, 2026-08-15).
            facts[String(format: "owner_answer_v%03d", approvedVersion)] = asked.isEmpty
                ? ownerWords
                : "Q: \(String(asked.prefix(120))) A: \(ownerWords)"
            // Deterministic structuring: contact-shaped tokens become real
            // fields the hands can type into the matching form inputs —
            // never the raw sentence.
            for (key, pattern) in [
                ("email", "[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}"),
                ("phone", "\\+?[0-9][0-9 ().-]{6,}[0-9]"),
            ] where facts[key] == nil {
                if let range = ownerWords.range(of: pattern, options: .regularExpression) {
                    facts[key] = String(ownerWords[range])
                }
            }
            if facts["name"] == nil,
               let match = ownerWords.range(
                   of: "(?i)name(?:\\s+is)?[:\\s]+[A-Za-z][A-Za-z'’-]{1,30}",
                   options: .regularExpression) {
                let phrase = String(ownerWords[match])
                if let tail = phrase.range(of: "[A-Za-z][A-Za-z'’-]{1,30}$",
                                           options: .regularExpression) {
                    facts["name"] = String(phrase[tail])
                }
            }
            workflow["facts"] = facts
            workflow["version"] = approvedVersion
            let consequence = workflow["consequence"] as? String ?? "consequential"
            let goal = workflow["goal"] as? String ?? job.goal
            var scopePayload: [String: Any] = [
                "plan_id": planID, "version": approvedVersion,
                "goal": goal, "facts": facts, "consequence": consequence,
            ]
            if let authority = workflow["authority_text"] as? String,
               !authority.isEmpty { scopePayload["authority_text"] = authority }
            approvedScope = try workflowDigest(scopePayload)
            let ownerRef = workflow["owner_ref"] as? String ?? ""
            var effectPayload: [String: Any] = [
                "owner_ref": ownerRef, "plan_id": planID,
                "version": approvedVersion, "goal": goal,
                "facts": facts, "consequence": consequence,
            ]
            if let authority = workflow["authority_text"] as? String,
               !authority.isEmpty { effectPayload["authority_text"] = authority }
            approvedEffect = try workflowDigest(effectPayload)
            workflow["scope_digest"] = approvedScope
            workflow["effect_key"] = approvedEffect
            params["owner_answer"] = ownerWords
            let oldScope = params["approved_scope"] as? String
                ?? humanApprovalScope(workflow, fallbackGoal: goal)
            params["approved_scope"] = oldScope
                + " You stopped and asked: \"\(asked)\". They answered: \"\(ownerWords)\"."
        }
        let approval: [String: Any] = [
            "plan_id": planID,
            "plan_version": approvedVersion,
            "scope_digest": approvedScope,
            "owner_words": ownerWords,
            "approved_at": now,
        ]
        workflow["approval"] = approval
        workflow["state"] = "queued"
        workflow["reason"] = "approved by owner"
        workflow["updated_at"] = now
        workflow["lease"] = NSNull()
        workflow["receipt"] = NSNull()
        // A fresh owner authorization is a fresh execution budget. Without
        // this, three needs_user question-rounds exhausted the attempt cap
        // and every later resume minted an approved version the extension
        // could never claim (live, 2026-08-15: the wedged Earls booking).
        workflow["attempts"] = 0
        params["_workflow"] = workflow
        params["authorized"] = true
        if job.status != "needs_user" || params["approved_scope"] == nil {
            params["approved_scope"] = humanApprovalScope(
                workflow, fallbackGoal: job.goal)
        }
        var fields: [String: Any] = [
            "status": "queued",
            "workflow_state": "queued",
            "workflow_version": approvedVersion,
            "attempts": 0,
            "scope_digest": approvedScope,
            "effect_key": approvedEffect,
            "approval": try jsonString(approval),
            "params": try jsonString(params),
            "lease_token": "",
            "lease_until": "",
            "receipt": "",
            "effect_uncertain": false,
        ]
        if job.effect_uncertain == true {
            guard let effectKey = job.effect_key, !effectKey.isEmpty else {
                throw WorkflowWriteError.malformed
            }
            // Every field the guard reads is read off the ROW: the conclusion
            // is the extension's verdict spelled as it spelled it, the
            // evidence is its list plus the one line that is genuinely his —
            // the tap — and `checked_at` says when the page was read. The
            // `mayRetry` guard above already refused anything but a positive
            // not_applied; this cannot be reached with any other verdict, and
            // the second `guard` keeps that true if the two ever drift.
            guard case .checked(let row) = reconciliation,
                  let evidence = RetryReconciliationPolicy.retryEvidence(
                      reconciliation, tappedAt: now)
            else { throw WorkflowWriteError.unsafeRetry }
            let cited: [String: Any] = [
                "effect_key": effectKey,
                "conclusion": row.verdict.rawValue,
                "verified": true,
                "owner_words": ownerWords,
                "evidence": evidence,
                "checked_at": row.at,
                "recorded_at": now,
            ]
            fields["reconciliation"] = try jsonString(cited)
        } else {
            fields["reconciliation"] = ""
        }
        return fields
    }


    private func cancellationFields(for job: AgentJob,
                                    trigger: String = "unspecified") throws -> [String: Any]? {
        guard let planID = job.workflow_id, !planID.isEmpty else { return nil }
        var params = (try? JSONSerialization.jsonObject(with: Data(job.params.utf8)))
            as? [String: Any] ?? [:]
        guard var workflow = params["_workflow"] as? [String: Any],
              workflow["plan_id"] as? String == planID
        else { throw WorkflowWriteError.malformed }
        let now = ISO8601DateFormatter.anticipyUTC.string(from: Date())
        workflow["state"] = "cancelled"
        // NAME THE TRIGGER. "cancelled by owner" is what every cancellation
        // said, so when he insisted he had pressed nothing there was no way
        // to tell a deliberate "Not now" from an answer misread as a
        // refusal — the two live on the same line of the same file.
        workflow["reason"] = "cancelled by owner (\(trigger))"
        workflow["updated_at"] = now
        workflow["approval"] = NSNull()
        workflow["lease"] = NSNull()
        workflow["receipt"] = NSNull()
        params["_workflow"] = workflow
        return [
            "status": "cancelled",
            "workflow_state": "cancelled",
            "approval": "",
            "receipt": "",
            "lease_token": "",
            "lease_until": "",
            "effect_uncertain": false,
            "params": try jsonString(params),
        ]
    }

    @discardableResult
    func confirm(_ job: AgentJob, ownerAnswer: String? = nil) async -> Bool {
        // Every typed answer goes to the brain instead of onto the job. Writing it
        // here would be a second path to a decision the text lane already owns
        // (brief ex 120): it skips whether the answer covers what the task said
        // it needed, skips keeping what he said about himself, and skips
        // deciding which task he meant when two are blocked — the 2026-08-02
        // failure, where an answer arrived and resolved nothing.
        let trimmed = ownerAnswer?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        switch AnswerRoutePolicy.route(
            status: job.status,
            workflowState: job.workflow_state,
            effectUncertain: job.effect_uncertain == true,
            answer: trimmed) {

        case .nothingToSend:
            return false

        case .toTheBrain(let answer):
            // ONE inbound turn, the same one a text produces. The worker reads
            // `app_reply` beside `sms_reply` and both reach on_reply, so the
            // stuck task resumes through _resume_stuck rather than being
            // requeued on the hope that the answer was sufficient.
            //
            // The job is deliberately NOT touched. If this write lands and the
            // brain never picks it up, the card stays as it is and says so —
            // which is the truth. Flipping it to queued here would show him a
            // task moving that nothing is working on.
            return await write(job) {
                try await self.backend.pushEvent(kind: "app_reply", text: answer)
            }

        case .approval:
            // Record the yes ON the job: the browser agent reads it and finishes
            // the task, instead of stopping at the final button to ask again.
            return await write(job, expected: "queued") {
                if let fields = try self.approvalFields(for: job,
                                                        ownerAnswer: ownerAnswer) {
                    try await self.backend.setJobFields(id: job.id, fields: fields)
                } else {
                    var params = (try? JSONSerialization.jsonObject(with: Data(job.params.utf8)))
                        as? [String: Any] ?? [:]
                    params["authorized"] = true
                    try await self.backend.setJobFields(id: job.id, fields: [
                        "status": "queued", "params": try self.jsonString(params),
                    ])
                }
            }
        }
    }

    /// A failed workflow is immutable evidence. A retry is a new request and
    /// therefore becomes a fresh plan/card instead of rewriting history.
    func requestFreshRetry(_ job: AgentJob) async {
        inFlight.insert(job.id)
        defer { inFlight.remove(job.id) }
        await heard("Try this again as a fresh attempt: \(job.humanGoal)",
                    explicit: true)
    }

    @discardableResult
    /// Stop something that is already running, from the phone.
    ///
    /// There was no way to do this. HandlingCard had no controls at all, and
    /// the only stop control in the entire product was a button in the Chrome
    /// popup — on the laptop. Away from the desk, watching it head somewhere
    /// wrong, the owner could do precisely nothing about it.
    ///
    /// Same write path and same cancellation fields as "Not now", so a stop
    /// from the phone and a stop from the laptop mean exactly one thing to
    /// the rest of the system. The browser loop re-reads liveness immediately
    /// before every irreversible action, so this lands before a submit rather
    /// than after it.
    func stopRunning(_ job: AgentJob) async -> Bool {
        await write(job, expected: "cancelled") {
            var fields = try self.cancellationFields(
                for: job, trigger: "tapped Stop on the phone")
                ?? ["status": "cancelled"]
            // Never claim more than is known. If the browser had already
            // committed something when the stop landed, saying "nothing was
            // done" is the one sentence that could cost him a duplicate
            // booking he never checks for.
            fields["result"] = job.effect_uncertain == true
                ? "You stopped this. It may already have gone through before I stopped. Worth a check."
                : "You stopped this."
            try await self.backend.setJobFields(id: job.id, fields: fields)
        }
    }

    func decline(_ job: AgentJob) async -> Bool {
        await write(job, expected: "cancelled") {
            if let fields = try self.cancellationFields(
                for: job, trigger: "tapped Not now") {
                try await self.backend.setJobFields(id: job.id, fields: fields)
            } else {
                try await self.backend.setJobFields(id: job.id, fields: ["status": "cancelled"])
            }
        }
    }

    /// One place every write goes, so success is only ever claimed for a write
    /// the server actually accepted — and the haptic fires after that, not
    /// before the request leaves.
    ///
    /// Keyed by an arbitrary id rather than a job, because a question she
    /// asked outside any task is answerable too and its card needs the same
    /// sending/failed states. `inFlight` and `failedWrites` were always
    /// `Set<String>`; only the assumption that the string was a job id was
    /// ever job-shaped.
    private func write(id: String,
                       expected: String? = nil,
                       reconciling job: AgentJob? = nil,
                       _ body: @escaping () async throws -> Void) async -> Bool {
        inFlight.insert(id)
        failedWrites.remove(id)
        unverifiedWrites.remove(id)
        pendingJobWrites.removeValue(forKey: id)
        // Still a defer, for the throwing path and for any caller with no
        // expected status - removing it twice is harmless on a Set.
        defer { inFlight.remove(id) }
        do {
            try await body()
            Haptics.success()
            // THE SPINNER ENDS HERE, not after a reconciling fetch.
            //
            // This used to `await refresh()` before returning, with `inFlight`
            // held by a `defer` until the whole function finished - so one tap
            // cost TWO sequential round-trips of spinner (the write, then a
            // full re-fetch of jobs, events, transcript and reachability)
            // before anything on screen moved. On cellular that is seconds of
            // dead time on the single most-used control in the product, and it
            // is the whole of what "doesn't feel responsive" meant.
            //
            // The honesty rule is untouched: nothing is claimed until the server
            // has accepted. What changed is that the ALREADY-CONFIRMED result
            // is shown at once, and the reconciling read happens behind it.
            inFlight.remove(id)
            if let expected, let job {
                confirmedStatus[id] = ConfirmedJobStatus(
                    original: job.status, expected: expected)
            }
            Task { await refresh() }
            return true
        } catch {
            // Refused ON THE PHONE, before any request left it — a retry the
            // reconciliation floor would not let through, or a row the app
            // could not assemble a patch for. Nothing reached the server, so
            // there is nothing to reconcile against and no "Check outcome" to
            // offer; treating it as a lost response below would send the card
            // to look for a write that was never made.
            if error is WorkflowWriteError {
                failedWrites.insert(id)
                Haptics.warning()
                return false
            }
            if let refusal = error as? AnticipyBackend.BackendError,
               ActionWritePolicy.isVerifiedRefusal(status: refusal.status) {
                failedWrites.insert(id)
                Haptics.warning()
                return false
            }

            guard let job else {
                // An app_reply event has no job row whose status proves whether
                // the event landed. Do not turn response loss into a retry.
                unverifiedWrites.insert(id)
                Haptics.warning()
                return false
            }

            let pending = PendingJobWrite(originalStatus: job.status,
                                          expectedStatus: expected)
            pendingJobWrites[id] = pending
            // Give a PATCH whose response connection died a moment to finish
            // before asking PocketBase for the exact canonical row.
            try? await Task.sleep(nanoseconds: 500_000_000)
            let reconciliation = await reconcilePendingJob(id: id, pending: pending)
            switch reconciliation {
            case .accepted:
                Haptics.success()
                Task { await refresh() }
                return true
            case .safeToRetry:
                failedWrites.insert(id)
                Haptics.warning()
                return false
            case .unverified:
                unverifiedWrites.insert(id)
                Haptics.warning()
                return false
            }
        }
    }

    private func write(_ job: AgentJob,
                       expected: String? = nil,
                       _ body: @escaping () async throws -> Void) async -> Bool {
        await write(id: job.id, expected: expected, reconciling: job, body)
    }

    /// Re-read the exact row after a response-lost write. This is the only
    /// action exposed while an uncertain card is on screen; it never sends the
    /// mutation again.
    func reconcileWrite(_ job: AgentJob) async {
        guard let pending = pendingJobWrites[job.id],
              !inFlight.contains(job.id) else { return }
        inFlight.insert(job.id)
        defer { inFlight.remove(job.id) }
        switch await reconcilePendingJob(id: job.id, pending: pending) {
        case .accepted:
            Haptics.success()
            Task { await refresh() }
        case .safeToRetry:
            failedWrites.insert(job.id)
            Haptics.tap()
        case .unverified:
            unverifiedWrites.insert(job.id)
            Haptics.warning()
        }
    }

    private func reconcilePendingJob(
        id: String,
        pending: PendingJobWrite
    ) async -> ActionWritePolicy.Reconciliation {
        guard let fetched = try? await backend.fetchJob(id: id) else {
            return .unverified
        }
        if let index = jobs.firstIndex(where: { $0.id == fetched.id }) {
            jobs[index] = fetched
        }
        let result: ActionWritePolicy.Reconciliation
        if let expected = pending.expectedStatus {
            result = ActionWritePolicy.reconcile(
                originalStatus: pending.originalStatus,
                expectedStatus: expected,
                observedStatus: fetched.status)
        } else {
            result = fetched.status == pending.originalStatus ? .unverified : .accepted
        }
        switch result {
        case .accepted:
            confirmedStatus.removeValue(forKey: id)
            failedWrites.remove(id)
            unverifiedWrites.remove(id)
            pendingJobWrites.removeValue(forKey: id)
        case .safeToRetry:
            unverifiedWrites.remove(id)
            pendingJobWrites.removeValue(forKey: id)
        case .unverified:
            unverifiedWrites.insert(id)
        }
        return result
    }

    /// Answer a question she asked that has no task behind it — "Want me to
    /// book a table at Earls tonight?", "what is 'it' in this case?".
    ///
    /// Until now those were answerable ONLY by text. Production holds 17 of
    /// them and not one `app_reply` event has ever existed, so the app half of
    /// "he answers on whichever channel he likes" was never actually reachable:
    /// the question rendered as unanswerable prose, and a person holding the
    /// phone that heard the question had to go find a different app to reply in.
    ///
    /// One inbound turn, the same shape a text produces, so it lands on the one
    /// answer path (`handle_inbound` -> `on_reply`) and gets the same
    /// which-task-did-he-mean reasoning rather than a second implementation of
    /// it here.
    @discardableResult
    func answer(_ event: BrainEvent, text: String) async -> Bool {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        // The view disables Send for this, but the guard cannot only live in
        // the view: an empty answer would record a turn of nothing and mark her
        // question closed.
        guard !trimmed.isEmpty, isSignedIn,
              let pending = pendingAppReply(eventID: event.id)
                ?? AppReplyWritePolicy.pending(accountID: accountID,
                                               eventID: event.id) else { return false }
        return await writeAppReply(pending, text: trimmed)
    }

    /// A reply POST is not safe to retry from its transport error. Persist its
    /// durable identity before the request leaves, then resolve any uncertain
    /// completion by reading that exact owner-scoped event back.
    private func writeAppReply(_ pending: AppReplyWritePolicy.Pending,
                               text: String) async -> Bool {
        guard isSignedIn, accountID == pending.accountID else { return false }
        let id = pending.eventID
        let requestedAccount = accountID
        let requestedToken = authToken
        let b = backend

        rememberPendingAppReply(pending) // before the first network yield
        inFlight.insert(id)
        failedWrites.remove(id)
        unverifiedWrites.remove(id)
        defer { inFlight.remove(id) }

        do {
            try await b.pushEvent(kind: "app_reply", text: text,
                                  externalEventID: pending.externalEventID)
            guard isSignedIn, accountID == requestedAccount,
                  authToken == requestedToken else { return false }
            removePendingAppReply(pending)
            failedWrites.remove(id)
            unverifiedWrites.remove(id)
            Haptics.success()
            Task { await refresh() }
            return true
        } catch {
            guard isSignedIn, accountID == requestedAccount,
                  authToken == requestedToken else { return false }
            if let refusal = error as? AnticipyBackend.BackendError,
               ActionWritePolicy.isVerifiedRefusal(status: refusal.status) {
                // PocketBase reports a unique external_event_id collision as a
                // 400/409. That can mean the earlier response-lost request won,
                // so these two statuses still require the exact canonical read.
                if refusal.status == 400 || refusal.status == 409 {
                    let read = await canonicalAppReplyRead(pending, backend: b)
                    guard isSignedIn, accountID == requestedAccount,
                          authToken == requestedToken else { return false }
                    return applyAppReplyReconciliation(
                        AppReplyWritePolicy.reconcile(read), pending: pending)
                }
                // This request was refused before acceptance. Its stable id is
                // deterministic, so a later retry will still use the same one.
                removePendingAppReply(pending)
                failedWrites.insert(id)
                Haptics.warning()
                return false
            }

            // Give a request whose response connection died time to commit,
            // then ask for this durable id rather than guessing from the feed.
            try? await Task.sleep(nanoseconds: 500_000_000)
            guard isSignedIn, accountID == requestedAccount,
                  authToken == requestedToken else { return false }
            let read = await canonicalAppReplyRead(pending, backend: b)
            guard isSignedIn, accountID == requestedAccount,
                  authToken == requestedToken else { return false }
            return applyAppReplyReconciliation(
                AppReplyWritePolicy.reconcile(read), pending: pending)
        }
    }

    private func canonicalAppReplyRead(
        _ pending: AppReplyWritePolicy.Pending,
        backend: AnticipyBackend
    ) async -> AppReplyWritePolicy.CanonicalRead {
        do {
            return try await backend.hasEvent(
                kind: "app_reply", externalEventID: pending.externalEventID)
                ? .present : .absent
        } catch {
            return .unknown
        }
    }

    @discardableResult
    private func applyAppReplyReconciliation(
        _ result: AppReplyWritePolicy.Reconciliation,
        pending: AppReplyWritePolicy.Pending
    ) -> Bool {
        let id = pending.eventID
        switch result {
        case .accepted:
            removePendingAppReply(pending)
            failedWrites.remove(id)
            unverifiedWrites.remove(id)
            Haptics.success()
            Task { await refresh() }
            return true
        case .safeToRetry:
            removePendingAppReply(pending)
            unverifiedWrites.remove(id)
            failedWrites.insert(id)
            Haptics.warning()
            return false
        case .unverified:
            // Keep the persisted identity. A restart restores this card to the
            // same Check outcome state instead of silently enabling a resend.
            failedWrites.remove(id)
            unverifiedWrites.insert(id)
            Haptics.warning()
            return false
        }
    }

    /// Reconcile is the only action offered while outcome is unknown. It does
    /// not resend the person's words; it reads the exact idempotency row and
    /// turns the card into received, safe-to-retry, or still-unverified.
    func reconcileAnswer(_ event: BrainEvent) async {
        guard isSignedIn, !inFlight.contains(event.id),
              let pending = pendingAppReply(eventID: event.id) else { return }
        let requestedAccount = accountID
        let requestedToken = authToken
        let b = backend
        inFlight.insert(event.id)
        defer { inFlight.remove(event.id) }

        let read = await canonicalAppReplyRead(pending, backend: b)
        guard isSignedIn, accountID == requestedAccount,
              authToken == requestedToken else { return }
        _ = applyAppReplyReconciliation(
            AppReplyWritePolicy.reconcile(read), pending: pending)
    }

    /// Identity is the server event id (or a stable local id until the
    /// server echoes the line) so the 3s poll rebuild compares EQUAL for
    /// unchanged content — the feed animates only what actually changed
    /// instead of cross-fading wholesale every refresh.
    struct TranscriptLine: Identifiable, Equatable {
        let id: String
        let text: String
        let decision: String? // ignore | act | ask
        /// What she is quietly chasing because of this line. The brain
        /// stamps it even when the outward decision is "ignore" — that
        /// pairing (ignored, but with a goal) is the difference between
        /// "left alone" and "looking into it", which used to render
        /// identically and read as her being dead.
        var goal: String? = nil
        /// The conversation this line belongs to, from `events.segment`.
        /// Empty or nil means ungrouped, which means one card of one line —
        /// i.e. exactly the row this app already draws.
        ///
        /// Appended AFTER `goal`, with a default, so the synthesized
        /// memberwise init keeps every existing call site compiling and every
        /// local line keeps behaving as it does today.
        var segmentID: String? = nil
        /// PocketBase `created`, carried through so a card can show a clock
        /// time. Empty on local lines and on anything we could not read a date
        /// from; the time is then simply not drawn.
        var created: String = ""
        /// WHICH EARS heard this line, from `events.source`: "phone_mic",
        /// "pendant" or "typed". Nil means the row predates the field or the
        /// capture had no verdict to give, and nothing is drawn.
        ///
        /// Appended last with a default for the same reason `segmentID` was:
        /// the synthesized memberwise init keeps every existing call site
        /// compiling.
        var source: String? = nil
    }

    /// One line spoken in the current Listen session, tracked locally from
    /// the instant it leaves the recognizer until the server confirms it.
    struct SessionLine: Identifiable {
        let id = UUID()
        let text: String
        var received = false
        var decision: String?
    }
}
