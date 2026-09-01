import SwiftUI

/// The private record and the controls that can remove it. Raw speech belongs
/// here rather than on Home: it remains inspectable without turning normal use
/// into a live developer console.
struct SettingsPrivacyDataView: View {
    @ObservedObject var session: AnticipySession
    @EnvironmentObject private var pendant: PendantManager
    @Environment(\.dismiss) private var dismiss

    @State private var showHistory = false
    @State private var showPendingSpeech = false
    @State private var confirmation: Confirmation?
    @State private var localNote: String?
    @State private var localDeleteFailed = false
    @State private var forgettingLocal = false
    @State private var serverNote: String?
    @State private var serverDeleteFailed = false

    private enum Confirmation: String, Identifiable {
        case pending, local, server
        var id: String { rawValue }
    }

    var body: some View {
        SheetChrome(title: "Privacy & Data", leading: .back) {
            dismiss()
        } content: {
            SectionHeader("Your listening record")
            GroupedCard {
                DisclosureRow("Listening history",
                              subtitle: "Review the recent words and interpretations loaded from your account.",
                              systemImage: "text.bubble") {
                    Haptics.engage()
                    showHistory = true
                }
            }
            FootnoteText("Home keeps raw speech out of the way. Your server history is available in the paged archive here; speech still waiting on this iPhone is listed separately below.")

            if session.pendingCount > 0 {
                SectionHeader("Waiting on this iPhone")
                GroupedCard {
                    DisclosureRow("Review unsent speech",
                                  subtitle: "Read the exact words that have not left this iPhone.",
                                  systemImage: "doc.text.magnifyingglass",
                                  value: "\(session.pendingCount)") {
                        Haptics.engage()
                        showPendingSpeech = true
                    }
                    DestructiveRow(pendingDeleteLabel,
                                   systemImage: "trash") {
                        confirmation = .pending
                    }
                }
                FootnoteText("These words have not left this iPhone. Deleting them here means they will never be sent.")
            }

            SectionHeader("This iPhone")
            GroupedCard {
                DestructiveRow(forgettingLocal ? "Forgetting this iPhone…" : "Forget me on this iPhone",
                               systemImage: "iphone.slash") {
                    if !forgettingLocal { confirmation = .local }
                }
            }
            FootnoteText("This removes the local profile, unsent words, device identity, and browser pairing. Data already on your account stays on the server.")
            if let localNote {
                statusText(localNote, failed: localDeleteFailed)
            }

            SectionHeader("Your account")
            GroupedCard {
                DestructiveRow("Delete my account and server data",
                               systemImage: "person.crop.circle.badge.minus") {
                    confirmation = .server
                }
            }
            FootnoteText("This permanently deletes your transcripts, memory, work, receipts, and account from Anticipy's server.")
            if let serverNote {
                statusText(serverNote, failed: serverDeleteFailed)
            }

            if let privacy = privacyURL {
                GroupedCard {
                    NavRow("Privacy policy", systemImage: "arrow.up.right.square") {
                        UIApplication.shared.open(privacy)
                    }
                }
            }
        }
        .navigationDestination(isPresented: $showHistory) {
            ListeningHistoryView(session: session)
        }
        .navigationDestination(isPresented: $showPendingSpeech) {
            PendingSpeechView(session: session)
        }
        .alert(item: $confirmation, content: confirmationAlert)
    }

    private var pendingDeleteLabel: String {
        session.pendingCount == 1
            ? "Delete 1 unsent line"
            : "Delete \(session.pendingCount) unsent lines"
    }

    private var privacyURL: URL? {
        URL(string: session.backendURLString)?.appendingPathComponent("privacy.html")
    }

