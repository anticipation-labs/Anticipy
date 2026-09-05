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
///
/// -- NO PAYLOAD HERE IS A `String`, AND THAT IS THE WHOLE PRIVACY ARGUMENT --
///
/// It used to be a scan's job. `ListenEvent` declared three free-form String
/// channels — `flushed(reason:)`, `posted(detail:)` and `noted(_:)` — and
/// `run_journal_tests.sh` proved, expression by expression, that nothing
/// carrying speech reached any of them. Five hardening passes did that, and
/// each one closed its findings and leaked at a new layer: two leaks, then
/// four, then two, then EIGHT (`.superpowers/sdd/privacy-gate-fifth.md`). Every
/// attack aimed at a RULE bounced — thirteen of them. What kept giving way was
/// the finder, the derivation and the allowlist: whatever decided WHAT THE
/// RULES RAN ON.
///
/// The one thing that held completely, under five separate attacks, was a TYPE:
/// `ListenSessionFacts` could not be made to hold a transcript because `+=`,
/// `.append` and a tuple assignment do not compile against it. So the journal
/// is now typed the whole way down. Every payload below is an `Int`, a `Bool`,
/// or a closed enum this file declares; the words on disk are written by
/// `describe`, from case names chosen here. There is no channel to put a
/// sentence into, so there is nothing left for a scan to have to catch.
///
/// `run_journal_tests.sh` still checks — but what it checks is that this
/// property HOLDS: `journal_payloads.py` walks every payload type recursively
/// and fails on the first one that is not closed. A `String` added back to any
/// case below turns that leg red, and it fails on a type it cannot classify
/// rather than skipping it, which is the inversion that let four payload
/// spellings through before.
enum ListenEvent: Equatable {
    case sessionStarted
    case sessionStopped(cause: StopCause)
    case recognizerSwapped(cause: SwapCause)
    /// Which timer cut these words, and how many of them went out. The COUNT,
    /// never the words.
    case flushed(reason: FlushReason, words: Int)
    /// Whether a line reached the server, and the SHAPE of what happened —
    /// never a sentence. The tempting values at the call site are the wrong
    /// ones: `BackendError` carries the server's own sentence, and a PocketBase
    /// error body is built from a request whose payload includes the owner's
    /// speech. Spec section 9 makes this journal exportable from Settings, so
    /// anything put here leaves the phone on a person's tap. `PostDetail` is
    /// what makes "a status code, never the words" a compiler rule instead of
    /// a comment.
    case posted(ok: Bool, detail: PostDetail)
    /// WHAT THE AUDIO SESSION ACTUALLY BECAME. Three `try?` calls configure it
    /// and swallow every failure, so the app can report "Listening" over a
    /// session it never got.
    ///
    /// This was `.noted(facts.sentence)` — a free String payload holding a
    /// rendered sentence — and the sentence was vouched for by an allowlist
    /// entry that a fifth-pass reviewer walked straight past (`f + acts.sentence`
    /// reduces to the allowlisted `facts.sentence` once `glue()` strips the
    /// `+`). Carrying the VALUE and rendering it in `describe` removes the
    /// allowlist entry and the expression that abused it.
    case sessionFacts(ListenSessionFacts)
    /// Audio the tap could not hand to a request, coalesced into one line by
    /// the watchdog that drains the counter.
    ///
    /// Also `.noted(...)` until 2026-08-25, interpolating a count the gate
    /// allowlisted as `self.orphanDropped` WITH NO TYPE CHECK — it was an `Int`
    /// by convention only, and flipping it to `String` put the transcript
    /// through the whole allowlisted chain. `count: Int` is that check, made by
    /// the compiler.
    case buffersDropped(count: Int)
    /// WHAT LISTENING COSTS, in the only unit the phone can give for free.
    ///
    /// A percentage and whether the phone was on a charger — never a verdict
    /// about either. Nothing in this product had ever measured the draw of an
    /// always-on microphone, a speech recognizer and a 4-second timer, so the
    /// two costs removed tonight (a call minting a recognizer every four
    /// seconds, and this journal writing fifteen identical lines a minute) were
    /// both argued about with no number attached.
    ///
    /// A TYPED CASE RATHER THAN A `.noted` SENTENCE, and the first one here to
    /// be written that way. It has to be FOLDED — subtracted from the reading
    /// before it — so it arrives as two values the compiler can keep honest,
    /// and the round trip through `describe`/`parse` is a check rather than a
    /// hope. Every case above now follows it.
    case batteryRead(percent: Int, onPower: Bool)
    /// AIRTIME THE RADIO LOST, in whole milliseconds.
    ///
    /// The pendant's packet index is the only loss-detection mechanism in the
    /// whole link: a client that sees the counter jump knows audio vanished and
    /// has no way to ask for it again. `OpusFrameAssembler` already does that
    /// arithmetic and hands the total to `recordPendantGap`, which put a marker
    /// on the feed and nowhere else — so a pendant that lost a minute lost it
    /// in memory, and the loss died with the process. Nothing off the phone,
    /// and nothing after a relaunch, could see it.
    ///
    /// MILLISECONDS AS AN `Int`, not seconds as a `Double`, and that is not
    /// fussiness. `describe`/`parse` is a round trip through text, and a
    /// `Double` goes through it lossily and locale-sensitively — a decimal
    /// comma reads back as a different number or as nothing. The wire is
    /// integral anyway: one packet is 160 samples at 16 kHz, exactly 10 ms, so
    /// every gap this can ever carry is a whole number of packets times ten.
    /// The exact unit is available for free, so the lossy one is a choice
    /// nobody has to make.
    ///
    /// NOT a `sessionStopped`, and the distinction is the reason this case
    /// exists rather than reusing one. A hole in the audio is not the end of a
    /// session, and journaling it as one would inflate the stop counts the
    /// tally uses to tell "the owner turned it off" from "a call took the
    /// microphone and nothing came back" — hiding the stops that were real
    /// behind holes that were not.
    case airtimeLost(milliseconds: Int)
    /// LINES THE PHONE GAVE UP ON, because the unsent queue was full.
    ///
    /// Distinct from `posted(ok: false, …)`, which is a line that FAILED to
    /// send and is still queued for another try. This is the terminal one: the
    /// words were heard, were never delivered, and are now gone. Nothing will
    /// retry them, because there is no longer anything to retry.
    ///
    /// It exists because the alternative to writing this number down is a
    /// bounded queue that discards in silence, which is a smaller copy of the
    /// bug bounding it was meant to fix. The count, never the words — same rule
    /// as every case above.
    case speechDropped(count: Int)

