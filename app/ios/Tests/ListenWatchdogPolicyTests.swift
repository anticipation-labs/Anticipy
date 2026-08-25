import Foundation

// Checks for ListenWatchdogPolicy — what the 4-second watchdog does about the
// state it finds.
//
// The failure being closed, seen on 2026-08-24: the rotation leg inside
// PhoneListener's watchdog fired only when `self.partial.isEmpty`. `partial` is
// assigned on EVERY recognizer result and cleared in exactly two places,
// neither of them a flush — so after the very first utterance of a recognition
// task it is never empty again, and that leg can never fire for the life of the
// task. A recognizer that goes deaf with NOTHING pending was therefore
// invisible: the UI says Listening, the ring looks healthy, and the day
// produces nothing. The "recognizer went silent" leg does not cover it, because
// that one requires words to be pending, which is the rarer state.
//
// Every question the watchdog answers is a question about TIME, so all of them
// can be answered here — pure Foundation, like TranscriptFlushPolicy,
// ListenJournal and ListenTally. No simulator, no scheme, no signing, no
// network, and — this is the point of the interruption case — no device that
// has to receive a real phone call before the answer can be checked.

@main
struct ListenWatchdogPolicyTests {
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

        let now = Date(timeIntervalSince1970: 1_756_000_000)
        func ago(_ seconds: TimeInterval) -> Date {
            now.addingTimeInterval(-seconds)
        }

        // ---------------------------------------------------- 1. the hole
        // The engine is up, audio is arriving, nothing is pending — and the
        // recognizer has not said a word in 130 seconds. `lastPartialAt` is a
        // real instant rather than nil BECAUSE the old blind spot needed
        // exactly one utterance to open: once something has been said on this
        // task, `partial` is never empty again and the old leg was dead.
        let deaf = ListenWatchdogPolicy.decide(
            engineRunning: true, hasTask: true, interrupted: false,
            lastBufferAt: ago(1), lastResultAt: ago(130),
            lastPartialAt: ago(130), requestBornAt: ago(200),
            hasPending: false, now: now)
        check("a recognizer silent for 130s with NOTHING pending is swapped",
              deaf == .rotate)

        // ---------------------------------------------------- 2. the guard
        // The request is ten minutes old, which is the only thing the old leg
        // ever measured. But someone is mid-sentence: a revision arrived 0.4s
        // ago and their words are unsent. `.rotate` does not flush, so rotating
        // here would drop a sentence out of the middle of a conversation.
        let midSentence = ListenWatchdogPolicy.decide(
            engineRunning: true, hasTask: true, interrupted: false,
            lastBufferAt: ago(0.2), lastResultAt: ago(0.4),
            lastPartialAt: ago(0.4), requestBornAt: ago(600),
            hasPending: true, now: now)
        check("a person mid-sentence (partial 0.4s ago) is never rotated",
              midSentence == .nothing)

        // ------------------------------- and the ordering that makes 1 safe
        // The same 130 seconds of silence, but this time with words unsent.
        // Rotation does not flush, so answering `.rotate` here would lose them.
        // It cannot: 130s is past the 8s deaf-with-pending window long before
        // it is past the 120s rotation window, so the swap that DOES flush is
        // reached first. That ordering is why rotation needs no `hasPending`
        // guard of its own — and why it must never grow one.
        let deafWithWords = ListenWatchdogPolicy.decide(
            engineRunning: true, hasTask: true, interrupted: false,
            lastBufferAt: ago(1), lastResultAt: ago(130),
            lastPartialAt: ago(130), requestBornAt: ago(200),
            hasPending: true, now: now)
        check("words pending are flushed across a swap, never lost to a rotation",
              deafWithWords == .swap(.taskLimit))

        // ---------------------------------------------------- 3. dead engine
        // Every other signal is screaming too — no recognition task, no buffer
        // and no result for five minutes, words pending — and the rebuild still
        // wins, because nothing below it can be honestly judged over an engine
        // that is not running.
        let dead = ListenWatchdogPolicy.decide(
            engineRunning: false, hasTask: false, interrupted: false,
            lastBufferAt: ago(300), lastResultAt: ago(300),
            lastPartialAt: nil, requestBornAt: ago(300),
            hasPending: true, now: now)
        check("a dead engine outranks everything", dead == .rebuild)

        // ---------------------------------------------------- 4. no audio
        // The engine reports itself running and not one buffer has reached the
        // tap for seven seconds. iOS does this with no notification of any
        // kind, which is the whole reason a timer has to ask.
        let starved = ListenWatchdogPolicy.decide(
            engineRunning: true, hasTask: true, interrupted: false,
            lastBufferAt: ago(7), lastResultAt: ago(0.5),
            lastPartialAt: ago(0.5), requestBornAt: ago(30),
            hasPending: true, now: now)
        check("a stale lastBufferAt rebuilds", starved == .rebuild)

