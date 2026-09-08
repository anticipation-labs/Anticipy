import Foundation

final class DeliveryServer: URLProtocol {
    static var handler: ((URLRequest, @escaping (Int, Data?, Error?) -> Void) -> Void)!
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.handler(request) { status, data, error in
            if let error { self.client?.urlProtocol(self, didFailWithError: error); return }
            self.client?.urlProtocol(self, didReceive: HTTPURLResponse(url: self.request.url!, statusCode: status,
                httpVersion: nil, headerFields: ["Content-Type": "application/json"])!, cacheStoragePolicy: .notAllowed)
            self.client?.urlProtocol(self, didLoad: data ?? Data())
            self.client?.urlProtocolDidFinishLoading(self)
        }
    }
    override func stopLoading() {}
}

final class ServerState: @unchecked Sendable {
    let lock = NSLock()
    var records: [String: [String: String]] = [:]
    var posts: [[String: String]] = []
    var failNext = false
    var dropNextResponse = false
    var corruptResponse = false
    var held: ((Int, Data?, Error?) -> Void)?
    var holdNext = false
    func count() -> Int { lock.lock(); defer { lock.unlock() }; return posts.count }
    func handle(_ request: URLRequest, finish: @escaping (Int, Data?, Error?) -> Void) {
        lock.lock(); defer { lock.unlock() }
        var bytes = request.httpBody ?? Data()
        if let stream = request.httpBodyStream {
            stream.open(); defer { stream.close() }
            var buffer = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable {
                let n = stream.read(&buffer, maxLength: buffer.count)
                if n <= 0 { break }; bytes.append(buffer, count: n)
            }
        }
        if request.url!.path.hasSuffix("auth-with-password") {
            let body = try! JSONSerialization.jsonObject(with: bytes) as! [String: String]
            let owner = body["identity"]!
            finish(200, try! JSONSerialization.data(withJSONObject: ["token": "token-" + owner,
                "record": ["id": owner, "email": owner + "@example.invalid"]]), nil)
            return
        }
        if request.httpMethod == "GET" {
            let stored = records[request.url!.lastPathComponent]
            finish(stored == nil ? 404 : 200, stored.map { try! JSONSerialization.data(withJSONObject: $0) }, nil)
            return
        }
        let body = try! JSONSerialization.jsonObject(with: bytes) as! [String: String]
        precondition(request.value(forHTTPHeaderField: "Authorization") == "token-" + body["owner_ref"]!,
                     "an account's capture was sent with another account's token")
        posts.append(body)
        if holdNext { holdNext = false; held = finish; return }
        if failNext { failNext = false; finish(0, nil, URLError(.notConnectedToInternet)); return }
        let id = body["id"]!
        if records[id] != nil { finish(400, Data("{}".utf8), nil); return }
        if corruptResponse { finish(200, Data("{}".utf8), nil); return }
        records[id] = body
        if dropNextResponse { dropNextResponse = false; finish(0, nil, URLError(.networkConnectionLost)); return }
        finish(200, try! JSONSerialization.data(withJSONObject: body), nil)
    }
}

@main struct BackendDeliveryTests {
    @MainActor static func wait(_ label: String, _ condition: () -> Bool) async {
        let end = Date().addingTimeInterval(4)
        while !condition(), Date() < end { try? await Task.sleep(nanoseconds: 10_000_000) }
        precondition(condition(), label)
    }
    @MainActor static func main() async throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [DeliveryServer.self]
        let session = URLSession(configuration: config)
        let server = ServerState()
        DeliveryServer.handler = server.handle
        let queue = dir.appendingPathComponent("queue.jsonl")
        let backend = MacBackend(baseURL: URL(string: "https://delivery.example.invalid")!, session: session,
                                 queueURL: queue, persistsSession: false, retryDelay: 0.04)
        try await backend.signIn(email: "owner-a", password: "fixture")
        func post(_ text: String) { backend.postTranscript(text: text, startedAt: Date(timeIntervalSince1970: 100),
                                                          endedAt: Date(timeIntervalSince1970: 101), speaker: "owner") }
        server.failNext = true
        post("An offline final sentence.")
        await wait("last offline line must retry without new speech") { server.count() >= 2 && backend.pendingCount == 0 }
        precondition(server.records.count == 1)
        print("PASS: the final offline line retries automatically")

