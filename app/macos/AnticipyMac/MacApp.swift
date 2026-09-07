import AppKit
import Combine
import SwiftUI
import UserNotifications

/// Anticipy for Mac. A window with the meeting library, a menu bar item for
/// the quick click, and one Settings pane. It listens when you ask it to,
/// offers when a meeting starts, transcribes on device, and sends the words
/// to the same brain the phone feeds. No audio ever leaves this Mac.
@main
struct AnticipyMacApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var runtime = MacRuntime()

    var body: some Scene {
        Window("Anticipy", id: "main") {
            MainWindowView()
                .environmentObject(runtime.listener)
                .environmentObject(runtime.backend)
                .environmentObject(runtime.meetings)
                .environmentObject(runtime.store)
        }
        .windowResizability(.contentMinSize)
        .defaultSize(width: 1120, height: 720)
        .commands {
            CommandGroup(replacing: .help) {
                GuideMenuItem()
            }
        }

        Window("Anticipy for Mac Guide", id: "guide") {
            GuideView()
        }
        .windowResizability(.contentMinSize)
        .defaultSize(width: 680, height: 720)

        Settings {
            MacSettingsView()
                .environmentObject(runtime.listener)
                .environmentObject(runtime.backend)
                .environmentObject(runtime.meetings)
                .environmentObject(runtime.store)
        }

        MenuBarExtra {
            MenuBarPanel()
                .environmentObject(runtime.listener)
                .environmentObject(runtime.backend)
                .environmentObject(runtime.meetings)
        } label: {
            MenuBarLabel()
                .environmentObject(runtime.listener)
                .environmentObject(runtime.meetings)
        }
        .menuBarExtraStyle(.window)
    }
}

/// The four objects the app is made of and the two wires between them,
/// alive for the whole run. THE WIRES DO NOT LIVE IN A VIEW: a window can be
/// closed, and a transcript line must reach the server whether or not
/// anybody is looking at it.
@MainActor
final class MacRuntime: ObservableObject {
    let listener = MacListener()
    let backend = MacBackend.shared
    let meetings = MeetingWatcher()
    let store = MeetingStore()
    private var posted = 0
    private var bag: Set<AnyCancellable> = []

    init() {
        // One push per settled line, at the listener's own cadence. The
        // count is tracked rather than "the last line": a session reset
        // empties the list, and a line must never be posted twice.
        listener.$lines
            .receive(on: DispatchQueue.main)
            .sink { [weak self] lines in
                guard let self else { return }
                if lines.count < self.posted { self.posted = 0 }
                for line in lines[self.posted...] {
                    self.backend.postTranscript(text: line.text,
                                                startedAt: line.startedAt,
                                                endedAt: line.endedAt,
                                                speaker: TranscriptWire.speaker(for: line.channel))
                }
                self.posted = lines.count
            }
            .store(in: &bag)

        // Auto-start is the owner's explicit setting, off by default; a
        // recording it started ends with the conversation that started it.
        meetings.$inMeeting
            .receive(on: DispatchQueue.main)
            .sink { [weak self] inMeeting in
                guard let self else { return }
                if inMeeting, self.meetings.autoStart, !self.listener.state.isCapturing,
                   self.listener.state != .starting {
                    self.listener.start(reason: .detectedMeeting(bundleID: self.meetings.activeBundleID))
                } else if !inMeeting, self.listener.startedForDetectedMeeting,
                          self.listener.state.isCapturing {
                    self.listener.stop()
                }
            }
            .store(in: &bag)
    }
}

/// The Help menu's one item. A View, because Commands cannot read the
/// environment and openWindow lives there.
struct GuideMenuItem: View {
    @Environment(\.openWindow) private var openWindow
    var body: some View {
        Button("Anticipy for Mac Guide") { openWindow(id: "guide") }
    }
}

/// The status item's glyph, and the one view alive for the whole run that
/// can call openWindow: MainWindowHandle asks it to when the window is gone.
struct MenuBarLabel: View {
    @EnvironmentObject private var listener: MacListener
    @EnvironmentObject private var meetings: MeetingWatcher
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        Image(systemName: symbol)
            .onReceive(NotificationCenter.default.publisher(for: .anticipyOpenMainWindow)) { _ in
                openWindow(id: "main")
            }
    }

    private var symbol: String {
        if listener.state.isCapturing { return "mic.fill" }
        if meetings.inMeeting { return "waveform.badge.magnifyingglass" }
        return "mic.slash"
    }
}

/// The quick click: state, start or stop, the window, quit.
struct MenuBarPanel: View {
    @EnvironmentObject private var listener: MacListener
    @EnvironmentObject private var backend: MacBackend
    @EnvironmentObject private var meetings: MeetingWatcher
    @Environment(\.openSettings) private var openSettings

    var body: some View {
        VStack(alignment: .leading, spacing: MacTheme.Space.tight) {
            HStack(spacing: MacTheme.Space.tight) {
                BrandMark(size: 22)
                Text("Anticipy")
                    .font(MacTheme.display(16, weight: .medium))
                    .foregroundStyle(MacTheme.text)
                Spacer()
                if listener.state.isCapturing { LiveDot(active: true, size: 8) }
            }
            Text(statusSentence)
                .font(.system(size: 12))
                .foregroundStyle(listener.state == .degraded || listener.state == .denied
                                 ? MacTheme.caution : MacTheme.muted)
                .fixedSize(horizontal: false, vertical: true)
            RecordControl()
                .frame(maxWidth: .infinity, alignment: .leading)
            Divider()
            Toggle("Start automatically in meetings", isOn: $meetings.autoStart)
                .toggleStyle(.checkbox)
                .font(.system(size: 12))
            Divider()
            Button("Open Anticipy") { MainWindowHandle.shared.show() }
                .buttonStyle(.ghost)
            Button("Settings") { openSettings() }
                .buttonStyle(.ghost)
            Button("Quit Anticipy") { NSApplication.shared.terminate(nil) }
                .buttonStyle(.ghost)
        }
        .padding(MacTheme.Space.base)
        .frame(width: 300)
    }

    private var statusSentence: String {
        if listener.state != .idle { return listener.healthSentence }
        if meetings.inMeeting {
            let app = MeetingLibraryPolicy.appLabel(bundleID: meetings.activeBundleID)
            return app.map { "A conversation is happening in \($0)." } ?? "A conversation is happening on this Mac."
        }
        return backend.isSignedIn ? "Quiet. No call detected." : "Quiet. Not signed in; recordings stay on this Mac."
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        UNUserNotificationCenter.current().delegate = self
        // A regular app: a Dock icon, a menu bar, a window that can be found.
        // The menu bar item stays for the quick click.
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }

    /// A click on the Dock icon with the window closed brings it back.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag { MainWindowHandle.shared.show() }
        return true
    }

    /// Closing the last window does not quit: the recorder and the menu bar
    /// item carry on, as they always have.
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        // The offer's notification was clicked: bring the window, where the
        // banner carries the Start button.
        Task { @MainActor in MainWindowHandle.shared.show() }
        completionHandler()
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter,
                                willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner])
    }
}
