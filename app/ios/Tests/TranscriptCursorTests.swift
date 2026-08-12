import Foundation

// Checks for TranscriptCursor — the layer that decides which words the phone
// has already said out loud.
//
// The bug these exist to kill, seen live: one spoken sentence arriving as two
// or three overlapping fragments. The cause was an integer word cursor into a
// transcript that Apple REWRITES rather than appends to, so the moment a word
// was inserted or dropped near the front, the cursor pointed at the wrong word.
//
// Every case below is written so the old integer cursor FAILS it. That is the
// only reason to trust them.

var checks = 0
var failures: [String] = []

func check(_ name: String, _ ok: Bool) {
    checks += 1
    if ok {
        print("  ok    \(name)")
    } else {
        print("  FAIL  \(name)")
        failures.append(name)
    }
}

/// What the old integer-word-count cursor would have handed out, so the tests
/// can assert that the new answer differs where it must. Kept deliberately
/// faithful to the shipped code: `words[emittedWords...]`, then
/// `emittedWords = words.count`.
struct IntegerCursor {
    var emittedWords = 0
    mutating func take(_ transcript: String) -> String {
        let words = TranscriptCursor.split(transcript)
        guard words.count > emittedWords else {
            emittedWords = max(emittedWords, words.count)
            return ""
        }
        let fresh = Array(words[emittedWords...])
        emittedWords = words.count
        return fresh.joined(separator: " ")
    }
}

enum Cases {

    // ---------------------------------------------------------------- basics

    /// The ordinary case, and the one the old cursor got right: the recogniser
    /// simply adds words on the end.
    static func plainAppend() {
        var c = TranscriptCursor()
        check("first hypothesis is all new", c.take("book") == "book")
        check("appended words only", c.take("book a table") == "a table")
        check("and again", c.take("book a table at seven") == "at seven")
        check("no change means nothing to say", c.take("book a table at seven") == "")
    }

    /// THE LIVE BUG. Apple refines "Cineplex" into "the Cineplex" — a word
    /// inserted BEFORE one already sent. Every later word shifts by one.
    static func insertionBeforeSaidWords() {
        var c = TranscriptCursor()
        _ = c.take("Cineplex")
        check("an inserted article does not resend the word after it",
              c.take("the Cineplex") == "")

        var old = IntegerCursor()
        _ = old.take("Cineplex")
        check("...and the integer cursor really did resend it",
              old.take("the Cineplex") == "Cineplex")
    }

    /// The same insertion, mid-sentence, with real speech after it.
    static func insertionKeepsLaterSpeech() {
        var c = TranscriptCursor()
        check("said so far", c.take("meet me at Cineplex") == "meet me at Cineplex")
        check("only the genuinely new tail comes back",
              c.take("meet me at the Cineplex at eight") == "at eight")

        var old = IntegerCursor()
        _ = old.take("meet me at Cineplex")
        check("...where the integer cursor duplicated a word",
              old.take("meet me at the Cineplex at eight") == "Cineplex at eight")
    }

    /// THE OTHER LIVE BUG. A twelve-second sentence collapses to "Of August"
    /// when the recogniser's window resets. The shipped code noticed this with
    /// a character-count heuristic (`partial.count > text.count + 10`), banked
    /// the tail, zeroed the cursor — and then said the short text AGAIN.
    static func windowCollapse() {
        var c = TranscriptCursor()
        _ = c.take("I need to get the numbers in before the end of August")
        check("a collapsed window repeats nothing",
              c.take("of August") == "")
        check("and real speech after it still gets through",
              c.take("of August and September") == "and September")
    }

    /// A collapse to something genuinely unrelated IS new speech.
    static func collapseToNewSpeech() {
        var c = TranscriptCursor()
        _ = c.take("book a table for tomorrow night")
        check("an unrelated hypothesis is all new",
              c.take("what time is it") == "what time is it")
    }

    // ------------------------------------------------------------ same words

    /// Casing and punctuation move constantly as the recogniser tidies up.
    /// None of it is speech.
    static func polishIsNotSpeech() {
        var c = TranscriptCursor()
        _ = c.take("book a table")
        check("capitalisation is not new speech", c.take("Book a table") == "")
        check("punctuation is not new speech", c.take("Book a table.") == "")
        check("both at once", c.take("Book a Table!") == "")
        check("a real word after the polish still lands",
              c.take("Book a Table, please") == "please")
    }

