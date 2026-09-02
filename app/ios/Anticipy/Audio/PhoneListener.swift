import AVFoundation
import Foundation
import Speech
// For the background task assertion held across an interruption. This file is
// not a pure policy file — it owns AVAudioEngine and SFSpeechRecognizer and
// could never be compiled by swiftc alone — so the rule that keeps UIKit out
// of the policies does not bind it. The decisions it makes live in
// ListenWatchdogPolicy and ListenResumePolicy, which stay pure.
import UIKit

/// Pendant-less listening: the phone's own microphone feeds Apple's speech
/// recognizer (on-device when supported), emitting one line per utterance.
/// This is the same transcript stream the pendant produces, so everything
/// downstream — brain, memory, jobs — is identical.
///
/// DESIGN, rewritten 2026-07-31 after a real conversation produced exactly ONE
/// line in production:
///
/// The old design ended the recognition request at every pause to force a
/// final result. But the microphone tap keeps delivering audio into a request
/// that has already been ended — those buffers are discarded — and the
/// replacement request only exists once the final callback arrives, hundreds
/// of milliseconds later. In continuous speech that gap swallowed most of what
/// was said, which is exactly what happened: a whole conversation arrived as
/// "What time is it on Monday".
///
/// Now the request is NEVER ended while someone is talking. One long-lived
/// recognition task streams partial results; we watch the running text and
/// emit a line when it stops changing (a natural pause). Everything after that
/// keeps accumulating in the SAME request, so no audio is ever orphaned. Any
/// unavoidable swap (error, interruption, rotation) buffers the microphone
/// audio and replays it into the new request.
///
/// Listening is also SELF-HEALING: iOS kills mic capture constantly (Siri,
/// calls, notification sounds, AirPods, media-services resets); observers plus
/// a watchdog bring the chain back, and `suspended` says so honestly instead
/// of glowing "Listening" over a dead microphone.
final class PhoneListener: NSObject, ObservableObject {
    @Published var isListening = false
    @Published var partial = ""
    @Published var authorized = true
    /// True while the user wants listening but the mic is down (interruption,
    /// route change) and recovery is in progress. The UI must say so.
    ///
    /// IT OWNS THE BACKGROUND ASSERTION, and that is why the observer is here
    /// rather than at the notification that seems to be about interruptions.
    /// The assertion is running time bought for getting the microphone back, so
    /// it is worth holding for exactly as long as the microphone is gone — and
    /// this is the one line every route to "gone" and back passes through.
    ///
    /// Keyed on the notification instead, it leaked both ways. `.began` took it
    /// and only `.ended` released it, but `suspended` also clears in
    /// `configureAndStartEngine` when the engine comes back up: Siri dismissed
    /// with no `.ended` delivered (iOS sometimes sends none) left listening
    /// healthy and an assertion held over nothing — and at the next
    /// backgrounding iOS grants and burns ~30s of background execution on an
    /// app that has nothing to do with it. And releasing it ON
    /// `.ended` spent it a beat too early: a call ending with the phone in a
    /// pocket finds an input still reporting 0 Hz, `suspended` goes straight
    /// back to true, and the app is left with no audio flowing and no assertion
    /// — suspended by iOS, watchdog frozen, listening gone until somebody opens
    /// the app. The thirty seconds this buys was exactly the window that retry
    /// needed.
    @Published var suspended = false {
        didSet {
            // Edges only. `configureAndStartEngine` assigns this on every
            // watchdog tick of a call, and re-taking an assertion each time
            // would hand back a fresh thirty seconds forever — which is not
            // what iOS grants, and orphans an identifier per tick.
            guard suspended != oldValue else { return }
            // Every writer of this flag is on the main queue (the two
            // notification observers are registered with `queue: .main`, the
            // watchdog Timer runs on the main runloop, and `begin()`/`stop()`
            // are called from the UI), which is where UIApplication expects
            // these two calls.
            if suspended {
                beginBackgroundAssertion()
            } else {
                endBackgroundAssertion()
            }
        }
    }

    /// Is she actually hearing you at this moment?
    ///
    /// `isListening` is the owner's standing wish and stays true for the whole
    /// of a phone call, so a screen that asks it gets "yes" while a call holds
    /// the input. FIVE places asked it that way, not four. Four of them speak
    /// about the microphone and were wrong — the listening control's own dot,
    /// the home screen's greeting dot, the settings headline, the briefing's
    /// idle line — and they ask this instead. The wave bars wrote
    /// `isListening && !suspended` by hand and were the only site already
    /// right, which is the whole argument for one name over an expression
    /// copied per view.
    ///
    /// THE FIFTH IS ONBOARDING'S "I'm listening. Thank you.", AND IT STAYS ON
    /// `isListening`. It sits in the `isListening` arm of a three-way branch
    /// about whether PERMISSION landed, so answering it with `capturing` would
    /// drop somebody who had just granted the microphone into the copy that
    /// asks them to grant it. The same words asking a different question.
    /// `run_control_policy_tests.sh` scopes its scan to the two other view
    /// files for that reason, and its comment there says so — this count is
    /// written out because a closed count that is quietly open is how the
    /// previous version of this note read.
    var capturing: Bool {
        ListenControlPolicy.capturing(isListening: isListening,
                                      suspended: suspended)
    }

    /// A finished line, BOTH instants that bracket it, and whether it carries
    /// on from the line before it.
    ///
    /// The instants travel WITH the words because the push can be much later
    /// than the speech: a line buffered offline and sent hours afterwards used
    /// to reach the backend stamped with the moment the network came back, so
    /// a whole buffered conversation looked like it happened in one second.
    ///
    /// TWO Dates, not one, and this is the fix rather than a tidy-up. This
    /// closure carried a single instant, so `pushEvent` had a single instant to
    /// write into `capture_started_at`, `spoken_at` and `capture_ended_at`
    /// alike — three columns, one number, and `end - start` identically zero
    /// for every row this product has ever stored. `deliver` has had both ends
    /// in scope the whole time and only one of them could get out.
    ///
    /// `startedAt` is when the words first went unsent; `endedAt` is the
    /// instant the flush produced the line. A caller that passes the flush
    /// instant for both satisfies this signature and reproduces the entire
    /// defect, which is what the wiring legs in
    /// `Tests/run_capture_envelope_tests.sh` are watching for.
    var onLine: ((_ line: String, _ startedAt: Date, _ endedAt: Date, _ continuesPrevious: Bool) -> Void)?
    /// Who said it, decided on this device. Fires with the same line that
    /// went to `onLine`, carrying "owner" / "other:<who>" — or nil when the
    /// phone cannot honestly say, which the brain reads as no verdict.
    var onSpeaker: ((_ line: String, _ speaker: String?, _ startedAt: Date, _ endedAt: Date, _ continuesPrevious: Bool) -> Void)?
    /// The on-device voice check. Optional: without a model the app runs
    /// exactly as it did before speaker recognition existed.
    var speaker: SpeakerTagger?
    /// True while recording a voice sample for enrollment. Audio still
    /// feeds the voice check; nothing is transcribed, emitted or sent.
    var enrolling = false

    private var engine = AVAudioEngine()
    /// True only after this exact engine accepted its input tap. A route
    /// rebuild replaces the engine instead of removing and reinstalling a tap
    /// on the same input node: `installTap` raises an Objective-C exception,
    /// and terminates the process, when AVFAudio still sees the old tap during
    /// route churn.
    private var tapInstalled = false
    /// Route notifications are delivered synchronously on the main queue.
    /// Re-entering AVFAudio from inside one is what the build 75/109/111 crash
    /// reports show, so the rebuild happens on the next main-queue turn and
    /// duplicate notifications collapse into one job.
    private var scheduledAudioRecovery: DispatchWorkItem?
    private var scheduledAudioRecoveryCause: ListenEvent.SwapCause?
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en_US"))
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    // iOS 26's SpeechTranscriber, when the device has it. Nil on the legacy
    // path — the two engines never run at once, and everything downstream
    // (cursor, flushes, journal, orphan buffers) is engine-blind on purpose:
    // the recognizer is the one swappable part, not the listening rules.
    private var analyzerEngine: (any ListenRequestEngine)?
    private var usingAnalyzer = false
    /// An engine that cannot provision its model is an outage to route
    /// around, not to retry into forever: three failures and this session
    /// finishes on the legacy recognizer. Session-scoped on purpose — the
    /// next listen starts optimistic again, because maybe the download
    /// finished while the phone sat in a pocket.
    private var analyzerFailures = 0
    private var analyzerDisabledForSession = false
    private var silenceFlush: DispatchWorkItem?
    private var watchdog: Timer?
    private var observersInstalled = false
    /// Held for the life of the process, like the observers.
    private var callSense: CallSense?

