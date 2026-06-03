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

struct MainView: View {
    @StateObject private var feed = FeedModel()
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

            SideDoor()
        }
        .padding(DS.s4)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(DS.bg)
        .onAppear { feed.refresh() }
        .onReceive(timer) { _ in feed.refresh() }
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

private struct SideDoor: View {
    var body: some View {
        HStack(spacing: DS.s1) {
            Image(systemName: "text.cursor").font(.system(size: 12)).foregroundColor(DS.textSecondary)
            Text("Tell Anticipy something…")
                .font(DS.secondary()).foregroundColor(DS.textSecondary.opacity(0.7))
            Spacer()
        }
        .padding(.horizontal, DS.s2).padding(.vertical, DS.s1)
        .frame(maxWidth: 360)
        .background(DS.surface)
        .overlay(RoundedRectangle(cornerRadius: DS.controlRadius, style: .continuous).stroke(DS.hairline))
    }
}
