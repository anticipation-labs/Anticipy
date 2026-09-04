import Foundation

/// What a day of listening actually did, folded out of the journal.
///
/// The question this answers is the one nobody could answer on 2026-08-24: a
/// manual voice test came back as "the test didn't complete" and there was
/// nothing to read. `ListenJournal` fixed the "nothing to read" half. This is
/// the other half — four hundred raw lines are a transcript of the instrument,
/// not a report, and the two failures worth catching are both invisible in
/// them:
///
///   - a phone call ended listening and nothing restarted it, so the app says
///     Listening over a dead engine for the rest of the day;
///   - the recognizer stopped streaming with no words pending, which no
///     watchdog leg can currently see.
///
/// Both look, line by line, like a quiet afternoon. Both are obvious the moment
/// you see one enormous silence and a stop whose cause was an interruption.
///
/// A FOLD, DELIBERATELY, WITH NO CALL SITES OF ITS OWN. `PhoneListener` already
/// records every event read here. Counters incremented beside those calls would
/// be a second source of truth that drifts the first time somebody adds an
/// event and forgets the counter — and the journal, not the counter, is what a
/// person exports and reads. `Tests/run_tally_tests.sh` fails the build if this
/// type is ever referenced from `PhoneListener`.
///
/// Pure Foundation, like `TranscriptFlushPolicy` and `ListenJournal`: the
/// instrument used to judge the audio path is itself verifiable with `swiftc`
/// alone, with no simulator, signing or network.
struct ListenTally: Equatable {
    /// How many times listening began.
    var sessions = 0
    /// Seconds between a start and its stop. A session still open at the end of
    /// the record counts up to its last event rather than being dropped: the
    /// day a session never closed is exactly the day worth reading.
    var listeningSeconds = 0
    /// The longest stretch in which nothing at all was heard WHILE LISTENING WAS
    /// SUPPOSED TO BE HAPPENING. THE number this card turns on — an interruption
    /// that killed the day shows up here and almost nowhere else.
    ///
    /// That second clause is the whole of it, in both directions. Hours of quiet
    /// after the owner turns listening off are correct behaviour and must never
    /// appear here; hours of quiet after a call took the microphone are the
    /// failure this card exists to end, and used to be invisible. The stop's
    /// cause is what separates them, and the journal already records it.
    var longestSilenceSeconds = 0

    /// How the record ENDS, at the moment it is read. No count can carry this,
    /// and it is the first thing a person needs: "you have it turned off" and
    /// "a call took the microphone at nine and it never came back" produce the
    /// same silence and want opposite reactions.
    enum Ending: Equatable {
        /// Not one session line in the record — both ends rotated away, or this
        /// phone has never listened. Reported rather than guessed at.
        case unknown
        /// A session was open when the record was read.
        case listening
        /// The owner turned it off. Quiet afterwards is the ordinary state of a
        /// phone nobody is talking to, not a finding.
        case stoppedByOwner
        /// Something took listening away and nothing brought it back. The
        /// silence since is the report.
        case stoppedByOther(cause: String)
    }
    var ending: Ending = .unknown

    /// Nothing has been heard for this long as of the moment the record was
    /// READ — not as of its last line, which on the day worth reading is the
    /// stop itself. Zero once the owner has listening turned off.
    var unheardForSeconds = 0

    var flushes = 0
    var wordsFlushed = 0
    /// Broken out because a `ceiling` flush is a thought cut in half by a clock,
    /// not a thought that ended. Its share is the honest read on how often she
    /// interrupts a sentence, and a single total hides it.
    var flushesByReason: [String: Int] = [:]

    var swaps = 0
    /// An error, Apple's task limit, a route change and the silence rotation
    /// need different fixes. "swaps: 12" would be useless.
    var swapsByCause: [String: Int] = [:]

    /// The owner stopping it and iOS taking the microphone away read
    /// identically in a total, and only one of them is a defect.
    var stopsByCause: [String: Int] = [:]

    /// Facts about the senses, in the order they were noted — what the audio
    /// session actually became, low power mode, audio dropped while swapping.
    /// Kept verbatim rather than re-parsed: they are already prose written for
    /// a person, and parsing our own sentences twice is how the writing and
    /// the reading drift apart.
    var notes: [String] = []

