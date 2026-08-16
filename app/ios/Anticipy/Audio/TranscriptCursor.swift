import Foundation

/// Decides which part of a live speech hypothesis is NEW.
///
/// WHY THIS TYPE EXISTS (2026-08-05, the garbled-transcript fix)
///
/// `SFSpeechRecognizer` does not append to `bestTranscription.formattedString`.
/// It REWRITES it: earlier words get revised as later audio arrives, words are
/// inserted in the middle, and when the decoder's window resets the whole
/// string is REPLACED by something unrelated. The old emission layer tracked
/// progress with an integer index into that string's word array, which cannot
/// be correct against a producer that rewrites in place:
///
///   * INSERTION — "meet at Cineplex" becoming "meet at the Cineplex" pushed
///     the word count up by one, so the cursor emitted a spurious one-word
///     line containing a word already sent.
///   * DELETION — when the text got SHORTER the cursor refused to come down
///     (`emittedWords = max(emittedWords, words.count)`), so it sat above the
///     real text and SWALLOWED the next words actually spoken.
///   * RESET — a replaced window left the cursor tens of words above the new
///     text. Everything under it was permanently deleted, and what followed
///     dribbled out as 1-, 2- and 3-word slices. That is the signature Omar
///     reported: "Pill 491 kill 492", "I kill 44 sorry".
///
/// The fix is to stop counting and start comparing TEXT. This type keeps the
/// words it has actually sent, and on every callback answers one question by
/// alignment rather than arithmetic: where in this new string does the text we
/// already sent end? Everything after that point — and only that — is new.
///
/// ---------------------------------------------------------------------------
/// THE TWO DECISIONS, AND WHY THEY ARE SEPARATE
/// ---------------------------------------------------------------------------
///
/// An earlier version of this file answered both questions with one fuzzy
/// longest-common-subsequence search over the sent record, and that search was
/// free to start anywhere inside the new text. That is what let a single
/// coincidental word place a boundary in the middle of a fresh sentence and
/// delete everything in front of it. The two questions are now asked, and
/// answered, separately:
///
///   1. IS ANYTHING AT RISK?  Only the words already heard and not yet sent can
///      be lost, and they are lost only if this new text has thrown them away.
///      So the question is asked about THEM and nothing else: is at least half
///      of the unsent tail still here, and is the hypothesis as a whole still
///      more than half its length? If either answer is no, they are BANKED —
///      emitted now — because a decode window that has moved on is never
///      coming back. See `pendingSurvives`.
///
///   2. WHERE DOES THE SENT TEXT END IN THIS STRING?  Answered by an alignment
///      that starts at the BEGINNING of both the record and the text. It cannot
///      wander: a match is only usable if the words in front of it line up too,
///      and it may not open by throwing sent words away. Of the alignments it
///      finds, the one used is the one that AGREED MOST net of what it paid —
///      matches minus edits — and it is believed only if all of the following
///      hold, each of which was put there by a measured deletion:
///
///        * more than half the record actually MATCHED (not "was stepped
///          over"), or the text ran out inside our own sentence with nothing
///          edited on the way down, which is what a collapse is;
///        * more of it agreed than it paid for, twice over;
///        * the run either reached the END of the record or is unbroken;
///        * it did not shrink onto the text — sent words may be swapped for
///          words, not vanish;
///        * and if the record had already stopped describing what we were
///          shown, two agreeing words at least, not one.
///
///      See `placeBoundary`.
///
/// Banking is what makes step 1 affordable. Banked words go into the sent
/// record exactly like any other emission, so calling a deep RETRACTION a reset
/// costs a line break and nothing else — when the recognizer rebuilds, the
/// rebuild aligns against the record in step 2 and is not sent twice. The
/// reverse mistake, calling a RESET a retraction, deletes a sentence and cannot
/// be undone. So where the text cannot say which happened, this type banks.
///
/// ---------------------------------------------------------------------------
/// THE ONE RULE THIS TYPE MAY NOT BREAK
/// ---------------------------------------------------------------------------
///
/// Words that were heard and not sent leave only by being emitted. Four ways of
/// breaking it were found — by fuzzing against the integer cursor, and by an
/// adversarial read that named them M1 to M4. All four came from the same root,
/// a boundary placed on evidence that did not reach back to the start of the
/// text, and all four are now cases 16 and 17 of the unit tests, on the exact
/// inputs they were found on:
///
///   * M1, DUPLICATION. A flushed line, then a fresh window opening on a word
///     that line contains. The old search matched that one word anywhere, put
///     the boundary after it, and the next word came out ALONE mid-sentence —
///     the reported signature — before the record stopped fitting and the whole
///     window was emitted again on top of it.
///   * M2, LOSS. A one- or two-word UNSENT hypothesis silently overwritten,
///     because the shrink test was met by any single word in common, and
///     English hands no sentence its own function words ("so", "the", "we").
///   * M3, LOSS. A fresh window opening on the same few words the last line
///     opened with ("we are really not leaving at four now" -> "we are really
///     not going home to the garage"): four sent words absorbed into the
///     boundary and never emitted, and a measured sweep lost one more for every
///     word the two sentences shared.
///   * M4, LOSS. A hold. When a retraction arrived with a tail in flight the
///     old code returned early WITHOUT taking the new words in, so an `isFinal`
///     or a Stop landing during the hold emitted the stale tail and dropped
///     everything the new window had shown.
///
/// The alignment now starts at the origin and may not open by discarding sent
/// words, so a lone shared word can only place the boundary if it is the FIRST
/// word of both — and even then only if it carries the acceptance rules above.
/// There is no hold any more: every non-empty callback is folded in, and the
/// protection is banking.
///
/// ---------------------------------------------------------------------------
/// WHAT IS STILL UNDECIDABLE, STATED RATHER THAN HIDDEN
/// ---------------------------------------------------------------------------
///
/// Words that two consecutive decode windows OPEN ON in common cannot be
/// attributed to either of them. "we are leaving at four" collapsing to "we"
/// and rebuilding, and a new window that happens to open on "we", produce the
/// same callbacks in the same order — one reading's identical repeat is the
/// other's window boundary, and the recognizer does both constantly.
///
/// This type takes the collapse reading WHILE THE TEXT IS STILL INSIDE WHAT WE
/// SENT, because that reading emits nothing and can therefore still be
/// overturned; and it takes the new-speech reading the instant the text says
/// something we did not send, emitting the whole of it. So the residual error
/// is duplication of a shared opening in the rare case the collapse reading was
/// right — recoverable by anyone reading the feed — and never deletion.
///
/// It was the other way round until 2026-08-05, and case 16 of the unit tests
/// asserted the deletion as correct behaviour. The sweep in that case now runs
/// shared openings of one through six words and demands the second sentence
/// whole every time; `run_cursor_fuzz.sh` counts the seams separately and
/// prints them, so the size of the ambiguity is visible on every run.
///
/// COST, measured rather than claimed. This runs on the MAIN THREAD on every
/// partial result, and `app/ios/Tests/run_cursor_bench.sh` is the script that
/// says what that costs. On this machine, over a request grown to 800 words —
/// about five minutes of speech with no 2.6s pause anywhere in it, which is
/// past anything the app will really see, since the listener also rotates the
/// request in silence — the mean callback is around a quarter of a millisecond
/// and the worst single callback a few milliseconds.
///
/// It is NOT flat, and saying so would be easy and wrong: the mean roughly
/// doubles between a 400-word request and an 800-word one. Three things in here
/// are linear in the length of the text and none of them can be windowed away —
/// the recognizer hands over the entire transcript every time, so it has to be
/// compared to the last one, the unsent tail has to be sliced out of it, and
/// the sent record has to be checked against its head. What IS bounded is the
/// alignment: it skips the agreeing head and is banded, so an edit costs the
/// same whether it lands in a short request or a long one.
///
/// (The previous version of this file quoted "0.011 ms mean, 0.28 ms worst" and
/// cited a bench script by name. That script had never been committed and those
/// numbers came from nowhere. The script exists now, the numbers above came out
/// of it, and it prints the growth factor next to every row so the claim in
/// this comment can be checked in about ten seconds.)
///
/// It is deliberately pure: Foundation only, no timers, no audio, no I/O, no
/// reference to `PhoneListener`. Every rule below is exercised by
/// `app/ios/Tests/TranscriptCursorTests.swift`, which runs without a simulator
/// (`app/ios/Tests/run_cursor_tests.sh`), and hammered by
/// `app/ios/Tests/run_cursor_fuzz.sh`.
struct TranscriptCursor {

