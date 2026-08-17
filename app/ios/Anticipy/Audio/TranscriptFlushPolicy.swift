import Foundation

/// WHEN the phone sends the words it has heard, and WHICH hypothesis it takes
/// them from.
///
/// This lived inside PhoneListener, tangled with AVFoundation and Speech, so
/// it could not be tested without a device — and it was wrong in a way that
/// only a continuous talker ever hit. (Choosing WHICH hypothesis to read, and
/// what a final result owes, now belong to TranscriptCursor, which banks the
/// words a discarded decode window held.) It is pure Foundation on purpose: the
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

    /// How long after a line is sent a near-copy of it is still the same
    /// sentence rather than a new one.
    let echoWindow: TimeInterval = 12

    /// Is this line the previous one said again?
    ///
    /// Not losing words cost something: the recognizer revises, and a flush
    /// on the ceiling followed by a banked window can deliver the SAME
    /// sentence twice in slightly different words. Live 2026-08-17, two
    /// seconds apart: "Yeah I know where it is" then "Yeah I know it is".
    /// Nothing was lost — it was said twice, and a transcript that repeats
    /// itself reads as broken to the person watching it.
    ///
    /// Judged on shared words rather than characters, because the difference
    /// between two hypotheses of one sentence is usually a word appearing or
    /// vanishing. Deliberately conservative: real repetition ("yeah yeah
    /// yeah", "no no no") is short and identical, and dropping a genuinely
    /// new sentence is far worse than letting one echo through.
    static func isEchoOfPrevious(_ line: String, previous: String,
                                 apart: TimeInterval,
                                 window: TimeInterval = 12) -> Bool {
        if apart > window { return false }
        let words = { (s: String) -> [String] in
            s.lowercased().split(whereSeparator: { !$0.isLetter && !$0.isNumber })
                .map(String.init)
        }
        let new = words(line), old = words(previous)
        // Too short to judge: "yes", "yeah", "ok" repeat naturally and often.
        if new.count < 4 || old.count < 4 { return false }
        // A brand-new longer thought that merely begins the same way is not
        // an echo — only something that says little the last one did not.
        let oldSet = Set(old)
        let shared = new.filter { oldSet.contains($0) }.count
        let novel = new.count - shared
        if novel > 2 { return false }
        return Double(shared) / Double(new.count) >= 0.7
    }
}
