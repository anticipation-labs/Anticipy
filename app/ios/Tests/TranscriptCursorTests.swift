import Foundation

// Unit tests for TranscriptCursor — the emission layer behind Omar's garbled
// transcripts. Deliberately NOT an XCTest bundle: the type is pure Foundation,
// so it compiles and runs in about a second with no simulator, no scheme and
// no signing. See app/ios/Tests/run_cursor_tests.sh.
//
// Every scenario below is a real SFSpeechRecognizer behaviour, and each one
// names the way the OLD integer-cursor implementation broke on it.

// ---------------------------------------------------------------- harness

var failures = 0
var checks = 0

func scenario(_ name: String) {
    print("\n\(name)")
}

func check(_ ok: Bool, _ what: String) {
    checks += 1
    if ok {
        print("  ok    \(what)")
    } else {
        failures += 1
        print("  FAIL  \(what)")
    }
}

func equal<T: Equatable>(_ got: T, _ want: T, _ what: String) {
    checks += 1
    if got == want {
        print("  ok    \(what)")
    } else {
        failures += 1
        print("  FAIL  \(what)\n          got:  \(got)\n          want: \(want)")
    }
}

/// Drives the cursor exactly the way PhoneListener's recognition callback
/// does, so a passing test says something about the shipping code path.
final class Listener {
    private var cursor = TranscriptCursor()
    /// Lines that reached `onLine` / `onSpeaker`, in order.
    private(set) var lines: [String] = []
    /// How many times the 2.6s pause timer was (re)armed. The old code armed
    /// on every callback, which cancelled the pause it was meant to detect.
    private(set) var timerArmed = 0
    private(set) var resets = 0

    /// A non-final partial result.
    @discardableResult
    func partial(_ text: String) -> TranscriptCursor.Update {
        let u = cursor.observe(text)
        if let banked = u.banked { lines.append(banked) }
        if u.didReset { resets += 1 }
        if u.changed { timerArmed += 1 }
        return u
    }

    /// The 2.6s of silence elapsed.
    func pause() {
        if let line = cursor.takePending() { lines.append(line) }
    }

    /// `result.isFinal` — flush, then the request is swapped for a fresh one.
    func final(_ text: String) {
        let u = cursor.observe(text)
        if let banked = u.banked { lines.append(banked) }
        if let line = cursor.takePending() { lines.append(line) }
        cursor.reset()
    }

    var pending: String { cursor.pending }
    var joined: String { lines.joined(separator: " ") }
}

func words(_ s: String) -> [String] {
    s.split(separator: " ").map {
        String($0).lowercased().filter { !$0.isPunctuation }
    }
}

/// Is `needle` a subsequence of `hay`? Used to prove nothing was deleted.
func isSubsequence(_ needle: [String], of hay: [String]) -> Bool {
    var i = 0
    for w in hay where i < needle.count && w == needle[i] { i += 1 }
    return i == needle.count
}

/// Deterministic pseudo-randomness — a failing property test must reproduce.
struct Rand {
    private var seed: UInt64
    init(_ s: UInt64) { seed = s }
    mutating func below(_ n: Int) -> Int {
        seed = seed &* 6364136223846793005 &+ 1442695040888963407
        return Int((seed >> 33) % UInt64(n))
    }
}

// ---------------------------------------------------------------- cases

enum Cases {

    // Apple refines a word it already gave us: "Cineplex" -> "the Cineplex".
    // OLD: the word count went 3 -> 4, so the cursor emitted a spurious
    // one-word line "Cineplex" — a word already sent, alone, mid-sentence.
    static func revision() {
        scenario("1. revision — a word inserted into text already sent")
        let l = Listener()
        l.partial("meet at")
        l.partial("meet at Cineplex")
        l.pause()
        l.partial("meet at the Cineplex")          // <- the revision
        l.pause()
        check(!l.lines.contains("Cineplex"), "no spurious one-word re-emission")
        equal(l.lines, ["meet at Cineplex"], "the revision produced no new line")
        l.partial("meet at the Cineplex tomorrow")
        l.pause()
        equal(l.lines, ["meet at Cineplex", "tomorrow"], "genuinely new speech still emitted")
    }

