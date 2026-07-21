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

    @AppStorage("backendURL") var backendURLString = "http://127.0.0.1:8090"

    private var pollTask: Task<Void, Never>?

    var backend: AnticipyBackend {
        AnticipyBackend(
            baseURL: URL(string: backendURLString) ?? URL(string: "http://127.0.0.1:8090")!,
            deviceID: "iphone"
        )
    }

    init() {
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
            // The agent is "online" if any job moved past queued recently.
            agentOnline = fetched.contains { $0.status != "queued" && $0.status != "cancelled" }
        }
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
