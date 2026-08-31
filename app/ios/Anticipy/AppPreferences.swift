import Foundation

/// User-facing preferences that affect more than one screen.
///
/// Keep the keys and their defaults here so a control in Settings and the
/// runtime behaviour it changes cannot quietly disagree. `UserDefaults.bool`
/// returns false when a key has never been written, so callers that need an
/// on-by-default value must use `bool(forKey:default:)`.
enum AppPreferences {
    static let hapticsKey = "preferences.haptics"
    static let ambientMotionKey = "preferences.ambientMotion"
    static let typedResponsesKey = "preferences.typedResponses"
    static let notificationsKey = "preferences.notifications"
    static let notificationSoundKey = "preferences.notificationSound"
    static let quietScheduleKey = "preferences.quietSchedule"

    static func bool(forKey key: String, default defaultValue: Bool) -> Bool {
        let defaults = UserDefaults.standard
        guard defaults.object(forKey: key) != nil else { return defaultValue }
        return defaults.bool(forKey: key)
    }
}

enum NotificationQuietSchedule: String, CaseIterable {
    case tenToEight
    case elevenToSeven
    case off

    static var current: NotificationQuietSchedule {
        let raw = UserDefaults.standard.string(forKey: AppPreferences.quietScheduleKey)
        return NotificationQuietSchedule(rawValue: raw ?? "") ?? .tenToEight
    }

    var title: String {
        switch self {
        case .tenToEight: return "10 PM to 8 AM"
        case .elevenToSeven: return "11 PM to 7 AM"
        case .off: return "No quiet hours"
        }
    }

    var subtitle: String {
        switch self {
        case .tenToEight: return "Hold non-urgent alerts overnight."
        case .elevenToSeven: return "A shorter overnight window."
        case .off: return "Send alerts as soon as work needs you."
        }
    }

    var hours: (start: Int, end: Int)? {
        switch self {
        case .tenToEight: return (22, 8)
        case .elevenToSeven: return (23, 7)
        case .off: return nil
        }
    }
}