    // Apple decides a word belongs BEFORE everything it has given us so far.
    // OLD: the word count rose, so the last word of the sentence came again.
    static func frontInsertion() {
        scenario("2. front-insertion — a word prepended to text already sent")
        let l = Listener()
        l.partial("meet at Cineplex")
        l.pause()
        equal(l.lines, ["meet at Cineplex"], "first line sent")
        l.partial("let's meet at Cineplex")        // <- prepended
        l.pause()
        equal(l.lines, ["meet at Cineplex"], "front-insertion produced no new line")
        l.partial("let's meet at Cineplex at eight")
        l.pause()
        equal(l.lines, ["meet at Cineplex", "at eight"], "later speech emitted once, in order")
    }

    // Apple retracts words it already gave us. THIS is the pin.
    // OLD: `emittedWords = max(emittedWords, words.count)` refused to come
    // down, so the cursor sat at 5 over a 3-word string and the next real
    // words fell underneath it — "to the" was swallowed and the line arrived
    // as "store tomorrow".
    static func deletion() {
        scenario("3. deletion — the text shrinks, then real speech follows")
        let l = Listener()
        l.partial("I will go there now")
        l.pause()
        equal(l.lines, ["I will go there now"], "first line sent")
        l.partial("I will go")                     // <- retraction
        l.pause()
        equal(l.lines, ["I will go there now"], "a retraction emits nothing")
        l.partial("I will go to the store tomorrow")
        l.pause()
        equal(l.lines.last, "to the store tomorrow",
              "the cursor came DOWN — nothing swallowed (old code: \"store tomorrow\")")
        equal(l.lines.count, 2, "exactly two lines")
    }

    // The decode window resets and the string is REPLACED by something
    // unrelated. OLD: the shrink test compared characters, the cursor stayed
    // tens of words above the new text, ~29 spoken words were permanently
    // deleted, and what followed dribbled out one and two words at a time.
    static func fullReset() {
        scenario("4. full reset — the window is replaced by unrelated text")
        let spoken = "so I told Eric that the Nicholson deal is dead and we should "
            + "call Baylor before the quarter closes because nobody else will pick "
            + "up that account"
        let l = Listener()
        // A long continuous stretch with no 2.6s pause: nothing sent yet.
        var built: [String] = []
        for w in spoken.split(separator: " ") {
            built.append(String(w))
            l.partial(built.joined(separator: " "))
        }
        equal(l.lines.count, 0, "nothing sent yet — no pause has happened")
        equal(l.pending, spoken, "all \(words(spoken).count) words are pending")

        l.partial("Of August")                     // <- the window resets
        equal(l.resets, 1, "reset detected by content")
        equal(l.lines, [spoken], "the whole pending sentence was banked, not deleted")

        l.pause()
        equal(l.lines, [spoken, "Of August"], "the new window's text follows as its own line")
        check(isSubsequence(words(spoken), of: words(l.joined)),
              "every spoken word survived, in order")
    }

    // The recognizer re-emits the same hypothesis while nobody is talking.
    // OLD: `scheduleSilenceFlush()` ran on EVERY callback and re-armed the
    // 2.6s deadline each time, so the timer could never reach its deadline
    // during the pause it existed to detect.
    static func identicalRepeats() {
        scenario("5. identical repeats — the pause timer must not be re-armed")
        let l = Listener()
        l.partial("the invoice goes out")
        equal(l.timerArmed, 1, "armed once on real speech")
        l.partial("the invoice goes out")
        l.partial("the invoice goes out")
        l.partial("the invoice goes out")
        equal(l.timerArmed, 1, "three identical repeats re-armed nothing (old code: 4)")
        equal(l.lines.count, 0, "and emitted nothing")
        l.pause()
        equal(l.lines, ["the invoice goes out"], "the pause still cuts the line")
    }

    static func emptyString() {
        scenario("6. empty string — carries no information, loses nothing")
        let l = Listener()
        l.partial("I will call you back")
        let u = l.partial("")
        equal(u.changed, false, "an empty hypothesis is not a change")
        equal(u.didReset, false, "and is not a reset")
        equal(u.banked, nil, "and banks nothing")
        equal(l.pending, "I will call you back", "the pending tail survived")
        l.partial("I will call you back later")
        l.pause()
        equal(l.lines, ["I will call you back later"], "one line, nothing lost or doubled")
    }

