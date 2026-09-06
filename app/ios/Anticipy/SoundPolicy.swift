import Foundation

/// WHEN ANTICIPY IS ALLOWED TO MAKE A SOUND.
///
/// Until 2026-09-06 this product made none. Thirty-six screens, one hundred and
/// thirty haptic call sites, and not one audio cue anywhere — in an app whose
/// entire premise is listening. The argument for fixing that is Apple's own
/// film `Design Is How It Works`, which has no dialogue at all: its whole
/// caption track is confirmation sounds, because for Apple the noise a thing
/// makes when it works IS the evidence that it worked.
///
/// ── THE RULE THAT DECIDES THE SHAPE OF THIS FILE ──────────────────────────
///
/// **The app must never record its own voice.** That is not an aesthetic
/// preference, it is a correctness property, and it comes straight out of
/// `PhoneListener.start()`:
///
///     session.setCategory(.playAndRecord, mode: .measurement,
///                         options: [.mixWithOthers, .defaultToSpeaker, …])
///
/// `.measurement` means minimal input processing — there is no echo
/// cancellation — and `.defaultToSpeaker` means our own output goes out of the
/// speaker an inch from the live microphone. A tonal cue played on that route
/// while the engine is running can be transcribed, and a transcribed cue
/// becomes a LINE in somebody's transcript, gets pushed to the server, and can
/// become a goal. The product would be putting words in its owner's mouth.
///
/// So tonal cues are refused whenever the microphone is running AND the output
/// is the built-in speaker. Transients — a filtered-noise tick, a knock — carry
/// no pitch track and cannot be heard as speech, so they are allowed to play
/// over a live microphone. Headphones remove the acoustic path entirely, and
/// then everything is allowed.
///
/// ── WHY THIS CAN WORK AT ALL ──────────────────────────────────────────────
///
/// `PhoneListener` already calls
/// `setAllowHapticsAndSystemSoundsDuringRecording(true)` — added on build 32
/// for an unrelated reason, because iOS was silently muting the Taptic Engine
/// for the whole app while a recording session was active. That one call is
/// also what permits SYSTEM SOUNDS during recording, which is why
/// `SoundEngine` plays through `AudioServicesPlaySystemSound` rather than
/// `AVAudioPlayer`: the blessed path, and the one that respects the ring
/// switch without this file having to model it.
///
/// ── NOTHING HERE DECIDES WHAT ANYTHING MEANS ──────────────────────────────
///
/// Law 1 is untouched: every input is a flag, a count or a clock. No cue is
/// chosen by looking at words.
enum SoundPolicy {

    /// The whole vocabulary. FIVE, and the number is load-bearing: a product
    /// that makes six noises is a product somebody turns off.
    ///
    /// The raw value is the file's base name in `Resources/Sound/`. The cues
    /// are SYNTHESISED, not sourced — `Tools/synth_cues.py` is the original
    /// and regenerates every one of them deterministically.
    enum Cue: String, CaseIterable, Equatable {
        /// Listening opened. A rising breath. The one moment a person must
        /// never be uncertain about, so it is the longest cue we have.
        case listenOpen = "listen-open"
        /// A line was captured. Near-subliminal: if you notice it twice in a
        /// row it is too loud.
        case heard = "heard"
        /// Listening closed. The same breath, falling. Closure, not a stop.
        case listenClose = "listen-close"
        /// Something needs the owner. A knuckle on wood, twice, the second
        /// quieter — the rhythm of somebody being polite about it.
        case needsYou = "needs-you"
        /// An errand came back done. The only cue with warmth in it.
        case done = "done"
    }

    /// Whether a cue carries PITCH, and can therefore be mistaken for speech by
    /// our own recogniser. See the file header — this is the property the
    /// echo rule turns on, and it is a fact about the audio files themselves.
    ///
    /// `heard` is a filtered-noise tick and `needsYou` is a damped low
    /// transient; neither has a pitch track. The two breaths and `done` are
    /// tonal by design, because warmth needs pitch.
    static func isTonal(_ cue: Cue) -> Bool {
        switch cue {
        case .heard, .needsYou:                    return false
        case .listenOpen, .listenClose, .done:     return true
        }
    }

    /// Why a cue did not play. A reason, never a bare `false` — this codebase
    /// does not have functions that refuse silently, because the refusals are
    /// the interesting half and Developer Diagnostics shows them.
    enum Refusal: Equatable {
        /// The owner turned sound off. Outranks everything else here.
        case soundIsOff
        /// The screen is dark. A noise out of a pocket is not a cue, it is a
        /// noise — and the lock screen doctrine from the Live Activity work
        /// says a dark phone belongs to whoever is holding it.
        case screenIsDark
        /// The app is not in front. The background channel is `Notifier`, which
        /// the owner has already consented to; sound is not a second one.
        case notInFront
        /// A tonal cue over a live microphone on the speaker route. THE rule.
        case theMicrophoneWouldHearIt
        /// A call is in progress. Never play into somebody's conversation.
        case onACall
        /// First run has not finished. Same gate as the microphone itself:
        /// nothing about this product happens before there is an owner.
        case beforeFirstRun
        /// Too soon after the last one. Carries how long is left.
        case tooSoon(TimeInterval)
    }

    enum Decision: Equatable {
        case play(Cue)
        case refuse(Refusal)
    }

