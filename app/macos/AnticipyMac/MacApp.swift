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
                ListenSection(listener: listener, meetings: meetings)
                Divider()
                if pocketbase.isSignedIn {
                    Button("Sign out (\(pocketbase.ownerEmail))") { pocketbase.signOut() }
                } else {
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
                return listener.state.isCapturing ? "mic.fill" : "mic.slash"
            }()
            Image(systemName: image)
        }
        .menuBarExtraStyle(.window)
        .onChange(of: meetings.inMeeting) { _, inMeeting in
            if inMeeting, meetings.autoStart, !listener.state.isCapturing {
                listener.start(reason: .detectedMeeting(bundleID: meetings.activeBundleID))
            } else if !inMeeting, listener.startedForDetectedMeeting,
                      listener.state.isCapturing {
                listener.stop()
            }
        }
        .onChange(of: listener.lines.count) { _, _ in
            // One push per line, at the listener's own cadence.
            guard let line = listener.lines.last else { return }
            pocketbase.postTranscript(text: line.text,
                                      startedAt: line.startedAt,
                                      endedAt: line.endedAt,
                                      speaker: TranscriptWire.speaker(for: line.channel))
        }
    }
}

struct ListenSection: View {
    @ObservedObject var listener: MacListener
    @ObservedObject var meetings: MeetingWatcher
    @EnvironmentObject var pocketbase: PocketBase

    var body: some View {
        Button(listener.state == .finishing ? "Finishing recording…"
               : listener.state.isCapturing ? "Stop recording" : "Start recording") {
            toggle()
        }
        .disabled(listener.state == .finishing)
        Toggle("Start automatically in meetings", isOn: $meetings.autoStart)
        Text(meetings.inMeeting ? "A call is active on this Mac." : meetingQuiet)
            .font(.caption)
            .foregroundStyle(.secondary)
        if listener.state.isCapturing || listener.state == .starting || listener.state == .finishing {
            Text(listener.healthSentence)
                .font(.caption)
                .foregroundStyle(listener.state == .degraded ? .orange : .secondary)
            Text("\(listener.lines.count) transcript line\(listener.lines.count == 1 ? "" : "s") saved")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        if listener.state == .denied {
            Text(listener.healthSentence)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        if listener.currentArchiveURL != nil || listener.lastArchiveURL != nil {
            Button("Show recording in Finder") { listener.revealLastRecording() }
        }
    }

    private var meetingQuiet: String { "No call detected." }

    private func toggle() {
        if listener.state.isCapturing || listener.state == .starting {
            listener.stop()
        } else {
            listener.start(reason: .manual)
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
            Text("Sign in to sync transcripts")
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
