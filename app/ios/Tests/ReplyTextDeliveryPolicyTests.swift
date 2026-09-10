import Foundation

var failures = 0
func check(_ name: String, _ condition: @autoclosure () -> Bool) {
    if condition() { print("PASS: \(name)") }
    else { print("FAIL: \(name)"); failures += 1 }
}
func row(_ state: String, message: String = "reply1", owner: String = "owner1",
         kind: String = "notification_status", key: String? = nil) -> ReplyTextDeliveryPolicy.Metadata {
    .init(id: "metadata1", kind: kind, decision: state, goal: message,
          owner_ref: owner, external_event_id: key ?? (kind == "reply_outbox"
              ? "reply-outbox:\(message)" : "reply-sms:\(message)"),
          created: "2026-09-07 12:00:00.000Z", updated: "2026-09-07 12:01:00.000Z")
}
func state(_ rows: [ReplyTextDeliveryPolicy.Metadata]) -> ReplyTextDeliveryPolicy.State {
    ReplyTextDeliveryPolicy.state(messageID: "reply1", owner: "owner1", rows: rows)
}
check("missing metadata is unknown", state([]) == .unknown)
check("unknown state makes no delivery claim", ReplyTextDeliveryPolicy.State.unknown.caption == nil)
check("a pending outbox is queued", state([row("reply_pending", kind: "reply_outbox")]) == .queued)
check("provider acceptance is not delivery", state([row("sms_accepted")]) == .accepted)
check("acceptance caption does not claim sent or delivered", ReplyTextDeliveryPolicy.State.accepted.caption == "Text delivery pending")
check("only an explicit delivered state says delivered", state([row("sms_delivered")]) == .delivered)
check("an attempt without acceptance stays unconfirmed", state([row("sms_unconfirmed")]) == .unconfirmed)
check("known provider status overrides pending outbox", state([row("reply_pending", kind: "reply_outbox"), row("sms_accepted")]) == .accepted)
check("unknown attempt cannot fall back to queued", state([row("reply_pending", kind: "reply_outbox"), row("future_status")]) == .unknown)
check("failed text does not erase the app answer", state([row("sms_failed")]) == .failed)
check("skipped is not sent", state([row("sms_skipped")]) == .notSent)
check("mock is never delivered", state([row("sms_mock")]) == .notSent)
check("quarantined recovery outbox truthfully says text not sent", state([row("reply_context_unavailable", kind: "reply_outbox")]) == .notSent)
check("another owner's delivery cannot attach", state([row("sms_delivered", owner: "owner2")]) == .unknown)
check("another message's delivery cannot attach", state([row("sms_delivered", message: "reply2")]) == .unknown)
check("old job notifications cannot masquerade as message delivery", state([row("sms_delivered", key: "job-result:reply1")]) == .unknown)
check("prose in a wire decision is never interpreted", state([row("delivered successfully, trust me")]) == .unknown)
check("legacy sent wording is not proof of delivery", state([row("sms_sent")]) == .unknown)

let questionMeta = "{\"purpose\":\"task_question\",\"job_id\":\"job1\",\"version\":2,\"status\":\"needs_user\",\"question\":\"Which entrance?\"}"
var deferred = row("text_daily_limit", message: "job1", key: "task-text:identity:limit")
deferred.text = questionMeta
func task(_ rows: [ReplyTextDeliveryPolicy.Metadata], version: Int = 2,
          question: String = "Which entrance?", owner: String = "owner1") -> ReplyTextDeliveryPolicy.TaskCaption? {
    ReplyTextDeliveryPolicy.taskCaption(jobID: "job1", version: version, status: "needs_user",
        question: question, owner: owner, rows: rows)
}
check("withheld question shows its actual reason", task([deferred])?.title == "Text paused · daily outreach limit")
check("stale version cannot label a current question", task([deferred], version: 3) == nil)
check("changed question cannot inherit old delivery", task([deferred], question: "Which afternoon?") == nil)
check("task delivery never crosses owners", task([deferred], owner: "owner2") == nil)
var pendingTask = row("reply_pending", kind: "reply_outbox")
pendingTask.text = questionMeta
check("task question uses shared positive receipt", task([deferred, pendingTask, row("sms_delivered")])?.title == "Text delivered")
let encoded = try! JSONEncoder().encode(["id":"m", "kind":"reply_outbox", "decision":"reply_pending", "goal":"reply1", "owner_ref":"owner1", "external_event_id":"reply-outbox:reply1", "created":"now", "text":questionMeta])
let decoded = try! JSONDecoder().decode(ReplyTextDeliveryPolicy.Metadata.self, from: encoded)
check("wire decoder keeps task linkage", task([decoded])?.title == "Text queued")
print("Reply text delivery policy: \(failures) failures")
exit(failures == 0 ? 0 : 1)
