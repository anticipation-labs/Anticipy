import AppKit
import SwiftUI
import UserNotifications

/// Anticipy for Mac — a menu bar ear. It listens when you ask it to, offers
/// when a meeting starts, transcribes on device, and sends the words to the
/// same brain the phone feeds. No audio ever leaves this Mac.
@main
struct AnticipyMacApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var listener = MacListener()
    @StateObject private var pocketbase = PocketBase.shared
    @StateObject private var meetings = MeetingWatcher()

    var body: some Scene {
        MenuBarExtra {
            VStack {
                switch pocketbase.isSignedIn {
                case true:
                    ListenSection(listener: listener, meetings: meetings)
                    Divider()
                    Button("Sign out (\(pocketbase.ownerEmail))") { pocketbase.signOut() }
                case false:
                    SignInSection()
                }
                Divider()
                Button("Quit Anticipy") { NSApplication.shared.terminate(nil) }
            }
            .padding(6)
            .environmentObject(pocketbase)
        } label: {
            let image: String = {
                if meetings.inMeeting { return "waveform.badge.magnifyingglass" }
                return listener.state == .listening ? "mic.fill" : "mic.slash"
            }()
            Image(systemName: image)
        }
        .menuBarExtraStyle(.window)
        .onChange(of: meetings.inMeeting) { _, inMeeting in
            guard inMeeting, meetings.autoStart else { return }
            if listener.state != .listening { listener.start() }
        }
        .onChange(of: listener.lines.count) { _, _ in
            // One push per line, at the listener's own cadence.
            guard let line = listener.lines.last, !line.posted else { return }
            pocketbase.postTranscript(text: line.text,
                                      startedAt: line.startedAt,
                                      endedAt: line.endedAt)
        }
    }
}

struct ListenSection: View {
    @ObservedObject var listener: MacListener
    @ObservedObject var meetings: MeetingWatcher
    @EnvironmentObject var pocketbase: PocketBase

    var body: some View {
        Button(listener.state == .listening ? "Stop listening" : "Start listening") {
            toggle()
        }
        Toggle("Start automatically in meetings", isOn: $meetings.autoStart)
        Text(meetings.inMeeting ? "A conversation is happening on this Mac." : meetingQuiet)
            .font(.caption)
            .foregroundStyle(.secondary)
        if listener.state == .listening {
            Text("\(listener.lines.count) line\(listener.lines.count == 1 ? "" : "s") heard this session")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        if listener.state == .denied {
            Text("Speech recognition is unavailable or was refused.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private var meetingQuiet: String { "No conversation on this Mac right now." }

    private func toggle() {
        if listener.state == .listening {
            listener.stop()
        } else {
            listener.start()
        }
    }
}

struct SignInSection: View {
    @EnvironmentObject var pocketbase: PocketBase
    @State private var email = ""
    @State private var password = ""
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        VStack(spacing: 6) {
            Text("Sign in with your Anticipy account")
                .font(.headline)
            TextField("Email", text: $email)
                .textFieldStyle(.roundedBorder)
            SecureField("Password", text: $password)
                .textFieldStyle(.roundedBorder)
            if let error {
                Text(error).font(.caption).foregroundStyle(.secondary)
            }
            if busy {
                ProgressView().controlSize(.small)
            } else {
                Button("Sign in") {
                    busy = true
                    error = nil
                    Task {
                        do {
                            try await pocketbase.signIn(email: email, password: password)
                        } catch {
                            await MainActor.run { self.error = "That email and password didn't open the door." }
                        }
                        await MainActor.run { busy = false }
                    }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(email.isEmpty || password.isEmpty)
            }
        }
        .padding(4)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        UNUserNotificationCenter.current().delegate = self
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert]) { _, _ in }
        NSApp.setActivationPolicy(.accessory)
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        completionHandler()
    }
}
