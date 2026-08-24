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

        // ------------------------------------------------- the live failure, end to end
        // Replay the shape of what happened: a continuous speaker, a recognizer that
        // collapses at the end, and a cursor that resets on the next task. Nothing the
        // person said may be lost.

        let full = "there's a transcription bug every time I talk for a long period "
            + "and then I talk too quickly the transcript doesn't save"
        let collapsed = "bug the way it takes an audio"
        var cursor = TranscriptCursor()
        // ~250 words, the length he actually spoke — long enough that the
        // ceiling must fire many times over, the way it does on a real
        // two-minute monologue.
        let spoken = Array(repeating: full, count: 11)
            .joined(separator: " and ").split(separator: " ").map(String.init)
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
            let update = cursor.observe(latest)
            if let banked = update.banked, !banked.isEmpty {
                delivered.append(banked); everEmitted = true
            }
            if pendingSince == nil { pendingSince = clock }
            if policy.mustFlushNow(pendingSince: pendingSince, now: clock) {
                if let line = cursor.takePending(), !line.isEmpty {
                    delivered.append(line); everEmitted = true
                }
                pendingSince = nil
            }
        }
        // Apple finalises with a COLLAPSED hypothesis, then the task resets.
        let finalUpdate = cursor.observe(collapsed)
        if let banked = finalUpdate.banked, !banked.isEmpty { delivered.append(banked) }
        if let tail = cursor.takePending(), !tail.isEmpty { delivered.append(tail) }
        _ = everEmitted

        let heard = delivered.joined(separator: " ")
        let spokenWords = spoken.map { $0.lowercased() }
        let heardWords = Set(heard.split(separator: " ").map { $0.lowercased() })
        let lost = spokenWords.filter { !heardWords.contains($0) }

        check("a 250-word monologue is delivered in pieces, not held to the end",
              delivered.count >= 5)
        check("nothing waits longer than the ceiling before being sent",
              delivered.count >= Int(Double(spoken.count) * 0.35 / policy.maxHold) - 1)
        check("no spoken word is lost across a collapsing final: \(lost)", lost.isEmpty)
        check("the delivered text is not a 71-character scrap", heard.count > 100)

        // ---------------------------------------------------------------- echoes
        // Not losing words cost this: one sentence delivered twice in
        // slightly different words. These are his real pairs, seconds apart.
        check("the same sentence revised is not said twice",
              TranscriptFlushPolicy.isEchoOfPrevious("Yeah I know it is", previous: "Yeah I know where it is",
                   apart: 2, window: 12))
        check("an exact repeat within the window is an echo",
              TranscriptFlushPolicy.isEchoOfPrevious("tell me a little bit more about yourself",
                   previous: "tell me a little bit more about yourself",
                   apart: 3, window: 12))
        // ...but a genuinely new sentence must always get through.
        check("a new thought is never swallowed",
              !TranscriptFlushPolicy.isEchoOfPrevious("let's do 7pm at Earls in West Van",
                    previous: "Yeah I know where it is", apart: 2, window: 12))
        check("saying more about the same thing is not an echo",
              !TranscriptFlushPolicy.isEchoOfPrevious("I know where it is, it's the one by the water past the bridge",
                    previous: "Yeah I know where it is", apart: 2, window: 12))
        check("short natural repetition is left alone",
              !TranscriptFlushPolicy.isEchoOfPrevious("yeah yeah yeah", previous: "yeah yeah yeah",
                    apart: 1, window: 12))
        check("the same words much later are a new sentence",
              !TranscriptFlushPolicy.isEchoOfPrevious("Yeah I know where it is", previous: "Yeah I know where it is",
                    apart: 60, window: 12))

        // ------------------------------------------------- why the flush fired
        // The ceiling ended the silent loss, but it ends a LINE as well, so
        // continuous speech was cut every 8 seconds wherever the sentence
        // happened to be. On the recorded call of 2026-08-23, 54% of the
        // delivered lines were four words or fewer. Nothing here changes WHEN
        // the words go out; it only tells the caller which of the two events
        // just happened, so a mid-sentence cut can be linked instead of
        // published as a finished thought.

        let p0 = Date()
        check("no waiting words means no reason to flush",
              policy.flushReason(pendingSince: nil,
                                 lastPartialAt: p0, now: p0) == nil)
        check("still speaking past the ceiling is a cut, not an ending",
              policy.flushReason(pendingSince: p0,
                                 lastPartialAt: p0.addingTimeInterval(8.9),
                                 now: p0.addingTimeInterval(9)) == .ceiling)
        check("a pause longer than the gap ended the utterance",
              policy.flushReason(pendingSince: p0,
                                 lastPartialAt: p0.addingTimeInterval(0.3),
                                 now: p0.addingTimeInterval(3)) == .gap)
        check("mid-sentence and short of the ceiling is nobody's business yet",
              policy.flushReason(pendingSince: p0,
                                 lastPartialAt: p0.addingTimeInterval(2.5),
                                 now: p0.addingTimeInterval(3)) == nil)
        // Both conditions at once. He stopped talking and stayed stopped, and
        // the ceiling merely expired behind him. Calling that a cut would
        // chain the next unrelated sentence onto this finished one.
        check("a finished thought is never reported as a cut",
              policy.flushReason(pendingSince: p0,
                                 lastPartialAt: p0.addingTimeInterval(6.3),
                                 now: p0.addingTimeInterval(9)) == .gap)
        // The ceiling has a boundary of its own, and it must include the
        // instant it names: at exactly maxHold the words have waited the whole
        // hold, and a flush one tick later than promised is a flush the
        // speaker can still outrun.
        check("the ceiling reports a cut from the instant it expires",
              policy.flushReason(pendingSince: p0,
                                 lastPartialAt: p0.addingTimeInterval(policy.maxHold),
                                 now: p0.addingTimeInterval(policy.maxHold)) == .ceiling)
        check("a hair under the ceiling is still nobody's business",
              policy.flushReason(pendingSince: p0,
                                 lastPartialAt: p0.addingTimeInterval(policy.maxHold - 0.01),
                                 now: p0.addingTimeInterval(policy.maxHold - 0.01)) == nil)
        // No partial time at all. The caller that cannot say when it last
        // heard something is told the silence ran the whole wait, so this
        // reads as a finished thought rather than a cut. That is the safe
        // direction, and it is also a trap worth pinning: because the ceiling
        // is longer than the gap, a caller passing nil gets .gap for every
        // input that exists and never sees a cut at all.
        check("no partial time means the whole wait was silence",
              policy.flushReason(pendingSince: p0, lastPartialAt: nil,
                                 now: p0.addingTimeInterval(9)) == .gap)
        // The reason is additive. The ceiling itself must answer exactly as it
        // did before, because PhoneListener still asks it this question.
        check("the ceiling contract is unchanged at the boundary",
              policy.mustFlushNow(pendingSince: p0, now: p0.addingTimeInterval(policy.maxHold))
              && !policy.mustFlushNow(pendingSince: p0,
                                      now: p0.addingTimeInterval(policy.maxHold - 0.01)))

        // ---------------------------------------------- does a cut still run on
        // Nothing was cut, so nothing carries on. The first line of a session
        // has to answer this and must never be linked to anything.
        check("no cut means no continuation",
              !policy.cutContinues(cutAt: nil, wordsAppearedAt: p0))
        // A continuous talker: the ceiling cut him off and he kept going. The
        // next words are the rest of that sentence.
        check("words that follow a cut at once carry on from it",
              policy.cutContinues(cutAt: p0, wordsAppearedAt: p0.addingTimeInterval(0.3)))
        // The reported residual: a cut took every pending word, then five
        // minutes of silence, then a brand-new thought. Marking that as a
        // continuation chains an unrelated sentence onto one from minutes ago.
        check("a new thought after a long silence carries on from nothing",
              !policy.cutContinues(cutAt: p0, wordsAppearedAt: p0.addingTimeInterval(300)))
        // The boundary is the same pause that ends an utterance everywhere
        // else. At exactly the gap the utterance is over by the policy's own
        // standard, so the words after it start something.
        check("at exactly the gap the cut is over",
              !policy.cutContinues(cutAt: p0,
                                   wordsAppearedAt: p0.addingTimeInterval(policy.utteranceGap)))
        check("a hair inside the gap still continues",
              policy.cutContinues(cutAt: p0,
                                  wordsAppearedAt: p0.addingTimeInterval(policy.utteranceGap - 0.01)))
        // The edge this rule must NOT destroy, and the reason the caller has to
        // pass the right instant. A monologue cut at the ceiling is cut again a
        // whole maxHold later, so the second fragment's words APPEAR a moment
        // after the cut but are DELIVERED eight seconds after it. Those two
        // instants give opposite answers here, which is the point: judged on
        // appearance the fragment continues the cut, judged on delivery every
        // true edge in a monologue is thrown away. The check asks both.
        let wordsAppeared = p0.addingTimeInterval(0.2)
        let wordsDelivered = wordsAppeared.addingTimeInterval(policy.maxHold)
        check("a fragment is judged on when its words appeared, not when it went out",
              policy.cutContinues(cutAt: p0, wordsAppearedAt: wordsAppeared)
              && !policy.cutContinues(cutAt: p0, wordsAppearedAt: wordsDelivered))

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
