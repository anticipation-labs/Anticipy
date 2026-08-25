import Foundation

/// What the audio session actually BECAME, as a VALUE rather than as a sentence.
///
/// Three `try?` calls configure the audio session in `PhoneListener` and each
/// one swallows its error, so the app can report "Listening" over a session it
/// never got. Reading the session back and journalling what it says is the
/// cheapest way to see that. Low power mode rides along because it changes what
/// iOS will let a background app do, and a day that died on a throttled phone
/// otherwise looks like a bug.
///
/// WHY A TYPE AND NOT A `var facts = "…"`. That sentence used to be built up in
/// a mutable local inside a 1,100-line file, and the whole privacy argument for
/// it rested on `run_journal_tests.sh` being able to read every line that gave
/// that local a value. A reviewer wrote two working leaks past that reading in
/// one sitting:
///
///     self.facts += self.partial                      the scan could not see a
///                                                     write through `self.`
///     (facts, lastSessionFacts) = (self.partial, "")  an assignment shape it
///                                                     did not recognise, and
///                                                     therefore read as a
///                                                     harmless mention
///
/// Both are now scan failures — but neither of them COMPILES any more either,
/// which is the point of this file. `ListenSessionFacts` is not a String, so
/// there is no `+=`, no `.append`, and no tuple assignment that can put a
/// transcript into it; the only way in is the memberwise initializer, on one
/// call site the gate reads whole. `ListenEvent.batteryRead` makes the same
/// argument with the same instrument: the privacy claim is the type.
///
/// Pure Foundation on purpose, like `ListenJournal` and `TranscriptFlushPolicy`:
/// no AVFoundation, no Speech, no UI, so `swiftc` alone can exercise it.
struct ListenSessionFacts: Equatable {
    /// `AVAudioSession.Category.rawValue` — "record", "playAndRecord", …
    let category: String
    /// `AVAudioSession.Mode.rawValue` — "measurement", "default", …
    let mode: String
    /// `ProcessInfo.isLowPowerModeEnabled` at the moment the session was read.
    let lowPower: Bool

    /// The one line this value is written to the journal as.
    ///
    /// ONE EXPRESSION, no mutable local, because `run_journal_tests.sh` puts
    /// this body through the two passes a journal literal gets: what survives
    /// outside its quotes must be the allowlisted residue, and every
    /// interpolation must be on the interpolation allowlist. A `+ speech` or a
    /// `\(partial)` added here fails one or the other.
    var sentence: String {
        "session category: \(category) mode: \(mode)"
            + (lowPower ? " · low power mode on" : "")
    }
}
