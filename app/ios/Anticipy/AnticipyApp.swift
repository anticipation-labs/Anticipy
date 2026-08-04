import Combine
import SwiftUI

@main
struct AnticipyApp: App {
    @StateObject private var pendant = PendantManager()
    @StateObject private var session = AnticipySession()
    @AppStorage("hasOnboarded") private var hasOnboarded = false

    var body: some Scene {
        WindowGroup {
            Group {
                if !session.isSignedIn {
                    // The door comes first. Everything past it belongs to a
                    // person; nothing before it does.
                    AuthView()
                } else if hasOnboarded {
                    HomeView()
                } else {
                    OnboardingView()
                }
            }
            .environmentObject(pendant)
            .environmentObject(session)
            .preferredColorScheme(.dark)
            .tint(Theme.champagne)
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
    @Published var backendReachable = false
    @Published var agentOnline = false
    @Published var agentLastSeenSeconds: Int?   // nil = never seen
    @Published var agentPaired = false

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
    /// When we last threw away a refused key, so recovery retries at a sane
    /// pace rather than on every 3-second poll.
    private var lastTokenRecovery = Date.distantPast
    let listener = PhoneListener()

    /// Words spoken with no network used to live in a plain in-memory array.
    /// If iOS reclaimed the app before it reconnected, they were gone — from a
    /// product whose whole promise is remembering. Now they survive a relaunch.
    @AppStorage("unsentLines") private var unsentStore = ""
    private var unsent: [String] {
        get { unsentStore.isEmpty ? [] : (try? JSONDecoder().decode([String].self, from: Data(unsentStore.utf8))) ?? [] }
        set {
            unsentStore = (try? JSONEncoder().encode(newValue))
                .flatMap { String(data: $0, encoding: .utf8) } ?? ""
            pendingCount = newValue.count
        }
    }

    @AppStorage("serviceToken") private var serviceToken = ""
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
            serviceToken: serviceToken,
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
        listener.onLine = { [weak self] line in
            Task { await self?.heard(line) }
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
    func heard(_ line: String) async {
        // A typed line deserves an instant felt ack. Ambient listening does
        // NOT — buzzing on every finalized utterance all day is a phone that
        // won't stop twitching; the meaningful buzz is the act-verdict one.
        if !listener.isListening { Haptics.tap() }
        sessionLines.append(SessionLine(text: line))
        transcript.append(TranscriptLine(id: "local-\(UUID().uuidString)", text: line, decision: nil))
        do {
            try await backend.pushEvent(kind: "transcript", text: line)
        } catch {
            // A dropped push used to vanish into try? — the line then sat at
            // the top of the feed saying "Thinking…" forever while the brain
            // had never seen it. Queue it (on disk) and keep trying.
            unsent = unsent + [line]
        }
    }

    /// Re-push anything the network ate, oldest first. Whatever still fails
    /// goes straight back to disk rather than evaporating.
    private func flushUnsent() async {
        guard backendReachable, !unsent.isEmpty else { return }
        let queue = unsent
        unsent = []
        var failed: [String] = []
        for line in queue {
            do { try await backend.pushEvent(kind: "transcript", text: line) }
            catch { failed.append(line) }
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
            jobs = try await b.fetchJobs(owner: ownerID)
            connection = .ready
        } catch let e as AnticipyBackend.BackendError {
            connection = .refused(e.status)
            // Being turned away is RECOVERABLE, and the app used to have no way
            // to recover: the key was fetched only `if serviceToken.isEmpty`, so
            // a key that was stale, rotated on the server, or saved wrong could
            // never be replaced. Every read 403'd forever and the only fix was
            // deleting the app. Throw the bad key away so the fetch below can
            // get a fresh one — rate-limited, so a genuinely rejected key
            // retries occasionally instead of hammering every 3 seconds.
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
                if Date().timeIntervalSince(lastTokenRecovery) > 60 {
                    lastTokenRecovery = Date()
                    serviceToken = ""
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
                .map { TranscriptLine(id: $0.id, text: $0.text ?? "", decision: ($0.decision?.isEmpty == false) ? $0.decision : nil) }
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
            // Pick up the shared write token once paired, so this phone keeps
            // writing when backend enforcement is switched on.
            if agentPaired, serviceToken.isEmpty,
               let t = await b.fetchServiceToken(agentID: agent.agent_id) {
                serviceToken = t
            }
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

    func startListening() {
        // keepListening is only armed once the mic is actually ours. Setting it
        // first meant a refused permission was remembered as "she should be
        // listening", so every foreground re-fired a start iOS instantly denies.
        listener.start()
        keepListening = true
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
        } catch let err as AnticipyBackend.BackendError where err.status == 400 {
            return "That email already has an account — sign in instead, or use another address."
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

    static func parsePBDate(_ s: String) -> Date? {
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
    /// Jobs with a write in flight — the card disables itself, so a tap that
    /// looks like it did nothing can't be tapped again into a double send.
    @Published var inFlight: Set<String> = []

    @discardableResult
    func confirm(_ job: AgentJob) async -> Bool {
        // Record the yes ON the job: the browser agent reads it and finishes
        // the task, instead of stopping at the final button to ask again.
        var params = (try? JSONSerialization.jsonObject(with: Data(job.params.utf8)))
            as? [String: Any] ?? [:]
        params["authorized"] = true
        let json = (try? JSONSerialization.data(withJSONObject: params))
            .flatMap { String(data: $0, encoding: .utf8) }
        return await write(job) {
            try await self.backend.setJobStatus(id: job.id, status: "queued", params: json)
        }
    }

    @discardableResult
    func decline(_ job: AgentJob) async -> Bool {
        await write(job) {
            try await self.backend.setJobStatus(id: job.id, status: "cancelled")
        }
    }

    /// One place every job write goes, so success is only ever claimed for a
    /// write the server actually accepted — and the haptic fires after that,
    /// not before the request leaves.
    private func write(_ job: AgentJob, _ body: @escaping () async throws -> Void) async -> Bool {
        inFlight.insert(job.id)
        failedWrites.remove(job.id)
        defer { inFlight.remove(job.id) }
        do {
            try await body()
            Haptics.success()
            await refresh()
            return true
        } catch {
            failedWrites.insert(job.id)
            Haptics.warning()
            return false
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