    enum StopCause: String, Equatable {
        case owner, interruption, routeChange, authorizationLost, unrecoveredFailure
    }

    /// Why a flush fired.
    ///
    /// `gap`, `ceiling` and `final` are `TranscriptFlushPolicy.Reason`; `banked`
    /// is the caller's word for "no policy asked for this one". Declared here
    /// rather than imported because this file must compile under `swiftc` with
    /// nothing but `ListenSessionFacts.swift` beside it — that standalone
    /// compile is what makes the instrument used to judge the audio path itself
    /// verifiable.
    ///
    /// It was `reason: String` and the call site passed `reason?.rawValue`. The
    /// derivation that was supposed to notice it did not: `reason:` was a third
    /// free-form String nobody had listed, and `reason: line` beside a word
    /// count of that same line exited 0.
    enum FlushReason: String, Equatable, CaseIterable {
        case gap, ceiling, final
        /// No policy asked; the words were banked at a stop.
        case banked

        /// From `TranscriptFlushPolicy.Reason?.rawValue`, which is the only
        /// caller. An unknown word banks rather than inventing a reason — and
        /// cannot be recorded as itself, which is the point.
        init(policyRawValue: String?) {
            self = policyRawValue.flatMap(FlushReason.init(rawValue:)) ?? .banked
        }
    }

    /// WHICH EARS heard the line, in the wire spelling the phone stamps on the
    /// event row (`AnticipySession.LineSource.wireName`, and the constants
    /// `CaptureSourcePolicy` matches against). `run_journal_tests.sh` checks
    /// those three spellings still agree with these, because a rename that
    /// slipped would land every line here as `unrecognised` in silence.
    enum Origin: String, Equatable, CaseIterable {
        case typed
        case phoneMic = "phone_mic"
        case pendant
        case unrecognised

        init(wireName: String) {
            self = Origin(rawValue: wireName) ?? .unrecognised
        }
    }

