import SwiftUI

/// Authenticated, local-only internals for reproducing a field failure. This
/// view reveals state the app already holds; it adds no control that can change
/// the backend, browser, jobs, or action policy.
struct DeveloperDiagnosticsView: View {
    @ObservedObject var session: AnticipySession
    @Environment(\.dismiss) private var dismiss
    @AppStorage(AppPreferences.developerModeKey) private var developerMode = false

    @State private var route: Route?
    @State private var browserReport = "Loading…"
    @State private var refreshing = false

    private enum Route: Hashable {
        case speechStream, listeningActivity, listeningHistory
    }

    var body: some View {
        SheetChrome(title: "Developer Diagnostics", leading: .back) {
            dismiss()
        } content: {
            SectionHeader("Build")
            GroupedCard {
                StateRow("App", systemImage: "hammer", state: build)
                StateRow("Backend host", systemImage: "server.rack", state: backendHost)
                StateRow("Connection", state: connection)
            }

            SectionHeader("Browser hand")
            GroupedCard {
                StateRow("Paired", systemImage: "link",
                         state: session.agentPaired ? "Yes" : "No")
                StateRow("Online", state: session.agentOnline ? "Yes" : "No")
                if let seconds = session.agentLastSeenSeconds {
                    StateRow("Last heartbeat", state: "\(PlainDuration.words(seconds)) ago")
                }
                InfoRow(browserReport,
                        title: "Browser and extension version",
                        systemImage: "safari")
                StateRow("Expected extension",
                         state: AnticipySession.expectedExtensionVersion)
            }

            SectionHeader("Local queue and jobs")
            GroupedCard {
                StateRow("Speech waiting to upload",
                         systemImage: "arrow.up.circle",
                         state: String(session.pendingCount))
                StateRow("Jobs loaded", systemImage: "tray.full",
                         state: String(session.jobs.count))
                InfoRow(jobStates, title: "Loaded job states")
            }

            SectionHeader("Inspect")
            GroupedCard {
                NavRow("Developer speech stream", systemImage: "waveform.and.mic") {
                    Haptics.engage()
                    route = .speechStream
                }
                NavRow("Listening activity", systemImage: "list.bullet.rectangle") {
                    Haptics.engage()
                    route = .listeningActivity
                }
                NavRow("Listening history", systemImage: "text.bubble") {
                    Haptics.engage()
                    route = .listeningHistory
                }
            }

            GroupedCard {
                ActionRow(refreshing ? "Refreshing…" : "Refresh diagnostics",
                          systemImage: "arrow.clockwise",
                          isEnabled: !refreshing) {
                    refresh()
                }
                ActionRow("Turn off developer mode",
                          systemImage: "lock") {
                    developerMode = false
                    dismiss()
                }
            }

            FootnoteText("Developer mode changes what this iPhone shows, not what Anticipy is allowed to access or do.")
        }
        .navigationDestination(isPresented: Binding(
            get: { route != nil },
            set: { if !$0 { route = nil } }
        )) {
            switch route {
            case .speechStream:
                DeveloperSpeechStreamView(session: session)
            case .listeningActivity:
                ListeningDiagnosticsView()
            case .listeningHistory:
                ListeningHistoryView(session: session)
            case nil:
                EmptyView()
            }
        }
        .task(id: session.ownerID) {
            await loadBrowserReport()
        }
    }

    private var build: String {
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
        let number = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "?"
        return "\(version) (\(number))"
    }

    private var backendHost: String {
        URL(string: session.backendURLString)?.host ?? session.backendURLString
    }

    private var connection: String {
        switch session.connection {
        case .loading: return "Loading"
        case .ready: return "Ready"
        case .offline: return "Offline"
        case let .refused(status): return "Refused (HTTP \(status))"
        }
    }

    private var jobStates: String {
        guard !session.jobs.isEmpty else { return "No jobs are loaded." }
        let counts = Dictionary(grouping: session.jobs, by: \AgentJob.status)
            .mapValues(\.count)
        return counts.keys.sorted().map { "\($0): \(counts[$0] ?? 0)" }
            .joined(separator: " · ")
    }

    private func refresh() {
        guard !refreshing else { return }
        refreshing = true
        Task {
            await session.refresh()
            await loadBrowserReport()
            refreshing = false
        }
    }

    private func loadBrowserReport() async {
        do {
            guard let agent = try await session.backend.fetchAgent(owner: session.ownerID) else {
                browserReport = "No paired agent record was returned."
                return
            }
            browserReport = agent.browser?.trimmingCharacters(in: .whitespacesAndNewlines)
                .nilIfEmpty ?? "The agent did not report a browser or extension version."
        } catch {
            browserReport = "The agent record could not be loaded."
        }
    }
}

/// The raw speech surface that Home deliberately is not. It is reachable only
/// after the authenticated developer-mode gate and never exports, logs, or
/// sends what it renders.
private struct DeveloperSpeechStreamView: View {
    @ObservedObject var session: AnticipySession
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        SheetChrome(title: "Developer Speech Stream", leading: .back) {
            dismiss()
        } content: {
            SectionHeader("Live partial")
            GroupedCard {
                CardRowBox.custom {
                    DeveloperMonospaceBlock(
                        session.listener.partial.isEmpty
                            ? "<no partial>"
                            : escaped(session.listener.partial))
                }
            }

            SectionHeader("Finalized on this launch")
            if session.sessionLines.isEmpty {
                GroupedCard {
                    InfoRow("No finalized session lines are in memory.")
                }
            } else {
                VStack(alignment: .leading, spacing: Theme.Space.snug) {
                    ForEach(Array(session.sessionLines.enumerated()), id: \.element.id) { index, line in
                        DeveloperMonospaceBlock("""
                        index=\(index)
                        received=\(line.received)
                        decision=\(field(line.decision))
                        text=\(escaped(line.text))
                        """)
                        .anticipyCard()
                    }
                }
            }

            SectionHeader("Recent server transcript metadata")
            if session.transcript.isEmpty {
                GroupedCard {
                    InfoRow("No server transcript metadata is loaded.")
                }
            } else {
                VStack(alignment: .leading, spacing: Theme.Space.snug) {
                    ForEach(Array(session.transcript.reversed())) { line in
                        DeveloperMonospaceBlock("""
                        id=\(escaped(line.id))
                        created=\(field(line.created))
                        source=\(field(line.source))
                        segment=\(field(line.segmentID))
                        decision=\(field(line.decision))
                        goal=\(field(line.goal))
                        """)
                        .anticipyCard()
                    }
                }
            }

            FootnoteText("This local screen can contain speech. It deliberately omits authentication tokens, owner and account identifiers, phone and email fields, and browser page contents.")
        }
    }

    private func field(_ value: String?) -> String {
        guard let value, !value.isEmpty else { return "<none>" }
        return escaped(value)
    }

    /// Keep each value on its labelled line so transcript content cannot pose
    /// as another metadata field in a copied diagnostic block.
    private func escaped(_ value: String) -> String {
        value
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\r", with: "\\r")
            .replacingOccurrences(of: "\n", with: "\\n")
            .replacingOccurrences(of: "\t", with: "\\t")
    }
}

private struct DeveloperMonospaceBlock: View {
    let text: String

    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text)
            .font(.system(.footnote, design: .monospaced))
            .foregroundStyle(Theme.text2)
            .textSelection(.enabled)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(Theme.Space.base)
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