    /// Held only across an interruption, and worth ROUGHLY THIRTY SECONDS —
    /// not a phone call.
    ///
    /// `UIBackgroundModes: audio` buys background execution only while audio is
    /// actually flowing. During an interruption none is: the engine is stopped
    /// and `configureAndStartEngine` returns at the 0 Hz guard without
    /// installing a tap. There is no `processing` or `fetch` mode in this app
    /// and `bluetooth-central` only fires for a pendant nobody has flashed, so
    /// without this assertion iOS can suspend the process the moment capture
    /// stops — and `.ended` arrives to an app that is not running, or never
    /// arrives at all.
    ///
    /// What thirty seconds actually covers: Siri, a notification tapped and
    /// dismissed, a fifteen-second call declined. Most interruptions by count,
    /// and none of the long ones. A ten-minute call still suspends the app;
    /// `ListenResumePolicy` is what makes THAT case recoverable, when the owner
    /// next opens the app.
    ///
    /// iOS TERMINATES an app that lets an assertion expire without ending it,
    /// which is why `endBackgroundAssertion` is also the expiration handler
    /// rather than politeness.
    private var backgroundTask: UIBackgroundTaskIdentifier = .invalid

    /// Which words of the current task's text have already been sent as lines.
    ///
    /// Not a count. A count was the bug: Apple REWRITES its transcript rather
    /// than appending to it ("Cineplex" becomes "the Cineplex"), so the moment
    /// a word is inserted or dropped near the front, an index points at the
    /// wrong word and one sentence goes out as two overlapping fragments. The
    /// cursor remembers the words themselves and re-finds them every time.
    private var cursor = TranscriptCursor()
    /// Audio captured while no request is accepting it, replayed into the next
    /// one so a swap can never lose speech.
    private var orphanBuffers: [AVAudioPCMBuffer] = []
    private let orphanLock = NSLock()
    private var acceptingAudio = false

    /// The last session facts actually recorded, so the same ones are not
    /// written again. Cleared by `stop()`: a new session is a new thing to
    /// describe, and the churn this guards against is per-watchdog-tick, not
    /// per-session.
    ///
    /// The VALUE, not the sentence it renders as — comparing two
    /// `ListenSessionFacts` is the compiler's job, and holding a String here
    /// would put a second mutable transcript-shaped variable back in this file.
    private var lastSessionFacts: ListenSessionFacts?

    /// The last battery reading actually recorded, so the same one is not
    /// written again. The thing that reads the battery is the 4-second
    /// watchdog, and an unguarded write there is fifteen lines a minute — the
    /// measured rate that evicts the 400-line ring in twenty-seven minutes and
    /// turns a day that went deaf at nine in the morning into a blank, healthy
    /// report. Cleared by `begin()` so every session writes its opening
    /// reading: without that, a session starting at the same percentage the
    /// last one ended at has nothing to measure its first stretch from.
    private var lastBatteryReading: BatteryReadingPolicy.Reading?

    private var lastBufferAt = Date()
    private var lastResultAt = Date()
    private var requestBornAt = Date()
    private var bufferTick = 0
    /// Buffers thrown away because the orphan hold was full — audio the
    /// recognizer will never see. Incremented on the audio thread under
    /// `orphanLock`, drained and reported by the watchdog on the main queue.
    private var orphanDropped = 0

    /// When the currently-unsent words first appeared, and the ceiling on how
    /// long they may wait.
    ///
    /// The silence flush is a DEBOUNCE: every partial result cancels the
    /// pending timer and schedules a new one. Someone speaking continuously
    /// produces partials faster than the gap, so the timer NEVER fires and
    /// nothing is sent for the whole monologue — until the recognizer hits
    /// Apple's task limit, finalises (often COLLAPSING its hypothesis, which
    /// the callback below documents), and the swap resets the cursor. The
    /// words the collapsed final no longer contains die there.
    ///
    /// Watched live 2026-08-16: ~250 words spoken continuously reached the
    /// backend as three fragments totalling 71 characters — the opening, a
    /// piece of the middle, and the tail. "Every time I talk for a long
    /// period and then talk too quickly, the transcript doesn't save."
    ///
    /// So: pending words are sent at a pause OR after this ceiling, whichever
    /// comes first. Long enough not to chop a flowing sentence, short enough
    /// that a fast talker never outruns it.
    private var pendingSince: Date?
    /// When the recognizer last revised its hypothesis: the only evidence this
    /// object has that someone is still mid-sentence.
    ///
    /// Load-bearing, not decoration. `flushReason` measures silence from this,
    /// and the ceiling (8s) is longer than the gap (2.6s), so a caller that
    /// cannot say when the last partial arrived makes `.ceiling` UNREACHABLE
    /// for every input there is — every flush reads as a finished thought, no
    /// cut is ever marked, and nothing goes red to say so.
    ///
    /// Not `lastResultAt`, which also moves on an error callback, where
    /// nothing was heard at all.
    private var lastPartialAt: Date?
    private let flushPolicy = TranscriptFlushPolicy()
    /// The last line actually handed over, so the same sentence arriving
    /// again in different words can be recognised as itself.
    ///
    /// It carried the instant it went out as well, for an elapsed-time
    /// comparison that no longer exists and could not have worked: see
    /// `TranscriptFlushPolicy.isEchoOfPrevious`. Keeping a timestamp nothing
    /// reads is how the next reader concludes there is still a window here.
    private var lastDelivered: String?
    /// WHEN the cursor last lost its record of what it had already sent, or
    /// nil once that break has been answered.
    ///
    /// This is the ONLY thing that can tell a recognizer re-rendering an
    /// utterance from a person saying it again, and the phone has always known
    /// it and never passed it on. Words already sent can come back as unsent
    /// words in exactly two ways — a decode window replaced under them
    /// (`update.didReset`) or a recognition task retired and its held audio
    /// replayed into a fresh one (`cursor.reset()` below) — and both of those
    /// are events here, not inferences about wording. A person repeating
    /// themselves inside one task breaks nothing.
    ///
    /// Cleared by the next delivery, whatever that delivery is: one break
    /// answers for one line. It is not a mode.
    private var lineageBrokeAt: Date?
    /// Whether this recognition task has sent anything yet — see the final
    /// handler, where it decides a polish from a whole unsent monologue.
    private var everEmittedThisTask = false
    /// WHEN the clock last cut a line off mid-sentence, or nil if it has not.
    ///
    /// Two lessons live in this one property, and both were bugs.
    ///
    /// WHICH line carries the mark. `.ceiling` describes how a line ENDED: the
    /// clock ran out while the recognizer was still revising. It says nothing
    /// about how that line BEGAN, so the line that carries on from a cut is the
    /// NEXT one. Marking the ceiling-flushed line itself chained the head of a
    /// monologue onto whatever unrelated sentence came before it, orphaned the
    /// tail, and for the commonest shape (one cut, then a pause) produced only
    /// false edges.
    ///
    /// HOW LONG the mark lasts. A bare "the last flush was a cut" flag has no
    /// way to stop being true: a cut takes every pending word, so if the
    /// speaker then goes quiet without the recognition task ending, no flush
    /// and no new task ever clears it, and the brand-new thought spoken minutes
    /// later went out as a continuation of a sentence nobody was still saying.
    /// Keeping the INSTANT instead of a flag lets `flushPolicy.cutContinues`
    /// answer that with the same pause that ends an utterance everywhere else,
    /// and it is checked at the one place the mark is read.
    private var cutAt: Date?

    /// A pause this long ends an utterance. 2.6s, not shorter: people pause
    /// mid-thought ("I'll send the invoice… tomorrow"), and chopping there
    /// splits one intent into fragments. Nothing is closed to achieve this —
    /// the line is simply cut from the running text.
    private let utteranceGap: TimeInterval = 2.6

