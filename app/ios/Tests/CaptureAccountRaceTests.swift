import Foundation

// These stand-ins isolate persistence/ownership, not speech recognition. The
// runner extracts the production heard function verbatim rather than copying
// its guard into a second harness which could pass while the app was broken.
enum Haptics { static func tap() {} }
enum Cue { case heard }
enum FailureShape { case refused }
enum Origin { init(wireName: String) { self = .any }; case any }
enum PostDetail {
    case sentLive(from: Origin)
    case sentFromQueue(from: Origin)
    case shelved(again: Bool, failure: FailureShape)
}
enum JournalEvent { case posted(ok: Bool, detail: PostDetail); case speechDropped(count: Int) }
struct ListenJournal {
    static let shared = ListenJournal()
    func record(_ event: JournalEvent) {}
}
struct SessionLine { let text: String; var externalEventID: String? = nil }
struct TranscriptLine {
    let id: String
    let text: String
    let decision: String?
    let speaker: String?
    let source: String?
}
enum LineSource: String {
    case typed
    case phoneMic = "phone_mic"
    case pendant
    var wireName: String { rawValue }
}

actor CaptureTransport {
    enum Failure: Error { case offline }
    var pending: CheckedContinuation<String, Error>?
    var started = false
    var sentOwner = ""
    var postedIdentities: [String] = []
    var acceptedRows: [String: String] = [:]
    var readUnavailable = false
    var acceptBeforeFailure = false
    var readFailsAfterPost = false
    func post(owner: String, externalID: String) async throws -> String {
        sentOwner = owner
        postedIdentities.append(externalID)
        started = true
        return try await withCheckedThrowingContinuation { pending = $0 }
    }
    func complete(ok: Bool) {
        if ok || acceptBeforeFailure, let id = postedIdentities.last { acceptedRows[id] = "A-posted" }
        readUnavailable = readFailsAfterPost
        if ok { pending?.resume(returning: "A-posted") }
        else { pending?.resume(throwing: Failure.offline) }
        pending = nil
    }
    func lookup(_ id: String) throws -> String? {
        if readUnavailable { throw Failure.offline }
        return acceptedRows[id]
    }
    func loseResponseAndReadback() { acceptBeforeFailure = true; readFailsAfterPost = true }
    func restoreReads() { readUnavailable = false; readFailsAfterPost = false }
    func count() -> Int { postedIdentities.count }
}
struct CaptureBackend {
    let accountID: String
    let transport: CaptureTransport
    func pushEvent(kind: String, text: String, speaker: String?, explicit: Bool,
                   source: String?, capture: CaptureEnvelope?, parentLine: String?, externalEventID: String?) async throws -> String {
        try await transport.post(owner: accountID, externalID: externalEventID ?? "")
    }
    func transcriptEventID(externalEventID: String) async throws -> String? {
        try await transport.lookup(externalEventID)
    }
}
@MainActor final class CaptureSession {
    var accountID = "A"
    var authToken = "A-token"
    var isSignedIn: Bool { !accountID.isEmpty && !authToken.isEmpty }
    var sessionLines: [SessionLine] = []
    var transcript: [TranscriptLine] = []
    var unsent: [BufferedLine] = []
    var backendReachable = true
    var flushingUnsent = false
    var captureStorageFailed = false
    var diskWriteFails = false
    var diskReadFails = false
    var stopped = false
    var lastTranscriptEventID = ""
    let transport = CaptureTransport()
    var backend: CaptureBackend { .init(accountID: accountID, transport: transport) }
    func playCue(_ cue: Cue) {}
    func discardListening() { stopped = true }
    func readPendingLines() throws -> [BufferedLine] {
        if diskReadFails { throw CaptureTransport.Failure.offline }
        return unsent
    }
    func persistPendingLines(_ rows: [BufferedLine]) throws {
        if diskWriteFails { throw CaptureTransport.Failure.offline }
        unsent = rows
    }
    static func postFailureShape(_ error: Error) -> FailureShape { .refused }
    func switchTo(account: String, token: String) {
        accountID = account; authToken = token
        sessionLines = []; transcript = []; lastTranscriptEventID = ""
    }
}

@MainActor final class ComposerHarness {
    var typed = ""
    var sendFailed = false
    var writing = true
    var followSentReply = false
    var onSend: (String) -> Bool = { _ in false }
}

@MainActor final class CaptureLookupBackend {
    struct BackendError: Error { let status: Int }
    var accountID = "A"
    let baseURL = URL(string: "https://unit-test.invalid")!
    var response = Data()
    var requestedURL: URL?
    func readData(from url: URL) async throws -> Data {
        requestedURL = url
        return response
    }
}

@MainActor final class DiskCaptureSession {
    let queueURL: URL
    var accountID = "A"
    var unsentStore = ""
    var captureStorageFailed = false
    var pendingCount = 0
    init(queueURL: URL) { self.queueURL = queueURL }
}

