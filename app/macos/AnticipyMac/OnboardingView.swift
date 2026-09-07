import AppKit
import AVFoundation
import Speech
import SwiftUI
import UserNotifications

/// What macOS has said about the two permissions a recording needs, read
/// from the system on demand. The rows in OnboardingView and the card in the
/// library both read this; neither asks the system for itself.
@MainActor
final class MacPermissions: ObservableObject {
    @Published private(set) var microphone: PermissionState = .notAsked
    @Published private(set) var speech: PermissionState = .notAsked

    init() { refresh() }

    func refresh() {
        microphone = Self.state(AVCaptureDevice.authorizationStatus(for: .audio))
        speech = Self.state(SFSpeechRecognizer.authorizationStatus())
    }

    var canRecord: Bool {
        OnboardingRoute.canRecord(microphone: microphone, speech: speech)
    }

    func requestMicrophone() {
        Task {
            _ = await AVCaptureDevice.requestAccess(for: .audio)
            refresh()
        }
    }

    func requestSpeech() {
        SFSpeechRecognizer.requestAuthorization { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
    }

    func requestNotifications() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert]) { _, _ in }
    }

    /// System Settings, opened on the Microphone pane. A denied permission
    /// cannot be asked again from inside the app; this is the only door.
    static func openPrivacySettings(pane: String) {
        let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?\(pane)")!
        NSWorkspace.shared.open(url)
    }

    private static func state(_ s: AVAuthorizationStatus) -> PermissionState {
        switch s {
        case .authorized: return .granted
        case .denied, .restricted: return .denied
        case .notDetermined: return .notAsked
        @unknown default: return .notAsked
        }
    }

    private static func state(_ s: SFSpeechRecognizerAuthorizationStatus) -> PermissionState {
        switch s {
        case .authorized: return .granted
        case .denied, .restricted: return .denied
        case .notDetermined: return .notAsked
        @unknown default: return .notAsked
        }
    }
}

/// First run: four beats on the phone's cream ground. The route is
/// OnboardingRoute's; this file only draws it.
struct OnboardingView: View {
    @EnvironmentObject private var backend: MacBackend
    @EnvironmentObject private var meetings: MeetingWatcher
    @StateObject private var permissions = MacPermissions()
    @AppStorage(OnboardingRoute.storageKey) private var hasOnboarded = false
    @State private var step: OnboardingStep = .welcome