    /// WHAT WENT WRONG, as a shape. Never a message: `BackendError` carries the
    /// server's own sentence, and a PocketBase error body is built from a
    /// request whose payload is the words the owner just said.
    enum PostFailure: Equatable {
        /// The server refused, with its status.
        case http(status: Int)
        /// Anything else, as an `NSError`'s domain and code.
        case system(domain: ErrorDomain, code: Int)
    }

    /// The `NSError` domains this app can actually produce, as a closed set.
    ///
    /// `NSError.domain` is an arbitrary `String` handed to us by Foundation, so
    /// passing it through verbatim would put a free String channel back on this
    /// enum for the sake of five known constants. Anything outside them records
    /// as `other`: the code still identifies the failure, and no string that
    /// arrived from outside this file reaches the disk.
    enum ErrorDomain: String, Equatable, CaseIterable {
        case url = "NSURLErrorDomain"
        case cocoa = "NSCocoaErrorDomain"
        case posix = "NSPOSIXErrorDomain"
        case osStatus = "NSOSStatusErrorDomain"
        case mach = "NSMachErrorDomain"
        case other

        init(name: String) { self = ErrorDomain(rawValue: name) ?? .other }
    }

    /// What happened to a line on its way to the server.
    enum PostDetail: Equatable {
        /// It went up live, from this ear.
        case sentLive(from: Origin)
        /// One that had been waiting on disk went up — and from which ear it
        /// was heard, because the queue kept that and the journal used to
        /// drop it here. Without it, a per-ear count of the day's lines was
        /// honest only on a day with no outage: every line delivered late
        /// vanished from whichever ear had heard it, and a day the pendant
        /// spent mostly offline read as a day the pendant barely spoke.
        case sentFromQueue(from: Origin)
        /// A push failed and the line went to disk. `again` distinguishes a
        /// live push that got queued from a queued one that got requeued —
        /// the difference between "the network just went" and "it is still
        /// gone", which is the whole reading of a bad day.
        case shelved(again: Bool, failure: PostFailure)
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

extension ListenEvent.PostFailure {
    /// The words this shape goes to disk as, and the ONLY place they are
    /// chosen. Both sides are here so a reworded line and its reader move
    /// together; `ListenJournalTests` round-trips every one of them.
    var text: String {
        switch self {
        case .http(let status): return "http \(status)"
        case .system(let domain, let code): return "\(domain.rawValue) \(code)"
        }
    }

    init?(text: String) {
        let fields = text.split(separator: " ")
        guard fields.count == 2, let number = Int(fields[1]) else { return nil }
        if fields[0] == "http" { self = .http(status: number); return }
        guard let domain = ListenEvent.ErrorDomain(rawValue: String(fields[0]))
        else { return nil }
        self = .system(domain: domain, code: number)
    }
}

extension ListenEvent.PostDetail {
    var text: String {
        switch self {
        case .sentLive(let from): return from.rawValue
        case .sentFromQueue(let from): return "queued line sent, from: \(from.rawValue)"
        case .shelved(let again, let failure):
            return (again ? "requeued, " : "queued, ") + failure.text
        }
    }