    // MARK: - what one recognizer callback tells the caller

    struct Update: Equatable {
        /// Text that must be sent RIGHT NOW because the recognizer threw away
        /// the window it belonged to. It is real speech; dropping it is how
        /// whole sentences used to disappear. `nil` when nothing was at risk.
        var banked: String?
        /// Did the SPOKEN CONTENT change? Re-punctuation, re-capitalisation
        /// and whitespace churn are not changes. The caller arms its pause
        /// timer on this flag and ONLY on this flag: the old code re-armed on
        /// every callback, including the identical repeats the recognizer
        /// emits while nobody is talking, which cancelled the very pause the
        /// timer existed to detect.
        var changed: Bool
        /// Did we conclude the recognizer started a new decode window?
        var didReset: Bool
    }

    // MARK: - tuning

    /// How far the alignment may drift off the diagonal. Drift is the net
    /// number of words inserted into, or deleted from, already-sent text since
    /// the record began; a few dozen is generous for one recognition request,
    /// and bounding it is what keeps the cost per callback flat.
    private static let band = 64
    /// Unsent words compared when asking "are they still here?". The tail is
    /// what a reset takes; comparing the whole of a two-minute pending stretch
    /// would cost more every callback and answer the same question.
    private static let survivalWindow = 48
    /// A hard ceiling on the sent record so one runaway request cannot grow
    /// without bound. Words dropped off the front are counted, not forgotten:
    /// `dropped` keeps the alignment's origin honest.
    private static let maxRecord = 2048