    var body: some View {
        ZStack {
            MacTheme.onboardGround.ignoresSafeArea()
            VStack(spacing: MacTheme.Space.roomy) {
                Spacer(minLength: 0)
                beat
                    .frame(maxWidth: 520)
                    .cardSurface(padding: MacTheme.Space.section, elevated: true)
                    .id(step)
                    .transition(.opacity.combined(with: .move(edge: .trailing)))
                pager
                Spacer(minLength: 0)
            }
            .padding(MacTheme.Space.wide)
        }
        .animation(MacTheme.spring, value: step)
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            // Somebody came back from System Settings; read what changed.
            permissions.refresh()
        }
    }

    @ViewBuilder private var beat: some View {
        switch step {
        case .welcome: welcome
        case .signIn: signIn
        case .permissions: permissionBeat
        case .ready, .done: ready
        }
    }

    private var pager: some View {
        HStack(spacing: MacTheme.Space.tight) {
            ForEach(OnboardingStep.beats, id: \.rawValue) { beat in
                Capsule()
                    .fill(beat == step ? MacTheme.fill : MacTheme.edge)
                    .frame(width: beat == step ? 22 : 8, height: 8)
            }
        }
        .accessibilityLabel("Step \(step.rawValue + 1) of \(OnboardingStep.beats.count)")
    }

    private func advance() {
        withAnimation(MacTheme.spring) { step = step.next }
    }

    // ------------------------------------------------------------- welcome

    private var welcome: some View {
        VStack(alignment: .leading, spacing: MacTheme.Space.card) {
            BrandMark(size: 56)
            Text("Anticipy for Mac")
                .font(MacTheme.display(34, weight: .medium))
                .foregroundStyle(MacTheme.text)
            Text("Notes from every meeting, kept on this Mac.")
                .font(MacTheme.voice)
                .foregroundStyle(MacTheme.text2)
            VStack(alignment: .leading, spacing: MacTheme.Space.snug) {
                promise("waveform", "I record both sides of a call as two separate tracks: your microphone, and what your Mac plays.")
                promise("lock", "I turn them into text right here. The audio never leaves this Mac.")
                promise("iphone", "The words reach the same Anticipy your phone talks to, so what you agreed to in a meeting becomes work.")
            }
            .padding(.top, MacTheme.Space.hair)
            HStack {
                Spacer()
                Button("Get started") { advance() }
                    .buttonStyle(.primary)
                    .keyboardShortcut(.defaultAction)
            }
        }
    }

    private func promise(_ symbol: String, _ text: String) -> some View {
        HStack(alignment: .top, spacing: MacTheme.Space.snug) {
            Image(systemName: symbol)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(MacTheme.accent)
                .frame(width: 20)
            Text(text)
                .font(MacTheme.aside)
                .foregroundStyle(MacTheme.text)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // ------------------------------------------------------------- sign in

    private var signIn: some View {
        VStack(alignment: .leading, spacing: MacTheme.Space.card) {
            Text("Same account as your phone")
                .font(MacTheme.display(26, weight: .medium))
                .foregroundStyle(MacTheme.text)
            Text("Sign in and every meeting's words reach your Anticipy. Skip it and I still record and keep notes here; nothing syncs until you do.")
                .font(MacTheme.aside)
                .foregroundStyle(MacTheme.text2)
                .fixedSize(horizontal: false, vertical: true)
            if backend.isSignedIn {
                Label("Signed in as \(backend.ownerEmail)", systemImage: "checkmark.circle.fill")
                    .font(MacTheme.aside.weight(.semibold))
                    .foregroundStyle(MacTheme.accent)
            } else {
                SignInForm(compact: false)
            }
            HStack {
                if !backend.isSignedIn {
                    Button("Skip for now") { advance() }
                        .buttonStyle(.ghost)
                }
                Spacer()
                Button("Continue") { advance() }
                    .buttonStyle(.primary)
                    .disabled(!backend.isSignedIn)
            }
        }
    }

    // --------------------------------------------------------- permissions

    private var permissionBeat: some View {
        VStack(alignment: .leading, spacing: MacTheme.Space.card) {
            Text("Two switches, both me")
                .font(MacTheme.display(26, weight: .medium))
                .foregroundStyle(MacTheme.text)
            VStack(spacing: 0) {
                PermissionRow(title: "Microphone",
                              detail: "Your side of the meeting.",
                              state: permissions.microphone) {
                    if permissions.microphone == .denied {
                        MacPermissions.openPrivacySettings(pane: "Privacy_Microphone")
                    } else {
                        permissions.requestMicrophone()
                    }
                }
                Divider().overlay(MacTheme.edge)
                PermissionRow(title: "Speech Recognition",
                              detail: "Words become text on this Mac, not on a server.",
                              state: permissions.speech) {
                    if permissions.speech == .denied {
                        MacPermissions.openPrivacySettings(pane: "Privacy_SpeechRecognition")
                    } else {
                        permissions.requestSpeech()
                    }
                }
                Divider().overlay(MacTheme.edge)
                HStack(alignment: .top, spacing: MacTheme.Space.snug) {
                    Image(systemName: "speaker.wave.2")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(MacTheme.accent)
                        .frame(width: 20)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("System audio").font(MacTheme.aside.weight(.semibold)).foregroundStyle(MacTheme.text)
                        Text("The other side. macOS asks for this the first time a recording starts; there is no way to ask sooner.")
                            .font(.system(size: 12)).foregroundStyle(MacTheme.text2)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer()
                }
                .padding(.vertical, MacTheme.Space.snug)
            }
            Text(OnboardingRoute.permissionSentence(microphone: permissions.microphone,
                                                    speech: permissions.speech))
                .font(.system(size: 12))
                .foregroundStyle(permissions.canRecord ? MacTheme.accent : MacTheme.muted)
                .fixedSize(horizontal: false, vertical: true)
            HStack {
                Button("Notifications: let me tell you when a call starts") {
                    permissions.requestNotifications()
                }
                .buttonStyle(.ghost)
                Spacer()
                Button("Continue") { advance() }
                    .buttonStyle(.primary)
                    .disabled(!permissions.canRecord)
                    .keyboardShortcut(.defaultAction)
            }
        }
    }

    // --------------------------------------------------------------- ready

    private var ready: some View {
        VStack(alignment: .leading, spacing: MacTheme.Space.card) {
            HStack(spacing: MacTheme.Space.snug) {
                LiveDot(active: true, size: 10, color: MacTheme.fill)
                Text("You're set.")
                    .font(MacTheme.display(26, weight: .medium))
                    .foregroundStyle(MacTheme.text)
            }
            Text("When a call starts on this Mac I'll notice and offer to record, from the menu bar and from this window. The click is yours.")
                .font(MacTheme.aside)
                .foregroundStyle(MacTheme.text2)
                .fixedSize(horizontal: false, vertical: true)
            Toggle(isOn: $meetings.autoStart) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Start recording on my own when a call begins")
                        .font(MacTheme.aside.weight(.semibold))
                        .foregroundStyle(MacTheme.text)
                    Text("Off by default. You can change this any time in Settings.")
                        .font(.system(size: 12))
                        .foregroundStyle(MacTheme.muted)
                }
            }
            .toggleStyle(.switch)
            .tint(MacTheme.fill)
            HStack {
                Spacer()
                Button("Open Anticipy") {
                    hasOnboarded = true
                }
                .buttonStyle(.primary)
                .keyboardShortcut(.defaultAction)
            }
        }
    }
}