    // The old detector was `partial.count > text.count + 10` — strictly
    // greater, on CHARACTERS. A shrink of exactly 10 slipped through it in
    // both directions: it never fired, whether or not the text was a new
    // window.
    static func shrinkByExactlyTenThatIsARevision() {
        scenario("7a. shrink of exactly 10 characters that is a genuine revision")
        let long = "we should ship the update on friday"     // 35 characters
        let short = "we should ship the update"               // 25 characters
        equal(long.count, short.count + 10, "the shrink is exactly 10 characters")
        let l = Listener()
        l.partial(long)
        l.pause()
        let u = l.partial(short)
        equal(u.didReset, false, "a truncation of our own text is NOT a reset")
        equal(l.lines, [long], "and emits nothing extra")
        l.partial("we should ship the update on friday and tell the team")
        l.pause()
        equal(l.lines, [long, "and tell the team"], "the continuation is emitted once")
    }

    static func shrinkByExactlyTenThatIsAReset() {
        scenario("7b. shrink of exactly 10 characters that IS a new window")
        let before = "the invoice goes out on friday"          // 30 characters
        let after = "lets grab lunch soon"                     // 20 characters
        equal(before.count, after.count + 10, "the shrink is exactly 10 characters")
        let l = Listener()
        l.partial(before)
        let u = l.partial(after)
        check(before.count <= after.count + 10,
              "the old character test could not fire here (it needed > +10)")
        equal(u.didReset, true, "content-based detection catches it anyway")
        equal(l.lines, [before], "the replaced sentence was banked, not deleted")
        l.pause()
        equal(l.lines, [before, after], "both sentences survive, in order")
    }

    static func punctuationOnly() {
        scenario("8. punctuation- and case-only changes")
        let l = Listener()
        l.partial("I'll send the invoice tomorrow")
        equal(l.timerArmed, 1, "armed once on real speech")
        let p = l.partial("I'll send the invoice tomorrow.")
        equal(p.changed, false, "adding a full stop is not a change")
        let c = l.partial("I'll send the Invoice tomorrow.")
        equal(c.changed, false, "re-capitalising a word is not a change")
        equal(l.timerArmed, 1, "so the pause timer was never re-armed")
        equal(l.lines.count, 0, "and no line was cut")
        l.pause()
        equal(l.lines, ["I'll send the Invoice tomorrow."],
              "the line carries the recognizer's latest spelling")
    }

    // A long stretch, a window reset, then a short one. This is the shape that
    // produced "Pill 491 kill 492" / "I kill 44 sorry": under the old cursor
    // everything before the reset vanished and everything after arrived in
    // 1-, 2- and 3-word slices.
    static func reportedSignature() {
        scenario("9. the reported signature — long stretch, reset, short bursts")
        let first = "call the clinic back about the referral and move the Thursday "
            + "review to next week because Priya is out"
        let second = "remind me to pay the parking ticket"
        let l = Listener()
        var built: [String] = []
        for w in first.split(separator: " ") {
            built.append(String(w))
            l.partial(built.joined(separator: " "))
        }
        built = []
        for w in second.split(separator: " ") {
            built.append(String(w))
            l.partial(built.joined(separator: " "))
        }
        l.final(second)

        check(isSubsequence(words(first), of: words(l.joined)),
              "nothing from before the reset was deleted")
        check(isSubsequence(words(second), of: words(l.joined)),
              "nothing from after the reset was deleted")
        equal(words(l.joined).count, words(first).count + words(second).count,
              "and nothing was emitted twice")
        check(l.lines.allSatisfy { $0.split(separator: " ").count >= 4 },
              "no line is a mid-sentence 1-, 2- or 3-word slice")
        equal(l.lines.count, 2, "two lines, one per window")
    }