    // MARK: - state

    /// Words we have actually emitted, oldest first. This is a HISTORICAL
    /// record, not a mirror of the current hypothesis: keeping what we really
    /// sent is what stops a word being sent twice after the recognizer
    /// retracts it and then puts it back.
    private var record: [Token] = []
    /// Emitted words that fell off the front of `record` at the ceiling. They
    /// are still assumed to occupy the head of the hypothesis, so the alignment
    /// starts at `dropped` rather than at zero.
    private var dropped = 0
    /// Does `record` still describe the text we are being shown? False after a
    /// window reset, and the reason the record is REPLACED rather than appended
    /// to at the next emission — carrying a dead window's words forward would
    /// mis-place every boundary after it.
    private var recordDescribes = true
    /// The last non-empty text the recognizer gave us.
    private var hypothesis: [Token] = []
    /// That text verbatim, kept only so the next callback can notice it is the
    /// same string with more on the end and tokenize just the new part. A
    /// recognizer streaming a two-minute request hands over the WHOLE
    /// transcript several times a second; folding and splitting all of it every
    /// time is work that grows with the length of the conversation, on the main
    /// thread, and the bench shows it as the mean climbing with request size.
    private var hypothesisText = ""
    /// Words heard on the current text that have not been sent.
    private var pendingWords: [Token] = []
    /// Index into `hypothesis` where the sent text ends. Kept separately from
    /// `record.count` because absorbing an insertion moves the boundary
    /// without adding anything to the record.
    private var boundary = 0

    // MARK: - reading

    /// Heard, not yet sent. Formatted exactly as it will be emitted.
    var pending: String { Token.join(pendingWords) }
    var hasPending: Bool { !pendingWords.isEmpty }
    /// Diagnostics and tests only.
    var pendingWordCount: Int { pendingWords.count }
    var sentWordCount: Int { record.count + dropped }

    // MARK: - the recognizer spoke

    /// Fold one hypothesis into the cursor. Never drops speech: anything that
    /// can no longer be tracked comes back as `banked` for the caller to send.
    mutating func observe(_ text: String) -> Update {
        let words = tokenizeIncrementally(text)

        // An empty hypothesis is not information. The recognizer clears its
        // string all the time between commitments; treating that as the new
        // truth would throw away the pending tail, and treating it as a reset
        // would cut a line in half every time. Hold everything, wait for text.
        guard !words.isEmpty else {
            return Update(banked: nil, changed: false, didReset: false)
        }

        var banked: String?
        var didReset = false

        // 1. Is anything at risk? Only the unsent words can be, and only if
        //    this text has thrown them away. Two ways of losing them:
        //
        //      * most of them are simply not in this string any more, or
        //      * the hypothesis as a whole collapsed to less than half its
        //        length, which is what a decode window replacing itself looks
        //        like even on the rare callback where the few unsent words
        //        happen to survive it by coincidence.
        //
        //    Either way they are emitted now. If this was really a retraction
        //    the recognizer will rebuild, the rebuild will align against the
        //    record in step 2, and nothing is sent twice — a wrong guess here
        //    costs a line break. The other way round it costs a sentence.
        if !pendingWords.isEmpty {
            // Half or less of the text left. "Or less" is not a rounding
            // choice: a two-word hypothesis "Priya so" going to "so" is a
            // window boundary whose unsent word — the whole of what was at
            // risk — happens to be the word the NEXT window opens on. Judged
            // on the tail alone it looks like nothing happened, and the "so"
            // Omar said twice came out once.
            let collapsed = hypothesis.count >= 2 && words.count * 2 <= hypothesis.count
            if collapsed || !pendingSurvives(pendingWords, in: words) {
                banked = takePending()
                didReset = true
            }
        }

        // 2. Where does the text we already sent end inside this new string?
        let placed = placeBoundary(in: words)
        resyncRecord(with: words, placed)
        // The first callback on which the record stops describing what we are
        // shown IS the reset, and the only one worth reporting as such. Saying
        // it again on every callback of the new window would tell the caller
        // nothing and inflate every counter that watches the flag.
        if !placed.accepted, recordDescribes, !record.isEmpty { didReset = true }
        recordDescribes = placed.accepted

        boundary = min(max(placed.boundary, 0), words.count)
        pendingWords = Array(words[boundary...])
        let changed = didReset || !Token.sameWords(words, hypothesis)
        hypothesis = words
        hypothesisText = text
        return Update(banked: banked, changed: changed, didReset: didReset)
    }