    func start() {
        SFSpeechRecognizer.requestAuthorization { [weak self] auth in
            guard let self else { return }
            guard auth == .authorized else {
                // Say WHY nothing was heard. Without this line, a session that
                // was never permitted to start and a session that started and
                // captured nothing read identically afterwards, and permission
                // is the first suspect a failed manual test has to rule out.
                ListenJournal.shared.record(.sessionStopped(cause: .authorizationLost))
                DispatchQueue.main.async { self.authorized = false }
                return
            }
            AVAudioSession.sharedInstance().requestRecordPermission { ok in
                DispatchQueue.main.async {
                    guard ok else {
                        ListenJournal.shared.record(.sessionStopped(cause: .authorizationLost))
                        self.authorized = false
                        return
                    }
                    // Set it back to TRUE on the way through. Nothing anywhere
                    // used to do this, so one "Don't Allow" branded the app
                    // permanently broken: even after granting access in iOS
                    // Settings, the refusal message stayed on screen forever
                    // and the only way out was deleting the app.
                    self.authorized = true
                    self.begin()
                }
            }
        }
    }

    /// Has the user already refused, so we know not to pretend a tap will work?
    /// iOS only ever shows its alert once — after that, `start()` is a silent
    /// no-op and only the Settings app can change the answer.
    var permissionDenied: Bool {
        SFSpeechRecognizer.authorizationStatus() == .denied
            || SFSpeechRecognizer.authorizationStatus() == .restricted
            || AVAudioSession.sharedInstance().recordPermission == .denied
    }

    private func begin() {
        // Re-entrancy guard: onAppear + scenePhase both fire at launch, and
        // isListening can't be checked by callers because start() runs through
        // two async permission callbacks. Two begin()s = two recognition
        // chains = duplicated lines. begin() only ever arrives via
        // DispatchQueue.main.async, so this guard is race-free.
        guard !isListening else { return }
        installObserversOnce()
        installCallSenseOnce()
        // OFF BY DEFAULT IN EVERY APP, and until it is on `batteryLevel` is
        // -1.0 forever. `BatteryReadingPolicy` correctly refuses that as
        // unreadable, so without this one line the journal records no readings,
        // the tally folds zero, and the Listening screen says "Not recorded" on
        // a phone that is spending battery all day — a whole instrument green
        // end to end and measuring nothing. `run_battery_tests.sh` fails if it
        // goes.
        UIDevice.current.isBatteryMonitoringEnabled = true
        isListening = true
        lastBatteryReading = nil
        ListenJournal.shared.record(.sessionStarted)
        lastBufferAt = Date()
        lastResultAt = Date()
        configureAndStartEngine()
        startRecognition()
        startWatchdog()
    }

