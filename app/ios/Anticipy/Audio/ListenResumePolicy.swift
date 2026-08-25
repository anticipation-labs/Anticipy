import Foundation

/// What to do when the owner opens the app again.
///
/// THE HOLE THIS CLOSES, 2026-08-24. `resumeListeningIfWanted()` read
/// `if keepListening, !listener.isListening { listener.start() }`. A phone
/// call sets `suspended` and leaves `isListening` alone — nothing anywhere in
/// the app ever cleared it for an interruption — so the guard was false in the
/// one state it existed for, and the function did nothing at all. iOS suspends
/// the app once audio stops flowing (`UIBackgroundModes: audio` buys execution
/// only while it IS flowing), so on return there was no route back to
/// listening except the owner reaching over and toggling the switch by hand,
/// with the briefing on the same screen saying "I'm listening." A stranger's
/// day ended on a nine-o'clock call and nothing said so.
///
/// TWO FLAGS, TWO DIFFERENT FACTS, and collapsing them was the whole bug:
///
/// - `isListening` means **the owner wants me listening**. It is set by
///   `begin()` and cleared only by `stop()` — a human decision, both ways.
/// - `suspended` means **the microphone is not ours right now**. It is set by
///   the interruption notification and by the 0 Hz guard that refuses to tap a
///   silenced input, and cleared when capture comes back.
///
/// The state that needed action — wanted, nominally listening, microphone
/// actually gone — is the state the old guard answered "nothing" to. Anyone
/// tempted to fold these back into one flag in six months is re-opening this.
///
/// Pure Foundation, like `TranscriptFlushPolicy`, `ListenJournal`,
/// `ListenTally` and `ListenWatchdogPolicy`: a decision that can be shown to
/// fail with `swiftc` alone, with no simulator and no device that has to
/// receive a real phone call. That is the point of it being a file at all — a
/// one-line guard is a decision nothing can prove wrong, which is how this one
/// spent a release unable to fire.
struct ListenResumePolicy {
    enum Action: Equatable {
        case start            // listening is off and the owner wants it on
        case retakeMicrophone // listening never stopped; the mic was taken
        case nothing
    }

    /// THE ORDER IS THE BEHAVIOUR. Each line below is only meaningful because
    /// the ones above it did not fire.
    static func decide(wantsListening: Bool,
                       isListening: Bool,
                       suspended: Bool) -> Action {
        // The owner's standing wish outranks everything. Somebody who turned
        // listening off during a call must not have it turned back on for them
        // by opening the app.
        guard wantsListening else { return .nothing }

        // Nothing is listening: launch, or a return after iOS reclaimed the
        // process. Above the `suspended` line deliberately — the last state
        // written before a termination can easily be "the microphone was
        // gone", and `retakeMicrophone()` guards on `isListening`, so
        // answering it here would return immediately and silently. A no-op
        // that looks like a fix is precisely the failure this file closes.
        if !isListening { return .start }

        // Wanted, still nominally listening, and the input belongs to
        // something else. THE CASE THE OLD GUARD MISSED.
        if suspended { return .retakeMicrophone }

        // Listening, and healthy. Rebuilding capture here would flush a live
        // sentence across a swap seam every time the owner glanced at the app.
        return .nothing
    }
}
