import Foundation

// Checks for CaptureEnvelope — the two instants that bracket a line of speech,
// and the three columns they go out as.
//
// WHY THIS TYPE EXISTS. `PhoneListener.deliver` has always received both ends
// of a line: `wordsAppearedAt`, when the words first went unsent, and `now`,
// the instant the flush produced the line. Only `now` ever escaped, and
// `pushEvent` wrote that single value into `capture_started_at`, `spoken_at`
// AND `capture_ended_at`. Three columns, one number.
//
// The damage is not that a column is empty. It is that `capture_started_at` is
// POPULATED — 137 of 137 production rows carry one — and worthless: measured
// against arrival it is p50 0.053 s, max 0.065 s, which is the postmark and not
// the moment anybody spoke. A monitor asking "is the capture timestamp
// present?" reports green today on the exact column that is broken.
//
// Ordering is a comparison and a constant offset preserves it. Boundaries are a
// SUBTRACTION, and a subtraction of a number from itself is zero: with start
// and end aliased, `brain/segmenter.py` falls back to `end = start`, so the
// silence between two turns is measured flush-to-flush and swallows the whole
// speaking duration of the later turn plus the 2.6 s debounce. The error only
// ever runs one way — toward splitting a conversation that never ended.
//
// Pure Foundation on purpose, like TranscriptFlushPolicy and ListenTally:
// these run with swiftc alone. No simulator, no scheme, no signing, no network.

@main
struct CaptureEnvelopeTests {
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

        // A stamp that is not a date format at all, so a column that skips the
        // caller's clock is visible rather than merely differently formatted.
        func marker(_ d: Date) -> String {
            "T+\(Int(d.timeIntervalSince(t0)))"
        }

        // The real wire clock's options. Duplicated here as a FIXTURE, not as a
        // second source of truth: production hands its own formatter in, and
        // the runner has a law leg that the one it hands in keeps fractional
        // seconds. Check 24 is what makes that leg matter.
        let fractional = ISO8601DateFormatter()
        fractional.timeZone = TimeZone(secondsFromGMT: 0)
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let wholeSeconds = ISO8601DateFormatter()
        wholeSeconds.timeZone = TimeZone(secondsFromGMT: 0)
        wholeSeconds.formatOptions = [.withInternetDateTime]

        // ------------------------------------------------- 1. the ordinary flush
        // A gap flush: words appear, the speaker stops, 2.6 s of silence later
        // the line goes out. Those are two different instants and the whole
        // point of this type is that both survive.
        let gapFlush = CaptureEnvelope(startedAt: at(0), endedAt: at(2.6))
        check("a gap flush keeps the instant the words appeared",
              gapFlush.startedAt == at(0))
        check("a gap flush keeps the instant it was flushed",
              gapFlush.endedAt == at(2.6))
        check("a gap flush measures the span between them",
              abs(gapFlush.spanSeconds - 2.6) < 0.000_1)
        check("a gap flush brackets speech",
              gapFlush.bracketsSpeech)

        // The 8 s ceiling: a person who does not pause. The span is the whole
        // hold, which is the largest honest one this policy can produce.
        let ceiling = CaptureEnvelope(startedAt: at(0), endedAt: at(8))
        check("a ceiling cut measures the whole hold",
              abs(ceiling.spanSeconds - 8) < 0.000_1)

        // ---------------------------------------------- 2. one instant, said so
        // A typed line has no speaking duration to measure and a pre-envelope
        // queue row carries no end. Both are the same honest statement: the
        // phone knows ONE moment. It is not a zero-length utterance claim —
        // `bracketsSpeech` is how a reader tells the two apart.
        let typed = CaptureEnvelope.instant(at(100))
        check("one instant puts both ends at the same moment",
              typed.startedAt == at(100) && typed.endedAt == at(100))
        check("one instant brackets no speech",
              !typed.bracketsSpeech)
        check("one instant spans nothing",
              typed.spanSeconds == 0)

        // Two reads that came back identical are the same statement, however
        // they were built. This is the aliasing case — today's behaviour — and
        // it must NOT report itself as a measured span.
        let aliased = CaptureEnvelope(startedAt: at(50), endedAt: at(50))
        check("two identical reads are not a span",
              !aliased.bracketsSpeech)
        check("two identical reads are the same as one instant",
              aliased == CaptureEnvelope.instant(at(50)))

        // ------------------------------------------- 3. the clock stepped back
        // NTP corrects, a person changes the time, a timezone database lands.
        // Between `pendingSince` and the flush the wall clock can move
        // BACKWARDS, and then the first read is in the future relative to the
        // second. That is not a span; it is one bad read and one good one.
        //
        // The flush instant is the fresher read and the one the words actually
        // left at, so the envelope collapses onto it. Collapsing the other way
        // would post an end that precedes its own start (the server's Leg 3
        // invariant, `capture_ended_at <= created`, is the one thing a wrong
        // clock breaks first) and would publish a stamp from the future.
        let stepped = CaptureEnvelope(startedAt: at(400), endedAt: at(100))
        check("reads that ran backwards collapse onto the flush instant",
              stepped.startedAt == at(100) && stepped.endedAt == at(100))
        check("reads that ran backwards claim no span",
              !stepped.bracketsSpeech && stepped.spanSeconds == 0)
        check("reads that ran backwards never publish the future read",
              stepped.startedAt != at(400) && stepped.endedAt != at(400))

