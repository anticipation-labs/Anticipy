import Foundation

/// What has already been said out loud, and what is new.
///
/// Apple's recogniser does not APPEND to its transcript — it REWRITES it. The
/// hypothesis "Cineplex" becomes "the Cineplex"; a twelve-second sentence
/// collapses to "Of August" when the window resets; a word near the front is
/// swapped for a better guess. Every one of those shifts the position of every
/// word after it.
///
/// So anything that remembers "I have already sent the first N words" is
/// pointing at the wrong word the moment the recogniser inserts or drops one
/// near the front. The live symptom: one spoken sentence arriving as two or
/// three overlapping fragments, or a sentence vanishing entirely.
///
/// This type remembers the WORDS it sent, not a count, and re-finds them in
/// each new hypothesis. It carries no clock, no timer and nothing from
/// Speech.framework on purpose — it is plain Foundation, so the checks in
/// `Tests/TranscriptCursorTests.swift` compile and run in about a second with
/// no simulator, no scheme, no signing and no microphone.
struct TranscriptCursor {

    /// The words already handed out, normalised for comparison. Not a count.
    private(set) var emitted: [String] = []

    /// Alignment is quadratic, so it is bounded. Real utterances are a handful
    /// of words; this only exists so a pathological transcript cannot stall the
    /// main thread. Beyond it, only the most recent words are used as the
    /// anchor, which is where any revision would be anyway.
    static let alignmentWindow = 300

    // ------------------------------------------------------------- reading

    /// The words in `transcript` that have not been handed out yet, in order,
    /// with their original spelling, casing and punctuation. Does not consume.
    func peek(_ transcript: String) -> String {
        let words = TranscriptCursor.split(transcript)
        let cut = TranscriptCursor.cut(emitted: emitted,
                                       current: words.map(TranscriptCursor.normalise))
        guard cut < words.count else { return "" }
        return words[cut...].joined(separator: " ")
    }

    /// How many words of `transcript` are new. Does not consume.
    func newWordCount(_ transcript: String) -> Int {
        let words = TranscriptCursor.split(transcript)
        let cut = TranscriptCursor.cut(emitted: emitted,
                                       current: words.map(TranscriptCursor.normalise))
        return max(0, words.count - cut)
    }

    // ------------------------------------------------------------- writing

    /// Take the new words and mark the whole transcript as said.
    ///
    /// `minNewWords` guards the final-result path: when the recogniser
    /// finalises an utterance it usually only polishes the wording, adding a
    /// word or none, and re-sending on that produced duplicates live. Below the
    /// threshold nothing is returned — but the transcript is still marked as
    /// said, because the recogniser is about to throw it away and asking for it
    /// again would hand back the same polish forever.
    mutating func take(_ transcript: String, minNewWords: Int = 1) -> String {
        let words = TranscriptCursor.split(transcript)
        let normal = words.map(TranscriptCursor.normalise)
        let cut = TranscriptCursor.cut(emitted: emitted, current: normal)

        // Whatever happens below, this hypothesis has now been seen.
        remember(normal, from: cut)

        guard cut < words.count else { return "" }
        let fresh = Array(words[cut...])
        guard fresh.count >= minNewWords else { return "" }
        return fresh.joined(separator: " ")
    }

    /// A new recognition task starts a transcript from nothing. Forgetting is
    /// the correct thing to do — the next hypothesis shares no words with the
    /// last one by position, only by luck.
    mutating func reset() {
        emitted = []
    }

    private mutating func remember(_ normal: [String], from cut: Int) {
        guard cut < normal.count else { return }
        var next = emitted + normal[cut...]
        // The anchor only ever needs the recent tail — the front of a long day
        // cannot be revised any more, and keeping all of it would grow without
        // bound in a process that runs for hours.
        if next.count > TranscriptCursor.alignmentWindow {
            next = Array(next.suffix(TranscriptCursor.alignmentWindow))
        }
        emitted = next
    }

    // ----------------------------------------------------------- the words

    static func split(_ text: String) -> [String] {
        text.split(whereSeparator: { $0 == " " || $0 == "\n" || $0 == "\t" })
            .map(String.init)
    }

    /// Two words are the same word when they differ only in casing or the
    /// punctuation hanging off them — the recogniser adds and removes both as
    /// it refines, and treating "table," as new speech is exactly the bug.
    static func normalise(_ word: String) -> String {
        let trimmed = word.trimmingCharacters(
            in: CharacterSet.alphanumerics.inverted)
        return (trimmed.isEmpty ? word : trimmed).lowercased()
    }

    // ------------------------------------------------------------ alignment

    /// How many leading words of `current` have already been handed out.
    ///
    /// Not an index carried over from last time — it is re-derived from the
    /// text every single call, which is the whole point.
    static func cut(emitted rawE: [String], current C: [String]) -> Int {
        if rawE.isEmpty || C.isEmpty { return 0 }
        let E = rawE.count > alignmentWindow
            ? Array(rawE.suffix(alignmentWindow)) : rawE

        // The overwhelmingly common case: the new hypothesis extends the old
        // one, word for word. Answer it without building a table.
        var p = 0
        while p < E.count && p < C.count && E[p] == C[p] { p += 1 }
        if p == E.count { return p }

        // The head was revised. Find the said words again wherever they went,
        // in order, preferring the EARLIEST place each one fits — so a word
        // that happens to repeat later in the sentence cannot drag the cut past
        // speech that was never sent.
        let n = E.count, m = C.count
        // lcs[i][j] = length of the longest common subsequence of E[i...] and
        // C[j...]. Suffix form, so the walk below can go forwards.
        var lcs = [[Int]](repeating: [Int](repeating: 0, count: m + 1), count: n + 1)
        if n > 0 && m > 0 {
            for i in stride(from: n - 1, through: 0, by: -1) {
                for j in stride(from: m - 1, through: 0, by: -1) {
                    lcs[i][j] = E[i] == C[j]
                        ? lcs[i + 1][j + 1] + 1
                        : max(lcs[i + 1][j], lcs[i][j + 1])
                }
            }
        }

        var i = 0, j = 0, cut = 0
        while i < n && j < m {
            if E[i] == C[j] {
                cut = j + 1
                i += 1
                j += 1
            } else if lcs[i + 1][j] > lcs[i][j + 1] {
                i += 1          // a said word the recogniser has since dropped
            } else {
                // A word the recogniser has since inserted — and, on a tie,
                // the deliberate choice. Both moves reconstruct a longest
                // match; this one carries the cut FURTHER, so when the
                // recogniser merely reshuffles words that were already said,
                // nothing is said a second time. Saying it twice is the bug
                // this whole type exists to kill, so ties break that way.
                j += 1
            }
        }
        return cut
    }
}
