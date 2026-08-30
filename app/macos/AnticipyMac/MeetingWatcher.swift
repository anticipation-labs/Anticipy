import AppKit
import CoreAudio
import Foundation
import UserNotifications

/// Watches Core Audio's process list for a two-way conversation and OFFERS
/// to listen. This is MeetingOfferPolicy's law running in a menu: detection
/// is automatic, recording starts explicitly — the click belongs to the
/// owner. (The policy file in this repo is plain Foundation and is used
/// directly; this watcher supplies the only thing it cannot: the readings.)
final class MeetingWatcher: ObservableObject {

    @Published var inMeeting: Bool = false

    /// The owner can ask for hands-off mornings: when this is on, a detected
    /// meeting starts the listener without the click. Default OFF — the
    /// offer comes first, always, until the owner says otherwise.
    @Published var autoStart: Bool = UserDefaults.standard.object(forKey: "autoStartInMeetings") as? Bool ?? false {
        didSet { UserDefaults.standard.set(autoStart, forKey: "autoStartInMeetings") }
    }

    var onMeetingDetected: (() -> Void)?
    var onMeetingEnded: (() -> Void)?

    private var timer: Timer?
    private var history: [[ProcessAudioObservation]] = []

    func start() {
        guard timer == nil else { return }
        let t = Timer.scheduledTimer(withTimeInterval: 4.0, repeats: true) { [weak self] _ in
            self?.poll()
        }
        RunLoop.main.add(t, forMode: .common)
        timer = t
    }

    func stop() {
        timer?.invalidate()
        timer = nil
    }

    private func poll() {
        let observations = ProcessAudioObservation.readAll()
        history.append(observations)
        if history.count > 3 { history.removeFirst() }
        let policy = MeetingOfferPolicy()
        let offer = policy.offer(history: history,
                                 selfPID: ProcessInfo.processInfo.processIdentifier)
        let was = inMeeting
        if case .offer(let pid, let bundleID) = offer {
            inMeeting = true
            if !was { onMeetingDetected?() }
            if !autoStart, !was {
                let name = bundleID ?? "This Mac"
                let note = "A conversation on " + name + " is happening. Click the mic in the menu bar to listen."
                MeetingWatcher.postMeetingNote(note)
            }
        } else {
            inMeeting = false
            if was { onMeetingEnded?() }
        }
    }

    /// One notification per transition, phrased neutrally about the SITUATION
    /// and never about content — the app owns whether it becomes an offer or
    /// an auto-start.
    static func postMeetingNote(_ body: String) {
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert]) { granted, _ in
            guard granted else { return }
            let content = UNMutableNotificationContent()
            content.title = "Anticipy"
            content.body = body
            let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil)
            center.add(request)
        }
    }
}

/// The reading layer: which PROCESS holds which audio STREAM. Reads no
/// audio, cannot know what anybody said — the same senses the capture
/// research measured on macOS 15.6 and the policy's only permitted input.
extension ProcessAudioObservation {
    static func readAll() -> [ProcessAudioObservation] {
        let sys = AudioObjectID(kAudioObjectSystemObject)
        var addr = AudioObjectPropertyAddress(
            mSelector: kAudioHardwarePropertyProcessObjectList,
            mScope: kAudioObjectPropertyScopeGlobal,
            mElement: kAudioObjectPropertyElementMain)
        var size: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(sys, &addr, 0, nil, &size) == noErr, size > 0 else { return [] }
        let count = Int(size) / MemoryLayout<AudioObjectID>.size
        var ids = [AudioObjectID](repeating: AudioObjectID(0), count: count)
        guard AudioObjectGetPropertyData(sys, &addr, 0, nil, &size, &ids) == noErr else { return [] }

        var out: [ProcessAudioObservation] = []
        for obj in ids {
            func u32(_ sel: AudioObjectPropertySelector) -> UInt32? {
                var a = AudioObjectPropertyAddress(mSelector: sel, mScope: kAudioObjectPropertyScopeGlobal,
                                                   mElement: kAudioObjectPropertyElementMain)
                var v: UInt32 = 0
                var sz = UInt32(MemoryLayout<UInt32>.size)
                return AudioObjectGetPropertyData(obj, &a, 0, nil, &sz, &v) == noErr ? v : nil
            }
            func cstr(_ sel: AudioObjectPropertySelector) -> String? {
                var a = AudioObjectPropertyAddress(mSelector: sel, mScope: kAudioObjectPropertyScopeGlobal,
                                                   mElement: kAudioObjectPropertyElementMain)
                var cfstr: CFString? = nil
                var sz = UInt32(MemoryLayout<CFString?>.size)
                guard AudioObjectGetPropertyData(obj, &a, 0, nil, &sz, &cfstr) == noErr, let s = cfstr as String? else { return nil }
                return s
            }
            let pid = Int32(u32(kAudioProcessPropertyPID) ?? 0)
            let bundle = cstr(kAudioProcessPropertyBundleID)
            let input = (u32(kAudioProcessPropertyIsRunningInput) ?? 0) == 1
            let output = (u32(kAudioProcessPropertyIsRunningOutput) ?? 0) == 1
            if input || output {
                out.append(ProcessAudioObservation(pid: pid, bundleID: bundle,
                                                   isRunningInput: input, isRunningOutput: output))
            }
        }
        return out
    }
}