        // ------------------------------------------------ 4. what the queue kept
        // `of` is the ONE construction rule, used by the live push and by the
        // offline flush alike, so a buffered line and a live line cannot mean
        // different things. It is total: every combination of what the queue
        // may hold has an answer.
        check("no stamp at all is no envelope",
              CaptureEnvelope.of(startedAt: nil, endedAt: nil) == nil)
        check("a queue row from the previous build is one instant",
              CaptureEnvelope.of(startedAt: at(10), endedAt: nil)
                  == CaptureEnvelope.instant(at(10)))
        check("a start with no end brackets no speech",
              CaptureEnvelope.of(startedAt: at(10), endedAt: nil)?
                  .bracketsSpeech == false)
        // Cannot happen by construction — an end is only ever written beside a
        // start — but a queue is disk somebody else's build wrote, so the rule
        // answers rather than crashing or inventing a start.
        check("an end with no start is one instant, not a guess",
              CaptureEnvelope.of(startedAt: nil, endedAt: at(10))
                  == CaptureEnvelope.instant(at(10)))
        check("both stamps rebuild the span",
              CaptureEnvelope.of(startedAt: at(0), endedAt: at(3))
                  == CaptureEnvelope(startedAt: at(0), endedAt: at(3)))

        // The round trip that matters: what the live path would have sent is
        // exactly what the queue re-sends an hour later. Omi's #6551 is this
        // property failing.
        let live = CaptureEnvelope(startedAt: at(0), endedAt: at(4.2))
        let requeued = CaptureEnvelope.of(startedAt: live.startedAt,
                                          endedAt: live.endedAt)
        check("a line that waited in the queue re-sends the same envelope",
              requeued == live)

        // --------------------------------------------------- 5. the three columns
        let fields = gapFlush.wireFields(stamp: marker)
        check("the wire carries exactly three columns",
              fields.count == 3)
        check("the wire names the columns the server already has",
              Set(fields.keys) == ["capture_started_at", "spoken_at",
                                   "capture_ended_at"])
        check("capture_started_at is when the words appeared",
              fields["capture_started_at"] == "T+0")
        check("capture_ended_at is when the flush produced the line",
              fields["capture_ended_at"] == "T+2")
        // The rollout alias stays meaningful rather than decorative: the worker
        // reads `capture_started_at` first and accepts `spoken_at` as the older
        // name for the SAME instant. Pointing it at the end would make the two
        // readers disagree about the same row.
        check("spoken_at is the older name for the start, not the end",
              fields["spoken_at"] == fields["capture_started_at"])
        check("start and end are two different values on the wire",
              fields["capture_started_at"] != fields["capture_ended_at"])
        check("every column goes through the clock it was handed",
              fields.values.allSatisfy { $0.hasPrefix("T+") })

        // One instant still writes all three, because the columns mean what
        // they say: this line's capture began and ended at one known moment.
        // The gate reads the RELATIONSHIP, so a row like this scores as no
        // measured span rather than as a missing field — which is the honest
        // report, and it is why no gate leg may check non-emptiness.
        let typedFields = typed.wireFields(stamp: marker)
        check("one instant still fills all three columns",
              typedFields.count == 3)
        check("one instant writes the same value three times",
              Set(typedFields.values).count == 1)

        // ------------------------------------- 6. the wire must not flatten them
        // The two instants of a short banked-words delivery can be a few hundred
        // milliseconds apart. A whole-second ISO8601 formatter renders those as
        // the SAME string, and the row lands looking exactly like the aliasing
        // bug this work removes — green code, red data, and nothing in Swift to
        // say so. The runner has a law leg that production's formatter keeps
        // fractional seconds; this is the check that proves the leg is not
        // ceremony.
        let brief = CaptureEnvelope(startedAt: at(0), endedAt: at(0.3))
        let briefFractional = brief.wireFields(stamp: fractional.string(from:))
        check("a sub-second span survives a fractional-seconds clock",
              briefFractional["capture_started_at"]
                  != briefFractional["capture_ended_at"])
        let briefWhole = brief.wireFields(stamp: wholeSeconds.string(from:))
        check("a whole-second clock would flatten it — the hazard is real",
              briefWhole["capture_started_at"] == briefWhole["capture_ended_at"])

        // And a real gap flush is far enough apart to survive either, which is
        // why this went unnoticed: the common case hides the hazard.
        let gapWhole = gapFlush.wireFields(stamp: wholeSeconds.string(from:))
        check("a 2.6 s gap flush survives even a whole-second clock",
              gapWhole["capture_started_at"] != gapWhole["capture_ended_at"])

        // ------------------------------------------- 7. what the gate will read
        // The gate's floors are stated against what the BROKEN implementation
        // can physically produce: push-time stamping measured p50 0.053 s and a
        // maximum of 0.065 s against arrival. An honest gap flush is at least
        // one utterance gap (2.6 s) behind the post and a ceiling cut up to 8 s,
        // so the two populations are two orders of magnitude apart and no
        // formatting accident can carry one into the other.
        check("an honest gap flush clears the gate's 2.6 s floor",
              gapFlush.spanSeconds >= 2.6)
        check("the broken shape cannot reach the gate's floor",
              aliased.spanSeconds < 2.0)
        check("a ceiling cut is the widest honest span the policy can make",
              ceiling.spanSeconds <= 8.000_1)

        // ------------------------------------------------------------------ result
        print("")
        if failures.isEmpty {
            print("CaptureEnvelope: all \(checks) checks passed")
        } else {
            print("CaptureEnvelope: \(failures.count)/\(checks) FAILED")
            for f in failures { print("  - \(f)") }
            exit(1)
        }
    }
}
