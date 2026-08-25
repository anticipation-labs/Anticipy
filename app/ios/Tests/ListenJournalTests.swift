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
              cause.entries.count == 1 && cause.entries[0].contains("routeChange"))

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
        // Emptying it is only half of clear's job. The ring also has to forget
        // WHERE it was writing: leave that behind and the next refill past the
        // limit unrolls from a stale offset, which keeps an old line and drops a
        // new one. That is the same newest-wins property case 4 pins, broken by
        // a path case 4 never walks. So this refills past the limit afterwards
        // instead of trusting emptiness alone, and it checks there was something
        // to clear in the first place, since a record that silently did nothing
        // would satisfy an emptiness test on its own.
        let cleared = ListenJournal(limit: 3)
        cleared.record(.sessionStarted, at: t0)
        let hadSomethingToClear = !cleared.entries.isEmpty
        cleared.clear()
        let emptyAfterClear = cleared.entries.isEmpty
        for i in 0..<5 { cleared.record(.flushed(reason: "c\(i)", words: i), at: t0) }
        let refilled = cleared.entries
        check("clearing empties the journal and resets it, so a refill still keeps the newest",
              hadSomethingToClear && emptyAfterClear
                  && refilled.count == 3
                  && refilled[0].contains("c2")
                  && refilled[1].contains("c3")
                  && refilled[2].contains("c4"))

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
              flush.entries.count == 1
                  && flush.entries[0].contains("ceiling")
                  && flush.entries[0].contains("12 words"))

        // ------------------------------------------------------------ 7. two threads
        // record() is called from the audio thread and from the main queue while
        // Settings may be reading it. An unsynchronised array here is a crash in
        // the one code path whose job is to explain crashes.
        //
        // Run twice on purpose. With room to spare every write must survive,
        // which is the plain no-loss property. With a limit BELOW the number of
        // writes, the contended branch is the ring's overwrite rather than its
        // append, so the wrap path is inside what this case proves instead of
        // beside it. A third queue reads entries throughout, because on a phone
        // Settings can be showing the journal while a session is still running.
        func hammer(limit: Int) -> (kept: Int, reads: Int, torn: Bool) {
            let journal = ListenJournal(limit: limit)
            let group = DispatchGroup()
            let audioThread = DispatchQueue(label: "test.audio")
            let mainThread = DispatchQueue(label: "test.main")
            let readerThread = DispatchQueue(label: "test.reader")
            var reads = 0
            var torn = false
            for (tag, queue) in [("audio", audioThread), ("main", mainThread)] {
                queue.async(group: group) {
                    for i in 0..<100 {
                        journal.record(.posted(ok: true, detail: "\(tag)\(i)"), at: t0)
                    }
                }
            }
            // A snapshot taken mid-write may be short, but it may never exceed
            // the bound, hold a blank line, or hold anything that is not one of
            // the lines just written.
            readerThread.async(group: group) {
                for _ in 0..<200 {
                    let snapshot = journal.entries
                    reads += 1
                    if snapshot.count > limit { torn = true }
                    if snapshot.contains(where: { !$0.contains("posted") }) { torn = true }
                }
            }
            group.wait()
            return (journal.entries.count, reads, torn)
        }
        let roomy = hammer(limit: 400)
        let tight = hammer(limit: 64)
        check("two queues writing while a third reads: nothing lost, nothing torn, bound held",
              roomy.kept == 200 && roomy.reads == 200 && !roomy.torn
                  && tight.kept == 64 && tight.reads == 200 && !tight.torn)

        // ------------------------------------------------------------ 8. it survives the process
        // The ring holds ~400 lines and dies with the app. A day of listening
        // is longer than that and the failure worth reading is usually the one
        // that killed the process, so the ring alone cannot answer "what
        // happened this morning". A file sink can.
        //
        // Bounded and rotated for the reason the class header already gives:
        // backend/start.sh exists in this repo because a disposable log filled
        // a volume and took production down. Two files, newest wins.
        func tempDir() -> URL {
            let d = FileManager.default.temporaryDirectory
                .appendingPathComponent("journal-\(UUID().uuidString)")
            try? FileManager.default.createDirectory(at: d, withIntermediateDirectories: true)
            return d
        }

        let dirA = tempDir()
        let fileA = dirA.appendingPathComponent("listen-journal.log")
        let persisted = ListenJournal(limit: 10, fileURL: fileA)
        persisted.record(.sessionStarted, at: t0)
        persisted.record(.flushed(reason: "gap", words: 7), at: t0.addingTimeInterval(1))
        check("what was recorded can be read back after the object is gone",
              persisted.persistedLines.count == 2
                  && persisted.persistedLines[0].contains("sessionStarted")
                  && persisted.persistedLines[1].contains("7 words"))

        // Oldest first across the rotation boundary too, for the same reason
        // entries is: a session that failed is read from its start.
        let dirB = tempDir()
        let fileB = dirB.appendingPathComponent("listen-journal.log")
        let rolling = ListenJournal(limit: 10_000, fileURL: fileB, rotateAtBytes: 2_048)
        for i in 0..<400 {
            rolling.record(.posted(ok: true, detail: "line\(i)"), at: t0)
        }
        let all = rolling.persistedLines
        check("a file past the cap rotates rather than growing without end",
              FileManager.default.fileExists(atPath: fileB.appendingPathExtension("1").path))
        check("the newest line is in the newest file, and survives the rotation",
              all.last?.contains("line399") == true)
        check("rotation keeps two files, never more",
              !FileManager.default.fileExists(atPath: fileB.appendingPathExtension("2").path))
        check("no single file is allowed past the cap by much",
              (try? FileManager.default.attributesOfItem(atPath: fileB.path)[.size] as? Int)
                  .flatMap { $0 } ?? 0 < 8_192)

        // The journal is exportable from Settings, so anything written here
        // leaves the phone on a person's tap. design/LOCAL-FIRST.md governs it:
        // a flush is a word COUNT, never the words.
        let dirC = tempDir()
        let fileC = dirC.appendingPathComponent("listen-journal.log")
        let priv = ListenJournal(limit: 10, fileURL: fileC)
        priv.record(.flushed(reason: "ceiling", words: 12), at: t0)
        priv.record(.posted(ok: false, detail: "requeued, offline"), at: t0)
        // record() is async — it must be, because it is called from the audio
        // thread and now touches a file. So a check that reads the file
        // DIRECTLY has to drain the queue first; any read through the journal
        // does that by entering the same serial queue. Without this line the
        // file is simply empty here and the check fails for a reason that has
        // nothing to do with what it is testing.
        _ = priv.persistedLines
        let onDisk = (try? String(contentsOf: fileC, encoding: .utf8)) ?? ""
        check("nothing written to disk carries transcript text",
              !onDisk.isEmpty && onDisk.contains("12 words")
                  && !onDisk.lowercased().contains("the quick brown"))

        // A journal with no file is still a journal. The ring must work when
        // the sink cannot be opened at all, because a diagnostic that needs
        // disk to function is useless on the device that ran out of it.
        let noFile = ListenJournal(limit: 3,
                                   fileURL: URL(fileURLWithPath: "/nope/nowhere/x.log"))
        noFile.record(.sessionStarted, at: t0)
        check("an unopenable sink never costs us the in-memory journal",
              noFile.entries.count == 1 && noFile.persistedLines.isEmpty)

        // ------------------------------------------------------------ 9. round trip
        // The tally folds over events read BACK from the file, so writing and
        // reading must agree. They are two functions that can drift, and the
        // drift would be silent: a reworded line still looks fine to a person
        // and simply stops counting. Every case goes out and comes back.
        let everyCase: [ListenEvent] = [
            .sessionStarted,
            .sessionStopped(cause: .interruption),
            .sessionStopped(cause: .owner),
            .recognizerSwapped(cause: .taskLimit),
            .recognizerSwapped(cause: .silenceRotation),
            .flushed(reason: "ceiling", words: 40),
            .flushed(reason: "gap", words: 1),
            .posted(ok: true, detail: "queued line sent"),
            .posted(ok: false, detail: "requeued, offline"),
            .posted(ok: true, detail: ""),
            .noted("session category: AVAudioSessionCategoryRecord mode: AVAudioSessionModeMeasurement"),
            .noted("low power mode on"),
            .noted("dropped 600 buffers while swapping"),
        ]
        let dirD = tempDir()
        let trip = ListenJournal(limit: 100,
                                 fileURL: dirD.appendingPathComponent("j.log"))
        for e in everyCase { trip.record(e, at: t0) }
        let readBack = trip.persistedEvents.map { $0.1 }
        check("every event written can be read back as the same event",
              readBack == everyCase)
        check("and the times come back too",
              trip.persistedEvents.allSatisfy {
                  Int($0.0.timeIntervalSince1970) == Int(t0.timeIntervalSince1970) })

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