    /// (Re)build the capture chain: audio session, tap (with the CURRENT
    /// route's format — it changes when the mic changes), engine.
    private func configureAndStartEngine() {
        let session = AVAudioSession.sharedInstance()
        // .measurement is deliberate and matches Apple's own SFSpeechRecognizer
        // sample: minimal input processing, and the primary mic pinned on
        // multi-mic devices. A haptics build must NOT quietly change the
        // transcription pipeline on a hunch — if the diagnostic proves the mode
        // is what mutes the Taptic Engine, that becomes its own change.
        // MIXABLE, BECAUSE `.record` COULD NOT SHARE THE PHONE WITH ANYTHING.
        //
        // `.record` is an exclusive category: the moment another app starts
        // playing, iOS interrupts this session, the engine stops, `suspended`
        // goes true, and the background assertion above — worth roughly thirty
        // seconds — is all that keeps the process alive. Put a YouTube video
        // on and walk away and she is not listening; leave it playing and the
        // app is eventually suspended outright, which is the "crashes when
        // media plays" report. `.duckOthers` did not soften that either: it is
        // only consulted for categories that can mix at all, so on `.record` it
        // was decoration on an exclusive session.
        //
        // `.playAndRecord` + `.mixWithOthers` is the only combination that lets
        // her keep a live input while another app owns playback —
        // `.mixWithOthers` is REFUSED on `.record`, so this is a category
        // change or it is nothing.
        //
        // `.defaultToSpeaker` is not optional here and is the part most likely
        // to be dropped by someone tidying this line: `.playAndRecord` routes
        // output to the RECEIVER by default, so without it the first effect of
        // this change is somebody's music jumping to the earpiece the moment
        // she starts listening.
        //
        // `.measurement` is UNCHANGED and deliberately so. The note below is
        // about the mode, not the category, and it still stands: minimal input
        // processing, primary mic pinned, matching Apple's own SFSpeechRecognizer
        // sample. This commit moves exactly one thing.
        //
        // UNPROVEN ON A DEVICE. The simulator has no second app playing audio,
        // so nothing here proves the route survives a real YouTube session, and
        // `.playAndRecord` can change which input is chosen on a multi-mic
        // phone. The read-back below prints what the session ACTUALLY became;
        // check it on a handset with something playing before believing this.
        try? session.setCategory(.playAndRecord, mode: .measurement,
                                 options: [.mixWithOthers, .defaultToSpeaker,
                                           .allowBluetoothHFP])
        // iOS MUTES the Taptic Engine for the whole app while a .record session
        // is active, so the buzz can't bleed into the mic. She starts listening
        // milliseconds after launch (keepListening is a standing state), so
        // without this every haptic in the app died before a finger touched
        // anything — the "I feel no haptics anywhere" report on build 32.
        // Nothing surfaces the suppression: no error, no log.
        try? session.setAllowHapticsAndSystemSoundsDuringRecording(true)
        try? session.setActive(true, options: .notifyOthersOnDeactivation)
        // READ IT BACK. The three try? calls above are the entire audio
        // configuration and each one swallows its error, so the app can report
        // "Listening" over a session it never actually got — silently, on some
        // device or iOS version we do not own. Asking the session what it
        // became is the cheapest possible way to see that, and HapticEngine
        // already proves these are readable at runtime. Also note low power
        // mode here: it changes what the OS will let a background app do, and
        // a day that died on a throttled phone otherwise looks like a bug.
        //
        // WRITTEN WHEN IT CHANGES, not on a flag. These lines sat unguarded and
        // obeyed nothing: while a call holds the microphone the 4s watchdog
        // calls this method on every tick, so they wrote 15 identical lines a
        // minute — 30 in low power. Measured: the 400-line ring is fully evicted
        // in 27 minutes and the two 256 KB files in about five hours of outage,
        // so the one `.sessionStopped(cause: .interruption)` line that explains
        // the whole day rotates away and the screen folds ~4,500 `.noted` events
        // into `sessions 0 / listening none / longest silence none / words 0`. A
        // blank, healthy-looking report on a dead day, produced by the
        // instrument built to make that day visible.
        //
        // A `!suspended` gate killed that churn and one more thing with it: the
        // line on the tick the call ENDS, which is the single moment these facts
        // are worth having, because that is when the session may have come back
        // as something else — a call that began on Bluetooth ending on speaker.
        // Comparing to the last line recorded kills 210 repetitions of one
        // sentence and keeps every sentence that is new. When nothing changed,
        // silence is right: `.sessionStarted` already says capture came back,
        // and repeating an unchanged fact adds nothing.
        //
        // A VALUE, NOT A SENTENCE BUILT UP IN A LOCAL. This used to be
        // `var facts = "…"` with a `+=` under it, and the entire privacy claim
        // rested on `run_journal_tests.sh` reading every line that gave that
        // local a value. A reviewer wrote two working leaks past that reading:
        // `self.facts += self.partial` (the scan could not see a write through
        // `self.`) and `(facts, lastSessionFacts) = (self.partial, "")` (a shape
        // it did not recognise, and therefore read as a harmless mention). Both
        // are scan failures now, and neither COMPILES any more:
        // `ListenSessionFacts` is not a String, so there is no `+=`, no
        // `.append` and no tuple assignment that can put a transcript into it.
        //
        // Low power is folded into the same VALUE rather than journalled beside
        // it: it is a fact about the same session, and two records would need
        // two change-detectors to say one thing.
        //
        // `facts.sentence` IS AN EXPRESSION `run_journal_tests.sh` HAS BEEN TOLD
        // IS SAFE, about this FILE and this expression together — never a bare
        // word, which five other bindings in AnticipyApp.swift and
        // SupervisedReadView.swift already carry. The gate earns that exception
        // rather than taking it, in two places: the construction below is read
        // whole and its argument list must match the allowlist character for
        // character, and `ListenSessionFacts.sentence`'s body goes through the
        // same two passes a journal literal gets.
        let facts = ListenSessionFacts(category: session.category.rawValue,
                                       mode: session.mode.rawValue,
                                       lowPower: ProcessInfo.processInfo.isLowPowerModeEnabled)
        if facts != lastSessionFacts {
            lastSessionFacts = facts
            ListenJournal.shared.record(.sessionFacts(facts))
        }

        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        // While a phone call owns the session, the input format can be
        // 0 Hz / 0 channels — installTap with it raises an NSException that
        // no try? can catch. Stand down; the watchdog retries after the call.
        guard format.sampleRate > 0, format.channelCount > 0 else {
            // Recorded once per outage, not once per watchdog tick: the 4s
            // watchdog retries this path for as long as the call lasts, and a
            // journal that spends all 400 of its lines saying the same thing
            // has evicted the session it was meant to explain.
            if !suspended {
                ListenJournal.shared.record(.sessionStopped(cause: .interruption))
            }
            suspended = true
            return
        }
        // Every call after the first goes through replaceCaptureEngine(), so
        // there cannot already be a tap on this bus. Keep the guard anyway:
        // `installTap` enforces its one-tap rule with NSException, not Error,
        // and a future caller must stand down instead of terminating the app.
        guard !tapInstalled else {
            engine.stop()
            suspended = true
            return
        }
        let installed = AudioTapExceptionShield.perform {
            input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
                guard let self else { return }
                // The same audio the recognizer hears also feeds the on-device
                // voice check — a short rolling window, never stored, never
                // sent. Only its one-word verdict ever leaves the phone.
                self.speaker?.accept(buffer)
                self.orphanLock.lock()
                if self.acceptingAudio {
                    if self.usingAnalyzer {
                        self.analyzerEngine?.append(buffer)
                    } else if let req = self.request {
                        req.append(buffer)
                    }
                } else if self.isListening {
                    // No request is taking audio right now (swap in flight).
                    // Hold it — do NOT drop it — and replay into the next one.
                    // A COUNTER, NOT A JOURNAL CALL. This closure runs on the
                    // audio thread; the journal now touches a file, and parking
                    // audio behind a disk write to report dropped audio would be
                    // the joke writing itself. The watchdog reports this from the
                    // main queue instead.
                    if self.orphanBuffers.count < 600 {
                        self.orphanBuffers.append(buffer)
                    } else {
                        self.orphanDropped &+= 1
                    }
                }
                self.orphanLock.unlock()
                // Cheap liveness beacon (~3x/sec), off the audio thread.
                self.bufferTick &+= 1
                if self.bufferTick % 32 == 0 {
                    DispatchQueue.main.async { self.lastBufferAt = Date() }
                }
            }
        }
        guard installed else {
            if !suspended {
                ListenJournal.shared.record(.sessionStopped(cause: .unrecoveredFailure))
            }
            suspended = true
            return
        }
        tapInstalled = true
        engine.prepare()
        try? engine.start()
        // Capture coming BACK is as much a fact about the session as capture
        // going down. A journal that only ever says "stopped" leaves a reader
        // unable to tell a recovered outage from a dead microphone.
        let up = engine.isRunning
        if up, suspended {
            ListenJournal.shared.record(.sessionStarted)
        } else if !up, !suspended {
            ListenJournal.shared.record(.sessionStopped(cause: .unrecoveredFailure))
        }
        suspended = !up
    }

    // ------------------------------------------------------------- healing

    /// Give the call policy something to see, once.
    ///
    /// `CallPresencePolicy` shipped correct and INERT — 44 passing checks and
    /// no call site, with `run_all.sh` printing that fact on every run. This is
    /// the line that ends it. Kept beside `installObserversOnce` because it is
    /// the same kind of thing: a sense installed once for the life of the
    /// process, never per session.
    ///
    /// WHY THE CALL SENSE AND THE INTERRUPTION OBSERVER BOTH EXIST. The
    /// interruption notification says the microphone went away; it never says
    /// why, so a forty-minute call and a forty-minute silence arrive identical.
    /// The sense answers the why, and it answers it EARLIER — CallKit reports a
    /// call connecting before iOS takes the input away. Neither replaces the
    /// other: the observer is the backstop for every interruption that is not a
    /// call, and this is the one that can name the commonest one.
    private func installCallSenseOnce() {
        guard callSense == nil else { return }
        callSense = CallSense(
            standDown: { [weak self] in
                guard let self, self.isListening else { return }
                // HONEST, and the same word the interruption path uses: the
                // microphone is gone. `suspended`'s observer takes the
                // background assertion, so saying it here buys the running time
                // as a side effect of admitting it, which is the ordering the
                // interruption observer already relies on.
                self.suspended = true
            },
            retake: { [weak self] in
                guard let self, self.isListening else { return }
                // Ask, do not assume. The call ending is a claim about the
                // call, not about the route — `retryCapture` mints a new
                // request ONLY if capture actually came back, and returns at
                // the 0 Hz guard if it has not, leaving `suspended` true for
                // the next attempt.
                self.retryCapture(cause: .routeChange)
            })
    }

    private func installObserversOnce() {
        guard !observersInstalled else { return }
        observersInstalled = true
        let nc = NotificationCenter.default
        nc.addObserver(forName: AVAudioSession.interruptionNotification,
                       object: nil, queue: .main) { [weak self] note in
            guard let self, self.isListening else { return }
            let raw = note.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt
            if raw.flatMap(AVAudioSession.InterruptionType.init) == .began {
                ListenJournal.shared.record(.sessionStopped(cause: .interruption))
                // The background assertion is taken by this line, not beside
                // it: `suspended`'s observer owns it, so the running time is
                // bought by the same statement that admits the microphone is
                // gone and cannot be ordered wrongly relative to it.
                self.suspended = true   // honest: the mic is gone right now
            } else {
                // Ended (or unknown): take it back. The session was handed
                // away and handed back, and the input we get back may not be
                // the one we had — so a request whose format was fixed by its
                // first buffer is no use, and `retryCapture` mints a new one
                // ONLY if capture actually came back.
                //
                // Nothing is released here. `.ended` is a claim about the
                // interruption, not about the microphone: the route may not
                // have settled, in which case the retry below returns at the
                // 0 Hz guard, `suspended` stays true, and the assertion this
                // path used to end is the only thing keeping the app running
                // for the next attempt.
                self.retryCapture(cause: .routeChange)
            }
        }
        nc.addObserver(forName: AVAudioSession.routeChangeNotification,
                       object: nil, queue: .main) { [weak self] note in
            // AirPods in, cable out, speakerphone — the input (and its format)
            // may have changed under the tap. Ignore .categoryChange: our own
            // setCategory posts one, and reacting rebuilds gratuitously.
            guard let self, self.isListening else { return }
            let raw = note.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt
            if raw.flatMap(AVAudioSession.RouteChangeReason.init) == .categoryChange { return }
            self.scheduleAudioRecovery(cause: .routeChange)
        }
        nc.addObserver(forName: AVAudioSession.mediaServicesWereResetNotification,
                       object: nil, queue: .main) { [weak self] _ in
            guard let self, self.isListening else { return }
            // Not a route change: media services died and took the engine
            // with them. A reader sent to AirPods and cables by a mislabelled
            // line is a reader who never looks at the engine.
            self.scheduleAudioRecovery(cause: .error)
        }
    }

    /// Leave AVAudioSession's notification stack before touching AVAudioEngine.
    /// YouTube can cause several route notifications in one turn; all of them
    /// describe one current route, so only the most severe pending cause needs
    /// a rebuild.
    private func scheduleAudioRecovery(cause: ListenEvent.SwapCause) {
        guard isListening else { return }
        if scheduledAudioRecoveryCause != .error {
            scheduledAudioRecoveryCause = cause
        }
        guard scheduledAudioRecovery == nil else { return }
        let work = DispatchWorkItem { [weak self] in
            guard let self else { return }
            self.scheduledAudioRecovery = nil
            guard self.isListening,
                  let cause = self.scheduledAudioRecoveryCause else {
                self.scheduledAudioRecoveryCause = nil
                return
            }
            self.scheduledAudioRecoveryCause = nil
            self.recoverAudio(cause: cause)
        }
        scheduledAudioRecovery = work
        DispatchQueue.main.async(execute: work)
    }

    /// Retire the whole graph. Reusing the input node and doing
    /// removeTap/installTap back-to-back is the crash: AVFAudio can still see
    /// the first tap while a route is settling, and its one-tap precondition is
    /// an uncatchable-in-Swift exception. A new engine has a new input bus and
    /// therefore no possible prior tap. Hold the retired engine until the next
    /// main turn so teardown also happens outside the notification callback.
    private func replaceCaptureEngine() {
        let retiredEngine = engine
        engine = AVAudioEngine()
        tapInstalled = false
        retiredEngine.stop()
        DispatchQueue.main.async { _ = retiredEngine }
    }

    /// Ask iOS for a little more running time while the microphone is gone.
    ///
    /// Called from one place, `suspended`'s observer, and only on the edge
    /// where it becomes true. The `endBackgroundAssertion()` below it is
    /// insurance rather than a live path: an identifier overwritten without
    /// being ended can never be ended, and iOS terminates an app over that, so
    /// it is not left resting on an argument about who calls this.
    private func beginBackgroundAssertion() {
        endBackgroundAssertion()
        backgroundTask = UIApplication.shared.beginBackgroundTask(withName: "listen-interruption") { [weak self] in
            // Called when iOS is out of patience. Ending it here is what keeps
            // the app alive; letting an assertion expire unended is a
            // termination, not a warning.
            self?.endBackgroundAssertion()
        }
    }

    /// Idempotent on purpose, because two paths end the same assertion in
    /// either order: iOS running out of patience (the expiration handler), and
    /// the microphone coming back (`suspended` clearing). A long call reaches
    /// both, thirty seconds apart. Apple's contract is that an identifier is
    /// ended once, by the holder; ending one iOS has already reclaimed is
    /// outside it. The guard is what makes "just call it" safe on the second
    /// of those.
    private func endBackgroundAssertion() {
        guard backgroundTask != .invalid else { return }
        UIApplication.shared.endBackgroundTask(backgroundTask)
        backgroundTask = .invalid
    }

    /// The owner came back and the microphone may be ours again.
    ///
    /// Distinct from `start()`, which is for listening that is OFF. Here
    /// listening never stopped wanting to happen — iOS took the input away and
    /// the app was suspended before it could take it back. `start()` would run
    /// the two permission callbacks and then return at `begin()`'s re-entrancy
    /// guard, doing nothing at all.
    ///
    /// No watchdog restart here, deliberately. A repeating `Timer` on the main
    /// runloop is FROZEN by app suspension, not invalidated, and resumes firing
    /// when the runloop does; and if iOS terminated the app instead, the fresh
    /// process has `isListening == false` and `ListenResumePolicy` sends it
    /// down the `.start` branch, which builds a new watchdog anyway. Restarting
    /// it here would be a line with no failure behind it.
    func retakeMicrophone() {
        guard isListening else { return }
        retryCapture(cause: .appReturned)
    }

    /// Try the engine again, and mint a new recognition request ONLY if capture
    /// actually came back.
    ///
    /// The shared body of every "the microphone may be ours again" moment: the
    /// watchdog's stand-down tick, `.ended` arriving, and the owner opening the
    /// app. Not `recoverAudio`, which swaps unconditionally — that is right for
    /// a failure it is repairing, and wrong here, where the input may still
    /// belong to a call and the swap would cancel a task to mint one that can
    /// hear nothing.
    ///
    /// WHY THE JOURNAL LINE IS ON THE FAR SIDE OF THE GUARD, and this is
    /// finding 3 of the review. `.appReturned` answers "how often did she only
    /// come back because he opened the app?" — the honest measure of how much
    /// of the interruption hole is still open. Recorded on ATTEMPT, a ten-minute
    /// call the owner glanced at six times wrote six lines claiming listening
    /// came back and cancelled six recognition tasks to build six more that
    /// could hear nothing, while it came back zero times. The count read the
    /// flattering way, and every one of those visits cost a working task.
    /// `swapRecognition` writes the line, so it is written by the same
    /// statement that does the thing it describes.
    private func retryCapture(cause: ListenEvent.SwapCause) {
        guard isListening else { return }
        replaceCaptureEngine()
        configureAndStartEngine()
        // Still not ours. `configureAndStartEngine` reconciles `suspended`
        // itself and only clears it when the engine really came up, so this is
        // the honest answer to "did that work" — nothing is recorded, the
        // recognition task is left alone, and the next tick tries again.
        guard !suspended else { return }
        // The tap just installed carries the CURRENT route's format, and a live
        // request's format was fixed by its first buffer. A call that starts on
        // Bluetooth and ends on speaker would otherwise feed the new tap into
        // the old request and the recognizer would produce nothing.
        swapRecognition(flushPending: true, cause: cause)
    }

    /// Bring the whole capture chain back after whatever iOS did to it.
    ///
    /// `cause` is required rather than defaulted. Its five callers are three
    /// different kinds of event — two route changes, two failures, and the
    /// owner walking back into the app — and a default here would let the next
    /// caller inherit "the route changed" for a dead AVAudioEngine, or for a
    /// call that suspended the whole process. That mislabelling is what this
    /// parameter exists to end.
    private func recoverAudio(cause: ListenEvent.SwapCause) {
        guard isListening else { return }
        // Read BEFORE the rebuild, because the rebuild is what clears it.
        // While a phone call owns the microphone, configureAndStartEngine
        // returns at the 0 Hz guard without ever starting the engine, so the
        // watchdog arrives here again 4s later for the whole call. Recording a
        // swap per attempt writes 75 identical lines in five minutes and
        // evicts the entire ring in twenty-seven — the session the journal
        // exists to explain, gone, replaced by one repeated sentence.
        let alreadyDown = suspended
        replaceCaptureEngine()
        configureAndStartEngine()
        guard !suspended else { return }
        // A live request's format was fixed by its first buffer; the new route
        // may differ, so start fresh — flushing whatever was pending first.
        swapRecognition(flushPending: true, cause: cause,
                        alreadyReported: alreadyDown)
    }

    /// Last line of defense: whatever stalled without a notification — engine
    /// dead, audio not flowing, recognizer gone DEAF — comes back within
    /// seconds. Listening ends when the user ends it, never when a component
    /// quietly dies.
    private func startWatchdog() {
        watchdog?.invalidate()
        let timer = Timer(timeInterval: 4, repeats: true) { [weak self] _ in
            guard let self, self.isListening else { return }
            // Drain the audio thread's drop counter here, on the main queue,
            // coalesced into ONE line however many buffers were lost. A
            // journal that spends its lines saying the same thing has evicted
            // the session it was meant to explain.
            self.orphanLock.lock()
            let dropped = self.orphanDropped
            self.orphanDropped = 0
            self.orphanLock.unlock()
            if dropped > 0 {
                ListenJournal.shared.record(.buffersDropped(count: dropped))
            }
            // WHAT LISTENING COSTS, read on the tick that is already running.
            // No timer of its own: a second repeating timer to measure the draw
            // of the first one would be funny once and wrong forever.
            //
            // Here rather than in the tap closure, for the reason the drop
            // counter is drained here — that closure is on the audio thread and
            // the journal touches a file. And guarded by `shouldRecord`, which
            // is what keeps a 4-second tick from writing fifteen lines a minute
            // through a phone call and evicting the interruption that explains
            // the day. `run_journal_tests.sh` fails if that guard goes.
            let device = UIDevice.current
            let power = device.batteryState
            if let reading = BatteryReadingPolicy.reading(
                    level: device.batteryLevel,
                    stateIsKnown: power != .unknown,
                    // `.full` is a phone at 100% on a cable: not charging, and
                    // spending nothing. What the fold needs is whether the
                    // interval starting here can be read as drain at all.
                    onPower: power == .charging || power == .full),
               BatteryReadingPolicy.shouldRecord(reading,
                                                 lastRecorded: self.lastBatteryReading) {
                self.lastBatteryReading = reading
                ListenJournal.shared.record(
                    .batteryRead(percent: reading.percent, onPower: reading.onPower))
            }
            // WHAT to do is decided in ListenWatchdogPolicy, which reads
            // clocks and nothing else, so every ordering below can be shown to
            // fail with swiftc alone. This body only carries the decision out.
            //
            // `interrupted: self.suspended` — `suspended` is this object's
            // answer to "the microphone is not ours right now", set by the
            // interruption notification and by the 0 Hz guard that refuses to
            // tap a silenced input. It is exactly the state in which every
            // other signal here is a lie.
            let action = ListenWatchdogPolicy.decide(
                engineRunning: self.engine.isRunning,
                hasTask: self.task != nil,
                interrupted: self.suspended,
                lastBufferAt: self.lastBufferAt,
                lastResultAt: self.lastResultAt,
                lastPartialAt: self.lastPartialAt,
                requestBornAt: self.requestBornAt,
                hasPending: !self.pendingTail.isEmpty,
                now: Date())
            switch action {
            case .standDown:
                // Retry the engine, leave the recognition task alone. Not a
                // no-op: `recoverAudio` is what used to run here, and it ends
                // in `swapRecognition`, so a call minted a fresh
                // SFSpeechRecognitionTask every 4 seconds for its whole
                // length. Standing down entirely would kill that churn and
                // also remove the only thing that notices a call ENDING when
                // iOS never delivers `.ended` — it sometimes doesn't. For as
                // long as the call lasts the retry writes nothing to the
                // journal and returns at the 0 Hz guard.
                // ...AND ON THE ONE TICK IT SUCCEEDS, THE REQUEST HAS TO GO
                // TOO, which is `retryCapture`'s whole shape: rebuild, and swap
                // only if the rebuild worked. Without the swap, a call that
                // starts on Bluetooth and ends on speaker feeds the new tap
                // into the old request, the recognizer produces nothing, and
                // leg 6 does not rescue it until the quiet passes 120 seconds —
                // up to two more minutes of the deafness this watchdog exists
                // to end, after the call is over.
                self.retryCapture(cause: .routeChange)
                return
            case .rebuild:
                // A dead engine, or audio that stopped flowing with no
                // notification. Both are failures, and neither is a route
                // change.
                self.recoverAudio(cause: .error)
                return
            case .startRecognition:
                self.startRecognition()
                return
            case .swap(let cause):
                // Flushes, deliberately: this is the leg reached with words
                // still unsent, and they cross the seam rather than dying with
                // the task.
                self.swapRecognition(flushPending: true, cause: cause)
                return
            case .rotate:
                // The one swap that must NOT flush. It is only ever reached in
                // true silence, so there is nothing to carry across.
                self.swapRecognition(flushPending: false, cause: .silenceRotation)
                return
            case .nothing:
                // Nothing to do, and nothing to reconcile either. This used to
                // fall through to "reaching here with `suspended` still set
                // means capture returned on its own", which was dead the day it
                // was written: `.nothing` is the only action that reaches here,
                // `.nothing` requires `interrupted == false`, and `interrupted`
                // IS `suspended` — so the branch tested a flag it had just been
                // told was clear and the line after it assigned false to false.
                // Swept over all 21,952 combinations of the other arguments,
                // `decide` never once answers `.nothing` while interrupted, and
                // `run_watchdog_policy_tests.sh` now fails if that changes.
                //
                // The reconciliation is real work and it happens in
                // `configureAndStartEngine`, which the `.standDown` arm calls on
                // every tick of a call — that is the path that notices capture
                // coming back, records the `.sessionStarted` and clears
                // `suspended`. A must-not-break invariant preserved as prose
                // over an unreachable branch is worse than no prose: it reads as
                // a live guard, and the next person to change what feeds
                // `interrupted:` would trust it.
                break
            }
        }
        // .common, not .default: a timer in .default never fires while the
        // user is scrolling the feed — the exact moment they're watching.
        RunLoop.main.add(timer, forMode: .common)
        watchdog = timer
    }

    // --------------------------------------------------------- recognition

    /// Words heard on the current task that haven't been sent yet.
    private var pendingTail: String {
        cursor.pending
    }

    private func startRecognition() {
        if #available(iOS 26.0, *), ListenEnginePolicy.usesAnalyzerNow,
           !analyzerDisabledForSession {
            // The engine is non-optional on an iOS 26 device; the failure
            // modes (model missing, locale uncovered) surface as onError and
            // land in the three-strike fallback, not in a nil bind here.
            runAnalyzerRequest(SpeechAnalyzerRequestEngine.make(locale: Locale(identifier: "en_US")))
            return
        }
        usingAnalyzer = false
        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        // Rebuilt per request, not cached: this fires on every swap, so a
        // person named in the roster an hour ago is already in the lexicon.
        req.contextualStrings = AnticipyVocabulary.current()
        // What this audio IS. Unset, the recognizer weighs a general language
        // model against what is actually continuous conversation; .dictation is
        // the hint Apple provides for exactly this. Nothing in the app set it.
        req.taskHint = .dictation
        // Punctuation from the recognizer rather than from a rule of ours. The
        // brain reads these lines as sentences, and an unpunctuated wall of
        // words is one sentence to everything downstream that counts them.
        req.addsPunctuation = true
        if recognizer?.supportsOnDeviceRecognition == true {
            req.requiresOnDeviceRecognition = true
        }
        requestBornAt = Date()
        lastResultAt = Date()
        // Everything the cursor knew about what it had already sent dies here,
        // and the orphan buffer below then replays the audio it was holding
        // into the new request. That pairing IS the duplicate: the same speech
        // decoded a second time by a cursor with no record of the first. Mark
        // the break before the replay, so the line it produces is judged
        // against it.
        lineageBrokeAt = Date()
        cursor.reset()
        partial = ""
        pendingSince = nil
        // `cutAt` is deliberately NOT cleared here. Speech can cross a swap
        // seam — the orphan buffer exists to replay it — and a cut whose words
        // continue half a second later on a new task is a true link. The rule
        // that ends it is silence, not the task boundary, and cutContinues
        // measures that on its own.

        // Nothing has been heard on THIS request yet. A stale timestamp here
        // would date the new task's silence from the old task's speech.
        lastPartialAt = nil
        everEmittedThisTask = false

        orphanLock.lock()
        request = req
        acceptingAudio = true
        // Replay anything the microphone captured during the swap so a
        // sentence spoken across the seam is not lost.
        let held = orphanBuffers
        orphanBuffers.removeAll()
        orphanLock.unlock()
        for b in held { req.append(b) }

        task = recognizer?.recognitionTask(with: req) { [weak self] result, error in
            guard let self else { return }
            DispatchQueue.main.async {
                // Only the CURRENT chain may touch shared state — a superseded
                // task's late callbacks must never clobber or double-emit.
                guard self.request === req else { return }
                self.lastResultAt = Date()

                if let result {
                    self.absorbRecognized(result.bestTranscription.formattedString,
                                          isFinal: result.isFinal)
                } else if error != nil {
                    // The recognizer died. Whatever was heard is real speech —
                    // emit it, then take a fresh one; buffered audio carries
                    // across the seam.
                    self.swapRecognition(flushPending: true, cause: .error)
                }
            }
        }
    }

    /// Send the words heard but not yet sent, as one line.
    ///
    /// `reason` is not bookkeeping. It is the difference between "he finished a
    /// sentence" and "the clock cut him off mid-sentence" — the one thing this
    /// object knows for certain about a line, and the thing it used to discard.
    private func flushTail(reason: TranscriptFlushPolicy.Reason) {
        silenceFlush?.cancel()
        // Read before it is cleared. Whether these words carry on from a cut
        // depends on when they STARTED waiting, not on when the flush got round
        // to them: a continuous talker's next ceiling is a whole maxHold after
        // the last one, so judging by delivery time would throw away every true
        // link in exactly the monologue this is for.
        let appeared = pendingSince ?? Date()
        pendingSince = nil
        // All-or-nothing: the cursor either hands over everything unsent or
        // nothing at all. The old take(minNewWords:) advanced its record and
        // THEN decided a one- or two-word tail was too short to bother with,
        // which marked those words sent without ever sending them.
        guard let line = cursor.takePending()?
            .trimmingCharacters(in: .whitespacesAndNewlines),
            !line.isEmpty else { return }
        // These words have been SENT. The live caption at ContentView:1026
        // renders `partial` verbatim, so leaving it standing keeps showing the
        // owner speech that already went out as a line — the caption and the
        // record disagreeing about what is still in flight. Cleared here rather
        // than in `deliver`, because the cursor is what actually took the
        // words, and `deliver` can decline to send (enrolling, an echo of the
        // previous line) after they are already gone from it.
        //
        // `TranscriptCursor` is untouched: it tracks the consumed prefix on its
        // own and never reads this string.
        partial = ""
        deliver(line, reason: reason, wordsAppearedAt: appeared)
    }

    /// The one way a line leaves this object. Banked words — speech the
    /// recognizer was about to discard — travel exactly the same path as an
    /// ordinary flush, so they get the same speaker verdict and the same
    /// enrollment protection instead of a second, subtly different route.
    ///
    /// `reason` is nil for those banked words: no timer fired and the
    /// recognizer did not finalise, a decode window was simply thrown away.
    /// `wordsAppearedAt` is when this line's words first went unsent, which is
    /// what decides whether they carry on from a cut. `now` is the instant the
    /// flush produced the line, and it is what the backend records as when the
    /// words were spoken.
    private func deliver(_ line: String, reason: TranscriptFlushPolicy.Reason?,
                         wordsAppearedAt: Date, at now: Date = Date()) {
        // A voice sample is not something he said. Never emit it.
        guard !enrolling else { return }
        // ...and neither is the last sentence handed over a second time. Not
        // losing words cost this: the recognizer revises, so a replaced decode
        // window can hand over ONE sentence twice in slightly different words.
        // Live 2026-08-17: "Yeah I know where it is" then "Yeah I know it is".
        //
        // The question is asked on the break, not on the clock. Every line
        // leaves here either on a partial or one utterance gap after the last
        // one, so a duplicate the silence timer delivers is ALWAYS further
        // apart than the gap — and so is a person saying it again. Elapsed
        // time cannot tell those two apart at any width; `lineageBrokeAt` can,
        // because only one of them happens with the cursor's send record gone.
        let broke = lineageBrokeAt
        // One break answers for one line, whether or not that line survives.
        // Read and cleared here rather than left standing, because a flag with
        // nothing to clear it is a mode: the swap that armed it would go on
        // eating repeats until the next one.
        lineageBrokeAt = nil
        if let last = lastDelivered,
           flushPolicy.isEchoOfPrevious(line, previous: last,
                                        lineageBrokeAt: broke,
                                        wordsAppearedAt: wordsAppearedAt) {
            return
        }
        lastDelivered = line
        everEmittedThisTask = true
        // WHICH line carries the mark, and for HOW LONG. `.ceiling` says how
        // THIS line ended: the clock ran out while he was still talking. The
        // line that carries on from a cut is the NEXT one, so the mark is read
        // here and written for the next line below. It only reaches words that
        // followed the cut immediately — a cut that empties the pending words
        // and is followed by silence is answered by nothing, and chaining a
        // new thought onto a finished sentence reads as one rambling thought
        // nobody ever had. This is mechanism, not meaning: it says which timer
        // fired and how long ago.
        let continuesPrevious = flushPolicy.cutContinues(cutAt: cutAt,
                                                         wordsAppearedAt: wordsAppearedAt)
        cutAt = reason == .ceiling ? now : nil
        // The word COUNT, never the words. The journal is exportable from
        // Settings and the events collection already holds the speech itself.
        ListenJournal.shared.record(
            .flushed(reason: ListenEvent.FlushReason(policyRawValue: reason?.rawValue),
                     words: line.split(whereSeparator: { $0.isWhitespace }).count))
        // Judge the voice behind THIS line before the window moves on. Done
        // here rather than on the audio thread: embedding takes tens of
        // milliseconds and must never stall capture.
        // BOTH ENDS, and the start is the one that was being thrown away.
        // `wordsAppearedAt` is read four lines up for the cut-continuation
        // mark and was then dropped on the floor; `now` went out as the start,
        // the end and the alias all at once. Sending `now` twice here would
        // compile, satisfy every signature, and be the original bug.
        if let speaker, let onSpeaker {
            let tag = speaker.tagForLatestUtterance()
            onSpeaker(line, tag, wordsAppearedAt, now, continuesPrevious)
        } else {
            onLine?(line, wordsAppearedAt, now, continuesPrevious)
        }
    }

    /// After a pause, cut a line from the running text — WITHOUT ending the
    /// request, so speech that follows keeps flowing into the same recognizer
    /// and nothing is orphaned.
    private func scheduleSilenceFlush() {
        silenceFlush?.cancel()
        guard !pendingTail.isEmpty else {
            pendingSince = nil
            return
        }
        // Start the clock the first time words go unsent.
        let since = pendingSince ?? Date()
        pendingSince = since
        // A continuous talker re-arms this debounce forever. The ceiling is
        // what makes that survivable: waiting words go out on their own. The
        // reason they went out now travels with them, so a cut can be linked
        // to the line before it instead of published as a whole thought.
        //
        // This runs on a fresh partial, so the recognizer is still revising:
        // the only answer possible here is the ceiling, or none.
        if let reason = flushPolicy.flushReason(pendingSince: since,
                                                lastPartialAt: lastPartialAt,
                                                now: Date()) {
            flushTail(reason: reason)
            return
        }
        let work = DispatchWorkItem { [weak self] in
            guard let self, self.isListening else { return }
            // The timer surviving long enough to fire IS the pause: every
            // partial cancels it. So these words are a finished thought.
            self.flushTail(reason: .gap)
        }
        silenceFlush = work
        DispatchQueue.main.asyncAfter(deadline: .now() + utteranceGap, execute: work)
    }

    /// Retire the current recognition task and start a clean one. Audio keeps
    /// being captured into the orphan buffer throughout and is replayed.
    ///
    /// `cause` is recorded, because "the recognizer was replaced" with no
    /// trigger is the useless half of the report: a route change, Apple's task
    /// limit, an error and the 120s rotation are indistinguishable afterwards.
    ///
    /// `alreadyReported` is how a recovery that the watchdog retries every 4s
    /// for the length of a phone call stays one line in the journal instead of
    /// hundreds. Only `recoverAudio` passes it.
    ///
    /// The same rule now governs every write above the 0 Hz guard in
    /// `configureAndStartEngine`. It did not, and the two `.noted` lines that
    /// escaped it evicted the whole ring in 27 minutes of one phone call.
    /// Everything one recognizer revision means — shared by BOTH engines.
    /// `isFinal` reaches here true only from the legacy path, where it means
    /// Apple's task limit landed mid-speech: flush what was held, take a
    /// fresh task. The analyzer engine finalizes progressively and passes
    /// false: its finalization is wording settling, not a limit, and tearing
    /// the request down on it would burn battery for nothing. Its swaps
    /// belong to the watchdog, exactly as before.
    private func absorbRecognized(_ text: String, isFinal: Bool) {
        // A window reset replaces the text instead of extending it
        // (a 12s sentence collapsing to "Of August"). There used to
        // be a character-count guess here that banked the tail and
        // zeroed the cursor — which then said the short text again.
        // The cursor re-finds the said words in whatever the
        // recogniser now believes, so a collapse needs no special
        // case and no magic number.
        partial = text
        // Stamped where a revision actually arrives. This is the
        // evidence that tells "still talking, the clock ran out"
        // (a cut) from "stopped talking" (a finished thought), and
        // without it the flush can only ever report the second.
        lastPartialAt = Date()
        // Show the cursor EVERY hypothesis, not just the ones we
        // flush on. That is what lets it notice the recognizer
        // throwing away a decode window and hand back the words
        // that window held (`banked`) before they are gone — the
        // 12-second sentence collapsing to "Of August". Nothing
        // else in the app remembers unsent speech.
        let update = cursor.observe(partial)
        if let banked = update.banked?
            .trimmingCharacters(in: .whitespacesAndNewlines),
            !banked.isEmpty, !enrolling {
            // Banked words are older than the ones still pending,
            // so the pending mark is the earliest honest answer to
            // "when did these appear". Absent one, they appeared
            // now, which continues nothing.
            deliver(banked, reason: nil,
                    wordsAppearedAt: pendingSince ?? Date())
            // The banked line consumed the old decode window. Any words the
            // replacement window still carries first became pending on THIS
            // callback, not when the now-banked window began. Keeping the old
            // mark made the banked line and every replacement tail share one
            // capture_started_at; three rows from build 113 arrived in 0.8s
            // with the identical start 05:00:14.974Z. Downstream that is
            // indistinguishable from an offline queue re-stamping a burst and
            // it destroys the ordering signal the capture envelope exists to
            // preserve.
            pendingSince = nil
        }
        // AFTER the banked line, never before it. Banked words are
        // words the cursor is handing over BECAUSE the window died
        // under them — they were never sent, and arming the guard
        // in front of them would suppress the one delivery that
        // exists to stop speech being lost. The line at risk is
        // the NEXT one: the replaced window's own text, which is
        // the already-sent audio decoded again.
        if update.didReset { lineageBrokeAt = Date() }
        if isFinal {
            // A final usually just polishes wording, so a couple of
            // new words is noise — EXCEPT when the task is ending
            // with speech never sent at all. That is not a polish,
            // it is the whole monologue, and gating it away is how
            // a continuous talker's words reached nobody.
            flushTail(reason: .final)
            // A final arriving mid-conversation is Apple's task
            // limit landing, not the speaker stopping.
            swapRecognition(flushPending: false, cause: .taskLimit)
        } else if update.changed || update.didReset {
            scheduleSilenceFlush()
        }
    }

    /// The iOS 26 request. Same contract as the legacy one below — same reset
    /// block, same orphan replay, same identity guard, same journal events —
    /// a different recognizer and nothing else. A request that cannot
    /// provision its model counts toward the three-strike session fallback
    /// rather than spinning: `onError` here is an outage, and the retry rule
    /// this codebase already wrote down for 410s applies — only the
    /// recoverable kind may be retried.
    @available(iOS 26.0, *)
    private func runAnalyzerRequest(_ engine: SpeechAnalyzerRequestEngine) {
        usingAnalyzer = true
        requestBornAt = Date()
        lastResultAt = Date()
        // Everything the cursor knew about what it had already sent dies
        // here — the same break the legacy path takes, for the same reason:
        // the orphan replay below re-decodes held audio through a cursor
        // with no record of the first decode, and the duplicate guard has
        // to know the seam exists.
        lineageBrokeAt = Date()
        cursor.reset()
        partial = ""
        pendingSince = nil
        // `cutAt` is deliberately NOT cleared here. Speech can cross a swap
        // seam — the orphan buffer exists to replay it — and a cut whose
        // words continue half a second later on a new engine is a true link.
        lastPartialAt = nil
        everEmittedThisTask = false

        orphanLock.lock()
        analyzerEngine = engine
        acceptingAudio = true
        let held = orphanBuffers
        orphanBuffers.removeAll()
        orphanLock.unlock()
        for b in held { engine.append(b) }

        engine.onResult = { [weak self, weak engine] text, isFinal in
            guard let self, let engine else { return }
            DispatchQueue.main.async {
                // Only the CURRENT engine may touch shared state — a
                // superseded engine's late callbacks must never clobber or
                // double-emit. The tail a finishing engine emits after the
                // swap has already happened is deliberately rejected: its
                // audio was orphan-replayed into the replacement, so the
                // words arrive once, from the engine that owns them.
                guard self.analyzerEngine === engine else { return }
                self.lastResultAt = Date()
                self.absorbRecognized(text, isFinal: isFinal)
            }
        }
        engine.onError = { [weak self, weak engine] in
            guard let self, let engine else { return }
            DispatchQueue.main.async {
                guard self.analyzerEngine === engine else { return }
                self.analyzerFailures &+= 1
                if self.analyzerFailures >= 3 { self.analyzerDisabledForSession = true }
                self.swapRecognition(flushPending: true, cause: .error)
            }
        }
        engine.begin()
    }

    private func swapRecognition(flushPending: Bool, cause: ListenEvent.SwapCause,
                                 alreadyReported: Bool = false) {
        if !alreadyReported {
            ListenJournal.shared.record(.recognizerSwapped(cause: cause))
        }
        silenceFlush?.cancel()
        // Whatever forced this swap ended the recognition task, so `.final` is
        // the honest label for the words it was still holding. It carries no
        // parent: a forced swap publishes what it has rather than guessing at
        // a link to a sentence it cannot know was unfinished.
        if flushPending { flushTail(reason: .final) }
        orphanLock.lock()
        acceptingAudio = false
        orphanLock.unlock()
        task?.cancel()
        task = nil
        request = nil
        // The analyzer finalizes its tail through finish(); whatever arrives
        // after the replacement is installed is identity-guarded away, and
        // the orphan replay re-decodes the seam either way.
        analyzerEngine?.finish()
        analyzerEngine = nil
        guard isListening else { return }
        startRecognition()
    }

    /// Enrollment needs the microphone but NOT the transcriber: those twelve
    /// seconds are a voice sample, not a thing he said, and they must never
    /// reach the feed or the brain. Remembers whether ambient listening was
    /// already on so it can be handed back untouched.
    private var wasListeningBeforeEnrollment = false

    func startForEnrollment() {
        wasListeningBeforeEnrollment = isListening
        enrolling = true
        // A voice sample is not a continuation of anything. Whatever the clock
        // cut off before this cannot be carried on by the first real sentence
        // after it, and the twelve seconds in between are not a pause in a
        // thought — they are "read this out loud". Said here rather than left
        // to the silence rule, because a cancelled enrollment can be over in
        // half a second and the mark would survive it.
        cutAt = nil
        if !isListening { start() }
    }

    func stopAfterEnrollment() {
        enrolling = false
        if !wasListeningBeforeEnrollment { stop() }
    }

    func stop() {
        // Recorded only when a session was actually running. Sign-out calls
        // stop() unconditionally, and a journal full of stops that ended
        // nothing is a journal that hides the one that ended something.
        if isListening {
            ListenJournal.shared.record(.sessionStopped(cause: .owner))
        }
        isListening = false
        // Toggling Listen off during a call is the path that reaches here with
        // an assertion still held, and this line is what hands it back — the
        // observer on `suspended` ends it. Left held it would sit until iOS
        // expired it: not a termination, the expiration handler ends it, but
        // background time charged to an app with nothing left to do.
        suspended = false
        lastSessionFacts = nil
        lastBatteryReading = nil
        watchdog?.invalidate()
        watchdog = nil
        scheduledAudioRecovery?.cancel()
        scheduledAudioRecovery = nil
        scheduledAudioRecoveryCause = nil
        silenceFlush?.cancel()
        // The engine outlives this stop only as a corpse; finishing it is
        // what delivers the tail it was still holding.
        analyzerEngine?.finish()
        analyzerEngine = nil
        usingAnalyzer = false
        if tapInstalled {
            engine.inputNode.removeTap(onBus: 0)
            tapInstalled = false
        }
        engine.stop()
        orphanLock.lock()
        acceptingAudio = false
        orphanBuffers.removeAll()
        orphanLock.unlock()
        // Emit whatever was still in flight — pressing Stop must never be the
        // thing that deletes what you just said.
        let tail = pendingTail.trimmingCharacters(in: .whitespacesAndNewlines)
        if !tail.isEmpty {
            ListenJournal.shared.record(
                .flushed(reason: .final,
                         words: tail.split(whereSeparator: { $0.isWhitespace }).count))
            // Stamped as the words leave, not when they are pushed: the push
            // behind this one may not happen until the network is back.
            //
            // THE FOURTH DELIVERY SITE, and the only one that does not go
            // through `deliver` — so widening that function's callbacks does
            // not reach it, and it is the last line of every session. It used
            // to hand over `Date()` alone: teardown time, as the start and the
            // end at once. Both instants are named here so the same line
            // cannot answer two different questions with two separate reads of
            // the clock.
            //
            // A parting tail that followed a cut immediately really does carry
            // on from it; one spoken after a long silence does not, so it is
            // judged by the same rule as every other line.
            let partingStartedAt = pendingSince ?? Date()
            let partingEndedAt = Date()
            onLine?(tail, partingStartedAt, partingEndedAt,
                    flushPolicy.cutContinues(cutAt: cutAt,
                                             wordsAppearedAt: partingStartedAt))
        }
        // Outside the branch on purpose: nothing follows this session whether a
        // tail went out or not, and the state a ceiling flush leaves behind is
        // exactly an EMPTY tail — it took every pending word. Toggling Listen
        // off in that window and straight back on used to carry the mark into
        // the new session, and the new session's first line went out naming the
        // old session's last line as the sentence it carried on from. A
        // recognition task deliberately does not clear this (speech crosses a
        // swap seam); a session ending is the one boundary nothing crosses.
        cutAt = nil
        // Same boundary, same reason. A break armed by a swap moments before
        // Stop must not be answered by the first line of the NEXT session,
        // which is a fresh sentence nobody has heard yet.
        lineageBrokeAt = nil
        task?.finish()
        request = nil
        task = nil
        partial = ""
        cursor.reset()
        // Hand the audio session back. Leaving it active kept the recording
        // mode — and everything it suppresses — in force for the rest of the
        // process, so turning Listen OFF never restored normal behavior.
        try? AVAudioSession.sharedInstance()
            .setActive(false, options: .notifyOthersOnDeactivation)
    }
}
