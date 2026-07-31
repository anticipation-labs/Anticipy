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
                if hasOnboarded {
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

    @AppStorage("backendURL") var backendURLString = "https://backend-production-61e0a.up.railway.app"
    @AppStorage("ownerID") var ownerID = ""

    private var pollTask: Task<Void, Never>?
    private var bag = Set<AnyCancellable>()
    private var seenDoneJobIDs = Set<String>()
    let listener = PhoneListener()

    var backend: AnticipyBackend {
        AnticipyBackend(
            baseURL: URL(string: backendURLString) ?? URL(string: "https://backend-production-61e0a.up.railway.app")!,
            deviceID: "iphone"
        )
    }

    init() {
        if ownerID.isEmpty { ownerID = UUID().uuidString }
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
        try? await backend.pushEvent(kind: "transcript", text: line)
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
            return
        }
        if let fetched = try? await b.fetchJobs() {
            jobs = fetched
        }
        if let events = try? await b.fetchEvents() {
            // Server view of the stream: heard lines with the brain's verdict,
            // plus everything Anticipy said/texted back.
            var serverLines = events
                .filter { $0.kind == "transcript" }
                .reversed()
                .map { TranscriptLine(id: $0.id, text: $0.text ?? "", decision: ($0.decision?.isEmpty == false) ? $0.decision : nil) }
            let serverTexts = Set(serverLines.map(\.text))
            // Reconcile the local session view: mark lines the server has
            // received, carry the brain's verdict back, and buzz once when a
            // decision lands as "act" so being heard is something you FEEL.
            for i in sessionLines.indices {
                if serverTexts.contains(sessionLines[i].text) {
                    sessionLines[i].received = true
                    let decision = serverLines.last { $0.text == sessionLines[i].text }?.decision
                    if decision != nil, sessionLines[i].decision == nil {
                        sessionLines[i].decision = decision
                        if decision == "act" { Haptics.engage() }
                    }
                }
            }
            // Never let a just-spoken line vanish: anything local the server
            // hasn't echoed yet stays at the end of the feed.
            serverLines.append(contentsOf: transcript.filter { $0.decision == nil && !serverTexts.contains($0.text) })
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

    /// Pair with the browser agent using the extension's 6-digit code.
    func pairAgent(code: String) async -> Bool {
        let ok = (try? await backend.pairAgent(code: code, owner: ownerID)) ?? false
        if ok { await refresh() }
        return ok
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

    func confirm(_ job: AgentJob) async {
        try? await backend.setJobStatus(id: job.id, status: "queued")
        await refresh()
    }

    func decline(_ job: AgentJob) async {
        try? await backend.setJobStatus(id: job.id, status: "cancelled")
        await refresh()
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
