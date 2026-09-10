import AVFoundation
import Foundation
import Speech

/// The seam between "audio buffers" and "words", so the recognizer under
/// PhoneListener and the pendant's transcription home are exchangeable
/// without either caller knowing which engine is listening.
protocol ListenRequestEngine: AnyObject {
    /// Each phrase's text, on the main queue. The Bool settles that phrase;
    /// it does not end the analyzer request. PhoneListener flushes and resets
    /// its phrase cursor on finality without replacing the engine. The pendant
    /// home likewise emits finalized phrases only. The shipping .transcription
    /// preset is final-only; this is not a cumulative legacy-task transcript.
    var onResult: ((_ text: String, _ isFinal: Bool) -> Void)? { get set }

    /// The engine died mid-request — or could not be provisioned at all. The
    /// listener treats this exactly like the legacy recognizer's error path:
    /// emit what was heard, take a fresh one, and after three strikes finish
    /// the session on the legacy recognizer instead of spinning forever.
    var onError: (() -> Void)? { get set }

    /// All results already published by the module have reached onResult.
    /// Finishing the analyzer alone is not proof that its results were read.
    var onFinished: (() -> Void)? { get set }

    /// Start analyzing. Called once, after the callbacks are wired and before
    /// the first append — the engine negotiates formats and provisions assets
    /// here, and buffers appended before it completes are held and replayed
    /// in order. An engine whose module or locale cannot be provisioned
    /// reports `onError` instead of speaking.
    func begin()

    func append(_ buffer: AVAudioPCMBuffer)

    /// Audio that WAS captured but must never be transcribed — the air inside
    /// a BLE gap. The engine advances its clock past it and receives no
    /// silence, so no model is ever handed a hole to speak through.
    func skipSilence(seconds: TimeInterval)

    /// End the request: finalize everything held, deliver the tail, stop.
    func finish()

    /// Privacy/account boundaries discard pending words and cancel owned work.
    func cancel()
}

/// iOS 26's SpeechTranscriber under the `ListenRequestEngine` contract.
///
/// Why this exists: the legacy recognizer measured 9.02% word error on clean
/// speech against this engine's 2.12% — four times the mistakes, on the same
/// audio, with the same promise. SpeechTranscriber runs entirely on device
/// (system-managed model, nothing bundled, nothing uploaded), so LOCAL-FIRST
/// rule 1 holds unchanged: raw audio never leaves the phone.
///
/// Lifecycle: one engine per recognition request, matching PhoneListener's
/// swap rhythm. `begin()` negotiates the locale and assets asynchronously —
/// buffers appended before it completes are held and replayed in order, the
/// orphan-buffer pattern one level down.
///
/// The one documented trap this class exists to get right: the tail of a
/// transcript never emits unless `finalizeAndFinishThroughEndOfInput()` runs.
/// `finish()` also waits for the results reader. The caller must keep its
/// identity and delivery lease alive until onFinished to receive that tail.
///
/// THE GAP LAW, IMPLEMENTED HERE AT THE CLOCK: every buffer is stamped with
/// the stream's running time, and `skipSilence` advances that clock without
/// yielding anything. After a skip the next buffer carries a LATER time-code,
/// which is exactly how Apple's docs say to skip audio — the analyzer sees
/// time move and no bytes for it. A recognizer is never handed a hole, so it
/// can never speak through one; the hole belongs to GapMarker, in the feed.
@available(iOS 26.0, *)
final class SpeechAnalyzerRequestEngine: NSObject, ListenRequestEngine {

    var onResult: ((String, Bool) -> Void)?
    var onError: (() -> Void)?
    var onFinished: (() -> Void)?

    private let desiredLocale: Locale
    private var transcriber: SpeechTranscriber?
    private var analyzer: SpeechAnalyzer?
    private var builder: AsyncStream<AnalyzerInput>.Continuation?
    private var audioConverter: AVAudioConverter?
    private var converterSourceFormat: AVAudioFormat?
    private var targetFormat: AVAudioFormat?
    private var held: [AVAudioPCMBuffer] = []
    private var clockSeconds: Double = 0
    private var finished = false
    private var cancelled = false
    private var failureReported = false
    private var provisioningTask: Task<Void, Never>?
    private var startTask: Task<Void, Never>?
    private var resultsTask: Task<Void, Never>?
    private var finalizationTask: Task<Void, Never>?
    private var cancellationTask: Task<Void, Never>?

    /// Everything below runs on this queue in order: conversion setup,
    /// buffer conversion, clock advances. The AsyncStream continuation is
    /// thread-safe, but ORDER is the contract — the transcription of second
    /// five must never be yielded before second four.
    private let queue = DispatchQueue(label: "ai.anticipy.listen.analyzer")

