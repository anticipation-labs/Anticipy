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
        // slightly different words. These are his real pairs, and the apart
        // times are the ones his transcript actually recorded — 16:47:48 then
        // 16:47:50. The window they are judged against is the shipped one, so
        // these checks measure what the phone does rather than a number that
        // only ever existed in this file.
        let echo = policy.echoWindow
        check("the same sentence revised is not said twice",
              TranscriptFlushPolicy.isEchoOfPrevious("Yeah I know it is", previous: "Yeah I know where it is",
                   apart: 2, window: echo))
        check("an exact repeat too soon to have been spoken again is an echo",
              TranscriptFlushPolicy.isEchoOfPrevious("tell me a little bit more about yourself",
                   previous: "tell me a little bit more about yourself",
                   apart: 1.5, window: echo))
        // ...but a genuinely new sentence must always get through.
        check("a new thought is never swallowed",
              !TranscriptFlushPolicy.isEchoOfPrevious("let's do 7pm at Earls in West Van",
                    previous: "Yeah I know where it is", apart: 2, window: echo))
        check("saying more about the same thing is not an echo",
              !TranscriptFlushPolicy.isEchoOfPrevious("I know where it is, it's the one by the water past the bridge",
                    previous: "Yeah I know where it is", apart: 2, window: echo))
        check("short natural repetition is left alone",
              !TranscriptFlushPolicy.isEchoOfPrevious("yeah yeah yeah", previous: "yeah yeah yeah",
                    apart: 1, window: echo))
        check("the same words much later are a new sentence",
              !TranscriptFlushPolicy.isEchoOfPrevious("Yeah I know where it is", previous: "Yeah I know where it is",
                    apart: 60, window: echo))

        // The two legs of the word comparison were covering for each other:
        // every case above that one leg would have got wrong, the other leg
        // caught, so either could be deleted or moved a long way and the suite
        // stayed green. Each of these fails if exactly one leg moves.
        //
        // Only the novelty leg spares this: a person restating their sentence
        // and carrying on with it shares 73% of its words with what came
        // before, which is over the overlap bar. Four of the words are new,
        // and they are the whole point of the line.
        check("restating a sentence and adding to it is not an echo",
              !TranscriptFlushPolicy.isEchoOfPrevious(
                  "I need to call the dentist about my appointment tomorrow morning and reschedule it please",
                  previous: "I need to call the dentist about my appointment tomorrow morning",
                  apart: 2, window: echo))
        // Only the overlap bar spares this: two of five words are new, which
        // the novelty leg permits, and those two words are a different errand
        // for a different person. 60% shared is what a short sentence looks
        // like when it happens to be built the same way as the last one.
        check("a different request built the same way is not an echo",
              !TranscriptFlushPolicy.isEchoOfPrevious("can you call Mum now",
                    previous: "can you hear me now", apart: 2, window: echo))
        // ...and the bar has to stay under identity. The recognizer's second
        // rendering of one utterance differs by a word appearing or vanishing
        // — here a contraction splitting "it is" into "it" and "s" — so a
        // guard that only recognised a perfect copy would have let his
        // recorded pair straight through.
        check("a re-rendering that is not word-for-word is still an echo",
              TranscriptFlushPolicy.isEchoOfPrevious("Yeah I know where it's",
                    previous: "Yeah I know where it is", apart: 2, window: echo))

        // ------------------------------------------- a person is not a recognizer
        // The defect this section exists to kill, root-caused 2026-08-24 in
        // research/2026-08-24-why-voice-tests-dont-complete.md and reproduced
        // below against the real cursor: the guard fired hardest on the single
        // most common thing a human tester does, which is say the phrase again
        // to check whether it worked. Three utterances, two rows, and the one
        // that vanished was the middle one. Nothing anywhere said so.
        //
        // What separates the two events is not what the words say — a machine
        // re-rendering audio and a person repeating themselves produce the
        // SAME words, which is why no comparison of the words can tell them
        // apart. It is what each one costs in time. A person who repeats
        // themselves had to stop long enough to end the first utterance and
        // then spend the seconds it takes to say the words again; a recognizer
        // handing back audio it already decoded spends neither.

        // The floor that the window has to clear, measured rather than
        // assumed. Every speaking rate and every pause that can produce two
        // separate lines of the same phrase, driven through the real cursor
        // and the real flush clock: if the similarity test would fire on the
        // pair, the person must still get both lines.
        //
        // This is the check that goes red if the window is ever widened back
        // towards the twelve seconds that swallowed his second attempt.
        var closestRealRepeat = Double.infinity
        var closestShape = ""
        for phrase in ["hey can you hear",
                       "testing can you hear me now",
                       "remind me to call the dentist tomorrow"] {
            let words = phrase.split(separator: " ").map(String.init)
            for pauseStep in 0...27 {
                let pause = 2.6 + Double(pauseStep) * 0.2
                // Seconds per word: faster than anyone sustains, ordinary, slow.
                for rate in [0.20, 0.35, 0.50] {
                    let span = Double(words.count - 1) * rate
                    let starts = [0.0, span + pause, (span + pause) * 2]
                    var c = TranscriptCursor()
                    var since: Date? = nil
                    var lastPartial: Date? = nil
                    var out: [(String, Date)] = []
                    let origin = Date()
                    var said: [String] = []
                    var tick = 0.0
                    while tick <= (span + pause) * 3 + 12 {
                        let now = origin.addingTimeInterval(tick)
                        for s in starts {
                            for (i, w) in words.enumerated()
                            where abs(tick - (s + Double(i) * rate)) < 0.025 {
                                said.append(w)
                                let u = c.observe(said.joined(separator: " "))
                                lastPartial = now
                                if let b = u.banked, !b.isEmpty { out.append((b, now)) }
                                if u.changed || u.didReset, c.hasPending, since == nil { since = now }
                            }
                        }
                        if c.hasPending, since == nil { since = now }
                        if policy.flushReason(pendingSince: since,
                                              lastPartialAt: lastPartial, now: now) != nil {
                            since = nil
                            if let l = c.takePending()?
                                .trimmingCharacters(in: .whitespacesAndNewlines), !l.isEmpty {
                                out.append((l, now))
                            }
                        }
                        tick += 0.05
                    }
                    guard out.count >= 2 else { continue }
                    for i in 1..<out.count {
                        // Only the pairs actually at risk: the ones the word
                        // comparison would fire on with no window at all.
                        guard TranscriptFlushPolicy.isEchoOfPrevious(
                                out[i].0, previous: out[i - 1].0,
                                apart: 0, window: .greatestFiniteMagnitude) else { continue }
                        let apart = out[i].1.timeIntervalSince(out[i - 1].1)
                        if apart < closestRealRepeat {
                            closestRealRepeat = apart
                            closestShape = "\(words.count) words, \(rate)s/word, \(pause)s pause"
                        }
                    }
                }
            }
        }
        check("a person repeating themselves is never inside the echo window "
              + "(closest real repeat \(closestRealRepeat)s — \(closestShape))",
              closestRealRepeat > policy.echoWindow)

        // The tester's own thirty-second confirmation, end to end through the
        // real cursor: say a phrase, watch, say it again, watch, say it a
        // third time. Three utterances have to produce three rows. Before the
        // window was narrowed this produced two, and the missing one was the
        // middle one — attempt two was inside twelve seconds of attempt one,
        // attempt three was outside twelve seconds of attempt one because
        // attempt two never became a delivery to measure from.
        do {
            let words = "remind me to call the dentist tomorrow"
                .split(separator: " ").map(String.init)
            var c = TranscriptCursor()
            var since: Date? = nil
            var lastPartial: Date? = nil
            var lastOut: (text: String, at: Date)? = nil
            var onScreen: [String] = []
            let origin = Date()
            var said: [String] = []
            func offer(_ line: String, _ now: Date) {
                if let last = lastOut,
                   TranscriptFlushPolicy.isEchoOfPrevious(
                       line, previous: last.text,
                       apart: now.timeIntervalSince(last.at),
                       window: policy.echoWindow) { return }
                lastOut = (line, now)
                onScreen.append(line)
            }
            var tick = 0.0
            while tick <= 32.0 {
                let now = origin.addingTimeInterval(tick)
                for s in [0.0, 10.5, 21.0] {
                    for (i, w) in words.enumerated()
                    where abs(tick - (s + Double(i) * 0.35)) < 0.025 {
                        said.append(w)
                        let u = c.observe(said.joined(separator: " "))
                        lastPartial = now
                        if let b = u.banked, !b.isEmpty { offer(b, now) }
                        if u.changed || u.didReset, c.hasPending, since == nil { since = now }
                    }
                }
                if c.hasPending, since == nil { since = now }
                if policy.flushReason(pendingSince: since,
                                      lastPartialAt: lastPartial, now: now) != nil {
                    since = nil
                    if let l = c.takePending()?
                        .trimmingCharacters(in: .whitespacesAndNewlines), !l.isEmpty {
                        offer(l, now)
                    }
                }
                tick += 0.05
            }
            check("three attempts at the same test phrase are three rows, not two "
                  + "(got \(onScreen.count))", onScreen.count == 3)
        }

        // ...and the protection that cost is still paid for. The recognizer
        // really does hand the same sentence over twice: a recognition task
        // ends, the cursor's record of what it already sent dies with it, and
        // the audio held across the seam is replayed into a fresh task that
        // decodes it again. Driven here through the real cursor, with the real
        // reset, so this is the machine doing it rather than two strings
        // chosen to look alike.
        do {
            var c = TranscriptCursor()
            let origin = Date()
            let heard = ["yeah", "I", "know", "where", "it", "is"]
            for i in heard.indices { _ = c.observe(heard[0...i].joined(separator: " ")) }
            guard let first = c.takePending() else {
                check("the recognizer's first rendering is delivered", false)
                exit(1)
            }
            let firstAt = origin
            // The task ended. Everything the cursor knew about what it had
            // already sent goes with it — this is `cursor.reset()` in
            // `startRecognition`, and it is the only state that could have
            // stopped the next line being the same sentence again.
            c.reset()
            // The orphan buffer replays the same audio into the new task,
            // which decodes it slightly differently — his real pair.
            let again = ["yeah", "I", "know", "it", "is"]
            for i in again.indices { _ = c.observe(again[0...i].joined(separator: " ")) }
            let second = c.takePending() ?? ""
            // The replay is immediate: the new task is handed that audio in
            // the same instant the old one was cancelled, so the duplicate
            // arrives a fraction of a second later, not seconds.
            let secondAt = origin.addingTimeInterval(0.4)
            check("a sentence re-decoded across a task seam is still caught",
                  TranscriptFlushPolicy.isEchoOfPrevious(
                      second, previous: first,
                      apart: secondAt.timeIntervalSince(firstAt),
                      window: policy.echoWindow))
        }

        // The window's own boundary. At exactly the gap the utterance is over
        // by this policy's own standard everywhere else, and words arriving no
        // later than that had no room to be spoken twice.
        check("at exactly the window the same words are still the same audio",
              TranscriptFlushPolicy.isEchoOfPrevious("tell me a little bit more about yourself",
                    previous: "tell me a little bit more about yourself",
                    apart: policy.echoWindow, window: policy.echoWindow))
        check("a hair past the window they were said again",
              !TranscriptFlushPolicy.isEchoOfPrevious("tell me a little bit more about yourself",
                    previous: "tell me a little bit more about yourself",
                    apart: policy.echoWindow + 0.01, window: policy.echoWindow))
        // The window is the utterance gap itself, not a number of its own.
        // Anything longer reaches past the point where this policy has already
        // declared the utterance finished, and a policy that calls a line a
        // new utterance and a repeat of the last one at the same time is
        // deciding by coin toss.
        check("the echo window is the pause that ends an utterance",
              policy.echoWindow == policy.utteranceGap)

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