/// One permission with its state and the one button that can change it.
struct PermissionRow: View {
    let title: String
    let detail: String
    let state: PermissionState
    let action: () -> Void

    var body: some View {
        HStack(alignment: .center, spacing: MacTheme.Space.snug) {
            Image(systemName: symbol)
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(state == .granted ? MacTheme.accent : state == .denied ? MacTheme.caution : MacTheme.muted)
                .frame(width: 20)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(MacTheme.aside.weight(.semibold)).foregroundStyle(MacTheme.text)
                Text(detail).font(.system(size: 12)).foregroundStyle(MacTheme.text2)
            }
            Spacer()
            if let button = OnboardingRoute.buttonTitle(for: state) {
                Button(button, action: action)
                    .buttonStyle(.secondary)
            } else {
                Text("On")
                    .font(MacTheme.meta)
                    .foregroundStyle(MacTheme.accent)
            }
        }
        .padding(.vertical, MacTheme.Space.snug)
    }

    private var symbol: String {
        switch state {
        case .granted: return "checkmark.circle.fill"
        case .denied: return "exclamationmark.triangle"
        case .notAsked: return "circle"
        }
    }
}

/// The sign-in form, shared by first run and the library's account card.
struct SignInForm: View {
    @EnvironmentObject private var backend: MacBackend
    var compact: Bool
    @State private var email = ""
    @State private var password = ""
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: MacTheme.Space.tight) {
            TextField("Email", text: $email)
                .textFieldStyle(.roundedBorder)
                .textContentType(.username)
            SecureField("Password", text: $password)
                .textFieldStyle(.roundedBorder)
                .textContentType(.password)
                .onSubmit { submit() }
            HStack {
                if let error {
                    Text(error)
                        .font(.system(size: 12))
                        .foregroundStyle(MacTheme.text2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
                if busy {
                    ProgressView().controlSize(.small)
                } else {
                    Button("Sign in") { submit() }
                        .buttonStyle(.primary)
                        .controlSize(compact ? .small : .regular)
                        .disabled(email.isEmpty || password.isEmpty)
                }
            }
        }
    }

    private func submit() {
        guard !email.isEmpty, !password.isEmpty, !busy else { return }
        busy = true
        error = nil
        Task {
            do {
                try await backend.signIn(email: email, password: password)
                await MainActor.run { password = "" }
            } catch {
                await MainActor.run {
                    self.error = "That email and password didn't open the door."
                }
            }
            await MainActor.run { busy = false }
        }
    }
}
