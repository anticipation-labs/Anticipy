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
}
