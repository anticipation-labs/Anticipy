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
    /// The longest stretch in which nothing at all was heard. THE number this
    /// card turns on — an interruption that killed the day shows up here and
    /// almost nowhere else.
    var longestSilenceSeconds = 0

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

    var postsAccepted = 0
    /// A day that heard everything and delivered nothing looks exactly like a
    /// microphone that heard nothing at all, from outside.
    var postsFailed = 0

    static func of(_ events: [(Date, ListenEvent)]) -> ListenTally {
        var tally = ListenTally()
        // Sorted here rather than assumed: the journal is written from two
        // threads and read back as a file that may have been rotated, so
        // arrival order is not a guarantee we own. An unsorted fold could
        // produce a negative duration, and a report that prints nonsense on the
        // one day it is needed is worse than no report.
        let ordered = events.sorted { $0.0 < $1.0 }
        guard let first = ordered.first else { return tally }

        var openedAt: Date? = nil
        // Silence is measured between anything HEARD, so a flush is the only
        // evidence that counts. A swap or a post proves the machinery moved,
        // not that a person spoke — and the failure being hunted is precisely a
        // machine that keeps ticking while hearing nothing.
        var lastHeardAt: Date = first.0

        for (time, event) in ordered {
            switch event {
            case .sessionStarted:
                tally.sessions += 1
                openedAt = time
                // A new session is not evidence of speech, but it does end the
                // silence being measured: nobody was listening, so nothing
                // could have been missed.
                lastHeardAt = time

            case .sessionStopped(let cause):
                tally.stopsByCause[cause.rawValue, default: 0] += 1
                if let opened = openedAt {
                    tally.listeningSeconds += Int(time.timeIntervalSince(opened))
                    openedAt = nil
                }
                tally.longestSilenceSeconds = max(
                    tally.longestSilenceSeconds,
                    Int(time.timeIntervalSince(lastHeardAt)))
                lastHeardAt = time

            case .flushed(let reason, let words):
                tally.flushes += 1
                tally.wordsFlushed += words
                tally.flushesByReason[reason, default: 0] += 1
                tally.longestSilenceSeconds = max(
                    tally.longestSilenceSeconds,
                    Int(time.timeIntervalSince(lastHeardAt)))
                lastHeardAt = time

            case .recognizerSwapped(let cause):
                tally.swaps += 1
                tally.swapsByCause[cause.rawValue, default: 0] += 1

            case .posted(let ok, _):
                if ok { tally.postsAccepted += 1 } else { tally.postsFailed += 1 }
            }
        }

        // A session still open when the record ends counts up to the last thing
        // that happened. Dropping it would erase the longest sessions, which
        // are the ones a full day is made of.
        if let opened = openedAt, let last = ordered.last?.0 {
            tally.listeningSeconds += Int(last.timeIntervalSince(opened))
            tally.longestSilenceSeconds = max(
                tally.longestSilenceSeconds,
                Int(last.timeIntervalSince(lastHeardAt)))
        }

        // Clamp rather than trust. `max(0,)` costs nothing and makes a
        // nonsensical number impossible to print even if a clock moved
        // backwards under us.
        tally.listeningSeconds = max(0, tally.listeningSeconds)
        tally.longestSilenceSeconds = max(0, tally.longestSilenceSeconds)
        return tally
    }
}