    /// The same tokens `Token.tokenize` would produce, reusing the previous
    /// callback's work when this text is that one with more on the end.
    ///
    /// The reuse is only taken when the split cannot differ: the extra text
    /// must begin at a word boundary, or "meet at" followed by "meet atx" would
    /// come back as three tokens instead of two. Everything else falls through
    /// to the full tokenizer, so the result is identical either way and only
    /// the cost changes.
    private func tokenizeIncrementally(_ text: String) -> [Token] {
        guard !hypothesisText.isEmpty, text.hasPrefix(hypothesisText) else {
            return Token.tokenize(text)
        }
        let tail = text.dropFirst(hypothesisText.count)
        if tail.isEmpty { return hypothesis }
        let boundaryOK = tail.first.map { $0 == " " || $0 == "\n" || $0 == "\t" || $0 == "\r" }
            ?? false
        let endedOnSpace = hypothesisText.last.map {
            $0 == " " || $0 == "\n" || $0 == "\t" || $0 == "\r"
        } ?? false
        guard boundaryOK || endedOnSpace else { return Token.tokenize(text) }
        return hypothesis + Token.tokenize(String(tail))
    }

    /// Take everything heard-but-unsent as one line, and record it as sent.
    /// Consumption is all-or-nothing: the old code advanced its cursor and
    /// THEN decided the tail was too short to bother with, which is how one-
    /// and two-word utterances were marked sent without ever being sent.
    mutating func takePending() -> String? {
        guard !pendingWords.isEmpty else { return nil }
        let line = Token.join(pendingWords)
        if recordDescribes {
            record.append(contentsOf: pendingWords)
        } else {
            // The record describes a window that is over. Appending to it would
            // leave a dead sentence in front of every future alignment, and the
            // alignment starts at the origin, so that sentence would push the
            // origin somewhere it does not belong and the boundary would never
            // be found again. The line we are sending IS the new lineage.
            record = pendingWords
            dropped = 0
            recordDescribes = true
        }
        if record.count > Self.maxRecord {
            let over = record.count - Self.maxRecord
            record.removeFirst(over)
            dropped += over
        }
        // pendingWords was exactly hypothesis[boundary...].
        boundary = hypothesis.count
        pendingWords.removeAll()
        return line.isEmpty ? nil : line
    }

    /// Rewrite the sent record in the recognizer's CURRENT words.
    ///
    /// Only ever called with an alignment the boundary search accepted, and it
    /// changes no decision — the same words are still marked sent. What it
    /// changes is the SPELLING and the SPACING they are remembered in, and that
    /// matters for one reason: without it, every word the recognizer pushed
    /// into already-sent text stayed a permanent one-word disagreement between
    /// the record and the screen. Two or three of them and the next alignment
    /// could no longer afford to reach the end of the record, the boundary fell
    /// to zero, and a sentence already on the feed was sent again. That is the
    /// duplication cases 12 and 15 caught: 37 of 400 and 61 of 600 schedules.
    ///
    /// The record's tail beyond the alignment is treated by what the text did
    /// after the last match: if the text carried on with other words, the tail
    /// was REVISED AWAY and goes; if the text simply ran out, the tail has not
    /// been shown again yet and stays, so a collapse does not amnesia away the
    /// sentence it collapsed from.
    private mutating func resyncRecord(with next: [Token], _ placed: Placement) {
        guard placed.viaAlignment, placed.accepted else { return }
        var rebuilt = Array(next[dropped..<placed.boundary])
        if placed.ranOut, placed.explained < record.count {
            rebuilt.append(contentsOf: record[placed.explained...])
        }
        record = rebuilt
    }