    static func everyWordExactlyOnce() {
        scenario("10. invariant — every spoken word emitted exactly once, in order")
        let spoken = "book the flight to Denver on Tuesday and tell Priya we land at noon"
        let l = Listener()
        l.partial("book the")
        l.partial("book the flight")
        l.partial("book the flight to Denver")
        l.pause()                                   // a real pause mid-sentence
        l.partial("book the flight to Denver on")
        l.partial("book the flight to Denver on Tuesday")
        l.partial("book the flight to Denver on Tuesday and tell Priya")
        l.partial("book the flight to Denver on Tuesday and tell Priya we")
        l.partial(spoken)
        l.final(spoken)
        equal(l.lines,
              ["book the flight to Denver", "on Tuesday and tell Priya we land at noon"],
              "cut at the pause, nowhere else")
        equal(l.joined, spoken, "the lines reassemble the sentence exactly")
    }

    static func propertyGrowth() {
        scenario("11. property — growth with pauses anywhere reassembles exactly")
        let pool = ["book", "the", "flight", "call", "Priya", "about", "Thursday",
                    "and", "move", "it", "to", "noon", "before", "she", "leaves",
                    "for", "Denver", "next", "week", "with", "Sam"]
        var r = Rand(0x5EED)
        var bad = 0
        for _ in 0..<400 {
            let count = 3 + r.below(40)
            let target = (0..<count).map { _ in pool[r.below(pool.count)] }
            let l = Listener()
            var built: [String] = []
            for w in target {
                built.append(w)
                l.partial(built.joined(separator: " "))
                if r.below(4) == 0 { l.pause() }    // a pause could fall anywhere
            }
            l.final(built.joined(separator: " "))
            if l.joined != target.joined(separator: " ") { bad += 1 }
        }
        equal(bad, 0, "400 random pause schedules reassembled the sentence exactly")
    }

    static func propertyInsertions() {
        scenario("12. property — mid-stream insertions never delete or duplicate speech")
        let pool = ["send", "the", "invoice", "to", "Sam", "on", "Monday", "and",
                    "tell", "him", "we", "are", "late", "again", "sorry", "about",
                    "that", "meeting", "yesterday", "morning"]
        let fillers = ["the", "a", "just", "really", "then"]
        var r = Rand(0xC0FFEE)
        var lost = 0, duplicated = 0
        for _ in 0..<400 {
            let count = 4 + r.below(30)
            let spoken = (0..<count).map { _ in pool[r.below(pool.count)] }
            let l = Listener()
            var shown: [String] = []
            var inserted = 0
            for w in spoken {
                shown.append(w)
                // Apple sometimes decides a filler belongs INSIDE what it has
                // already shown — including inside text we already emitted.
                if shown.count > 2 && r.below(6) == 0 {
                    shown.insert(fillers[r.below(fillers.count)], at: r.below(shown.count - 1))
                    inserted += 1
                }
                l.partial(shown.joined(separator: " "))
                if r.below(5) == 0 { l.pause() }
            }
            l.final(shown.joined(separator: " "))
            let out = words(l.joined)
            if !isSubsequence(spoken.map { $0.lowercased() }, of: out) { lost += 1 }
            if out.count > spoken.count + inserted { duplicated += 1 }
        }
        equal(lost, 0, "400 insertion schedules lost no spoken word")
        equal(duplicated, 0, "and emitted nothing beyond what the recognizer showed")
    }

    static func propertyResets() {
        scenario("13. property — a window reset banks, it never deletes")
        let a = ["move", "the", "Thursday", "review", "to", "next", "week", "because",
                 "Priya", "is", "out", "and", "nobody", "else", "can", "run", "it"]
        let b = ["remind", "me", "to", "pay", "the", "parking", "ticket", "before",
                 "Friday", "or", "it", "doubles"]
        var r = Rand(0xBADA55)
        var lostFirst = 0, lostSecond = 0
        for _ in 0..<200 {
            let cut = 3 + r.below(a.count - 3)      // reset after this many words
            let first = Array(a[0..<cut])
            let l = Listener()
            var built: [String] = []
            for w in first {
                built.append(w)
                l.partial(built.joined(separator: " "))
                if r.below(8) == 0 { l.pause() }
            }
            built = []
            for w in b {                            // the window is replaced
                built.append(w)
                l.partial(built.joined(separator: " "))
                if r.below(8) == 0 { l.pause() }
            }
            l.final(built.joined(separator: " "))
            let out = words(l.joined)
            if !isSubsequence(first.map { $0.lowercased() }, of: out) { lostFirst += 1 }
            if !isSubsequence(b.map { $0.lowercased() }, of: out) { lostSecond += 1 }
        }
        equal(lostFirst, 0, "200 resets: nothing spoken before the reset was lost")
        equal(lostSecond, 0, "200 resets: nothing spoken after the reset was lost")
    }

