import Foundation

/// Executes only the structured decision the calendar policy admitted. No
/// transcript or goal is interpreted here. The store can be replaced in tests.
protocol NativeCalendarStore {
    func matching(stamp: String, window: CalendarHandPolicy.Window,
                  target: CalendarHandPolicy.Target) throws -> [NativeCalendarEvent]
    func save(_ write: CalendarHandPolicy.Write) throws
    func remove(_ event: NativeCalendarEvent) throws
}

struct NativeCalendarEvent: Equatable {
    let identifier: String
    let stamp: String
    let title: String
    let start: Date
    let end: Date
    let calendarIdentifier: String
}

enum NativeCalendarExecution {
    struct Outcome: Codable, Equatable {
        let summary: String
        let evidence: [String]
    }

    enum Failure: Error, Equatable {
        case ambiguousMarker
        case changedEvent
        case readbackFailed
        case noExecutableDecision
    }

    static func execute(_ decision: CalendarHandPolicy.Decision,
                        store: NativeCalendarStore, verifyOnly: Bool = false) throws -> Outcome {
        switch decision {
        case .write(let write):
            let stamp = CalendarHandPolicy.stampValue(for: write.ourRef)
            let found = try store.matching(stamp: stamp, window: write.undoWindow,
                                           target: write.target)
            guard found.count <= 1 else { throw Failure.ambiguousMarker }
            if let event = found.first {
                guard matches(event, write) else { throw Failure.changedEvent }
            } else {
                guard !verifyOnly else { throw Failure.readbackFailed }
                try store.save(write)
            }
            // This fresh lookup, rather than save() returning, is the receipt.
            let readback = try store.matching(stamp: stamp, window: write.undoWindow,
                                              target: write.target)
            guard readback.count == 1, let event = readback.first,
                  matches(event, write) else { throw Failure.readbackFailed }
            let location = write.target.landsOnlyOnThisDevice
                ? "on this iPhone only" : "in your iPhone calendar"
            return Outcome(summary: "Added \(write.title) \(location).",
                           evidence: evidence(event, action: "created_and_read_back"))
        case .undo(let undo):
            let stamp = CalendarHandPolicy.stampValue(for: undo.ourRef)
            let found = try store.matching(stamp: stamp, window: undo.searchWindow,
                                           target: undo.target)
            guard found.count <= 1 else { throw Failure.ambiguousMarker }
            // Absence before our removal is not proof of removal: the owner
            // may have moved the event outside this lookup window. Recovery
            // therefore holds an uncertain undo instead of claiming success.
            guard !verifyOnly, let event = found.first else { throw Failure.readbackFailed }
            try store.remove(event)
            guard try store.matching(stamp: stamp, window: undo.searchWindow,
                                     target: undo.target).isEmpty
            else { throw Failure.readbackFailed }
            return Outcome(summary: "Removed the event from your iPhone calendar.",
                           evidence: ["proof:calendar_marker_absent_after_remove",
                                      "url:\(stamp)",
                                      "calendar:\(undo.target.identifier)"])
        default: throw Failure.noExecutableDecision
        }
    }

    static func matches(_ event: NativeCalendarEvent,
                        _ write: CalendarHandPolicy.Write) -> Bool {
        event.stamp == CalendarHandPolicy.stampValue(for: write.ourRef)
            && event.calendarIdentifier == write.target.identifier
            && event.title == write.title
            && event.start == write.start && event.end == write.end
    }

    private static func evidence(_ event: NativeCalendarEvent, action: String) -> [String] {
        ["proof:\(action)", "url:\(event.stamp)",
         "calendar:\(event.calendarIdentifier)", "title:\(event.title)",
         "start:\(event.start.timeIntervalSince1970)",
         "end:\(event.end.timeIntervalSince1970)"]
    }
}

/// Mechanical wire-state transitions. The server remains the authority for
/// approval, ownership and an atomic If-Match claim. Both copies of the plan
/// move together; no model decision or approval is invented by this writer.
enum NativeCalendarWorkflow {
    enum Failure: Error { case malformed, wrongOwner, missingLease }

