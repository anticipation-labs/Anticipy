import AVFoundation
import Foundation
import Speech

/// Pendant-less listening: the phone's own microphone feeds Apple's speech
/// recognizer (on-device when supported), emitting one line per utterance.
/// This is the same transcript stream the pendant produces, so everything
/// downstream — brain, memory, jobs — is identical.
///
/// Listening is SELF-HEALING: iOS kills mic capture constantly (Siri, calls,
/// notification sounds, AirPods connecting, media-services resets) and every
/// one of those used to stop transcription silently while the UI still said
/// "Listening" — the user experiences that as "it forgets after a few
/// sentences". Interruption/route observers plus a watchdog now bring the
/// whole chain back, and `suspended` tells the UI honestly when the mic is
/// down instead of pretending.
final class PhoneListener: NSObject, ObservableObject {
    @Published var isListening = false
    @Published var partial = ""
    @Published var authorized = true
    /// True while the user wants listening but the mic is down (interruption,
    /// route change) and recovery is in progress. The UI must say so.
    @Published var suspended = false

    var onLine: ((String) -> Void)?

    // var, not let: after a media-services reset Apple's contract (QA1749)
    // is that every audio object must be DESTROYED and recreated — an
    // orphaned engine can never start again, and touching it can crash.
    private var engine = AVAudioEngine()
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en_US"))
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var silenceFlush: DispatchWorkItem?
    private var watchdog: Timer?
    private var observersInstalled = false

    /// Apple's recognizer rarely finalizes on its own mid-stream; left alone,
    /// one task accumulates sentences until it times out (~1 min) and the
    /// error path used to drop everything on the floor. Instead, treat a pause
    /// this long as the end of an utterance and force a final result.
    /// 2.6s, not shorter: people pause mid-thought ("I'll send the invoice…
    /// tomorrow"), and chopping there splits one intent into fragments.
    private let utteranceGap: TimeInterval = 2.6

    func start() {
        SFSpeechRecognizer.requestAuthorization { [weak self] auth in
            guard let self else { return }
            guard auth == .authorized else {
                DispatchQueue.main.async { self.authorized = false }
                return
            }
            AVAudioSession.sharedInstance().requestRecordPermission { ok in
                DispatchQueue.main.async {
                    guard ok else { self.authorized = false; return }
                    self.begin()
                }
            }
        }
    }

    private func begin() {
        // Re-entrancy guard: onAppear + scenePhase both fire at launch, and
        // isListening can't be checked by callers because start() runs through
        // two async permission callbacks. Two begin()s = two recognition
        // chains = duplicated lines pushed to the brain. begin() only ever
        // arrives via DispatchQueue.main.async, so this guard is race-free.
        guard !isListening else { return }
        installObserversOnce()
        isListening = true
        configureAndStartEngine()
        startRecognition()
        startWatchdog()
    }

