import SwiftUI

struct ContentView: View {
    @EnvironmentObject var pendant: PendantManager
    @EnvironmentObject var session: AnticipySession

    var body: some View {
        NavigationStack {
            ZStack {
                Color(red: 0.05, green: 0.05, blue: 0.07).ignoresSafeArea()
                VStack(spacing: 0) {
                    pendantCard
                    if session.transcript.isEmpty {
                        emptyState
                    } else {
                        transcriptList
                    }
                    ForEach(session.pendingConfirms) { card in
                        ConfirmCardView(card: card)
                    }
                }
            }
            .navigationTitle("Anticipy")
            .toolbar {
                NavigationLink { SettingsView() } label: {
                    Image(systemName: "slider.horizontal.3")
                }
            }
        }
    }

    private var pendantCard: some View {
        HStack(spacing: 12) {
            ZStack {
                Circle()
                    .fill(pendant.state == "connected"
                        ? Color.green.opacity(0.15) : Color.orange.opacity(0.15))
                    .frame(width: 40, height: 40)
                Image(systemName: "circle.hexagongrid.circle")
                    .foregroundStyle(pendant.state == "connected" ? .green : .orange)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(pendant.deviceName ?? "Anticipy Pendant")
                    .font(.subheadline.weight(.semibold))
                Text(pendant.state == "connected" ? "Listening" : pendant.state.capitalized)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if let b = pendant.battery {
                VStack(spacing: 1) {
                    Image(systemName: b > 60 ? "battery.100" : b > 25 ? "battery.50" : "battery.25")
                    Text("\(b)%").font(.caption2)
                }
                .foregroundStyle(b > 25 ? .secondary : Color.orange)
            }
        }
        .padding(14)
        .background(RoundedRectangle(cornerRadius: 18).fill(.white.opacity(0.05)))
        .padding([.horizontal, .top])
    }

    private var emptyState: some View {
        VStack(spacing: 14) {
            Spacer()
            Image(systemName: "waveform")
                .font(.system(size: 42))
                .foregroundStyle(.tertiary)
            Text("Wear your pendant and live your day.")
                .font(.headline)
            Text("Anticipy listens, understands, and handles\nthe follow-through — asking before anything is sent.")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Spacer()
        }
    }

    private var transcriptList: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 10) {
                ForEach(session.transcript) { line in
                    TranscriptRow(line: line)
                }
            }
            .padding()
        }
    }
}

struct TranscriptRow: View {
    let line: AnticipySession.TranscriptLine

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(line.text)
                .font(.callout)
            if let d = line.decision, d != "ignore" {
                HStack(spacing: 5) {
                    Image(systemName: d == "act" ? "bolt.fill" : "questionmark.circle")
                    Text(d == "act" ? "On it" : "Quick question for you")
                }
                .font(.caption.weight(.medium))
                .foregroundStyle(d == "act" ? Color.green : Color.orange)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 14).fill(.white.opacity(0.05)))
    }
}

struct ConfirmCardView: View {
    let card: AnticipySession.ConfirmCard
    @EnvironmentObject var session: AnticipySession

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Ready to go", systemImage: "checkmark.seal")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.green)
            Text(card.summary)
                .font(.subheadline)
            HStack(spacing: 10) {
                Button {
                    session.pendingConfirms.removeAll { $0.id == card.id }
                } label: {
                    Text("Send it").frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(.green)
                Button {
                    session.pendingConfirms.removeAll { $0.id == card.id }
                } label: {
                    Text("Not now").frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
            }
        }
        .padding(14)
        .background(RoundedRectangle(cornerRadius: 18).fill(.white.opacity(0.07)))
        .padding(.horizontal)
        .padding(.bottom, 8)
    }
}
