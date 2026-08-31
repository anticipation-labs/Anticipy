import AVFoundation
import CoreMedia
import Foundation
import Speech

/// One on-device transcription lane. A meeting owns two instances: microphone
/// and system audio. Each lane has its own analyzer and clock so overlapping
/// speakers cannot overwrite one another's hypotheses.
@available(macOS 26.0, *)
final class MacSpeechPipeline: @unchecked Sendable {
    var onResult: (@MainActor @Sendable (_ text: String, _ isFinal: Bool) -> Void)?
    var onError: (@MainActor @Sendable () -> Void)?

    private let desiredLocale: Locale
    private let queue: DispatchQueue
    private var transcriber: SpeechTranscriber?
    private var analyzer: SpeechAnalyzer?
    private var builder: AsyncStream<AnalyzerInput>.Continuation?
    private var audioConverter: AVAudioConverter?
    private var converterSourceFormat: AVAudioFormat?
    private var targetFormat: AVAudioFormat?
    private var held: [AVAudioPCMBuffer] = []
    private var clockSeconds: Double = 0
    private var finished = false
    private var resultTask: Task<Void, Never>?
    private var analyzerTask: Task<Void, Never>?

    init(label: String, locale: Locale = Locale(identifier: "en_US")) {
        desiredLocale = locale
        queue = DispatchQueue(label: "ai.anticipy.mac.speech.\(label)")
    }

    func begin() {
        let desired = desiredLocale
        Task { [weak self] in
            guard let self,
                  SpeechTranscriber.isAvailable,
                  let supported = await SpeechTranscriber.supportedLocale(equivalentTo: desired)
            else {
                await self?.reportError()
                return
            }

            let transcriber = SpeechTranscriber(locale: supported, preset: .transcription)
            let analyzer = SpeechAnalyzer(modules: [transcriber])
            if let install = try? await AssetInventory.assetInstallationRequest(supporting: [transcriber]) {
                try? await install.downloadAndInstall()
            }
            let fallback = AVAudioFormat(standardFormatWithSampleRate: 16_000, channels: 1)
            guard let format = (await SpeechAnalyzer.bestAvailableAudioFormat(
                compatibleWith: [transcriber])) ?? fallback else {
                await reportError()
                return
            }

            var continuation: AsyncStream<AnalyzerInput>.Continuation!
            let stream = AsyncStream<AnalyzerInput> { continuation = $0 }
            queue.async { [weak self] in
                guard let self, !self.finished else {
                    continuation.finish()
                    return
                }
                self.transcriber = transcriber
                self.analyzer = analyzer
                self.builder = continuation
                self.targetFormat = format
                let replay = self.held
                self.held.removeAll(keepingCapacity: false)
                for buffer in replay { self.convertAndYield(buffer) }
            }

            analyzerTask = Task { [weak self] in
                do {
                    try await analyzer.start(inputSequence: stream)
                } catch is CancellationError {
                } catch {
                    await self?.reportError()
                }
            }
            resultTask = Task { [weak self] in
                do {
                    for try await result in transcriber.results {
                        let text = String(result.text.characters)
                            .trimmingCharacters(in: .whitespacesAndNewlines)
                        guard !text.isEmpty else { continue }
                        let isFinal = result.isFinal
                        if let callback = self?.onResult {
                            await callback(text, isFinal)
                        }
                    }
                } catch is CancellationError {
                } catch {
                    await self?.reportError()
                }
            }
        }
    }

    func append(_ buffer: AVAudioPCMBuffer) {
        queue.async { [weak self] in
            guard let self, !self.finished else { return }
            if self.targetFormat != nil {
                self.convertAndYield(buffer)
            } else if self.held.count < 600 {
                self.held.append(buffer)
            }
        }
    }

    /// Finalizes the analyzer so its last stable phrase is emitted before the
    /// result stream closes. The callback fires after the analyzer has had the
    /// chance to deliver that tail.
    func finish(onFinished: @escaping @MainActor @Sendable () -> Void) {
        queue.async { [weak self] in
            guard let self, !self.finished else {
                Task { @MainActor in onFinished() }
                return
            }
            self.finished = true
            let analyzer = self.analyzer
            self.builder?.finish()
            Task { [weak self] in
                if let analyzer { try? await analyzer.finalizeAndFinishThroughEndOfInput() }
                try? await Task.sleep(for: .milliseconds(150))
                self?.analyzerTask?.cancel()
                self?.resultTask?.cancel()
                await MainActor.run { onFinished() }
            }
        }
    }

    private func convertAndYield(_ buffer: AVAudioPCMBuffer) {
        guard let builder else { return }
        let target = targetFormat ?? buffer.format
        let converted: AVAudioPCMBuffer?
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

        if let converted, converted.frameLength > 0 {
            let start = CMTime(seconds: clockSeconds, preferredTimescale: 16_000)
            builder.yield(AnalyzerInput(buffer: converted, bufferStartTime: start))
        }
        clockSeconds += Double(buffer.frameLength) / buffer.format.sampleRate
    }

    private func reportError() async {
        await MainActor.run { onError?() }
    }

    deinit {
        builder?.finish()
        analyzerTask?.cancel()
        resultTask?.cancel()
    }
}

extension AVAudioPCMBuffer {
    /// Audio callbacks reuse their buffers as soon as they return. The archive
    /// and transcriber work asynchronously, so they receive owned bytes.
    func anticipyCopy() -> AVAudioPCMBuffer? {
        guard let copy = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frameLength) else { return nil }
        copy.frameLength = frameLength
        let source = UnsafeMutableAudioBufferListPointer(mutableAudioBufferList)
        let destination = UnsafeMutableAudioBufferListPointer(copy.mutableAudioBufferList)
        guard source.count == destination.count else { return nil }
        for index in source.indices {
            guard let src = source[index].mData, let dst = destination[index].mData else { continue }
            let byteCount = min(Int(source[index].mDataByteSize),
                                Int(destination[index].mDataByteSize))
            memcpy(dst, src, byteCount)
            destination[index].mDataByteSize = UInt32(byteCount)
        }
        return copy
    }
}