    /// WHAT LISTENING COST, and the window that cost was spent over. Both
    /// halves, always: "4%" with no window is not a measurement, and a rate is
    /// a division this screen has no business doing on the reader's behalf.
    ///
    /// Points the battery FELL while a session was open and the phone was off
    /// power. Signed deltas are summed, so a level that ticks up mid-stretch
    /// (recalibration; it happens) nets itself out instead of being clamped
    /// away in one direction and counted in the other. The TOTAL is floored at
    /// zero, because a report claiming the phone gained battery by listening is
    /// a report nobody will believe about anything else either.
    var batterySpentPoints = 0
    /// Seconds those points were spent over — the sum of the intervals between
    /// readings that were both inside one unbroken listening session, off
    /// power. Not the same as `listeningSeconds`, and deliberately smaller: a
    /// session with one reading in it brackets nothing and contributes none.
    var batteryMeasuredSeconds = 0
    /// Time inside a listening session with the phone on a charger. EXCLUDED
    /// from the two numbers above and reported anyway, so the exclusion is
    /// visible: a day spent plugged in otherwise reports a triumphantly small
    /// drain, and a day that charged in the middle of it reports a negative
    /// one.
    var batteryOnPowerSeconds = 0
    /// How many readings reached the record at all. THE DIFFERENCE BETWEEN
    /// "nothing was spent" AND "nothing was seen", which are the two things a
    /// zero here would otherwise mean at once. Zero is the simulator, a journal
    /// written by a build before this existed, and a phone where battery
    /// monitoring was never switched on.
    var batteryReadings = 0

    var postsAccepted = 0
    /// A day that heard everything and delivered nothing looks exactly like a
    /// microphone that heard nothing at all, from outside.
    var postsFailed = 0

    /// AIRTIME THE PENDANT'S RADIO LOST, summed over the day, in milliseconds.
    ///
    /// The one number that separates "the room was quiet" from "the link was
    /// dropping packets and the transcript has holes in it". Both produce a
    /// short transcript; only one of them is a defect, and until this existed
    /// the assembler measured the difference and then threw it away when the
    /// process ended.
    var airtimeLostMilliseconds = 0
    /// HOW MANY SEPARATE HOLES made up that total, which the total alone
    /// cannot say. Thirty seconds lost in one dropout is a radio that went out
    /// of range; the same thirty seconds spread over three hundred stutters is
    /// a link failing continuously in place. They want different fixes, and a
    /// single sum reads identically for both.
    var airtimeGaps = 0

