import Foundation

// Checks for TranscriptFlushPolicy — WHEN heard words are sent and WHICH
// hypothesis they are taken from.
//
// The bug these exist to kill, watched live on 2026-08-16: about 250 words
// spoken continuously reached the backend as three fragments totalling 71
// characters — the opening, a scrap of the middle, and the tail. In the
// owner's words: "Every time I talk for a long period of time and then I talk
// too quickly, the transcript doesn't save. That audio goes away, and then a
// new one will appear. It's like it writes over itself."
//
// Two independent faults produced that. Every case below fails against the
// code as it was.

@main
struct TranscriptFlushPolicyTests {
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

        let policy = TranscriptFlushPolicy()

        // ---------------------------------------------------------------- fault 1
        // The silence flush is a debounce re-armed by every partial result. A person
        // who does not pause outruns it forever, so nothing is ever sent.

        check("nothing waiting means nothing to force out",
              !policy.mustFlushNow(pendingSince: nil, now: Date()))

        let t0 = Date()
        check("a brief wait still belongs to the pause detector",
              !policy.mustFlushNow(pendingSince: t0, now: t0.addingTimeInterval(1)))
        check("words still waiting at the gap are not yet forced",
              !policy.mustFlushNow(pendingSince: t0, now: t0.addingTimeInterval(2.6)))
        check("words waiting past the ceiling MUST go out",
              policy.mustFlushNow(pendingSince: t0, now: t0.addingTimeInterval(8)))
        check("a long monologue cannot outrun the ceiling",
              policy.mustFlushNow(pendingSince: t0, now: t0.addingTimeInterval(120)))

        // The ceiling has to beat Apple's task limit, which is where the old code
        // finally emitted — and by then the collapse had already eaten the middle.
        check("the ceiling fires well before a recognition task ends",
              policy.maxHold < 55)
        // ...and it must not chop a person mid-thought.
        check("the ceiling still leaves room for a natural pause",
              policy.maxHold > policy.utteranceGap * 2)

        // ---------------------------------------------------------------- fault 2
        // Apple revises DOWNWARD. Taking only from the latest hypothesis lets a
        // collapsed revision delete words that were genuinely heard, because the task
        // resets immediately afterwards.

        let full = "there's a transcription bug every time I talk for a long period "
            + "and then I talk too quickly the transcript doesn't save"
        let collapsed = "bug the way it takes an audio"

        check("a collapsed revision never replaces the fullest hearing",
              TranscriptFlushPolicy.source(latest: collapsed, richest: full) == full)
        check("a genuinely richer revision is preferred",
              TranscriptFlushPolicy.source(latest: full, richest: collapsed) == full)
        check("with no history the latest hypothesis is used",
              TranscriptFlushPolicy.source(latest: collapsed, richest: "") == collapsed)

        // ---------------------------------------------------------------- fault 3
        // The final-result floor of three new words is right for a polish and fatal
        // for a monologue that has sent nothing at all.

        check("a polish after speech already sent keeps its floor",
              TranscriptFlushPolicy.finalMinNewWords(everEmitted: true) == 3)
        check("a task ending having sent NOTHING gives up every word it has",
              TranscriptFlushPolicy.finalMinNewWords(everEmitted: false) == 1)

        // ------------------------------------------------- the live failure, end to end
        // Replay the shape of what happened: a continuous speaker, a recognizer that
        // collapses at the end, and a cursor that resets on the next task. Nothing the
        // person said may be lost.

        var cursor = TranscriptCursor()
        // ~250 words, the length he actually spoke — long enough that the
        // ceiling must fire many times over, the way it does on a real
        // two-minute monologue.
        let spoken = Array(repeating: full, count: 11)
            .joined(separator: " and ").split(separator: " ").map(String.init)
        var richest = ""
        var latest = ""
        var delivered: [String] = []
        var pendingSince: Date? = nil
        var clock = Date()
        var everEmitted = false

        for i in spoken.indices {
            // Partials arrive far faster than the utterance gap — this is what
            // starves the debounce.
            clock = clock.addingTimeInterval(0.35)
            latest = spoken[0...i].joined(separator: " ")
            if TranscriptCursor.split(latest).count > TranscriptCursor.split(richest).count {
                richest = latest
            }
            if pendingSince == nil { pendingSince = clock }
            if policy.mustFlushNow(pendingSince: pendingSince, now: clock) {
                let line = cursor.take(
                    TranscriptFlushPolicy.source(latest: latest, richest: richest))
                if !line.isEmpty { delivered.append(line); everEmitted = true }
                pendingSince = nil
            }
        }
        // Apple finalises with a COLLAPSED hypothesis, then the task resets.
        latest = collapsed
        let tail = cursor.take(
            TranscriptFlushPolicy.source(latest: latest, richest: richest),
            minNewWords: TranscriptFlushPolicy.finalMinNewWords(everEmitted: everEmitted))
        if !tail.isEmpty { delivered.append(tail) }

        let heard = delivered.joined(separator: " ")
        let spokenWords = spoken.map { $0.lowercased() }
        let heardWords = Set(TranscriptCursor.split(heard).map { $0.lowercased() })
        let lost = spokenWords.filter { !heardWords.contains($0) }

        check("a 250-word monologue is delivered in pieces, not held to the end",
              delivered.count >= 5)
        check("nothing waits longer than the ceiling before being sent",
              delivered.count >= Int(Double(spoken.count) * 0.35 / policy.maxHold) - 1)
        check("no spoken word is lost across a collapsing final: \(lost)", lost.isEmpty)
        check("the delivered text is not a 71-character scrap", heard.count > 100)

        // ------------------------------------------------------------------ result
        print("")
        if failures.isEmpty {
            print("TranscriptFlushPolicy: all \(checks) checks passed")
        } else {
            print("TranscriptFlushPolicy: \(failures.count)/\(checks) FAILED")
            for f in failures { print("  - \(f)") }
            exit(1)
        }

    }
}
