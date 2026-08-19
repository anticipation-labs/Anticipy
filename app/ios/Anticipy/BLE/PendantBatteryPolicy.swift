import Foundation

/// When a pendant's battery is worth mentioning, and in what words.
///
/// docs ex 90: "Pendant battery is dying. -> The app says so before it dies - a
/// dead pendant that looks alive is silent data loss."
///
/// The percentage was already on screen, and a percentage is not a warning. A
/// person glancing at "12%" has to know what 12% means for a device they have
/// owned for a week; the app knows, so the app should say. Ex 84 puts it as one
/// of the three questions every screen must answer at a glance: is anything
/// wrong.
///
/// Pure Foundation so it is testable with no radio and no pendant, and the
/// WORDS live here too - not in a View. That is deliberate: the connection
/// state had its copy in two places, and the copy in the second place was the
/// enum's own spelling (ex 83). One source for the sentence, used by every
/// surface that shows it.
///
/// -- On the numbers ------------------------------------------------------
///
/// These are dials, not physics (docs Part 3: "Guardrails are dials, not
/// cages"). 25% is roughly a day of wear on this hardware and 10% is roughly an
/// evening, so the first is "sort it when you're near a cable" and the second is
/// "sort it now or lose words". Omar owns both numbers; nothing about the shape
/// of this file changes if he moves them.
enum PendantBatteryPolicy {
    static let lowAtPercent = 25
    static let criticalAtPercent = 10

    enum Warning: Equatable {
        /// Healthy, or unknown. Both stay quiet - see `warning(percent:)`.
        case none
        /// Getting low. Worth saying calmly, once it is on screen anyway.
        case low
        /// About to die. This is the one the example is about.
        case critical

        /// Plain words, or nil when there is nothing to say. Never a status
        /// word, an id, or a number the person has to interpret (ex 83).
        var plainWords: String? {
            switch self {
            case .none: return nil
            case .low: return "charge it soon"
            case .critical: return "about to die"
            }
        }
    }

    /// - Parameter percent: the level the pendant reported, or nil if it has not
    ///   reported one yet.
    ///
    /// A nil level is silent on purpose. We have not heard a number, so any
    /// warning would be invented - and an invented warning about someone's
    /// hardware is the same class of lie as an invented memory.
    static func warning(percent: Int?) -> Warning {
        guard let percent else { return .none }
        if percent <= criticalAtPercent { return .critical }
        if percent <= lowAtPercent { return .low }
        return .none
    }

    /// The whole string a surface should show for a battery level: the number,
    /// and the warning when there is one. One function so the status pill and
    /// the settings row cannot drift apart.
    ///
    /// Returns nil when there is no level to show, so a caller can omit the row
    /// rather than print "unknown".
    static func detail(percent: Int?) -> String? {
        guard let percent else { return nil }
        guard let words = warning(percent: percent).plainWords else {
            return "\(percent)%"
        }
        return "\(percent)% · \(words)"
    }
}