    /// `now` is the moment the record is being READ, and it is the difference
    /// between an instrument and a decoration.
    ///
    /// On the day this type exists for, the journal's last line IS the failure:
    /// 09:00, a call took the microphone, iOS never delivered `.ended`, nothing
    /// restarted listening. There are no later events. A fold that measures to
    /// its own last line therefore answers "58 min" for a phone that has heard
    /// nothing since breakfast, and a reassuring wrong number is worse than no
    /// number, because it is believed.
    ///
    /// Passed in rather than read from `Date()` inside, so the fold stays a pure
    /// function of its inputs and every case below is checkable with `swiftc`
    /// alone. Defaulted to nil — the record then ends at its own last line, the
    /// behaviour every existing check means by "the end of the day".
    /// `Tests/run_tally_tests.sh` fails the build if the screen stops passing one.
    static func of(_ events: [(Date, ListenEvent)], now: Date? = nil) -> ListenTally {
        var tally = ListenTally()
        // Sorted here rather than assumed: the journal is written from two
        // threads and read back as a file that may have been rotated, so
        // arrival order is not a guarantee we own. An unsorted fold could
        // produce a negative duration, and a report that prints nonsense on the
        // one day it is needed is worse than no report.
        //
        // TIES ARE BROKEN, and the tiebreak is not decoration. This fold runs
        // through single-slot state (`openedAt`, `lastHeardAt`), so events
        // sharing a stamp are order-sensitive, and `sorted(by:)` is documented
        // as NOT stable — equal keys carry no defined order at all. Measured
        // before the stamps carried sub-seconds: the same three events folded to
        // `listening 0s` one way and `listening 43200s` the other. Sub-second
        // stamps make a real tie nearly impossible; `orderWithinAnInstant` makes
        // the answer defined anyway, because "nearly" is what the invariant is
        // about.
        let ordered = events.sorted {
            $0.0 == $1.0
                ? orderWithinAnInstant($0.1) < orderWithinAnInstant($1.1)
                : $0.0 < $1.0
        }
        guard let first = ordered.first else { return tally }

        var openedAt: Date? = nil
        // Silence is measured between anything HEARD, so a flush is the only
        // evidence that counts. A swap or a post proves the machinery moved,
        // not that a person spoke — and the failure being hunted is precisely a
        // machine that keeps ticking while hearing nothing.
        var lastHeardAt: Date = first.0
        // Whether the owner has listening switched OFF. The one condition under
        // which quiet is not a finding: nobody was listening, so nothing could
        // have been missed. It starts false because a journal whose start line
        // has rotated away is still a journal of a listening day, and guessing
        // "off" there would hide exactly the silence this type reports.
        var ownerHasItOff = false
        // The last reading recorded, and whether one unbroken listening session
        // has covered every instant since it. Both are needed: the interval
        // between two readings is only drain if nobody stopped listening in the
        // middle of it, and an overnight fall with the microphone off is not a
        // cost of listening. Attributing it would make this number a lie in the
        // one direction that matters, because it is the direction that makes
        // the product look expensive when it is not.
        var lastReading: (at: Date, percent: Int, onPower: Bool)? = nil
        var sessionUnbrokenSinceReading = false

        for (time, event) in ordered {
            switch event {
            case .sessionStarted:
                tally.sessions += 1
                // A new session is not evidence of speech, so the stretch that
                // ended here still counts. This is the interruption at 09:00
                // that nobody noticed until the app was opened at 18:00: nine
                // deaf hours with a start line on either side of them, which
                // the fold used to erase by simply resetting the clock.
                if !ownerHasItOff {
                    tally.longestSilenceSeconds = max(
                        tally.longestSilenceSeconds,
                        Int(time.timeIntervalSince(lastHeardAt)))
                }
                openedAt = time
                lastHeardAt = time
                ownerHasItOff = false
                tally.ending = .listening
                // A start breaks the span for the same reason a stop does: the
                // hole before it is time nobody was listening, and the readings
                // on either side of it cannot bracket it.
                sessionUnbrokenSinceReading = false

            case .sessionStopped(let cause):
                tally.stopsByCause[cause.rawValue, default: 0] += 1
                if let opened = openedAt {
                    tally.listeningSeconds += Int(time.timeIntervalSince(opened))
                    openedAt = nil
                }
                sessionUnbrokenSinceReading = false
                if cause == .owner {
                    // The owner was still listening right up to here, so the
                    // quiet before this stop counts — and the quiet after it
                    // does not.
                    tally.longestSilenceSeconds = max(
                        tally.longestSilenceSeconds,
                        Int(time.timeIntervalSince(lastHeardAt)))
                    lastHeardAt = time
                    ownerHasItOff = true
                    tally.ending = .stoppedByOwner
                } else {
                    // AND THE CLOCK KEEPS RUNNING. An interruption, a route
                    // change, a lost permission or a failure did not end the
                    // expectation that this phone is listening — it IS the
                    // failure, and the hours after it are the report. Moving
                    // `lastHeardAt` here is what answered "58 min" for a day
                    // that heard nothing after nine in the morning.
                    tally.ending = .stoppedByOther(cause: cause.rawValue)
                }

            case .flushed(let reason, let words):
                tally.flushes += 1
                tally.wordsFlushed += words
                tally.flushesByReason[reason.rawValue, default: 0] += 1
                if !ownerHasItOff {
                    tally.longestSilenceSeconds = max(
                        tally.longestSilenceSeconds,
                        Int(time.timeIntervalSince(lastHeardAt)))
                }
                lastHeardAt = time
                // Words arrived, so listening is plainly on whatever the
                // session lines did or did not survive rotation.
                ownerHasItOff = false

            case .recognizerSwapped(let cause):
                tally.swaps += 1
                tally.swapsByCause[cause.rawValue, default: 0] += 1

            case .batteryRead(let percent, let onPower):
                tally.batteryReadings += 1
                // THE INTERVAL IS DESCRIBED BY THE READING THAT OPENED IT, not
                // by this one. A reading is written when the level or the power
                // state CHANGES, so the reading that says "on power" is the one
                // taken the moment the cable went in — and the interval it
                // opens is the charged one.
                if let previous = lastReading,
                   sessionUnbrokenSinceReading, openedAt != nil {
                    let seconds = max(0, Int(time.timeIntervalSince(previous.at)))
                    if previous.onPower {
                        tally.batteryOnPowerSeconds += seconds
                    } else {
                        tally.batteryMeasuredSeconds += seconds
                        tally.batterySpentPoints += previous.percent - percent
                    }
                }
                lastReading = (at: time, percent: percent, onPower: onPower)
                sessionUnbrokenSinceReading = openedAt != nil
                // AND NOTHING ELSE MOVES. A reading is not evidence that anybody
                // spoke, so `lastHeardAt` stays where it is: the phone reporting
                // its own battery every few minutes through a call that took the
                // microphone would otherwise cut the day's one enormous silence
                // into pieces and delete the finding.

            // THE SENTENCE IS BUILT HERE, from a value, and that is the whole
            // difference. `notes` is still prose for a person to read, but no
            // call site hands prose in any more: what arrives is a
            // `ListenSessionFacts` (two closed enums and a Bool) or an Int, and
            // the words come from this file and `ListenSessionFacts.sentence`.
            case .sessionFacts(let facts):
                tally.notes.append(facts.sentence)

            case .buffersDropped(let count):
                tally.notes.append("dropped \(count) buffers while swapping")

            case .posted(let ok, _):
                if ok { tally.postsAccepted += 1 } else { tally.postsFailed += 1 }

            // DELIBERATELY DOES NOT TOUCH `lastHeardAt`. A gap is the opposite
            // of hearing: it is the record of a stretch in which nothing was
            // heard because nothing arrived. Counting it as evidence of
            // activity would let a failing radio hold `longestSilenceSeconds`
            // down by reporting its own failures — the instrument reassuring
            // itself with the very thing it exists to catch.
            case .airtimeLost(let milliseconds):
                tally.airtimeLostMilliseconds += milliseconds
                tally.airtimeGaps += 1
            }
        }

        // The record ends at the later of its own last line and the moment it is
        // being read. `max` rather than a bare `now`: a clock that has moved
        // backwards under us must not shorten the day, and a caller that passes
        // nothing gets the last line, which is what it always got.
        let lastLine = ordered.last?.0 ?? first.0
        let end = max(lastLine, now ?? lastLine)

        // A session still open when the record ends counts up to there. Dropping
        // it would erase the longest sessions, which are the ones a full day is
        // made of.
        if let opened = openedAt {
            tally.listeningSeconds += Int(end.timeIntervalSince(opened))
        }
        // NOT nested inside that, and the nesting was the bug. An interruption
        // is exactly what sets `openedAt` back to nil, so the trailing silence
        // of the one day this card is for was the one trailing silence never
        // measured. The RECOVERABLE failure (a session left open) reported
        // 10hr 58min correctly while the FATAL one reported 58 minutes.
        if !ownerHasItOff {
            tally.unheardForSeconds = max(0, Int(end.timeIntervalSince(lastHeardAt)))
            tally.longestSilenceSeconds = max(
                tally.longestSilenceSeconds, tally.unheardForSeconds)
        }

        // Clamp rather than trust. `max(0,)` costs nothing and makes a
        // nonsensical number impossible to print even if a clock moved
        // backwards under us.
        tally.listeningSeconds = max(0, tally.listeningSeconds)
        tally.longestSilenceSeconds = max(0, tally.longestSilenceSeconds)
        // Floored here rather than per interval. Clamping each delta would
        // count every fall in full and every rise as nothing, which biases a
        // day of ordinary battery jitter upward by a point or two an hour — an
        // invented drain, in the direction that makes listening look costly.
        tally.batterySpentPoints = max(0, tally.batterySpentPoints)
        return tally
    }

