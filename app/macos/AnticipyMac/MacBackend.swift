import Foundation
import Combine
import Security

/// The Mac's mouth and its memory of who it is. Signs in the same way the
/// phone does (owners/auth-with-password), posts transcript events the same
/// way (TranscriptWire: kind, text, capture envelope, owner_ref, source
/// "mac"), and keeps unsent lines in a JSONL queue on disk so a dead network
/// delays a line rather than deleting it.
///
/// The backend is the Cloudflare Worker at api.anticipy.ai — the one the
/// phone posts to and the one the brain reads. Build 119 shipped pointed at
/// the retired Railway host that Worker replaced, so every meeting it
/// recorded reached a backend nothing was listening to.
///
/// A 401 or 403 on a push is not a delayed row. It is a token the server
/// will never accept — the session build 119 left in the Keychain is one —
/// and the honest answer is to drop the session so the sign-in door
/// reappears. The rows stay on disk under their owner and drain after the
/// next sign-in; nothing is deleted.
///
/// The auth token lives in the Keychain, not in UserDefaults — it is a
/// session credential for a person's whole life, and plists are readable by
/// anything running as the user.
@MainActor
final class MacBackend: ObservableObject {

    struct Credentials: Codable {
        let token: String
        let ownerId: String
        let email: String
        let expiry: Date?
    }

    private struct QueuedTranscript: Codable {
        let id: UUID
        let ownerId: String
        let text: String
        let startedAt: Date
        let endedAt: Date
        let speaker: String

        init(id: UUID = UUID(), ownerId: String, text: String,
             startedAt: Date, endedAt: Date, speaker: String) {
            self.id = id
            self.ownerId = ownerId
            self.text = text
            self.startedAt = startedAt
            self.endedAt = endedAt
            self.speaker = speaker
        }

        // Rows written by build 119 also carry a per-channel `source`; the
        // decoder ignores it, and the ear is stamped by the wire on the way
        // out. A queue on disk is somebody else's build's handwriting.
        private enum CodingKeys: String, CodingKey {
            case id, ownerId, text, startedAt, endedAt, speaker
        }

        init(from decoder: Decoder) throws {
            let values = try decoder.container(keyedBy: CodingKeys.self)
            id = try values.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
            ownerId = try values.decodeIfPresent(String.self, forKey: .ownerId) ?? ""
            text = try values.decode(String.self, forKey: .text)
            startedAt = try values.decode(Date.self, forKey: .startedAt)
            endedAt = try values.decode(Date.self, forKey: .endedAt)
            speaker = try values.decodeIfPresent(String.self, forKey: .speaker) ?? ""
        }
    }

    /// What one push came back as. Three states, because "the server said
    /// no" and "the server could not be reached" call for opposite things:
    /// the first must never be retried behind the same token, the second
    /// must never be dropped.
    private enum PushOutcome {
        case sent
        case refused
        case retryLater
    }

    static let shared = MacBackend()

    let baseURL: URL
    @Published private(set) var isSignedIn = false
    /// How many lines are on disk waiting for a 2xx. The sidebar reads it;
    /// it is the only thing the app can honestly say about sync, because a
    /// row leaves the queue on the server's answer and on nothing else.
    @Published private(set) var pendingCount = 0
    private(set) var authToken: String = ""
    private(set) var ownerId: String = ""
    private(set) var ownerEmail: String = ""

    private let keychainAccount = "ai.anticipy.mac.session"
    private let session: URLSession
    private let persistsSession: Bool
    private let retryDelay: TimeInterval
    private let queueURL: URL
    private var generation = UUID()
    private var draining = false
    private var retryTask: Task<Void, Never>?
    @Published private(set) var syncError: String?


