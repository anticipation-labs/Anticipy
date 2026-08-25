import Foundation

/// What the 4-second watchdog should do about the state it finds.
///
/// THE HOLE THIS CLOSES, 2026-08-24. The rotation leg inside the watchdog fired
/// only when `self.partial.isEmpty`. `partial` is assigned on EVERY recognizer
/// result and cleared in exactly two places — the start of a recognition task
/// and the stop path — neither of them a flush. So after the very first
/// utterance of a task, `partial` is never empty again and that leg could never
/// fire for the life of the task. A recognizer that goes deaf with NOTHING
/// pending was therefore invisible: the UI says Listening, the ring looks
/// healthy, and the day produces nothing. The "recognizer went silent" leg does
/// not cover it either, because that one requires words to be PENDING, which is
/// the rarer state.
///
/// Every question the watchdog asks is a question about TIME — when did a
/// buffer last arrive, when did the recognizer last revise, how old is this
/// request — so all of them can be answered with no engine, no recognizer, no
/// Timer and no transcript. Pure Foundation, like `TranscriptFlushPolicy`,
/// `ListenJournal` and `ListenTally`: the instrument used to judge the audio
/// path is itself verifiable with `swiftc` alone, with no simulator, signing or
/// network — and, for the interruption case, with no device that has to receive
/// a real phone call.
///
/// Unlike `ListenTally`, this type MUST have a call site.
/// `Tests/run_watchdog_policy_tests.sh` fails the build if `PhoneListener` ever
/// stops asking it, because a green suite over a function nothing calls is the
/// blind spot back in production with a passing test vouching for it.
struct ListenWatchdogPolicy {
    /// What the watchdog does, named by intent rather than by the method it
    /// happens to call today. `.rotate` is deliberately its own case and not
    /// `.swap(.silenceRotation)`: it is the ONE swap that must not flush, and a
    /// call site that has to remember that from the cause alone will eventually
    /// forget.
    enum Action: Equatable {
        case rebuild
        case startRecognition
        case swap(ListenEvent.SwapCause)
        case rotate
        case standDown
        case nothing
    }

    /// Audio has not reached the tap for this long. The engine reports itself
    /// running and nothing is arriving; iOS does this with no notification of
    /// any kind, which is why a timer has to ask.
    static let bufferStaleSeconds: TimeInterval = 6
    /// Words are on screen unsent and the recognizer has said nothing for this
    /// long. A healthy one streams continuously, so this is Apple's
    /// task-duration limit landing without ever finalising.
    static let deafWithPendingSeconds: TimeInterval = 8
    /// How long a recognition task may hear nothing at all before it is
    /// replaced.
    static let rotationSeconds: TimeInterval = 120

    /// THE ORDER IS THE BEHAVIOUR. Each leg below is only meaningful because
    /// the ones above it did not fire.
    static func decide(engineRunning: Bool,
                       hasTask: Bool,
                       interrupted: Bool,
                       lastBufferAt: Date,
                       lastResultAt: Date,
                       lastPartialAt: Date?,
                       requestBornAt: Date,
                       hasPending: Bool,
                       now: Date) -> Action {
        // FIRST, above the dead engine below, and that ranking is the whole
        // point. While a call owns the microphone every other signal here is a
        // lie: no buffers arrive, no results arrive, and the engine is down
        // because `configureAndStartEngine`'s 0 Hz guard refused to install a
        // tap on a 0 Hz input. Letting the dead engine win means `recoverAudio`
        // on every tick, and `recoverAudio` ends in `swapRecognition` — a fresh
        // SFSpeechRecognitionTask every 4 seconds for the length of the call,
        // 45 of them in three minutes, not one of which can hear anything.
        //
        // Standing down is not standing still: the call site still retries the
        // engine, which is the only path that notices a call ending when iOS
        // never delivers `.ended`. It costs nothing — the retry returns at the
        // 0 Hz guard — and it leaves the recognition task alone.
        if interrupted { return .standDown }

        // A dead engine is a failure, not a route change. This is the one stall
        // the watchdog was built to catch, and nothing below it can be judged
        // honestly over an engine that is not running.
        if !engineRunning { return .rebuild }

        // No recognizer at all: there is nothing for the timing legs to be
        // about until there is one.
        if !hasTask { return .startRecognition }

        // The engine says it is running and the microphone has gone quiet
        // underneath it. Silent, and unannounced by iOS.
        if now.timeIntervalSince(lastBufferAt) > bufferStaleSeconds {
            return .rebuild
        }

        // Words unsent and the recognizer has stopped streaming. Apple's
        // task-duration limit is the known reason a healthy recognizer goes
        // quiet without ever finalising, and this swap FLUSHES, so the words
        // cross the seam instead of dying with the task.
        if hasPending, now.timeIntervalSince(lastResultAt) > deafWithPendingSeconds {
            return .swap(.taskLimit)
        }

        // THE LEG THE BLIND SPOT WAS IN. Judged on when something last ARRIVED,
        // never on what it said — that substitution IS the fix.
        //
        // Deliberately no `hasPending` guard, and it must never grow one.
        // `.rotate` does not flush, so rotating over pending words would drop
        // them — but that state cannot reach here: a stale `lastResultAt` with
        // words pending is caught by the leg above, because 130 seconds of
        // silence is past 8 long before it is past 120. The ordering is what
        // makes "swap whether or not words are pending" safe, and a guard added
        // here would re-open the hole for the commonest case of all.
        let quietSince = max(lastResultAt, lastPartialAt ?? Date.distantPast)
        if now.timeIntervalSince(quietSince) > rotationSeconds,
           // ...and the task is old enough to be worth replacing. Without this
           // clause a request born seconds ago that has not heard anything yet
           // is swapped on every tick, so a genuinely quiet minute becomes
           // fifteen recognition tasks — the churn rotation exists to avoid.
           now.timeIntervalSince(requestBornAt) > rotationSeconds {
            return .rotate
        }

        return .nothing
    }
}
