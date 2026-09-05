import Foundation

/// What the OS said about the battery, and whether it is worth writing down.
///
/// Nothing in this product has ever measured what listening costs. An
/// always-on microphone, a speech recognizer and a 4-second watchdog are a real
/// draw, and the two costs this card removed tonight — a call minting a fresh
/// `SFSpeechRecognitionTask` every four seconds for its whole length, and the
/// journal writing fifteen identical lines a minute through an outage — were
/// both argued about with no number attached to either.
///
/// SO THIS FILE REPORTS AND DOES NOT JUDGE. There is no threshold here, no
/// "low", no "heavy", no score. A rule written while the sense is unmeasured is
/// tape by Law 5's definition, and until this ships there is not one recorded
/// drain figure in the repo to draw a line from. What the phone spent, and over
/// how long, goes on the Listening screen next to the counts that say what it
/// was doing; a person judges.
///
/// A policy rather than a `switch` at the call site, matching
/// `CaptureSourcePolicy` and `ListenWatchdogPolicy`: the two decisions below are
/// where this goes wrong, and both are checkable with `swiftc` alone.
///
/// Pure Foundation on purpose — no UIKit. The caller reads `UIDevice` and hands
/// over the two raw numbers, so the instrument that judges the battery cost of
/// listening is itself verifiable with no simulator, signing or device.
enum BatteryReadingPolicy {
    struct Reading: Equatable {
        /// 0 to 100. Never negative: -1 is iOS saying it cannot tell, and that
        /// answer arrives from `reading` as nil rather than as a number.
        let percent: Int
        /// On a charger. Deliberately not "charging": a phone sitting at 100%
        /// on a cable reports `.full`, not `.charging`, and it is spending
        /// nothing either way. What the fold needs to know is whether the
        /// interval that starts here can be read as drain at all.
        let onPower: Bool
    }

    /// The raw pair from `UIDevice`, turned into a reading or into nothing.
    ///
    /// THE SENTINEL IS THE WHOLE REASON THIS FUNCTION EXISTS.
    /// `UIDevice.current.batteryLevel` is -1.0 whenever battery monitoring was
    /// never switched on, and the simulator returns it forever. The obvious
    /// call-site cast, `Int(level * 100)`, is -100; clamp that with `max(0,)`
    /// and it is 0. Either one is a number this app would print on a screen,
    /// and the second is a phone reported as flat all day. A reading that
    /// cannot be read comes back as NOTHING — the same answer
    /// `CaptureSourcePolicy` gives for an ear it cannot name, and for the same
    /// reason: silence is recoverable, a confident wrong number is not.
    ///
    /// `stateIsKnown` is `batteryState != .unknown`. A level with no state
    /// behind it is not usable, because `onPower` is what decides whether the
    /// interval that follows may be counted as drain at all — and a reading
    /// counted as unplugged when it was charging turns the whole measurement
    /// upside down.
    static func reading(level: Float, stateIsKnown: Bool, onPower: Bool) -> Reading? {
        guard stateIsKnown else { return nil }
        // Also catches NaN, which fails every comparison. -1.0 is the documented
        // sentinel; any other negative is nonsense from the same source and is
        // refused for the same reason.
        guard level >= 0 else { return nil }
        // ROUNDED, NOT TRUNCATED. `Int(0.479 * 100)` is 47 on a phone that is at
        // 48, and the entire value of the number is that it can be subtracted
        // from the one an hour later. Truncation loses a point per reading in
        // the same direction every time, which over a day is a fabricated drain.
        //
        // Clamped at the top rather than refused: a level above 1.0 is nonsense
        // too, but a percentage over 100 on a screen is a defect a person cannot
        // act on, and 100 is the honest reading of "as full as it goes".
        let points = Int((min(level, 1) * 100).rounded())
        return Reading(percent: points, onPower: onPower)
    }

    /// Whether this reading belongs in the journal at all.
    ///
    /// THE CHURN RULE, and it is not a nicety. The thing that reads the battery
    /// is the 4-second watchdog, so an unguarded write is fifteen lines a
    /// minute — the exact rate that evicted the 400-line ring in twenty-seven
    /// minutes and turned a day that went deaf at nine in the morning into a
    /// blank, healthy-looking report. Measured, on this codebase, three commits
    /// ago. An instrument that destroys the record it lives in is worse than no
    /// instrument.
    ///
    /// A reading is written when it CHANGES and at no other time, which on a
    /// phone spending a point every ten minutes is six lines an hour. The power
    /// state counts as a change even at the same percentage: plugging in alters
    /// nothing about the number and everything about what may be done with it.
    ///
    /// `atBoundary` IS THE ONE EXCEPTION, AND IT IS THE FOLD'S. `ListenTally`
    /// measures drain only between two readings inside one unbroken session,
    /// so the window a session's cost is spent over runs from its first
    /// reading to its last — and with readings written only on change, the
    /// last one was the last CHANGE, not the stop. The stretch after it was
    /// never measured: up to ten minutes of every session on a phone spending
    /// a point every ten, and the whole of a five-minute test, which folded to
    /// "Nothing to compare yet". That undercounts the window in the one
    /// direction that makes listening look costly. A reading stamped with the
    /// start opens the window and one stamped with the stop closes it, and
    /// both are written whether or not anything changed. Boundaries are rare —
    /// one per start, one per stop — so the churn rule has nothing to protect
    /// there, and `run_journal_tests.sh` still fails the build if the 4-second
    /// tick ever passes `true`.
    static func shouldRecord(_ reading: Reading, lastRecorded: Reading?,
                             atBoundary: Bool = false) -> Bool {
        atBoundary || reading != lastRecorded
    }
}
