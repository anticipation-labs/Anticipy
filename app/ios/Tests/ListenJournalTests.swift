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
        //
        // THE READER THREAD IS A CRASH TEST, AND SAYING SO IS THE POINT. It used
        // to carry two assertions that could not fail: `snapshot.count > limit`
        // over a ring bounded at construction, and `!contains("posted")` when
        // every line written here is a `.posted`. Both read like safety and
        // proved nothing. What the reader really pins is that 200 concurrent
        // reads of a journal two queues are writing complete at all — an
        // unsynchronised array here is a crash or a garbage read, and the count
        // coming back is the evidence that neither happened.
        func hammer(limit: Int) -> (kept: Int, reads: Int) {
            let journal = ListenJournal(limit: limit)
            let group = DispatchGroup()
            let audioThread = DispatchQueue(label: "test.audio")
            let mainThread = DispatchQueue(label: "test.main")
            let readerThread = DispatchQueue(label: "test.reader")
            var reads = 0
            for (tag, queue) in [("audio", audioThread), ("main", mainThread)] {
                queue.async(group: group) {
                    for i in 0..<100 {
                        journal.record(.posted(ok: true, detail: "\(tag)\(i)"), at: t0)
                    }
                }
            }
            readerThread.async(group: group) {
                for _ in 0..<200 {
                    // The read itself is the check, and its RESULT deliberately
                    // is not. Every property one could assert about a snapshot
                    // of a bounded ring of `.posted` lines is true by
                    // construction, and a condition that cannot fail is not a
                    // check — it is a sentence that reads like one.
                    _ = journal.entries
                    reads += 1
                }
            }
            group.wait()
            return (journal.entries.count, reads)
        }
        let roomy = hammer(limit: 400)
        let tight = hammer(limit: 64)
        check("two queues writing while a third reads 200 times: nothing lost, the bound held, no crash",
              roomy.kept == 200 && roomy.reads == 200
                  && tight.kept == 64 && tight.reads == 200)

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
        // COUNTED, not asserted against a name no implementation could produce.
        // This used to check that `listen-journal.log.2` did not exist, and
        // `rotateIfNeeded` only ever writes `.1` — so no change to the rotation
        // could have failed it. Counting the directory can: a rotation that
        // started keeping three generations, or one that stopped deleting the
        // one it rolled over, shows up here as a third file.
        let kept = (try? FileManager.default.contentsOfDirectory(
            atPath: dirB.path))?.count ?? 0
        check("rotation keeps two files, never more",
              kept == 2)
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
        // and simply stops counting.
        //
        // EVERY CASE, AND NOW THAT IS TRUE. This used to be a hand-written array
        // literal, and Swift has no exhaustiveness check over an array of enum
        // values — so a reworded line failed the check while a NEW CASE sailed
        // through it. `parse` ends in `default: return nil`, so the new case's
        // every line would be dropped from `persistedEvents`, the tally would
        // under-report a whole event class, and the gate would stay green
        // vouching for it. `ListenEvent.everyCase` below closes that with a
        // compiler error instead of a comment.
        let everyCase = ListenEvent.everyCase
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

        // A DELIVERY FAILURE THAT READS BACK AS A SUCCESS. `parse` decided the
        // outcome with `body.contains("accepted")` — a substring search over the
        // whole line, detail included. Measured:
        //
        //   posted(ok: false, detail: "not accepted by proxy")
        //     -> posted(ok: true,  detail: "by proxy")
        //
        // A day that heard everything and delivered nothing is one of the two
        // failures this screen is for, and this turned it into a clean day.
        // Latent rather than live — today's details are wire names and `http
        // NNN` shapes — but "no live value happens to contain the word" is not a
        // property anything enforces.
        let trap = ListenEvent.posted(ok: false, detail: "not accepted by proxy")
        let dirE = tempDir()
        let trapped = ListenJournal(limit: 10,
                                    fileURL: dirE.appendingPathComponent("j.log"))
        trapped.record(trap, at: t0)
        check("a failed post whose detail contains the word 'accepted' does not read back as accepted",
              trapped.persistedEvents.map { $0.1 } == [trap])

        // ------------------------------------------------ 10. sub-second stamps
        // `[.withInternetDateTime]` has no fractional part, so two lines written
        // 0.8s apart parsed back to the SAME instant. The tally folds through
        // single-slot state, `sorted(by:)` is documented as not stable, and the
        // measured cost of one such tie was twelve hours of listening appearing
        // out of nowhere. The stamps carry milliseconds now.
        let dirF = tempDir()
        let fine = ListenJournal(limit: 10,
                                 fileURL: dirF.appendingPathComponent("j.log"))
        fine.record(.sessionStarted, at: t0)
        fine.record(.sessionStopped(cause: .owner), at: t0.addingTimeInterval(0.8))
        let instants = fine.persistedEvents.map { $0.0 }
        check("two lines written 0.8s apart do not collapse onto the same instant",
              instants.count == 2 && instants[0] != instants[1])

        // AND EVERY LINE ALREADY ON DISK STILL READS. A phone that has been
        // running the old build has a journal full of stamps with no fractional
        // part, and the day worth reading is usually the one before the update.
        // A reader that only understands the new shape would silently drop all
        // of it and report a blank, healthy day.
        check("a line stamped before the milliseconds existed still parses",
              ListenJournal.parse("2026-08-24T09:00:00Z  sessionStopped  listening ended, cause: interruption")?.1
                  == .sessionStopped(cause: .interruption))

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

