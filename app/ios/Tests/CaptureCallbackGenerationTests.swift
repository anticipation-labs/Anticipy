import Foundation

enum Haptics { static func tap() {} }
enum SoundPolicy { enum Cue { case heard, listenClose } }
enum AppPreferences { static let postSignOutNoticeKey = "fixture-notice" }
struct FixtureDefaults {
    static let standard = FixtureDefaults()
    func set(_ value: String, forKey key: String) {}
}
@MainActor final class CallbackListener {
    var onLine: ((String, Date, Date, Bool) -> Void)?
    var onSpeaker: ((String, String?, Date, Date, Bool) -> Void)?
    var shouldDeliver: (() -> Bool)?
    var stopped = false
    func stop() { stopped = true; shouldDeliver = nil }
    func discardCapturedAudio() { stop() }
    func stopAfterCurrentAudio(shouldDeliver: @escaping () -> Bool) {
        stopped = true
        self.shouldDeliver = shouldDeliver
    }
}
@MainActor final class CallbackSpeaker {
    var invalidations = 0
    func invalidatePendingDeliveries() { invalidations += 1 }
}
@MainActor final class BrowserDisconnect {
    var started = false
    var continuation: CheckedContinuation<Bool, Never>?
    func unpairAgent(owner: String) async -> Bool {
        started = true
        return await withCheckedContinuation { continuation = $0 }
    }
    func complete() { continuation?.resume(returning: true); continuation = nil }
}

@MainActor final class CallbackSession {
    var accountID = "owner-a"
    var authToken = "token-a"
    var isSignedIn: Bool { !accountID.isEmpty && !authToken.isEmpty }
    var keepListening = true
    var ownerID = "device-a"
    var localPersonAccountID = "owner-a"
    var captureDeliveryGeneration = 0
    var captureStorageFailed = false
    var lastTranscriptEventID = ""
    var sessionLines: [SessionLine] = []
    var transcript: [TranscriptLine] = []
    var queued: [BufferedLine] = []
    var uploads = 0
    var writeFails = false
    let listener = CallbackListener()
    let speakerTagger = CallbackSpeaker()
    let backend = BrowserDisconnect()
    func readPendingLines() throws -> [BufferedLine] { queued }
    func persistPendingLines(_ rows: [BufferedLine]) throws {
        if writeFails { throw NSError(domain: "fixture", code: 1) }
        queued = rows
    }
    func flushUnsent() async { uploads += 1 }
    func playCue(_ cue: SoundPolicy.Cue) {}
    func clearAllPendingAppRepliesOnDevice() {}
    func invalidateRefreshes() {}
    func signOut() { accountID = ""; authToken = "" }
    func sendFixtureCallback(tagged: Bool) {
        let now = Date()
        if tagged { listener.onSpeaker?("captured before erasure", "owner", now, now, false) }
        else { listener.onLine?("captured before erasure", now, now, false) }
    }
}

@main enum CaptureCallbackGenerationTests {
    @MainActor static func main() async {
        var checks = 0
        var failures = 0
        func check(_ name: String, _ ok: Bool) {
            checks += 1
            if !ok { failures += 1 }
            print("\(ok ? "PASS" : "FAIL"): \(name)")
        }
        func drainTasks() async { for _ in 0..<20 { await Task.yield() } }
        for tagged in [false, true] {
            let control = CallbackSession()
            control.installCallbacks()
            control.sendFixtureCallback(tagged: tagged)
            await drainTasks()
            check("current callback reaches real staging (tagged: \(tagged))",
                  control.queued.count == 1 && control.uploads == 1)

            let discarded = CallbackSession()
            discarded.installCallbacks()
            discarded.sendFixtureCallback(tagged: tagged)
            // Exactly the synchronous boundary before forget's first await.
            discarded.discardListening()
            _ = discarded.clearAllPendingLinesOnDevice()
            await drainTasks()
            check("queued callback cannot restore erased speech (tagged: \(tagged))",
                  discarded.queued.isEmpty && discarded.uploads == 0)

            let forgetting = CallbackSession()
            forgetting.installCallbacks()
            let operation = Task {
                forgetting.sendFixtureCallback(tagged: tagged)
                return await forgetting.forgetThisPhone()
            }
            while !forgetting.backend.started { await Task.yield() }
            await drainTasks()
            check("real Forget awaits browser with erased queue still empty (tagged: \(tagged))",
                  forgetting.queued.isEmpty && forgetting.uploads == 0)
            forgetting.backend.complete()
            _ = await operation.value

            let erased = CallbackSession()
            erased.installCallbacks()
            erased.sendFixtureCallback(tagged: tagged)
            _ = erased.clearPendingLines()
            await drainTasks()
            check("successful unsent deletion rejects earlier queued callback (tagged: \(tagged))",
                  erased.queued.isEmpty && erased.uploads == 0)
            check("unsent deletion does not stop ongoing microphone (tagged: \(tagged))",
                  !erased.listener.stopped && erased.keepListening)
            erased.sendFixtureCallback(tagged: tagged)
            await drainTasks()
            check("new speech after deletion remains capturable (tagged: \(tagged))",
                  erased.queued.count == 1)

            let replaced = CallbackSession()
            replaced.installCallbacks()
            replaced.sendFixtureCallback(tagged: tagged)
            replaced.clearSignedInSurfaceBoundary()
            // Even an A→B→A cycle cannot give this older callback a new lease.
            replaced.accountID = "owner-b"
            replaced.authToken = "token-b"
            replaced.accountID = "owner-a"
            replaced.authToken = "token-a"
            await drainTasks()
            check("account-boundary generation survives A to B to A (tagged: \(tagged))",
                  replaced.queued.isEmpty && replaced.uploads == 0)
        }

        let pendingStop = CallbackSession()
        pendingStop.stopListening()
        let callback = pendingStop.listener.shouldDeliver
        check("current Stop has an authorized drain", callback?() == true)
        _ = pendingStop.clearPendingLines()
        check("successful unsent deletion invalidates an already captured Stop lease", callback?() == false)

        let failedErase = CallbackSession()
        failedErase.stopListening()
        let retained = failedErase.listener.shouldDeliver
        failedErase.writeFails = true
        check("failed erase reports failure", !failedErase.clearPendingLines())
        check("failed erase does not silently discard recognized Stop tail", retained?() == true)
        print("Capture callback generation: \(checks) checks, \(failures) failures")
        if failures > 0 { exit(1) }
    }
}
