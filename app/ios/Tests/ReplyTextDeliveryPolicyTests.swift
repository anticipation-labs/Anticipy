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
check("another owner's delivery cannot attach", state([row("sms_delivered", owner: "owner2")]) == .unknown)
check("another message's delivery cannot attach", state([row("sms_delivered", message: "reply2")]) == .unknown)
check("old job notifications cannot masquerade as message delivery", state([row("sms_delivered", key: "job-result:reply1")]) == .unknown)
check("prose in a wire decision is never interpreted", state([row("delivered successfully, trust me")]) == .unknown)
check("legacy sent wording is not proof of delivery", state([row("sms_sent")]) == .unknown)
print("Reply text delivery policy: \(failures) failures")
exit(failures == 0 ? 0 : 1)