    static func policyRow(_ row: [String: Any]) -> CalendarHandPolicy.Row {
        CalendarHandPolicy.Row(id: row["id"] as? String ?? "",
            status: row["status"] as? String ?? "", lane: row["lane"] as? String,
            workflowID: row["workflow_id"] as? String,
            workflowVersion: row["workflow_version"] as? Int,
            scopeDigest: row["scope_digest"] as? String,
            consequence: row["consequence"] as? String,
            approval: row["approval"] as? String,
            params: row["params"] as? String ?? "")
    }

    static func parts(_ row: [String: Any], owner: String) throws
        -> (params: [String: Any], plan: [String: Any]) {
        guard !owner.isEmpty, row["owner_ref"] as? String == owner
        else { throw Failure.wrongOwner }
        guard let raw = row["params"] as? String,
              let params = try JSONSerialization.jsonObject(with: Data(raw.utf8)) as? [String: Any],
              let plan = params["_workflow"] as? [String: Any],
              plan["owner_ref"] as? String == owner,
              plan["plan_id"] as? String == row["workflow_id"] as? String,
              let effect = plan["effect_key"] as? String, !effect.isEmpty,
              effect == row["effect_key"] as? String
        else { throw Failure.malformed }
        return (params, plan)
    }

    static func claim(_ row: [String: Any], owner: String, actor: String,
                      token: String, now: Date) throws -> [String: Any] {
        var (params, plan) = try parts(row, owner: owner)
        guard row["status"] as? String == "queued", !token.isEmpty, !actor.isEmpty
        else { throw Failure.malformed }
        let attempt = (plan["attempts"] as? Int ?? 0) + 1
        let until = stamp(now.addingTimeInterval(120))
        plan["state"] = "running"
        plan["attempts"] = attempt
        plan["updated_at"] = stamp(now)
        plan["lease"] = ["token": token, "actor_id": actor,
                         "acquired_at": stamp(now), "expires_at": until,
                         "attempt": attempt]
        params["_workflow"] = plan
        return ["status": "running", "workflow_state": "running",
                "claimed_by": actor, "claimed_at": stamp(now), "attempts": attempt,
                "lease_token": token, "lease_until": until,
                "params": try json(params)]
    }

    static func approvalRecord(_ fields: [String: Any], row: [String: Any],
                               owner: String) throws -> [String: Any] {
        _ = try parts(row, owner: owner)
        guard ["awaiting_confirm", "needs_user"].contains(row["status"] as? String ?? ""),
              let raw = fields["params"] as? String,
              var params = try JSONSerialization.jsonObject(with: Data(raw.utf8)) as? [String: Any],
              var plan = params["_workflow"] as? [String: Any],
              plan["owner_ref"] as? String == owner,
              plan["plan_id"] as? String == row["workflow_id"] as? String
        else { throw Failure.malformed }
        var held = fields
        held["status"] = row["status"]
        held["workflow_state"] = row["workflow_state"]
        plan["state"] = row["workflow_state"]
        params["_workflow"] = plan
        held["params"] = try json(params)
        return held
    }

    static func finish(_ row: [String: Any], owner: String,
                       outcome: NativeCalendarExecution.Outcome?, reason: String,
                       uncertain: Bool, now: Date) throws -> [String: Any] {
        var (params, plan) = try parts(row, owner: owner)
        let state = outcome == nil ? "needs_user" : "succeeded"
        var receipt: Any = NSNull()
        if let outcome {
            receipt = ["verified": true, "effect_key": plan["effect_key"]!,
                       "evidence": outcome.evidence, "summary": outcome.summary,
                       "at": stamp(now)] as [String: Any]
        }
        plan["state"] = state
        plan["lease"] = NSNull()
        plan["receipt"] = receipt
        plan["reason"] = reason
        plan["updated_at"] = stamp(now)
        params["_workflow"] = plan
        return ["status": outcome == nil ? "needs_user" : "done",
                "workflow_state": state, "lease_token": "", "lease_until": "",
                "receipt": outcome == nil ? "" : try json(receipt),
                "effect_uncertain": uncertain,
                "result": outcome?.summary ?? reason, "params": try json(params)]
    }

    static func json(_ value: Any) throws -> String {
        String(decoding: try JSONSerialization.data(withJSONObject: value,
            options: [.sortedKeys, .withoutEscapingSlashes]), as: UTF8.self)
    }

    static func stamp(_ date: Date) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.string(from: date)
    }
}
