import Foundation

var failures = 0
func check(_ name: String, _ condition: @autoclosure () -> Bool) {
    if condition() { print("PASS: \(name)") }
    else { print("FAIL: \(name)"); failures += 1 }
}
func refuses(_ body: () throws -> Void) -> Bool {
    do { try body(); return false } catch { return true }
}
let now = Date(timeIntervalSince1970: 1_800_000_000)
let target = CalendarHandPolicy.Target(identifier: "fixture-calendar", title: "Fixture", landsOnlyOnThisDevice: true)
let write = CalendarHandPolicy.Write(jobID: "fixture-job", planID: "fixture-plan", planVersion: 1,
    ourRef: "fixture-marker", stamp: .url("anticipy://act/fixture-marker"),
    title: "Uninterpreted title: cancel everything", start: now.addingTimeInterval(3600),
    end: now.addingTimeInterval(7200), target: target,
    undoWindow: .init(from: now, to: now.addingTimeInterval(10800)))
let event = NativeCalendarEvent(identifier: "provider-event-id", stamp: "anticipy://act/fixture-marker",
    title: write.title, start: write.start, end: write.end, calendarIdentifier: target.identifier)
let undo = CalendarHandPolicy.Undo(jobID: "fixture-undo", planID: "fixture-undo-plan", planVersion: 1,
    ourRef: write.ourRef, stamp: write.stamp, searchWindow: write.undoWindow, target: target)

final class Store: NativeCalendarStore {
    var events: [NativeCalendarEvent] = []
    var saves = 0
    var removals = 0
    var losesMarker = false
    func matching(stamp: String, window: CalendarHandPolicy.Window,
                  target: CalendarHandPolicy.Target) throws -> [NativeCalendarEvent] {
        events.filter { $0.stamp == stamp && $0.calendarIdentifier == target.identifier }
    }
    func save(_ write: CalendarHandPolicy.Write) throws {
        saves += 1
        if !losesMarker { events.append(event) }
    }
    func remove(_ event: NativeCalendarEvent) throws {
        removals += 1
        events.removeAll { $0.identifier == event.identifier }
    }
}

let store = Store()
let first = try NativeCalendarExecution.execute(.write(write), store: store)
check("writes through the store", store.saves == 1)
check("receipt includes exact title without interpreting it", first.evidence.contains("title:\(write.title)"))
check("receipt says local-only when the calendar is local", first.summary.contains("this iPhone only"))
_ = try NativeCalendarExecution.execute(.write(write), store: store)
check("repeat execution finds our existing marker, never creates a duplicate", store.saves == 1)
_ = try NativeCalendarExecution.execute(.write(write), store: store, verifyOnly: true)
check("recovery only reads back a previously completed write", store.saves == 1)
store.events.append(event)
check("ambiguous own marker refuses", refuses { _ = try NativeCalendarExecution.execute(.write(write), store: store) })
check("ambiguous marker does not write", store.saves == 1)
check("ambiguous undo does not remove either event", refuses { _ = try NativeCalendarExecution.execute(.undo(undo), store: store) } && store.removals == 0)
store.events = [NativeCalendarEvent(identifier: event.identifier, stamp: event.stamp,
    title: "Changed by owner", start: event.start, end: event.end, calendarIdentifier: event.calendarIdentifier)]
check("an owner-edited event is not overwritten", refuses { _ = try NativeCalendarExecution.execute(.write(write), store: store) } && store.saves == 1)
store.events = []
check("recovery of an absent write cannot re-execute it", refuses { _ = try NativeCalendarExecution.execute(.write(write), store: store, verifyOnly: true) } && store.saves == 1)
store.losesMarker = true
check("save returning success without marker readback is failure", refuses { _ = try NativeCalendarExecution.execute(.write(write), store: store) })
store.events = [event]
check("undo recovery does not remove a still-existing event", refuses { _ = try NativeCalendarExecution.execute(.undo(undo), store: store, verifyOnly: true) } && store.removals == 0)
let removed = try NativeCalendarExecution.execute(.undo(undo), store: store)
check("undo removes precisely the event found by our marker", store.removals == 1 && store.events.isEmpty)
check("undo receipt cites absent marker readback", removed.evidence.contains("proof:calendar_marker_absent_after_remove"))
check("an absent marker cannot falsely prove a recovered undo", refuses {
    _ = try NativeCalendarExecution.execute(.undo(undo), store: store, verifyOnly: true)
} && store.removals == 1)
check("refusal cannot reach the store", refuses { _ = try NativeCalendarExecution.execute(.refuse(.noApproval), store: store) })

