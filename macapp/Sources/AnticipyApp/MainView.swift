import SwiftUI

/// Screen 3 — Main (proactive-first). The centerpiece is the live glass-box feed
/// ("what I'm doing / what I did") read from the engine. Record controls present
/// but inert. A small, secondary text box is the side door.

struct GlassEntry: Decodable, Identifiable {
    let ts: Double
    let kind: String
    let summary: String
    var id: String { "\(ts)-\(kind)-\(summary)" }
}

private struct GlassResponse: Decodable { let entries: [GlassEntry] }

@MainActor
final class FeedModel: ObservableObject {
    @Published var entries: [GlassEntry] = []
    @Published var online = false
    private let url = URL(string: "http://127.0.0.1:8787/glassbox?limit=40")!

    func refresh() {
        Task {
            do {
                let (data, _) = try await URLSession.shared.data(from: url)
                let decoded = try JSONDecoder().decode(GlassResponse.self, from: data)
                self.entries = decoded.entries.reversed()  // newest first
                self.online = true
            } catch {
                self.online = false
            }
        }
    }
}

@MainActor
final class TaskInputModel: ObservableObject {
    @Published var text = ""
    @Published var isSubmitting = false
    @Published var lastError: String?
    @Published var lastAccepted = false

    private let url = URL(string: "http://127.0.0.1:8787/event")!

    var canSubmit: Bool {
        !isSubmitting && !trimmedText.isEmpty
    }

    func submit(afterAccepted: @escaping () -> Void) {
        let bodyText = trimmedText
        guard !bodyText.isEmpty, !isSubmitting else { return }

        isSubmitting = true
        lastError = nil
        lastAccepted = false

        Task {
            do {
                var req = URLRequest(url: url)
                req.httpMethod = "POST"
                req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                req.httpBody = try JSONSerialization.data(withJSONObject: ["source": "app", "text": bodyText])
                let (_, response) = try await URLSession.shared.data(for: req)

                guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
                    throw URLError(.badServerResponse)
                }

                text = ""
                lastAccepted = true
                afterAccepted()
            } catch {
                lastError = "Engine did not accept that task."
            }

            isSubmitting = false
        }
    }

    private var trimmedText: String {
        text.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

// ---- Room 6: the "needs you" surface — pending detrimental actions awaiting approve/deny ----
struct PendingItem: Decodable, Identifiable {
    let ask_id: String
    let action: String
    let reason: String
    let category: String
    var id: String { ask_id }
}

private struct PendingResponse: Decodable { let pending: [PendingItem] }

@MainActor
final class PendingModel: ObservableObject {
    @Published var items: [PendingItem] = []
    private let base = "http://127.0.0.1:8787"

    func refresh() {
        Task {
            guard let url = URL(string: base + "/pending") else { return }
            if let (data, _) = try? await URLSession.shared.data(from: url),
               let decoded = try? JSONDecoder().decode(PendingResponse.self, from: data) {
                self.items = decoded.pending
            }
        }
    }

    /// The app tap that resolves the REAL paused goal (mirrors the text/call round-trip).
    func resolve(_ askId: String, approved: Bool) {
        Task {
            guard let url = URL(string: base + "/resolve") else { return }
            var req = URLRequest(url: url)
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try? JSONSerialization.data(withJSONObject: ["ask_id": askId, "approved": approved])
            _ = try? await URLSession.shared.data(for: req)
            self.items.removeAll { $0.ask_id == askId }   // optimistic; the glass-box feed confirms
            self.refresh()
        }
    }
}

struct MainView: View {
    @StateObject private var feed = FeedModel()
    @StateObject private var pending = PendingModel()
    @StateObject private var taskInput = TaskInputModel()
    private let timer = Timer.publish(every: 2, on: .main, in: .common).autoconnect()

    var body: some View {
        VStack(alignment: .leading, spacing: DS.s3) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Today").font(DS.display()).foregroundColor(DS.textPrimary)
                    HStack(spacing: 6) {
                        Circle().fill(feed.online ? DS.accent : DS.textSecondary).frame(width: 7, height: 7)
                        Text(feed.online ? "what I'm doing · things to approve" : "engine offline")
                            .font(DS.secondary()).foregroundColor(DS.textSecondary)
                    }
                }
                Spacer()
                RecordControls()
            }

            TaskComposer(model: taskInput) {
                feed.refresh()
                pending.refresh()
            }

            if !pending.items.isEmpty { NeedsYou(model: pending) }

            Card(elevated: true) {
                if feed.entries.isEmpty {
                    EmptyFeed()
                } else {
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 0) {
                            ForEach(feed.entries) { FeedRow(entry: $0) }
                        }
                        .padding(.vertical, DS.s1)
                    }
                }
            }
            .frame(maxHeight: .infinity)

        }
        .padding(DS.s4)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(DS.bg)
        .onAppear { feed.refresh(); pending.refresh() }
        .onReceive(timer) { _ in feed.refresh(); pending.refresh() }
    }
}

