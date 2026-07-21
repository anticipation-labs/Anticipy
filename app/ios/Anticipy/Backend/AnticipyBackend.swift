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

/// Thin client for the Anticipy PocketBase backend (pairing, events, jobs).
/// Endpoints proven live in proof/test_backend.py and proof/test_extension.py.
final class AnticipyBackend {
    var baseURL: URL
    let deviceID: String

    init(baseURL: URL, deviceID: String) {
        self.baseURL = baseURL
        self.deviceID = deviceID
    }

    /// Pair this app to a pendant using the short code the pendant registered.
    func pair(code: String, owner: String) async throws -> Bool {
        let filter = "pair_code=\"\(code)\"".addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)!
        let listURL = baseURL.appendingPathComponent("api/collections/pendants/records")
        var comps = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
        comps.percentEncodedQuery = "filter=\(filter)"
        let (data, _) = try await URLSession.shared.data(from: comps.url!)
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let items = root["items"] as? [[String: Any]],
              let id = items.first?["id"] as? String else { return false }

        var patch = URLRequest(url: listURL.appendingPathComponent(id))
        patch.httpMethod = "PATCH"
        patch.setValue("application/json", forHTTPHeaderField: "Content-Type")
        patch.httpBody = try JSONSerialization.data(withJSONObject: ["owner": owner, "paired": true])
        _ = try await URLSession.shared.data(for: patch)
        return true
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

    /// Latest jobs, newest first — powers the proactive feed.
    func fetchJobs(limit: Int = 30) async throws -> [AgentJob] {
        let listURL = baseURL.appendingPathComponent("api/collections/jobs/records")
        var comps = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
        comps.queryItems = [
            URLQueryItem(name: "perPage", value: String(limit)),
            URLQueryItem(name: "sort", value: "-created"),
        ]
        let (data, _) = try await URLSession.shared.data(from: comps.url!)
        struct Page: Decodable { let items: [AgentJob] }
        return try JSONDecoder().decode(Page.self, from: data).items
    }

    /// Release a held job (in-app "Send it") or cancel it ("Not now").
    func setJobStatus(id: String, status: String) async throws {
        let url = baseURL
            .appendingPathComponent("api/collections/jobs/records")
            .appendingPathComponent(id)
        var patch = URLRequest(url: url)
        patch.httpMethod = "PATCH"
        patch.setValue("application/json", forHTTPHeaderField: "Content-Type")
        patch.httpBody = try JSONSerialization.data(withJSONObject: ["status": status])
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

    private func post(_ path: String, body: [String: Any]) async throws {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        _ = try await URLSession.shared.data(for: request)
    }
}
