import AVFoundation
import Foundation
import Speech

/// On-device transcription for pendant audio — decoded 16 kHz mono PCM
/// arrives as buffers, words leave as text, and no audio ever leaves the
/// phone. This is the intended home for `startPendantTranscription`.
///
/// Engine selection: iOS 26 runs Apple's SpeechTranscriber through
/// `SpeechAnalyzerRequestEngine` (2.12% word error on clean speech against
/// the legacy recognizer's 9.02% — see that file); anything older keeps the
/// SFSpeechRecognizer path below. Both are on-device only, so the
/// LOCAL-FIRST law does not care which one is listening.
///
/// Emission semantics differ by engine and callers must know: the legacy
/// recognizer emits the task's whole running text on its final result
/// (deduped); iOS 26 emits each finalized phrase once, in order. There are
/// zero call sites today — `startPendantTranscription` still waits on an
/// Opus decoder — so no consumer can be surprised, and whoever wires it
/// reads this paragraph first.
final class LocalTranscriber: NSObject {
    private var analyzerEngine: ListenRequestEngine?
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en_US"))
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var lastEmitted = ""

    var onTranscript: ((String) -> Void)?

    func start() {
        SFSpeechRecognizer.requestAuthorization { _ in }
        if #available(iOS 26.0, *), ListenEnginePolicy.usesAnalyzerNow {
            let engine = SpeechAnalyzerRequestEngine.make(locale: Locale(identifier: "en_US"))
            analyzerEngine = engine
            engine.onResult = { [weak self] text, isFinal in
                guard let self, isFinal else { return }
                self.emit(text)
            }
            engine.onError = { [weak self] in
                // The engine session died. Nothing was held here — the caller
                // owns the audio — so the honest response is to say so and
                // stop, not to spin a replacement against a dead session.
                self?.analyzerEngine = nil
            }
            engine.begin()
            return
        }
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
        if let analyzerEngine {
            analyzerEngine.append(pcmBuffer)
        } else {
            request?.append(pcmBuffer)
        }
    }

    /// Audio the pendant captured but nobody can transcribe — a BLE gap the
    /// assembler measured. The engine skips its clock past it; the silence
    /// is never handed to a model, so the transcript carries a mark instead
    /// of an invention.
    func skipSilence(seconds: TimeInterval) {
        analyzerEngine?.skipSilence(seconds: seconds)
    }

    func stop() {
        analyzerEngine?.finish()
        analyzerEngine = nil
        request?.endAudio()
        task?.cancel()
        request = nil
        task = nil
    }

    private func emit(_ text: String) {
        guard text != lastEmitted, !text.isEmpty else { return }
        lastEmitted = text
        DispatchQueue.main.async { self.onTranscript?(text) }
    }
}
