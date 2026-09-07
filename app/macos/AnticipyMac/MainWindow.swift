import AppKit
import SwiftUI

/// Which meeting the window is showing.
enum MeetingSelection: Hashable {
    /// The one being recorded right now.
    case live
    case record(UUID)
}

extension Notification.Name {
    /// "Bring the main window", from anywhere that cannot reach SwiftUI's
    /// openWindow: the Dock's reopen, a notification click, the menu bar.
    static let anticipyOpenMainWindow = Notification.Name("ai.anticipy.mac.openMainWindow")
}

/// Where the main window is, if it exists. SwiftUI owns the window and its
/// delegate; this only remembers it. When the window has been closed, show()
/// asks the App to open it again through the notification above, which the
/// menu bar item (alive for the whole run) turns into openWindow.
@MainActor
final class MainWindowHandle {
    static let shared = MainWindowHandle()
    private(set) weak var window: NSWindow?

    func adopt(_ window: NSWindow) {
        guard self.window !== window else { return }
        self.window = window
        window.identifier = NSUserInterfaceItemIdentifier("anticipy.main")
    }

    func show() {
        NSApp.activate(ignoringOtherApps: true)
        if let window, window.isVisible || window.isMiniaturized {
            window.makeKeyAndOrderFront(nil)
        } else {
            NotificationCenter.default.post(name: .anticipyOpenMainWindow, object: nil)
        }
    }
}

/// Finds the NSWindow a SwiftUI view landed in and hands it to the handle.
struct WindowAdopter: NSViewRepresentable {
    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.async {
            if let window = view.window { MainWindowHandle.shared.adopt(window) }
        }
        return view
    }
    func updateNSView(_ nsView: NSView, context: Context) {
        if let window = nsView.window { MainWindowHandle.shared.adopt(window) }
    }
}

/// The main window: first run until it has been walked, the library after.
struct MainWindowView: View {
    @AppStorage(OnboardingRoute.storageKey) private var hasOnboarded = false
    @AppStorage(MacAppearance.key) private var appearanceRaw = MacAppearance.light.rawValue

    var body: some View {
        Group {
            if OnboardingRoute.initial(hasOnboarded: hasOnboarded) == .done {
                LibraryView()
            } else {
                OnboardingView()
            }
        }
        .frame(minWidth: 940, minHeight: 600)
        .background(WindowAdopter())
        .preferredColorScheme(MacAppearance(rawValue: appearanceRaw).colorScheme)
    }
}

// MARK: - The library

struct LibraryView: View {
    @EnvironmentObject private var backend: MacBackend
    @EnvironmentObject private var listener: MacListener
    @EnvironmentObject private var meetings: MeetingWatcher
    @EnvironmentObject private var store: MeetingStore
    @Environment(\.openWindow) private var openWindow
    @State private var selection: MeetingSelection?
    @State private var dismissedOfferPID: Int32?
    @State private var confirmTrash: MeetingRecord?

