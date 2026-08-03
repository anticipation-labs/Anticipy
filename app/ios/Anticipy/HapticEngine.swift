import CoreHaptics
import UIKit
import AVFAudio

/// Why this exists — and what it deliberately does NOT claim.
///
/// Build 32: no haptics anywhere. Build 33 set
/// `setAllowHapticsAndSystemSoundsDuringRecording(true)` (the one documented way
/// to let haptics play while a `.record` session is up) — shipped, still silent.
///
/// The honest position after that: we do not yet know what is muting the phone.
/// Apple documents `allowHapticsAndSystemSoundsDuringRecording` as a
/// SESSION-WIDE policy, not a per-API one, and documents no mode that defeats
/// it. So a second guess — "CoreHaptics escapes the mic" — is exactly that, a
/// guess, and shipping guesses is what wasted build 33.
///
/// So this type is a MEASURING INSTRUMENT, not the fix:
///   - it reads back the session flag build 33 set, which is the single most
///     decisive fact available and was never checked (it was set with `try?`,
///     so a failure was swallowed silently),
///   - it exposes a CoreHaptics test path so we can find out on real hardware
///     whether it behaves differently from UIFeedbackGenerator,
///   - it records WHY the engine stopped, which names the audio session if the
///     audio session is the culprit.
///
/// The app's normal haptics still go through `UIFeedbackGenerator` (see
/// `Haptics` in Theme.swift). That is the documented API for UI feedback, and
/// it is not replaced on a theory.
///
/// Thread safety: CoreHaptics calls `stoppedHandler`/`resetHandler` OFF the main
/// thread. All mutable state here is guarded by `lock`, and published state is
/// updated on main.
final class HapticEngine: ObservableObject {
    static let shared = HapticEngine()

    /// Live state for the diagnostic screen.
    @Published private(set) var engineRunning = false
    @Published private(set) var lastError: String?
    @Published private(set) var lastStoppedReason: String?

    let supportsHaptics: Bool = CHHapticEngine.capabilitiesForHardware().supportsHaptics

    private let lock = NSLock()
    private var engine: CHHapticEngine?
    /// Players must outlive the call that starts them, or a multi-event pattern
    /// loses its later events when the player deallocates mid-playback.
    private var players: [CHHapticPatternPlayer] = []
    /// A flapping haptic server must not be able to spin us forever.
    private var restarts = 0
    private static let maxRestarts = 5

    private init() {}

    private func publish(running: Bool? = nil, error: String? = nil,
                         stopped: String? = nil) {
        DispatchQueue.main.async {
            if let running { self.engineRunning = running }
            if let error { self.lastError = error }
            if let stopped { self.lastStoppedReason = stopped }
        }
    }

    /// Build and start the engine. Never blocks the caller: `CHHapticEngine.start()`
    /// is documented to block the calling thread until the engine is up, which is
    /// not acceptable on main during launch or a button press.
    func start() {
        guard supportsHaptics else { return }
        lock.lock()
        if engine != nil || restarts >= Self.maxRestarts {
            lock.unlock()
            return
        }
        let e: CHHapticEngine
        do {
            e = try CHHapticEngine()
        } catch {
            lock.unlock()
            publish(running: false, error: "create: \(error.localizedDescription)")
            return
        }
        // No audio events — lower latency, and one less thing to arbitrate.
        // NOT claimed as an escape from the recording session; see the note above.
        e.playsHapticsOnly = true
        e.isAutoShutdownEnabled = true
        e.stoppedHandler = { [weak self] reason in
            guard let self else { return }
            self.lock.lock()
            self.engine = nil
            self.players.removeAll()
            self.lock.unlock()
            // The reason names the culprit — .audioSessionInterrupt is exactly
            // the hypothesis we are trying to confirm or kill.
            self.publish(running: false, stopped: Self.name(for: reason))
        }
        e.resetHandler = { [weak self] in
            guard let self else { return }
            self.lock.lock()
            self.engine = nil
            self.players.removeAll()
            self.restarts += 1
            let giveUp = self.restarts >= Self.maxRestarts
            self.lock.unlock()
            self.publish(running: false, stopped: "reset")
            guard !giveUp else { return }
            // NOT a synchronous restart inside the framework's own callback
            // thread: that blocks the haptic server's queue and can recurse.
            DispatchQueue.main.async { self.start() }
        }
        engine = e
        lock.unlock()

        e.start { [weak self] error in
            guard let self else { return }
            if let error {
                self.lock.lock(); self.engine = nil; self.lock.unlock()
                self.publish(running: false, error: "start: \(error.localizedDescription)")
            } else {
                self.publish(running: true, error: nil)
            }
        }
    }