    /// A brand-new recognition request: nothing carries over.
    mutating func reset() {
        record.removeAll()
        hypothesis.removeAll()
        hypothesisText = ""
        pendingWords.removeAll()
        boundary = 0
        dropped = 0
        recordDescribes = true
    }

    // MARK: - is anything at risk?

    /// Are the words we heard and have not sent still in this text?
    ///
    /// This is the ONLY question banking needs answered, and it is asked about
    /// the words at risk rather than about the hypothesis as a whole. Totals
    /// cannot answer it: a retraction and a replacement both end up short.
    ///
    /// The bar is half — at least half the unsent words still present, matched
    /// in order with the usual spelling tolerance. Half and not more, because
    /// the case that needs a strict majority ("to review" collapsing to "to",
    /// where reading one word of two as survival used to overwrite "review")
    /// is already caught by the collapse test in `observe`, which fires on that
    /// exact shape. Demanding a strict majority as well took a two-word tail
    /// with ONE word substituted — "on and" becoming "sorry and", which the
    /// recognizer does constantly — and banked a word it had just taken back,
    /// putting a retracted word on the feed and burying its replacement.
    private func pendingSurvives(_ pending: [Token], in next: [Token]) -> Bool {
        let a = Array(pending.suffix(Self.survivalWindow))
        guard !a.isEmpty else { return true }
        // The unsent words sit at the end of the text, so that is where to look
        // for them, with room for everything one callback can add in front.
        let take = min(next.count, a.count + Self.survivalWindow)
        let b = Array(next.suffix(take))
        guard !b.isEmpty else { return false }

        let m = a.count, n = b.count
        var prev = [Int](repeating: 0, count: n + 1)
        var cur = [Int](repeating: 0, count: n + 1)
        for i in 1...m {
            cur[0] = 0
            for j in 1...n {
                cur[j] = (a[i - 1].key == b[j - 1].key || Token.similar(a[i - 1], b[j - 1]))
                    ? prev[j - 1] + 1
                    : max(prev[j], cur[j - 1])
            }
            swap(&prev, &cur)
        }
        return prev[n] * 2 >= m
    }

    // MARK: - where does the sent text end?

