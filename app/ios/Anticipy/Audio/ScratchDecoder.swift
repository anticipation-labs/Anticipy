import Foundation
import Speech

/// Decode a recorded WAV with the app's OWN recognizer, offline.
///
/// The harness needs four on-device cells (`proof/engine_or_audio.py:239-244`):
/// `sf_ctx` — today's configuration, vocabulary on — and `sf_noctx` — the same
/// decode with `contextualStrings` removed. The difference between them is the
/// R4 verdict, VOCABULARY INERT: the `contextualStrings` line has been in the
/// tree since August, is vouched for by a green gate leg that greps for the
/// literal word, and its effect on recognition has never once been observed
/// (`research/2026-08-25-transcription-quality.md` §1.3).
///
/// WHY THE DECODE HAPPENS ON THE PHONE. `SFSpeechURLRecognitionRequest` against
/// a file is the only way to ask *this* recognizer, on *this* iOS version, with
/// *this* vocabulary, about audio it can be asked twice about. A live decode
/// cannot be repeated, so it can never answer "what would the same words have
/// become with the setting off?"
///
/// WHAT IT IS NOT. It is not the reference decoder. The reference is an
/// independent, stronger recognizer running on the Mac
/// (`proof/reference_decode.py`), and the whole experiment turns on the two
/// being different things. A phone scoring its own homework answers nothing.
///
/// TWO OPTIONS DELIBERATELY DIFFER FROM THE LIVE PATH, and both are forced by
/// the file request rather than chosen: there is no partial-results stream to
/// consume (the file is decoded whole, `isFinal` once), and there is no
/// segmentation — the 2.6s/8s clock never runs. That is correct for this
/// measurement: the harness scores WORDS against a script, and the segmenter
/// decides where lines break, not what they say.
enum ScratchDecoder {

    /// Which decode this is, spelled the way the manifest spells it. The string
    /// goes into the provenance line and into the filename, and
    /// `proof/engine_or_audio.py` reads it to know which cell it is scoring.
    enum Decoder: String, CaseIterable {
        case sfCtx = "sf_ctx"
        case sfNoCtx = "sf_noctx"

        var usesVocabulary: Bool { self == .sfCtx }

        var label: String {
            switch self {
            case .sfCtx: return "Today's settings (vocabulary on)"
            case .sfNoCtx: return "Same, vocabulary off"
            }
        }
    }

    enum Failure: LocalizedError {
        case notAuthorized
        case noRecognizer
        case offDevice
        case engine(String)
        case empty

        var errorDescription: String? {
            switch self {
            case .notAuthorized:
                return "Speech recognition is not permitted. Allow it in Settings and try again."
            case .noRecognizer:
                return "No en_US recognizer on this device."
            case .offDevice:
                // Refused rather than allowed. A cell decoded in Apple's cloud
                // is not the engine this product ships, and the scorer has no
                // way to see the difference after the fact.
                return "This device cannot decode a file on-device. The cell "
                    + "would have been decoded in Apple's cloud, which is not "
                    + "the engine under test, so it was refused."
            case .engine(let why):
                return why
            case .empty:
                // The scorer's own hard-won rule, applied at the source. See
                // proof/engine_or_audio.py:169-191: an empty or one-word
                // transcript and a dead recognizer look identical downstream,
                // and this repo has twice printed a headline off exactly that.
                return "The recognizer returned nothing. An empty transcript "
                    + "and a broken decode are the same shape to the scorer, "
                    + "so nothing was written."
            }
        }
    }

    /// Ask for permission once, so the buttons can say why they are disabled.
    static func authorize(_ done: @escaping (Bool) -> Void) {
        SFSpeechRecognizer.requestAuthorization { status in
            DispatchQueue.main.async { done(status == .authorized) }
        }
    }

    /// Decode `wav` and return the transcript.
    ///
    /// Every option below is copied from the live legacy path
    /// (`PhoneListener.swift:1041-1056`) so the cell describes the shipping
    /// configuration, with exactly one difference per decoder — the vocabulary.
    static func decode(wav: URL, using decoder: Decoder,
                       completion: @escaping (Result<String, Failure>) -> Void) {
        guard SFSpeechRecognizer.authorizationStatus() == .authorized else {
            return completion(.failure(.notAuthorized))
        }
        guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "en_US")),
              recognizer.isAvailable else {
            return completion(.failure(.noRecognizer))
        }
        guard recognizer.supportsOnDeviceRecognition else {
            return completion(.failure(.offDevice))
        }

        let request = SFSpeechURLRecognitionRequest(url: wav)
        request.requiresOnDeviceRecognition = true
        request.shouldReportPartialResults = false
        request.taskHint = .dictation
        request.addsPunctuation = true
        // THE ONE DIFFERENCE BETWEEN THE TWO CELLS.
        request.contextualStrings = decoder.usesVocabulary ? AnticipyVocabulary.current() : []

        var delivered = false
        recognizer.recognitionTask(with: request) { result, error in
            guard !delivered else { return }
            if let error {
                delivered = true
                return DispatchQueue.main.async {
                    completion(.failure(.engine(error.localizedDescription)))
                }
            }
            guard let result, result.isFinal else { return }
            delivered = true
            let text = result.bestTranscription.formattedString
                .trimmingCharacters(in: .whitespacesAndNewlines)
            // One word is refused for the same reason zero is. "you" and
            // "Thank you." are a failed decode's canonical output.
            let words = text.split(whereSeparator: { $0 == " " || $0 == "\n" })
            DispatchQueue.main.async {
                completion(words.count < 2 ? .failure(.empty) : .success(text))
            }
        }
    }

    /// Write a decoded cell where the protocol says it goes, with its
    /// provenance line first.
    ///
    /// The file lands beside the WAV as `arm_a__sf_ctx.txt`. The operator
    /// copies both to the Mac; the double underscore keeps the arm and the
    /// decoder legible in a flat Files listing, and the provenance line inside
    /// is what the harness actually reads — a renamed file cannot lie about
    /// which recording it came from.
    @discardableResult
    static func write(_ transcript: String, for take: ScratchRecorder.Take,
                      decoder: Decoder) -> URL? {
        let name = "arm_\(take.arm.rawValue.lowercased())__\(decoder.rawValue).txt"
        let url = ScratchRecorder.directory.appendingPathComponent(name)
        let body = take.provenance(decoder: decoder.rawValue) + "\n" + transcript + "\n"
        do {
            try body.write(to: url, atomically: true, encoding: .utf8)
            return url
        } catch {
            return nil
        }
    }
}