    var body: some View {
        NavigationSplitView {
            MeetingSidebar(selection: $selection, confirmTrash: $confirmTrash)
                .navigationSplitViewColumnWidth(min: 240, ideal: 280, max: 360)
        } detail: {
            ZStack(alignment: .top) {
                MacTheme.bg.ignoresSafeArea()
                detail
                offerBanner
            }
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) { RecordControl() }
        }
        .background(MacTheme.bg)
        .onChange(of: listener.state) { _, state in
            if state == .starting { selection = .live }
            if state == .idle || state == .denied { selectNewestIfLive() }
        }
        .onChange(of: listener.lastArchiveURL) { _, url in
            // The recorder closed a folder; read it back and land on it.
            store.reload()
            if let url, let record = store.record(at: url) {
                selection = .record(record.id)
            }
        }
        .onChange(of: meetings.inMeeting) { _, inMeeting in
            if !inMeeting { dismissedOfferPID = nil }
        }
        .confirmationDialog(
            "Move this meeting to the Trash?",
            isPresented: Binding(get: { confirmTrash != nil }, set: { if !$0 { confirmTrash = nil } }),
            titleVisibility: .visible
        ) {
            Button("Move to Trash", role: .destructive) {
                if let record = confirmTrash {
                    if selection == .record(record.id) { selection = nil }
                    store.trash(record)
                }
                confirmTrash = nil
            }
            Button("Keep", role: .cancel) { confirmTrash = nil }
        } message: {
            Text("The audio and the transcript go to the Trash together. Nothing on the server is touched.")
        }
    }

    @ViewBuilder private var detail: some View {
        switch selection {
        case .live:
            if listener.state != .idle {
                LiveMeetingView()
            } else {
                EmptyLibraryView()
            }
        case .record(let id):
            if let record = store.record(id: id) {
                MeetingDetailView(record: record)
                    .id(record.id)
            } else {
                EmptyLibraryView()
            }
        case nil:
            EmptyLibraryView()
        }
    }

    /// The offer, when a call is happening and nothing is recording. Not
    /// shown when auto-start is on, because then it is not an offer.
    private var offerIsUp: Bool {
        meetings.inMeeting && !listener.state.isCapturing && listener.state != .starting
            && !meetings.autoStart && dismissedOfferPID != meetings.activePID
    }

    @ViewBuilder private var offerBanner: some View {
        if offerIsUp { offerBannerBody }
    }

    private var offerBannerBody: some View {
        let app = MeetingLibraryPolicy.appLabel(bundleID: meetings.activeBundleID)
        return HStack(spacing: MacTheme.Space.snug) {
            LiveDot(active: true, size: 8, color: MacTheme.fill)
            Text(app.map { "A conversation is happening in \($0)." } ?? "A conversation is happening on this Mac.")
                .font(MacTheme.aside.weight(.medium))
                .foregroundStyle(MacTheme.text)
            Spacer()
            Button("Not now") { dismissedOfferPID = meetings.activePID }
                .buttonStyle(.ghost)
            Button("Start recording") {
                listener.start(reason: .detectedMeeting(bundleID: meetings.activeBundleID))
            }
            .buttonStyle(.primary)
        }
        .padding(.horizontal, MacTheme.Space.base)
        .padding(.vertical, MacTheme.Space.snug)
        .background(
            RoundedRectangle(cornerRadius: MacTheme.Radius.card, style: .continuous)
                .fill(MacTheme.raised)
                .overlay(RoundedRectangle(cornerRadius: MacTheme.Radius.card, style: .continuous)
                    .strokeBorder(MacTheme.edge, lineWidth: 1))
                .shadow(color: MacTheme.ink.opacity(0.12), radius: 14, y: 6)
        )
        .padding(MacTheme.Space.base)
        .transition(.move(edge: .top).combined(with: .opacity))
    }

    private func selectNewestIfLive() {
        guard selection == .live else { return }
        if let url = listener.lastArchiveURL, let record = store.record(at: url) {
            selection = .record(record.id)
        } else {
            selection = store.records.first.map { .record($0.id) }
        }
    }
}

/// Start and Stop, in the toolbar, with the one sentence about the wire.
struct RecordControl: View {
    @EnvironmentObject private var listener: MacListener

    var body: some View {
        HStack(spacing: MacTheme.Space.snug) {
            if listener.state != .idle {
                Text(listener.healthSentence)
                    .font(.system(size: 12))
                    .foregroundStyle(listener.state == .degraded || listener.state == .denied
                                     ? MacTheme.caution : MacTheme.muted)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .frame(maxWidth: 360, alignment: .trailing)
                    .help(listener.healthSentence)
            }
            switch listener.state {
            case .idle, .denied:
                Button {
                    listener.start(reason: .manual)
                } label: {
                    Label("Start recording", systemImage: "record.circle")
                }
                .buttonStyle(.primary)
                .keyboardShortcut("r", modifiers: [.command])
            case .starting:
                Button("Cancel") { listener.stop() }
                    .buttonStyle(.secondary)
            case .recording, .degraded:
                Button {
                    listener.stop()
                } label: {
                    Label("Stop recording", systemImage: "stop.fill")
                }
                .buttonStyle(.alarm)
                .keyboardShortcut(".", modifiers: [.command])
            case .finishing:
                HStack(spacing: MacTheme.Space.tight) {
                    ProgressView().controlSize(.small)
                    Text("Finishing").font(MacTheme.aside).foregroundStyle(MacTheme.muted)
                }
            }
        }
    }
}