    init?(text: String) {
        // The line as builds before 2026-09-05 wrote it, with no ear on it.
        // Read back as `.unrecognised` rather than refused: a journal full of
        // last week's queued sends is still a journal of last week, and the
        // per-ear fold reports those lines under "ear not recorded", which is
        // the truth about them.
        if text == "queued line sent" { self = .sentFromQueue(from: .unrecognised); return }
        if text.hasPrefix("queued line sent, from: ") {
            // `Origin(rawValue:)`, not `Origin(wireName:)`, for the reason
            // `.sentLive` gives below: an unknown word must not parse as if
            // `describe` had written it.
            guard let origin = ListenEvent.Origin(
                    rawValue: String(text.dropFirst("queued line sent, from: ".count)))
            else { return nil }
            self = .sentFromQueue(from: origin)
            return
        }
        for (prefix, again) in [("requeued, ", true), ("queued, ", false)]
        where text.hasPrefix(prefix) {
            guard let failure = ListenEvent.PostFailure(
                    text: String(text.dropFirst(prefix.count))) else { return nil }
            self = .shelved(again: again, failure: failure)
            return
        }
        // A wire name and nothing else. `Origin(rawValue:)` rather than
        // `Origin(wireName:)`: reading an unknown word back as `.unrecognised`
        // would let a line that was never written by `describe` parse as if it
        // had been, and the round-trip check is the only thing keeping the
        // writing and the reading from drifting apart.
        guard let origin = ListenEvent.Origin(rawValue: text) else { return nil }
        self = .sentLive(from: origin)
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
            // The reason is read back as a CASE, so a line whose reason is not
            // one of the four this build can write is dropped rather than
            // carried. A free `String` here is what let `reason: line` — the
            // whole utterance, beside a word count of that same utterance —
            // reach disk and read back as if it had always belonged.
            guard let raw = after("reason: "),
                  let reason = ListenEvent.FlushReason(rawValue: raw),
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
        case "airtimeLost":
            // The FIELD, like `batteryRead` above, never a substring of the
            // line. A negative count is refused rather than carried: airtime
            // cannot be un-lost, and a negative here would subtract from the
            // day's total and quietly make a real loss look smaller.
            guard let ms = body.split(separator: " ").dropFirst().first
                    .flatMap({ Int($0) }), ms >= 0 else { return nil }
            return (when, .airtimeLost(milliseconds: ms))
        case "speechDropped":
            // Refused below one for the same reason `airtimeLost` refuses a
            // negative: this event only ever means "words were lost", and a
            // zero or negative would subtract from the day's total and make a
            // real loss read as smaller than it was.
            guard let n = body.split(separator: " ").dropFirst().first
                    .flatMap({ Int($0) }), n > 0 else { return nil }
            return (when, .speechDropped(count: n))
        case "sessionFacts":
            // Read back through the same type that wrote it, so the writer and
            // the reader cannot drift: `ListenSessionFacts` owns both halves,
            // and an unknown category or mode fails the line rather than being
            // kept as itself.
            let sentence = body.dropFirst(name.count)
                .trimmingCharacters(in: .whitespaces)
            guard let facts = ListenSessionFacts(sentence: sentence) else { return nil }
            return (when, .sessionFacts(facts))
        case "buffersDropped":
            guard let count = body.split(separator: " ").dropFirst().first
                    .flatMap({ Int($0) }) else { return nil }
            return (when, .buffersDropped(count: count))
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
            let tail = String(rest.dropFirst(outcome.count))
                .trimmingCharacters(in: CharacterSet(charactersIn: ", "))
            guard let detail = ListenEvent.PostDetail(text: tail) else { return nil }
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
    ///
    /// THE ONLY PLACE THE JOURNAL CHOOSES WORDS. Every payload reaching here is
    /// an `Int`, a `Bool` or a closed enum, so every sentence on disk is one
    /// this file wrote. `run_journal_tests.sh` reads this body and requires
    /// each value it names to be one its own `case` arm bound — a stored
    /// property, a static, or anything else reachable from outside is a red
    /// leg, because that is the shape the fifth-pass review used: a
    /// `var lastTail` on `ListenJournal`, set from a call site the finder never
    /// looked at, rendered into a line from right here.
    private static func describe(_ event: ListenEvent) -> String {
        switch event {
        case .sessionStarted:
            return "sessionStarted  listening began"
        case .sessionStopped(let cause):
            return "sessionStopped  listening ended, cause: \(cause.rawValue)"
        case .recognizerSwapped(let cause):
            return "recognizerSwapped  a fresh recognizer took over, cause: \(cause.rawValue)"
        case .flushed(let reason, let words):
            return "flushed  \(words) words sent, reason: \(reason.rawValue)"
        case .sessionFacts(let facts):
            return "sessionFacts  \(facts.sentence)"
        case .buffersDropped(let count):
            return "buffersDropped  \(count) buffers dropped while swapping"
        case .batteryRead(let percent, let onPower):
            return "batteryRead  \(percent) percent, on power: \(onPower ? "yes" : "no")"
        case .airtimeLost(let milliseconds):
            return "airtimeLost  \(milliseconds) ms never arrived from the pendant"
        case .speechDropped(let count):
            return "speechDropped  \(count) unsent lines dropped, the queue was full"
        case .posted(let ok, let detail):
            return "posted  \(ok ? "accepted" : "failed"), \(detail.text)"
        }
    }
}
