import Foundation

/// A browser-agent job as stored in the backend. The Chrome extension claims
/// queued jobs, runs them, and reports status/result back here.
struct AgentJob: Identifiable, Decodable, Equatable {
    let id: String
    let goal: String
    let params: String
    let status: String // queued | running | awaiting_confirm | done | failed | cancelled
    let result: String?
    let created: String
}

/// A registered browser-agent (Chrome extension install). `lastSeen` is its
/// heartbeat — the app renders it as "last seen Ns ago".
struct BrowserAgent: Decodable, Equatable {
    let id: String
    let agent_id: String
    let owner: String?
    let paired: Bool?
    let last_seen: String?
    let browser: String?
}

/// One brain event: a transcript line, the brain's decision on it, or
/// something Anticipy said/texted.
struct BrainEvent: Decodable, Identifiable, Equatable {
    let id: String
    let kind: String // transcript | decision | anticipy_says | anticipy_text
    let text: String?
    let decision: String?
    let goal: String?
    let created: String
}

/// Thin client for the Anticipy PocketBase backend (pairing, events, jobs).
/// Endpoints proven live in proof/test_backend.py and proof/test_extension.py.
final class AnticipyBackend {
    var baseURL: URL
    let deviceID: String
    /// Shared write token, fetched after pairing. Empty until then; the
    /// backend guard ignores the header until enforcement is switched on.
    var serviceToken: String
    /// The signed-in person's session token, when there is one.
    var authToken: String

    init(baseURL: URL, deviceID: String, serviceToken: String = "",
         authToken: String = "", accountID: String = "") {
        self.baseURL = baseURL
        self.deviceID = deviceID
        self.serviceToken = serviceToken
        self.authToken = authToken
        self.accountID = accountID
    }

    /// Attach whatever credentials we have. Both may be present during the
    /// move onto accounts; the account token is the one that will outlive the
    /// shared secret.
    private func authorize(_ r: inout URLRequest) {
        if !serviceToken.isEmpty {
            r.setValue(serviceToken, forHTTPHeaderField: "X-Anticipy-Token")
        }
        if !authToken.isEmpty {
            r.setValue(authToken, forHTTPHeaderField: "Authorization")
        }
    }

