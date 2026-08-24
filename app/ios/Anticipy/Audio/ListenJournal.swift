import Foundation

/// What a listening session actually did, in plain lines a person can read.
///
/// The incident this exists for, 2026-08-24: a manual voice test came back as
/// "the test didn't complete" and there was nothing to read. There was no
/// `print`, `NSLog`, `os_log` or `Logger` anywhere in `PhoneListener.swift` or
/// `AnticipyApp.swift`, so the microphone, the recognizer, the flush, the
/// network and the brain were indistinguishable as suspects and none of them
/// could be ruled out. Every manual session was a guess.
///
/// Pure Foundation on purpose, like `TranscriptFlushPolicy`: no AVFoundation,
/// no Speech, no UI. The checks in `Tests/ListenJournalTests.swift` exercise
/// THIS code with `swiftc` alone, with no simulator, signing or network, so the
/// instrument used to judge the audio path is itself verifiable.
///
/// What it deliberately does not hold: no audio, ever, and no transcript text.
/// A flush is recorded as a word COUNT. The events collection already holds the
/// owner's speech, and a second copy of it sitting in a diagnostic log is a
/// privacy regression under `design/LOCAL-FIRST.md`.
enum ListenEvent: Equatable {
    case sessionStarted
    case sessionStopped(cause: StopCause)
    case recognizerSwapped(cause: SwapCause)
    case flushed(reason: String, words: Int)
    case posted(ok: Bool, detail: String)

    enum StopCause: String, Equatable {
        case owner, interruption, routeChange, authorizationLost, unrecoveredFailure
    }
    enum SwapCause: String, Equatable {
        case error, taskLimit, routeChange, silenceRotation
    }
}

final class ListenJournal {
    static let shared = ListenJournal()

    /// `record` is called from the audio thread and from the main queue. An
    /// unsynchronised array here would be a crash in the one code path whose
    /// job is to explain crashes. Same serialization VoiceRoster uses.
    private let queue = DispatchQueue(label: "ai.anticipy.listenjournal")

    /// A ring, so a long session overwrites its own oldest line in place
    /// instead of growing without end. `backend/start.sh` exists in this repo
    /// because a disposable log database filled a volume and took production
    /// down; an unbounded journal on a phone is the same mistake at smaller
    /// scale. When it is full the newest events win, because those are the ones
    /// that explain the failure being investigated.
    private var ring: [String]
    private var cursor = 0
    private var wrapped = false
    private let limit: Int

    private let stamp: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    init(limit: Int = 400) {
        // A journal with no room is a journal that reports nothing, which is
        // the exact condition this class was written to end.
        self.limit = max(1, limit)
        ring = []
        ring.reserveCapacity(self.limit)
    }

    func record(_ event: ListenEvent, at time: Date = Date()) {
        let described = Self.describe(event)
        // The formatter is journal state like the ring is, so it is read under
        // the same lock. A shared Formatter touched from the audio thread and
        // the main queue at once is the sort of fault that would only ever show
        // up in the diagnostic that was supposed to explain the fault.
        queue.sync {
            let line = "\(stamp.string(from: time))  \(described)"
            if ring.count < limit {
                ring.append(line)
            } else {
                ring[cursor] = line
                wrapped = true
            }
            cursor = (cursor + 1) % limit
        }
    }

    /// Oldest first. A journal read newest-first buries the start of the
    /// session, which is where a session that failed has to be read from.
    var entries: [String] {
        queue.sync {
            guard wrapped else { return ring }
            return Array(ring[cursor...]) + Array(ring[..<cursor])
        }
    }

    func clear() {
        queue.sync {
            ring.removeAll(keepingCapacity: true)
            cursor = 0
            wrapped = false
        }
    }

    /// One line per event. The case name is present so a line is greppable, and
    /// the cause or trigger is spelled out because "it stopped" is the useless
    /// half of the report.
    private static func describe(_ event: ListenEvent) -> String {
        switch event {
        case .sessionStarted:
            return "sessionStarted  listening began"
        case .sessionStopped(let cause):
            return "sessionStopped  listening ended, cause: \(cause.rawValue)"
        case .recognizerSwapped(let cause):
            return "recognizerSwapped  a fresh recognizer took over, cause: \(cause.rawValue)"
        case .flushed(let reason, let words):
            return "flushed  \(words) words sent, reason: \(reason)"
        case .posted(let ok, let detail):
            let outcome = ok ? "accepted" : "failed"
            return detail.isEmpty
                ? "posted  \(outcome)"
                : "posted  \(outcome), \(detail)"
        }
    }
}
