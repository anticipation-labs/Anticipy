import SwiftUI

struct SettingsView: View {
    @AppStorage("transcriptionEngine") private var engine = "cloud"
    @AppStorage("proactivityLevel") private var proactivity = 1.0

    var body: some View {
        Form {
            Section("Transcription") {
                Picker("Engine", selection: $engine) {
                    Label("Cloud — Deepgram (fast, most accurate)", systemImage: "cloud").tag("cloud")
                    Label("Local — on device (private, offline)", systemImage: "iphone").tag("local")
                }
                .pickerStyle(.inline)
                Text(engine == "local"
                    ? "Audio never leaves your phone."
                    : "Audio is streamed securely to Deepgram and not stored.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Section("Proactivity") {
                Slider(value: $proactivity, in: 0 ... 2, step: 1)
                Text(["Only when I ask", "Balanced", "Act on everything"][Int(proactivity)])
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .navigationTitle("Settings")
    }
}