    /// Repeated words are how he actually talks on a call.
    static func repeatedWords() {
        var c = TranscriptCursor()
        check("three of them", c.take("yeah yeah yeah") == "yeah yeah yeah")
        check("a fourth is one word, not four", c.take("yeah yeah yeah yeah") == "yeah")
        check("still just one more", c.take("yeah yeah yeah yeah yeah") == "yeah")
    }

    /// A word that repeats later in the sentence must not drag the cut past
    /// speech that was never sent. This is the trap in aligning by matching:
    /// the naive answer finds the LAST "a" and silently drops everything
    /// before it.
    static func aRepeatedWordCannotSwallowSpeech() {
        var c = TranscriptCursor()
        _ = c.take("a")
        let out = c.take("book a table for a party")
        check("the later duplicate did not eat the sentence",
              out.contains("table") && out.contains("party"))
    }

    /// When the recogniser reshuffles words it already gave us, both readings
    /// of the transcript are equally good matches and the alignment has to pick
    /// one. It picks the one that says LESS, because saying a sentence twice is
    /// the bug this type exists to kill.
    ///
    /// Written because a mutation that flipped this tie survived all the other
    /// checks — the choice was being made by accident.
    static func reorderedWordsAreNotNewSpeech() {
        var c = TranscriptCursor()
        _ = c.take("Toby email")
        check("the same two words in the other order are not new speech",
              c.take("email Toby") == "")
        check("but a genuinely new word after them still lands",
              c.take("email Toby back") == "back")
    }

    /// THE 2026-08-12 LIVE SHRED. A long conversation, flushed sentence by
    /// sentence; then the window resets and a brand-new sentence arrives. Its
    /// everyday words — "tomorrow", "we", "for" — all appear somewhere in the
    /// emitted history, and those scattered coincidences dragged the cut
    /// across the whole sentence: only "Tomorrow you bet" survived out of
    /// "How's Earls the one in West Van for tomorrow you bet".
    static func aNewSentenceIsNotSwallowedByOldWords() {
        var c = TranscriptCursor()
        _ = c.take("Hey how are you good good yourself good that's great to "
                   + "hear we really should grab some food I know we really "
                   + "have to catch up over dinner and stuff")
        // The recogniser's window resets: the next hypothesis is a fresh
        // sentence sharing only everyday words with the history.
        let out = c.take("How's Earls the one in West Van for tomorrow "
                         + "you bet")
        check("a fresh sentence after a reset comes out whole",
              out.contains("Earls") && out.contains("West Van")
                  && out.contains("tomorrow") && out.contains("you bet"))
    }

    /// The same trap with a profanity-shaped tail: "what the fuck is going
    /// on" arrived live as just "fuck is going on" because "what" and "the"
    /// matched old speech.
    static func stopwordsCannotEatTheFrontOfASentence() {
        var c = TranscriptCursor()
        _ = c.take("I know what you mean the whole thing is a mess and "
                   + "the deal needs work on the numbers side")
        let out = c.take("what the hell is going on")
        check("the sentence keeps its front",
              out.contains("what") && out.contains("going on"))
    }

    // ------------------------------------------------------------- the laws

    /// LAW 1 — nothing is ever said twice.
    ///
    /// Replayed over a real refinement sequence: every word of the final
    /// transcript appears in the output at most as many times as it appears in
    /// the transcript itself.
    static func nothingIsEverSaidTwice() {
        let hypotheses = [
            "so", "so I", "so I need", "so I need to", "so I need to book",
            "so I need to book a", "so I need to book a table",
            "so I need to book a table at", "so I need to book a table at Cactus",
            // the recogniser reconsiders the front
            "So, I need to book a table at Cactus Club",
            "So, I need to book a table at the Cactus Club",
            "So, I need to book a table at the Cactus Club for two",
            "So, I need to book a table at the Cactus Club for two tomorrow",
        ]
        var c = TranscriptCursor()
        var said: [String] = []
        for h in hypotheses {
            let out = c.take(h)
            if !out.isEmpty { said.append(contentsOf: TranscriptCursor.split(out)) }
        }
        let saidCounts = counted(said.map(TranscriptCursor.normalise))
        let finalCounts = counted(
            TranscriptCursor.split(hypotheses.last!).map(TranscriptCursor.normalise))
        var overspoken: [String] = []
        for (w, n) in saidCounts where n > (finalCounts[w] ?? 0) { overspoken.append(w) }
        check("no word is said more often than it was spoken",
              overspoken.isEmpty)

        var old = IntegerCursor()
        var oldSaid: [String] = []
        for h in hypotheses {
            let out = old.take(h)
            if !out.isEmpty { oldSaid.append(contentsOf: TranscriptCursor.split(out)) }
        }
        let oldCounts = counted(oldSaid.map(TranscriptCursor.normalise))
        var oldOver: [String] = []
        for (w, n) in oldCounts where n > (finalCounts[w] ?? 0) { oldOver.append(w) }
        check("...and the integer cursor overspoke on this very sequence",
              !oldOver.isEmpty)
    }