    /// Where, inside `next`, does the text we have already sent end?
    ///
    /// `accepted` is false when the record does not describe this text at all,
    /// which the caller reads as a window reset: the boundary is then zero, so
    /// every word of `next` is treated as unsent and nothing can be swallowed.
    ///
    /// The alignment starts at the ORIGIN of both sequences. That single
    /// constraint is what the old fuzzy search lacked and what every deletion
    /// bug came through: a match is usable only if the words in front of it
    /// line up too, so a lone "the" in the middle of a fresh sentence can no
    /// longer declare everything before it already sent.
    ///
    /// Of the matches the alignment finds, the one used is the one that
    /// explains the MOST of the record — the recognizer revises its recent
    /// words, so the last sent word still visible is where the boundary
    /// belongs — with ties broken toward the cheaper and then the earlier
    /// alignment, because absorbing less is the safer error.
    ///
    /// The run is then accepted only if it is credible:
    ///
    ///   * it explains MORE THAN HALF the record — the recognizer coming back
    ///     with our own sentence revised, or
    ///   * it explains ALL of `next` — the recognizer collapsed to an opening
    ///     it has shown us before, and nothing is emitted while that is on
    ///     screen, so believing it costs nothing and is undone by the next word
    ///     that does not fit.
    ///
    /// Four words of an eight-word line reappearing at the head of a different
    /// sentence is not a majority and is not accepted. That is the case that
    /// used to delete them.
    private func placeBoundary(in next: [Token]) -> Placement {
        guard !record.isEmpty else { return Placement(boundary: 0, accepted: true) }
        let m = record.count
        // Words that fell off the front of the record are still assumed to
        // occupy the head of the text; the alignment's origin moves with them.
        let origin = dropped
        guard origin <= next.count else { return Placement(boundary: 0, accepted: false) }
        let n = next.count - origin
        guard n > 0 else { return Placement(boundary: 0, accepted: false) }

        // How much of the record is still, word for word, the head of this
        // text. Almost always all of it — the recognizer appended and changed
        // nothing — and then there is nothing to align at all.
        var head = 0
        while head < m, head < n, record[head].key == next[origin + head].key { head += 1 }
        if head == m { return Placement(boundary: origin + m, accepted: true) }
        if head == n { return Placement(boundary: origin + n, accepted: true) }

        // Otherwise something was edited in place, and only what comes AFTER
        // the agreeing head can move. Aligning the head again would cost the
        // whole length of the request on a callback that changed one word near
        // the end, which is the shape of nearly every edit the recognizer
        // makes. Matching it one-for-one is free and cannot be beaten, so it is
        // taken as given and the alignment starts where the two texts part.
        let rows = m - head, cols = n - head

        // Otherwise something was edited in place. Align, banded, from the
        // origin of both. `rows` is two rolling rows of the edit-distance
        // table; only the band around the diagonal is ever filled.
        let far = Int.max / 4
        let w = Self.band
        let lastRow = min(rows, cols + w)
        // Two rolling rows of edit distance, and beside each the number of
        // words that actually MATCHED on the cheapest path to that cell. The
        // match count is not a decoration: cost alone cannot tell an alignment
        // that agreed twice and paid once from one that agreed once and paid
        // once, and that difference is the difference between a boundary and a
        // deleted sentence.
        var prev = [Int](repeating: far, count: cols + 1)
        var cur = [Int](repeating: far, count: cols + 1)
        var prevHits = [Int](repeating: 0, count: cols + 1)
        var curHits = [Int](repeating: 0, count: cols + 1)
        for j in 0...min(cols, w) { prev[j] = j }

        // The best match found so far: `bestI` sent words explained, ending on
        // `next[origin + bestJ]`, having cost `bestCost` and `bestHits`
        // agreements to get there.
        var bestI = -1, bestJ = -1, bestCost = 0, bestHits = 0

        var i = 1
        while i <= lastRow {
            let lo = max(0, i - w), hi = min(cols, i + w)
            for j in max(0, lo - 1)...hi { cur[j] = far; curHits[j] = 0 }
            // Column zero stays unreachable: an alignment may NOT open by
            // throwing away sent words. Words inserted in front of our text are
            // ordinary ("let's" arriving before "meet at Cineplex"); sent words
            // vanishing off the front is not, and allowing it is how a record
            // reading "it so remind" put its "so" over a fresh window's "so"
            // and deleted the window. The head of the record has to be the head
            // of the text, or this is not our text.
            if lo <= hi {
                for j in max(1, lo)...hi {
                    let a = record[head + i - 1], b = next[origin + head + j - 1]
                    let same = a.key == b.key || Token.similar(a, b)
                    let diagBase = prev[j - 1]
                    let diag = diagBase >= far ? far : diagBase + (same ? 0 : 1)
                    let up = prev[j] >= far ? far : prev[j] + 1
                    let left = cur[j - 1] >= far ? far : cur[j - 1] + 1
                    let best = min(diag, min(up, left))
                    cur[j] = best
                    // Ties go to the path that agreed more often.
                    var hits = 0
                    if diag == best { hits = max(hits, prevHits[j - 1] + (same ? 1 : 0)) }
                    if up == best { hits = max(hits, prevHits[j]) }
                    if left == best { hits = max(hits, curHits[j - 1]) }
                    curHits[j] = hits

                    guard same, diagBase < far else { continue }
                    // A real revision swaps words roughly one for one, so the
                    // words stepped over on the way here have to stay in
                    // proportion to the ground covered. An alignment that pays
                    // more than that is a coincidence wearing a match. The
                    // floor of two is what a callback that both inserts a word
                    // and respells another costs, which happens.
                    guard diagBase <= max(2, (i + j) / 6) else { continue }
                    // Pick the alignment that AGREED MOST, net of what it paid
                    // to get there: matches minus edits. Reaching further into
                    // the record is only worth it if the extra ground was
                    // actually matched.
                    //
                    // Reaching further used to win outright, and it cost real
                    // speech: a record ending "... trailer" against a text
                    // reading "... screening popcorn trailer" paid two edits to
                    // land on the SECOND "trailer" and took "screening popcorn"
                    // down with it. Net score prefers the honest stop one word
                    // earlier. Ties still go to the longer reach, which is what
                    // keeps a word inserted into sent text ("meet at the
                    // Cineplex") from pushing "Cineplex" out a second time.
                    let reached = prevHits[j - 1] + 1
                    let score = reached - diagBase
                    let bestScore = bestHits - bestCost
                    if bestI < 0 || score > bestScore
                        || (score == bestScore && (i - 1 > bestI
                            || (i - 1 == bestI && j - 1 > bestJ))) {
                        bestI = i - 1
                        bestJ = j - 1
                        bestCost = diagBase
                        bestHits = reached
                    }
                }
            }
            swap(&prev, &cur)
            swap(&prevHits, &curHits)
            i += 1
        }

        // Nothing after the agreeing head lines up. If there was a head, that
        // head IS the alignment — the recognizer revised everything past the
        // point the two texts part, which is exactly the shape of case 3, "I
        // will go there now" becoming "I will go to the store tomorrow". If
        // there was no head either, this text is not ours.
        // The head is itself an alignment, and a good one: it agreed `head`
        // times and paid nothing. A run that carries on past it is only worth
        // taking if carrying on gained more than it cost. Skipping this
        // comparison — which is what happens if the head is treated as free
        // ground rather than as a candidate — let a run pay two insertions to
        // reach a second "trailer" and take two unsent words with it.
        if bestI >= 0, bestHits - bestCost < 0, head > 0 {
            bestI = -1; bestJ = -1; bestCost = 0; bestHits = 0
        }
        if bestI < 0 {
            guard head > 0 else { return Placement(boundary: 0, accepted: false) }
            bestI = -1; bestJ = -1; bestCost = 0; bestHits = 0
        }
        // Back into whole-record terms: the agreeing head counts as explained,
        // as cut, and as matched, because that is exactly what it is.
        bestHits += head
        let explained = head + bestI + 1   // sent words this run accounts for
        let cut = head + bestJ + 1         // words of `next`, past the origin
        // MOST OF WHAT IT CLAIMS TO EXPLAIN MUST ACTUALLY HAVE AGREED. A run
        // reaching a late match over substituted words explains nothing: a sent
        // line "eight it" and a fresh window "at we it" share exactly the "it",
        // and reading that as a boundary deleted all three words of the window.
        guard bestHits * 2 > explained else { return Placement(boundary: 0, accepted: false) }
        // And it must not have paid more than twice over for what it found. A
        // one-word record reading "yesterday" against a fresh window's
        // "meeting we yesterday" matches on the last word and buys it with two
        // insertions; believing that buried the window's first two words.
        guard bestHits * 2 > bestCost else { return Placement(boundary: 0, accepted: false) }
        // And if the record was NOT describing the last thing we were shown, it
        // takes more than one word to bring it back. This is the only place the
        // cursor's own previous conclusion is evidence, and it is the only
        // thing that separates two byte-identical shapes:
        //
        //   sent "are", then "really are are the"  — the recognizer pushed a
        //       filler in front of a word we sent. Absorb, or that word is
        //       emitted twice. The record described the previous callback.
        //   sent "at",  then "me at"               — a fresh window that
        //       happens to end on a word we sent. Absorb, and the whole window
        //       is deleted. The record had ALREADY failed on the callback
        //       before this one.
        //
        // Nothing inside either callback tells them apart. What tells them
        // apart is that in the second the cursor had already concluded, one
        // callback earlier, that this record does not describe this text — and
        // one coincidental word is not enough to overturn that.
        if !recordDescribes, !(bestHits >= 2 && bestCost == 0) {
            return Placement(boundary: 0, accepted: false)
        }
        // The text ran out inside our own sentence: a collapse. Nothing is
        // emitted while a collapse is on screen, so believing it costs nothing
        // and the next word that does not fit undoes it — but only if it IS
        // our sentence, word for word. A collapse re-shows what it collapsed
        // from; it does not edit on the way down. Allowing one edit here read
        // a fresh window's "Nicholson I so" as a collapse onto a sent "I so"
        // and swallowed all three words. Zero, or the majority rule has to
        // carry it on its own.
        let ranOut = cut == n && bestCost == 0
        // The majority rule counts AGREEMENTS, not distance travelled. Counting
        // the record index instead let an alignment that matched "that" and
        // "to" three words apart claim the three sent words between them and
        // absorb a whole new window's opening. What has to be more than half
        // the record is the part of it this text actually said again.
        //
        // And the run has to be one of the two kinds that can be checked: it
        // either reached the END of the record — so we know which sent words
        // came back and which were revised away — or it is CLEAN, an unbroken
        // agreement with nothing edited on the way. A run that is neither is
        // guessing about the record's tail on the strength of a gap it filled
        // in: "me so filling" against a fresh window's "me Eric so" matches the
        // "me" and the "so", steps over "Eric", never reaches "filling", and
        // takes all three of the new window's words with it.
        //
        // The run may also not SHRINK onto the text. Words appearing inside
        // text we sent are ordinary and get absorbed; sent words vanishing
        // without anything taking their place is the shape a seam wears —
        // "we to at" followed by a fresh window's "we at" is our own line with
        // one word missing, and reading it that way ate the window. Requiring
        // at least as many text words as sent words keeps substitutions (a
        // word swapped for a word) and refuses pure disappearances.
        let checkable = (explained == m || bestCost == 0) && explained <= cut
        if ranOut || (checkable && bestHits * 2 > m) {
            return Placement(boundary: origin + cut, accepted: true,
                             explained: explained, viaAlignment: true, ranOut: ranOut)
        }
        return Placement(boundary: 0, accepted: false)
    }

