import Combine
import CryptoKit
import SwiftUI

@main
struct AnticipyApp: App {
    @StateObject private var pendant = PendantManager()
    @StateObject private var session = AnticipySession()
    @AppStorage("hasOnboarded") private var hasOnboarded = false
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

    var body: some Scene {
        WindowGroup {
            Group {
                if !session.isSignedIn {
                    // The door comes first. Everything past it belongs to a
                    // person; nothing before it does.
                    AuthView()
                        .transition(.opacity)
                } else if hasOnboarded {
                    HomeView()
                        .transition(.opacity)
                } else {
                    OnboardingView(onFinished: {
                        // Order matters, and it is the whole fix: write the
                        // durable fact FIRST, then decorate. The old code did
                        // it the other way round — the flag was the last line
                        // of a 2.4s animation — so an interrupted animation
                        // meant doing all five steps again.
                        hasOnboarded = true
                        celebrating = true
                    })
                    .transition(.opacity)
                }
            }
            .overlay {
                if celebrating {
                    OnboardingFinale { celebrating = false }
                }
            }
            // The three biggest state changes in the product used to hard-cut.
            .animation(Theme.springSlow, value: session.isSignedIn)
            .animation(Theme.springSlow, value: hasOnboarded)
            .environmentObject(pendant)
            .environmentObject(session)
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
    static let expectedExtensionVersion = "0.11.0"

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

    @AppStorage("backendURL") var backendURLString = "https://backend-production-61e0a.up.railway.app"
    @AppStorage("ownerID") var ownerID = ""
    /// Listening is a STANDING state, not a per-open chore: once you turn it
    /// on, she keeps it on — across backgrounds and relaunches — until you
    /// turn it off. This is "knowing when to start" without ever surprising
    /// you: the only hand on the switch is yours.
    @AppStorage("keepListening") var keepListening = false

    private var pollTask: Task<Void, Never>?
    private var bag = Set<AnyCancellable>()
    private var seenDoneJobIDs = Set<String>()
    let listener = PhoneListener()
    private let pendantTranscriber = TranscriberClient()
    private var pendantTokenInFlight = false
    private var pendantRetryTask: Task<Void, Never>?

    /// Words spoken with no network used to live in a plain in-memory array.
    /// If iOS reclaimed the app before it reconnected, they were gone — from a
    /// product whose whole promise is remembering. Now they survive a relaunch.
    private struct BufferedLine: Codable {
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
            unsentStore = (try? JSONEncoder().encode(newValue))
                .flatMap { String(data: $0, encoding: .utf8) } ?? ""
            pendingCount = newValue.count
        }
    }

    @AppStorage("ownerPhone") var ownerPhone = ""
    @AppStorage("ownerFirstName") var ownerFirstName = ""
    @AppStorage("ownerLastName") var ownerLastName = ""
    @AppStorage("ownerEmail") var ownerEmail = ""
    @AppStorage("ownerBirthday") var ownerBirthday = ""

    var backend: AnticipyBackend {
        AnticipyBackend(
            baseURL: URL(string: backendURLString) ?? URL(string: "https://backend-production-61e0a.up.railway.app")!,
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
        if ownerID.isEmpty { ownerID = UUID().uuidString }
        // Seed from disk. The count is otherwise only written by the `unsent`
        // setter, so a relaunch with lines still queued reported "0 waiting"
        // until the next failed push — and the screens that reassure you your
        // words survived read exactly this number.
        pendingCount = unsent.count
        listener.onLine = { [weak self] line, at, continues in
            Task { await self?.heard(line, from: .phoneMic, at: at,
                                     continuesPrevious: continues) }
        }
        // The on-device voice check rides with each line. It only engages
        // when a model is present AND he has enrolled; otherwise every line
        // travels bare, exactly as before.
        listener.speaker = speakerTagger
        listener.onSpeaker = { [weak self] line, tag, at, continues in
            Task { await self?.heard(line, speaker: tag, from: .phoneMic, at: at,
                                     continuesPrevious: continues) }
        }
        pendantTranscriber.onTranscript = { [weak self] line in
            Task { await self?.heard(line, from: .pendant) }
        }
        pendantTranscriber.onConnection = { [weak self] connected in
            self?.pendantCapturing = connected
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
    enum LineSource {
        case typed, phoneMic, pendant

        /// The stable name that goes on the wire and stays greppable in
        /// production. Deliberately not `String(describing:)` — renaming a
        /// Swift case must never silently re-label a year of history.
        var wireName: String {
            switch self {
            case .typed: return "typed"
            case .phoneMic: return "phone_mic"
            case .pendant: return "pendant"
            }
        }
    }

    /// The id of the last transcript row this session created, so a line the
    /// clock cut in half can say what it carries on from.
    ///
    /// Deliberately not persisted: a parent from a previous launch is a
    /// sentence nobody is still speaking, and linking onto it would chain two
    /// unrelated conversations into one.
    private var lastTranscriptEventID = ""

    /// `at` is when the words were spoken, which is not when this runs for
    /// anything the phone buffered. `continuesPrevious` is true only when the
    /// ceiling cut a sentence in half.
    func heard(_ line: String, speaker: String? = nil,
               explicit: Bool = false,
               from source: LineSource = .typed,
               at capturedAt: Date = Date(),
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
        do {
            let id = try await backend.pushEvent(kind: "transcript", text: line,
                                        speaker: speaker, explicit: explicit,
                                        source: source.wireName,
                                        capturedAt: capturedAt,
                                        parentLine: parent)
            if !id.isEmpty { lastTranscriptEventID = id }
            ListenJournal.shared.record(.posted(ok: true, detail: source.wireName))
        } catch {
            // A dropped push used to vanish into try? — the line then sat at
            // the top of the feed saying "Thinking…" forever while the brain
            // had never seen it. Queue it (on disk) and keep trying.
            ListenJournal.shared.record(
                .posted(ok: false, detail: "queued, \(Self.postFailureShape(error))"))
            unsent = unsent + [BufferedLine(text: line, explicit: explicit,
                                            speaker: speaker,
                                            source: source.wireName,
                                            account: accountID,
                                            capturedAt: capturedAt,
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
    static func postFailureShape(_ error: Error) -> String {
        if let refusal = error as? AnticipyBackend.BackendError {
            return "http \(refusal.status)"
        }
        let ns = error as NSError
        return "\(ns.domain) \(ns.code)"
    }

    /// Re-push anything the network ate, oldest first. Whatever still fails
    /// goes straight back to disk rather than evaporating.
    private func flushUnsent() async {
        guard backendReachable, !unsent.isEmpty, !accountID.isEmpty else { return }
        let queue = unsent
        unsent = []
        var failed: [BufferedLine] = []
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
            // attributed, so it is dropped rather than guessed at.
            guard line.account == accountID else {
                previousInThisFlush = ""
                continue
            }
            let parent = line.continuesPrevious == true ? previousInThisFlush : ""
            do {
                let id = try await backend.pushEvent(kind: "transcript", text: line.text,
                                            speaker: line.speaker,
                                            explicit: line.explicit,
                                            source: line.source,
                                            capturedAt: line.capturedAt,
                                            parentLine: parent)
                if !id.isEmpty { lastTranscriptEventID = id }
                // An unreadable id is a broken link, not a guessable one.
                previousInThisFlush = id
                ListenJournal.shared.record(.posted(ok: true, detail: "queued line sent"))
            }
            catch {
                ListenJournal.shared.record(
                    .posted(ok: false, detail: "requeued, \(Self.postFailureShape(error))"))
                previousInThisFlush = ""
                failed.append(line)
            }
        }
        if !failed.isEmpty { unsent = failed + unsent }
    }

    /// Anticipy's latest spoken line, only while it's actually fresh — a
    /// remark from an hour ago rereading itself forever feels haunted.
    /// An unparseable date shows the line rather than silently killing the
    /// feature on a backend format drift; only a parsed-and-stale date hides it.
    var freshAnticipySays: String? {
        guard let ev = anticipySays.first,
              let text = ev.text, !text.isEmpty else { return nil }
        if let date = Self.parsePBDate(ev.created),
           Date().timeIntervalSince(date) >= 15 * 60 { return nil }
        return text
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

    func refresh() async {
        let b = backend
        backendReachable = await b.isReachable()
        guard backendReachable else {
            agentOnline = false
            connection = .offline
            return
        }
        await flushUnsent()
        // /api/health is NOT behind the guard hook, so "reachable" says nothing
        // about whether our reads are allowed. Only a real read can promote us
        // to .ready — otherwise the app reports itself perfectly healthy while
        // every read is being refused.
        do {
            let fetched = try await b.fetchJobs(owner: ownerID)
            // Retire each held value the moment the server says the same thing,
            // so this can never pin a stale status indefinitely - the overlay
            // survives exactly as long as the disagreement does.
            for job in fetched where confirmedStatus[job.id] == job.status {
                confirmedStatus.removeValue(forKey: job.id)
            }
            jobs = fetched.map { job in
                guard let held = confirmedStatus[job.id] else { return job }
                return job.withStatus(held)
            }
            connection = .ready
            // Raised from the poll on purpose: the app keeps running while it
            // listens (background audio), so a local notification from here
            // reaches a locked screen without a push server.
            await notifier.announce(jobs: jobs)
        } catch let e as AnticipyBackend.BackendError {
            connection = .refused(e.status)
            if e.status == 401 || e.status == 403 {
                // A signed-in session that is being refused is over — the
                // account was deleted, or the token expired (PocketBase issues
                // 7-day tokens). Put them back at the door rather than leaving
                // them staring at "Anticipy won't let me in" with no way
                // forward. Seen for real in the simulator: an account removed
                // server-side left the app in a permanent refused state.
                if !authToken.isEmpty {
                    signOut()
                    return
                }
            }
        } catch {
            connection = .offline
        }
        if let events = try? await b.fetchEvents() {
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
        if let agent = try? await b.fetchAgent(owner: ownerID) {
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
    /// Returns nil when it isn't a complete number yet.
    nonisolated func e164(_ raw: String) -> String? {
        let digits = raw.filter(\.isNumber)
        guard digits.count >= 10 else { return nil }
        if raw.hasPrefix("+") { return "+" + digits }
        if digits.count == 10 { return "+1" + digits }        // NANP local
        if digits.count == 11, digits.hasPrefix("1") { return "+" + digits }
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
        await backend.claimLegacy(legacyUUID: ownerID)
        await reportTimeZone()
        await refresh()
    }

    /// Save the owner's number where the brain can read it, so texting works
    /// without anyone hand-editing a server variable.
    func saveOwnerPhone(_ raw: String) async -> Bool {
        guard let e = e164(raw) else { return false }
        let ok = await backend.upsertOwnerPhone(ownerID: ownerID, phone: e)
        if ok { ownerPhone = e }
        return ok
    }

    /// Her one record of who you are — used to fill the name/email/phone that
    /// every booking form asks for. Payment details are never stored here.
    func saveOwnerDetails(first: String, last: String, email: String, birthday: String = "") async -> Bool {
        let ok = await backend.upsertOwner(ownerID: ownerID, fields: [
            "first_name": first.trimmingCharacters(in: .whitespaces),
            "last_name": last.trimmingCharacters(in: .whitespaces),
            "email": email.trimmingCharacters(in: .whitespaces),
            "birthday": birthday.trimmingCharacters(in: .whitespaces),
        ])
        if ok {
            ownerFirstName = first; ownerLastName = last; ownerEmail = email
            if !birthday.isEmpty { ownerBirthday = birthday }
        }
        return ok
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
        do {
            let (status, _) = try await backend.deleteAccount()
            switch status {
            case 200:
                return (true, "Done. It's gone, and so is your account.")
            case 409:
                return (false, "I deleted your data but couldn't close the account. What's gone stays gone. Try again.")
            case 401, 403:
                return (false, "I couldn't prove it was you. Sign out, sign back in, and ask again.")
            default:
                return (false, "I couldn't finish, so I stopped rather than tell you I had. Nothing was half-deleted. Try again.")
            }
        } catch {
            return (false, "I couldn't reach my side. Nothing was deleted.")
        }
    }

    func startListening() {
        // keepListening is only armed once the mic is actually ours. Setting it
        // first meant a refused permission was remembered as "she should be
        // listening", so every foreground re-fired a start iOS instantly denies.
        listener.start()
        keepListening = true
    }

    /// Pendant frames follow a separate, honest path: BLE Opus -> Deepgram
    /// websocket -> finalized text -> the same durable brain event as phone
    /// speech. The app receives only a 60-second JWT, never the vendor key.
    func startPendantTranscription(_ pendant: PendantManager) async {
        guard isSignedIn, pendant.state == .connected,
              !pendantTokenInFlight, !pendantCapturing else { return }
        pendantRetryTask?.cancel()
        let transcriber = pendantTranscriber
        pendant.onOpusFrame = { frame in transcriber.send(opusFrame: frame) }
        pendantTranscriber.onNeedsReconnect = { [weak self, weak pendant] in
            guard let self, let pendant else { return }
            self.schedulePendantRetry(pendant)
        }
        pendantTokenInFlight = true
        defer { pendantTokenInFlight = false }
        do {
            let token = try await backend.transcriptionToken()
            guard pendant.state == .connected, isSignedIn else { return }
            pendantTranscriber.connect(accessToken: token)
        } catch {
            pendantCapturing = false
            schedulePendantRetry(pendant)
        }
    }

    func stopPendantTranscription(_ pendant: PendantManager) {
        pendantRetryTask?.cancel()
        pendantRetryTask = nil
        pendant.onOpusFrame = nil
        pendantTranscriber.onNeedsReconnect = nil
        pendantTranscriber.disconnect()
        pendantTokenInFlight = false
        pendantCapturing = false
    }

    private func schedulePendantRetry(_ pendant: PendantManager) {
        guard isSignedIn, pendant.state == .connected else { return }
        pendantRetryTask?.cancel()
        pendantRetryTask = Task { [weak self, weak pendant] in
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            guard !Task.isCancelled, let self, let pendant else { return }
            await self.startPendantTranscription(pendant)
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
    var isSignedIn: Bool { !accountID.isEmpty && !authToken.isEmpty }

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
            authToken = token
            accountID = id
            // The account email is already a verified fact from the auth
            // boundary. Carry it straight into onboarding/profile defaults;
            // otherwise a new customer sees the literal placeholder
            // "you@example.com" after signing up with their real address.
            ownerEmail = email.trimmingCharacters(in: .whitespaces).lowercased()
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
        // CLOSE THE EARS. signOut cleared the credentials and nothing else:
        // the AVAudioEngine tap stayed installed and the room kept being
        // transcribed behind the sign-in door. The views that normally stop
        // the microphone are torn down the instant isSignedIn flips, so
        // nothing was left to do it. keepListening stays as the person's
        // standing preference — it is honoured again when they sign back in.
        listener.stop()
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
        pendingCount = unsent.count
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
        unsent = []
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
    func resumeListeningIfWanted() {
        if keepListening, !listener.isListening { listener.start() }
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
    private var confirmedStatus: [String: String] = [:]
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
        let ownerWords = job.effect_uncertain == true
            ? "I checked the site; the action did not happen. Try again."
            : (job.status == "needs_user" ? answer : "Tapped “Send it”.")
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
            let reconciliation: [String: Any] = [
                "effect_key": effectKey,
                "conclusion": "not_applied",
                "verified": true,
                "owner_words": ownerWords,
                "evidence": ["owner explicitly checked the destination before retry"],
                "recorded_at": now,
            ]
            fields["reconciliation"] = try jsonString(reconciliation)
        } else {
            fields["reconciliation"] = ""
        }
        return fields
    }

    /// Deterministic, not model-judged: does this answer END the errand?
    /// Returns the honest result line to store, or nil to proceed normally.
    ///
    /// Ending an errand is not a cheap guess: it writes the job cancelled and
    /// files the owner's own sentence as the evidence they called it off, so a
    /// wrong hit puts words in their mouth in the ledger. Returning nil is not
    /// "act blindly" — the answer rides up as a fact on the plan and the brain
    /// reads it. So anything short of an unmistakable stop goes there.
    // ANCHOR: end-of-errand decision. Everything down to the END marker is
    // compiled and exercised on its own by Tests/run_end_errand_tests.sh, so
    // it must stay pure Foundation and self-contained.
    static func answerThatEndsTheErrand(_ answer: String) -> String? {
        let normalized = answer.lowercased()
            .replacingOccurrences(of: "’", with: "'")
            .trimmingCharacters(in: .punctuationCharacters.union(.whitespaces))
        guard !normalized.isEmpty else { return nil }
        let whole: Set<String> = [
            "no", "nope", "stop", "cancel", "skip", "skip it", "never mind",
            "nevermind", "forget it", "drop it", "leave it", "don't bother",
            "dont bother", "call it off", "not anymore",
        ]
        let declines = [
            "never mind", "nevermind", "forget it", "don't bother",
            "dont bother", "no longer need", "don't need", "dont need",
            "do not need", "not needed", "drop it", "skip it", "skip this",
            "call it off", "don't do it", "dont do it", "cancel it",
            "cancel that", "cancel this", "stop it", "leave it",
        ]
        let handled = [
            "handled it", "i handled", "did it myself", "took care of it",
            "already did", "already done", "already handled", "already booked",
            "already sent", "already ordered", "done it myself",
            "did that myself", "sorted it", "i did it already",
        ]
        // A DECLINE IS THE WHOLE ANSWER, NOT A PHRASE BURIED IN ONE.
        // Substring matching anywhere in the text killed errands the owner
        // still wanted: "leave it with the concierge" (leave it), "drop it off
        // at reception after 5" (drop it), "stop it from auto-renewing"
        // (stop it), and — worst — "it's not already booked yet, go ahead",
        // where a NEGATED phrase filed the owner's go-ahead as proof they had
        // done it themselves. Capping the answer at eight words didn't fix any
        // of those: they are all short. Length was never the condition.
        //
        // The condition is position. A stop leads its clause, and nothing but
        // filler follows it — "ok, forget it", "already sent it, thanks". The
        // moment real content follows ("with the concierge", "off at
        // reception", "from auto-renewing"), the sentence is an instruction,
        // not a stop, and it belongs to the brain. Anchoring at the front is
        // also what makes the negation case safe for free: "not already
        // booked" does not start with "already booked".
        let clauses = normalized
            .split(whereSeparator: { ",;:!?\n\u{2014}\u{2013}".contains($0) })
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        // A CONDITION IS NOT A STOP. "if they're full, skip it" leads a clause
        // with a decline and means the opposite of one: it hands back a
        // judgment call, which is the brain's job and not a lookup table's.
        let spokenWords = Set(normalized
            .split(whereSeparator: { !$0.isLetter && $0 != "'" })
            .map(String.init))
        guard spokenWords.isDisjoint(with: ["if", "unless", "otherwise", "whether"])
        else { return nil }
        // What a person puts in FRONT of the real answer, and what can trail it
        // without changing it. Deliberately short lists of pure filler: every
        // word that carries meaning has to fall outside them, because a word
        // that carries meaning is exactly the signal that this is not a stop.
        let openers: Set<String> = [
            "ok", "okay", "oh", "well", "so", "and", "but", "then", "actually",
            "just", "please", "sorry", "yeah", "yea", "yep", "yes", "sure",
            "no", "nah", "i", "we", "it", "it's", "its", "that", "that's",
            "thats", "hey", "um", "uh",
        ]
        let trailers: Set<String> = [
            "it", "that", "this", "them", "already", "myself", "please",
            "thanks", "thank", "you", "now", "for", "anymore", "any", "more",
            "though", "anyway", "too", "sorry", "then", "ok", "okay",
        ]
        func leads(_ clause: String, _ phrases: [String]) -> Bool {
            var words = clause.split(separator: " ").map(String.init)
            while !words.isEmpty {
                let rest = words.joined(separator: " ")
                for phrase in phrases
                where rest == phrase || rest.hasPrefix(phrase + " ") {
                    let tail = rest.dropFirst(phrase.count)
                        .split(separator: " ").map(String.init)
                    if tail.allSatisfy(trailers.contains) { return true }
                }
                // Only filler may be stepped over. The first word that means
                // something ends the search, so "don't cancel it" can never
                // reach the "cancel it" sitting one word inside it.
                guard openers.contains(words[0]) else { return false }
                words.removeFirst()
            }
            return false
        }
        if clauses.contains(where: { leads($0, handled) }) {
            return "You handled it yourself: \u{201C}\(answer)\u{201D}. I did nothing further."
        }
        if whole.contains(normalized) || clauses.contains(where: { leads($0, declines) }) {
            return "You called it off: \u{201C}\(answer)\u{201D}. I did nothing further."
        }
        return nil
    }
    // END ANCHOR: end-of-errand decision

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
        // "Type what I need — or say you handled it." Both halves now go
        // somewhere honest, and they are different places (AnswerRoutePolicy):
        //
        // An answer that ENDS the errand ends it here, deterministically, on the
        // same cancellation path as "Not now" — because EVERY non-empty answer
        // used to requeue the run, so "skip it, I don't need the batteries
        // anymore" relaunched it, Bing-searched those exact words and hit a
        // CAPTCHA (found live, 2026-08-14).
        //
        // A real ANSWER goes to the brain instead of onto the job. Writing it
        // here would be a second path to a decision the text lane already owns
        // (brief ex 120): it skips whether the answer covers what the task said
        // it needed, skips keeping what he said about himself, and skips
        // deciding which task he meant when two are blocked — the 2026-08-02
        // failure, where an answer arrived and resolved nothing.
        let trimmed = ownerAnswer?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        switch AnswerRoutePolicy.route(
            status: job.status,
            effectUncertain: job.effect_uncertain == true,
            answer: trimmed,
            endsTheErrand: Self.answerThatEndsTheErrand(trimmed)) {

        case .nothingToSend:
            return false

        case .endTheErrand(let ending):
            return await write(job, expected: "cancelled") {
                var fields = try self.cancellationFields(
                    for: job, trigger: "their answer read as ending it")
                    ?? ["status": "cancelled"]
                fields["result"] = ending
                try await self.backend.setJobFields(id: job.id, fields: fields)
            }

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
                       _ body: @escaping () async throws -> Void) async -> Bool {
        inFlight.insert(id)
        failedWrites.remove(id)
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
            if let expected { confirmedStatus[id] = expected }
            Task { await refresh() }
            return true
        } catch {
            failedWrites.insert(id)
            Haptics.warning()
            return false
        }
    }

    private func write(_ job: AgentJob,
                       expected: String? = nil,
                       _ body: @escaping () async throws -> Void) async -> Bool {
        await write(id: job.id, expected: expected, body)
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
        guard !trimmed.isEmpty else { return false }
        return await write(id: event.id) {
            try await self.backend.pushEvent(kind: "app_reply", text: trimmed)
        }
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