    private static func name(for reason: CHHapticEngine.StoppedReason) -> String {
        switch reason {
        case .audioSessionInterrupt: return "audioSessionInterrupt"
        case .applicationSuspended: return "applicationSuspended"
        case .idleTimeout: return "idleTimeout"
        case .systemError: return "systemError"
        case .notifyWhenFinished: return "notifyWhenFinished"
        case .engineDestroyed: return "engineDestroyed"
        case .gameControllerDisconnect: return "gameControllerDisconnect"
        @unknown default: return "unknown"
        }
    }

    /// Play a test pattern. Returns whether CoreHaptics ACCEPTED it —
    /// which is NOT the same as the user feeling it: playing into a
    /// system-muted Taptic Engine does not throw. The screen says so.
    @discardableResult
    func playTest(double: Bool = false) -> Bool {
        guard supportsHaptics else { return false }
        lock.lock()
        let live = engine
        lock.unlock()
        guard let live else {
            start()
            return false
        }
        do {
            var events = [CHHapticEvent(eventType: .hapticTransient, parameters: [
                .init(parameterID: .hapticIntensity, value: 1.0),
                .init(parameterID: .hapticSharpness, value: 0.6),
            ], relativeTime: 0)]
            if double {
                events.append(CHHapticEvent(eventType: .hapticTransient, parameters: [
                    .init(parameterID: .hapticIntensity, value: 1.0),
                    .init(parameterID: .hapticSharpness, value: 0.9),
                ], relativeTime: 0.15))
            }
            let player = try live.makePlayer(with: CHHapticPattern(events: events,
                                                                   parameters: []))
            lock.lock(); players.append(player); lock.unlock()
            try player.start(atTime: CHHapticTimeImmediate)
            // Hold the player past the pattern's own length, then let it go.
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in
                guard let self else { return }
                self.lock.lock()
                if let i = self.players.firstIndex(where: { $0 === player }) {
                    self.players.remove(at: i)
                }
                self.lock.unlock()
            }
            publish(error: nil)
            return true
        } catch {
            lock.lock(); engine = nil; lock.unlock()
            publish(running: false, error: "play: \(error.localizedDescription)")
            return false
        }
    }

    // ------------------------------------------------------------ diagnosis

    struct Report {
        var hardware: Bool
        var engineRunning: Bool
        var lowPowerMode: Bool
        /// THE decisive field. Build 33 SET this; nothing ever read it back.
        /// If it is false, the session refused the request and that is the bug.
        var allowsHapticsWhileRecording: Bool
        var sessionCategory: String
        var sessionMode: String
        var listening: Bool
        var stoppedReason: String?
        var error: String?
    }

    /// There is NO API to read Settings › Sounds & Haptics › System Haptics, so
    /// that one is named as the thing for him to check, never reported as fact.
    func report(listening: Bool) -> Report {
        let s = AVAudioSession.sharedInstance()
        let clean = { (v: String) in
            v.replacingOccurrences(of: "AVAudioSessionCategory", with: "")
             .replacingOccurrences(of: "AVAudioSessionMode", with: "")
        }
        return Report(
            hardware: supportsHaptics,
            engineRunning: engineRunning,
            lowPowerMode: ProcessInfo.processInfo.isLowPowerModeEnabled,
            allowsHapticsWhileRecording: s.allowHapticsAndSystemSoundsDuringRecording,
            sessionCategory: clean(s.category.rawValue),
            sessionMode: clean(s.mode.rawValue),
            listening: listening,
            stoppedReason: lastStoppedReason,
            error: lastError)
    }
}
