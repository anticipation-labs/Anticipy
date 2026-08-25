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
    /// A fact about the SENSES — what the audio session actually became, what
    /// the power mode is, how much audio was dropped. Never speech, and never
    /// anything derived from speech: the same rule `posted`'s detail carries,
    /// for the same reason. This exists because three `try?` calls configure
    /// the audio session and swallow every failure, so the app can report
    /// "Listening" over a session it never got.
    case noted(String)
    /// WHAT LISTENING COSTS, in the only unit the phone can give for free.
    ///
    /// A percentage and whether the phone was on a charger — never a verdict
    /// about either. Nothing in this product had ever measured the draw of an
    /// always-on microphone, a speech recognizer and a 4-second timer, so the
    /// two costs removed tonight (a call minting a recognizer every four
    /// seconds, and this journal writing fifteen identical lines a minute) were
    /// both argued about with no number attached.
    ///
    /// A TYPED CASE RATHER THAN A `.noted` SENTENCE, deliberately. `ListenTally`
    /// keeps notes verbatim because they are prose written for a person, and
    /// parsing our own sentences twice is how the writing and the reading drift
    /// apart. This has to be FOLDED — subtracted from the reading before it —
    /// so it arrives as two values the compiler can keep honest, and the round
    /// trip through `describe`/`parse` is a check rather than a hope.
    ///
    /// Ints and a Bool, so no wording of the owner's can ever reach it: this is
    /// the one journal payload whose privacy argument is its type.
    case batteryRead(percent: Int, onPower: Bool)

    enum StopCause: String, Equatable {
        case owner, interruption, routeChange, authorizationLost, unrecoveredFailure
    }
    enum SwapCause: String, Equatable {
        case error, taskLimit, routeChange, silenceRotation
        /// The owner opened the app and the microphone was taken back.
        ///
        /// Its own case rather than `.routeChange` because the route did not
        /// change — a call held the input, iOS suspended the app, and nothing
        /// brought listening back until somebody looked at their phone. That
        /// distinction is the finding: this count answers "how often did she
        /// only come back because he opened the app?", which is the honest
        /// measure of how much of the interruption hole is still open.
        case appReturned
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
    /// Readable so Settings can hand the file to a ShareLink. The screen that
    /// does that is what makes this class's own 'exportable from Settings'
    /// comments true.
    let fileURL: URL?
    private let rotateAtBytes: Int

    /// MILLISECONDS, and they are load-bearing rather than tidy.
    /// `[.withInternetDateTime]` alone has no fractional part, so two lines
    /// written 0.8s apart parsed back to the SAME instant. `ListenTally.of`
    /// folds through single-slot state and `sorted(by:)` is documented as not
    /// stable, so a tie carried no defined order at all — and the measured cost
    /// of one tie between a start and a stop was twelve hours of listening
    /// appearing out of nowhere.
    private static let stamp: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    /// Two readers, because a phone updating to this build has a journal full of
    /// stamps written by the old one, and the day worth reading is usually the
    /// day before the update. A reader that only understood the new shape would
    /// drop every one of those lines and report a blank, healthy day — which is
    /// the exact failure this whole file exists to make impossible.
    ///
    /// Static, unlike the per-line formatters this replaced. `persistedEvents`
    /// runs over every line on disk — thousands of them on a bad day — and
    /// building two `ISO8601DateFormatter`s per line was paid by the one screen
    /// somebody opens when their phone has stopped working.
    private static let readerWithMillis: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    private static let readerWithoutMillis: ISO8601DateFormatter = {
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
            let line = "\(Self.stamp.string(from: time))  \(described)"
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

    /// The day as typed events, so a tally can be folded over a record that
    /// OUTLIVED THE PROCESS — which is the whole point, because the day worth
    /// reading is usually the one that ended when the app did.
    ///
    /// This parses our own format, which is plumbing rather than meaning: the
    /// case name is the second field precisely because `describe` was written
    /// to be greppable. The risk is drift between writing and reading, and the
    /// drift is silent — a reworded line still looks fine to a person and simply
    /// stops counting.
    ///
    /// `ListenJournalTests` round-trips every case through describe and back,
    /// over `ListenEvent.everyCase` — which the COMPILER keeps every. Adding a
    /// case to `ListenEvent` stops that file compiling until the case has been
    /// given a sample, and the sample then has to survive the trip. The array
    /// literal it replaced could not do that: `parse` ends in
    /// `default: return nil`, so a new case's every line was dropped here in
    /// silence while the gate stayed green.
    var persistedEvents: [(Date, ListenEvent)] {
        persistedLines.compactMap(Self.parse)
    }

    static func parse(_ line: String) -> (Date, ListenEvent)? {
        let parts = line.components(separatedBy: "  ")
        guard parts.count >= 2 else { return nil }
        guard let when = readerWithMillis.date(from: parts[0])
                ?? readerWithoutMillis.date(from: parts[0]) else { return nil }
        let body = parts.dropFirst().joined(separator: "  ")
        guard let name = body.split(separator: " ").first.map(String.init)
        else { return nil }

        func after(_ marker: String) -> String? {
            guard let r = body.range(of: marker) else { return nil }
            return String(body[r.upperBound...])
                .trimmingCharacters(in: .whitespaces)
        }

        switch name {
        case "sessionStarted":
            return (when, .sessionStarted)
        case "sessionStopped":
            guard let raw = after("cause: "),
                  let cause = ListenEvent.StopCause(rawValue: raw) else { return nil }
            return (when, .sessionStopped(cause: cause))
        case "recognizerSwapped":
            guard let raw = after("cause: "),
                  let cause = ListenEvent.SwapCause(rawValue: raw) else { return nil }
            return (when, .recognizerSwapped(cause: cause))
        case "flushed":
            guard let reason = after("reason: "),
                  let words = body.split(separator: " ").dropFirst().first
                      .flatMap({ Int($0) }) else { return nil }
            return (when, .flushed(reason: reason, words: words))
        case "batteryRead":
            // The FIELDS, never a substring of the line — the lesson `posted`
            // paid for, where `body.contains("accepted")` read a delivery
            // failure back as a success. "yes"/"no" and nothing else: an
            // unreadable power state makes the whole reading unusable, because
            // it is what decides whether the interval after it counts as drain.
            guard let percent = body.split(separator: " ").dropFirst().first
                    .flatMap({ Int($0) }),
                  let power = after("on power: "),
                  power == "yes" || power == "no" else { return nil }
            return (when, .batteryRead(percent: percent, onPower: power == "yes"))
        case "noted":
            let fact = body.dropFirst("noted".count).trimmingCharacters(in: .whitespaces)
            return (when, .noted(fact))
        case "posted":
            // THE OUTCOME FIELD, never a substring of the line. This was
            // `body.contains("accepted")`, and a detail is free-form prose, so
            // `posted(ok: false, detail: "not accepted by proxy")` read back as
            // `posted(ok: true, detail: "by proxy")` — a delivery failure
            // reporting itself as a success on the screen whose whole job is to
            // tell a day that heard nothing from a day that delivered nothing.
            let rest = parts.dropFirst().joined(separator: "  ")
                .dropFirst(name.count).trimmingCharacters(in: .whitespaces)
            let outcome = String(rest.prefix(while: { $0 != "," }))
            guard outcome == "accepted" || outcome == "failed" else { return nil }
            let detail = String(rest.dropFirst(outcome.count))
                .trimmingCharacters(in: CharacterSet(charactersIn: ", "))
            return (when, .posted(ok: outcome == "accepted", detail: detail))
        default:
            return nil
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
        case .noted(let fact):
            return "noted  \(fact)"
        case .batteryRead(let percent, let onPower):
            return "batteryRead  \(percent) percent, on power: \(onPower ? "yes" : "no")"
        case .posted(let ok, let detail):
            let outcome = ok ? "accepted" : "failed"
            return detail.isEmpty
                ? "posted  \(outcome)"
                : "posted  \(outcome), \(detail)"
        }
    }
}
