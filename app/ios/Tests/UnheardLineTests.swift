import Foundation

// Checks for UnheardLine — the one sentence on the Settings listening row that
// reports something the phone actually MEASURED.
//
// WHY THIS FILE EXISTS. The row shipped with checks on the SHAPE of the call
// and none on its value: that it asked PlainDuration, that it sat in a .task,
// that it ran detached, that it passed `now:`. Which field it read and whether
// the seconds reached the formatter unchanged were pinned by nothing, and two
// mutations went green through the whole suite:
//
//   unheardForSeconds -> longestSilenceSeconds. A historical maximum over the
//   whole journal, not a stretch anybody is in. On a day with one long morning
//   interruption the row then reads "Nothing heard for 11 hr" all evening, in
//   the present tense, on a phone that heard speech ten seconds ago.
//
//   PlainDuration.words(unheard) -> PlainDuration.words(unheard * 2). Every
//   scan matched, because every scan was looking at the call and not the answer.
//
// So the cases below are FOLDS OF REAL EVENT LISTS, never hand-built tallies. A
// ListenTally() with one field set proves nothing about which field the screen
// would have read. Where a case is meant to tell two fields apart it says so out
// loud first, with a control leg asserting that the fold really does hold two
// different numbers — a discriminating case that has quietly stopped
// discriminating is the failure this file was written after.
//
// Pure Foundation, like ListenTally and PlainDuration beside it: swiftc alone,
// no simulator, no scheme, no signing, no network.