    /// What one boundary search concluded. `explained`, `viaAlignment` and
    /// `ranOut` exist only so the record can be rewritten in the recognizer's
    /// current words afterwards; nothing downstream reads them.
    private struct Placement {
        var boundary: Int
        var accepted: Bool
        var explained = 0
        var viaAlignment = false
        var ranOut = false
    }

    // MARK: - words

    /// A word as the recognizer wrote it, plus the form we compare on.
    struct Token: Equatable {
        let raw: String
        let key: String
        /// The key's characters, folded once at construction. The alignments
        /// below compare thousands of word pairs per callback and this runs on
        /// the main thread; rebuilding this array per comparison cost more
        /// than every other part of the type put together.
        let chars: [Character]

        init(_ raw: String) {
            self.raw = raw
            var folded = raw.folding(options: [.diacriticInsensitive, .caseInsensitive],
                                     locale: Locale(identifier: "en_US"))
            folded.removeAll { $0.isPunctuation || $0.isSymbol }
            // A token that is nothing but punctuation still has to compare as
            // itself rather than collapsing into every other such token.
            self.key = folded.isEmpty ? raw.lowercased() : folded
            self.chars = Array(self.key)
        }

        static func tokenize(_ text: String) -> [Token] {
            text.split(whereSeparator: { $0 == " " || $0 == "\n" || $0 == "\t" || $0 == "\r" })
                .map { Token(String($0)) }
        }

