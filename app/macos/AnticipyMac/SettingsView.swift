import AppKit
import SwiftUI

/// Cmd+comma. Four groups, each a sentence long, because a settings pane
/// that needs a paragraph is a design that needs a rethink.
struct MacSettingsView: View {
    @EnvironmentObject private var backend: MacBackend
    @EnvironmentObject private var meetings: MeetingWatcher
    @EnvironmentObject private var store: MeetingStore
    @AppStorage(MacAppearance.key) private var appearanceRaw = MacAppearance.light.rawValue
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        Form {
            Section("Account") {
                if backend.isSignedIn {
                    LabeledContent("Signed in as", value: backend.ownerEmail)
                    LabeledContent("Sync") {
                        Text(backend.pendingCount == 0
                             ? "No transcript lines waiting to sync."
                             : "\(backend.pendingCount) line\(backend.pendingCount == 1 ? "" : "s") waiting for a connection.")
                            .foregroundStyle(backend.pendingCount == 0 ? MacTheme.muted : MacTheme.caution)
                    }
                    if let error = backend.syncError {
                        Text(error).foregroundStyle(MacTheme.caution)
                    }
                    Button("Sign out") { backend.signOut() }
                } else {
                    Text("Not signed in. New recordings stay on this Mac. Sign in before recording to send transcript text to Anticipy.")
                        .foregroundStyle(MacTheme.text2)
                    SignInForm(compact: true)
                }
            }

            Section("Recording") {
                Toggle("Start recording on my own when a call begins", isOn: $meetings.autoStart)
                Text("Off, and I offer instead: a notification, and a banner in the window. On, and I start the moment a two-way conversation is held by an app on this Mac.")
                    .font(.system(size: 12))
                    .foregroundStyle(MacTheme.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Section("Appearance") {
                Picker("Theme", selection: $appearanceRaw) {
                    ForEach(MacAppearance.allCases, id: \.rawValue) { choice in
                        Text(choice.label).tag(choice.rawValue)
                    }
                }
                .pickerStyle(.segmented)
                Text("Light unless you choose dark, the same as the phone. The system setting is not followed on purpose.")
                    .font(.system(size: 12))
                    .foregroundStyle(MacTheme.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Section("On this Mac") {
                LabeledContent("Meetings folder") {
                    Button("Show in Finder") { store.revealRoot() }
                }
                Text(store.rootURL.path)
                    .font(MacTheme.mono)
                    .foregroundStyle(MacTheme.muted)
                    .textSelection(.enabled)
                Text("Each meeting is one folder: two audio tracks, the transcript, and your notes. Audio never leaves this Mac; only the transcript text is sent, and only when you are signed in.")
                    .font(.system(size: 12))
                    .foregroundStyle(MacTheme.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Section("About") {
                LabeledContent("Version", value: Self.versionLine)
                LabeledContent("Backend", value: backend.baseURL.host ?? backend.baseURL.absoluteString)
                Button("Open the guide") { openWindow(id: "guide") }
            }
        }
        .formStyle(.grouped)
        .frame(width: 520)
        .preferredColorScheme(MacAppearance(rawValue: appearanceRaw).colorScheme)
    }

    static var versionLine: String {
        let info = Bundle.main.infoDictionary
        let short = info?["CFBundleShortVersionString"] as? String ?? "?"
        let build = info?["CFBundleVersion"] as? String ?? "?"
        return "\(short) (\(build))"
    }
}
