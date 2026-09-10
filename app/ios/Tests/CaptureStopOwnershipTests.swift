import Foundation

@MainActor final class StopListener {
    var authorized: (() -> Bool)?
    var stopped = false
    var discarded = false
    func stop() { stopped = true; authorized = nil }
    func stopAfterCurrentAudio(shouldDeliver: @escaping () -> Bool) {
        stopped = true
        authorized = shouldDeliver
    }
    func discardCapturedAudio() { stop(); discarded = true }
}
enum StopCue { case listenClose }
@MainActor final class StopSpeaker {
    func invalidatePendingDeliveries() {}
}
@MainActor final class StopSession {
    var captureDeliveryGeneration = 0
    var accountID = "owner-a"
    var authToken = "token-a"
    var isSignedIn: Bool { !accountID.isEmpty && !authToken.isEmpty }
    var keepListening = true
    var cueAfterStop = false
    let listener = StopListener()
    let speakerTagger = StopSpeaker()
    func playCue(_ cue: StopCue) { cueAfterStop = listener.stopped }
}

@main struct CaptureStopOwnershipTests {
    @MainActor static func main() {
        var failed = 0
        var checked = 0
        func check(_ name: String, _ ok: Bool) {
            checked += 1
            if !ok { failed += 1 }
            print("\(ok ? "PASS" : "FAIL"): \(name)")
        }
        let session = StopSession()
        session.stopListening()
        check("user Stop immediately closes microphone and standing wish", session.listener.stopped && !session.keepListening)
        check("Stop cue plays only after microphone closes", session.cueAfterStop)
        check("user Stop authorizes original account's captured tail", session.listener.authorized?() == true)
        // Do not simulate the listener's own invalidation here: this exercises
        // the independent account/token lease inside the real app callback.
        session.accountID = "owner-b"
        session.authToken = "token-b"
        check("late drain cannot adopt the next account", session.listener.authorized?() == false)
        session.accountID = "owner-a"
        session.authToken = "replacement-token"
        check("same account with a replacement token cannot adopt a drain", session.listener.authorized?() == false)
        session.authToken = ""
        session.accountID = ""
        check("signed-out completion is refused", session.listener.authorized?() == false)
        session.stopListening()
        check("signed-out Stop does not open a new drain", session.listener.authorized == nil)

        var temporary: StopSession? = StopSession()
        temporary?.stopListening()
        let pending = temporary?.listener.authorized
        temporary = nil
        check("a drain cannot keep the session alive or deliver after teardown", pending?() == false)

        let forgetting = StopSession()
        forgetting.stopListening()
        forgetting.discardListening()
        check("privacy discard clears an existing drain and standing wish",
              forgetting.listener.discarded && forgetting.listener.authorized == nil && !forgetting.keepListening)

        print("Capture Stop ownership: \(checked) checks, \(failed) failures")
        if failed != 0 { exit(1) }
    }
}