@main enum CaptureAccountRaceTests {
    @MainActor static func main() async {
        var failed = 0
        func check(_ name: String, _ ok: Bool) {
            print("\(ok ? "PASS" : "FAIL"): \(name)")
            if !ok { failed += 1 }
        }
        for source in [LineSource.typed, .phoneMic] {
            for completionOK in [true, false] {
                for destination in [("A", "A-token"), ("B", "B-token"), ("", ""), ("A", "replacement-token")] {
                    let session = CaptureSession()
                    let work = Task { await session.heard("A's private words", explicit: source == .typed, from: source) }
                    while !(await session.transport.started) { await Task.yield() }
                    let sameLease = destination.0 == "A" && destination.1 == "A-token"
                    check("staged before first POST: \(source.rawValue)", session.unsent.count == 1
                          && session.unsent.first?.externalEventID?.isEmpty == false)
                    if !sameLease { session.switchTo(account: destination.0, token: destination.1) }
                    await session.transport.complete(ok: completionOK)
                    await work.value
                    let label = "\(source.rawValue), \(completionOK ? "accepted" : "failed"), now \(destination.0)/\(destination.1)"
                    check("request retains original owner: \(label)", await session.transport.sentOwner == "A")
                    check("only current success installs parent: \(label)",
                          session.lastTranscriptEventID == (sameLease && completionOK ? "A-posted" : ""))
                    check("stale/failed completion preserves original owner in outbox: \(label)",
                          session.unsent.count == (sameLease && completionOK ? 0 : 1)
                          && session.unsent.allSatisfy { $0.account == "A" })
                }
            }
        }
        let signedOut = CaptureSession()
        signedOut.switchTo(account: "", token: "")
        await signedOut.heard("Nobody owns this", from: .phoneMic)
        check("signed-out callback does not publish a local echo", signedOut.transcript.isEmpty && signedOut.sessionLines.isEmpty)
        check("signed-out callback never starts network", !(await signedOut.transport.started))
        for readFailure in [true, false] {
            let brokenDisk = CaptureSession()
            brokenDisk.diskReadFails = readFailure
            brokenDisk.diskWriteFails = !readFailure
            check("failed disk rejects typed acceptance (read failure: \(readFailure))", !brokenDisk.acceptTyped("keep draft"))
            check("failed disk publishes no false local echo", brokenDisk.transcript.isEmpty && brokenDisk.unsent.isEmpty)
            await Task.yield()
            check("failed disk starts no POST", await brokenDisk.transport.count() == 0)
        }
        let lost = CaptureSession()
        await lost.transport.loseResponseAndReadback()
        let pending = Task { await lost.heard("survive restart", from: .typed) }
        while !(await lost.transport.started) { await Task.yield() }
        let stableID = lost.unsent.first!.externalEventID
        check("session echo carries the exact durable upload identity", stableID != nil && lost.sessionLines.first?.externalEventID == stableID)
        await lost.transport.complete(ok: false)
        await pending.value
        check("lost response+readback retains stable pending identity", lost.unsent.first?.externalEventID == stableID)
        // Reconstruct the persisted payload exactly as a relaunch does. No
        // in-memory sent flag is available to reconcile the already accepted row.
        let encoded = try! JSONEncoder().encode(lost.unsent)
        lost.unsent = try! JSONDecoder().decode([BufferedLine].self, from: encoded)
        await lost.transport.restoreReads()
        await lost.flushUnsent()
        let postCount = await lost.transport.count()
        check("restart canonical read removes accepted row without another POST", lost.unsent.isEmpty && postCount == 1)
        check("canonical row ID recovers continuation parent", lost.lastTranscriptEventID == "A-posted")

        let legacy = CaptureSession()
        legacy.unsent = [.init(text: "old queue", explicit: true, speaker: nil, account: "A")]
        let retry = Task { await legacy.flushUnsent() }
        while !(await legacy.transport.started) { await Task.yield() }
        check("legacy owned row receives persisted ID before retry", legacy.unsent.first?.externalEventID?.isEmpty == false)
        await legacy.transport.complete(ok: true)
        await retry.value

        let typed = CaptureSession()
        let composer = ComposerHarness()
        composer.typed = "first draft"
        composer.onSend = { typed.acceptTyped($0) }
        composer.send()
        composer.send() // before either asynchronous delivery task can begin
        check("two immediate taps enqueue once and clear only after persistence", typed.unsent.count == 1 && composer.typed.isEmpty)
        while !(await typed.transport.started) { await Task.yield() }
        composer.typed = "newer draft"
        await typed.transport.complete(ok: true)
        while typed.flushingUnsent { await Task.yield() }
        check("late delivery cannot clear a newer composer draft", composer.typed == "newer draft")
        let failedComposer = ComposerHarness()
        failedComposer.typed = "  exact draft  "
        failedComposer.send()
        check("failed enqueue keeps exact draft and shows recovery", failedComposer.typed == "  exact draft  " && failedComposer.sendFailed)

        let reader = CaptureLookupBackend()
        for (payload, expected) in [
            (#"{"items":[]}"#, "absent"),
            (#"{"items":[{"id":"row-1","kind":"transcript","owner_ref":"A","external_event_id":"stable-id"}]}"#, "row-1"),
            (#"{"items":[{"id":"row-1","kind":"transcript","owner_ref":"B","external_event_id":"stable-id"}]}"#, "throw"),
            (#"{"items":[{"id":"row-1","kind":"app_reply","owner_ref":"A","external_event_id":"stable-id"}]}"#, "throw"),
            (#"{"items":[{"id":"row-1","kind":"transcript","owner_ref":"A","external_event_id":"other-id"}]}"#, "throw"),
            (#"{"items":[{"id":"","kind":"transcript","owner_ref":"A","external_event_id":"stable-id"}]}"#, "throw"),
            (#"{"items":[{"kind":"transcript","owner_ref":"A","external_event_id":"stable-id"}]}"#, "throw"),
            (#"{"items":[{"id":"row-1","kind":"transcript","owner_ref":"A","external_event_id":"stable-id"},{"id":"row-2","kind":"transcript","owner_ref":"A","external_event_id":"stable-id"}]}"#, "throw"),
            ("not JSON", "throw")
        ] {
            reader.response = Data(payload.utf8)
            do {
                let actual = try await reader.transcriptEventID(externalEventID: "stable-id") ?? "absent"
                check("canonical lookup validates \(expected) response", actual == expected)
            } catch { check("canonical lookup rejects malformed/foreign response", expected == "throw") }
        }
        let filter = URLComponents(url: reader.requestedURL!, resolvingAgainstBaseURL: false)!.queryItems!.first { $0.name == "filter" }!.value!
        check("exact lookup requests owner, kind and stable ID", filter == "owner_ref=\"A\" && external_event_id=\"stable-id\" && kind=\"transcript\"")

        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            defer { try? FileManager.default.removeItem(at: directory) }
            let file = directory.appendingPathComponent("outbox.json")
            try CaptureOutboxPersistence.write(encoded, to: file)
            check("atomic file survives independent reopen", try CaptureOutboxPersistence.read(at: file) == encoded)
            do {
                try CaptureOutboxPersistence.write(encoded, to: directory.appendingPathComponent("missing/queue.json"))
                check("invalid destination must throw", false)
            } catch { check("invalid destination refuses acceptance", true) }

            let migrationFile = directory.appendingPathComponent("migrated.json")
            let disk = DiskCaptureSession(queueURL: migrationFile)
            disk.unsentStore = #"[{"text":"A old words","explicit":true,"account":"A"},{"text":"B sealed","explicit":false,"account":"B"},{"text":"unattributed","explicit":false}]"#
            let oldRows = try disk.readPendingLines()
            check("real migration decodes legacy rows without inventing identity", oldRows.count == 3 && oldRows.allSatisfy { $0.externalEventID == nil })
            try disk.persistPendingLines(oldRows)
            let reopened = DiskCaptureSession(queueURL: migrationFile)
            let reopenedRows = try reopened.readPendingLines()
            check("real queue migration persists before retiring legacy copy", disk.unsentStore.isEmpty && reopenedRows == oldRows)
            check("real pending count excludes sealed other-owner rows", disk.pendingCount == 1)
            check("real scoped clear reports success", disk.clearPendingLinesOwned(by: "A"))
            check("real scoped clear preserves B and unattributed rows", try disk.readPendingLines().map(\.account) == ["B", nil])
            let damaged = Data("invalid JSON must remain unchanged".utf8)
            try CaptureOutboxPersistence.write(damaged, to: migrationFile)
            check("real scoped clear refuses corrupt file", !disk.clearPendingLinesOwned(by: "A") && disk.captureStorageFailed)
            check("corrupt-file failure preserves original bytes", try Data(contentsOf: migrationFile) == damaged)
            check("explicit whole-device Forget can erase corrupt pending file", disk.clearAllPendingLinesOnDevice())
            check("whole-device Forget does not revive legacy rows", try disk.readPendingLines().isEmpty)
            let unavailable = DiskCaptureSession(queueURL: directory.appendingPathComponent("not-present/outbox.json"))
            unavailable.unsentStore = #"["legacy sealed words"]"#
            do {
                try unavailable.persistPendingLines(oldRows)
                check("failed replacement must throw", false)
            } catch {
                check("failed atomic replacement preserves legacy fallback", unavailable.unsentStore == #"["legacy sealed words"]"#)
            }
        } catch { check("atomic file fixture ran", false) }
        if failed > 0 { print("\(failed) capture/outbox checks failed"); exit(1) }
    }
}
