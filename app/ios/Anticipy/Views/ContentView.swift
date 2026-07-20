import SwiftUI

struct ContentView: View {
    @EnvironmentObject var pendant: PendantManager
    @EnvironmentObject var session: AnticipySession

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                statusBar
                if session.transcript.isEmpty {
                    Spacer()
                    Text("Wear your pendant and start talking.\nAnticipy is listening.")
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.secondary)
                    Spacer()
                } else {
                    transcriptList
                }
                ForEach(session.pendingConfirms) { card in
                    ConfirmCardView(card: card)
                }
            }
            .navigationTitle("Anticipy")
        }
    }

    private var statusBar: some View {
        HStack {
            Circle()
                .fill(pendant.state == "connected" ? .green : .orange)
                .frame(width: 9, height: 9)
            Text(pendant.deviceName ?? "Anticipy Pendant")
                .font(.footnote)
            Spacer()
            if let b = pendant.battery {
                Label("\(b)%", systemImage: "battery.75")
                    .font(.footnote)
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(.ultraThinMaterial)
    }

    private var transcriptList: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 10) {
                ForEach(session.transcript) { line in
                    VStack(alignment: .leading, spacing: 3) {
                        Text(line.text)
                        if let d = line.decision, d != "ignore" {
                            Text(d == "act" ? "→ acting on this" : "→ needs your input")
                                .font(.caption2)
                                .foregroundStyle(d == "act" ? .green : .orange)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(10)
                    .background(RoundedRectangle(cornerRadius: 12).fill(Color(.secondarySystemBackground)))
                }
            }
            .padding()
        }
    }
}

struct ConfirmCardView: View {
    let card: AnticipySession.ConfirmCard
    @EnvironmentObject var session: AnticipySession

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(card.summary).font(.subheadline)
            HStack {
                Button("Send it") { session.pendingConfirms.removeAll { $0.id == card.id } }
                    .buttonStyle(.borderedProminent)
                Button("Not now") { session.pendingConfirms.removeAll { $0.id == card.id } }
                    .buttonStyle(.bordered)
            }
        }
        .padding()
        .background(RoundedRectangle(cornerRadius: 14).fill(Color(.secondarySystemBackground)))
        .padding(.horizontal)
    }
}