        static func join(_ tokens: [Token]) -> String {
            tokens.map(\.raw).joined(separator: " ")
                .trimmingCharacters(in: .whitespacesAndNewlines)
        }

        /// Same words in the same order, ignoring case and punctuation.
        static func sameWords(_ a: [Token], _ b: [Token]) -> Bool {
            a.count == b.count && zip(a, b).allSatisfy { $0.key == $1.key }
        }

        /// Close enough to be the same word respelled. BOTH words must be four
        /// letters or more. At three letters almost everything is one edit from
        /// everything else — "now"/"not", "and"/"end", "the"/"she" — and
        /// treating a genuinely different word as a respelling is a deletion.
        /// Measuring the LONGER word instead of the shorter one is not enough
        /// and cost real speech: "land" and "and" differ by one letter, so a
        /// window opening on "land" was read as the "and" we had already sent
        /// and the word never came out. Four-and-four is also exactly where the
        /// fuzzer's own, independently written, tolerance sits, so the type is
        /// never more forgiving than the thing scoring it.
        /// The budget is ONE edit, not a fraction of the word's length. A
        /// quarter of an eight-letter word is two edits, and two edits is the
        /// distance from "Thursday" to "Tuesday" — a different day, absorbed as
        /// a respelling, and a window that opened on it deleted. One edit is
        /// what an inflection costs ("invoice" -> "invoices") and it is exactly
        /// the tolerance the fuzzer's independently written scorer uses, so the
        /// type can never be more forgiving than the thing measuring it.
        static func similar(_ a: Token, _ b: Token) -> Bool {
            let x = a.chars, y = b.chars
            guard min(x.count, y.count) >= 4 else { return x == y }
            guard abs(x.count - y.count) <= 1 else { return false }
            return characterDistance(x, y, budget: 1) <= 1
        }

        /// Levenshtein distance, abandoned as soon as it passes `budget`.
        static func characterDistance(_ x: [Character], _ y: [Character], budget: Int) -> Int {
            if x.isEmpty { return y.count }
            if y.isEmpty { return x.count }
            var prev = Array(0...y.count)
            var cur = [Int](repeating: 0, count: y.count + 1)
            for i in 1...x.count {
                cur[0] = i
                var best = cur[0]
                for j in 1...y.count {
                    let sub = prev[j - 1] + (x[i - 1] == y[j - 1] ? 0 : 1)
                    cur[j] = min(sub, prev[j] + 1, cur[j - 1] + 1)
                    best = min(best, cur[j])
                }
                if best > budget { return budget + 1 }
                swap(&prev, &cur)
            }
            return prev[y.count]
        }
    }
}
