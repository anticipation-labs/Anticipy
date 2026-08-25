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

    /// Is this line the recognizer handing back audio it already decoded?
    ///
    /// Not losing words cost this: the recognizer revises, and a flush on the
    /// ceiling followed by a replaced decode window can deliver ONE sentence
    /// twice in slightly different words. Live 2026-08-17: "Yeah I know where
    /// it is" then "Yeah I know it is". Nothing was lost — it was said once,
    /// and a transcript that repeats itself reads as broken to the person
    /// watching it. It is not cosmetic either: every duplicate runs the whole
    /// downstream act once more.
    ///
    /// TIME CANNOT ANSWER THIS, and the version that tried made the defect
    /// worse. Every line leaves the phone either on a partial callback or one
    /// `utteranceGap` after the last partial, because the silence flush is a
    /// debounce that each partial re-arms. So two lines delivered by that
    /// timer are ALWAYS more than `utteranceGap` apart — the machine's second
    /// rendering and the person's second attempt alike, for the same reason.
    /// Driven through the real cursor and the real flush clock, both land at
    /// 2.61s at their closest, and the checks below measure exactly that. The
    /// two populations share a floor, so no width of window separates them:
    /// widening it eats more genuine repeats, narrowing it lets more
    /// duplicates through, in the same proportion and in the same band. Twelve
    /// seconds ate the tester's second attempt with no trace anywhere
    /// (research/2026-08-24-why-voice-tests-dont-complete.md: three
    /// utterances, two rows, and the one that vanished was the middle one).
    /// 2.6 seconds — the gap itself — let the recorded 2026-08-17 duplicate
    /// straight back in, because a gap flush cannot land any closer than that.
    ///
    /// What DOES separate them is a fact the machine holds rather than one
    /// inferred from the words. Words already sent can only come back as
    /// unsent words when the cursor has LOST the record of having sent them:
    /// a decode window replaced mid-task (`TranscriptCursor.Update.didReset`),
    /// or a recognition task swapped out and its held audio replayed into a
    /// fresh one (`cursor.reset()` in `startRecognition`). A person repeating
    /// themselves inside one task breaks nothing — the record still describes
    /// the text, the cursor places the boundary past it, and the repeat
    /// arrives as ordinary new words. That is `lineageBrokeAt`, and it is
    /// measured, not argued: on every shape of the recorded duplicate the
    /// break is raised, on the tester's three attempts and on the tightest
    /// batched repeat there is it is not, and 250 words of continuous speech
    /// raise it zero times.
    ///
    /// `wordsAppearedAt` is what stops the arming outliving the break. Audio
    /// held across a seam is replayed into the new request at once, so a
    /// re-rendering's words appear in the same breath as the break, while
    /// someone who speaks again a minute later is a minute past it. Judged on
    /// when the words APPEARED and never on when the flush got round to them:
    /// delivery time is the thing the debounce pushes past the gap, which is
    /// precisely how the last version made itself unreachable.
    func isEchoOfPrevious(_ line: String, previous: String,
                          lineageBrokeAt: Date?, wordsAppearedAt: Date) -> Bool {
        // Lineage intact. The cursor still knows what it sent, so nothing it
        // is handing over now was handed over before.
        guard let brokeAt = lineageBrokeAt else { return false }
        let age = wordsAppearedAt.timeIntervalSince(brokeAt)
        // Words that predate the break were never delivered — they are the
        // ones the cursor banked BECAUSE the window died under them. Words
        // that first appeared a whole utterance after it were spoken, not
        // replayed: the replay is synchronous with the seam.
        guard age >= 0, age < utteranceGap else { return false }
        return Self.addsNoWord(line, beyond: previous)
    }

    /// Does `line` contain no word that `previous` did not already contain, in
    /// the order `previous` had them?
    ///
    /// This is the whole word test, and it is deliberately not a similarity
    /// score. What it replaced carried three numbers — a four-word floor, "no
    /// more than two novel words", "at least 70% of the words shared" — which
    /// together decided whether a line "says little the last one did not".
    /// That is a reading of what the words MEAN. It is item #54 of
    /// research/2026-08-24-law1-audit.md, severity H, and the most upstream
    /// meaning-decision in the system: a line it drops is delivered nowhere at
    /// all, not to the backend, not to the brain, not to the screen. Two of
    /// those three numbers could be moved and all 41 checks stayed green.
    ///
    /// Subsumption asks a transport question instead, with no number in it. A
    /// second rendering of one utterance drops words and respells them; it
    /// does not invent them. So a line contributing even one word of its own
    /// is a line the recognizer had not already given us, and it goes out.
    /// One-directional on purpose — restating a sentence and carrying on with
    /// it adds words, and those words are the whole point of the line.
    ///
    /// The known miss is a re-rendering that SPLITS a word: "it is" coming
    /// back as "it's" tokenizes to a word ("s") the first rendering never had,
    /// so that duplicate survives. That is the safe direction — dropping a
    /// genuinely new sentence is far worse than letting one echo through — and
    /// it is pinned by a check rather than left to be rediscovered.
    static func addsNoWord(_ line: String, beyond previous: String) -> Bool {
        let words = { (s: String) -> [String] in
            s.lowercased().split(whereSeparator: { !$0.isLetter && !$0.isNumber })
                .map(String.init)
        }
        let new = words(line), old = words(previous)
        // Nothing to judge. An empty line is never sent anyway, and answering
        // "yes" here would make emptiness its own justification for a drop.
        guard !new.isEmpty else { return false }
        var i = 0
        for w in new {
            while i < old.count, old[i] != w { i += 1 }
            guard i < old.count else { return false }
            i += 1
        }
        return true
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
