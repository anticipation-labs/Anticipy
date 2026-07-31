import AVFoundation
import Foundation
import Speech

/// Pendant-less listening: the phone's own microphone feeds Apple's speech
/// recognizer (on-device when supported), emitting one line per utterance.
/// This is the same transcript stream the pendant produces, so everything
/// downstream — brain, memory, jobs — is identical.
final class PhoneListener: NSObject, ObservableObject {
    @Published var isListening = false
    @Published var partial = ""
    @Published var authorized = true

    var onLine: ((String) -> Void)?

    private let engine = AVAudioEngine()
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en_US"))
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var silenceFlush: DispatchWorkItem?

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
        let session = AVAudioSession.sharedInstance()
        try? session.setCategory(.record, mode: .measurement, options: .duckOthers)
        try? session.setActive(true, options: .notifyOthersOnDeactivation)

        startRecognition()

        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: format) { [weak self] buffer, _ in
            self?.request?.append(buffer)
        }
        engine.prepare()
        try? engine.start()
        isListening = true
    }

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
                    self.partial = text
                    if result.isFinal {
                        self.silenceFlush?.cancel()
                        self.partial = ""
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
                    self.silenceFlush?.cancel()
                    let pending = self.partial.trimmingCharacters(in: .whitespacesAndNewlines)
                    self.partial = ""
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
