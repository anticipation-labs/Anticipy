import AVFoundation
import Foundation

#if canImport(SherpaOnnx)
import SherpaOnnx
#endif

/// Turns the last few seconds of microphone audio into ONE word about who
/// was speaking — on this phone, with nothing leaving it.
///
/// Wiring: the mic tap hands every buffer to `accept(_:)`, which keeps a
/// short rolling window of 16 kHz mono audio. When the recognizer finishes
/// a line, `tagForLatestUtterance()` embeds the audio behind that line and
/// asks the roster who it was. The answer — "owner", "other:v2",
/// "other:Sarah", or nothing at all — rides along with the transcript.
///
/// The audio itself is never written to disk and never uploaded. The window
/// is a ring buffer that overwrites itself continuously.
///
/// Compiles with or without the speaker model package present: without it,
/// `available` is false, every tag is nil, and the app behaves exactly as
/// it did before speaker recognition existed. That is deliberate — the
/// brain treats a missing verdict as no verdict, so a phone that cannot
/// tag is never a phone that misbehaves.
final class SpeakerTagger {

    static let sampleRate: Double = 16_000
    /// Enough to cover a long sentence; anything older is not this line.
    private let windowSeconds: Double = 20
    /// Below this there is not enough voice to judge anyone honestly.
    private let minSeconds: Double = 1.2
    /// A very long "utterance" is usually several people; judge the tail.
    private let maxSeconds: Double = 8

    let roster = VoiceRoster()

    private var ring: [Float] = []
    private var consumedUpTo = 0          // ring index already tagged
    private let lock = NSLock()
    private var converter: AVAudioConverter?
    private var converterInputFormat: AVAudioFormat?

    private lazy var embedder: VoiceEmbedder? = VoiceEmbedderFactory.make()

    /// Can this phone actually judge a voice right now?
    var available: Bool { embedder != nil }
    var hasOwnerProfile: Bool { roster.hasOwnerProfile }

    // MARK: - audio in (called from the audio thread — keep it cheap)

    func accept(_ buffer: AVAudioPCMBuffer) {
        guard available else { return }
        guard let mono = downmix(buffer) else { return }
        lock.lock()
        ring.append(contentsOf: mono)
        let cap = Int(Self.sampleRate * windowSeconds)
        if ring.count > cap {
            let drop = ring.count - cap
            ring.removeFirst(drop)
            consumedUpTo = max(0, consumedUpTo - drop)
        }
        lock.unlock()
    }

    /// Device format (usually 48 kHz, sometimes stereo) -> 16 kHz mono Float32.
    private func downmix(_ buffer: AVAudioPCMBuffer) -> [Float]? {
        guard let target = AVAudioFormat(commonFormat: .pcmFormatFloat32,
                                         sampleRate: Self.sampleRate,
                                         channels: 1, interleaved: false)
        else { return nil }
        if converter == nil || converterInputFormat != buffer.format {
            converter = AVAudioConverter(from: buffer.format, to: target)
            converterInputFormat = buffer.format
        }
        guard let converter else { return nil }
        let ratio = target.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 64
        guard let out = AVAudioPCMBuffer(pcmFormat: target,
                                         frameCapacity: capacity)
        else { return nil }
        var fed = false
        var err: NSError?
        converter.convert(to: out, error: &err) { _, status in
            if fed { status.pointee = .noDataNow; return nil }
            fed = true
            status.pointee = .haveData
            return buffer
        }
        guard err == nil, out.frameLength > 0,
              let ch = out.floatChannelData?[0] else { return nil }
        return Array(UnsafeBufferPointer(start: ch, count: Int(out.frameLength)))
    }

    // MARK: - the verdict

    /// Who spoke the line that just finished? nil when the phone cannot say.
    func tagForLatestUtterance() -> String? {
        guard let embedder else { return nil }
        lock.lock()
        let start = min(consumedUpTo, ring.count)
        var slice = Array(ring[start...])
        consumedUpTo = ring.count
        lock.unlock()

        let maxSamples = Int(Self.sampleRate * maxSeconds)
        if slice.count > maxSamples { slice = Array(slice.suffix(maxSamples)) }
        guard Double(slice.count) / Self.sampleRate >= minSeconds else { return nil }
        guard let vec = embedder.embed(slice), !vec.isEmpty else { return nil }

        let verdict = roster.identify(vec)
        // "unknown" is a real answer — it means DO NOT claim anyone — and
        // the brain reads a missing field the same way, so send nothing.
        return verdict.tag == "unknown" ? nil : verdict.tag
    }

    /// Enrollment: embed a held recording of his voice and store the profile.
    @discardableResult
    func enrollOwner(from samples: [Float]) -> Bool {
        guard let embedder, let vec = embedder.embed(samples), !vec.isEmpty
        else { return false }
        roster.enrollOwner(vec)
        return true
    }

    /// Take everything currently in the window (used by the enrollment
    /// screen, which records deliberately rather than ambiently).
    func drainWindow() -> [Float] {
        lock.lock(); defer { lock.unlock() }
        let all = ring
        ring.removeAll(keepingCapacity: true)
        consumedUpTo = 0
        return all
    }

    func resetUtterance() {
        lock.lock(); consumedUpTo = ring.count; lock.unlock()
    }
}

// MARK: - the embedder, present or not

protocol VoiceEmbedder {
    /// 16 kHz mono float samples -> a voiceprint, or nil if it cannot.
    func embed(_ samples: [Float]) -> [Float]?
}

enum VoiceEmbedderFactory {
    /// The model lives in the app bundle. Named exactly so a future model
    /// swap is a file swap (see design/briefs/09 for the benchmark rules).
    static let modelName = "speaker-embedding"

    static func make() -> VoiceEmbedder? {
        #if canImport(SherpaOnnx)
        guard let path = Bundle.main.path(forResource: modelName,
                                          ofType: "onnx") else { return nil }
        return SherpaVoiceEmbedder(modelPath: path)
        #else
        return nil
        #endif
    }
}

#if canImport(SherpaOnnx)
/// Real on-device extraction. Everything here is CPU-local; the library
/// makes no network calls and the model file ships inside the app.
final class SherpaVoiceEmbedder: VoiceEmbedder {
    private let extractor: SherpaOnnxSpeakerEmbeddingExtractorWrapper

    init?(modelPath: String) {
        var config = sherpaOnnxSpeakerEmbeddingExtractorConfig(
            model: modelPath, numThreads: 1, debug: 0, provider: "cpu")
        extractor = SherpaOnnxSpeakerEmbeddingExtractorWrapper(config: &config)
    }

    func embed(_ samples: [Float]) -> [Float]? {
        let stream = extractor.createStream()
        stream.acceptWaveform(samples: samples,
                              sampleRate: Int(SpeakerTagger.sampleRate))
        stream.inputFinished()
        guard extractor.isReady(stream: stream) else { return nil }
        return extractor.compute(stream: stream)
    }
}
#endif