private struct TaskComposer: View {
    @ObservedObject var model: TaskInputModel
    let afterAccepted: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: DS.s1) {
            HStack(spacing: DS.s1) {
                Image(systemName: "text.cursor")
                    .font(.system(size: 12))
                    .foregroundColor(DS.textSecondary)
                    .frame(width: 18)

                TextField("Tell Anticipy something...", text: $model.text)
                    .textFieldStyle(.plain)
                    .font(DS.body())
                    .foregroundColor(DS.textPrimary)
                    .disabled(model.isSubmitting)
                    .onSubmit { submit() }
                    .accessibilityLabel("Task input")

                if model.isSubmitting {
                    ProgressView()
                        .scaleEffect(0.65)
                        .frame(width: 22, height: 22)
                }

                Button(action: submit) {
                    Image(systemName: "paperplane.fill")
                        .font(.system(size: 13, weight: .semibold))
                        .frame(width: 28, height: 24)
                }
                .buttonStyle(.plain)
                .foregroundColor(model.canSubmit ? DS.bg : DS.textSecondary.opacity(0.55))
                .background(model.canSubmit ? DS.accent : DS.elevated)
                .clipShape(RoundedRectangle(cornerRadius: DS.controlRadius, style: .continuous))
                .disabled(!model.canSubmit)
                .help("Send task")
                .accessibilityLabel("Send task")
            }
            .padding(.horizontal, DS.s2)
            .padding(.vertical, DS.s1)
            .background(DS.surface)
            .overlay(RoundedRectangle(cornerRadius: DS.controlRadius, style: .continuous).stroke(DS.hairline))

            if let error = model.lastError {
                Text(error)
                    .font(DS.secondary())
                    .foregroundColor(DS.titanium)
            } else if model.lastAccepted {
                Text("Sent to the engine.")
                    .font(DS.secondary())
                    .foregroundColor(DS.textSecondary)
            }
        }
    }

    private func submit() {
        model.submit(afterAccepted: afterAccepted)
    }
}

private struct FeedRow: View {
    let entry: GlassEntry
    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: DS.s2) {
            Image(systemName: glyph)
                .font(.system(size: 13)).foregroundColor(color).frame(width: 18)
            Text(entry.summary)
                .font(DS.body()).foregroundColor(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer()
        }
        .padding(.horizontal, DS.s2).padding(.vertical, DS.s1)
        .overlay(Rectangle().fill(DS.hairline).frame(height: 1), alignment: .bottom)
    }

    private var glyph: String {
        switch entry.kind {
        case "event": return "waveform"
        case "decision": return "sparkles"
        case "ask_human": return "hand.raised"
        case "job": return "arrow.triangle.turn.up.right.circle"
        case "result": return "checkmark.circle"
        case "approval": return "checkmark.shield"
        case let k where k.hasPrefix("goal_done"): return "checkmark.seal.fill"
        case let k where k.hasPrefix("goal_"): return "circle.dashed"
        default: return "dot.circle"
        }
    }

    private var color: Color {
        if entry.kind == "decision" || entry.kind.hasPrefix("goal_done") { return DS.accent }
        if entry.kind == "ask_human" { return DS.titanium }
        return DS.textSecondary
    }
}

private struct EmptyFeed: View {
    var body: some View {
        VStack(spacing: DS.s2) {
            Image(systemName: "sparkles").font(.system(size: 26)).foregroundColor(DS.accent)
            Text("Nothing needs you right now.").font(DS.title()).foregroundColor(DS.textPrimary)
            Text("Anticipy is listening for what it can take off your plate.\nWhen it acts, you'll see every step here.")
                .font(DS.body()).foregroundColor(DS.textSecondary)
                .multilineTextAlignment(.center).lineSpacing(4)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity).padding(DS.s4)
    }
}

private struct NeedsYou: View {
    @ObservedObject var model: PendingModel
    var body: some View {
        Card(elevated: true) {
            VStack(alignment: .leading, spacing: DS.s2) {
                HStack(spacing: 6) {
                    Image(systemName: "hand.raised.fill").font(.system(size: 13)).foregroundColor(DS.accent)
                    Text("Needs you").font(DS.title()).foregroundColor(DS.textPrimary)
                    Spacer()
                    Text("\(model.items.count)").font(DS.secondary()).foregroundColor(DS.textSecondary)
                }
                ForEach(model.items) { item in
                    VStack(alignment: .leading, spacing: DS.s1) {
                        Text(item.action).font(DS.body(.medium)).foregroundColor(DS.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(item.reason).font(DS.secondary()).foregroundColor(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                        HStack(spacing: DS.s1) {
                            Button { model.resolve(item.ask_id, approved: true) } label: {
                                Text("Approve").font(DS.body(.medium)).foregroundColor(DS.bg)
                                    .padding(.horizontal, DS.s3).padding(.vertical, DS.s1 + 4)
                                    .background(DS.accent)
                                    .clipShape(RoundedRectangle(cornerRadius: DS.controlRadius, style: .continuous))
                            }.buttonStyle(.plain)
                            Button { model.resolve(item.ask_id, approved: false) } label: {
                                Text("Skip").font(DS.body(.medium)).foregroundColor(DS.textSecondary)
                                    .padding(.horizontal, DS.s3).padding(.vertical, DS.s1 + 4)
                                    .overlay(RoundedRectangle(cornerRadius: DS.controlRadius, style: .continuous).stroke(DS.hairline))
                            }.buttonStyle(.plain)
                        }
                    }
                    .padding(.vertical, DS.s1)
                    .overlay(Rectangle().fill(DS.hairline).frame(height: 1), alignment: .bottom)
                }
            }
        }
    }
}

private struct RecordControls: View {
    var body: some View {
        HStack(spacing: DS.s1) {
            ForEach(["MP3", "Transcript"], id: \.self) { label in
                Text(label)
                    .font(DS.secondary(.medium)).foregroundColor(DS.textSecondary)
                    .padding(.horizontal, DS.s2).padding(.vertical, 6)
                    .overlay(RoundedRectangle(cornerRadius: DS.controlRadius, style: .continuous).stroke(DS.hairline))
            }
            HStack(spacing: 6) {
                Circle().fill(DS.accent).frame(width: 8, height: 8)
                Text("Record").font(DS.secondary(.medium)).foregroundColor(DS.textPrimary)
            }
            .padding(.horizontal, DS.s2).padding(.vertical, 6)
            .background(DS.elevated)
            .clipShape(RoundedRectangle(cornerRadius: DS.controlRadius, style: .continuous))
        }
    }
}