// MARK: - Sidebar

struct MeetingSidebar: View {
    @EnvironmentObject private var backend: MacBackend
    @EnvironmentObject private var listener: MacListener
    @EnvironmentObject private var store: MeetingStore
    @Binding var selection: MeetingSelection?
    @Binding var confirmTrash: MeetingRecord?
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: MacTheme.Space.tight) {
                BrandMark(size: 26)
                Text("Anticipy")
                    .font(MacTheme.display(20, weight: .medium))
                    .foregroundStyle(MacTheme.text)
                Spacer()
            }
            .padding(.horizontal, MacTheme.Space.base)
            .padding(.top, MacTheme.Space.snug)
            .padding(.bottom, MacTheme.Space.tight)

            List(selection: $selection) {
                if listener.state != .idle {
                    Section {
                        LiveRow()
                            .tag(MeetingSelection.live)
                    } header: {
                        SectionLabel(text: "Now")
                    }
                }
                ForEach(groups, id: \.label) { group in
                    Section {
                        ForEach(group.records) { record in
                            MeetingRow(record: record)
                                .tag(MeetingSelection.record(record.id))
                                .contextMenu {
                                    Button("Show in Finder") { store.reveal(record) }
                                    Button("Copy as Markdown") { copy(record) }
                                    Divider()
                                    Button("Move to Trash") { confirmTrash = record }
                                }
                        }
                    } header: {
                        SectionLabel(text: group.label)
                    }
                }
            }
            .listStyle(.sidebar)
            .scrollContentBackground(.hidden)

            Divider().overlay(MacTheme.edge)
            AccountCard()
        }
        .background(MacTheme.surface)
    }

    private var groups: [MeetingLibraryPolicy.DayGroup] {
        // The folder being recorded into is the live row, not a library row.
        let livePath = listener.currentArchiveURL?.path
        let settled = store.records.filter { $0.directoryURL.path != livePath }
        return MeetingLibraryPolicy.grouped(settled, now: Date(), calendar: .current, locale: .current)
    }

    private func copy(_ record: MeetingRecord) {
        let text = MeetingLibraryPolicy.markdown(for: record, calendar: .current, locale: .current)
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }
}

struct MeetingRow: View {
    let record: MeetingRecord

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(MeetingLibraryPolicy.title(for: record))
                .font(MacTheme.aside.weight(.medium))
                .foregroundStyle(MacTheme.text)
                .lineLimit(1)
            HStack(spacing: MacTheme.Space.hair) {
                Text(MeetingLibraryPolicy.timeOfDay(record.startedAt, calendar: .current, locale: .current))
                if let seconds = MeetingLibraryPolicy.duration(of: record) {
                    Text("·")
                    Text(MeetingLibraryPolicy.durationWords(seconds))
                }
                if record.transcript.isEmpty {
                    Text("·")
                    Text("no words")
                }
            }
            .font(.system(size: 11))
            .foregroundStyle(MacTheme.muted)
        }
        .padding(.vertical, 3)
    }
}

struct LiveRow: View {
    @EnvironmentObject private var listener: MacListener
    @EnvironmentObject private var meetings: MeetingWatcher

    var body: some View {
        HStack(spacing: MacTheme.Space.tight) {
            LiveDot(active: listener.state.isCapturing, size: 8)
            VStack(alignment: .leading, spacing: 3) {
                Text(listener.state == .finishing ? "Finishing" : listener.state == .starting ? "Starting" : "Recording")
                    .font(MacTheme.aside.weight(.medium))
                    .foregroundStyle(MacTheme.text)
                Text("\(listener.lines.count) line\(listener.lines.count == 1 ? "" : "s") so far")
                    .font(.system(size: 11))
                    .foregroundStyle(MacTheme.muted)
            }
        }
        .padding(.vertical, 3)
    }
}

