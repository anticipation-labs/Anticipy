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

    func postTranscript(text: String, startedAt: Date, endedAt: Date) {
        guard isSignedIn, !text.isEmpty else { return }
        var body: [String: Any] = [
            "device_id": deviceID(),
            "kind": "transcript",
            "text": text,
            "decision": "",
            "goal": "",
            "owner_ref": ownerId,
            "source": "mac",
        ]
        let clock = ISO8601DateFormatter.anticipyUTC
        body["capture_started_at"] = clock.string(from: startedAt)
        body["spoken_at"] = clock.string(from: startedAt)
        body["capture_ended_at"] = clock.string(from: endedAt)

        queue.async { [weak self] in
            guard let self else { return }
            var req = URLRequest(url: self.baseURL.appendingPathComponent("api/collections/events/records"))
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.setValue(self.authToken, forHTTPHeaderField: "Authorization")
            req.httpBody = try? JSONSerialization.data(withJSONObject: body)
            let sem = DispatchSemaphore(value: 0)
            URLSession.shared.dataTask(with: req) { _, response, _ in
                defer { sem.signal() }
                if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
                    self.enqueueLocal(text: text, startedAt: startedAt, endedAt: endedAt)
                }
            }.resume()
            sem.wait()
        }
    }

    // The offline line: JSONL, one line per unsent utterance, drained on
    // launch and after every successful post. A queued line keeps its own
    // instants — re-stamping at flush time would reorder somebody's day
    // (the Omi #6551 class of bug, already fixed once on the phone).
    private func enqueueLocal(text: String, startedAt: Date, endedAt: Date) {
        struct Queued: Codable { let text: String; let startedAt: Date; let endedAt: Date }
        guard let data = try? JSONEncoder().encode(Queued(text: text, startedAt: startedAt, endedAt: endedAt)) else { return }
        guard let handle = try? FileHandle(forWritingTo: queueURL) else {
            try? data.write(to: queueURL)
            return
        }
        defer { try? handle.close() }
        _ = try? handle.seekToEnd()
        try? handle.write(contentsOf: Data(data + Data("\n".utf8)))
    }

    private func drainQueue() {
        guard isSignedIn, let raw = try? String(contentsOf: queueURL, encoding: .utf8) else { return }
        let rows = raw.split(separator: "\n")
        guard !rows.isEmpty else { return }
        struct Queued: Codable { let text: String; let startedAt: Date; let endedAt: Date }
        let decoder = JSONDecoder()
        DispatchQueue.global().async { [weak self] in
            for row in rows {
                guard let q = try? decoder.decode(Queued.self, from: Data(row.utf8)) else { continue }
                self?.postTranscript(text: q.text, startedAt: q.startedAt, endedAt: q.endedAt)
            }
            try? FileManager.default.removeItem(at: self?.queueURL ?? URL(fileURLWithPath: "/dev/null"))
        }
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
