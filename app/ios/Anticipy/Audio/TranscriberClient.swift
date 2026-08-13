import Foundation

/// Streams pendant audio to Deepgram's realtime STT over a websocket and emits
/// finalized transcript lines. Deepgram accepts raw Opus frames when told the
/// encoding, so we forward the pendant's frames without decoding on-phone.
/// (Cloud STT for the MVP; local models come later, per the Anticipy plan.)
final class TranscriberClient: NSObject, URLSessionWebSocketDelegate {
    private let stateQueue = DispatchQueue(label: "ai.anticipy.transcriber")
    private var task: URLSessionWebSocketTask?
    private var session: URLSession?
    private var keepAlive: DispatchSourceTimer?
    private var closingIntentionally = false
    private var outgoing = BoundedOpusQueue()
    private var sendInFlight = false

    var onTranscript: ((String) -> Void)?
    var onConnection: ((Bool) -> Void)?
    var onNeedsReconnect: (() -> Void)?

    func connect(accessToken: String) {
        guard !accessToken.isEmpty else { return }
        stateQueue.async { [weak self] in
            guard let self else { return }
            self.disconnectLocked(reconnect: false)
            self.closingIntentionally = false
            var request = URLRequest(url: URL(string:
                "wss://api.deepgram.com/v1/listen?encoding=opus&sample_rate=16000&channels=1&punctuate=true&smart_format=true&interim_results=false&endpointing=500")!)
            request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
            let newSession = URLSession(configuration: .default, delegate: self,
                                        delegateQueue: nil)
            let socket = newSession.webSocketTask(with: request)
            self.session = newSession
            self.task = socket
            socket.resume()
            self.receiveLoop(socket)
        }
    }

    func send(opusFrame: Data) {
        guard !opusFrame.isEmpty else { return }
        stateQueue.async { [weak self] in
            guard let self, self.task != nil else { return }
            self.outgoing.enqueue(opusFrame)
            self.pumpLocked()
        }
    }

    private func pumpLocked() {
        guard !sendInFlight,
              let socket = task,
              let frame = outgoing.dequeue() else { return }
        sendInFlight = true
        socket.send(.data(frame)) { [weak self, weak socket] error in
            guard let self, let socket else { return }
            self.stateQueue.async {
                guard self.task === socket else { return }
                self.sendInFlight = false
                if error != nil {
                    self.closedLocked(socket, shouldReconnect: true)
                } else {
                    self.pumpLocked()
                }
            }
        }
    }

    private func receiveLoop(_ socket: URLSessionWebSocketTask) {
        socket.receive { [weak self, weak socket] result in
            guard let self, let socket else { return }
            self.stateQueue.async {
                guard self.task === socket else { return }
                if case let .success(message) = result {
                    self.handleLocked(message)
                    self.receiveLoop(socket)
                } else {
                    self.closedLocked(socket, shouldReconnect: true)
                }
            }
        }
    }

    private func handleLocked(_ message: URLSessionWebSocketTask.Message) {
        guard case let .string(text) = message,
              let data = text.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              (obj["is_final"] as? Bool ?? true),
              let channel = obj["channel"] as? [String: Any],
              let alternatives = channel["alternatives"] as? [[String: Any]],
              let transcript = alternatives.first?["transcript"] as? String else { return }
        let clean = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return }
        DispatchQueue.main.async { [weak self] in self?.onTranscript?(clean) }
    }

    func disconnect(reconnect: Bool = false) {
        stateQueue.async { [weak self] in self?.disconnectLocked(reconnect: reconnect) }
    }

    private func disconnectLocked(reconnect: Bool) {
        closingIntentionally = !reconnect
        let socket = task
        task = nil
        sendInFlight = false
        outgoing.clear()
        stopKeepAliveLocked()
        socket?.cancel(with: .normalClosure, reason: nil)
        session?.invalidateAndCancel()
        session = nil
        DispatchQueue.main.async { [weak self] in self?.onConnection?(false) }
    }

    private func startKeepAliveLocked(_ socket: URLSessionWebSocketTask) {
        stopKeepAliveLocked()
        let timer = DispatchSource.makeTimerSource(queue: stateQueue)
        timer.schedule(deadline: .now() + 8, repeating: 8)
        timer.setEventHandler { [weak self, weak socket] in
            guard let self, let socket, self.task === socket else { return }
            socket.send(.string("{\"type\":\"KeepAlive\"}")) { error in
                guard error != nil else { return }
                self.stateQueue.async {
                    guard self.task === socket else { return }
                    self.closedLocked(socket, shouldReconnect: true)
                }
            }
        }
        keepAlive = timer
        timer.resume()
    }

    private func stopKeepAliveLocked() {
        keepAlive?.cancel()
        keepAlive = nil
    }

    private func closedLocked(_ socket: URLSessionWebSocketTask,
                              shouldReconnect: Bool) {
        guard task === socket else { return }
        task = nil
        sendInFlight = false
        outgoing.clear()
        stopKeepAliveLocked()
        session?.invalidateAndCancel()
        session = nil
        let reconnect = shouldReconnect && !closingIntentionally
        DispatchQueue.main.async { [weak self] in
            self?.onConnection?(false)
            if reconnect { self?.onNeedsReconnect?() }
        }
    }

    func urlSession(_ session: URLSession,
                    webSocketTask: URLSessionWebSocketTask,
                    didOpenWithProtocol protocol: String?) {
        stateQueue.async { [weak self, weak webSocketTask] in
            guard let self, let webSocketTask, self.task === webSocketTask else { return }
            self.startKeepAliveLocked(webSocketTask)
            self.pumpLocked()
            DispatchQueue.main.async { [weak self] in self?.onConnection?(true) }
        }
    }

    func urlSession(_ session: URLSession,
                    webSocketTask: URLSessionWebSocketTask,
                    didCloseWith closeCode: URLSessionWebSocketTask.CloseCode,
                    reason: Data?) {
        stateQueue.async { [weak self, weak webSocketTask] in
            guard let self, let webSocketTask else { return }
            self.closedLocked(webSocketTask, shouldReconnect: true)
        }
    }
}
