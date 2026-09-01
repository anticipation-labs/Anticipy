import SwiftUI
import LocalAuthentication
import Speech

/// The settings index. Every row opens one focused page, so a chevron always
/// means navigation and no preference changes accidentally on the index.
struct SettingsHomeView: View {
    @EnvironmentObject var session: AnticipySession
    @Environment(\.dismiss) private var dismiss

    @State private var route: Route?

    private enum Route: Hashable {
        case profile, listening, notifications, connectors, personalization
        case privacyData, appearance, advanced, about
    }

    var body: some View {
        SheetChrome(
            title: "Settings",
            leading: .back,
            onLeading: { dismiss() }
        ) {
            GroupedCard {
                InfoRow(session.ownerEmail.isEmpty
                        ? "Signed in on this phone" : session.ownerEmail)
            }

            SectionHeader("Account")
            GroupedCard {
                NavRow("Profile", systemImage: "person.crop.circle",
                       value: session.ownerFirstName.isEmpty
                           ? nil : session.ownerFirstName) {
                    Haptics.engage(); route = .profile
                }
            }

            SectionHeader("Anticipy")
            GroupedCard {
                NavRow("Listening", systemImage: "waveform",
                       value: session.listener.isListening ? "On" : "Off") {
                    Haptics.engage(); route = .listening
                }
                NavRow("Notifications", systemImage: "bell") {
                    Haptics.engage(); route = .notifications
                }
                NavRow("Personalization", systemImage: "person.text.rectangle") {
                    Haptics.engage(); route = .personalization
                }
            }

            SectionHeader("Connections")
            GroupedCard {
                NavRow("Connectors", systemImage: "link") {
                    Haptics.engage(); route = .connectors
                }
            }

            SectionHeader("Privacy")
            GroupedCard {
                NavRow("Privacy & Data", systemImage: "hand.raised") {
                    Haptics.engage(); route = .privacyData
                }
            }

            SectionHeader("Preferences")
            GroupedCard {
                NavRow("Appearance", systemImage: "circle.lefthalf.filled") {
                    Haptics.engage(); route = .appearance
                }
                NavRow("Advanced", systemImage: "slider.horizontal.3") {
                    Haptics.engage(); route = .advanced
                }
            }

            SectionHeader("About")
            GroupedCard {
                NavRow("About Anticipy", systemImage: "info.circle") {
                    Haptics.engage(); route = .about
                }
            }
        }
        .navigationDestination(isPresented: Binding(
            get: { route != nil },
            set: { if !$0 { route = nil } }
        )) {
            switch route {
            case .profile:   SettingsProfileView(session: session)
            case .listening: SettingsListeningView(session: session)
            case .notifications: SettingsNotificationsView()
            case .connectors: SettingsConnectorsView(session: session)
            case .personalization: SettingsPersonalizationView(session: session)
            case .privacyData: SettingsPrivacyDataView(session: session)
            case .appearance: SettingsAppearanceView()
            case .advanced: SettingsAdvancedView()
            case .about: SettingsAboutView()
            case nil:        EmptyView()
            }
        }
    }
}

/// Screen 5: the info popover, as a sheet.
///
/// A popover anchored to the header button is what the source does; on a phone
/// UIKit renders that as a sheet anyway, so this is the same thing without
/// pretending the anchor matters.
///
/// The build number is printed beside the version ON PURPOSE. This repo has
/// spent whole days on the question "which build is that phone actually
/// running" — `device_id` IS the build number in the ears pipeline, and builds
/// 76 to 80 delivered zero rows while looking healthy. A version string without
/// the build is the half that cannot answer it.
private struct SettingsAboutView: View {
    @Environment(\.dismiss) private var dismiss
    @AppStorage(AppPreferences.developerModeKey) private var developerMode = false
    @State private var buildTaps = 0
    @State private var tapGeneration = 0
    @State private var authenticating = false
    @State private var authenticationContext: LAContext?
    @State private var unlockError: String?

    private var version: String {
        let v = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
        let b = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "?"
        return "Anticipy \(v) (\(b))"
    }

    /// Mirrors the recognizer decision used by PhoneListener. Some older
    /// devices cannot perform speech recognition locally; on those devices iOS
    /// may send microphone audio to Apple's speech service, so About must say
    /// that plainly instead of making an unconditional local-audio promise.
    private var speechPrivacyPath: String {
        let onDevice = SFSpeechRecognizer(locale: Locale(identifier: "en_US"))?
            .supportsOnDeviceRecognition ?? false
        return onDevice
            ? "Microphone audio is turned into text on this iPhone, then the text is sent to Anticipy's server so it can create and complete work."
            : "This iPhone may use Apple's speech service to turn microphone audio into text. Anticipy then sends the text—not an audio recording—to its server so it can create and complete work."
    }

    var body: some View {
        SheetChrome(title: "About", leading: .back) {
            dismiss()
        } content: {
            GroupedCard {
                InfoRow(version)
                    .contentShape(Rectangle())
                    .onTapGesture(perform: registerBuildTap)
            }

            if developerMode {
                FootnoteText("Developer mode is on. Its diagnostics are under Advanced.")
            }

            GroupedCard {
                if let url = URL(string: "https://anticipy.ai/privacy") {
                    NavRow("Privacy policy", systemImage: "arrow.up.right.square") {
                        UIApplication.shared.open(url)
                    }
                }
                if let url = URL(string: "https://anticipy.ai/terms") {
                    NavRow("Terms of service", systemImage: "arrow.up.right.square") {
                        UIApplication.shared.open(url)
                    }
                }
            }

            FootnoteText(speechPrivacyPath)
        }
        .alert("Developer mode stayed locked", isPresented: Binding(
            get: { unlockError != nil },
            set: { if !$0 { unlockError = nil } }
        )) {
            Button("OK", role: .cancel) { unlockError = nil }
        } message: {
            Text(unlockError ?? "This iPhone could not verify its owner.")
        }
    }

    /// Seven deliberate taps make the control discoverable to a developer who
    /// knows it is there without turning About into another settings page.
    /// Authentication is the actual gate; the taps merely ask to approach it.
    private func registerBuildTap() {
        guard !developerMode, !authenticating else { return }
        buildTaps += 1
        tapGeneration += 1
        let generation = tapGeneration

        if buildTaps >= 7 {
            buildTaps = 0
            authenticateOwner()
            return
        }

        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            guard generation == tapGeneration else { return }
            buildTaps = 0
        }
    }

    /// Device-owner authentication can use Face ID, Touch ID, or the iPhone's
    /// passcode. It protects a local diagnostics surface; it is not a passkey
    /// and it grants no additional backend permission.
    private func authenticateOwner() {
        let context = LAContext()
        var error: NSError?
        guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) else {
            unlockError = "Set a passcode, Face ID, or Touch ID on this iPhone before unlocking diagnostics."
            return
        }

        authenticating = true
        authenticationContext = context
        context.evaluatePolicy(
            .deviceOwnerAuthentication,
            localizedReason: "Unlock Anticipy developer diagnostics"
        ) { success, evaluationError in
            DispatchQueue.main.async {
                authenticating = false
                authenticationContext = nil
                if success {
                    developerMode = true
                    Haptics.success()
                    return
                }
                if let laError = evaluationError as? LAError,
                   laError.code == .userCancel || laError.code == .appCancel {
                    return
                }
                unlockError = "This iPhone could not verify its owner. Nothing changed."
            }
        }
    }
}
