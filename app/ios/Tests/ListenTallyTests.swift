import Foundation

// Checks for ListenTally — what a day of listening actually did, folded out of
// the journal the session already wrote.
//
// Why a fold and not a counter: PhoneListener already records every event this
// reads. A parallel set of counters incremented at the call sites would be a
// second source of truth that drifts from the journal the moment somebody adds
// an event and forgets the counter — and the journal is the thing a person
// exports and reads. So the tally derives, and has NO call sites of its own.
//
// Pure Foundation on purpose, like TranscriptFlushPolicy and ListenJournal:
// these run with swiftc alone. No simulator, no scheme, no signing, no network.

@main
struct ListenTallyTests {
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

        // ------------------------------------------------------- 1. an empty day
        // Zeros, never nil. A day that produced nothing is a FINDING — it is the
        // exact shape of the two holes this card exists for, a suspended app and
        // a deaf recognizer — so it has to be reportable, not absent.
        let empty = ListenTally.of([])
        check("an empty day reports zeros rather than nothing",
              empty.sessions == 0 && empty.listeningSeconds == 0
                  && empty.wordsFlushed == 0 && empty.longestSilenceSeconds == 0)

        // ------------------------------------------------------- 2. time listening
        // Measured start-to-stop, because that is the only pair the journal
        // gives. A session still open at the end of the day counts up to the
        // last event rather than being dropped: the day a session never closed
        // is precisely the day worth reading.
        let oneSession: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(60), .flushed(reason: "gap", words: 10)),
            (at(300), .sessionStopped(cause: .owner)),
        ]
        let s1 = ListenTally.of(oneSession)
        check("a closed session is measured start to stop",
              s1.sessions == 1 && s1.listeningSeconds == 300)

        let stillOpen: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(120), .flushed(reason: "gap", words: 5)),
        ]
        check("a session that never closed still counts, up to its last event",
              ListenTally.of(stillOpen).listeningSeconds == 120)

        // ------------------------------------------------------- 3. the silence
        // The number the whole card turns on. A phone call that ended listening
        // for the rest of the day shows up here as one enormous gap and nowhere
        // else — the UI still says Listening, and the ring still looks healthy.
        let gapDay: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(30), .flushed(reason: "gap", words: 8)),
            (at(3_600), .flushed(reason: "gap", words: 4)),   // 3570s of nothing
            (at(3_630), .sessionStopped(cause: .owner)),
        ]
        check("the longest stretch with nothing heard is reported",
              ListenTally.of(gapDay).longestSilenceSeconds == 3_570)

        // ------------------------------------------------------- 4. words and shards
        let words: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(10), .flushed(reason: "gap", words: 12)),
            (at(20), .flushed(reason: "ceiling", words: 40)),
            (at(30), .flushed(reason: "gap", words: 3)),
        ]
        let w = ListenTally.of(words)
        check("words and flushes are counted",
              w.wordsFlushed == 55 && w.flushes == 3)
        // A ceiling flush is a thought CUT IN HALF by a clock, not a thought
        // that ended. Its rate is the honest read on how often she interrupts a
        // sentence, so it is broken out rather than buried in a total.
        check("ceiling cuts are broken out from ordinary gap flushes",
              w.flushesByReason["ceiling"] == 1 && w.flushesByReason["gap"] == 2)

        // ------------------------------------------------------- 5. swaps by cause
        // An error, Apple's task limit, a route change and the silence rotation
        // need different fixes, so a single "swaps: 12" would be useless.
        let swaps: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(10), .recognizerSwapped(cause: .taskLimit)),
            (at(20), .recognizerSwapped(cause: .taskLimit)),
            (at(30), .recognizerSwapped(cause: .error)),
        ]
        let sw = ListenTally.of(swaps)
        check("swaps are counted by cause, never as one number",
              sw.swaps == 3 && sw.swapsByCause["taskLimit"] == 2
                  && sw.swapsByCause["error"] == 1)

        // ------------------------------------------------------- 6. stops by cause
        // The owner stopping it and iOS taking the microphone away read
        // identically in a total, and only one of them is a defect.
        let stops: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(10), .sessionStopped(cause: .interruption)),
            (at(20), .sessionStarted),
            (at(30), .sessionStopped(cause: .owner)),
        ]
        let st = ListenTally.of(stops)
        check("stops are counted by cause",
              st.sessions == 2 && st.stopsByCause["interruption"] == 1
                  && st.stopsByCause["owner"] == 1)

        // ------------------------------------------------------- 7. delivery
        // A day that heard everything and delivered nothing looks exactly like
        // a microphone that heard nothing at all, from the outside.
        let posts: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(10), .posted(ok: true, detail: "queued line sent")),
            (at(20), .posted(ok: false, detail: "requeued, offline")),
            (at(30), .posted(ok: false, detail: "requeued, offline")),
        ]
        let p = ListenTally.of(posts)
        check("posts are split into landed and failed",
              p.postsAccepted == 1 && p.postsFailed == 2)

        // ------------------------------------------------------- 8. a real shape
        // The failure this card names: listening began, a call interrupted it,
        // and nothing was ever heard again. Every number has to make that
        // legible at a glance rather than requiring the raw lines.
        let deadDay: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(120), .flushed(reason: "gap", words: 30)),
            (at(600), .sessionStopped(cause: .interruption)),
        ]
        let dead = ListenTally.of(deadDay)
        check("a day that died on an interruption says so in the numbers",
              dead.sessions == 1 && dead.stopsByCause["interruption"] == 1
                  && dead.wordsFlushed == 30)

        // Events out of order must not produce a negative anything. The journal
        // is written from two threads and read as a file that may have been
        // rotated; a tally that can go negative would report nonsense on the
        // one day it is needed.
        // The property is not "no negatives" — that passes for the wrong reason,
        // because the unsorted path happens to produce zeros here. The real
        // invariant is that ARRIVAL ORDER CANNOT CHANGE THE ANSWER: the same
        // events shuffled must fold to the same tally.
        let inOrder: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(30), .flushed(reason: "gap", words: 9)),
            (at(900), .flushed(reason: "ceiling", words: 40)),
            (at(960), .sessionStopped(cause: .interruption)),
        ]
        let shuffled: [(Date, ListenEvent)] = [
            (at(960), .sessionStopped(cause: .interruption)),
            (at(30), .flushed(reason: "gap", words: 9)),
            (at(0), .sessionStarted),
            (at(900), .flushed(reason: "ceiling", words: 40)),
        ]
        let straight = ListenTally.of(inOrder)
        let jumbled = ListenTally.of(shuffled)
        check("arrival order cannot change the answer",
              straight == jumbled)
        check("and the numbers are the real ones, not zeros agreeing with zeros",
              straight.listeningSeconds == 960
                  && straight.longestSilenceSeconds == 870
                  && straight.wordsFlushed == 49)

        // ------------------------------------------------------------------ result
        print("")
        if failures.isEmpty {
            print("ListenTally: all \(checks) checks passed")
        } else {
            print("ListenTally: \(failures.count)/\(checks) FAILED")
            for f in failures { print("  - \(f)") }
            exit(1)
        }
    }
}
