import AudioToolbox
import QuartzCore
import AVFoundation
import Foundation
import SwiftUI
import UIKit

/// THE THING THAT ACTUALLY MAKES THE NOISE.
///
/// `SoundPolicy` decides WHETHER and WHICH; this only carries the answer out.
/// The split is the usual one — the policy is pure Foundation and walked by
/// `run_sound_tests.sh`, this is plumbing that can only be checked by holding a
/// phone.
///
/// ── WHY `AudioServicesPlaySystemSound` AND NOT `AVAudioPlayer` ────────────
///
/// `PhoneListener.start()` calls
/// `setAllowHapticsAndSystemSoundsDuringRecording(true)`. That call was added
/// on build 32 because iOS silently mutes the Taptic Engine for a whole app
/// while a recording session is live, and every haptic in the product had died.
/// The same call is what permits SYSTEM SOUNDS over a live session — so this
/// path is the one iOS has already been told to allow, and it is the only one
/// guaranteed not to fight the capture session for the route.
///
/// An `AVAudioPlayer` would play through the app's own audio session, which is
/// `.playAndRecord` with `.measurement` and a pinned primary microphone. Taking
/// that session for playback risks a route change mid-capture, and a route
/// change is exactly what `PhoneListener` rebuilds the engine for. The cue
/// would cost a gap in somebody's transcript.
///
/// System sounds also respect the ring switch on their own, so no code here
/// models it and no test has to pretend to.
@MainActor
final class SoundEngine {

    static let shared = SoundEngine()

    /// `SystemSoundID` per cue, registered lazily and kept for the process
    /// lifetime. Five files, ~216 KB — cheaper to hold than to re-register.
    private var ids: [SoundPolicy.Cue: SystemSoundID] = [:]
    /// When each cue last actually played, which is what the policy's rate
    /// limit reads. Only successful plays are recorded: a refusal is not a
    /// play, and letting refusals reset the clock would make a rate-limited
    /// cue permanently silent.
    private var lastPlayed: [String: TimeInterval] = [:]
    /// The last decision, for Developer Diagnostics. Refusals are the half
    /// worth seeing.
    private(set) var lastDecision: SoundPolicy.Decision?

    private init() {}

    /// The single entry point. Facts in, noise or silence out.
    /// The listener whose tap must go deaf while a cue is sounding. Weak: the
    /// engine outlives nothing and must not keep a capture graph alive.
    weak var listener: PhoneListener?

    @discardableResult
    func play(_ cue: SoundPolicy.Cue,
              soundOn: Bool,
              microphoneRunning: Bool,
              pastFirstRun: Bool) -> SoundPolicy.Decision {
        let world = SoundPolicy.World(
            soundOn: soundOn,
            screenIsOn: !UIScreen.main.isCaptured && UIApplication.shared.applicationState != .background,
            inFront: UIApplication.shared.applicationState == .active,
            microphoneRunning: microphoneRunning,
            outputIsSpeaker: Self.outputIsBuiltInSpeaker(),
            onACall: Self.onACall(),
            pastFirstRun: pastFirstRun,
            lastPlayed: lastPlayed,
            now: Date().timeIntervalSinceReferenceDate)

        let decision = SoundPolicy.decide(cue, in: world)
        lastDecision = decision
        guard case .play = decision else { return decision }

        guard let id = soundID(for: cue) else { return decision }
        lastPlayed[cue.rawValue] = world.now
        // ARM THE DEAFNESS BEFORE THE SOUND, NEVER AFTER.
        //
        // The tap runs on the audio thread and reads this without a lock, so
        // the write has to be in front of the noise rather than racing it. This
        // is also what covers the OPENING breath: it is played before the tap
        // exists, but a 0.44s cue is still sounding when capture begins a
        // moment later, and the window is already set by then.
        listener?.deafUntil = CACurrentMediaTime() + SoundPolicy.deafenFor(cue)
        AudioServicesPlaySystemSound(id)
        return decision
    }

    /// Whether our own output would come back in through the microphone.
    ///
    /// `.defaultToSpeaker` is set by the capture session, so the built-in route
    /// is the common case and the dangerous one. Anything else — headphones,
    /// AirPods, CarPlay, a Bluetooth headset — breaks the acoustic path and
    /// lets the tonal cues through.
    private static func outputIsBuiltInSpeaker() -> Bool {
        let outputs = AVAudioSession.sharedInstance().currentRoute.outputs
        // No route at all is not evidence of headphones. Fail SAFE, which here
        // means assuming the speaker and refusing the tonal cue.
        guard !outputs.isEmpty else { return true }
        return outputs.contains { $0.portType == .builtInSpeaker || $0.portType == .builtInReceiver }
    }

    /// A call, a FaceTime, anything else holding the input. `isOtherAudioPlaying`
    /// is true for music too, which is deliberately NOT a refusal — somebody
    /// listening to a podcast still wants to know their microphone opened.
    private static func onACall() -> Bool {
        AVAudioSession.sharedInstance().currentRoute.outputs
            .contains { $0.portType == .builtInReceiver }
            && AVAudioSession.sharedInstance().isOtherAudioPlaying
    }

    private func soundID(for cue: SoundPolicy.Cue) -> SystemSoundID? {
        if let existing = ids[cue] { return existing }
        guard let url = Bundle.main.url(forResource: cue.rawValue, withExtension: "caf") else {
            // A missing asset is a build mistake, not a runtime condition. It
            // is silent here and RED in run_sound_tests.sh, which checks every
            // case of the enum has a file beside it.
            return nil
        }
        var id: SystemSoundID = 0
        guard AudioServicesCreateSystemSoundID(url as CFURL, &id) == kAudioServicesNoError else {
            return nil
        }
        ids[cue] = id
        return id
    }
}

/// The app's own switch for it, beside the haptics one it mirrors.
extension AppPreferences {
    /// Sound is ON by default and the owner can turn it off in Settings, exactly
    /// like haptics. Default-on because a cue nobody ever hears is a feature
    /// nobody ever discovers, and every cue in the vocabulary is a confirmation
    /// of something the owner themselves caused.
    static let soundKey = "preferences.sound"
}