/// Every case of `ListenEvent`, and the compiler is what keeps it every.
///
/// THE HOLE THIS CLOSES. `ListenJournal` promised that "ListenJournalTests
/// round-trips EVERY case through describe and back; a new case or a reworded
/// line cannot land without failing that check." Half of that was true. A
/// reworded line does fail it. A NEW CASE did not: the list was a hand-written
/// array literal, and Swift has no exhaustiveness check over an array of enum
/// values. `describe` and `ListenTally.of` both switch exhaustively, so the
/// compiler forces those — but `parse` ends in `default: return nil`, so the new
/// case's every line is silently dropped from `persistedEvents`, the tally
/// under-reports a whole class of event, and the gate stays green vouching for
/// the drift the comment said it prevented.
///
/// The chain below cannot be left half-done. Add a case to `ListenEvent` and
/// `kind` stops compiling; add the `Kind` and `samples(of:)` stops compiling;
/// supply a sample and the round-trip check starts covering it. Three compiler
/// errors, in the order a person would want them, instead of a sentence.
///
/// It lives in the test file rather than in `ListenJournal.swift` because
/// nothing in the app would ever call it, and this repo already fails the build
/// over a suite that vouches for a function with no call sites. The gate leg is
/// the same either way: `run_journal_tests.sh` compiles this file.
extension ListenEvent {
    enum Kind: CaseIterable {
        case sessionStarted, sessionStopped, recognizerSwapped
        case flushed, posted, noted
    }

    var kind: Kind {
        switch self {
        case .sessionStarted: return .sessionStarted
        case .sessionStopped: return .sessionStopped
        case .recognizerSwapped: return .recognizerSwapped
        case .flushed: return .flushed
        case .posted: return .posted
        case .noted: return .noted
        }
    }

    /// More than one per kind where the SHAPE of the line differs: a cause that
    /// is a different word, a detail that is empty, a prose fact with a colon in
    /// it. Those are where a describe/parse pair drifts.
    static func samples(of kind: Kind) -> [ListenEvent] {
        switch kind {
        case .sessionStarted:
            return [.sessionStarted]
        case .sessionStopped:
            return [.sessionStopped(cause: .interruption),
                    .sessionStopped(cause: .owner),
                    .sessionStopped(cause: .authorizationLost)]
        case .recognizerSwapped:
            return [.recognizerSwapped(cause: .taskLimit),
                    .recognizerSwapped(cause: .silenceRotation),
                    .recognizerSwapped(cause: .appReturned)]
        case .flushed:
            return [.flushed(reason: "ceiling", words: 40),
                    .flushed(reason: "gap", words: 1)]
        case .posted:
            return [.posted(ok: true, detail: "queued line sent"),
                    .posted(ok: false, detail: "requeued, offline"),
                    .posted(ok: true, detail: "")]
        case .noted:
            return [.noted("session category: AVAudioSessionCategoryRecord mode: AVAudioSessionModeMeasurement"),
                    .noted("low power mode on"),
                    .noted("dropped 600 buffers while swapping")]
        }
    }

    static var everyCase: [ListenEvent] {
        Kind.allCases.flatMap(samples(of:))
    }
}
