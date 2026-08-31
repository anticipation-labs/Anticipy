import Foundation
import Security

/// The Mac's mouth and its memory of who it is. Signs into PocketBase the
/// same way the phone does (owners/auth-with-password), posts transcript
/// events the same way (kind, text, capture envelope, owner_ref), and keeps
/// unsent lines in a JSONL queue on disk so a dead network delays a line
/// rather than deleting it.
///
/// The auth token lives in the Keychain, not in UserDefaults — it is a
/// session credential for a person's whole life, and plists are readable by
/// anything running as the user.
final class PocketBase: ObservableObject {

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
        let source: String

        init(id: UUID = UUID(), ownerId: String, text: String,
             startedAt: Date, endedAt: Date, speaker: String, source: String) {
            self.id = id
            self.ownerId = ownerId
            self.text = text
            self.startedAt = startedAt
            self.endedAt = endedAt
            self.speaker = speaker
            self.source = source
        }

        private enum CodingKeys: String, CodingKey {
            case id, ownerId, text, startedAt, endedAt, speaker, source
        }

        init(from decoder: Decoder) throws {
            let values = try decoder.container(keyedBy: CodingKeys.self)
            id = try values.decodeIfPresent(UUID.self, forKey: .id) ?? UUID()
            ownerId = try values.decodeIfPresent(String.self, forKey: .ownerId) ?? ""
            text = try values.decode(String.self, forKey: .text)
            startedAt = try values.decode(Date.self, forKey: .startedAt)
            endedAt = try values.decode(Date.self, forKey: .endedAt)
            speaker = try values.decodeIfPresent(String.self, forKey: .speaker) ?? ""
            source = try values.decodeIfPresent(String.self, forKey: .source) ?? "mac"
        }
    }

    private final class RequestResult: @unchecked Sendable {
        private let lock = NSLock()
        private var value = false

        func markSuccessful() { lock.lock(); value = true; lock.unlock() }
        func read() -> Bool { lock.lock(); defer { lock.unlock() }; return value }
    }

    static let shared = PocketBase()

    let baseURL: URL
    @Published private(set) var isSignedIn = false
    private(set) var authToken: String = ""
    private(set) var ownerId: String = ""
    private(set) var ownerEmail: String = ""

    private let keychainAccount = "ai.anticipy.mac.session"
    private let queue = DispatchQueue(label: "ai.anticipy.mac.push")
    private var queueURL: URL

    init(baseURL: URL = URL(string: "https://backend-production-61e0a.up.railway.app")!) {
        self.baseURL = baseURL
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Anticipy", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        queueURL = dir.appendingPathComponent("unsent.jsonl")
        loadSession()
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
        authToken = creds.token
        ownerId = creds.ownerId
        ownerEmail = creds.email
        isSignedIn = true
        drainQueue()
    }

    func signIn(email: String, password: String) async throws {
        struct AuthResponse: Decodable { let token: String; let record: OwnerRecord }
        struct OwnerRecord: Decodable { let id: String; let email: String }
        var req = URLRequest(url: baseURL.appendingPathComponent("api/collections/owners/auth-with-password"))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONSerialization.data(withJSONObject: ["identity": email, "password": password])
        let (data, response) = try await URLSession.shared.data(for: req)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw URLError(.userAuthenticationRequired)
        }
        let auth = try JSONDecoder().decode(AuthResponse.self, from: data)
        saveSession(Credentials(token: auth.token, ownerId: auth.record.id,
                                email: auth.record.email, expiry: nil))
    }

    func signOut() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: keychainAccount,
        ]
        SecItemDelete(query as CFDictionary)
        authToken = ""
        ownerId = ""
        ownerEmail = ""
        isSignedIn = false
    }

    // --------------------------------------------------------------- posts

    func postTranscript(text: String, startedAt: Date, endedAt: Date,
                        speaker: String, source: String) {
        guard isSignedIn, !text.isEmpty else { return }
        let queued = QueuedTranscript(ownerId: ownerId, text: text,
                                      startedAt: startedAt, endedAt: endedAt,
                                      speaker: speaker, source: source)
        queue.async { [weak self] in
            guard let self else { return }
            var rows = self.readQueuedRows()
            rows.append(queued)
            self.writeQueuedRows(rows)
            self.drainQueueOnWorker()
        }
    }

    // The offline line: JSONL, one line per unsent utterance, drained on
    // launch and after every successful post. A queued line keeps its own
    // instants — re-stamping at flush time would reorder somebody's day
    // (the Omi #6551 class of bug, already fixed once on the phone).
    private func drainQueue() {
        guard isSignedIn else { return }
        queue.async { [weak self] in self?.drainQueueOnWorker() }
    }

    /// Runs only on `queue`. A row is removed after a 2xx response, never when
    /// a request merely started. Rows for another account stay on disk.
    private func drainQueueOnWorker() {
        guard isSignedIn else { return }
        let rows = readQueuedRows()
        guard !rows.isEmpty else { return }
        var keep: [QueuedTranscript] = []

        for row in rows {
            guard row.ownerId == ownerId else {
                keep.append(row)
                continue
            }
            if !sendSynchronously(row) { keep.append(row) }
        }
        writeQueuedRows(keep)
    }

    private func sendSynchronously(_ row: QueuedTranscript) -> Bool {
        var body: [String: Any] = [
            "device_id": deviceID(),
            "kind": "transcript",
            "text": row.text,
            "decision": "",
            "goal": "",
            "owner_ref": row.ownerId,
            "source": row.source,
            "speaker": row.speaker,
        ]
        let clock = ISO8601DateFormatter.anticipyUTC
        body["capture_started_at"] = clock.string(from: row.startedAt)
        body["spoken_at"] = clock.string(from: row.startedAt)
        body["capture_ended_at"] = clock.string(from: row.endedAt)

        var request = URLRequest(
            url: baseURL.appendingPathComponent("api/collections/events/records"),
            timeoutInterval: 20)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(authToken, forHTTPHeaderField: "Authorization")
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        let semaphore = DispatchSemaphore(value: 0)
        let result = RequestResult()
        URLSession.shared.dataTask(with: request) { _, response, _ in
            if let http = response as? HTTPURLResponse,
               (200...299).contains(http.statusCode) { result.markSuccessful() }
            semaphore.signal()
        }.resume()
        semaphore.wait()
        return result.read()
    }

    private func readQueuedRows() -> [QueuedTranscript] {
        guard let raw = try? String(contentsOf: queueURL, encoding: .utf8) else { return [] }
        let decoder = JSONDecoder()
        return raw.split(separator: "\n").compactMap {
            try? decoder.decode(QueuedTranscript.self, from: Data($0.utf8))
        }
    }

    private func writeQueuedRows(_ rows: [QueuedTranscript]) {
        if rows.isEmpty {
            try? FileManager.default.removeItem(at: queueURL)
            return
        }
        let encoder = JSONEncoder()
        let data = rows.compactMap { try? encoder.encode($0) }
            .reduce(into: Data()) { output, row in
                output.append(row)
                output.append(Data("\n".utf8))
            }
        try? data.write(to: queueURL, options: .atomic)
    }

    private func deviceID() -> String {
        let key = "ai.anticipy.mac.deviceID"
        if let existing = UserDefaults.standard.string(forKey: key) { return existing }
        let fresh = UUID().uuidString
        UserDefaults.standard.set(fresh, forKey: key)
        return fresh
    }
}

extension ISO8601DateFormatter {
    /// The same formatter iOS's CaptureEnvelope uses: fractional
    /// seconds, UTC. Two instants 300 ms apart must not render as the
    /// same string, or a genuinely bracketed line is indistinguishable
    /// from the collapsed one.
    static let anticipyUTC: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        f.timeZone = TimeZone(identifier: "UTC")
        return f
    }()
}
