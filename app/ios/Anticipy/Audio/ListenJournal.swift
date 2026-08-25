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
    /// `detail` is a status or an error shape, never transcript text. The
    /// tempting values at the call site are the wrong ones: `BackendError`
    /// carries the server's own sentence, and a PocketBase error body is built
    /// from a request whose payload includes the owner's speech. Spec section 9
    /// makes this journal exportable from Settings, so anything put here leaves
    /// the phone on a person's tap. A status code, a queue state or an error
    /// name is what belongs; the words the owner said never do.
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

    /// The ring dies with the process, and the failure most worth reading is
    /// usually the one that killed it — a battery death mid-errand, iOS
    /// reclaiming the app, a crash. 400 lines is roughly forty minutes; a day
    /// of listening is not. So the same line also goes to a file.
    ///
    /// Two files and no more, rotated, for the reason the ring is bounded:
    /// `backend/start.sh` exists in this repo because a disposable log filled a
    /// volume and took production down. On a phone that would be someone's
    /// storage instead, which is worse, because they cannot see why.
    private let fileURL: URL?
    private let rotateAtBytes: Int

    private let stamp: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    init(limit: Int = 400, fileURL: URL? = nil, rotateAtBytes: Int = 256 * 1024) {
        // A journal with no room is a journal that reports nothing, which is
        // the exact condition this class was written to end.
        self.limit = max(1, limit)
        self.rotateAtBytes = max(1, rotateAtBytes)
        self.fileURL = fileURL ?? Self.defaultFileURL()
        ring = []
        ring.reserveCapacity(self.limit)
    }

    func record(_ event: ListenEvent, at time: Date = Date()) {
        let described = Self.describe(event)
        // ASYNC, AND THAT IS THE POINT. This is called from the audio thread —
        // the same thread that must keep handing buffers to the recognizer —
        // and it now touches a FILE. A `sync` hop here would park audio behind
        // a disk write, so the instrument built to explain dropped speech would
        // become a way to drop speech. Ordering is not lost: the queue is
        // serial, and every reader below enters it the same way, so a read
        // always drains the writes issued before it.
        queue.async { [self] in
            let line = "\(stamp.string(from: time))  \(described)"
            if ring.count < limit {
                ring.append(line)
            } else {
                ring[cursor] = line
                wrapped = true
            }
            cursor = (cursor + 1) % limit
            appendToFile(line)
        }
    }

    /// Everything on disk, oldest first, across the rotation boundary — the
    /// rotated half first, then the live one. Same ordering rule as `entries`
    /// and for the same reason: a session that failed is read from its start.
    var persistedLines: [String] {
        queue.sync {
            guard let url = fileURL else { return [] }
            let older = (try? String(contentsOf: url.appendingPathExtension("1"),
                                     encoding: .utf8)) ?? ""
            let live = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
            return (older + live)
                .split(separator: "\n", omittingEmptySubsequences: true)
                .map(String.init)
        }
    }

    /// Called only from inside `queue`, so the file is single-writer.
    private func appendToFile(_ line: String) {
        guard let url = fileURL else { return }
        let data = Data((line + "\n").utf8)
        guard let handle = try? FileHandle(forWritingTo: url) else {
            // No file yet, or it cannot be opened at all. Creating it is the
            // ordinary first-write case; a failure is NOT worth escalating,
            // because a diagnostic that needs disk to function is useless on
            // the device that has just run out of it. The ring still holds
            // this line either way.
            try? data.write(to: url, options: .atomic)
            return
        }
        defer { try? handle.close() }
        _ = try? handle.seekToEnd()
        try? handle.write(contentsOf: data)
        rotateIfNeeded(url)
    }

    /// Rotate AFTER the write, never before: a line is never held back waiting
    /// for a rotation, so the newest line is always in the newest file.
    private func rotateIfNeeded(_ url: URL) {
        let size = (try? FileManager.default
            .attributesOfItem(atPath: url.path)[.size] as? Int).flatMap { $0 } ?? 0
        guard size >= rotateAtBytes else { return }
        let rolled = url.appendingPathExtension("1")
        try? FileManager.default.removeItem(at: rolled)
        try? FileManager.default.moveItem(at: url, to: rolled)
    }

    private static func defaultFileURL() -> URL? {
        guard let dir = try? FileManager.default.url(
            for: .applicationSupportDirectory, in: .userDomainMask,
            appropriateFor: nil, create: true) else { return nil }
        return dir.appendingPathComponent("listen-journal.log")
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
            // The files go too. A person who clears the journal and still has
            // a copy of it on disk was not told the truth about what clearing
            // means, and this is the one screen that promises exportability.
            if let url = fileURL {
                try? FileManager.default.removeItem(at: url)
                try? FileManager.default.removeItem(at: url.appendingPathExtension("1"))
            }
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
