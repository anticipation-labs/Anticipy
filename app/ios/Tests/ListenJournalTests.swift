import Foundation

// Checks for ListenJournal — the on-device record of what a listening session
// actually did.
//
// The incident these exist for, 2026-08-24: a manual voice test was reported as
// "the test didn't complete", and there was nothing to read. No print, NSLog,
// os_log or Logger anywhere in PhoneListener.swift or AnticipyApp.swift. The
// mic, the recognizer, the flush, the network and the brain were all equally
// plausible suspects and none could be ruled out. A session that fails has to
// be able to say why.
//
// Pure Foundation on purpose, like TranscriptFlushPolicy: these run with swiftc
// alone, no simulator, no scheme, no signing, no network.

@main
struct ListenJournalTests {
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

        // ------------------------------------------------------------ 1. it records
        let one = ListenJournal(limit: 10)
        one.record(.sessionStarted, at: t0)
        check("a recorded event leaves one readable line naming it",
              one.entries.count == 1 && one.entries[0].contains("sessionStarted"))

        // ------------------------------------------------------------ 2. in order
        // A journal read newest-first buries the start of the session, which is
        // where a failed session has to be read from.
        let order = ListenJournal(limit: 10)
        order.record(.sessionStarted, at: t0)
        order.record(.posted(ok: true, detail: "queued"), at: t0.addingTimeInterval(1))
        order.record(.sessionStopped(cause: .owner), at: t0.addingTimeInterval(2))
        check("entries come back oldest first",
              order.entries.count == 3
                  && order.entries[0].contains("sessionStarted")
                  && order.entries[1].contains("posted")
                  && order.entries[2].contains("sessionStopped"))

        // ------------------------------------------------------------ 3. the cause
        // "It stopped" is the useless half of the report. WHY it stopped is the
        // whole reason the journal exists, so the cause has to survive into the
        // text a person reads.
        let cause = ListenJournal(limit: 10)
        cause.record(.sessionStopped(cause: .routeChange), at: t0)
        check("a stop carries its cause into the line",
              cause.entries[0].contains("routeChange"))

        // ------------------------------------------------------------ 4. bounded
        // backend/start.sh exists in this repo because a disposable log database
        // filled a volume and took production down. An unbounded journal on a
        // phone is the same mistake at smaller scale, and the newest events are
        // the ones that explain the failure being investigated.
        let bounded = ListenJournal(limit: 3)
        for i in 0..<10 { bounded.record(.flushed(reason: "r\(i)", words: i), at: t0) }
        check("a full journal keeps the newest events and drops the oldest",
              bounded.entries.count == 3
                  && bounded.entries[0].contains("r7")
                  && bounded.entries[1].contains("r8")
                  && bounded.entries[2].contains("r9"))

        // ------------------------------------------------------------ 5. clear
        let cleared = ListenJournal(limit: 10)
        cleared.record(.sessionStarted, at: t0)
        cleared.clear()
        check("clearing empties the journal", cleared.entries.isEmpty)

        // ------------------------------------------------------------ 6. a flush
        // The trigger and the size of a flush are what distinguish "the ceiling
        // cut a sentence" from "nothing was ever heard". Both belong in the
        // line. The word COUNT and never the words: the events collection
        // already holds the owner's speech, and a second copy of it in a
        // diagnostic log is a privacy regression under design/LOCAL-FIRST.md.
        let flush = ListenJournal(limit: 10)
        flush.record(.flushed(reason: "ceiling", words: 12), at: t0)
        // "12 words" and not a bare "12": the timestamp on the line is made of
        // digits too, and a check that a passing digit pair satisfies is not
        // checking the word count at all.
        check("a flush names its trigger and how many words went out",
              flush.entries[0].contains("ceiling") && flush.entries[0].contains("12 words"))

        // ------------------------------------------------------------ 7. two threads
        // record() is called from the audio thread and from the main queue. An
        // unsynchronised array here is a crash in the one code path whose job is
        // to explain crashes.
        let concurrent = ListenJournal(limit: 400)
        let group = DispatchGroup()
        let audioThread = DispatchQueue(label: "test.audio")
        let mainThread = DispatchQueue(label: "test.main")
        for queue in [audioThread, mainThread] {
            queue.async(group: group) {
                for i in 0..<100 {
                    concurrent.record(.posted(ok: true, detail: "\(i)"), at: t0)
                }
            }
        }
        group.wait()
        check("two queues recording at once neither crash nor lose an entry",
              concurrent.entries.count == 200)

        // ------------------------------------------------------------------ result
        print("")
        if failures.isEmpty {
            print("ListenJournal: all \(checks) checks passed")
        } else {
            print("ListenJournal: \(failures.count)/\(checks) FAILED")
            for f in failures { print("  - \(f)") }
            exit(1)
        }
    }
}
