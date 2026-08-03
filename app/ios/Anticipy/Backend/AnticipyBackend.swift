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

    init(baseURL: URL, deviceID: String, serviceToken: String = "") {
        self.baseURL = baseURL
        self.deviceID = deviceID
        self.serviceToken = serviceToken
    }

    /// Reads carry the token too — the guard hook protects the whole data
    /// API, not just writes.
    private func readData(from url: URL) async throws -> Data {
        var r = URLRequest(url: url)
        if !serviceToken.isEmpty {
            r.setValue(serviceToken, forHTTPHeaderField: "X-Anticipy-Token")
        }
        let (data, _) = try await URLSession.shared.data(for: r)
        return data
    }

    private func writeRequest(_ url: URL, method: String) -> URLRequest {
        var r = URLRequest(url: url)
        r.httpMethod = method
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if !serviceToken.isEmpty {
            r.setValue(serviceToken, forHTTPHeaderField: "X-Anticipy-Token")
        }
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
        _ = try await URLSession.shared.data(for: patch)
        return true
    }

    /// Pair this phone to a browser agent using the 6-digit code the
    /// extension displays. Binds the agent to this owner; from then on it
    /// only claims this owner's jobs.
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
        _ = try await URLSession.shared.data(for: patch)
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

    func pushEvent(kind: String, text: String, decision: String? = nil, goal: String? = nil) async throws {
        try await post("api/collections/events/records", body: [
            "device_id": deviceID, "kind": kind, "text": text,
            "decision": decision ?? "", "goal": goal ?? "",
        ])
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
        comps.queryItems = [
            URLQueryItem(name: "perPage", value: String(limit)),
            URLQueryItem(name: "sort", value: "-created"),
        ]
        let data = try await readData(from: comps.url!)
        struct Page: Decodable { let items: [BrainEvent] }
        return try JSONDecoder().decode(Page.self, from: data).items
    }

    /// Latest jobs, newest first — powers the proactive feed.
    func fetchJobs(limit: Int = 30) async throws -> [AgentJob] {
        let listURL = baseURL.appendingPathComponent("api/collections/jobs/records")
        var comps = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
        comps.queryItems = [
            URLQueryItem(name: "perPage", value: String(limit)),
            URLQueryItem(name: "sort", value: "-created"),
        ]
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
        _ = try await URLSession.shared.data(for: patch)
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
