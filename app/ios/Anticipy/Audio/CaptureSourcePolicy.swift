import Foundation

/// WHICH EARS heard a line, turned into something a person can read.
///
/// `events.source` has existed since backend/pb_migrations/1700000004_segments.js
/// and for a long time nothing wrote it; then the phone wrote it on every event
/// and nothing read it back. So the one comparison the field exists for — the
/// pendant run of an errand against the phone-mic run of the same errand — was
/// invisible in the app that produced both halves.
///
/// A policy rather than a `switch` inside the view, matching `AnswerRoutePolicy`
/// and `PendantRadioPolicy`: the interesting part is WHICH sources get a badge
/// and which stay silent, and that judgement deserves a test that does not need
/// a simulator to run.
enum CaptureSourcePolicy {
    struct Badge: Equatable {
        /// SF Symbol name.
        let glyph: String
        /// What the person reads.
        let label: String
    }

    /// The wire values the phone stamps (`AnticipySession.LineSource.wireName`).
    static let phone = "phone_mic"
    static let pendant = "pendant"
    static let typed = "typed"

    /// Nil means DRAW NOTHING, and there are three separate reasons for it:
    ///
    /// - `typed`: the person watching knows they typed it. A badge on every
    ///   typed line is noise on the busiest lane in the feed, and it labels the
    ///   one case that was never in question.
    /// - unknown/empty: PocketBase sends "" for an unset column, and thousands
    ///   of rows predate anything writing this field. Silence is honest;
    ///   defaulting to "Phone" would be a lie about a measurement, and it would
    ///   quietly pollute the very comparison this badge exists to serve.
    /// - an unrecognised value: a future third microphone must show up as
    ///   nothing rather than being mislabelled as one of the two we know.
    static func badge(for source: String?) -> Badge? {
        switch source?.trimmingCharacters(in: .whitespacesAndNewlines) {
        case phone: return Badge(glyph: "iphone", label: "Phone")
        case pendant: return Badge(glyph: "badge.plus.radiowaves.right", label: "Pendant")
        default: return nil
        }
    }

    /// Spoken by VoiceOver. "Heard by Pendant" rather than just "Pendant",
    /// because out of visual context the bare word names nothing.
    static func accessibilityLabel(for badge: Badge) -> String {
        "Heard by \(badge.label)"
    }
}