    /// LAW 2 — on a pure append, nothing is ever lost. Everything spoken comes
    /// out, once, in order.
    static func nothingIsLostOnAppend() {
        let words = ("hey can you book a table for two at the cactus club in "
                     + "park royal tomorrow at seven thirty please").split(separator: " ")
        var c = TranscriptCursor()
        var said: [String] = []
        for i in 1...words.count {
            let out = c.take(words[0..<i].joined(separator: " "))
            if !out.isEmpty { said.append(contentsOf: TranscriptCursor.split(out)) }
        }
        check("every spoken word came out exactly once, in order",
              said == words.map(String.init))
    }

    /// LAW 3 — whatever comes out is always a run of the transcript it came
    /// from, in order. Never reordered, never invented.
    static func outputIsAlwaysInOrder() {
        var c = TranscriptCursor()
        var ok = true
        let hypotheses = ["one", "one two", "one two three", "the one two three",
                          "the one two three four", "one two three four five"]
        for h in hypotheses {
            let out = TranscriptCursor.split(c.take(h)).map(TranscriptCursor.normalise)
            let full = TranscriptCursor.split(h).map(TranscriptCursor.normalise)
            if !out.isEmpty && !isRun(out, of: full) { ok = false }
        }
        check("every line is a contiguous run of its own transcript", ok)
    }

    /// LAW 4 — a fresh recognition task shares nothing with the last one.
    static func resetForgetsEverything() {
        var c = TranscriptCursor()
        _ = c.take("book a table at seven")
        c.reset()
        check("after a task swap the same words are new speech again",
              c.take("book a table at seven") == "book a table at seven")
    }

    // -------------------------------------------------------- the threshold

    /// A final result usually only polishes wording. `minNewWords` is what
    /// stops that polish becoming a second line — but it must still mark the
    /// transcript as said, or the recogniser hands back the same polish forever.
    static func minNewWordsWithholdsButStillConsumes() {
        var c = TranscriptCursor()
        _ = c.take("book a table")
        check("two new words under a threshold of three say nothing",
              c.take("book a table at seven", minNewWords: 3) == "")
        check("and they are not offered again",
              c.take("book a table at seven") == "")
        check("three new words clear it",
              c.take("book a table at seven tomorrow for two", minNewWords: 3)
                == "tomorrow for two")
    }

    static func peekDoesNotConsume() {
        var c = TranscriptCursor()
        _ = c.take("book a table")
        check("peek reports the tail", c.peek("book a table at seven") == "at seven")
        check("peek again, same answer", c.peek("book a table at seven") == "at seven")
        check("counting agrees", c.newWordCount("book a table at seven") == 2)
        check("and taking it still works", c.take("book a table at seven") == "at seven")
    }

    // ------------------------------------------------------------- the wall

    /// Junk must never crash and never invent speech.
    static func junkIsSafe() {
        var c = TranscriptCursor()
        check("empty is nothing", c.take("") == "")
        check("whitespace is nothing", c.take("     ") == "")
        check("newlines are nothing", c.take("\n\n") == "")
        check("still nothing said", c.emitted.isEmpty)
        check("a first real word after junk lands", c.take("hello") == "hello")
        check("empty after speech is nothing", c.take("") == "")
        check("and the speech is not re-offered", c.take("hello") == "")
        var d = TranscriptCursor()
        check("punctuation-only tokens do not crash", d.take("... --- ,,,").isEmpty == false)
    }

    /// The alignment is bounded, so a transcript that never ends cannot stall
    /// the main thread or grow memory without limit.
    static func alignmentIsBounded() {
        var c = TranscriptCursor()
        var text = ""
        for i in 0..<(TranscriptCursor.alignmentWindow + 250) {
            text += (text.isEmpty ? "" : " ") + "w\(i)"
            _ = c.take(text)
        }
        check("the anchor stays inside its window",
              c.emitted.count <= TranscriptCursor.alignmentWindow)
        check("and it is still working at the tail",
              c.take(text + " done") == "done")
    }

    // ------------------------------------------------------------- fuzzing

