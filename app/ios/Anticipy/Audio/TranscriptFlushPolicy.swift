import Foundation

/// WHEN the phone sends the words it has heard, and WHICH hypothesis it takes
/// them from.
///
/// This lived inside PhoneListener, tangled with AVFoundation and Speech, so
/// it could not be tested without a device — and it was wrong in two ways that
/// only a continuous talker ever hit. It is pure Foundation on purpose: the
/// checks in Tests/TranscriptFlushPolicyTests.swift exercise THIS code, not a
/// re-implementation of it.
///
/// The live failure, 2026-08-16: ~250 words spoken without pausing reached the
/// backend as three fragments totalling 71 characters. "Every time I talk for
/// a long period of time and then I talk too quickly, the transcript doesn't
/// save. That audio goes away, and then a new one will appear."
struct TranscriptFlushPolicy {
    /// A pause this long ends an utterance.
    let utteranceGap: TimeInterval
    /// The longest that heard words may wait to be sent.
    let maxHold: TimeInterval

    init(utteranceGap: TimeInterval = 2.6, maxHold: TimeInterval = 8) {
        self.utteranceGap = utteranceGap
        self.maxHold = maxHold
    }

    /// Must the waiting words go out right now?
    ///
    /// The silence flush is a debounce: every partial result cancels the
    /// pending timer and arms a new one. Someone speaking continuously
    /// produces partials faster than the gap, so the timer never fires and
    /// NOTHING is sent for the whole monologue — until the recognizer hits
    /// Apple's task limit and finalises, by which point a collapsed final and
    /// a cursor reset have already destroyed the middle. A debounce with no
    /// ceiling is a promise the speaker can outrun; this is the ceiling.
    func mustFlushNow(pendingSince: Date?, now: Date = Date()) -> Bool {
        guard let pendingSince else { return false }
        return now.timeIntervalSince(pendingSince) >= maxHold
    }

    /// Which hypothesis a flush should take its words from.
    ///
    /// Apple revises downward as well as upward — PhoneListener's callback
    /// records a 12-second sentence collapsing to "Of August". Reading only
    /// the CURRENT text means every word the collapse dropped is gone, because
    /// the task then resets. Falling back to the fullest hypothesis actually
    /// heard means a bad revision can no longer delete speech.
    static func source(latest: String, richest: String) -> String {
        TranscriptCursor.split(richest).count > TranscriptCursor.split(latest).count
            ? richest : latest
    }

    /// How many new words a FINAL result must carry before it is worth sending.
    ///
    /// A final usually just polishes wording, and re-sending on that produced
    /// duplicates and stray fragments — hence the floor. But when the task is
    /// ending having sent nothing at all, that is not a polish, it is the
    /// entire utterance, and a floor of three is how a fast talker's words
    /// reached nobody.
    static func finalMinNewWords(everEmitted: Bool) -> Int {
        everEmitted ? 3 : 1
    }
}
