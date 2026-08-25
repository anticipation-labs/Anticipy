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
            (at(60), .flushed(reason: .gap, words: 10)),
            (at(300), .sessionStopped(cause: .owner)),
        ]
        let s1 = ListenTally.of(oneSession)
        check("a closed session is measured start to stop",
              s1.sessions == 1 && s1.listeningSeconds == 300)

        let stillOpen: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(120), .flushed(reason: .gap, words: 5)),
        ]
        check("a session that never closed still counts, up to its last event",
              ListenTally.of(stillOpen).listeningSeconds == 120)

        // ------------------------------------------------------- 3. the silence
        // The number the whole card turns on. A phone call that ended listening
        // for the rest of the day shows up here as one enormous gap and nowhere
        // else — the UI still says Listening, and the ring still looks healthy.
        let gapDay: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(30), .flushed(reason: .gap, words: 8)),
            (at(3_600), .flushed(reason: .gap, words: 4)),   // 3570s of nothing
            (at(3_630), .sessionStopped(cause: .owner)),
        ]
        check("the longest stretch with nothing heard is reported",
              ListenTally.of(gapDay).longestSilenceSeconds == 3_570)

        // ------------------------------------------------------- 4. words and shards
        let words: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(10), .flushed(reason: .gap, words: 12)),
            (at(20), .flushed(reason: .ceiling, words: 40)),
            (at(30), .flushed(reason: .gap, words: 3)),
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
            (at(10), .posted(ok: true, detail: .sentFromQueue)),
            (at(20), .posted(ok: false, detail: .shelved(again: true, failure: .system(domain: .url, code: -1009)))),
            (at(30), .posted(ok: false, detail: .shelved(again: true, failure: .system(domain: .url, code: -1009)))),
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
            (at(120), .flushed(reason: .gap, words: 30)),
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
            (at(30), .flushed(reason: .gap, words: 9)),
            (at(900), .flushed(reason: .ceiling, words: 40)),
            (at(960), .sessionStopped(cause: .interruption)),
        ]
        let shuffled: [(Date, ListenEvent)] = [
            (at(960), .sessionStopped(cause: .interruption)),
            (at(30), .flushed(reason: .gap, words: 9)),
            (at(0), .sessionStarted),
            (at(900), .flushed(reason: .ceiling, words: 40)),
        ]
        let straight = ListenTally.of(inOrder)
        let jumbled = ListenTally.of(shuffled)
        check("arrival order cannot change the answer",
              straight == jumbled)
        check("and the numbers are the real ones, not zeros agreeing with zeros",
              straight.listeningSeconds == 960
                  && straight.longestSilenceSeconds == 870
                  && straight.wordsFlushed == 49)

        // ...AND THE CASE THE INVARIANT IS ACTUALLY ABOUT. The four events above
        // sit at four DISTINCT timestamps, so they only ever prove the sort is
        // called. Two lines written 0.8s apart used to parse back to the same
        // Date, `sorted(by:)` is documented as not stable, and this fold runs
        // through single-slot state — so equal stamps were order-sensitive and
        // the answers were 12 hours apart:
        //
        //   [started@T, stopped@T, posted@T+12h] -> listening 0s     silence 0s
        //   [stopped@T, started@T, posted@T+12h] -> listening 43200s silence 43200s
        //
        // Sub-second stamps make a real tie almost impossible; this makes the
        // answer defined even so, because "almost" is what the invariant is for.
        let tieOne: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(0), .sessionStopped(cause: .interruption)),
            (at(43_200), .posted(ok: true, detail: .sentFromQueue)),
        ]
        let tieOther: [(Date, ListenEvent)] = [
            (at(0), .sessionStopped(cause: .interruption)),
            (at(0), .sessionStarted),
            (at(43_200), .posted(ok: true, detail: .sentFromQueue)),
        ]
        check("two events stamped at the same instant fold the same way in either order",
              ListenTally.of(tieOne, now: at(43_200))
                  == ListenTally.of(tieOther, now: at(43_200)))
        // Same for two events of the SAME case at one instant: `notes` is an
        // ordered array, so two facts sharing a stamp would otherwise make the
        // whole tally depend on which thread's write landed first.
        let facts = ListenSessionFacts(category: "AVAudioSessionCategoryRecord",
                                       mode: "AVAudioSessionModeMeasurement",
                                       lowPower: true)
        let tieNotes: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(5), .sessionFacts(facts)),
            (at(5), .buffersDropped(count: 600)),
        ]
        let tieNotesOther: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(5), .buffersDropped(count: 600)),
            (at(5), .sessionFacts(facts)),
        ]
        check("two facts stamped at the same instant come back in the same order either way",
              ListenTally.of(tieNotes) == ListenTally.of(tieNotesOther))

        // ------------------------------------- 10. the day a call ended and nobody noticed
        // THE CASE THIS WHOLE TYPE EXISTS FOR, and the one it used to get wrong.
        //
        // 09:00 a call takes the microphone. iOS never delivers `.ended`,
        // nothing restarts listening, and the phone is deaf until bedtime. The
        // journal's last line is the 09:00 stop — there are no later events at
        // all — so a fold that measures to its own last line answers zero, and
        // a fold that only measures a trailing silence for a session left OPEN
        // never reaches this one, because an interruption is exactly what sets
        // `openedAt` back to nil.
        //
        // Measured on the code before this check existed, with the screen read
        // at 19:00: `longestSilence = 3480` — "58 min", a reassuring number on
        // a phone that had heard nothing for eleven hours. The asymmetry was
        // backwards: the recoverable failure (session left open) reported
        // 10hr 58min correctly, the FATAL one reported 58 minutes.
        let callAt0900: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),                             // 08:00
            (at(120), .flushed(reason: .gap, words: 30)),        // 08:02
            (at(3_600), .sessionStopped(cause: .interruption)),   // 09:00
        ]
        let readAt1900 = at(39_600)                               // 19:00
        let deaf = ListenTally.of(callAt0900, now: readAt1900)
        check("a call that ended listening at 09:00 reads as eleven deaf hours at 19:00",
              deaf.longestSilenceSeconds == 39_480
                  && deaf.unheardForSeconds == 39_480)
        check("and the screen can say why nothing is being heard, not only how long",
              deaf.ending == .stoppedByOther(cause: "interruption"))

        // THE OTHER DIRECTION, and it is a lie of the same size. If the owner
        // turned listening off at 09:00, ten quiet hours are correct behaviour
        // — nobody was listening, so nothing was missed. Reporting them as
        // "longest stretch hearing nothing" would invent a failure. The cause
        // on the stop is what tells the two apart, and it is already recorded.
        let ownerStoppedAt0900: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(120), .flushed(reason: .gap, words: 30)),
            (at(3_600), .sessionStopped(cause: .owner)),
        ]
        let off = ListenTally.of(ownerStoppedAt0900, now: readAt1900)
        check("hours of quiet after the owner turned listening off are not a finding",
              off.longestSilenceSeconds == 3_480 && off.unheardForSeconds == 0
                  && off.ending == .stoppedByOwner)

        // The same hole in the MIDDLE of a day. A call at 09:00, the owner
        // finally opens the app at 18:00 and listening resumes — that is nine
        // deaf hours with a start line on both sides of them, and the fold used
        // to answer zero for it because a `sessionStarted` simply reset the
        // silence clock. `.appReturned` counts how often that happened; this is
        // how long it cost.
        let nineDeafHours: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(120), .flushed(reason: .gap, words: 30)),
            (at(3_600), .sessionStopped(cause: .interruption)),
            (at(36_000), .recognizerSwapped(cause: .appReturned)),
            (at(36_000), .sessionStarted),
            (at(36_060), .flushed(reason: .gap, words: 5)),
        ]
        let recovered = ListenTally.of(nineDeafHours, now: at(39_600))
        check("an interruption nothing recovered from until 18:00 is nine hours of silence, not none",
              recovered.longestSilenceSeconds == 35_880)
        check("and once words arrive again the phone is not still reported as deaf",
              recovered.unheardForSeconds == 3_540
                  && recovered.ending == .listening)

        // WHY THE CLOCK IS A PARAMETER AND NOT AN OPTIONAL EXTRA. With no
        // reading moment the record can only end at its own last line, and on
        // this day the last line IS the 09:00 stop — so the answer is the
        // 58 minutes before the call, and the eleven hours after it are
        // unmeasurable by construction. `of` stays pure; the SCREEN owns the
        // clock, because the screen is the thing that knows when it is being
        // read. Every check above this section relies on this fallback, which
        // is why it is defaulted rather than required.
        check("with no reading moment the deaf hours are unmeasurable, which is why the screen passes one",
              ListenTally.of(callAt0900).longestSilenceSeconds == 3_480)

        // ------------------------------------------------------- 9. senses facts
        // The three things that were invisible: what the audio session ACTUALLY
        // became (three try? calls decide it and swallow every failure), low
        // power mode, and audio dropped while a swap was in flight. Kept in
        // order and verbatim — they are prose written for a person already.
        let noted: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(0), .sessionFacts(ListenSessionFacts(category: "AVAudioSessionCategoryRecord",
                                                     mode: "AVAudioSessionModeMeasurement",
                                                     lowPower: false))),
            (at(1), .sessionFacts(ListenSessionFacts(category: "AVAudioSessionCategoryPlayAndRecord",
                                                     mode: "AVAudioSessionModeDefault",
                                                     lowPower: true))),
            (at(40), .buffersDropped(count: 600)),
        ]
        let n = ListenTally.of(noted)
        check("senses facts are kept, in order, verbatim",
              n.notes.count == 3
                  && n.notes[0].contains("AVAudioSessionCategoryRecord")
                  && n.notes[1].hasSuffix("low power mode on")
                  && n.notes[2] == "dropped 600 buffers while swapping")
        // A name the closed sets do not know cannot be RECORDED as itself. The
        // journal's payloads are typed precisely so a transcript handed to this
        // initializer arrives as the word "unrecognised" — the state a scan
        // used to have to detect is now one the type cannot hold.
        let smuggled = ListenTally.of([
            (at(0), .sessionStarted),
            (at(0), .sessionFacts(ListenSessionFacts(
                category: "he said his card number is 4111 1111 1111 1111",
                mode: "AVAudioSessionModeMeasurement", lowPower: false))),
        ])
        check("a category that is not a category cannot be written down as one",
              smuggled.notes.count == 1
                  && !smuggled.notes[0].contains("4111")
                  && smuggled.notes[0].contains("unrecognised"))
        check("a note is not mistaken for something heard",
              n.wordsFlushed == 0 && n.flushes == 0)

        // --------------------------------------------------- 10. what it cost
        // An always-on microphone, a speech recognizer and a 4-second timer are
        // a real draw, and until now nothing in this product had ever measured
        // one. The honest question is not "is the battery low" — the phone
        // already says that better than we can — but "what did LISTENING spend,
        // and over how long", so the number can be put next to the counts above
        // it and read as explainable or not.
        //
        // No threshold anywhere below. A comparison would be a rule written
        // while the sense is unmeasured, which is what Law 5 forbids, and there
        // is no measured drain in this repo to draw a line from.

        // Nothing recorded is its own answer, and it is the SIMULATOR's answer
        // and every pre-existing journal's answer. It must not read as "spent
        // nothing", which is a different and much more reassuring claim.
        let noBattery = ListenTally.of([
            (at(0), .sessionStarted),
            (at(600), .flushed(reason: .gap, words: 12)),
        ])
        check("a day with no battery readings says so rather than reporting zero spent",
              noBattery.batteryReadings == 0
                  && noBattery.batterySpentPoints == 0
                  && noBattery.batteryMeasuredSeconds == 0)

        // The ordinary case: an hour of listening off the charger, four points
        // gone. Both halves are reported, because "4%" with no window is not a
        // measurement and "%/hr" is a rate this screen has no business inventing
        // on the reader's behalf.
        let anHour: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(0), .batteryRead(percent: 90, onPower: false)),
            (at(3_600), .batteryRead(percent: 86, onPower: false)),
            (at(3_601), .sessionStopped(cause: .owner)),
        ]
        let spent = ListenTally.of(anHour)
        check("points spent while listening are counted, with the time they were spent over",
              spent.batterySpentPoints == 4 && spent.batteryMeasuredSeconds == 3_600)
        check("and the readings themselves are counted, so absent and zero stay different",
              spent.batteryReadings == 2)

        // THE CHARGER. A day spent plugged in would otherwise report a tiny
        // drain, or a negative one, and read as a triumph of efficiency. That
        // time is excluded from the measurement and reported separately, so the
        // exclusion is visible rather than silent.
        let plugged: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(0), .batteryRead(percent: 50, onPower: true)),
            (at(3_600), .batteryRead(percent: 80, onPower: false)),
            (at(7_200), .batteryRead(percent: 77, onPower: false)),
        ]
        let charged = ListenTally.of(plugged)
        check("time on the charger is not counted as drain",
              charged.batterySpentPoints == 3 && charged.batteryMeasuredSeconds == 3_600)
        check("and it is reported rather than quietly dropped",
              charged.batteryOnPowerSeconds == 3_600)

        // A level that goes UP while unplugged is a recalibration, not a gift.
        // Signed deltas are summed so a bounce nets itself out, and the total is
        // floored at zero so a report can never claim the phone gained battery
        // by listening.
        let bounced: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(0), .batteryRead(percent: 60, onPower: false)),
            (at(600), .batteryRead(percent: 61, onPower: false)),
            (at(1_200), .batteryRead(percent: 60, onPower: false)),
        ]
        let bounce = ListenTally.of(bounced)
        check("a battery that ticks up while unplugged does not net out as negative drain",
              bounce.batterySpentPoints == 0 && bounce.batteryMeasuredSeconds == 1_200)

        // NOT LISTENING IS NOT MEASURED. This is the whole reason the fold reads
        // the session lines at all: an overnight drain with the app suspended
        // and the microphone off is not a cost of listening, and attributing it
        // would make every number here a lie in the direction that matters most.
        let overnight: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(0), .batteryRead(percent: 80, onPower: false)),
            (at(60), .sessionStopped(cause: .owner)),
            (at(28_800), .batteryRead(percent: 55, onPower: false)),
        ]
        let night = ListenTally.of(overnight)
        check("a drain while listening was off is not charged to listening",
              night.batterySpentPoints == 0 && night.batteryMeasuredSeconds == 0)

        // And a stop-and-restart between two readings breaks the span for the
        // same reason: the hole in the middle is time nobody was listening, and
        // the two readings on either side of it cannot bracket it.
        let broken: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(0), .batteryRead(percent: 80, onPower: false)),
            (at(60), .sessionStopped(cause: .owner)),
            (at(7_200), .sessionStarted),
            (at(10_800), .batteryRead(percent: 70, onPower: false)),
            (at(14_400), .batteryRead(percent: 68, onPower: false)),
        ]
        let gap = ListenTally.of(broken)
        check("a session that stopped and restarted between two readings breaks the span",
              gap.batterySpentPoints == 2 && gap.batteryMeasuredSeconds == 3_600)

        // A reading stamped at the same instant as the stop belongs to the
        // session that is ending, not to the silence that follows it. Ties are
        // ordered rather than left to `sorted(by:)`, which is documented as not
        // stable and carries no defined order for equal keys at all.
        let tie: [(Date, ListenEvent)] = [
            (at(1_800), .sessionStopped(cause: .owner)),
            (at(1_800), .batteryRead(percent: 70, onPower: false)),
            (at(0), .batteryRead(percent: 75, onPower: false)),
            (at(0), .sessionStarted),
        ]
        let tied = ListenTally.of(tie)
        check("a reading stamped with the stop still belongs to the session it ended",
              tied.batterySpentPoints == 5 && tied.batteryMeasuredSeconds == 1_800)

        // A reading is not something heard. The silence clock must not be reset
        // by the phone reporting its own battery, or an interruption that killed
        // the day would be broken into four-second pieces and disappear.
        let quiet: [(Date, ListenEvent)] = [
            (at(0), .sessionStarted),
            (at(1_800), .batteryRead(percent: 70, onPower: false)),
            (at(3_600), .batteryRead(percent: 69, onPower: false)),
        ]
        let q = ListenTally.of(quiet, now: at(3_600))
        check("a battery reading is not evidence that anybody spoke",
              q.longestSilenceSeconds == 3_600 && q.wordsFlushed == 0)

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