/// Who the Mac is, and whether its words are getting through.
struct AccountCard: View {
    @EnvironmentObject private var backend: MacBackend
    @Environment(\.openWindow) private var openWindow
    @State private var showSignIn = false

    var body: some View {
        VStack(alignment: .leading, spacing: MacTheme.Space.tight) {
            if backend.isSignedIn {
                HStack(spacing: MacTheme.Space.tight) {
                    Image(systemName: "person.crop.circle")
                        .foregroundStyle(MacTheme.accent)
                    Text(backend.ownerEmail)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(MacTheme.text)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Spacer()
                }
                Text(syncSentence)
                    .font(.system(size: 11))
                    .foregroundStyle(backend.pendingCount > 0 ? MacTheme.caution : MacTheme.muted)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                Text("Not signed in")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundStyle(MacTheme.text)
                Text("Recordings stay here. Sign in and the words reach your Anticipy.")
                    .font(.system(size: 11))
                    .foregroundStyle(MacTheme.muted)
                    .fixedSize(horizontal: false, vertical: true)
                if showSignIn {
                    SignInForm(compact: true)
                } else {
                    Button("Sign in") { withAnimation(MacTheme.spring) { showSignIn = true } }
                        .buttonStyle(.secondary)
                }
            }
        }
        .padding(MacTheme.Space.base)
    }

    private var syncSentence: String {
        switch backend.pendingCount {
        case 0: return "Every line has reached your Anticipy."
        case 1: return "1 line waiting for a connection."
        default: return "\(backend.pendingCount) lines waiting for a connection."
        }
    }
}

// MARK: - Detail

struct EmptyLibraryView: View {
    @EnvironmentObject private var listener: MacListener
    @EnvironmentObject private var store: MeetingStore
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(spacing: MacTheme.Space.card) {
            BrandMark(size: 72)
            Text(store.records.isEmpty ? "Nothing recorded yet" : "Pick a meeting")
                .font(MacTheme.display(28, weight: .medium))
                .foregroundStyle(MacTheme.text)
            Text(store.records.isEmpty
                 ? "Start a recording during a call, or let me offer when one begins. Both sides are kept as separate tracks on this Mac, and the words appear here as they are said."
                 : "Every recording keeps its transcript and your notes together, in a folder you can open any time.")
                .font(MacTheme.voice)
                .foregroundStyle(MacTheme.text2)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 440)
            HStack(spacing: MacTheme.Space.snug) {
                if listener.state == .idle {
                    Button {
                        listener.start(reason: .manual)
                    } label: {
                        Label("Start recording", systemImage: "record.circle")
                    }
                    .buttonStyle(.primary)
                }
                Button("How it works") { openWindow(id: "guide") }
                    .buttonStyle(.secondary)
            }
        }
        .padding(MacTheme.Space.hero)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// One finished meeting: title, facts, transcript on the left, notes on the