    /// Everything at once: growth, retraction-then-restore, mid-text
    /// insertion and window resets, interleaved at random. Only the two hard
    /// invariants are asserted, because they are the whole point of the type:
    /// no spoken word is lost, and nothing runs away duplicating.
    static func propertyEverything() {
        scenario("15. property — growth, retraction, insertion and resets together")
        // Each decoder window draws from its OWN vocabulary. That is what a
        // window reset is: the decoder discards its hypothesis and starts on
        // different content. Letting two windows share words would not make
        // the test stricter, it would make it a test of a recognizer that does
        // not exist — see case 16 for the one ambiguity that models.
        let pools = [
            ["move", "review", "Thursday", "call", "Priya", "invoice", "leaves"],
            ["tell", "Sam", "land", "noon", "Friday", "doubles", "late"],
            ["book", "clinic", "referral", "quarter", "Baylor", "parking", "ticket"],
        ]
        let fillers = ["just", "really", "then", "so"]
        var r = Rand(0x0DDBA11)
        var lost = 0, runaway = 0, worstRatio = 0
        for _ in 0..<600 {
            // Speech is delivered in one or more decoder windows.
            let windowCount = 1 + r.below(3)
            var windows: [[String]] = []
            for k in 0..<windowCount {
                let pool = pools[k % pools.count]
                let n = 2 + r.below(18)
                windows.append((0..<n).map { _ in pool[r.below(pool.count)] })
            }
            let spoken = windows.flatMap { $0 }

            let l = Listener()
            var inserted = 0
            var lastShown = ""
            for window in windows {
                var shown: [String] = []
                for w in window {
                    shown.append(w)
                    l.partial(shown.joined(separator: " "))

                    // The recognizer takes words back and puts them straight
                    // back — the shape that used to pin the old cursor high
                    // and swallow everything underneath it.
                    if shown.count >= 3 && r.below(5) == 0 {
                        let keep = shown.count - (1 + r.below(2))
                        l.partial(shown[0..<keep].joined(separator: " "))
                        l.partial(shown.joined(separator: " "))
                    }
                    // A filler appears inside text already shown.
                    if shown.count > 2 && r.below(7) == 0 {
                        shown.insert(fillers[r.below(fillers.count)], at: r.below(shown.count - 1))
                        inserted += 1
                        l.partial(shown.joined(separator: " "))
                    }
                    if r.below(5) == 0 { l.pause() }
                }
                lastShown = shown.joined(separator: " ")
                l.pause()
            }
            // The final result is the last text the recognizer actually showed
            // — fillers and all. Feeding anything else would be testing a
            // recognizer that does not exist.
            l.final(lastShown)

            let out = words(l.joined)
            if !isSubsequence(spoken.map { $0.lowercased() }, of: out) { lost += 1 }
            let ceiling = spoken.count + inserted
            if out.count > ceiling { runaway += 1 }
            worstRatio = max(worstRatio, out.count * 100 / max(1, ceiling))
        }
        equal(lost, 0, "600 mixed schedules: not one spoken word was lost")
        equal(runaway, 0, "600 mixed schedules: nothing emitted twice (worst \(worstRatio)% of ceiling)")
    }

