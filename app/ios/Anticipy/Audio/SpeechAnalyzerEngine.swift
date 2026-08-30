import AVFoundation
import Foundation
import Speech

/// The seam between "audio buffers" and "words", so the recognizer under
/// PhoneListener and the pendant's transcription home are exchangeable
/// without either caller knowing which engine is listening.
protocol ListenRequestEngine: AnyObject {
    /// Every revision of the running text, on the main queue — the same role
    /// SFSpeechRecognizer's per-result callback plays for the cursor. The
    /// Bool is whether this revision is final; PhoneListener deliberately
    /// ignores it (the cursor owns revisions, the watchdog owns swaps), the
    /// pendant home acts on it (a backfill emits finalized phrases only).
    var onResult: ((_ text: String, _ isFinal: Bool) -> Void)? { get set }

    /// The engine died mid-request — or could not be provisioned at all. The
    /// listener treats this exactly like the legacy recognizer's error path:
    /// emit what was heard, take a fresh one, and after three strikes finish
    /// the session on the legacy recognizer instead of spinning forever.
    var onError: (() -> Void)? { get set }

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
/// `finish()` does, so the last words of every request reach the cursor.
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
        Task { [weak self] in
            guard let self else { return }
            // Device and locale support: an iOS 26 phone without the asset,
            // or with a locale the model does not cover, reports an error to
            // the listener rather than listening badly in silence. The
            // three-strike fallback one level up owns what happens next.
            guard SpeechTranscriber.isAvailable,
                  let supported = await SpeechTranscriber.supportedLocale(equivalentTo: desired) else {
                await MainActor.run { self.onError?() }
                return
            }
            let transcriber = SpeechTranscriber(locale: supported, preset: .transcription)
            let analyzer = SpeechAnalyzer(modules: [transcriber])
            // The per-locale model may not be installed yet. First launch on
            // a fresh device pays one download; every device after that is a
            // no-op check. Nothing here ships audio — assets only.
            if let install = try? await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
                try? await install.downloadAndInstall()
            }
            // Apple publishes no format for the model; ask it. The fallback
            // is the format the whole app speaks — 16 kHz mono — which the
            // module's own compatibility check can still reconfigure for.
            let fallback = AVAudioFormat(standardFormatWithSampleRate: 16_000, channels: 1)
            let format = (try? await SpeechAnalyzer.bestAvailableAudioFormat(compatibleWith: [transcriber])) ?? fallback
            guard let format else {
                await MainActor.run { self.onError?() }
                return
            }
            self.warmUp(analyzer: analyzer, transcriber: transcriber, stream: self.makeStream(), format: format)
        }
    }

    private func makeStream() -> AsyncStream<AnalyzerInput> {
        var continuation: AsyncStream<AnalyzerInput>.Continuation!
        let stream = AsyncStream<AnalyzerInput> { continuation = $0 }
        builder = continuation
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
        }
        Task { [weak self] in
            do {
                try await analyzer.start(inputSequence: stream)
            } catch {
                await MainActor.run { self?.onError?() }
            }
        }
        Task { [weak self] in
            do {
                for try await result in transcriber.results {
                    let text = String(result.text.characters)
                    guard !text.isEmpty else { continue }
                    let isFinal = result.isFinal
                    await MainActor.run { self?.onResult?(text, isFinal) }
                }
            } catch is CancellationError {
            } catch {
                // The session finished under us (resource limits, a finished
                // analyzer). The listener's error path is swap-with-flush —
                // the same recovery the legacy recognizer gets.
                await MainActor.run { self?.onError?() }
            }
        }
    }

    func append(_ buffer: AVAudioPCMBuffer) {
        queue.async { [weak self] in
            guard let self, !self.finished else { return }
            if self.targetFormat != nil {
                self.convertAndYield(buffer)
            } else if self.held.count < 600 {
                // Warm-up hold, bounded the same way the mic tap's orphan
                // buffer is: a counter, dropped past the cap, reported by
                // whoever reads the gap markers.
                self.held.append(buffer)
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
            self.builder?.finish()
            guard let analyzer = self.analyzer else { return }
            Task {
                // The documented trap, handled: without this call the tail of
                // the transcript never emits and the last words of every
                // request die in the model's pipeline.
                try? await analyzer.finalizeAndFinishThroughEndOfInput()
            }
        }
    }

    deinit {
        builder?.finish()
    }
}