    private func statusText(_ text: String, failed: Bool) -> some View {
        Text(text)
            .font(.footnote)
            .foregroundStyle(failed ? Theme.alarm : Theme.accent)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, Theme.Space.base)
    }

    private func confirmationAlert(_ choice: Confirmation) -> Alert {
        switch choice {
        case .pending:
            return Alert(
                title: Text("Delete unsent words?"),
                message: Text("They have not left this iPhone. This cannot be undone."),
                primaryButton: .destructive(Text("Delete")) {
                    session.clearPendingLines()
                    localNote = "The unsent words are gone."
                },
                secondaryButton: .cancel())
        case .local:
            return Alert(
                title: Text("Forget you on this iPhone?"),
                message: Text("Listening will stop, unsent words and local profile details will be removed, this iPhone will get a new identity, and your browser will need pairing again. Server data is unchanged."),
                primaryButton: .destructive(Text("Forget me"), action: forgetLocalUser),
                secondaryButton: .cancel())
        case .server:
            return Alert(
                title: Text("Delete everything?"),
                message: Text("Every transcript, memory, errand, and receipt on the server, plus your account, will be permanently deleted. You will be signed out when it finishes."),
                primaryButton: .destructive(Text("Delete it all"), action: deleteServerData),
                secondaryButton: .cancel(Text("Keep it")))
        }
    }

    /// The established local-forget boundary from the original Settings page:
    /// close the microphone and queue, release hardware/browser links before
    /// rotating the device identity, and leave server data untouched.
    private func forgetLocalUser() {
        guard !forgettingLocal else { return }
        forgettingLocal = true
        localDeleteFailed = false
        localNote = "Forgetting this iPhone and checking the browser link…"
        if pendant.hasPairedPendant { pendant.forgetPendant() }
        Task {
            // The call persists its outcome for Auth BEFORE it signs out. This
            // view is removed by that route change, so writing the verdict into
            // local @State afterwards would make a browser failure invisible.
            _ = await session.forgetThisPhone()
            forgettingLocal = false
            Haptics.taskDone()
        }
    }

    private func deleteServerData() {
        serverNote = "Deleting…"
        serverDeleteFailed = false
        Task {
            let outcome = await session.deleteEverythingOnServer()
            serverDeleteFailed = !outcome.ok
            serverNote = outcome.message
            guard outcome.ok else { return }
            Haptics.taskDone()
            // The session owns the guarded sign-out. Scheduling one here after
            // a delay lets an account-A delete task sign out account B.
        }
    }
}

/// Exact local speech that has not reached the server. The session exposes
/// only text owned by the currently authenticated account; timestamps,
/// account ids, and delivery envelopes remain private implementation details.
private struct PendingSpeechView: View {
    @ObservedObject var session: AnticipySession
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        SheetChrome(title: "Unsent Speech", leading: .back) {
            dismiss()
        } content: {
            if session.pendingSpeechLines.isEmpty {
                GroupedCard {
                    InfoRow("There are no words waiting to leave this iPhone.",
                            title: "Nothing waiting",
                            systemImage: "checkmark.circle")
                }
            } else {
                GroupedCard {
                    InfoRow("These are the exact words currently waiting for a network. They have not been sent to Anticipy.",
                            title: pendingSpeechTitle,
                            systemImage: "iphone")
                }
                VStack(alignment: .leading, spacing: Theme.Space.tight) {
                    ForEach(Array(session.pendingSpeechLines.enumerated()), id: \.offset) { index, line in
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Line \(index + 1)")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(Theme.muted)
                            Text(line)
                                .font(.body)
                                .foregroundStyle(Theme.text)
                                .fixedSize(horizontal: false, vertical: true)
                                .textSelection(.enabled)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .anticipyCard()
                    }
                }
            }
            FootnoteText("Delete these words from Privacy & Data if you do not want this iPhone to retry them.")
        }
    }

    private var pendingSpeechTitle: String {
        session.pendingCount == 1 ? "1 unsent line" : "\(session.pendingCount) unsent lines"
    }
}

/// The account's transcript archive, paged independently from Home's small
/// live poll. Each request carries PocketBase's `totalPages`, so the button can
/// stop at the real end instead of treating an arbitrary item count as one.
struct ListeningHistoryView: View {
    @ObservedObject var session: AnticipySession
    @Environment(\.dismiss) private var dismiss

    @State private var events: [BrainEvent] = []
    @State private var page = 0
    @State private var totalPages = 0
    @State private var totalItems = 0
    @State private var loading = false
    @State private var loadError: String?
    @State private var started = false
    /// Excludes rows created after page one began. This reduces ordinary live
    /// insert churn, but it does not make offset pagination a snapshot: a
    /// deletion or an insert sharing the boundary timestamp can still shift a
    /// later page, which the visible history copy says explicitly.
    @State private var snapshotUpperBound: String?

    private var lines: [AnticipySession.TranscriptLine] {
        events.map(Self.transcriptLine)
    }