    /// The one case that cannot be decided from the text alone. A shared
    /// opening is a shared opening: "we are leaving at four" collapsing to "we"
    /// and rebuilding, and a NEW window that happens to open on "we", are the
    /// same strings in the same order.
    ///
    /// CHANGED 2026-08-05, and changed to demand MORE, not less. This case used
    /// to assert that the shared opening was ABSORBED — the expected value on
    /// the second listener was `["we are leaving at four now", "going home"]`,
    /// with "we are" deleted, described as "the known cost". A passing test
    /// whose expected value is two deleted words is not a pin, it is a licence,
    /// and it sat directly across the project's one binding rule: never lose
    /// speech. It also failed in the direction the earlier review caught, and
    /// it got worse as the shared opening got longer — a measured sweep put the
    /// loss at 4, 5 and 6 words for openings of 4, 5 and 6.
    ///
    /// The ambiguity has not gone away; the CHOICE has changed, and it is now
    /// made the same way in both directions:
    ///
    ///   * while the text is still INSIDE what we sent (case a, "we"), nothing
    ///     is emitted — a collapse costs nothing to believe, because believing
    ///     it emits no words and the next callback can still overturn it;
    ///   * the moment the text says something we did not send (case b, "going"
    ///     after "we are"), the whole of it is treated as new speech and comes
    ///     out whole.
    ///
    /// The cost is now duplication of the shared opening in the rare case where
    /// the collapse reading was right, which is recoverable by anyone reading
    /// the feed. The cost before was deletion, which is not.
    static func ambiguousReopening() {
        scenario("16. the irreducible ambiguity — a shared opening")

        // Collapse and rebuild: the text never leaves what we sent, so nothing
        // is emitted while it is on screen and the rebuild is not sent twice.
        let a = Listener()
        a.partial("we are leaving at four")
        a.pause()
        a.partial("we")                              // deep collapse
        a.pause()
        a.partial("we are leaving at four thirty")   // and back
        a.pause()
        equal(a.lines, ["we are leaving at four", "thirty"],
              "collapse and rebuild: nothing lost, nothing repeated")

        // A different sentence that opens on the same word. The moment it
        // diverges it is new speech, and ALL of it is emitted.
        let b = Listener()
        b.partial("we are leaving at four now")
        b.pause()
        b.partial("we")
        b.partial("we are")
        b.partial("we are going")
        b.partial("we are going home")
        b.pause()
        equal(b.lines, ["we are leaving at four now", "we are going home"],
              "a shared opening is no longer absorbed — the second sentence is whole")
        check(isSubsequence(words("we are going home"), of: words(b.joined)),
              "every word of the second sentence survived, in order")

        // And it does not get worse as the shared opening gets longer. This is
        // the sweep that failed before: four shared words deleted four, five
        // deleted five, six deleted six.
        for k in 1...6 {
            let opening = Array(repeating: "really", count: k - 1)
            let first = (["we"] + opening + ["leaving", "at", "four", "now"])
                .joined(separator: " ")
            let secondWords = ["we"] + opening + ["going", "home", "to", "the", "garage"]
            let c = Listener()
            c.partial(first)
            c.pause()
            var built: [String] = []
            for w in secondWords {
                built.append(w)
                c.partial(built.joined(separator: " "))
            }
            c.final(built.joined(separator: " "))
            check(isSubsequence(secondWords.map { $0.lowercased() }, of: words(c.joined)),
                  "shared opening of \(k): the second sentence still arrives whole")
        }
    }

