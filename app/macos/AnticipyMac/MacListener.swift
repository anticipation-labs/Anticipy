import AVFoundation
import Foundation
import Speech

/// The Mac's ears. Same engine as the phone (iOS/macOS 26 SpeechTranscriber),
/// same law: audio is decoded in memory, never written, never uploaded.
///
/// Threading: the analyzer's results arrive on a background task and are
/// marshalled to main; the flush timer owns the line lifecycle. A "line" is
/// a stretch of speech bracketed by silence (2.5 s) or a 15 s ceiling — the
/// same shape the phone sends, so the segmenter sees one kind of day no
/// matter which device heard it.
@available(macOS 26.0, *)
final class MacListener: NSObject, ObservableObject {

    enum State: String {
        case idle, starting, listening, denied
    }

    @Published var state: State = .idle
    @Published var lastLine: String = ""
    /// Every line this session produced, newest last. The menu shows a count;
    /// the debug window shows the words.
    @Published var lines: [Line] = []

    struct Line: Identifiable {
        let id = UUID()
        let text: String
        let startedAt: Date
        let endedAt: Date
        var posted: Bool = false
    }

    var onLine: ((Line) -> Void)?

    private let audioEngine = AVAudioEngine()
    private var transcriber: SpeechTranscriber?
    private var analyzer: SpeechAnalyzer?
    private var inputBuilder: AsyncStream<AnalyzerInput>.Continuation?
    private var resultsTask: Task<Void, Never>?
    private var analyzeTask: Task<Void, Never>?

    /// When the current line's words first appeared.
    private var lineStartedAt: Date?
    private var lastSpeechAt: Date?
    private var pendingText: [String] = []
    private var flushTimer: Timer?

    private let silenceFlush: TimeInterval = 2.5
    private let ceilingFlush: TimeInterval = 15.0

    static func isSupported() -> Bool {
        if #available(macOS 26.0, *) { return SpeechTranscriber.isAvailable }
        return false
    }

    func start() {
        guard state == .idle || state == .denied else { return }
        guard #available(macOS 26.0, *) else {
            state = .denied
            return
        }
        state = .starting

        SFSpeechRecognizer.requestAuthorization { [weak self] _ in
            DispatchQueue.main.async {
                Task { await self?.beginListening() }
            }
        }
    }

    @available(macOS 26.0, *)
    private func beginListening() async {
        guard let locale = await SpeechTranscriber.supportedLocale(equivalentTo: Locale(identifier: "en_US")) else {
            state = .denied
            return
        }
        let transcriber = SpeechTranscriber(locale: locale, preset: .transcription)
        let analyzer = SpeechAnalyzer(modules: [transcriber])
        self.transcriber = transcriber
        self.analyzer = analyzer

        var builder: AsyncStream<AnalyzerInput>.Continuation!
        let stream = AsyncStream<AnalyzerInput> { builder = $0 }
        inputBuilder = builder

        let inputTask = Task {
            do { try await analyzer.start(inputSequence: stream) } catch { await self.reportError() }
        }
        analyzeTask = inputTask
        resultsTask = Task { [weak self] in
            do {
                for try await result in transcriber.results {
                    let text = String(result.text.characters).trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !text.isEmpty else { continue }
                    await MainActor.run {
                        self?.absorb(text, isFinal: result.isFinal)
                    }
                }
            } catch { /* session finished or failed; the menu reflects state */ }
        }

        // The model may need a one-time download on a fresh machine. Done
        // before the tap opens, so the first words are not the test case.
        Task {
            if let install = try? await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
                try? await install.downloadAndInstall()
            }
            let format = (try? await SpeechAnalyzer.bestAvailableAudioFormat(compatibleWith: [transcriber]))
                ?? AVAudioFormat(standardFormatWithSampleRate: 16_000, channels: 1)
            guard let format else {
                await MainActor.run { self.state = .denied }
                return
            }
            await MainActor.run { self.openTap(format: format) }
        }
    }

    @available(macOS 26.0, *)
    private func openTap(format: AVAudioFormat) {
        let input = audioEngine.inputNode
        let tapFormat = AVAudioFormat(standardFormatWithSampleRate: 16_000, channels: 1) ?? input.outputFormat(forBus: 0)
        var converter: AVAudioConverter? = format != tapFormat ? AVAudioConverter(from: tapFormat, to: format) : nil

        input.installTap(onBus: 0, bufferSize: 4_096, format: tapFormat) { [weak self] buffer, _ in
            guard let self else { return }
            let yield: (AVAudioPCMBuffer) -> Void = { pcm in
                self.inputBuilder?.yield(AnalyzerInput(buffer: pcm, bufferStartTime: nil))
            }
            if let converter {
                let ratio = format.sampleRate / tapFormat.sampleRate
                guard let out = AVAudioPCMBuffer(pcmFormat: format,
                                                 frameCapacity: AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 1_024) else { return }
                var consumed = false
                var err: NSError?
                let status = converter.convert(to: out, error: &err) { _, outStatus in
                    if consumed { outStatus.pointee = .noDataNow; return nil }
                    consumed = true
                    outStatus.pointee = .haveData
                    return buffer
                }
                if status != .error, err == nil, out.frameLength > 0 {
                    yield(out)
                }
            } else {
                yield(buffer)
            }
        }
        audioEngine.prepare()
        do {
            try audioEngine.start()
            state = .listening
        } catch {
            state = .denied
        }
    }

    private func absorb(_ text: String, isFinal: Bool) {
        let now = Date()
        if lineStartedAt == nil { lineStartedAt = now }
        lastSpeechAt = now
        if !pendingText.lastFrameContains(text) {
            pendingText.append(text)
        }
        lastLine = text
        scheduleFlush()
        if pendingText.joined(separator: " ").count > 400 {
            flushNow()
        }
    }

    private func scheduleFlush() {
        flushTimer?.invalidate()
        flushTimer = Timer.scheduledTimer(withTimeInterval: silenceFlush, repeats: false) { [weak self] _ in
            self?.flushNow()
        }
    }

    /// Emits the pending line. Silence or the ceiling ends a line; nothing
    /// else does. The envelope keeps both instants so the segmenter measures
    /// real speech, not flush-to-flush drift.
    func flushNow() {
        flushTimer?.invalidate()
        flushTimer = nil
        guard !pendingText.isEmpty else { return }
        let text = pendingText.joined(separator: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        pendingText.removeAll()
        let startedAt = lineStartedAt ?? Date()
        let endedAt = lastSpeechAt ?? Date()
        lineStartedAt = nil
        lastSpeechAt = nil
        guard !text.isEmpty else { return }
        let line = Line(text: text, startedAt: startedAt, endedAt: endedAt)
        lines.append(line)
        onLine?(line)
    }

    private func reportError() {
        DispatchQueue.main.async { [weak self] in self?.state = .denied }
    }

    func stop() {
        flushNow()
        audioEngine.inputNode.removeTap(onBus: 0)
        audioEngine.stop()
        inputBuilder?.finish()
        analyzeTask?.cancel()
        resultsTask?.cancel()
        transcriber = nil
        analyzer = nil
        state = .idle
    }
}

private extension Array where Element == String {
    /// The recognizer revises its running text; keeping every revision would
    /// repeat the sentence. Keep the frame only when it is not the tail
    /// restated.
    func lastFrameContains(_ text: String) -> Bool {
        guard let last = last else { return false }
        return text.contains(last) || last.contains(text)
    }
}