    private var groups: [HeardGroup] {
        Array(HeardGroup.build(lines).reversed())
    }

    var body: some View {
        SheetChrome(title: "Listening History", leading: .back) {
            dismiss()
        } content: {
            if loading && events.isEmpty {
                GroupedCard {
                    InfoRow("Loading the first page from your account.",
                            title: "Loading listening history…",
                            systemImage: "arrow.clockwise")
                }
            } else if started && groups.isEmpty && loadError == nil {
                GroupedCard {
                    InfoRow("The server returned no transcript lines for this account.",
                            title: "Nothing here yet",
                            systemImage: "waveform")
                }
            } else {
                if !events.isEmpty {
                    GroupedCard {
                        InfoRow(historySummary,
                                title: historyTitle,
                                systemImage: "clock.arrow.circlepath")
                    }

                    VStack(alignment: .leading, spacing: Theme.Space.base) {
                        ForEach(groups) { group in
                            ConversationCard(group: group)
                        }
                    }
                }
            }

            if let loadError {
                GroupedCard {
                    InfoRow(loadError,
                            title: "History could not finish loading",
                            systemImage: "exclamationmark.triangle")
                    ActionRow("Try again", systemImage: "arrow.clockwise",
                              isEnabled: !loading) {
                        Task { await loadPage(max(1, page + 1)) }
                    }
                }
            }

            if page < totalPages {
                GroupedCard {
                    ActionRow(loading ? "Loading older history…" : "Load older history",
                              subtitle: "Continue with page \(page + 1) of \(totalPages).",
                              systemImage: "arrow.down",
                              isEnabled: !loading) {
                        Task { await loadPage(page + 1) }
                    }
                }
            }

            FootnoteText(historyFootnote)
        }
        .task(id: session.accountID) {
            events = []
            page = 0
            totalPages = 0
            totalItems = 0
            started = false
            loadError = nil
            snapshotUpperBound = nil
            await loadPage(1)
        }
    }

    private var historyTitle: String {
        page >= totalPages ? "Available history loaded" : "Listening history"
    }

    private var historySummary: String {
        let noun = events.count == 1 ? "line" : "lines"
        let scope = page >= totalPages
            ? "Loaded \(events.count) transcript \(noun) across the available server pages."
            : "Loaded \(events.count) of the server's current \(totalItems) transcript lines."
        return scope + " History can change while older pages load, so a deletion or same-time insert may shift this list. Tap a conversation to see its loaded lines."
    }

    private var historyFootnote: String {
        if let loadError { return loadError }
        if page < totalPages {
            return "This is page \(page) of \(totalPages). Older transcript pages remain on the server until you load them. Unsent speech is listed separately on Privacy & Data."
        }
        return "All currently reported pages are loaded. This is paged history, not a frozen snapshot; reopen it to refresh changes. Unsent speech is listed separately on Privacy & Data."
    }

    private func loadPage(_ requestedPage: Int) async {
        guard !loading else { return }
        loading = true
        loadError = nil
        do {
            let result = try await session.backend.fetchTranscriptPage(
                page: requestedPage,
                createdAtOrBefore: snapshotUpperBound)
            if requestedPage == 1 && snapshotUpperBound == nil {
                snapshotUpperBound = result.items.first?.created
            }
            var byID = Dictionary(uniqueKeysWithValues: events.map { ($0.id, $0) })
            for event in result.items { byID[event.id] = event }
            events = byID.values.sorted {
                if $0.created == $1.created { return $0.id < $1.id }
                return $0.created < $1.created
            }
            page = result.page
            totalPages = result.totalPages
            totalItems = result.totalItems
            started = true
        } catch {
            loadError = "The server page did not arrive. Nothing already loaded was removed."
            started = true
        }
        loading = false
    }

    private static func transcriptLine(_ event: BrainEvent) -> AnticipySession.TranscriptLine {
        AnticipySession.TranscriptLine(
            id: event.id,
            text: event.text ?? "",
            decision: event.decision?.isEmpty == false ? event.decision : nil,
            goal: event.goal?.isEmpty == false ? event.goal : nil,
            segmentID: event.segment?.isEmpty == false ? event.segment : nil,
            created: event.created,
            source: event.source?.isEmpty == false ? event.source : nil)
    }
}