@main
struct UnheardLineTests {
    static func main() {
        var checks = 0
        var failures: [String] = []

        func check(_ name: String, _ ok: Bool) {
            checks += 1
            if ok {
                print("  ok    \(name)")
            } else {
                failures.append(name)
                print("  FAIL  \(name)")
            }
        }

        let t0 = Date(timeIntervalSince1970: 1_756_000_000)
        func at(_ s: TimeInterval) -> Date { t0.addingTimeInterval(s) }

        // ------------------------------------------------- 1. nothing to report
        // A phone that has never listened has an empty journal — every
        // `ListenJournal.shared.record` call site is inside a listening or post
        // path. The row must not exist there rather than reporting a zero, which
        // on a fresh install would be a finding about a phone that has done
        // nothing wrong.
        check("a phone that has never listened has no line at all",
              UnheardLine.words(ListenTally.of([])) == nil)

        // ------------------------------------------------- 2. the owner's silence
        // THE LOAD-BEARING ONE. Quiet after you turned it off is the ordinary
        // state of a phone nobody is talking to, and this row must never nag
        // somebody who chose the silence. ListenTally hard-zeroes the stretch
        // under `.stoppedByOwner`; the gate here is above-zero, so that hard
        // zero IS the off switch and no second condition is needed.
        let ownerOff: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(600), .flushed(reason: .gap, words: 40)),
            (at(1_200), .sessionStopped(cause: .owner)),
        ]
        check("silence the owner chose is not reported, an hour later",
              UnheardLine.words(ListenTally.of(ownerOff, now: at(4_800))) == nil)
        check("silence the owner chose is not reported, fourteen hours later",
              UnheardLine.words(ListenTally.of(ownerOff, now: at(51_600))) == nil)

        // THE CAUSE IS THE WHOLE DIFFERENCE, and here are both sides of it with
        // nothing else changed: same events, same clock, one word apart.
        let interrupted: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(600), .flushed(reason: .gap, words: 40)),
            (at(1_200), .sessionStopped(cause: .interruption)),
        ]
        check("the same silence, after something ELSE took the microphone, is reported",
              UnheardLine.words(ListenTally.of(interrupted, now: at(4_200)))
                  == "Nothing heard for 1 hr")

        // ------------------------------------- 3. which field, and it is not the max
        // THE MUTATION THAT SURVIVED. `longestSilenceSeconds` is the longest
        // stretch anywhere in the record; `unheardForSeconds` is the stretch
        // being lived through right now. This day holds one of each and they are
        // ten hours apart, so exactly one of them can produce the sentence below.
        let longMorningThenWords: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(60), .flushed(reason: .gap, words: 12)),
            // Ten hours in which nothing was heard, and then somebody spoke.
            (at(36_060), .flushed(reason: .gap, words: 9)),
            (at(36_120), .sessionStopped(cause: .interruption)),
        ]
        let mixed = ListenTally.of(longMorningThenWords, now: at(36_660))
        // The control. If these two ever become the same number this case has
        // stopped telling the two fields apart, and would go green over the
        // mutation it exists to kill.
        check("the case really does hold two different numbers",
              mixed.longestSilenceSeconds == 36_000 && mixed.unheardForSeconds == 600)
        check("the line reports the stretch being lived through, not the day's longest",
              UnheardLine.words(mixed) == "Nothing heard for 10 min")

        // ------------------------------------------ 4. the day the row exists for
        // A call took the microphone at nine and nothing brought it back. The
        // journal's last line IS the failure, so the fold has to be read against
        // the moment somebody opened the screen — 58 minutes is what this day
        // answers when it is measured to its own last line, and a reassuring
        // wrong number is worse than no number, because it is believed.
        let deafSinceBreakfast: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(3_480), .flushed(reason: .gap, words: 31)),
            (at(3_600), .sessionStopped(cause: .interruption)),
        ]
        check("eleven deaf hours read as eleven deaf hours",
              UnheardLine.words(ListenTally.of(deafSinceBreakfast, now: at(43_080)))
                  == "Nothing heard for 11 hr")
        check("the same day measured to its own last line says something much smaller",
              UnheardLine.words(ListenTally.of(deafSinceBreakfast))
                  == "Nothing heard for 2 min")

        // ------------------------------------------- 5. the seconds arrive unchanged
        // Folds built to hold a known stretch, and the sentence read back
        // literally. This is what the doubling mutation walked through.
        //
        // The stop is one second after the last words so that `now` is always
        // past the record's own last line — the fold reads to the later of the
        // two, and a case where the line wins measures the line, not the clock.
        func deaf(for seconds: Int) -> ListenTally {
            ListenTally.of([
                (at(0), .sessionStarted),
                (at(60), .flushed(reason: .gap, words: 5)),
                (at(61), .sessionStopped(cause: .interruption)),
            ], now: at(60 + Double(seconds)))
        }
        let table: [(Int, String)] = [
            (1, "Nothing heard for 1 seconds"),
            (59, "Nothing heard for 59 seconds"),
            (60, "Nothing heard for 1 min"),
            (600, "Nothing heard for 10 min"),
            (3_600, "Nothing heard for 1 hr"),
            (22_800, "Nothing heard for 6 hr 20 min"),
            (108_000, "Nothing heard for 30 hr"),
        ]
        for (seconds, sentence) in table {
            let tally = deaf(for: seconds)
            check("a fold holding \(seconds)s really holds \(seconds)s",
                  tally.unheardForSeconds == seconds)
            check("\(seconds)s reads \"\(sentence)\"",
                  UnheardLine.words(tally) == sentence)
        }

        // "1 seconds" IS PINNED ON PURPOSE and is not this row's to fix.
        // PlainDuration's own doc comment records that the lift out of
        // ListeningDiagnosticsView kept every string byte-identical so that a
        // copy change could not be smuggled in under a refactor. This row now
        // renders that string, so it is written down here where the screen that
        // renders it can be found — and the day somebody makes the call, this
        // line goes red and says so rather than the change landing unread.

        // ------------------------------------- 6. the wording is not written here
        // Delegation, checked as delegation. The diagnostics screen reports these
        // same seconds one tap deeper, and the whole no-verdict argument both
        // screens rest on holds only while "6 hr 20 min" here is not "6.3 hours"
        // there. Six lines of arithmetic copied into this type would compile,
        // pass every case above that happens to agree, and drift on the first
        // one that does not.
        var delegated = true
        for seconds in [1, 45, 60, 119, 3_599, 3_600, 3_661, 86_400, 108_000] {
            let tally = deaf(for: seconds)
            if UnheardLine.words(tally)
                != "Nothing heard for " + PlainDuration.words(tally.unheardForSeconds) {
                delegated = false
            }
        }
        check("every magnitude is worded by PlainDuration and nothing else", delegated)

        // --------------------------------------------- 7. no threshold, no verdict
        // THE LAW LEG. There is no recorded normal in this repo for a stretch of
        // silence, so any line drawn through these numbers is invented — which is
        // exactly what law 1 exists to stop. The sentence must therefore be the
        // same sentence at four minutes and at thirty hours: one prefix, a
        // magnitude, and a full stop's worth of nothing after it.
        var prefixes = Set<String>()
        var judged: [String] = []
        for seconds in [1, 30, 90, 240, 1_800, 3_600, 21_600, 39_600, 108_000] {
            guard let line = UnheardLine.words(deaf(for: seconds)) else {
                judged.append("\(seconds)s went silent")
                continue
            }
            prefixes.insert(String(line.prefix(18)))
            let lower = line.lowercased()
            for banned in ["!", "too long", "you missed", "you're missing",
                           "check", "wrong", "deaf", "still", "only", "just",
                           "ago", "over", "nearly", "almost"] where lower.contains(banned) {
                judged.append("\(seconds)s said \"\(banned)\"")
            }
        }
        check("one sentence at every magnitude, never a second shape",
              prefixes == ["Nothing heard for "])
        check("no magnitude is graded, softened or exclaimed at", judged.isEmpty)

        // --------------------------------------------------- 8. above zero only
        // Zero is not a threshold. It is the owner's own off switch arriving
        // through the fold, and it is the ONLY gate — a negative can only be a
        // clock that moved backwards under us, and there is no honest duration
        // to report from one.
        let listeningRightNow: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(1_000), .flushed(reason: .gap, words: 22)),
        ]
        check("a phone that was just spoken to says nothing",
              UnheardLine.words(ListenTally.of(listeningRightNow, now: at(1_000))) == nil)
        check("and one second later it says one second",
              UnheardLine.words(ListenTally.of(listeningRightNow, now: at(1_001)))
                  == "Nothing heard for 1 seconds")
        // A clock that moved backwards cannot shorten the day — the fold reads
        // to the later of its last line and `now` — so the row reports the
        // record rather than nonsense.
        check("a backwards clock cannot invent a negative stretch",
              UnheardLine.words(ListenTally.of(listeningRightNow, now: at(-90_000)))
                  == nil)

        // ------------------------------------------------------------------ result
        print("")
        if failures.isEmpty {
            print("UnheardLine: all \(checks) checks passed")
        } else {
            print("UnheardLine: \(failures.count)/\(checks) FAILED")
            for f in failures { print("  - \(f)") }
            exit(1)
        }
    }
}
