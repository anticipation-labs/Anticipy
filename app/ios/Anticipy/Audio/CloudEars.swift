import AVFoundation
import Foundation

/// The main ears: phone-mic audio streamed to Deepgram's realtime STT, the
/// same engine class the transcription products people trust actually use.
/// Apple's on-device recognizer stays as the offline fallback — it dies
/// quietly mid-conversation (whole minutes of speech producing nothing,
/// seen live on build 51, 2026-08-12), so it is no longer trusted as the
/// only ear.
///
/// The key comes from the backend (`/ears/key`), never ships in the binary.
/// No key configured server-side = this class stays dormant and the app
/// behaves exactly as before.
final class CloudEars: NSObject {
    /// A finished utterance, ready for the brain.
    var onLine: ((String) -> Void)?
    /// Ears telemetry: connection opened/closed/failed, utterances emitted.
    /// Everything here also lands in the events table so a silent failure
    /// is never unexplainable again.
    var onDiag: ((String) -> Void)?

    /// True while the socket is delivering: the arbiter in PhoneListener
    /// lets Apple's lines through only when this is false.
    var healthy: Bool {
        connected && Date().timeIntervalSince(lastMessageAt) < 10
    }

    private var task: URLSessionWebSocketTask?
    private var session: URLSession?
    private var apiKey = ""
    private var connected = false
    private var lastMessageAt = Date.distantPast
    private var lastAudioSentAt = Date.distantPast
    private var keepAlive: Timer?
    private var reconnectDelay: TimeInterval = 1
    private var wantConnected = false

    /// Pieces of the current utterance: Deepgram finalizes speech in chunks
    /// (`is_final`) and marks the end of the whole utterance separately
    /// (`speech_final`). Joining the chunks is what makes one spoken thought
    /// arrive as one line.
    private var utterance: [String] = []

    private var converter: AVAudioConverter?
    private var converterSourceFormat: AVAudioFormat?
    private let targetFormat = AVAudioFormat(
        commonFormat: .pcmFormatInt16, sampleRate: 16000,
        channels: 1, interleaved: true)!

    func start(apiKey: String) {
        guard !apiKey.isEmpty else { return }
        self.apiKey = apiKey
        wantConnected = true
        open()
    }

    func stop() {
        wantConnected = false
        keepAlive?.invalidate()
        keepAlive = nil
        task?.cancel(with: .normalClosure, reason: nil)
        task = nil
        connected = false
        utterance = []
    }

    private func open() {
        guard wantConnected, !apiKey.isEmpty else { return }
        var request = URLRequest(url: URL(string:
            "wss://api.deepgram.com/v1/listen"
            + "?encoding=linear16&sample_rate=16000&channels=1"
            + "&model=nova-3&smart_format=true&interim_results=true"
            + "&endpointing=600&utterance_end_ms=1200&punctuate=true")!)
        request.setValue("Token \(apiKey)", forHTTPHeaderField: "Authorization")
        let s = URLSession(configuration: .default)
        session = s
        let t = s.webSocketTask(with: request)
        task = t
        t.resume()
        connected = true
        lastMessageAt = Date()
        onDiag?("cloud ears: connecting")
        receiveLoop(t)
        startKeepAlive()
    }

    private func startKeepAlive() {
        keepAlive?.invalidate()
        let timer = Timer(timeInterval: 5, repeats: true) { [weak self] _ in
            guard let self, self.connected else { return }
            // Deepgram closes an idle socket after ~10s of no audio; the
            // KeepAlive message holds it open through silence.
            if Date().timeIntervalSince(self.lastAudioSentAt) > 4 {
                self.task?.send(.string(#"{"type":"KeepAlive"}"#)) { _ in }
            }
        }
        RunLoop.main.add(timer, forMode: .common)
        keepAlive = timer
    }

    /// Mic audio, any format iOS hands us. Converted to 16 kHz mono Int16 and
    /// streamed. Called on the audio tap thread; conversion is cheap.
    func accept(_ buffer: AVAudioPCMBuffer) {
        guard connected, let task else { return }
        guard let data = convert(buffer) else { return }
        lastAudioSentAt = Date()
        task.send(.data(data)) { _ in }
    }

    private func convert(_ buffer: AVAudioPCMBuffer) -> Data? {
        let src = buffer.format
        if converter == nil || converterSourceFormat != src {
            converter = AVAudioConverter(from: src, to: targetFormat)
            converterSourceFormat = src
        }
        guard let converter else { return nil }
        let ratio = targetFormat.sampleRate / src.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 32
        guard let out = AVAudioPCMBuffer(pcmFormat: targetFormat,
                                         frameCapacity: capacity) else { return nil }
        var fed = false
        var convErr: NSError?
        converter.convert(to: out, error: &convErr) { _, status in
            if fed {
                status.pointee = .noDataNow
                return nil
            }
            fed = true
            status.pointee = .haveData
            return buffer
        }
        guard convErr == nil, out.frameLength > 0,
              let ch = out.int16ChannelData else { return nil }
        return Data(bytes: ch[0], count: Int(out.frameLength) * 2)
    }

    private func receiveLoop(_ t: URLSessionWebSocketTask) {
        t.receive { [weak self] result in
            guard let self, self.task === t else { return }
            switch result {
            case let .success(message):
                self.lastMessageAt = Date()
                if case let .string(text) = message { self.handle(text) }
                self.receiveLoop(t)
            case .failure:
                self.connected = false
                self.onDiag?("cloud ears: socket dropped, reconnecting")
                self.flushUtterance()
                self.retry()
            }
        }
    }

    private func retry() {
        guard wantConnected else { return }
        let delay = reconnectDelay
        reconnectDelay = min(reconnectDelay * 2, 15)
        DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
            guard let self, self.wantConnected else { return }
            self.open()
        }
    }

    private func handle(_ text: String) {
        guard let data = text.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data)
                as? [String: Any] else { return }
        reconnectDelay = 1
        if obj["type"] as? String == "UtteranceEnd" {
            // Silence closed the utterance without a speech_final (happens
            // when the endpointer misses the boundary). Say what we have.
            flushUtterance()
            return
        }
        guard let channel = obj["channel"] as? [String: Any],
              let alternatives = channel["alternatives"] as? [[String: Any]],
              let transcript = alternatives.first?["transcript"] as? String
        else { return }
        let isFinal = obj["is_final"] as? Bool ?? false
        let speechFinal = obj["speech_final"] as? Bool ?? false
        guard isFinal else { return }
        if !transcript.isEmpty { utterance.append(transcript) }
        if speechFinal { flushUtterance() }
    }

    private func flushUtterance() {
        let line = utterance.joined(separator: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        utterance = []
        guard !line.isEmpty else { return }
        DispatchQueue.main.async { self.onLine?(line) }
    }
}