    /// Where an event sorts against another stamped at the same instant.
    ///
    /// The narrative order of one moment: a session starts, the machinery moves,
    /// words go out, and only then can it stop. Any total order would make the
    /// fold deterministic; this one also makes it right, because the alternative
    /// reading of `[started@T, stopped@T]` is a stop that precedes its own start
    /// and books twelve hours of listening that never happened.
    ///
    /// Exhaustive on purpose. A new `ListenEvent` case cannot land without a
    /// decision about where it sorts inside a shared instant.
    private static func orderWithinAnInstant(_ event: ListenEvent) -> String {
        switch event {
        case .sessionStarted: return "0"
        // Between a start and everything else: a reading stamped with the start
        // describes the session that is beginning, and a reading stamped with a
        // STOP is the last one that session gets — it must be folded before the
        // stop closes the span, or the final interval of every session is lost.
        // "." sorts below "1" and above "0", which is exactly that slot, and it
        // cannot collide with `sessionStarted`, whose key is the bare "0".
        case .batteryRead(let percent, let onPower): return "0.\(percent) \(onPower)"
        case .recognizerSwapped(let cause): return "1\(cause.rawValue)"
        case .flushed(let reason, let words): return "2\(words) \(reason.rawValue)"
        // `.noted` split into these two on 2026-08-25. Both keep the "3" slot
        // they shared, so a day recorded by an older build sorts against a
        // newer one the same way; the letter after it is what keeps two events
        // at one instant from colliding.
        case .sessionFacts(let facts): return "3a\(facts.sentence)"
        case .buffersDropped(let count): return "3b\(count)"
        // The same "3" slot as the two observational cases above, for the same
        // reason they share it: a day recorded by an older build sorts against
        // a newer one the same way. A gap is an observation about the link, not
        // a flush and not a stop, so it belongs beside them rather than
        // anywhere that would reorder hearing or session boundaries.
        case .airtimeLost(let milliseconds): return "3c\(milliseconds)"
        case .posted(let ok, let detail): return "4\(ok) \(detail.text)"
        case .sessionStopped(let cause): return "5\(cause.rawValue)"
        }
    }
}
