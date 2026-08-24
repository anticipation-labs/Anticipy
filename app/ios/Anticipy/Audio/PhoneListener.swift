import AVFoundation
import Foundation
import Speech

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
    @Published var suspended = false

    /// A finished line, the instant the flush produced it, and whether it
    /// carries on from the line before it.
    ///
    /// The instant travels WITH the words because the push can be much later
    /// than the speech: a line buffered offline and sent hours afterwards used
    /// to reach the backend stamped with the moment the network came back, so
    /// a whole buffered conversation looked like it happened in one second.
    var onLine: ((_ line: String, _ capturedAt: Date, _ continuesPrevious: Bool) -> Void)?
    /// Who said it, decided on this device. Fires with the same line that
    /// went to `onLine`, carrying "owner" / "other:<who>" — or nil when the
    /// phone cannot honestly say, which the brain reads as no verdict.
    var onSpeaker: ((_ line: String, _ speaker: String?, _ capturedAt: Date, _ continuesPrevious: Bool) -> Void)?
    /// The on-device voice check. Optional: without a model the app runs
    /// exactly as it did before speaker recognition existed.
    var speaker: SpeakerTagger?
    /// True while recording a voice sample for enrollment. Audio still
    /// feeds the voice check; nothing is transcribed, emitted or sent.
    var enrolling = false

    private var engine = AVAudioEngine()
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en_US"))
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var silenceFlush: DispatchWorkItem?
    private var watchdog: Timer?
    private var observersInstalled = false

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

    private var lastBufferAt = Date()
    private var lastResultAt = Date()
    private var requestBornAt = Date()
    private var bufferTick = 0

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
    private var lastDelivered: (text: String, at: Date)?
    /// Whether this recognition task has sent anything yet — see the final
    /// handler, where it decides a polish from a whole unsent monologue.
    private var everEmittedThisTask = false

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
        isListening = true
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
        try? session.setCategory(.record, mode: .measurement, options: .duckOthers)
        // iOS MUTES the Taptic Engine for the whole app while a .record session
        // is active, so the buzz can't bleed into the mic. She starts listening
        // milliseconds after launch (keepListening is a standing state), so
        // without this every haptic in the app died before a finger touched
        // anything — the "I feel no haptics anywhere" report on build 32.
        // Nothing surfaces the suppression: no error, no log.
        try? session.setAllowHapticsAndSystemSoundsDuringRecording(true)
        try? session.setActive(true, options: .notifyOthersOnDeactivation)

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
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            guard let self else { return }
            // The same audio the recognizer hears also feeds the on-device
            // voice check — a short rolling window, never stored, never
            // sent. Only its one-word verdict ever leaves the phone.
            self.speaker?.accept(buffer)
            self.orphanLock.lock()
            if self.acceptingAudio, let req = self.request {
                req.append(buffer)
            } else if self.isListening {
                // No request is taking audio right now (swap in flight).
                // Hold it — do NOT drop it — and replay into the next one.
                if self.orphanBuffers.count < 600 { self.orphanBuffers.append(buffer) }
            }
            self.orphanLock.unlock()
            // Cheap liveness beacon (~3x/sec), off the audio thread.
            self.bufferTick &+= 1
            if self.bufferTick % 32 == 0 {
                DispatchQueue.main.async { self.lastBufferAt = Date() }
            }
        }
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
                self.suspended = true   // honest: the mic is gone right now
            } else {
                self.recoverAudio()     // ended (or unknown): take it back
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
            self.recoverAudio()
        }
        nc.addObserver(forName: AVAudioSession.mediaServicesWereResetNotification,
                       object: nil, queue: .main) { [weak self] _ in
            guard let self, self.isListening else { return }
            self.engine = AVAudioEngine()   // QA1749: the old engine is dead forever
            self.recoverAudio()
        }
    }

    /// Bring the whole capture chain back after whatever iOS did to it.
    private func recoverAudio() {
        guard isListening else { return }
        engine.stop()
        configureAndStartEngine()
        // A live request's format was fixed by its first buffer; the new route
        // may differ, so start fresh — flushing whatever was pending first.
        swapRecognition(flushPending: true, cause: .routeChange)
    }

    /// Last line of defense: whatever stalled without a notification — engine
    /// dead, audio not flowing, recognizer gone DEAF — comes back within
    /// seconds. Listening ends when the user ends it, never when a component
    /// quietly dies.
    private func startWatchdog() {
        watchdog?.invalidate()
        let timer = Timer(timeInterval: 4, repeats: true) { [weak self] _ in
            guard let self, self.isListening else { return }
            if !self.engine.isRunning { self.recoverAudio(); return }
            if self.task == nil { self.startRecognition(); return }
            let now = Date()
            if now.timeIntervalSince(self.lastBufferAt) > 6 { self.recoverAudio(); return }
            // Recognizer went silent mid-utterance: words on screen, nothing
            // arriving for 8s (a healthy one streams continuously).
            if !self.pendingTail.isEmpty, now.timeIntervalSince(self.lastResultAt) > 8 {
                // Apple's task-duration limit is the known reason a healthy
                // recognizer stops streaming without ever finalising.
                self.swapRecognition(flushPending: true, cause: .taskLimit)
                return
            }
            // Rotate only in true silence — nothing pending, nothing to lose.
            if self.pendingTail.isEmpty, self.partial.isEmpty,
               now.timeIntervalSince(self.requestBornAt) > 120 {
                self.swapRecognition(flushPending: false, cause: .silenceRotation)
                return
            }
            // A rebuild is not the only way capture comes back. Reaching here
            // with `suspended` still set means it returned on its own, and a
            // stop with no matching start reads as a session that never
            // recovered at all.
            if self.suspended, self.engine.isRunning {
                ListenJournal.shared.record(.sessionStarted)
            }
            self.suspended = !self.engine.isRunning
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
        cursor.reset()
        partial = ""
        pendingSince = nil
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
                    // A window reset replaces the text instead of extending it
                    // (a 12s sentence collapsing to "Of August"). There used to
                    // be a character-count guess here that banked the tail and
                    // zeroed the cursor — which then said the short text again.
                    // The cursor re-finds the said words in whatever the
                    // recogniser now believes, so a collapse needs no special
                    // case and no magic number.
                    self.partial = result.bestTranscription.formattedString
                    // Stamped where a revision actually arrives. This is the
                    // evidence that tells "still talking, the clock ran out"
                    // (a cut) from "stopped talking" (a finished thought), and
                    // without it the flush can only ever report the second.
                    self.lastPartialAt = Date()
                    // Show the cursor EVERY hypothesis, not just the ones we
                    // flush on. That is what lets it notice the recognizer
                    // throwing away a decode window and hand back the words
                    // that window held (`banked`) before they are gone — the
                    // 12-second sentence collapsing to "Of August". Nothing
                    // else in the app remembers unsent speech.
                    let update = self.cursor.observe(self.partial)
                    if let banked = update.banked?
                        .trimmingCharacters(in: .whitespacesAndNewlines),
                        !banked.isEmpty, !self.enrolling {
                        self.deliver(banked, reason: nil)
                    }
                    if result.isFinal {
                        // A final usually just polishes wording, so a couple of
                        // new words is noise — EXCEPT when the task is ending
                        // with speech never sent at all. That is not a polish,
                        // it is the whole monologue, and gating it away is how
                        // a continuous talker's words reached nobody.
                        self.flushTail(reason: .final)
                        // A final arriving mid-conversation is Apple's task
                        // limit landing, not the speaker stopping.
                        self.swapRecognition(flushPending: false, cause: .taskLimit)
                    } else if update.changed || update.didReset {
                        self.scheduleSilenceFlush()
                    }
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
        pendingSince = nil
        // All-or-nothing: the cursor either hands over everything unsent or
        // nothing at all. The old take(minNewWords:) advanced its record and
        // THEN decided a one- or two-word tail was too short to bother with,
        // which marked those words sent without ever sending them.
        guard let line = cursor.takePending()?
            .trimmingCharacters(in: .whitespacesAndNewlines),
            !line.isEmpty else { return }
        deliver(line, reason: reason)
    }

    /// The one way a line leaves this object. Banked words — speech the
    /// recognizer was about to discard — travel exactly the same path as an
    /// ordinary flush, so they get the same speaker verdict and the same
    /// enrollment protection instead of a second, subtly different route.
    ///
    /// `reason` is nil for those banked words: no timer fired and the
    /// recognizer did not finalise, a decode window was simply thrown away.
    /// `now` is the instant the flush produced this line, and it is what the
    /// backend records as when the words were spoken.
    private func deliver(_ line: String, reason: TranscriptFlushPolicy.Reason?,
                         at now: Date = Date()) {
        // A voice sample is not something he said. Never emit it.
        guard !enrolling else { return }
        // ...and neither is the last sentence said a second time. Not losing
        // words cost this: the recognizer revises, so a ceiling flush and a
        // banked window can hand over ONE sentence twice in slightly
        // different words. Live 2026-08-17, two seconds apart: "Yeah I know
        // where it is" then "Yeah I know it is".
        if let last = lastDelivered,
           TranscriptFlushPolicy.isEchoOfPrevious(
               line, previous: last.text,
               apart: now.timeIntervalSince(last.at),
               window: flushPolicy.echoWindow) {
            return
        }
        lastDelivered = (line, now)
        everEmittedThisTask = true
        // A CUT is the only thing marked as carrying on from what came before.
        // A gap means the sentence ended, and chaining the next, unrelated
        // sentence onto a finished one reads as one rambling thought nobody
        // ever had. This is mechanism, not meaning: it says which timer fired.
        let continuesPrevious = reason == .ceiling
        // The word COUNT, never the words. The journal is exportable from
        // Settings and the events collection already holds the speech itself.
        ListenJournal.shared.record(
            .flushed(reason: reason?.rawValue ?? "banked",
                     words: line.split(whereSeparator: { $0.isWhitespace }).count))
        // Judge the voice behind THIS line before the window moves on. Done
        // here rather than on the audio thread: embedding takes tens of
        // milliseconds and must never stall capture.
        if let speaker, let onSpeaker {
            let tag = speaker.tagForLatestUtterance()
            onSpeaker(line, tag, now, continuesPrevious)
        } else {
            onLine?(line, now, continuesPrevious)
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
    private func swapRecognition(flushPending: Bool, cause: ListenEvent.SwapCause) {
        ListenJournal.shared.record(.recognizerSwapped(cause: cause))
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
        suspended = false
        watchdog?.invalidate()
        watchdog = nil
        silenceFlush?.cancel()
        engine.inputNode.removeTap(onBus: 0)
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
                .flushed(reason: TranscriptFlushPolicy.Reason.final.rawValue,
                         words: tail.split(whereSeparator: { $0.isWhitespace }).count))
            // Stamped as the words leave, not when they are pushed: the push
            // behind this one may not happen until the network is back.
            onLine?(tail, Date(), false)
        }
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
