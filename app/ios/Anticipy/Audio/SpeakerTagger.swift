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

    let roster: VoiceRoster
    private let makeEmbedder: () -> VoiceEmbedder?
    private let modelIsAvailable: Bool

    init(roster: VoiceRoster = VoiceRoster(),
         modelAvailable: Bool = VoiceEmbedderFactory.modelAvailable,
         makeEmbedder: @escaping () -> VoiceEmbedder? = VoiceEmbedderFactory.make) {
        self.roster = roster
        self.modelIsAvailable = modelAvailable
        self.makeEmbedder = makeEmbedder
    }

    private var ring: [Float] = []
    private var consumedUpTo = 0          // ring index already tagged
    private let lock = NSLock()
    private var converter: AVAudioConverter?
    private var converterInputFormat: AVAudioFormat?

    private let embeddingQueue = DispatchQueue(label: "ai.anticipy.speaker-work", qos: .userInitiated)
    // Read and used only on embeddingQueue. Loading ONNX is work too.
    private lazy var embedder: VoiceEmbedder? = makeEmbedder()
    private var deliveryGeneration = 0

    /// Account changes invalidate queued voice results before they can learn
    /// a voice or deliver an old account's words into the new account.
    func invalidatePendingDeliveries() {
        deliveryGeneration &+= 1
        _ = drainWindow()
    }

    /// Can this phone actually judge a voice right now?
    var available: Bool { modelIsAvailable }
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
    func tagForLatestUtterance(completion: @escaping (String?) -> Void) {
        let generation = deliveryGeneration
        // Snapshot now, before the next utterance changes the audio window.
        lock.lock()
        let start = min(consumedUpTo, ring.count)
        let slice = Array(ring[start...].suffix(Int(Self.sampleRate * maxSeconds)))
        consumedUpTo = ring.count
        lock.unlock()
        // A serial queue preserves utterance order even when inference is slow.
        embeddingQueue.async { [weak self] in
            guard let self else { return }
            let vec = Double(slice.count) / Self.sampleRate >= self.minSeconds
                ? self.embedder?.embed(slice) : nil
            DispatchQueue.main.async { [weak self] in
                guard let self, generation == self.deliveryGeneration else { return }
                guard let vec, !vec.isEmpty else { completion(nil); return }
                let verdict = self.roster.identify(vec)
                completion(verdict.tag == "unknown" ? nil : verdict.tag)
            }
        }
    }

    /// Enrollment uses the same serialized model work, never the UI thread.
    func enrollOwner(from samples: [Float], completion: @escaping (Bool) -> Void) {
        let generation = deliveryGeneration
        embeddingQueue.async { [weak self] in
            guard let self else { return }
            let vec = self.embedder?.embed(samples)
            DispatchQueue.main.async { [weak self] in
                guard let self, generation == self.deliveryGeneration else { return }
                guard let vec, !vec.isEmpty else { completion(false); return }
                self.roster.enrollOwner(vec)
                completion(true)
            }
        }
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

    static var modelAvailable: Bool {
        #if canImport(SherpaOnnx)
        return Bundle.main.path(forResource: modelName, ofType: "onnx") != nil
        #else
        return false
        #endif
    }

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
