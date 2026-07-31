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

    var onLine: ((String) -> Void)?

    private var engine = AVAudioEngine()
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en_US"))
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var silenceFlush: DispatchWorkItem?
    private var watchdog: Timer?
    private var observersInstalled = false

    /// The part of the CURRENT recognition task's text already emitted as
    /// lines. Everything after it is the not-yet-emitted tail.
    private var emitted = ""
    /// Audio captured while no request is accepting it, replayed into the next
    /// one so a swap can never lose speech.
    private var orphanBuffers: [AVAudioPCMBuffer] = []
    private let orphanLock = NSLock()
    private var acceptingAudio = false

    private var lastBufferAt = Date()
    private var lastResultAt = Date()
    private var requestBornAt = Date()
    private var bufferTick = 0

    /// A pause this long ends an utterance. 2.6s, not shorter: people pause
    /// mid-thought ("I'll send the invoice… tomorrow"), and chopping there
    /// splits one intent into fragments. Nothing is closed to achieve this —
    /// the line is simply cut from the running text.
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
        // chains = duplicated lines. begin() only ever arrives via
        // DispatchQueue.main.async, so this guard is race-free.
        guard !isListening else { return }
        installObserversOnce()
        isListening = true
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
            guard let self else { return }
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
        swapRecognition(flushPending: true)
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
                self.swapRecognition(flushPending: true)
                return
            }
            // Rotate only in true silence — nothing pending, nothing to lose.
            if self.pendingTail.isEmpty, self.partial.isEmpty,
               now.timeIntervalSince(self.requestBornAt) > 120 {
                self.swapRecognition(flushPending: false)
                return
            }
            self.suspended = !self.engine.isRunning
        }
        // .common, not .default: a timer in .default never fires while the
        // user is scrolling the feed — the exact moment they're watching.
        RunLoop.main.add(timer, forMode: .common)
        watchdog = timer
    }

    // --------------------------------------------------------- recognition

    /// Text heard on the current task that hasn't been emitted as a line yet.
    private var pendingTail: String {
        guard partial.count > emitted.count,
              partial.hasPrefix(emitted) else { return partial }
        return String(partial.dropFirst(emitted.count))
    }

    private func startRecognition() {
        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        if recognizer?.supportsOnDeviceRecognition == true {
            req.requiresOnDeviceRecognition = true
        }
        requestBornAt = Date()
        lastResultAt = Date()
        emitted = ""
        partial = ""

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
                    let text = result.bestTranscription.formattedString
                    // A window reset replaces the text instead of extending it
                    // (a 12s sentence collapsing to "Of August"). Bank what we
                    // had before accepting the new, shorter reality.
                    if !text.hasPrefix(self.emitted), self.partial.count > text.count + 10 {
                        self.flushTail()
                        self.emitted = ""
                    }
                    self.partial = text
                    if result.isFinal {
                        self.flushTail()
                        self.swapRecognition(flushPending: false)
                    } else {
                        self.scheduleSilenceFlush()
                    }
                } else if error != nil {
                    // The recognizer died. Whatever was heard is real speech —
                    // emit it, then take a fresh one; buffered audio carries
                    // across the seam.
                    self.swapRecognition(flushPending: true)
                }
            }
        }
    }

    /// Emit everything heard but not yet sent, as one line.
    private func flushTail() {
        silenceFlush?.cancel()
        let tail = pendingTail.trimmingCharacters(in: .whitespacesAndNewlines)
        emitted = partial
        guard !tail.isEmpty else { return }
        onLine?(tail)
    }

    /// After a pause, cut a line from the running text — WITHOUT ending the
    /// request, so speech that follows keeps flowing into the same recognizer
    /// and nothing is orphaned.
    private func scheduleSilenceFlush() {
        silenceFlush?.cancel()
        guard !pendingTail.isEmpty else { return }
        let work = DispatchWorkItem { [weak self] in
            guard let self, self.isListening else { return }
            self.flushTail()
        }
        silenceFlush = work
        DispatchQueue.main.asyncAfter(deadline: .now() + utteranceGap, execute: work)
    }

    /// Retire the current recognition task and start a clean one. Audio keeps
    /// being captured into the orphan buffer throughout and is replayed.
    private func swapRecognition(flushPending: Bool) {
        silenceFlush?.cancel()
        if flushPending { flushTail() }
        orphanLock.lock()
        acceptingAudio = false
        orphanLock.unlock()
        task?.cancel()
        task = nil
        request = nil
        guard isListening else { return }
        startRecognition()
    }

    func stop() {
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
        if !tail.isEmpty { onLine?(tail) }
        task?.finish()
        request = nil
        task = nil
        partial = ""
        emitted = ""
    }
}