/// right. Edits go to owner.json through the store; the transcript is read
/// only, because it is what was said.
struct MeetingDetailView: View {
    let record: MeetingRecord
    @EnvironmentObject private var store: MeetingStore
    @State private var title: String = ""
    @State private var notes: String = ""
    @State private var copied = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
                .padding(.horizontal, MacTheme.Space.roomy)
                .padding(.top, MacTheme.Space.card)
                .padding(.bottom, MacTheme.Space.base)
            Divider().overlay(MacTheme.edge)
            HSplitView {
                TranscriptPane(startedAt: record.startedAt, lines: record.transcript,
                               liveOwner: "", liveSystem: "")
                    .frame(minWidth: 360)
                NotesPane(text: $notes)
                    .frame(minWidth: 260, idealWidth: 340)
            }
        }
        .onAppear {
            title = record.ownerTitle ?? ""
            notes = record.notes
        }
        .onChange(of: title) { _, new in save(title: new, notes: notes) }
        .onChange(of: notes) { _, new in save(title: title, notes: new) }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: MacTheme.Space.tight) {
            TextField(MeetingLibraryPolicy.title(for: record), text: $title)
                .textFieldStyle(.plain)
                .font(MacTheme.display(30, weight: .medium))
                .foregroundStyle(MacTheme.text)
            HStack(spacing: MacTheme.Space.tight) {
                Text(MeetingLibraryPolicy.longDate(record.startedAt, calendar: .current, locale: .current))
                if let seconds = MeetingLibraryPolicy.duration(of: record) {
                    Text("·")
                    Text(MeetingLibraryPolicy.durationWords(seconds))
                }
                if let app = MeetingLibraryPolicy.appLabel(bundleID: record.detectedBundleID) {
                    Text("·")
                    Text("on \(app)")
                }
                Text("·")
                Text("\(record.transcript.count) line\(record.transcript.count == 1 ? "" : "s")")
                Spacer()
                Button(copied ? "Copied" : "Copy as Markdown") { copy() }
                    .buttonStyle(.ghost)
                Button("Show in Finder") { store.reveal(record) }
                    .buttonStyle(.ghost)
            }
            .font(.system(size: 12))
            .foregroundStyle(MacTheme.muted)
        }
    }

    private func save(title: String, notes: String) {
        let clean = title.trimmingCharacters(in: .whitespacesAndNewlines)
        store.save(title: clean.isEmpty ? nil : clean, notes: notes, for: record.id)
    }

    private func copy() {
        var current = record
        current.ownerTitle = title
        current.notes = notes
        let text = MeetingLibraryPolicy.markdown(for: current, calendar: .current, locale: .current)
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
        copied = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) { copied = false }
    }
}

/// The meeting being recorded: the clock, the health of both wires, the
/// lines as they settle and the two partial hypotheses underneath them.
/// Notes typed now are written into the recorder's folder and are there when
/// the meeting becomes a record.
struct LiveMeetingView: View {
    @EnvironmentObject private var listener: MacListener
    @EnvironmentObject private var meetings: MeetingWatcher
    @EnvironmentObject private var store: MeetingStore
    @State private var notes = ""
    @State private var notesFolder: URL?
    @State private var startedAt = Date()

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
                .padding(.horizontal, MacTheme.Space.roomy)
                .padding(.top, MacTheme.Space.card)
                .padding(.bottom, MacTheme.Space.base)
            Divider().overlay(MacTheme.edge)
            HSplitView {
                TranscriptPane(startedAt: startedAt, lines: listener.lines,
                               liveOwner: listener.liveOwnerText,
                               liveSystem: listener.liveSystemText)
                    .frame(minWidth: 360)
                NotesPane(text: $notes)
                    .frame(minWidth: 260, idealWidth: 340)
            }
        }
        .onAppear { adoptFolder() }
        .onChange(of: listener.currentArchiveURL) { _, _ in adoptFolder() }
        .onChange(of: notes) { _, new in
            guard let folder = notesFolder else { return }
            store.saveSidecar(MeetingSidecar(title: nil, notes: new), into: folder)
        }
    }

    private func adoptFolder() {
        guard let folder = listener.currentArchiveURL, folder != notesFolder else { return }
        notesFolder = folder
        startedAt = Date()
        notes = store.sidecar(in: folder).notes
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: MacTheme.Space.tight) {
            HStack(spacing: MacTheme.Space.snug) {
                LiveDot(active: listener.state.isCapturing, size: 11)
                Text(listener.state == .finishing ? "Finishing" : "Recording")
                    .font(MacTheme.display(30, weight: .medium))
                    .foregroundStyle(MacTheme.text)
                TimelineView(.periodic(from: startedAt, by: 1)) { tick in
                    Text(MeetingLibraryPolicy.clock(tick.date, from: startedAt))
                        .font(MacTheme.display(30, weight: .regular))
                        .foregroundStyle(MacTheme.muted)
                        .monospacedDigit()
                }
                Spacer()
            }
            HStack(spacing: MacTheme.Space.tight) {
                if let app = MeetingLibraryPolicy.appLabel(bundleID: meetings.activeBundleID),
                   listener.startedForDetectedMeeting {
                    Text("on \(app)")
                    Text("·")
                }
                Text(listener.healthSentence)
                    .foregroundStyle(listener.state == .degraded ? MacTheme.caution : MacTheme.muted)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer()
            }
            .font(.system(size: 12))
            .foregroundStyle(MacTheme.muted)
        }
    }
}

