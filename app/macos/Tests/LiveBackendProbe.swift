// Explicit opt-in live transport proof with a disposable account and no phone.
import Foundation
@main struct LiveBackendProbe {
    struct Failure: Error { let message: String }
    static func check(_ condition: Bool, _ message: String = "live proof failed") throws {
        if !condition { throw Failure(message: message) }
    }
    static let base = URL(string: "https://api.anticipy.ai")!
    static func request(_ method: String, _ path: String, _ body: [String: Any]? = nil,
                        token: String = "") async throws -> (Int, [String: Any]) {
        var req = URLRequest(url: URL(string: "/" + path, relativeTo: base)!.absoluteURL, timeoutInterval: 25)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("Anticipy-Mac-release-proof/171", forHTTPHeaderField: "User-Agent")
        if !token.isEmpty { req.setValue(token, forHTTPHeaderField: "Authorization") }
        if let body { req.httpBody = try JSONSerialization.data(withJSONObject: body) }
        let (data, response) = try await URLSession.shared.data(for: req)
        return ((response as! HTTPURLResponse).statusCode,
                (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:])
    }
    @MainActor static func main() async throws {
        try check(CommandLine.arguments.contains("--live"), "requires explicit --live")
        let email = "mac-release-" + UUID().uuidString.lowercased() + "@anticipy-test.invalid"
        let password = UUID().uuidString + UUID().uuidString
        let privateURL = URL(fileURLWithPath: "work/audit/mac-integration/live-fixture-private.json")
        try JSONSerialization.data(withJSONObject: ["email": email, "password": password])
            .write(to: privateURL, options: .atomic)
        let (signup, _) = try await request("POST", "api/collections/owners/records",
            ["email": email, "password": password, "passwordConfirm": password])
        try check(signup == 200, "fixture signup failed")
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let backend = MacBackend(queueURL: dir.appendingPathComponent("queue.jsonl"), persistsSession: false)
        try await backend.signIn(email: email, password: password)
        try JSONSerialization.data(withJSONObject: ["email": email, "password": password,
            "ownerId": backend.ownerId, "token": backend.authToken]).write(to: privateURL, options: .atomic)
        var receipt: [String: Any] = ["source": "real MacBackend.swift", "base": base.absoluteString,
                                      "fixture_has_phone": false, "audio_uploaded": false]
        do {
            let now = Date()
            backend.postTranscript(text: "This is a synthetic Mac transport check. No action is requested.",
                startedAt: now.addingTimeInterval(-2), endedAt: now, speaker: "owner")
            backend.postTranscript(text: "A second synthetic speaker confirms the connection only.",
                startedAt: now, endedAt: now.addingTimeInterval(1), speaker: "other")
            let deadline = Date().addingTimeInterval(45)
            while backend.pendingCount > 0, Date() < deadline {
                try await Task.sleep(nanoseconds: 100_000_000)
            }
            try check(backend.isSignedIn && backend.pendingCount == 0 && backend.syncError == nil,
                         "live capture queue did not drain")
            let filter = "owner_ref=\"\(backend.ownerId)\"".addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)!
            let (status, list) = try await request("GET", "api/collections/events/records?filter=" + filter, token: backend.authToken)
            guard let rows = list["items"] as? [[String: Any]] else { throw Failure(message: "events read returned HTTP \(status)") }
            try check(status == 200 && rows.count == 2)
            try check(Set(rows.compactMap { $0["speaker"] as? String }) == Set(["owner", "other"]))
            try check(rows.allSatisfy { $0["source"] as? String == "mac" && $0["owner_ref"] as? String == backend.ownerId })
            let row = rows[0]
            let keys = ["id", "owner_ref", "kind", "source", "text", "speaker", "capture_started_at", "spoken_at", "capture_ended_at", "device_id"]
            let repeatBody = Dictionary(uniqueKeysWithValues: keys.map { ($0, row[$0]!) })
            let (repeatStatus, _) = try await request("POST", "api/collections/events/records", repeatBody, token: backend.authToken)
            let (readStatus, readBack) = try await request("GET", "api/collections/events/records/" + (row["id"] as! String), token: backend.authToken)
            try check(repeatStatus == 400 && readStatus == 200 && readBack["id"] as? String == row["id"] as? String)
            receipt["capture_count"] = rows.count
            receipt["speakers"] = ["owner", "other"]
            receipt["duplicate_rejected"] = true
            receipt["owner_scoped_readback"] = true
            receipt["capture_timestamps_preserved"] = rows.allSatisfy { ($0["capture_started_at"] as? String)?.contains("T") == true }
            receipt["brain_decision_measured"] = false
        } catch {
            _ = try? await request("POST", "me/delete", ["confirm": "delete"], token: backend.authToken)
            backend.signOut()
            try? FileManager.default.removeItem(at: dir)
            throw error
        }
        let (deleted, _) = try await request("POST", "me/delete", ["confirm": "delete"], token: backend.authToken)
        receipt["fixture_deleted"] = deleted == 200
        try check(deleted == 200, "fixture cleanup failed")
        backend.signOut()
        try? FileManager.default.removeItem(at: dir)
        try? FileManager.default.removeItem(at: privateURL)
        print(String(data: try JSONSerialization.data(withJSONObject: receipt, options: [.prettyPrinted, .sortedKeys]), encoding: .utf8)!)
    }
}
