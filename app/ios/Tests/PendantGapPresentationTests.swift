import Foundation

// Only framework/storage collaborators are doubled. The runner inserts the
// current production manager and session method bodies at the markers below.
struct SessionLine { let text: String }
enum GapEvent: Equatable {
    case transportGap(missingNotifications: Int, discardedFrames: Int)
}
final class ListenJournal {
    static let shared = ListenJournal()
    var events: [GapEvent] = []
    func record(_ event: GapEvent) { events.append(event) }
}
enum DispatchQueue {
    static let main = ImmediateQueue()
    struct ImmediateQueue { func async(execute: () -> Void) { execute() } }
}
final class CBPeripheral {}
struct CBCharacteristic {
    let uuid: String
    let value: Data?
}
final class PendantManager {
    static let audioUUID = "audio"
    static let batteryLevelUUID = "battery"
    var battery: Int?
    var onGap: ((OpusTransportGap) -> Void)?
    var onOpusFrame: ((Data) -> Void)?
    private var frameAssembler = OpusFrameAssembler()
    /* MANAGER_SOURCE */
}
final class SessionGapProbe {
    var sessionLines: [SessionLine] = []
    var pendantCapturing = true
    /* SESSION_SOURCE */
}

@main
struct PendantGapPresentationTests {
    static func main() async {
        var failures = 0
        var checks = 0
        func check(_ value: Bool, _ name: String) {
            checks += 1
            if !value { failures += 1; print("FAIL: \(name)") }
        }
        let manager = PendantManager()
        let session = SessionGapProbe()
        var decoded = 0
        manager.onOpusFrame = { _ in decoded += 1 }
        await session.startPendantTranscription(manager)
        check(manager.onOpusFrame == nil && !session.pendantCapturing,
              "production start keeps unsupported raw-audio capture disabled")
        let peripheral = CBPeripheral()
        func send(_ index: UInt8, _ counter: UInt8, _ payload: UInt8 = 0xAA) {
            manager.peripheral(peripheral, didUpdateValueFor:
                CBCharacteristic(uuid: PendantManager.audioUUID,
                                 value: Data([index, 0, counter, payload])), error: nil)
        }
        send(0, 0)
        send(1, 1)
        send(4, 0)
        check(ListenJournal.shared.events == [.transportGap(missingNotifications: 2, discardedFrames: 1)],
              "actual manager and session propagate transport counts without milliseconds")
        check(session.sessionLines.map(\.text) == [GapMarker.unknownDuration],
              "the actual UI consumer explicitly marks unknown duration")
        check(decoded == 0, "gap diagnostics never enable decoder or raw-audio delivery")
        send(5, 1)
        check(ListenJournal.shared.events.count == 1, "a drained gap is not journaled twice")
        send(5, 1)
        check(ListenJournal.shared.events.last == .transportGap(missingNotifications: 0, discardedFrames: 1),
              "duplicate corruption records only the local discarded frame")
        check(session.sessionLines.count == 2, "discard-only interruption remains visible")
        session.stopPendantTranscription(manager)
        check(manager.onGap == nil && manager.onOpusFrame == nil && !session.pendantCapturing,
              "production stop clears callbacks and leaves capture disabled")
        send(6, 0)
        send(8, 0)
        check(ListenJournal.shared.events.count == 2 && session.sessionLines.count == 2,
              "after stop no gap reaches the journal or previous session feed")
        print("Pendant gap presentation: \(checks - failures)/\(checks) passed")
        if failures > 0 { exit(1) }
    }
}
