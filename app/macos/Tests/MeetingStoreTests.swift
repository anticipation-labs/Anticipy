import Foundation

@main
struct MeetingStoreTests {
    @MainActor static func main() async throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: root) }
        let archive = try MeetingArchive(detectedBundleID: nil, rootURL: root)
        await withCheckedContinuation { continuation in
            archive.finish { _ in continuation.resume() }
        }
        let store = MeetingStore(rootURL: root)
        let record = store.records[0]
        let sidecar = record.directoryURL.appendingPathComponent("owner.json")
        var failures = 0
        func check(_ title: String, _ result: Bool) {
            print("\(result ? "PASS" : "FAIL"): \(title)")
            if !result { failures += 1 }
        }

        store.save(title: "Saved title", notes: "Saved notes", for: record.id)
        let reopened = MeetingStore(rootURL: root)
        check("saved notes survive reopening", reopened.record(id: record.id)?.notes == "Saved notes")

        // A directory at the destination makes an atomic file write fail on
        // every Mac, without changing permissions or touching real meetings.
        try fm.removeItem(at: sidecar)
        try fm.createDirectory(at: sidecar, withIntermediateDirectories: false)
        store.save(title: "Unsaved title", notes: "Unsaved notes", for: record.id)
        check("failed save never claims the new notes were stored", store.record(id: record.id)?.notes == "Saved notes")
        check("failed save never claims the new title was stored", store.record(id: record.id)?.ownerTitle == "Saved title")
        check("failed save remains visibly pending", store.pendingSidecars.count == 1)
        let sameFolder = URL(fileURLWithPath: record.directoryURL.path,
                             isDirectory: !record.directoryURL.hasDirectoryPath)
        check("folder URL spelling cannot hide an unsaved draft",
              store.sidecar(in: sameFolder).notes == "Unsaved notes")
        store.saveSidecar(MeetingSidecar(title: "Unsaved title", notes: "Unsaved notes"), into: sameFolder)
        check("the same folder has only one pending draft", store.pendingSidecars.count == 1)
        store.reload()
        check("unsaved draft survives a library reload", store.sidecar(in: record.directoryURL).notes == "Unsaved notes")

        try fm.removeItem(at: sidecar)
        store.retryPendingSaves()
        check("retry saves the retained draft", MeetingStore(rootURL: root).record(id: record.id)?.notes == "Unsaved notes")
        check("successful retry clears the pending warning", store.pendingSidecars.isEmpty)
        store.save(title: "Recovered", notes: "Recovered notes", for: record.id)
        check("save recovers once the disk destination is writable", MeetingStore(rootURL: root).record(id: record.id)?.notes == "Recovered notes")

        let moved = root.appendingPathComponent("moved")
        try fm.moveItem(at: record.directoryURL, to: moved)
        store.trash(record)
        check("failed Trash operation retains the visible meeting", store.record(id: record.id) != nil)
        check("failed Trash operation reports the failure", store.trashError != nil)
        exit(failures == 0 ? 0 : 1)
    }
}
