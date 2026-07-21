import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var pendant: PendantManager
    @EnvironmentObject var session: AnticipySession
    @AppStorage("transcriptionEngine") private var engine = "local"
    @AppStorage("proactivityLevel") private var proactivity = 1.0
    @AppStorage("backendURL") private var backendURL = "http://127.0.0.1:8090"
    @AppStorage("hasOnboarded") private var hasOnboarded = true

    var body: some View {
        Form {
            Section("Pendant") {
                HStack {
                    Text("Status")
                    Spacer()
                    Text(pendant.state.rawValue.capitalized)
                        .foregroundStyle(Theme.gray)
                }
                if let b = pendant.battery {
                    HStack {
                        Text("Battery")
                        Spacer()
                        Text("\(b)%").foregroundStyle(Theme.gray)
                    }
                }
                if let r = pendant.rssi {
                    HStack {
                        Text("Signal")
                        Spacer()
                        Text(r > -60 ? "Strong" : r > -80 ? "OK" : "Weak")
                            .foregroundStyle(Theme.gray)
                    }
                }
                if pendant.hasPairedPendant {
                    Button("Forget this pendant", role: .destructive) {
                        pendant.forgetPendant()
                    }
                } else {
                    Button("Pair a pendant") { pendant.startScan() }
                }
            }

            Section("Transcription") {
                Picker("Engine", selection: $engine) {
                    Label("On this iPhone — private, offline", systemImage: "iphone").tag("local")
                    Label("Cloud — fastest, most accurate", systemImage: "cloud").tag("cloud")
                }
                .pickerStyle(.inline)
                Text(engine == "local"
                    ? "Audio never leaves your phone."
                    : "Audio is streamed securely and not stored.")
                    .font(.caption)
                    .foregroundStyle(Theme.gray)
            }

            Section("Proactivity") {
                Slider(value: $proactivity, in: 0 ... 2, step: 1)
                Text(["Only when I ask", "Balanced", "Act on everything"][Int(proactivity)])
                    .font(.caption)
                    .foregroundStyle(Theme.gray)
            }

            Section("Browser agent") {
                HStack {
                    Text("Link")
                    Spacer()
                    Text(session.backendReachable ? "Connected" : "Offline")
                        .foregroundStyle(session.backendReachable ? Theme.champagne : Theme.gray)
                }
                TextField("Backend URL", text: $backendURL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .font(.footnote.monospaced())
            }

            Section {
                Button("Replay the welcome tour") { hasOnboarded = false }
            }
        }
        .scrollContentBackground(.hidden)
        .background(Theme.ink)
        .navigationTitle("Settings")
    }
}
