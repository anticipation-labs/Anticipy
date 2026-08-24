import AVFoundation
import Foundation
import Speech

/// On-device transcription via Apple's speech recognizer with
/// `requiresOnDeviceRecognition` — no audio ever leaves the phone.
/// Selected by the Local/Cloud toggle in Settings.
final class LocalTranscriber: NSObject {
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en_US"))
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var lastEmitted = ""

    var onTranscript: ((String) -> Void)?

    func start() {
        SFSpeechRecognizer.requestAuthorization { _ in }
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.requiresOnDeviceRecognition = true
        request.shouldReportPartialResults = true
        // Same lexicon as PhoneListener: the pendant's transcripts must not
        // spell "Anticipy" differently from the phone's.
        request.contextualStrings = AnticipyVocabulary.current()
        self.request = request
        task = recognizer?.recognitionTask(with: request) { [weak self] result, _ in
            guard let self, let result, result.isFinal else { return }
            let text = result.bestTranscription.formattedString
            guard text != self.lastEmitted, !text.isEmpty else { return }
            self.lastEmitted = text
            DispatchQueue.main.async { self.onTranscript?(text) }
        }
    }

    /// Pendant audio arrives as decoded 16 kHz mono PCM buffers.
    func append(pcmBuffer: AVAudioPCMBuffer) {
        request?.append(pcmBuffer)
    }

    func stop() {
        request?.endAudio()
        task?.cancel()
    }
}
