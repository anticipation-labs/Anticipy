import Foundation

/// Streams pendant audio to Deepgram's realtime STT over a websocket and emits
/// finalized transcript lines. Deepgram accepts raw Opus frames when told the
/// encoding, so we forward the pendant's frames without decoding on-phone.
/// (Cloud STT for the MVP; local models come later, per the Anticipy plan.)
final class TranscriberClient: NSObject {
    private var task: URLSessionWebSocketTask?
    var onTranscript: ((String) -> Void)?

    func connect(apiKey: String) {
        var request = URLRequest(url: URL(string:
            "wss://api.deepgram.com/v1/listen?encoding=opus&sample_rate=16000&channels=1&punctuate=true&interim_results=false")!)
        request.setValue("Token \(apiKey)", forHTTPHeaderField: "Authorization")
        let session = URLSession(configuration: .default)
        task = session.webSocketTask(with: request)
        task?.resume()
        receiveLoop()
    }

    func send(opusFrame: Data) {
        task?.send(.data(opusFrame)) { _ in }
    }

    private func receiveLoop() {
        task?.receive { [weak self] result in
            guard let self else { return }
            if case let .success(message) = result {
                if case let .string(text) = message,
                   let data = text.data(using: .utf8),
                   let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let channel = obj["channel"] as? [String: Any],
                   let alternatives = channel["alternatives"] as? [[String: Any]],
                   let transcript = alternatives.first?["transcript"] as? String,
                   !transcript.isEmpty {
                    DispatchQueue.main.async { self.onTranscript?(transcript) }
                }
                self.receiveLoop()
            }
        }
    }

    func disconnect() {
        task?.cancel(with: .normalClosure, reason: nil)
    }
}