    /// Everything a decision needs, and nothing else. A struct rather than
    /// eight parameters because the call sites are in three different files and
    /// an argument added later must not silently default at two of them.
    struct World: Equatable {
        /// The owner's own switch.
        var soundOn: Bool
        /// The screen is lit.
        var screenIsOn: Bool
        /// The app is foreground-active.
        var inFront: Bool
        /// The capture engine is running RIGHT NOW — `isListening && !suspended`,
        /// not the owner's standing wish.
        var microphoneRunning: Bool
        /// Output is the built-in speaker rather than headphones. When false
        /// there is no acoustic path back into the microphone.
        var outputIsSpeaker: Bool
        var onACall: Bool
        /// First run is over and an account exists.
        var pastFirstRun: Bool
        /// When each cue last actually played, by raw value.
        var lastPlayed: [String: TimeInterval]
        var now: TimeInterval

        init(soundOn: Bool = true, screenIsOn: Bool = true, inFront: Bool = true,
             microphoneRunning: Bool = false, outputIsSpeaker: Bool = true,
             onACall: Bool = false, pastFirstRun: Bool = true,
             lastPlayed: [String: TimeInterval] = [:], now: TimeInterval = 0) {
            self.soundOn = soundOn; self.screenIsOn = screenIsOn; self.inFront = inFront
            self.microphoneRunning = microphoneRunning; self.outputIsSpeaker = outputIsSpeaker
            self.onACall = onACall; self.pastFirstRun = pastFirstRun
            self.lastPlayed = lastPlayed; self.now = now
        }
    }

    /// The tick is not a metronome. Somebody in a meeting produces a line every
    /// few seconds, and a cue on each one is a woodpecker in their pocket.
    static let heardMinimumGap: TimeInterval = 12
    /// Nothing at all fires twice inside this window, whatever the cue.
    static let minimumGap: TimeInterval = 0.35

    /// THE DECISION. Order matters and is argued case by case.
    static func decide(_ cue: Cue, in world: World) -> Decision {
        // The owner's switch first. Everything below is a reason we would not
        // have played anyway; this is the reason we may not.
        guard world.soundOn else { return .refuse(.soundIsOff) }
        // Before there is an owner there is no product. Same rule as the
        // microphone primer and the `anticipy://listen` doorbell.
        guard world.pastFirstRun else { return .refuse(.beforeFirstRun) }
        guard !world.onACall else { return .refuse(.onACall) }
        guard world.screenIsOn else { return .refuse(.screenIsDark) }
        guard world.inFront else { return .refuse(.notInFront) }

        // THE ECHO RULE. A tonal cue on the speaker route while the engine is
        // running would be recorded, transcribed, and posted as a line the
        // owner never said.
        if isTonal(cue) && world.microphoneRunning && world.outputIsSpeaker {
            return .refuse(.theMicrophoneWouldHearIt)
        }

        let gap = cue == .heard ? heardMinimumGap : minimumGap
        if let last = world.lastPlayed[cue.rawValue] {
            let since = world.now - last
            // A clock that went backwards (a timezone change, a manual set) is
            // not evidence that a cue is due. Treat it as "just played".
            if since < 0 { return .refuse(.tooSoon(gap)) }
            if since < gap { return .refuse(.tooSoon(gap - since)) }
        }
        return .play(cue)
    }

    /// How long the microphone must be deaf for after a cue starts.
    ///
    /// The cue's own length plus a tail for the room to stop ringing. This is
    /// audio plumbing — a duration, not a judgment about anybody's words — and
    /// HARNESS-LAWS names the senses as the one place thresholds are legal.
    static func deafenFor(_ cue: Cue) -> TimeInterval {
        let length: TimeInterval
        switch cue {
        case .listenOpen:  length = 0.44
        case .heard:       length = 0.04
        case .listenClose: length = 0.52
        case .needsYou:    length = 0.29
        case .done:        length = 0.85
        }
        return length + deafenTail
    }

    /// The room, not the cue. A short reverberant tail that would otherwise
    /// arrive after the file has finished playing.
    static let deafenTail: TimeInterval = 0.12

    /// The two breaths bracket the engine, and the ORDER at the call site is
    /// what makes them legal: `listenOpen` is played BEFORE `listener.start()`
    /// and `listenClose` AFTER `listener.stop()`, so `microphoneRunning` is
    /// false at both moments and the echo rule never has to refuse them.
    ///
    /// If somebody moves either call inside the running window, this returns
    /// true and the suite says so — because the cue would then go silent on the
    /// speaker route and nobody would notice a missing sound.
    static func mustBracketTheEngine(_ cue: Cue) -> Bool {
        cue == .listenOpen || cue == .listenClose
    }

    /// What Developer Diagnostics prints. Refusals are the half worth seeing.
    static func words(_ decision: Decision) -> String {
        switch decision {
        case .play(let cue): return "played \(cue.rawValue)"
        case .refuse(let why):
            switch why {
            case .soundIsOff:               return "sound is off"
            case .screenIsDark:             return "the screen is dark"
            case .notInFront:               return "the app is not in front"
            case .theMicrophoneWouldHearIt: return "the microphone would hear it"
            case .onACall:                  return "a call is in progress"
            case .beforeFirstRun:           return "first run is not over"
            case .tooSoon(let left):        return "too soon (\(Int(left.rounded()))s)"
            }
        }
    }
}
