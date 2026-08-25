import Foundation

/// The two instants that bracket one line of speech, and the three columns
/// they go out as.
///
/// ORDERING IS A COMPARISON; BOUNDARIES ARE A SUBTRACTION. A constant offset
/// preserves the first and destroys the second, and that is the whole of what
/// was wrong. `pushEvent` used to take ONE `Date` and write it into
/// `capture_started_at`, `spoken_at` and `capture_ended_at` alike, so
/// `end - start` was always zero.
///
/// The failure is not a missing column, which is what makes it hard to see.
/// All 137 stored production rows carry a non-empty `capture_started_at`, and
/// every one of them is the postmark: measured against arrival it is p50
/// 0.053 s, max 0.065 s. Present, populated, and informationally identical to
/// the moment the network delivered the row. Anything that asks "is the
/// capture timestamp there?" has reported green for months on the exact column
/// this type exists to fix.
///
/// WHAT THE COLLAPSE COSTS DOWNSTREAM. `brain/segmenter.py` reads an empty or
/// equal end as `end = start`, so `brain/sorter.py` computes the silence
/// between two turns as flush-to-flush — which swallows the entire speaking
/// duration of the later turn plus the 2.6 s debounce, up to 8 s for a ceiling
/// cut. Measured on the real call: a 38.0 s recorded gap whose true silence was
/// about 23.2 s, against a `CONTINUE_S = 45` threshold that decides whether the
/// next turn joins the open conversation or starts a new one. The error is
/// one-directional. It always pushes toward splitting a conversation that did
/// not end.
///
/// Nothing here decides what any word MEANS. Two wall-clock reads and the
/// arithmetic between them — this type cannot see a single word of anybody's
/// speech, and does not take one.
///
/// Pure Foundation, like `TranscriptFlushPolicy` and `ListenTally`: it builds
/// with `swiftc` alone, so `Tests/run_capture_envelope_tests.sh` needs no
/// simulator, no scheme and no signing.
struct CaptureEnvelope: Equatable {
    /// When this line's words first went unsent — `PhoneListener`'s
    /// `wordsAppearedAt`, taken from `pendingSince` on the first partial after
    /// words went pending.
    ///
    /// It lags true speech onset by tens to low hundreds of milliseconds,
    /// because a partial is the earliest the recognizer says anything at all.
    /// That is 30–100x better than the 2.6–10.6 s error it replaces, and it is
    /// noise against a 45 s conversation threshold. It is NOT sample-accurate
    /// and this type does not claim it is; `SFTranscriptionSegment.timestamp`
    /// is what would be, and it is a different piece of work.
    let startedAt: Date

    /// The instant the flush produced the line — `PhoneListener`'s `now`.
    /// This is the value that used to be all three columns.
    let endedAt: Date

    /// Two reads that bracket a real stretch of time.
    ///
    /// Reads that came back OUT OF ORDER collapse onto the flush instant. A
    /// wall clock steps backwards for ordinary reasons — NTP correcting, a
    /// person changing the time, a timezone database landing — and between
    /// `pendingSince` and the flush there is room for it. Two instants that do
    /// not bracket anything are not a span; they are one stale read and one
    /// fresh one, and the fresh one is where the words actually left.
    ///
    /// Collapsing the other way would publish a stamp from the future and post
    /// an end that precedes its own start, which is the first invariant a
    /// wrong clock breaks and the one `capture_key`'s skew window exists to
    /// survive.
    init(startedAt: Date, endedAt: Date) {
        if endedAt > startedAt {
            self.startedAt = startedAt
            self.endedAt = endedAt
        } else {
            self.startedAt = endedAt
            self.endedAt = endedAt
        }
    }

    /// One known moment, and no claim about a span.
    ///
    /// A typed line has no speaking duration to measure. A queue row written
    /// by a build that predates this type carries no end. Both are the same
    /// honest statement, and `bracketsSpeech` is how a reader tells this from a
    /// measured zero.
    static func instant(_ at: Date) -> CaptureEnvelope {
        CaptureEnvelope(startedAt: at, endedAt: at)
    }

    /// THE ONE CONSTRUCTION RULE, used by the live push and by the offline
    /// flush alike.
    ///
    /// Two paths building envelopes two ways is how a buffered line and a live
    /// line come to mean different things — and the buffered ones are exactly
    /// the rows this work exists for, because they are the ones a radio
    /// dropped. Total on purpose: the queue is disk that somebody else's build
    /// wrote, so every combination has an answer rather than a crash or an
    /// invented instant.
    ///
    /// Returns nil when there is no stamp at all. An event posted the moment it
    /// happens is already described by `created`, and a guessed stamp is worse
    /// than an absent one.
    static func of(startedAt: Date?, endedAt: Date?) -> CaptureEnvelope? {
        switch (startedAt, endedAt) {
        case let (start?, end?): return CaptureEnvelope(startedAt: start, endedAt: end)
        case let (start?, nil): return .instant(start)
        case let (nil, end?): return .instant(end)
        case (nil, nil): return nil
        }
    }

    /// How long the words took, in seconds. Zero when nothing was measured.
    var spanSeconds: TimeInterval { endedAt.timeIntervalSince(startedAt) }

    /// Whether these two instants measured a stretch of speech, as opposed to
    /// naming one moment twice. The gate reads this relationship and never
    /// asks whether a field is filled in, because filled-in is what the broken
    /// version already was.
    var bracketsSpeech: Bool { endedAt > startedAt }

    /// The three columns, and which instant each one gets.
    ///
    /// `capture_started_at` is canonical — the worker reads it first — and
    /// `spoken_at` is the older name for the SAME instant, kept written so the
    /// rollout tolerance stays meaningful rather than decorative. Pointing
    /// `spoken_at` at the end would make two readers of one row disagree.
    ///
    /// The clock is HANDED IN rather than owned here, so this file needs no
    /// formatter of its own and there is no second set of format options to
    /// drift. One caveat the caller inherits: a whole-second formatter renders
    /// two instants a few hundred milliseconds apart as the same string, and
    /// the row then arrives indistinguishable from the collapsed one this type
    /// removes. `Tests/run_capture_envelope_tests.sh` holds a leg on the wire
    /// clock keeping fractional seconds.
    func wireFields(stamp: (Date) -> String) -> [String: String] {
        let start = stamp(startedAt)
        return [
            "capture_started_at": start,
            "spoken_at": start,
            "capture_ended_at": stamp(endedAt),
        ]
    }
}