        server.dropNextResponse = true
        post("The response disappeared after commit.")
        await wait("uncertain delivery must be read back") { server.count() >= 4 && backend.pendingCount == 0 }
        precondition(server.records.count == 2 && server.posts[2]["id"] == server.posts[3]["id"])
        print("PASS: a lost response produces one stored capture with one stable ID")

        server.holdNext = true
        post("Keep the first line when the next arrives.")
        await wait("first request should be in flight") { server.count() == 5 }
        post("A second line arrived during network I/O.")
        let (first, held) = server.lock.withLock {
            let first = server.posts.last!; server.records[first["id"]!] = first
            let held = server.held!; server.held = nil
            return (first, held)
        }
        held(200, try JSONSerialization.data(withJSONObject: first), nil)
        await wait("concurrent append must survive") { server.count() == 6 && backend.pendingCount == 0 }
        print("PASS: a new transcript survives an in-flight queue drain")

        server.holdNext = true
        post("An old account's request will be refused.")
        await wait("old account request should be held") { server.count() == 7 }
        backend.signOut()
        try await backend.signIn(email: "owner-b", password: "fixture")
        let stale = server.lock.withLock { let held = server.held!; server.held = nil; return held }
        stale(403, nil, nil)
        post("Only owner B may receive this capture.")
        await wait("new account must keep its session") { server.count() == 8 && backend.pendingCount == 0 }
        precondition(backend.isSignedIn && backend.ownerId == "owner-b")
        let retainedA = try String(contentsOf: queue, encoding: .utf8)
        precondition(retainedA.contains("owner-a"))
        print("PASS: stale refusal cannot sign out a newer account or mix owners")

        server.holdNext = true
        post("The current token will be rejected.")
        await wait("current request should be held") { server.count() == 9 }
        let refusal = server.lock.withLock { let held = server.held!; server.held = nil; return held }
        refusal(401, nil, nil)
        await wait("current refusal must reopen sign-in") { !backend.isSignedIn }
        let retainedRefusal = try String(contentsOf: queue, encoding: .utf8)
        precondition(retainedRefusal.contains("current token"))
        print("PASS: current 401 signs out and retains the capture")

        let corruptQueue = dir.appendingPathComponent("corrupt.jsonl")
        try Data("not valid json\n".utf8).write(to: corruptQueue)
        let corrupt = MacBackend(session: session, queueURL: corruptQueue, persistsSession: false)
        try await corrupt.signIn(email: "owner-c", password: "fixture")
        corrupt.postTranscript(text: "Do not erase an unreadable queue.", startedAt: Date(), endedAt: Date(), speaker: "owner")
        let retainedCorrupt = try String(contentsOf: corruptQueue, encoding: .utf8)
        precondition(corrupt.syncError != nil && retainedCorrupt == "not valid json\n")
        corrupt.signOut()
        print("PASS: an unreadable queue is preserved with a visible error")

        let wrongQueue = dir.appendingPathComponent("wrong.jsonl")
        server.corruptResponse = true
        let wrong = MacBackend(session: session, queueURL: wrongQueue, persistsSession: false, retryDelay: 1)
        try await wrong.signIn(email: "owner-d", password: "fixture")
        wrong.postTranscript(text: "A bare 200 is not persistence proof.", startedAt: Date(), endedAt: Date(), speaker: "other")
        await wait("server response should arrive") { server.count() == 10 }
        try? await Task.sleep(nanoseconds: 30_000_000)
        precondition(wrong.pendingCount == 1)
        wrong.signOut()
        print("PASS: a success response without the stored capture cannot clear the queue")
        print("all 7 Mac backend delivery tests passed")
    }
}