        // ---------------------------------------------------- 5. a phone call
        // Three minutes into a call, with every other signal screaming: the
        // engine is down, no buffer and no result for 300 seconds, words
        // pending. Today that is `recoverAudio` on every tick, and
        // `recoverAudio` ends in `swapRecognition` — 45 fresh
        // SFSpeechRecognitionTasks in three minutes, not one of which can hear
        // anything, because the microphone belongs to the call.
        //
        // `.standDown` is not "do nothing". The call site still retries the
        // engine, which is the only path that notices a call ending when iOS
        // never delivers `.ended` — it sometimes doesn't. It leaves the
        // recognition task alone.
        let onACall = ListenWatchdogPolicy.decide(
            engineRunning: false, hasTask: true, interrupted: true,
            lastBufferAt: ago(300), lastResultAt: ago(300),
            lastPartialAt: nil, requestBornAt: ago(300),
            hasPending: true, now: now)
        // The two wrong answers are wrong in different ways and both are named
        // here: `.rebuild` swaps the task on its way through `recoverAudio`,
        // and any swap mints one outright.
        var mintedATask = false
        if case .swap = onACall { mintedATask = true }
        check("while a call owns the microphone the recognition task is left alone",
              onACall == .standDown && onACall != .rebuild
                  && !mintedATask && onACall != .rotate)

        // ---------------------------------------------------- 6. young request
        // Guards the rotation leg's SECOND clause on its own: the quiet is far
        // past the rotation window and only the age of the request stands
        // between this tick and a swap. Without that clause a genuinely quiet
        // minute becomes a fresh recognition task every four seconds, each one
        // too young to have heard anything — the exact churn rotation exists to
        // avoid.
        let young = ListenWatchdogPolicy.decide(
            engineRunning: true, hasTask: true, interrupted: false,
            lastBufferAt: ago(1), lastResultAt: ago(300),
            lastPartialAt: nil, requestBornAt: ago(10),
            hasPending: false, now: now)
        check("a young request is not rotated however quiet it has been",
              young == .nothing)

        // ------------------------------------------- 7. the drill, 45 ticks
        // Check 5 asks the call question once, at one instant. The churn was
        // never one wrong answer: it was the SAME wrong answer every four
        // seconds for the length of the call, and a policy can be right on one
        // tick and wrong for all of a three-minute call. So this steps the
        // clock through the whole outage — 180 seconds, 4 seconds at a time,
        // 45 ticks, which is the exact number of SFSpeechRecognitionTasks the
        // old body minted while the microphone belonged to somebody else.
        //
        // Everything below `interrupted` is screaming for the whole stretch,
        // deliberately: the engine never comes up (`configureAndStartEngine`
        // returns at the 0 Hz guard, because a silenced input reports 0 Hz),
        // no buffer and no result has arrived since the call took the
        // microphone, words are left pending, and the request is five minutes
        // old — past the rotation window on every single tick. Every leg has a
        // reason to fire and none of them may.
        let callBegan = now
        var duringTheCall: [ListenWatchdogPolicy.Action] = []
        for tick in 1...45 {
            duringTheCall.append(ListenWatchdogPolicy.decide(
                engineRunning: false, hasTask: true, interrupted: true,
                lastBufferAt: callBegan, lastResultAt: callBegan,
                lastPartialAt: nil,
                requestBornAt: callBegan.addingTimeInterval(-300),
                hasPending: true,
                now: callBegan.addingTimeInterval(Double(tick) * 4)))
        }
        let mintedATaskDuringTheCall = duringTheCall.contains { action in
            if case .swap = action { return true }
            return action == .rotate
        }
        // THE COUNT, not only the absence. `.nothing` 45 times would satisfy an
        // absence-only check while having quietly stopped retrying the engine —
        // a different bug wearing the same symptom, because that retry is the
        // only thing that notices a call ENDING when iOS never delivers
        // `.ended`. Standing down has to mean standing down 45 times.
        let stoodDown = duringTheCall.filter { $0 == .standDown }.count
        check("a call that began 3 minutes ago never swapped the recognition task",
              duringTheCall.count == 45 && !mintedATaskDuringTheCall
                  && stoodDown == 45)

        // ------------------------------------------------------------ result
        print("")
        if failures.isEmpty {
            print("ListenWatchdogPolicy: all \(checks) checks passed")
        } else {
            print("ListenWatchdogPolicy: \(failures.count)/\(checks) FAILED")
            for f in failures { print("  - \(f)") }
            exit(1)
        }
    }
}
