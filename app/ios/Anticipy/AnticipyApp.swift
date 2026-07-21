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
    @Published var jobs: [AgentJob] = []
    @Published var backendReachable = false
    @Published var agentOnline = false
    @Published var agentLastSeenSeconds: Int?   // nil = never seen
    @Published var agentPaired = false

    @AppStorage("backendURL") var backendURLString = "http://127.0.0.1:8090"
    @AppStorage("ownerID") var ownerID = ""

    private var pollTask: Task<Void, Never>?

    var backend: AnticipyBackend {
        AnticipyBackend(
            baseURL: URL(string: backendURLString) ?? URL(string: "http://127.0.0.1:8090")!,
            deviceID: "iphone"
        )
    }

    init() {
        if ownerID.isEmpty { ownerID = UUID().uuidString }
        startPolling()
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

    struct TranscriptLine: Identifiable {
        let id = UUID()
        let text: String
        let decision: String? // ignore | act | ask
        let date = Date()
    }
}