    static func make(locale: Locale) -> SpeechAnalyzerRequestEngine {
        SpeechAnalyzerRequestEngine(locale: locale)
    }

    init(locale: Locale) {
        self.desiredLocale = locale
        super.init()
    }

    func begin() {
        let desired = desiredLocale
        queue.async { [weak self] in
            guard let self, !self.finished, self.provisioningTask == nil else { return }
            self.provisioningTask = Task { [weak self] in
                guard let self else { return }
                do {
                    try Task.checkCancellation()
                    // Provisioning failures use the listener's existing
                    // session-scoped three-strike fallback.
                    guard SpeechTranscriber.isAvailable,
                          let supported = await SpeechTranscriber.supportedLocale(equivalentTo: desired) else {
                        self.reportFailure()
                        return
                    }
                    try Task.checkCancellation()
                    let transcriber = SpeechTranscriber(locale: supported, preset: .transcription)
                    let analyzer = SpeechAnalyzer(modules: [transcriber])
                    // This may download a model, never captured audio.
                    if let install = try await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
                        try Task.checkCancellation()
                        try await install.downloadAndInstall()
                    }
                    try Task.checkCancellation()
                    let fallback = AVAudioFormat(standardFormatWithSampleRate: 16_000, channels: 1)
                    let format = await SpeechAnalyzer.bestAvailableAudioFormat(
                        compatibleWith: [transcriber]) ?? fallback
                    try Task.checkCancellation()
                    guard let format else {
                        self.reportFailure()
                        return
                    }
                    self.warmUp(analyzer: analyzer, transcriber: transcriber,
                                stream: self.makeStream(), format: format)
                } catch is CancellationError {
                    // Only cancellation requested on our owned Task is a
                    // silent stop. The underlying service can cancel itself
                    // too; that is an outage the listener must recover from.
                    if !Task.isCancelled { self.reportFailure() }
                } catch {
                    self.reportFailure()
                }
            }
        }
    }

    private func makeStream() -> AsyncStream<AnalyzerInput> {
        var continuation: AsyncStream<AnalyzerInput>.Continuation!
        let stream = AsyncStream<AnalyzerInput> { continuation = $0 }
        queue.sync {
            if finished { continuation.finish() }
            else { builder = continuation }
        }
        return stream
    }

    private func warmUp(analyzer: SpeechAnalyzer, transcriber: SpeechTranscriber,
                        stream: AsyncStream<AnalyzerInput>, format: AVAudioFormat) {
        queue.async { [weak self] in
            guard let self, !self.finished else { return }
            self.analyzer = analyzer
            self.transcriber = transcriber
            self.targetFormat = format
            let replay = self.held
            self.held = []
            for buffer in replay { self.convertAndYield(buffer) }
            // Installing state and taking ownership of both tasks is atomic
            // with finish/cancel. A resumed asset await cannot launch work
            // after the queue has already closed this request.
            self.startTask = Task { [weak self] in
                do {
                    try Task.checkCancellation()
                    try await analyzer.start(inputSequence: stream)
                } catch is CancellationError {
                    if !Task.isCancelled { self?.reportFailure() }
                } catch {
                    self?.reportFailure()
                }
            }
            self.resultsTask = Task { [weak self] in
                do {
                    for try await result in transcriber.results {
                        try Task.checkCancellation()
                        let text = String(result.text.characters)
                        guard !text.isEmpty else { continue }
                        let isFinal = result.isFinal
                        await MainActor.run { [weak self] in
                            guard let self, !self.queue.sync(execute: { self.cancelled }) else { return }
                            self.onResult?(text, isFinal)
                        }
                    }
                } catch is CancellationError {
                    if !Task.isCancelled { self?.reportFailure() }
                } catch {
                    self?.reportFailure()
                }
            }
        }
    }

    private func reportFailure() {
        queue.async { [weak self] in
            guard let self, !self.cancelled, !self.failureReported else { return }
            self.failureReported = true
            DispatchQueue.main.async { [weak self] in
                guard let self, !self.queue.sync(execute: { self.cancelled }) else { return }
                self.onError?()
            }
        }
    }

    private func canCompleteSuccessfully() -> Bool {
        // A task may have just enqueued its error report. This serialized
        // read also joins that report before a success callback is possible.
        queue.sync { !cancelled && !failureReported }
    }

    func append(_ buffer: AVAudioPCMBuffer) {
        queue.async { [weak self] in
            guard let self, !self.finished else { return }
            if self.targetFormat != nil {
                self.convertAndYield(buffer)
            } else if self.held.count < 600 {
                // Keep ordering and the memory bound. The overflow path is
                // an explicit capture gap plus one recoverable engine error.
                self.held.append(buffer)
            } else {
                DispatchQueue.main.async {
                    ListenJournal.shared.record(.buffersDropped(count: 1))
                }
                self.reportFailure()
            }
        }
    }

    /// MUST run on `queue`. Converts to the analyzer's format when the source
    /// differs (the phone tap speaks 16 kHz measurement-Float32; the module
    /// may want something else), then yields with the running time-code.
    private func convertAndYield(_ buffer: AVAudioPCMBuffer) {
        guard let builder else { return }
        let target = targetFormat ?? buffer.format

        var converted: AVAudioPCMBuffer?
        if buffer.format == target {
            converted = buffer
        } else {
            if converterSourceFormat != buffer.format {
                converterSourceFormat = buffer.format
                audioConverter = AVAudioConverter(from: buffer.format, to: target)
            }
            guard let audioConverter else { return }
            let ratio = target.sampleRate / buffer.format.sampleRate
            let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 1_024
            guard let out = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: capacity) else { return }
            var consumed = false
            var conversionError: NSError?
            let status = audioConverter.convert(to: out, error: &conversionError) { _, outStatus in
                if consumed {
                    outStatus.pointee = .noDataNow
                    return nil
                }
                consumed = true
                outStatus.pointee = .haveData
                return buffer
            }
            guard status != .error, conversionError == nil, out.frameLength > 0 else { return }
            converted = out
        }

        let start = CMTime(seconds: clockSeconds, preferredTimescale: 16_000)
        if let pcm = converted, pcm.frameLength > 0 {
            builder.yield(AnalyzerInput(buffer: pcm, bufferStartTime: start))
        }
        // The clock advances by the SOURCE duration whether or not a
        // conversion produced samples: time that was captured is time that
        // passed, and the timeline must not quietly lose it.
        clockSeconds += Double(buffer.frameLength) / buffer.format.sampleRate
    }

    func skipSilence(seconds: TimeInterval) {
        queue.async { [weak self] in
            guard let self, !self.finished else { return }
            self.clockSeconds += seconds
        }
    }

    func finish() {
        queue.async { [weak self] in
            guard let self, !self.finished else { return }
            self.finished = true
            self.provisioningTask?.cancel()
            self.builder?.finish()
            guard let analyzer = self.analyzer else {
                let dropped = self.held.count
                self.held.removeAll()
                DispatchQueue.main.async { [weak self] in
                    guard let self, !self.queue.sync(execute: { self.cancelled }) else { return }
                    if dropped > 0 {
                        ListenJournal.shared.record(.buffersDropped(count: dropped))
                        self.onError?()
                    }
                    self.onFinished?()
                }
                return
            }
            let startTask = self.startTask
            let resultsTask = self.resultsTask
            self.finalizationTask = Task { [weak self] in
                await startTask?.value
                guard !Task.isCancelled, self?.canCompleteSuccessfully() == true else { return }
                // The documented trap, handled: without this call the tail of
                // the transcript never emits and the last words of every
                // request die in the model's pipeline.
                do { try await analyzer.finalizeAndFinishThroughEndOfInput() }
                catch is CancellationError {
                    if !Task.isCancelled { self?.reportFailure() }
                    return
                }
                catch { self?.reportFailure(); return }
                // Apple's finish closes the results stream, but queued
                // results still have to be iterated before the caller retires
                // the identity that owns those words.
                await resultsTask?.value
                guard !Task.isCancelled, self?.canCompleteSuccessfully() == true else { return }
                await MainActor.run { [weak self] in
                    guard let self, self.canCompleteSuccessfully() else { return }
                    self.onFinished?()
                }
            }
        }
    }

    func cancel() {
        queue.async { [weak self] in
            guard let self, !self.cancelled else { return }
            self.cancelled = true
            self.finished = true
            self.provisioningTask?.cancel()
            self.startTask?.cancel()
            self.resultsTask?.cancel()
            self.finalizationTask?.cancel()
            self.builder?.finish()
            self.held.removeAll()
            if let analyzer = self.analyzer {
                self.cancellationTask = Task { await analyzer.cancelAndFinishNow() }
            }
            self.analyzer = nil
            self.transcriber = nil
        }
    }

    deinit {
        builder?.finish()
        provisioningTask?.cancel()
        startTask?.cancel()
        resultsTask?.cancel()
        finalizationTask?.cancel()
    }
}