    /// (Re)build the capture chain: audio session, tap (with the CURRENT
    /// route's format — it changes when the mic changes), engine.
    private func configureAndStartEngine() {
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.record, mode: .measurement, options: .duckOthers)
        try? session.setActive(true, options: .notifyOthersOnDeactivation)

        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        // While a phone call owns the session, the input format can be
        // 0 Hz / 0 channels — installTap with it raises an NSException that
        // no try? can catch. Stand down; the watchdog retries after the call.
        guard format.sampleRate > 0, format.channelCount > 0 else {
            suspended = true
            return
        }
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            self?.request?.append(buffer)
        }
        engine.prepare()
        try? engine.start()
        suspended = !engine.isRunning
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
                self.suspended = true   // honest: the mic is gone right now
            } else {
                self.recoverAudio()     // ended (or unknown): take it back
            }
        }
        nc.addObserver(forName: AVAudioSession.routeChangeNotification,
                       object: nil, queue: .main) { [weak self] note in
            // AirPods in, cable out, speakerphone — the input (and its
            // format) may have changed under the tap. Rebuild. But ignore
            // .categoryChange: our own setCategory posts one, and reacting
            // to it rebuilds gratuitously right after every start.
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
        if task == nil {
            startRecognition()
        } else {
            // A live request's format was fixed by its first buffer; feeding
            // it the NEW route's format garbles recognition. Finalize it —
            // its words are emitted, not lost — and the isFinal path rolls
            // into a fresh task that accepts the new format.
            request?.endAudio()
        }
    }

    /// Last line of defense: whatever stalled without a notification —
    /// engine dead, recognition task gone — comes back within seconds.
    private func startWatchdog() {
        watchdog?.invalidate()
        let timer = Timer(timeInterval: 4, repeats: true) { [weak self] _ in
            guard let self, self.isListening else { return }
            if !self.engine.isRunning { self.recoverAudio(); return }
            if self.task == nil, self.recognizer?.isAvailable != false { self.startRecognition() }
            self.suspended = !self.engine.isRunning
        }
        // .common, not .default: a timer in .default never fires while the
        // user is scrolling the feed — the exact moment they're watching.
        RunLoop.main.add(timer, forMode: .common)
        watchdog = timer
    }

    // --------------------------------------------------------- recognition

    /// One recognition task per utterance: when the recognizer finalizes
    /// (pause in speech), emit the line and roll straight into the next task.
    private func startRecognition() {
        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        if recognizer?.supportsOnDeviceRecognition == true {
            req.requiresOnDeviceRecognition = true
        }
        request = req
        task = recognizer?.recognitionTask(with: req) { [weak self] result, error in
            guard let self else { return }
            if let result {
                let text = result.bestTranscription.formattedString
                DispatchQueue.main.async {
                    // Stale-callback guard: only the CURRENT chain may touch
                    // shared state — a finalized/superseded task's late
                    // callbacks must never clobber or double-emit.
                    guard self.request === req else { return }
                    self.partial = text
                    if result.isFinal {
                        self.silenceFlush?.cancel()
                        self.partial = ""
                        self.task = nil
                        self.request = nil
                        // stop() already flushed the open utterance, so only
                        // emit finals while actively listening.
                        if !text.isEmpty, self.isListening { self.onLine?(text) }
                        if self.isListening { self.startRecognition() }
                    } else {
                        self.scheduleSilenceFlush()
                    }
                }
            } else if error != nil {
                // Recognizer died (timeout, service hiccup). Whatever was on
                // screen is still real speech — emit it, never drop it.
                DispatchQueue.main.async {
                    guard self.request === req else { return }
                    self.silenceFlush?.cancel()
                    let pending = self.partial.trimmingCharacters(in: .whitespacesAndNewlines)
                    self.partial = ""
                    self.task = nil
                    self.request = nil
                    if !pending.isEmpty, self.isListening { self.onLine?(pending) }
                    if self.isListening { self.startRecognition() }
                }
            }
        }
    }

    /// After a pause in speech, end the current request so the recognizer
    /// finalizes this utterance; the final-result path emits it and rolls
    /// straight into a fresh task for the next one.
    private func scheduleSilenceFlush() {
        silenceFlush?.cancel()
        guard !partial.isEmpty else { return }
        let work = DispatchWorkItem { [weak self] in
            guard let self, self.isListening else { return }
            self.request?.endAudio()
        }
        silenceFlush = work
        DispatchQueue.main.asyncAfter(deadline: .now() + utteranceGap, execute: work)
    }

    func stop() {
        isListening = false
        suspended = false
        watchdog?.invalidate()
        watchdog = nil
        silenceFlush?.cancel()
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        request?.endAudio()
        // Emit whatever was said in the still-open utterance; cancelling the
        // task would otherwise drop it before the final result arrives.
        let pending = partial.trimmingCharacters(in: .whitespacesAndNewlines)
        if !pending.isEmpty { onLine?(pending) }
        task?.finish()
        request = nil
        task = nil
        partial = ""
    }
}
