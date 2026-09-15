import AppKit
import Foundation

/// The library on disk: every meeting folder under Application Support, read
/// through MeetingLibraryPolicy, watched for change, and the ONLY writer of
/// owner.json. It never writes into meeting.json or the audio tracks; those
/// belong to MeetingArchive.
@MainActor
final class MeetingStore: ObservableObject {
    @Published private(set) var records: [MeetingRecord] = []
    @Published private(set) var lastLoadFailed = false
    @Published private(set) var pendingSidecars: [String: MeetingSidecar] = [:]
    @Published var trashError: String?

    let rootURL: URL
    private var source: DispatchSourceFileSystemObject?
    private var descriptor: Int32 = -1
    private var reloadWork: DispatchWorkItem?

    /// The same folder MeetingArchive writes into by default.
    nonisolated static var defaultRoot: URL {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Anticipy", isDirectory: true)
            .appendingPathComponent("Meetings", isDirectory: true)
    }

    init(rootURL: URL = MeetingStore.defaultRoot) {
        self.rootURL = rootURL
        try? FileManager.default.createDirectory(at: rootURL, withIntermediateDirectories: true)
        reload()
        watch()
    }

    // ------------------------------------------------------------ reading

    func reload() {
        let fm = FileManager.default
        guard let entries = try? fm.contentsOfDirectory(
            at: rootURL, includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]) else {
            records = []
            lastLoadFailed = true
            return
        }
        var loaded: [MeetingRecord] = []
        for dir in entries {
            guard (try? dir.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true else { continue }
            let manifestURL = dir.appendingPathComponent(MeetingLibraryPolicy.manifestName)
            guard let manifest = try? Data(contentsOf: manifestURL) else { continue }
            let sidecar = try? Data(contentsOf: dir.appendingPathComponent(MeetingLibraryPolicy.sidecarName))
            if let record = try? MeetingLibraryPolicy.record(manifest: manifest, sidecar: sidecar,
                                                              directoryURL: dir) {
                loaded.append(record)
            }
        }
        records = MeetingLibraryPolicy.sortedNewestFirst(loaded)
        lastLoadFailed = false
    }

    func record(id: UUID) -> MeetingRecord? {
        records.first { $0.id == id }
    }

    /// By path, not by URL: a directory URL from `contentsOfDirectory` and one
    /// built with `appendingPathComponent(_:isDirectory:)` are equal on disk
    /// and can differ in a trailing slash.
    func record(at directoryURL: URL) -> MeetingRecord? {
        records.first { $0.directoryURL.path == directoryURL.path }
    }

    // ------------------------------------------------------------ writing

    /// Writes the owner's half of a meeting folder and updates the record in
    /// place, so the sidebar's title changes on the keystroke rather than on
    /// the next directory event.
    @discardableResult
    func save(title: String?, notes: String, for id: UUID) -> Bool {
        guard let index = records.firstIndex(where: { $0.id == id }) else { return false }
        var record = records[index]
        record.ownerTitle = title
        record.notes = notes
        guard write(MeetingLibraryPolicy.sidecar(of: record), into: record.directoryURL) else { return false }
        records[index] = record
        return true
    }

    /// The live meeting has no record yet; its notes are written straight
    /// into the folder the recorder is filling, keyed by that folder.
    @discardableResult
    func saveSidecar(_ sidecar: MeetingSidecar, into directoryURL: URL) -> Bool {
        write(sidecar, into: directoryURL)
    }

    func sidecar(in directoryURL: URL) -> MeetingSidecar {
        if let pending = pendingSidecars[directoryURL.standardizedFileURL.path] { return pending }
        let url = directoryURL.appendingPathComponent(MeetingLibraryPolicy.sidecarName)
        guard let data = try? Data(contentsOf: url),
              let side = try? JSONDecoder().decode(MeetingSidecar.self, from: data) else {
            return MeetingSidecar()
        }
        return side
    }

    func hasPendingSave(in directoryURL: URL) -> Bool {
        pendingSidecars[directoryURL.standardizedFileURL.path] != nil
    }

    /// Failed edits remain available while the app is open, including after
    /// changing the selected meeting. Only a successful atomic write clears
    /// their warning; a directory refresh is not evidence that they saved.
    private func write(_ sidecar: MeetingSidecar, into directoryURL: URL) -> Bool {
        // A directory URL can differ only by its trailing slash. Key the
        // file's path so live capture and library selection share one draft.
        let key = directoryURL.standardizedFileURL.path
        let url = directoryURL.appendingPathComponent(MeetingLibraryPolicy.sidecarName)
        do {
            let data = try MeetingLibraryPolicy.sidecarData(sidecar)
            try data.write(to: url, options: .atomic)
            pendingSidecars.removeValue(forKey: key)
            return true
        } catch {
            pendingSidecars[key] = sidecar
            return false
        }
    }

    func retryPendingSaves() {
        for (directory, sidecar) in Array(pendingSidecars) {
            _ = write(sidecar, into: URL(fileURLWithPath: directory, isDirectory: true))
        }
        reload()
    }

    /// To the Trash, never deleted: the audio is the only copy there is.
    @discardableResult
    func trash(_ record: MeetingRecord) -> Bool {
        do {
            try FileManager.default.trashItem(at: record.directoryURL, resultingItemURL: nil)
            records.removeAll { $0.id == record.id }
            pendingSidecars.removeValue(forKey: record.directoryURL.standardizedFileURL.path)
            trashError = nil
            return true
        } catch {
            trashError = "This meeting couldn't be moved to the Trash. Its files have not been removed."
            return false
        }
    }

    func reveal(_ record: MeetingRecord) {
        NSWorkspace.shared.activateFileViewerSelecting([record.directoryURL])
    }

    func revealRoot() {
        NSWorkspace.shared.activateFileViewerSelecting([rootURL])
    }

    // ----------------------------------------------------------- watching

    /// One directory watch on the root: a folder appearing or vanishing
    /// reloads. Edits INSIDE a folder do not reach a root watch, and do not
    /// need to: the live meeting's words come from the listener, and the
    /// owner's own edits update the record in place above.
    private func watch() {
        descriptor = open(rootURL.path, O_EVTONLY)
        guard descriptor >= 0 else { return }
        let source = DispatchSource.makeFileSystemObjectSource(
            fileDescriptor: descriptor, eventMask: [.write, .rename, .delete], queue: .main)
        source.setEventHandler { [weak self] in self?.scheduleReload() }
        source.setCancelHandler { [descriptor] in close(descriptor) }
        source.resume()
        self.source = source
    }

    private func scheduleReload() {
        reloadWork?.cancel()
        let work = DispatchWorkItem { [weak self] in self?.reload() }
        reloadWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4, execute: work)
    }
}