    /// The four mechanisms an adversarial read of the previous version found,
    /// each on the exact input it was found on. They are here as themselves,
    /// not as a property, because a named defect that comes back should come
    /// back by name.
    static func namedDefects() {
        scenario("17. the four named defects, on their own inputs")

        // M1 — DUPLICATION. A flushed line, then a fresh window opening on a
        // word that line contains. The boundary swallowed the shared "the",
        // the next word came out ALONE mid-sentence — the reported signature —
        // and then the whole window was emitted again on top of it.
        let m1 = Listener()
        m1.partial("the meeting ran late and Sam was sorry")
        m1.pause()
        for text in ["the", "the meter", "the meter in", "the meter in the",
                     "the meter in the garage", "the meter in the garage doubles",
                     "the meter in the garage doubles on",
                     "the meter in the garage doubles on Friday"] {
            m1.partial(text)
        }
        m1.pause()
        equal(m1.lines, ["the meeting ran late and Sam was sorry",
                         "the meter in the garage doubles on Friday"],
              "M1: no one-word slice, no sentence sent twice")

        // M2 — LOSS. A one- or two-word UNSENT hypothesis silently overwritten
        // when the window reset onto a word it shared.
        let m2 = Listener()
        for text in ["to", "to review", "to", "to and", "to and August",
                     "to and August filling", "to and August filling me",
                     "to and August filling me insurance"] {
            m2.partial(text)
        }
        m2.final("to and August filling me insurance")
        check(isSubsequence(words("to review"), of: words(m2.joined)),
              "M2: the two-word hypothesis was not overwritten")
        check(isSubsequence(words("to and August filling me insurance"), of: words(m2.joined)),
              "M2: and the window that replaced it arrived whole")

        // M3 — LOSS. A multi-word shared opening absorbed after a flush. The
        // sweep for this one lives in case 16; this is the original input.
        let m3 = Listener()
        m3.partial("we are really not leaving at four now")
        m3.pause()
        for text in ["we", "we are", "we are really", "we are really not",
                     "we are really not going", "we are really not going home",
                     "we are really not going home to",
                     "we are really not going home to the",
                     "we are really not going home to the garage"] {
            m3.partial(text)
        }
        m3.final("we are really not going home to the garage")
        equal(m3.lines, ["we are really not leaving at four now",
                         "we are really not going home to the garage"],
              "M3: four shared words are no longer deleted")

        // M4 — LOSS. `isFinal` or Stop arriving while the cursor was HELD. The
        // hold returned early without taking the new words in, so the final
        // emitted the stale tail and dropped everything the new window showed.
        // Measured before: 1 word lost for a 1-word window, up to 4 for four.
        for n in 1...5 {
            let m4 = Listener()
            let long = "so I told Eric that the Nicholson deal is dead"
            var built: [String] = []
            for w in long.split(separator: " ") {
                built.append(String(w))
                m4.partial(built.joined(separator: " "))
            }
            let short = Array("so I need to leave".split(separator: " ").prefix(n))
            built = []
            for w in short {
                built.append(String(w))
                m4.partial(built.joined(separator: " "))
            }
            m4.final(built.joined(separator: " "))    // isFinal during the old hold
            check(isSubsequence(built.map { $0.lowercased() }, of: words(m4.joined)),
                  "M4: a final after a \(n)-word window keeps all \(n) words")
            check(isSubsequence(words(long), of: words(m4.joined)),
                  "M4: and does not drop the sentence it interrupted (\(n))")
        }

        // Stop, not isFinal — the other path into the same hold.
        let m5 = Listener()
        for text in ["so I told Eric that the Nicholson deal is dead",
                     "so", "so I", "so I need", "so I need to"] {
            m5.partial(text)
        }
        m5.pause()                                    // Stop flushes the same way
        check(isSubsequence(words("so I need to"), of: words(m5.joined)),
              "M4: Stop during the old hold keeps the new window too")
    }

    static func degenerate() {
        scenario("14. degenerate inputs")
        let l = Listener()
        equal(l.partial("").changed, false, "empty first hypothesis is inert")
        equal(l.pending, "", "nothing pending")
        l.pause()
        equal(l.lines.count, 0, "a pause with nothing pending emits nothing")
        l.partial("   ")
        equal(l.lines.count, 0, "whitespace-only emits nothing")
        l.partial("ok")
        l.pause()
        equal(l.lines, ["ok"], "a single word still gets through")

        // A retraction all the way back to one word, then a rebuild.
        let m = Listener()
        m.partial("we are leaving at four")
        m.pause()
        m.partial("we")
        m.pause()
        equal(m.lines, ["we are leaving at four"], "a collapse emits nothing new")
        m.partial("we are leaving at four thirty")
        m.pause()
        check(isSubsequence(words("we are leaving at four thirty"), of: words(m.joined)),
              "and the rebuild loses nothing")
    }
}

// ------------------------------------------------------------------ main

@main
struct TranscriptCursorTests {
    static func main() {
        Cases.revision()
        Cases.frontInsertion()
        Cases.deletion()
        Cases.fullReset()
        Cases.identicalRepeats()
        Cases.emptyString()
        Cases.shrinkByExactlyTenThatIsARevision()
        Cases.shrinkByExactlyTenThatIsAReset()
        Cases.punctuationOnly()
        Cases.reportedSignature()
        Cases.everyWordExactlyOnce()
        Cases.propertyGrowth()
        Cases.propertyInsertions()
        Cases.propertyResets()
        Cases.propertyEverything()
        Cases.ambiguousReopening()
        Cases.namedDefects()
        Cases.degenerate()

        print("\n\(checks - failures)/\(checks) checks passed")
        if failures > 0 {
            print("\(failures) FAILED")
            exit(1)
        }
        print("TranscriptCursor: all green")
        exit(0)
    }
}
