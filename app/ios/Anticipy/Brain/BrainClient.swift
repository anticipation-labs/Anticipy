import Foundation

/// The phone-side brain: sends each transcript line to OpenRouter for triage
/// (same prompt + JSON contract as the server brain, proven in proof/test_brain.py)
/// and queues 'act' goals as jobs for the Chrome extension via the backend.
struct BrainDecision: Decodable {
    let decision: String // ignore | act | ask
    let goal: String?
    let reason: String
}

final class BrainClient {
    private let apiKey: String
    private let model: String
    private let backend: AnticipyBackend

    init(apiKey: String, model: String = "deepseek/deepseek-v3.2", backend: AnticipyBackend) {
        self.apiKey = apiKey
        self.model = model
        self.backend = backend
    }

    static let triageSystem = """
    You are Anticipy, a proactive assistant that listens to a person's day \
    through a pendant microphone. For each transcript line decide one of: \
    "ignore" (small talk), "ask" (ambiguous, ask a short question), or "act" \
    (a clear commitment you can complete in the user's browser). Reply ONLY with \
    compact JSON: {"decision":"ignore|ask|act","goal":"<short goal or null>","reason":"<8 words>"}
    """

    func triage(_ line: String) async throws -> BrainDecision {
        var request = URLRequest(url: URL(string: "https://openrouter.ai/api/v1/chat/completions")!)
        request.httpMethod = "POST"
        request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("https://anticipy.ai", forHTTPHeaderField: "HTTP-Referer")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "model": model,
            "temperature": 0.1,
            "messages": [
                ["role": "system", "content": Self.triageSystem],
                ["role": "user", "content": line],
            ],
        ])
        let (data, _) = try await URLSession.shared.data(for: request)
        let root = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        let content = (((root?["choices"] as? [[String: Any]])?.first?["message"]
            as? [String: Any])?["content"] as? String) ?? "{}"
        let json = Self.extractJSON(content)
        return try JSONDecoder().decode(BrainDecision.self, from: Data(json.utf8))
    }

    /// Action-first: queue the job immediately; irreversible ends stop at a
    /// prefilled confirm screen driven by the extension.
    func handle(_ line: String) async throws -> BrainDecision {
        let decision = try await triage(line)
        try await backend.pushEvent(kind: "decision", text: line,
                                    decision: decision.decision, goal: decision.goal)
        if decision.decision == "act", let goal = decision.goal {
            try await backend.queueJob(goal: goal, params: ["source": line])
        }
        return decision
    }

    static func extractJSON(_ text: String) -> String {
        guard let start = text.firstIndex(of: "{"), let end = text.lastIndex(of: "}") else { return "{}" }
        return String(text[start ... end])
    }
}
