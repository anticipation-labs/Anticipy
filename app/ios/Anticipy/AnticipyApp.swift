import SwiftUI

@main
struct AnticipyApp: App {
    @StateObject private var pendant = PendantManager()
    @StateObject private var session = AnticipySession()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(pendant)
                .environmentObject(session)
                .preferredColorScheme(.dark)
        }
    }
}

/// App-level state: transcript, decisions, confirm cards.
final class AnticipySession: ObservableObject {
    @Published var transcript: [TranscriptLine] = []
    @Published var pendingConfirms: [ConfirmCard] = []
    @Published var paired = false
    @Published var batteryPercent: Int?

    struct TranscriptLine: Identifiable {
        let id = UUID()
        let text: String
        let decision: String? // ignore | act | ask
        let date = Date()
    }

    struct ConfirmCard: Identifiable {
        let id = UUID()
        let goal: String
        let summary: String
    }
}