/// The words, one line per settled envelope, each with its side and clock.
struct TranscriptPane: View {
    let startedAt: Date
    let lines: [MeetingTranscriptLine]
    let liveOwner: String
    let liveSystem: String

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: MacTheme.Space.base) {
                    SectionLabel(text: "Transcript")
                        .padding(.bottom, MacTheme.Space.hair)
                    if lines.isEmpty && liveOwner.isEmpty && liveSystem.isEmpty {
                        Text("Nothing said yet.")
                            .font(MacTheme.voice)
                            .foregroundStyle(MacTheme.muted)
                    }
                    ForEach(Array(lines.enumerated()), id: \.offset) { index, line in
                        TranscriptLineView(line: line, startedAt: startedAt)
                            .id(index)
                    }
                    if !liveOwner.isEmpty { partial(liveOwner, channel: .owner) }
                    if !liveSystem.isEmpty { partial(liveSystem, channel: .system) }
                    Color.clear.frame(height: 1).id("bottom")
                }
                .padding(MacTheme.Space.roomy)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .background(MacTheme.bg)
            .onChange(of: lines.count) { _, _ in
                withAnimation(MacTheme.spring) { proxy.scrollTo("bottom", anchor: .bottom) }
            }
        }
    }

    /// A hypothesis the transcriber may still revise: shown in the muted
    /// register so it never reads as settled.
    private func partial(_ text: String, channel: MeetingCaptureChannel) -> some View {
        HStack(alignment: .top, spacing: MacTheme.Space.snug) {
            Text(MeetingLibraryPolicy.speakerLabel(channel))
                .font(MacTheme.meta)
                .foregroundStyle(MacTheme.muted)
                .frame(width: 52, alignment: .leading)
            Text(text)
                .font(MacTheme.voice.italic())
                .foregroundStyle(MacTheme.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

struct TranscriptLineView: View {
    let line: MeetingTranscriptLine
    let startedAt: Date

    var body: some View {
        HStack(alignment: .top, spacing: MacTheme.Space.snug) {
            VStack(alignment: .leading, spacing: 2) {
                Text(MeetingLibraryPolicy.speakerLabel(line.channel))
                    .font(MacTheme.meta)
                    .foregroundStyle(line.channel == .owner ? MacTheme.accent : MacTheme.text2)
                Text(MeetingLibraryPolicy.clock(line.startedAt, from: startedAt))
                    .font(MacTheme.mono)
                    .foregroundStyle(MacTheme.muted)
            }
            .frame(width: 52, alignment: .leading)
            Text(line.text)
                .font(MacTheme.voice)
                .foregroundStyle(MacTheme.text)
                .fixedSize(horizontal: false, vertical: true)
                .textSelection(.enabled)
        }
    }
}

/// The owner's notes, plain text, saved as they are typed.
struct NotesPane: View {
    @Binding var text: String

    var body: some View {
        VStack(alignment: .leading, spacing: MacTheme.Space.tight) {
            HStack {
                SectionLabel(text: "Your notes")
                Spacer()
                Text("Saved on this Mac")
                    .font(.system(size: 11))
                    .foregroundStyle(MacTheme.muted)
            }
            ZStack(alignment: .topLeading) {
                if text.isEmpty {
                    Text("Anything you want to keep beside the words.")
                        .font(MacTheme.voice)
                        .foregroundStyle(MacTheme.muted)
                        .padding(.top, 8)
                        .padding(.leading, 5)
                        .allowsHitTesting(false)
                }
                TextEditor(text: $text)
                    .font(MacTheme.voice)
                    .foregroundStyle(MacTheme.text)
                    .scrollContentBackground(.hidden)
                    .background(Color.clear)
            }
        }
        .padding(MacTheme.Space.roomy)
        .background(MacTheme.surface)
    }
}