    /// Reads carry the token too — the guard hook protects the whole data
    /// API, not just writes.
    ///
    /// A non-2xx read THROWS. It used to hand the body of a 403 back as if it
    /// were data; every caller then swallowed the decode failure with `try?`,
    /// so a refused read was indistinguishable from "you have nothing yet" and
    /// the app confidently painted an empty screen.
    private func readData(from url: URL) async throws -> Data {
        var r = URLRequest(url: url)
        authorize(&r)
        let (data, resp) = try await URLSession.shared.data(for: r)
        if let http = resp as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw BackendError(status: http.statusCode)
        }
        return data
    }

    /// Every write goes through here, so none of them can report success for a
    /// request the server refused. Four call sites used to do
    /// `_ = try await URLSession.shared.data(for:)` and then `return true`.
    @discardableResult
    private func send(_ request: URLRequest) async throws -> Data {
        let (data, resp) = try await URLSession.shared.data(for: request)
        if let http = resp as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw BackendError(status: http.statusCode)
        }
        return data
    }

    private func writeRequest(_ url: URL, method: String) -> URLRequest {
        var r = URLRequest(url: url)
        r.httpMethod = method
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        authorize(&r)
        return r
    }

    /// Store the owner's number where the brain reads it. Updates the
    /// existing row for this owner rather than piling up duplicates.
    func upsertOwnerPhone(ownerID: String, phone: String) async -> Bool {
        await upsertOwner(ownerID: ownerID, fields: ["phone": phone])
    }

    /// Name and email too: every booking and signup form asks for the same
    /// four things, and without them a run reaches the form and stops.
    func upsertOwner(ownerID: String, fields: [String: String]) async -> Bool {
        let listURL = baseURL.appendingPathComponent("api/collections/owner_profile/records")
        var comps = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
        let filter = "owner_id=\"\(ownerID)\"".addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)!
        comps.percentEncodedQuery = "filter=\(filter)&perPage=1"
        var existingID: String?
        if let url = comps.url,
           let data = try? await readData(from: url),
           let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let items = root["items"] as? [[String: Any]] {
            existingID = items.first?["id"] as? String
        }
        var body: [String: Any] = ["owner_id": ownerID]
        for (k, v) in fields where !v.isEmpty { body[k] = v }
        var req: URLRequest
        if let id = existingID {
            req = writeRequest(listURL.appendingPathComponent(id), method: "PATCH")
        } else {
            req = writeRequest(listURL, method: "POST")
        }
        req.httpBody = try? JSONSerialization.data(withJSONObject: body)
        guard let (_, resp) = try? await URLSession.shared.data(for: req),
              let http = resp as? HTTPURLResponse else { return false }
        return (200..<300).contains(http.statusCode)
    }

    /// An error that carries the server's own sentence, so the screen can show
    /// what actually went wrong instead of a generic apology.
    struct MessageError: Error { let message: String }

    /// Why an account couldn't be created, by field, so the screen can say
    /// what is actually wrong instead of blaming the email for everything.
    struct CreateAccountError: Error {
        let status: Int
        let emailTaken: Bool
        let phoneTaken: Bool
        let deviceTaken: Bool
    }

    /// Create an account. `legacyUUID` is this device's pre-accounts identity,
    /// carried up so the person's existing rows can be claimed rather than
    /// orphaned.
    func createAccount(email: String, password: String,
                       phone: String?, legacyUUID: String) async throws {
        var req = writeRequest(
            baseURL.appendingPathComponent("api/collections/owners/records"), method: "POST")
        var body: [String: Any] = [
            "email": email.trimmingCharacters(in: .whitespaces).lowercased(),
            "password": password,
            "passwordConfirm": password,
            "legacy_uuid": legacyUUID,
        ]
        if let phone, !phone.isEmpty { body["phone"] = phone }
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw BackendError(status: -1) }
        if (200..<300).contains(http.statusCode) { return }
        let root = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        let fields = (root?["data"] as? [String: Any]) ?? [:]
        throw CreateAccountError(status: http.statusCode,
                                 emailTaken: fields["email"] != nil,
                                 phoneTaken: fields["phone"] != nil,
                                 deviceTaken: fields["legacy_uuid"] != nil)
    }

    /// Sign in. Returns the session token and the account id.
    func authWithPassword(email: String, password: String) async throws -> (token: String, id: String) {
        var req = writeRequest(
            baseURL.appendingPathComponent("api/collections/owners/auth-with-password"),
            method: "POST")
        req.httpBody = try JSONSerialization.data(withJSONObject: [
            "identity": email.trimmingCharacters(in: .whitespaces).lowercased(),
            "password": password,
        ])
        let data = try await send(req)
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let token = root["token"] as? String,
              let record = root["record"] as? [String: Any],
              let id = record["id"] as? String
        else { throw BackendError(status: -1) }
        return (token, id)
    }

    /// Adopt everything this device made before accounts existed onto the
    /// account that just signed in, so signing up never looks like losing your
    /// history.
    func claimLegacy(legacyUUID: String) async {
        var req = writeRequest(baseURL.appendingPathComponent("auth/claim"), method: "POST")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["legacy_uuid": legacyUUID])
        _ = try? await send(req)
    }

    /// "I forgot my password" — the code arrives by text, because this backend
    /// has no way to send mail.
    func requestPasswordReset(email: String) async throws {
        var req = writeRequest(baseURL.appendingPathComponent("auth/reset/request"), method: "POST")
        req.httpBody = try JSONSerialization.data(withJSONObject: [
            "email": email.trimmingCharacters(in: .whitespaces).lowercased()])
        try await send(req)
    }

    func confirmPasswordReset(email: String, code: String, password: String) async throws {
        var req = writeRequest(baseURL.appendingPathComponent("auth/reset/confirm"), method: "POST")
        req.httpBody = try JSONSerialization.data(withJSONObject: [
            "email": email.trimmingCharacters(in: .whitespaces).lowercased(),
            "code": code.trimmingCharacters(in: .whitespaces),
            "password": password,
        ])
        do {
            try await send(req)
        } catch let e as BackendError {
            // The reset routes answer with a human sentence; surface it.
            _ = e
            throw MessageError(message: "That code isn't right, or it has expired. Ask for a new one.")
        }
    }

    /// The paired agent's key bundle also carries this phone's write token.
    func fetchServiceToken(agentID: String) async -> String? {
        var comps = URLComponents(url: baseURL.appendingPathComponent("agent/key"),
                                  resolvingAgainstBaseURL: false)!
        comps.queryItems = [URLQueryItem(name: "agent_id", value: agentID)]
        guard let url = comps.url,
              let (data, _) = try? await URLSession.shared.data(from: url),
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        let token = root["service_token"] as? String
        return (token?.isEmpty == false) ? token : nil
    }

    /// Pair this app to a pendant using the short code the pendant registered.
    func pair(code: String, owner: String) async throws -> Bool {
        let filter = "pair_code=\"\(code)\"".addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)!
        let listURL = baseURL.appendingPathComponent("api/collections/pendants/records")
        var comps = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
        comps.percentEncodedQuery = "filter=\(filter)"
        let data = try await readData(from: comps.url!)
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let items = root["items"] as? [[String: Any]],
              let id = items.first?["id"] as? String else { return false }

        var patch = writeRequest(listURL.appendingPathComponent(id), method: "PATCH")
        patch.httpBody = try JSONSerialization.data(withJSONObject: ["owner": owner, "paired": true])
        try await send(patch)
        return true
    }

    /// Pair this phone to a browser agent using the 6-digit code the
    /// extension displays. Binds the agent to this owner; from then on it
    /// only claims this owner's jobs.
    ///
    /// Returns false ONLY when the code genuinely matched nothing. Anything
    /// else — no network, a refused write — throws, so the UI can tell "that
    /// code is wrong" apart from "I can't reach Anticipy right now". Telling
    /// someone their correct code is wrong is how they give up.
    func pairAgent(code: String, owner: String) async throws -> Bool {
        let listURL = baseURL.appendingPathComponent("api/collections/agents/records")
        let filter = "pair_code=\"\(code)\"".addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)!
        var comps = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
        comps.percentEncodedQuery = "filter=\(filter)"
        let data = try await readData(from: comps.url!)
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let items = root["items"] as? [[String: Any]],
              let id = items.first?["id"] as? String else { return false }

        var patch = writeRequest(listURL.appendingPathComponent(id), method: "PATCH")
        patch.httpBody = try JSONSerialization.data(withJSONObject: ["owner": owner, "paired": true])
        try await send(patch)
        return true
    }

    /// The agent paired to this owner (if any), with its latest heartbeat.
    func fetchAgent(owner: String) async throws -> BrowserAgent? {
        let listURL = baseURL.appendingPathComponent("api/collections/agents/records")
        let filter = "owner=\"\(owner)\"".addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)!
        var comps = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
        comps.percentEncodedQuery = "filter=\(filter)&sort=-updated&perPage=1"
        let data = try await readData(from: comps.url!)
        struct Page: Decodable { let items: [BrowserAgent] }
        return try JSONDecoder().decode(Page.self, from: data).items.first
    }

    /// The signed-in account these writes belong to, when there is one.
    var accountID: String = ""

    func pushEvent(kind: String, text: String, decision: String? = nil,
                   goal: String? = nil, speaker: String? = nil) async throws {
        var body: [String: Any] = [
            "device_id": deviceID, "kind": kind, "text": text,
            "decision": decision ?? "", "goal": goal ?? "",
        ]
        // WHEN IT WAS SAID, not when it arrived. The phone buffers: offline,
        // backgrounded, bad signal, a call holding the mic — and then flushes
        // a lump. Everything downstream that reasons about order was reading
        // PocketBase's `created`, which is the moment the network delivered
        // the row, so a flushed backlog looked like a burst of unrelated
        // fragments seconds apart. Omi ships this exact bug (their #6551).
        // Stamped here, at the moment the line is finished, because this is
        // the last place that knows. The server treats an implausible stamp
        // as absent, so a device with a wrong clock degrades to today's
        // behaviour rather than reordering his day.
        // `capture_started_at` is the column the rest of the system already
        // names for this — it was provisioned long ago and no build ever wrote
        // to it, which is why everything downstream fell back to `created`.
        // Writing the existing name rather than a second one of my own.
        body["capture_started_at"] = ISO8601DateFormatter.anticipyUTC.string(from: Date())
        // The ONLY thing the voice check ever sends: one short word about
        // who spoke ("owner", "other:v2", "other:Sarah"). The voiceprint it
        // came from never leaves the phone, and neither does the audio.
        if let speaker, !speaker.isEmpty { body["speaker"] = speaker }
        // Say whose words these are. Until today `events` had no owner column
        // at all, which is why a brand-new account opened the app to a stranger's
        // transcripts — seen for real in the simulator against production.
        if !accountID.isEmpty { body["owner_ref"] = accountID }
        try await post("api/collections/events/records", body: body)
    }

    func queueJob(goal: String, params: [String: String]) async throws {
        let paramsJSON = String(data: try JSONSerialization.data(withJSONObject: params), encoding: .utf8) ?? "{}"
        try await post("api/collections/jobs/records", body: [
            "goal": goal, "params": paramsJSON, "status": "queued", "device_id": deviceID,
        ])
    }

    /// Latest brain events, newest first — heard lines + what Anticipy said.
    func fetchEvents(limit: Int = 40) async throws -> [BrainEvent] {
        let listURL = baseURL.appendingPathComponent("api/collections/events/records")
        var comps = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
        var items = [URLQueryItem(name: "perPage", value: String(limit)),
                     URLQueryItem(name: "sort", value: "-created")]
        // Scoped, always. Unowned legacy rows are deliberately NOT included:
        // showing them to whoever happens to be signed in is the exact bug this
        // fixes. They are claimed onto an account by /auth/claim instead.
        if !accountID.isEmpty {
            items.append(URLQueryItem(name: "filter", value: "owner_ref=\"\(accountID)\""))
        }
        comps.queryItems = items
        let data = try await readData(from: comps.url!)
        struct Page: Decodable { let items: [BrainEvent] }
        return try JSONDecoder().decode(Page.self, from: data).items
    }

    /// Latest jobs for THIS owner, newest first — powers the proactive feed.
    ///
    /// The owner filter is not cosmetic: unscoped, the second person to install
    /// Anticipy opened it to the first person's errands, with "Send it" next to
    /// them. `jobs` already carries `owner` (the brain stamps it), so this is a
    /// client-side change only. Note it is a courtesy, not a security boundary —
    /// the backend still gates every read on one shared token.
    func fetchJobs(owner: String, limit: Int = 30) async throws -> [AgentJob] {
        let listURL = baseURL.appendingPathComponent("api/collections/jobs/records")
        var comps = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
        var items = [URLQueryItem(name: "perPage", value: String(limit)),
                     URLQueryItem(name: "sort", value: "-created")]
        if !owner.isEmpty {
            items.append(URLQueryItem(name: "filter", value: "owner=\"\(owner)\""))
        }
        comps.queryItems = items
        let data = try await readData(from: comps.url!)
        struct Page: Decodable { let items: [AgentJob] }
        return try JSONDecoder().decode(Page.self, from: data).items
    }

    /// Release a held job (in-app "Send it") or cancel it ("Not now").
    func setJobStatus(id: String, status: String, params: String? = nil) async throws {
        let url = baseURL
            .appendingPathComponent("api/collections/jobs/records")
            .appendingPathComponent(id)
        var patch = writeRequest(url, method: "PATCH")
        var body: [String: Any] = ["status": status]
        if let params { body["params"] = params }
        patch.httpBody = try JSONSerialization.data(withJSONObject: body)
        // "Send it" and "Not now" land here. This used to discard the response,
        // so a 403 buzzed success and left the card sitting there — which reads
        // as a UI glitch, so people tap it again.
        try await send(patch)
    }

    /// Quick reachability probe for the connection health UI.
    func isReachable() async -> Bool {
        var req = URLRequest(url: baseURL.appendingPathComponent("api/health"))
        req.timeoutInterval = 4
        guard let (_, resp) = try? await URLSession.shared.data(for: req),
              let http = resp as? HTTPURLResponse else { return false }
        return http.statusCode == 200
    }

    struct BackendError: Error { let status: Int }

    private func post(_ path: String, body: [String: Any]) async throws {
        var request = writeRequest(baseURL.appendingPathComponent(path), method: "POST")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (_, resp) = try await URLSession.shared.data(for: request)
        // A rejected write is a FAILED write: without this the caller's
        // do/catch never fires and a line the backend refused looks sent.
        if let http = resp as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw BackendError(status: http.statusCode)
        }
    }
}

extension ISO8601DateFormatter {
    /// One shared, explicitly-UTC formatter for the capture stamp.
    ///
    /// Explicit about the timezone because the failure it prevents is not
    /// hypothetical: a build that stamps naive local time hands the server a
    /// timestamp hours away from the truth, and anything that gates on
    /// "how old is this line" then either drops today's speech as stale or
    /// treats yesterday's as fresh. Built once — ISO8601DateFormatter is
    /// expensive to construct and this runs on every finished line.
    static let anticipyUTC: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.timeZone = TimeZone(secondsFromGMT: 0)
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
}