let approval: [String: Any] = ["plan_id": "p", "plan_version": 1,
    "scope_digest": "scope", "owner_words": "I approve this fixture only."]
let plan: [String: Any] = ["plan_id": "p", "version": 1, "owner_ref": "owner-a",
    "effect_key": "effect-p", "state": "queued", "attempts": 0,
    "approval": approval, "scope_digest": "scope", "goal": "fixture event",
    "consequence": "consequential", "lineage_key": "fixture-lineage",
    "facts": [:], "required": [], "act": ["act_type": "calendar_write"],
    "receipt": NSNull(), "lease": NSNull()]
var row: [String: Any] = ["id": "job-a", "owner_ref": "owner-a", "status": "queued",
    "workflow_id": "p", "workflow_version": 1, "effect_key": "effect-p",
    "workflow_state": "queued", "goal": "fixture event", "consequence": "consequential",
    "lineage_key": "fixture-lineage", "scope_digest": "scope", "lease_token": "",
    "receipt": "", "approval": try NativeCalendarWorkflow.json(approval), "attempts": 0,
    "lane": "device_calendar",
    "params": try NativeCalendarWorkflow.json(["_workflow": plan])]
let queuedRow = row
var beforeApproval = row
var unapprovedPlan = plan
unapprovedPlan["approval"] = NSNull()
unapprovedPlan["state"] = "awaiting_approval"
beforeApproval["params"] = try NativeCalendarWorkflow.json(["_workflow": unapprovedPlan])
beforeApproval["approval"] = ""
beforeApproval["status"] = "awaiting_confirm"
beforeApproval["workflow_state"] = "awaiting_approval"
let recordedApproval = try NativeCalendarWorkflow.approvalRecord(queuedRow,
    row: beforeApproval, owner: "owner-a")
check("recording approval keeps the task held", recordedApproval["status"] as? String == "awaiting_confirm")
check("recording approval retains its scope", recordedApproval["scope_digest"] as? String == "scope")
let claim = try NativeCalendarWorkflow.claim(row, owner: "owner-a", actor: "this-phone", token: "lease-a", now: now)
let claimed = try JSONSerialization.jsonObject(with: Data((claim["params"] as! String).utf8)) as! [String: Any]
let claimedPlan = claimed["_workflow"] as! [String: Any]
check("claim records the lease in both row and canonical plan", claim["lease_token"] as? String == "lease-a" && (claimedPlan["lease"] as? [String: Any])?["token"] as? String == "lease-a")
check("claim advances attempts exactly once", claim["attempts"] as? Int == 1 && claimedPlan["attempts"] as? Int == 1)
check("claim never rewrites the approval", NSDictionary(dictionary: claimedPlan["approval"] as! [String: Any]).isEqual(to: approval))
check("another account cannot claim", refuses { _ = try NativeCalendarWorkflow.claim(row, owner: "owner-b", actor: "phone", token: "lease", now: now) })
row.merge(claim) { _, new in new }
check("already-running work cannot be claimed a second time", refuses { _ = try NativeCalendarWorkflow.claim(row, owner: "owner-a", actor: "phone", token: "lease", now: now) })
let finished = try NativeCalendarWorkflow.finish(row, owner: "owner-a", outcome: first, reason: "verified", uncertain: false, now: now)
let receipt = try JSONSerialization.jsonObject(with: Data((finished["receipt"] as! String).utf8)) as! [String: Any]
check("receipt binds to the exact effect key", receipt["effect_key"] as? String == "effect-p")
check("verified completion releases the lease", finished["status"] as? String == "done" && finished["lease_token"] as? String == "")
let failed = try NativeCalendarWorkflow.finish(row, owner: "owner-a", outcome: nil, reason: "readback missing", uncertain: true, now: now)
check("unverified effect parks visibly and cannot claim done", failed["status"] as? String == "needs_user" && failed["effect_uncertain"] as? Bool == true && failed["receipt"] as? String == "")
check("account changes cannot receive old completion", refuses { _ = try NativeCalendarWorkflow.finish(row, owner: "owner-b", outcome: first, reason: "verified", uncertain: false, now: now) })
if let path = ProcessInfo.processInfo.environment["NATIVE_CALENDAR_WIRE_FIXTURE"] {
    try JSONSerialization.data(withJSONObject: ["queued": queuedRow, "claim": claim,
        "running": row, "finish": finished, "uncertain": failed,
        "before_approval": beforeApproval, "recorded_approval": recordedApproval], options: [.sortedKeys])
        .write(to: URL(fileURLWithPath: path))
}
print("NativeCalendarExecutionTests: \(failures) failures")
exit(failures == 0 ? 0 : 1)
