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

    /// How long after a line is sent a near-copy of it is still the same AUDIO
    /// arriving twice, rather than a person saying the thing again.
    ///
    /// It is the utterance gap, not a number of its own, and the reason is
    /// arithmetic rather than taste. Two separately-flushed lines are two
    /// lines because a pause of at least `utteranceGap` ended the first one —
    /// and the second line then costs however many seconds it takes to say.
    /// So a person who repeats themselves cannot land the second delivery any
    /// sooner than the gap plus the length of what they said, whatever they
    /// do. A recognizer handing back audio it already decoded pays neither
    /// cost: the words exist already.
    ///
    /// Both ends of that are measured, not assumed. `run_flush_policy_tests.sh`
    /// drives the real cursor and the real flush clock over every speaking
    /// rate and every pause that can produce two lines of one phrase, and the
    /// closest a genuine repeat ever lands is 3.4 seconds — four words at five
    /// words a second with the shortest pause that still makes two lines. The
    /// recorded machine duplicate of 2026-08-17 landed at 2.0 seconds. The gap
    /// sits between them and a check goes red if it stops doing so.
    ///
    /// It was twelve seconds, which is above that floor, and the cost was
    /// root-caused on 2026-08-24 in
    /// research/2026-08-24-why-voice-tests-dont-complete.md: a tester saying a
    /// phrase, watching for the row, and saying it again got ONE row for two
    /// utterances, with no trace of the second anywhere. Three attempts, two
    /// rows, and the one that vanished was the middle one. Saying it again to
    /// see whether it worked is the single most common thing a person does
    /// when checking a microphone, and it was the one thing this guard was
    /// guaranteed to eat.
    ///
    /// Reaching past the gap is also this policy contradicting itself. A pause
    /// that long ends an utterance everywhere else in this file — it is what
    /// `flushReason` calls `.gap` and what `cutContinues` refuses to reach
    /// across. A window wider than that calls the same line a new utterance
    /// and a repeat of the last one in the same breath.
    var echoWindow: TimeInterval { utteranceGap }

    /// Is this line the same audio arriving a second time?
    ///
    /// Not losing words cost something: the recognizer revises, and a flush
    /// on the ceiling followed by a banked window can deliver the SAME
    /// sentence twice in slightly different words. Live 2026-08-17, two
    /// seconds apart: "Yeah I know where it is" then "Yeah I know it is".
    /// Nothing was lost — it was said once, and a transcript that repeats
    /// itself reads as broken to the person watching it.
    ///
    /// The words cannot be what decides this, and that is the whole design.
    /// A recognizer re-rendering an utterance and a person deliberately
    /// repeating one produce the same words on purpose; comparing them can
    /// only ever guess, and the guess it made was the wrong one for every
    /// manual test anybody ran. `window` is what decides, on the one thing the
    /// two events genuinely differ in — whether there was time to say it
    /// again. The word comparison below only runs INSIDE that window, where no
    /// person could have re-spoken four words, and its job there is narrowed
    /// to recognising one utterance in two renderings.
    ///
    /// Judged on shared words rather than characters, because the difference
    /// between two hypotheses of one sentence is usually a word appearing or
    /// vanishing. Deliberately conservative: real repetition ("yeah yeah
    /// yeah", "no no no") is short and identical, and dropping a genuinely
    /// new sentence is far worse than letting one echo through.
    ///
    /// `window` carries no default. It was twelve, nothing passed it, and the
    /// number outlived every reason anyone had for it.
    static func isEchoOfPrevious(_ line: String, previous: String,
                                 apart: TimeInterval,
                                 window: TimeInterval) -> Bool {
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

extension TranscriptFlushPolicy {
    /// Why a flush happened. Not what the words mean: only which of the two
    /// timers ran out, or that the recognizer stopped on its own.
    ///
    /// The ceiling above ended the silent loss, but it also ends a LINE, so
    /// someone talking without pausing gets cut every eight seconds wherever
    /// the sentence happens to be. On the call recorded 2026-08-23, 54% of the
    /// lines that arrived were four words or fewer. A reader cannot tell those
    /// shards from real one-word answers, because the phone threw away the one
    /// thing it knew for certain: that it was the clock, not the speaker, that
    /// ended the line.
    enum Reason: String, Equatable {
        /// A pause ended the utterance: a complete thought.
        case gap
        /// maxHold expired mid-speech: a cut, not an ending.
        case ceiling
        /// The recognizer finalized.
        ///
        /// Never returned below. A clock cannot see a final result arrive, so
        /// only the caller holding the recognition callback can name this one.
        case final
    }

    /// Why must these words go out now, or nil if they need not.
    ///
    /// Additive: mustFlushNow still answers exactly as it did, and callers
    /// asking it get the same ceiling they got before.
    ///
    /// - Parameters:
    ///   - pendingSince: when the words now waiting first began waiting.
    ///   - lastPartialAt: when the recognizer last revised its hypothesis.
    ///     Nil means nothing has been heard since the wait began, which is
    ///     silence of exactly that length.
    ///
    ///     Read that consequence before passing nil, because it is larger than
    ///     it looks: the ceiling is longer than the gap, so a nil partial makes
    ///     the measured silence equal to the whole wait, and every wait long
    ///     enough to reach the ceiling is by then already long enough to be a
    ///     gap. Passing nil therefore does not make .ceiling rare. It makes
    ///     .ceiling UNREACHABLE, for every input there is. The answer is always
    ///     .gap or nil, no flush is ever reported as a cut, nothing downstream
    ///     is ever linked, and no test anywhere goes red to say so. A caller
    ///     that wants cuts marked must track and pass the real time of the last
    ///     partial. The fallback is deliberately this way round: it fails to
    ///     today's behaviour, which publishes every line as a finished thought,
    ///     rather than guessing a cut and chaining unrelated sentences.
    func flushReason(pendingSince: Date?, lastPartialAt: Date?, now: Date) -> Reason? {
        guard let pendingSince else { return nil }
        let silence = now.timeIntervalSince(lastPartialAt ?? pendingSince)

        // The gap is asked FIRST, and it wins when both are true. If he
        // stopped talking and stayed stopped, the ceiling expiring behind him
        // changes nothing about what he said: the sentence was over. Reporting
        // that as a cut would tell the consumer to link the next, unrelated
        // sentence onto the end of this finished one, and unrelated lines
        // chained together read as one rambling thought nobody had.
        if silence >= utteranceGap { return .gap }

        // Still revising, so he is still mid-sentence, and the ceiling has run
        // out anyway. The words go out now for the same reason they always
        // did, but the caller is told this was a cut so the fragment can be
        // linked to what came before instead of published as a whole thought.
        if now.timeIntervalSince(pendingSince) >= maxHold { return .ceiling }

        // Mid-utterance and inside the ceiling. Answering anything here would
        // flush on every partial and shred every sentence into words.
        return nil
    }

    /// Do words that first appeared at `wordsAppearedAt` still carry on from
    /// the cut made at `cutAt`?
    ///
    /// A cut means the clock ended a line while the speaker was still going,
    /// so the words that follow it IMMEDIATELY are the rest of that sentence.
    /// This answers what "immediately" means, and it is not decoration: a
    /// caller holding "the last flush was a cut" as a bare flag has no way to
    /// stop holding it. A cut that emptied the pending words, followed by a
    /// long silence inside the same recognition task, left that flag set with
    /// nothing to clear it, and the brand-new thought spoken minutes later was
    /// published as a continuation of a sentence nobody was still saying. That
    /// is the same false head edge the gap-wins precedence above exists to
    /// prevent, arriving through silence instead of through ordering.
    ///
    /// Measured from when the words APPEARED, never from when the flush got
    /// round to them: a continuous talker's next ceiling is a whole `maxHold`
    /// after the last one, so judging by delivery time would throw away every
    /// true edge in exactly the monologue this exists for.
    ///
    /// Nil `cutAt` means nothing was cut, so nothing continues.
    func cutContinues(cutAt: Date?, wordsAppearedAt: Date) -> Bool {
        guard let cutAt else { return false }
        // The same standard that ends an utterance anywhere else here. A pause
        // this long is a new thought, whether it lands before a flush or after
        // one.
        return wordsAppearedAt.timeIntervalSince(cutAt) < utteranceGap
    }
}
