import Foundation

/// Delivery facts, not an interpretation of the reply. Missing metadata is
/// unknown; a saved app reply by itself never proves that a text was sent.
enum ReplyTextDeliveryPolicy {
    struct Metadata: Decodable, Equatable {
        let id: String
        let kind: String
        let decision: String?
        let goal: String?
        let owner_ref: String?
        let external_event_id: String?
        let created: String
        let updated: String?
        var text: String? = nil
    }

    enum State: Equatable {
        case unknown, queued, accepted, delivered, unconfirmed, failed, notSent

        var caption: String? {
            switch self {
            case .unknown: return nil
            case .queued: return "Text queued"
            case .accepted: return "Text delivery pending"
            case .delivered: return "Text delivered"
            case .unconfirmed: return "Text not confirmed · reply is saved here"
            case .failed: return "Text delivery failed · reply is saved here"
            case .notSent: return "Text not sent · reply is saved here"
            }
        }

        var symbol: String {
            switch self {
            case .queued, .accepted: return "clock"
            case .delivered: return "checkmark.message"
            case .unconfirmed, .failed, .notSent: return "exclamationmark.bubble"
            case .unknown: return "questionmark.bubble"
            }
        }
    }

    static func state(messageID: String, owner: String, rows: [Metadata]) -> State {
        guard !messageID.isEmpty, !owner.isEmpty else { return .unknown }
        let scoped = rows.filter { $0.goal == messageID && $0.owner_ref == owner }
        let attempt = scoped.filter {
            $0.kind == "notification_status" && $0.external_event_id == "reply-sms:\(messageID)"
        }.max { ($0.updated ?? $0.created, $0.id) < ($1.updated ?? $1.created, $1.id) }
        if let attempt { return decode(attempt.decision) }
        let outbox = scoped.filter {
            $0.kind == "reply_outbox" && $0.external_event_id == "reply-outbox:\(messageID)"
        }.max { ($0.updated ?? $0.created, $0.id) < ($1.updated ?? $1.created, $1.id) }
        guard let outbox else { return .unknown }
        return outbox.decision == "reply_pending" ? .queued : decode(outbox.decision)
    }

    private static func decode(_ state: String?) -> State {
        switch state {
        case "sms_delivered": return .delivered
        case "sms_accepted": return .accepted
        case "sms_unconfirmed", "sms_attempted": return .unconfirmed
        case "sms_failed": return .failed
        case "sms_skipped", "sms_mock": return .notSent
        default: return .unknown
        }
    }

    struct TaskCaption: Equatable {
        let title: String
        let detail: String
        let icon: String
    }

    static func taskCaption(jobID: String, version: Int, status: String,
                            question: String, owner: String, rows: [Metadata]) -> TaskCaption? {
        guard !owner.isEmpty, !jobID.isEmpty else { return nil }
        let matching = rows.filter { row in
            guard row.owner_ref == owner, let text = row.text,
                  let meta = try? JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any]
            else { return false }
            return meta["purpose"] as? String == "task_question"
                && meta["job_id"] as? String == jobID
                && meta["version"] as? Int == version
                && meta["status"] as? String == status
                && meta["question"] as? String == question
        }
        if let outbox = matching.first(where: { $0.kind == "reply_outbox" }), let messageID = outbox.goal {
            let delivery = state(messageID: messageID, owner: owner, rows: rows)
            if let title = delivery.caption {
                return TaskCaption(title: title, detail: "You can answer this question here or by text.", icon: delivery.symbol)
            }
        }
        guard let latest = matching.filter({ $0.kind == "notification_status" })
            .max(by: { ($0.created, $0.id) < ($1.created, $1.id) }) else { return nil }
        let title: String
        switch latest.decision {
        case "text_daily_limit": title = "Text paused · daily outreach limit"
        case "text_question_limit": title = "Text paused · follow-up limit"
        case "text_quiet_hours": title = "Text paused · quiet hours"
        case "text_conversation_paused": title = "Text paused · conversation in progress"
        case "text_no_phone": title = "Text not sent · phone unavailable"
        case "text_policy_unknown": title = "Text paused · schedule check unavailable"
        default: return nil
        }
        return TaskCaption(title: title, detail: "This question is saved here. You can answer it now.", icon: "pause.circle")
    }
}