    init(baseURL: URL = URL(string: "https://api.anticipy.ai")!,
         session: URLSession = .shared, queueURL: URL? = nil,
         persistsSession: Bool = true, retryDelay: TimeInterval = 5) {
        self.baseURL = baseURL
        self.session = session
        self.persistsSession = persistsSession
        self.retryDelay = retryDelay
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Anticipy", isDirectory: true)
        self.queueURL = queueURL ?? dir.appendingPathComponent("unsent.jsonl")
        try? FileManager.default.createDirectory(at: self.queueURL.deletingLastPathComponent(),
                                                 withIntermediateDirectories: true)
        if persistsSession { loadSession() }
        refreshPendingCount()
        drainQueue()
    }

    // ------------------------------------------------------------ identity

    private func loadSession() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: keychainAccount,
            kSecReturnData as String: true,
        ]
        var out: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &out)
        guard status == errSecSuccess,
              let data = out as? Data,
              let creds = try? JSONDecoder().decode(Credentials.self, from: data) else { return }
        authToken = creds.token
        ownerId = creds.ownerId
        ownerEmail = creds.email
        isSignedIn = true
    }

    private func saveSession(_ creds: Credentials) {
        if persistsSession {
        guard let data = try? JSONEncoder().encode(creds) else { return }
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: keychainAccount,
        ]
        SecItemDelete(query as CFDictionary)
        let add: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: keychainAccount,
            kSecValueData as String: data,
        ]
        SecItemAdd(add as CFDictionary, nil)
        }
        generation = UUID()
        authToken = creds.token
        ownerId = creds.ownerId
        ownerEmail = creds.email
        isSignedIn = true
        refreshPendingCount()
        drainQueue()
    }

    func signIn(email: String, password: String) async throws {
        generation = UUID()
        let attempt = generation
        struct AuthResponse: Decodable { let token: String; let record: OwnerRecord }
        struct OwnerRecord: Decodable { let id: String; let email: String }
        var req = URLRequest(url: baseURL.appendingPathComponent("api/collections/owners/auth-with-password"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: ["identity": email, "password": password])
        let (data, response) = try await session.data(for: req)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw URLError(.userAuthenticationRequired)
        }
        let auth = try JSONDecoder().decode(AuthResponse.self, from: data)
        guard generation == attempt else { throw CancellationError() }
        saveSession(Credentials(token: auth.token, ownerId: auth.record.id,
                                email: auth.record.email, expiry: nil))
    }

    func signOut() {
        generation = UUID()
        retryTask?.cancel()
        retryTask = nil
        if persistsSession {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: keychainAccount,
        ]
        SecItemDelete(query as CFDictionary)
        }
        authToken = ""
        ownerId = ""
        ownerEmail = ""
        isSignedIn = false
        refreshPendingCount()
    }

    // --------------------------------------------------------------- posts

    func postTranscript(text: String, startedAt: Date, endedAt: Date,
                        speaker: String) {
        guard isSignedIn, !text.isEmpty else { return }
        let row = QueuedTranscript(ownerId: ownerId, text: text,
                                   startedAt: startedAt, endedAt: endedAt, speaker: speaker)
        do {
            var rows = try readQueuedRows()
            rows.append(row)
            try writeQueuedRows(rows)
            drainQueue()
        } catch { reportStorageError() }
    }

    /// All session/queue state is owned by the main actor; network I/O yields
    /// it. A response from an old session cannot sign out a newer account.
    private func drainQueue() {
        guard isSignedIn, !draining else { return }
        retryTask?.cancel()
        retryTask = nil
        draining = true
        Task { [weak self] in await self?.drainQueueNow() }
    }

    private func drainQueueNow() async {
        let attempt = generation
        let token = authToken
        let owner = ownerId
        defer {
            draining = false
            refreshPendingCount()
            if isSignedIn, generation != attempt { drainQueue() }
            else if isSignedIn, pendingCount > 0 { scheduleRetry() }
        }
        do {
            // Persist legacy queue IDs before making any network request.
            try writeQueuedRows(readQueuedRows())
            while isSignedIn, generation == attempt,
                  let row = try readQueuedRows().first(where: { $0.ownerId == owner }) {
                let outcome = await send(row, token: token)
                guard generation == attempt else { return }
                switch outcome {
                case .sent:
                    // A new line may have arrived while this request yielded.
                    try writeQueuedRows(readQueuedRows().filter { $0.id != row.id })
                case .refused:
                    signOut()
                    return
                case .retryLater:
                    return // Preserve capture order and retry even if speech stops.
                }
            }
        } catch { reportStorageError() }
    }

    private func scheduleRetry() {
        retryTask?.cancel()
        let delay = retryDelay
        retryTask = Task { [weak self] in
            do { try await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000)) }
            catch { return }
            self?.drainQueue()
        }
    }

    private func send(_ row: QueuedTranscript, token: String) async -> PushOutcome {
        var body = TranscriptWire.body(text: row.text, speaker: row.speaker,
                                       startedAt: row.startedAt, endedAt: row.endedAt,
                                       ownerRef: row.ownerId, deviceID: deviceID())
        // A capture's identity survives response loss, restarts and upgrades.
        // The existing events primary key prevents a retry becoming new speech.
        let id = row.id.uuidString.lowercased().replacingOccurrences(of: "-", with: "")
        body["id"] = id
        var request = URLRequest(
            url: baseURL.appendingPathComponent("api/collections/events/records"),
            timeoutInterval: 20)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(token, forHTTPHeaderField: "Authorization")
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse else { return .retryLater }
            if http.statusCode == 401 || http.statusCode == 403 { return .refused }
            if (200...299).contains(http.statusCode), matchesCapture(data, body: body) { return .sent }
            // An earlier insert may have committed before its response was lost.
            // Only the exact owner-scoped capture is proof, never a bare 400/409.
            if http.statusCode == 400 || http.statusCode == 409 {
                request.url = request.url?.appendingPathComponent(id)
                request.httpMethod = "GET"
                request.httpBody = nil
                let (stored, readResponse) = try await session.data(for: request)
                if (readResponse as? HTTPURLResponse)?.statusCode == 200,
                   matchesCapture(stored, body: body) { return .sent }
            }
        } catch { /* The durable row remains queued. */ }
        return .retryLater
    }

    private func matchesCapture(_ data: Data, body: [String: String]) -> Bool {
        guard let stored = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else { return false }
        // decision/goal may already have been populated by the brain; device_id
        // can describe the earlier build that successfully inserted this row.
        return ["id", "owner_ref", "kind", "source", "text", "speaker",
                "capture_started_at", "spoken_at", "capture_ended_at"].allSatisfy {
            stored[$0] as? String == body[$0]
        }
    }

    private func readQueuedRows() throws -> [QueuedTranscript] {
        guard FileManager.default.fileExists(atPath: queueURL.path) else { return [] }
        let raw = try String(contentsOf: queueURL, encoding: .utf8)
        let decoder = JSONDecoder()
        return try raw.split(separator: "\n").map {
            try decoder.decode(QueuedTranscript.self, from: Data($0.utf8))
        }
    }

    private func writeQueuedRows(_ rows: [QueuedTranscript]) throws {
        let encoder = JSONEncoder()
        var data = Data()
        for row in rows {
            data.append(try encoder.encode(row))
            data.append(Data("\n".utf8))
        }
        try data.write(to: queueURL, options: .atomic)
        syncError = nil
        pendingCount = rows.filter { $0.ownerId == ownerId }.count
    }

    private func refreshPendingCount() {
        do { pendingCount = try readQueuedRows().filter { $0.ownerId == ownerId }.count }
        catch { reportStorageError() }
    }

    private func reportStorageError() {
        syncError = "Transcript sync paused. I could not read or save the delivery queue. Your recording remains on this Mac."
    }

    /// "mac-b<CFBundleVersion>", the way the phone stamps "iphone-b<build>":
    /// the ears gate names the build that last spoke from this column.
    private func deviceID() -> String {
        TranscriptWire.deviceID(
            build: Bundle.main.infoDictionary?["CFBundleVersion"] as? String)
    }
}
