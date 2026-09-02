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
        // A replica of PhoneListener's delivery loop: the REAL cursor, the
        // REAL flush clock, the REAL debounce and the REAL guard, wired the
        // way `startRecognition` -> `scheduleSilenceFlush` -> `flushTail` ->
        // `deliver` wire them. Every echo check below runs through this
        // instead of handing the guard two strings and a made-up interval.
        //
        // That is not tidiness. The version this replaced pinned the seam case
        // with a hardcoded 0.4s gap, which is true of any window at all, so it
        // could not see that the shipped window had become unreachable: it
        // asserted a duplicate was caught while the phone was emitting it.
        struct Partial {
            /// Seconds after the origin.
            let at: Double
            /// The whole hypothesis the recognizer now believes.
            let text: String
            /// This callback belongs to a NEW recognition task: the cursor's
            /// record of what it sent died and the held audio was replayed.
            let newTask: Bool
        }
        struct Row {
            let text: String
            let appearedAt: Double
            let at: Double
            let dropped: Bool
        }

        func drive(_ script: [Partial]) -> [Row] {
            let origin = Date()
            func date(_ t: Double) -> Date { origin.addingTimeInterval(t) }
            var cursor = TranscriptCursor()
            var pendingSince: Double?
            var lastPartialAt: Double?
            var timer: Double?
            var lastDelivered: String?
            var lineageBrokeAt: Double?
            var rows: [Row] = []

            func deliver(_ line: String, appearedAt: Double, at now: Double) {
                let broke = lineageBrokeAt
                lineageBrokeAt = nil
                var dropped = false
                if let last = lastDelivered,
                   policy.isEchoOfPrevious(line, previous: last,
                                           lineageBrokeAt: broke.map(date),
                                           wordsAppearedAt: date(appearedAt)) {
                    dropped = true
                }
                rows.append(Row(text: line, appearedAt: appearedAt,
                                at: now, dropped: dropped))
                if !dropped { lastDelivered = line }
            }
            func flushTail(at now: Double) {
                timer = nil
                let appeared = pendingSince ?? now
                pendingSince = nil
                guard let line = cursor.takePending()?
                    .trimmingCharacters(in: .whitespacesAndNewlines),
                    !line.isEmpty else { return }
                deliver(line, appearedAt: appeared, at: now)
            }

            var i = 0
            while i < script.count {
                let p = script[i]
                // The armed debounce fires before the next callback if its
                // deadline is earlier. This is the whole reason a duplicate
                // the timer delivers can never land closer than the gap.
                if let t = timer, t < p.at { flushTail(at: t); continue }
                if p.newTask {
                    lineageBrokeAt = p.at
                    cursor.reset()
                    pendingSince = nil; lastPartialAt = nil; timer = nil
                }
                let u = cursor.observe(p.text)
                lastPartialAt = p.at
                if let b = u.banked?.trimmingCharacters(in: .whitespacesAndNewlines),
                   !b.isEmpty {
                    deliver(b, appearedAt: pendingSince ?? p.at, at: p.at)
                    // The old decode window left with the banked row. The
                    // replacement tail starts on this callback, exactly as
                    // PhoneListener does; otherwise two distinct rows publish
                    // the same capture start and a live burst looks collapsed.
                    pendingSince = nil
                }
                // After the banked line, exactly as PhoneListener does it.
                if u.didReset { lineageBrokeAt = p.at }
                if u.changed || u.didReset {
                    if cursor.hasPending {
                        let since = pendingSince ?? p.at
                        pendingSince = since
                        if policy.flushReason(pendingSince: date(since),
                                              lastPartialAt: lastPartialAt.map(date),
                                              now: date(p.at)) != nil {
                            flushTail(at: p.at)
                        } else {
                            timer = p.at + policy.utteranceGap
                        }
                    } else {
                        pendingSince = nil; timer = nil
                    }
                }
                i += 1
            }
            if let t = timer { flushTail(at: t) }
            return rows
        }

        // A replaced decode window can hand over an old sentence and leave a
        // new tail in the same callback. They are two rows, but they are not
        // two claims on the old window's start instant. This is the exact
        // build-113 production shape that failed turn_envelope_gate leg 5:
        // three rows arrived together with one identical capture start.
        do {
            let rows = drive([
                Partial(at: 0, text: "the old decode window still has its words",
                        newTask: false),
                Partial(at: 0.4, text: "replacement tail", newTask: false),
            ]).filter { !$0.dropped }
            check("a banked window and its replacement tail have distinct starts",
                  rows.count == 2
                  && rows[0].appearedAt == 0
                  && rows[1].appearedAt == 0.4)
        }

        /// One phrase turned into partial callbacks, `k` words at a time, each
        /// callback arriving when the last word of its batch has been spoken.
        ///
        /// `k` is the whole point of this parameter and the reason the old
        /// human floor was wrong. The sweep it replaced emitted ONE WORD PER
        /// CALLBACK, which charges every repeat the full length of the phrase
        /// before it can be delivered and reported a comfortable 3.4s floor.
        /// Real recognizers batch. At four words a callback the same phrase
        /// lands 2.61s apart — ten milliseconds outside a 2.6s window.
        func say(_ phrase: String, from start: Double, rate: Double,
                 wordsPerPartial k: Int, newTask: Bool = false,
                 after prefix: String = "") -> [Partial] {
            let w = phrase.split(separator: " ").map(String.init)
            let head = prefix.isEmpty ? "" : prefix + " "
            var out: [Partial] = []
            var j = k
            while j <= w.count {
                out.append(Partial(at: start + Double(j - 1) * rate,
                                   text: head + w[0..<j].joined(separator: " "),
                                   newTask: newTask && j == k))
                j += k
            }
            if w.count % k != 0 {
                out.append(Partial(at: start + Double(w.count - 1) * rate,
                                   text: head + w.joined(separator: " "),
                                   newTask: false))
            }
            return out
        }

        let saidOnce = "yeah I know where it is"
        let reRendered = "yeah I know it is"

        // ------------------------------------------- the machine says it twice
        // His recorded pair, 2026-08-17. The words are delivered, and then the
        // recognizer REPLACES its decode window and hands the same audio back
        // in slightly different words. The duplicate goes out on the silence
        // timer, which is the ordinary path — and a 2.6s window could not
        // touch it, because the timer cannot deliver anything sooner than 2.6s
        // after the last one. Three attempts at three ways of losing the
        // lineage, and none of them may produce two rows.
        do {
            let spoken = say(saidOnce, from: 0, rate: 0.35, wordsPerPartial: 1)
            let last = spoken.last!.at
            var caught = 0, cases = 0
            for delay in [0.01, 0.05, 0.25, 1.0, 3.0] {
                for k in [1, 2, 5] {
                    // The window is replaced just after the first line went out.
                    let at = last + policy.utteranceGap + delay
                    for seam in [false, true] {
                        let rows = drive(spoken + say(reRendered, from: at, rate: 0.05,
                                                      wordsPerPartial: k, newTask: seam))
                        cases += 1
                        if rows.filter({ !$0.dropped }).count == 1 { caught += 1 }
                    }
                }
            }
            check("a re-decoded sentence is caught however the window was lost "
                  + "(\(caught)/\(cases))", cases == 30 && caught == cases)
        }

        // ------------------------------------------- a person says it twice
        // The defect root-caused 2026-08-24 in
        // research/2026-08-24-why-voice-tests-dont-complete.md: the guard fired
        // hardest on the single most common thing a human tester does, which is
        // say the phrase again to check whether it worked. Three utterances,
        // two rows, and the one that vanished was the middle one.
        //
        // No floor is measured here, because the floor was the error. Whenever
        // the clock made two lines out of two attempts, BOTH have to arrive —
        // at any speaking rate, any pause, and any batching the recognizer
        // does. A window of any width fails this: the closest genuine repeat
        // and the closest machine duplicate land the same distance apart.
        do {
            var eaten: [String] = []
            var cases = 0
            for phrase in ["hey can you hear",
                           "testing can you hear me now",
                           "remind me to call the dentist tomorrow"] {
                let n = phrase.split(separator: " ").count
                for rate in [0.20, 0.35, 0.50] {
                    for k in [1, 2, n] {
                        for silence in [2.0, 2.61, 3.0, 5.0, 10.5] {
                            let first = say(phrase, from: 0, rate: rate, wordsPerPartial: k)
                            let start2 = Double(n - 1) * rate + silence
                            let second = say(phrase, from: start2, rate: rate,
                                             wordsPerPartial: k, after: phrase)
                            let rows = drive(first + second)
                            guard rows.count >= 2 else { continue }
                            cases += 1
                            if rows.contains(where: { $0.dropped }) {
                                eaten.append("\(n)w rate \(rate) k\(k) pause \(silence)")
                            }
                        }
                    }
                }
            }
            check("a person repeating themselves is never eaten, at any rate, "
                  + "pause or batching (\(cases) pairs, eaten: \(eaten))",
                  cases >= 90 && eaten.isEmpty)
        }

        // The two events at their closest, side by side, from the same clock.
        // This is the measurement that killed the window: they are the SAME
        // interval apart, so no width of window can hold one and pass the
        // other. The old code's comment claimed 2.0s against 3.4s.
        do {
            let spoken = say(saidOnce, from: 0, rate: 0.35, wordsPerPartial: 1)
            // The tightest a duplicate can be: the replaced window handed
            // over in ONE callback, the instant after the timer fired.
            let machine = drive(spoken + say(reRendered,
                                             from: spoken.last!.at + policy.utteranceGap + 0.01,
                                             rate: 0, wordsPerPartial: 5))
            let phrase = "hey can you hear"
            let n = 4, rate = 0.20
            let human = drive(say(phrase, from: 0, rate: rate, wordsPerPartial: n)
                              + say(phrase, from: Double(n - 1) * rate + 2.61 - Double(n - 1) * rate,
                                    rate: rate, wordsPerPartial: n, after: phrase))
            let machineApart = machine.count >= 2 ? machine[1].at - machine[0].at : -1
            let humanApart = human.count >= 2 ? human[1].at - human[0].at : -1
            check("the closest duplicate and the closest genuine repeat are the "
                  + "same distance apart, and only one of them is caught "
                  + "(machine \(machineApart)s caught=\(machine.count >= 2 && machine[1].dropped), "
                  + "human \(humanApart)s caught=\(human.count >= 2 && human[1].dropped))",
                  machineApart > 0 && humanApart > 0
                  && abs(machineApart - humanApart) < 0.001
                  && machine[1].dropped && !human[1].dropped)
        }

        // The tester's own thirty-second confirmation, end to end: say a
        // phrase, watch, say it again, watch, say it a third time. Three
        // utterances, three rows. Before the fix this produced two.
        do {
            let w = "remind me to call the dentist tomorrow"
            let rows = drive(say(w, from: 0, rate: 0.35, wordsPerPartial: 1)
                             + say(w, from: 10.5, rate: 0.35, wordsPerPartial: 1, after: w)
                             + say(w, from: 21.0, rate: 0.35, wordsPerPartial: 1,
                                   after: w + " " + w))
            check("three attempts at the same test phrase are three rows, not two "
                  + "(got \(rows.filter { !$0.dropped }.count))",
                  rows.filter { !$0.dropped }.count == 3)
        }

        // A break nobody answered must not eat a sentence a minute later. The
        // task rotates every couple of minutes whether anyone is speaking or
        // not, so a mark with nothing to expire it is a mode: the swap arms it
        // and the next repeat — whenever it comes — is deleted.
        do {
            let w = "hey can you hear"
            // The task rotates during the silence after the line went out —
            // an empty callback, because nobody is talking — and the person
            // says it again half a minute later.
            let rows = drive(say(w, from: 0, rate: 0.35, wordsPerPartial: 1)
                             + [Partial(at: 5, text: "", newTask: true)]
                             + say(w, from: 30, rate: 0.35, wordsPerPartial: 1))
            check("a task swap does not eat a sentence spoken long after it "
                  + "(got \(rows.filter { !$0.dropped }.count))",
                  rows.filter { !$0.dropped }.count == 2)
        }

        // ...and 250 words of continuous speech break no lineage at all, so
        // nothing in a monologue is ever a candidate for this guard.
        do {
            var script: [Partial] = []
            for i in spoken.indices {
                script.append(Partial(at: Double(i + 1) * 0.35,
                                      text: spoken[0...i].joined(separator: " "),
                                      newTask: false))
            }
            let rows = drive(script)
            check("nothing in a 250-word monologue is suppressed "
                  + "(\(rows.filter { $0.dropped }.count) of \(rows.count) dropped)",
                  rows.count >= 5 && !rows.contains { $0.dropped })
        }

        // --------------------------------------------- the two facts, alone
        // The lineage break is the ONLY thing that arms this. Without it the
        // cursor still holds the record of what it sent, so words it is
        // handing over now were never handed over before — whatever they say.
        let t = Date()
        check("with the lineage intact, identical words are never an echo",
              !policy.isEchoOfPrevious(saidOnce, previous: saidOnce,
                                       lineageBrokeAt: nil, wordsAppearedAt: t))
        check("a broken lineage catches the same words",
              policy.isEchoOfPrevious(saidOnce, previous: saidOnce,
                                      lineageBrokeAt: t, wordsAppearedAt: t))
        // Words that were already waiting when the window died are the ones
        // the cursor BANKS because they were never sent. Suppressing them is
        // the exact loss the cursor exists to prevent.
        check("words that predate the break are never suppressed",
              !policy.isEchoOfPrevious(saidOnce, previous: saidOnce,
                                       lineageBrokeAt: t,
                                       wordsAppearedAt: t.addingTimeInterval(-0.01)))
        // The arming reaches only as far as the pause that ends an utterance.
        // Held audio is replayed into the new request in the same breath as
        // the seam, so a re-rendering's words appear at once; anything a whole
        // utterance later was spoken.
        // Anchored to the reference date rather than written as `t + gap`,
        // so the boundary is REACHABLE. `t.addingTimeInterval(2.6)` measured
        // back gives 2.6000000000000005, which is outside the gap whichever
        // way the comparison is written — a check that reads the boundary that
        // way is green for `<` and for `<=` alike and pins neither.
        let zero = Date(timeIntervalSinceReferenceDate: 0)
        func atGap(_ d: Double) -> Date {
            Date(timeIntervalSinceReferenceDate: policy.utteranceGap + d)
        }
        check("the arming ends where an utterance ends",
              policy.isEchoOfPrevious(saidOnce, previous: saidOnce,
                                      lineageBrokeAt: zero, wordsAppearedAt: atGap(-0.01))
              && !policy.isEchoOfPrevious(saidOnce, previous: saidOnce,
                                          lineageBrokeAt: zero, wordsAppearedAt: atGap(0)))

        // --------------------------------------------- did it say anything new
        // The word test, which now carries no number at all. What it replaced
        // held three — a four-word floor, "at most two novel words", "70% of
        // the words shared" — and two of them could be moved without a single
        // check going red (research/2026-08-24-echo-guard.md).
        check("the same sentence re-rendered says nothing new",
              TranscriptFlushPolicy.addsNoWord(reRendered, beyond: saidOnce))
        check("a word-for-word repeat says nothing new",
              TranscriptFlushPolicy.addsNoWord("tell me a little bit more about yourself",
                    beyond: "tell me a little bit more about yourself"))
        check("a new thought is never swallowed",
              !TranscriptFlushPolicy.addsNoWord("let's do 7pm at Earls in West Van",
                    beyond: saidOnce))
        check("saying more about the same thing says something new",
              !TranscriptFlushPolicy.addsNoWord(
                    "I know where it is, it's the one by the water past the bridge",
                    beyond: saidOnce))
        // Restating a sentence and carrying on with it. Four of the words are
        // new and they are the whole point of the line — the case the old
        // novelty threshold was carrying, now answered by the mechanism.
        check("restating a sentence and adding to it says something new",
              !TranscriptFlushPolicy.addsNoWord(
                  "I need to call the dentist about my appointment tomorrow morning "
                  + "and reschedule it please",
                  beyond: "I need to call the dentist about my appointment tomorrow morning"))
        // Two of five words differ, which the old novelty leg permitted, and
        // those two words are a different errand for a different person.
        check("a different request built the same way says something new",
              !TranscriptFlushPolicy.addsNoWord("can you call Mum now",
                    beyond: "can you hear me now"))
        // ORDER, not membership. A set test would call this a re-rendering; a
        // recognizer does not hand the same sentence back backwards.
        check("the same words in a different order say something new",
              !TranscriptFlushPolicy.addsNoWord("is it know I yeah", beyond: reRendered))
        // No floor. The old guard refused to judge anything under four words,
        // and that constant was what the whole safety argument was computed
        // from — "four words at five words a second". It could be raised to
        // five, or half-deleted, with all 41 checks still green. There is no
        // number here to move now: three identical words are judged exactly
        // like thirty, and what protects "yeah yeah yeah" is that nobody's
        // decode window died in the middle of it.
        check("a short repetition says nothing new either",
              TranscriptFlushPolicy.addsNoWord("yeah yeah yeah", beyond: "yeah yeah yeah"))
        // ...and HOW MANY times counts. One "yeah" in the last line does not
        // account for three in this one; a match that could be spent twice
        // would let a whole new line hide behind a single repeated word.
        check("a word said three times is not accounted for by one",
              !TranscriptFlushPolicy.addsNoWord("yeah yeah yeah", beyond: reRendered))
        check("short natural repetition is still left alone with the lineage intact",
              !policy.isEchoOfPrevious("yeah yeah yeah", previous: "yeah yeah yeah",
                                       lineageBrokeAt: nil, wordsAppearedAt: t))
        // Nothing is not a re-rendering of something.
        check("an empty line is not an echo of anything",
              !TranscriptFlushPolicy.addsNoWord("   ", beyond: saidOnce))
        // The known miss, pinned rather than left to be rediscovered: a
        // re-rendering that SPLITS a word invents a token ("s") the first one
        // never had, so it survives. That is the safe direction — a duplicate
        // on the feed costs a line, a deleted sentence costs the sentence.
        check("a re-rendering that splits a word is NOT caught (known miss)",
              !TranscriptFlushPolicy.addsNoWord("Yeah I know where it's", beyond: saidOnce))

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