    /// A thousand replays of a sentence being refined the way the recogniser
    /// really refines one — words appended, articles inserted near the front,
    /// the window collapsing — asserting the two laws every time.
    static func randomisedRefinement() {
        var seed: UInt64 = 0x5EED
        func rnd(_ n: Int) -> Int {
            seed = seed &* 6364136223846793005 &+ 1442695040888963407
            return Int((seed >> 33) % UInt64(max(1, n)))
        }
        let vocab = ["book", "a", "table", "at", "the", "cactus", "club", "for",
                     "two", "tomorrow", "yeah", "seven", "please", "and"]
        var outOfOrder = 0, saidAgain = 0, overBudget = 0
        for _ in 0..<1000 {
            var spoken: [String] = []
            var c = TranscriptCursor()
            // Every word in a transcript got there by exactly one append or one
            // insertion — a collapse only ever removes. So the number of words
            // handed out over the whole replay can never exceed the number of
            // words that were ever added. That is the anti-duplication budget,
            // and the old integer cursor blows straight through it.
            var wordsEverAdded = 0
            var wordsEverSaid = 0
            for _ in 0..<12 {
                switch rnd(10) {
                case 0 where !spoken.isEmpty:            // insert near the front
                    spoken.insert(vocab[rnd(vocab.count)], at: rnd(min(3, spoken.count)))
                    wordsEverAdded += 1
                case 1 where spoken.count > 3:           // the window collapses
                    spoken = Array(spoken.suffix(2))
                default:                                 // one more word heard
                    spoken.append(vocab[rnd(vocab.count)])
                    wordsEverAdded += 1
                }
                let text = spoken.joined(separator: " ")
                let out = TranscriptCursor.split(c.take(text))
                let full = TranscriptCursor.split(text).map(TranscriptCursor.normalise)
                wordsEverSaid += out.count

                // Whatever came out must be a contiguous run of THIS transcript.
                if !out.isEmpty && !isRun(out.map(TranscriptCursor.normalise), of: full) {
                    outOfOrder += 1
                }
                // THE INVARIANT. Once a transcript has been taken, there must be
                // nothing left in it. Anything still pending would be handed out
                // a second time on the next callback — and the recogniser fires
                // that callback several times a second. This is precisely how
                // one sentence became three overlapping fragments.
                if !c.peek(text).isEmpty { saidAgain += 1 }
            }
            if wordsEverSaid > wordsEverAdded { overBudget += 1 }
        }
        check("1000 randomised refinements stayed in order", outOfOrder == 0)
        check("1000 randomised refinements left nothing pending after taking it",
              saidAgain == 0)
        check("1000 randomised refinements never said more words than were spoken",
              overBudget == 0)
    }

    // ------------------------------------------------------------- helpers

    static func counted(_ words: [String]) -> [String: Int] {
        var out: [String: Int] = [:]
        for w in words { out[w, default: 0] += 1 }
        return out
    }

    /// Is `needle` a contiguous run inside `hay`?
    static func isRun(_ needle: [String], of hay: [String]) -> Bool {
        if needle.isEmpty { return true }
        if needle.count > hay.count { return false }
        for start in 0...(hay.count - needle.count) {
            if Array(hay[start..<(start + needle.count)]) == needle { return true }
        }
        return false
    }
}

@main
struct TranscriptCursorTests {
    static func main() {
        print("TranscriptCursor")
        Cases.plainAppend()
        Cases.insertionBeforeSaidWords()
        Cases.insertionKeepsLaterSpeech()
        Cases.windowCollapse()
        Cases.collapseToNewSpeech()
        Cases.polishIsNotSpeech()
        Cases.repeatedWords()
        Cases.aRepeatedWordCannotSwallowSpeech()
        Cases.reorderedWordsAreNotNewSpeech()
        Cases.aNewSentenceIsNotSwallowedByOldWords()
        Cases.stopwordsCannotEatTheFrontOfASentence()
        Cases.nothingIsEverSaidTwice()
        Cases.nothingIsLostOnAppend()
        Cases.outputIsAlwaysInOrder()
        Cases.resetForgetsEverything()
        Cases.minNewWordsWithholdsButStillConsumes()
        Cases.peekDoesNotConsume()
        Cases.junkIsSafe()
        Cases.alignmentIsBounded()
        Cases.randomisedRefinement()

        print("\n\(checks - failures.count)/\(checks) checks passed")
        if !failures.isEmpty {
            print("\(failures.count) FAILED")
            for f in failures { print("   - \(f)") }
            exit(1)
        }
        print("TranscriptCursor: all green")
        exit(0)
    }
}
