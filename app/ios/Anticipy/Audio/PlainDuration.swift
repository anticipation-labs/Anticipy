import Foundation

/// How long something lasted, in units a person reads — from one place, so
/// three screens cannot word the same seconds differently.
///
/// WHERE IT CAME FROM, 2026-08-26. This is `duration(_:)`, lifted verbatim out
/// of `ListeningDiagnosticsView` where it was private. The diagnostics screen
/// is about to stop being the only screen that reports a stretch of silence:
/// the listening row in Settings and the home card both want to say how long
/// the phone has heard nothing, off the same `ListenTally.unheardForSeconds`.
/// Three copies of six lines of arithmetic is how "6 hr 20 min" here becomes
/// "6.3 hours" there and "over 6 hours" on the third screen, and at that point
/// the reader is comparing three different claims about one measurement.
///
/// IT NAMES A MAGNITUDE AND STOPS. No threshold decides that a number is worth
/// mentioning, no adjective decides it is bad, and nothing here has a colour to
/// give it — for any positive number of seconds the answer starts with a digit
/// and ends with its unit. That is `ListeningDiagnosticsView.swift:38-43`
/// written as a type: "a phone that has heard nothing for eleven hours and a
/// phone that has heard nothing for four minutes both say so, and the reader
/// judges." Thirty deaf hours reads "30 hr" — no day unit arrives to soften it,
/// and no rule turns it into "too long". The whole no-verdict argument on that
/// screen rests on the same seconds reading the same way everywhere, which is
/// why this is one type and not a convention.
///
/// PURE FOUNDATION, and that is the point of it being here beside
/// `ListenControlPolicy` rather than in `Theme`. Wording is not a look; a
/// formatter that can reach for a `Color` is a formatter that will eventually
/// return a red one. `run_duration_tests.sh` compiles this file against
/// Foundation alone and refuses a SwiftUI import, so it cannot.
///
/// IT TRUNCATES, NEVER ROUNDS. The number shown is never larger than what the
/// phone measured, and is short of it by less than a minute — 7859 seconds
/// reads "2 hr 10 min". Both halves matter on a screen whose job is a deaf
/// morning: rounding up would invent silence nobody had, and rounding down by
/// more than the unit it names is the reassuring wrong number `ListenTally`'s
/// own comments were written against.
///
/// "1 seconds" is what shipped and what still ships. The lift kept every string
/// byte-identical on purpose — two other screens are being built against these
/// exact words this week, and a grammar fix smuggled in under a refactor is a
/// copy change nobody reviewed. It is now one line in one file when somebody
/// wants to make that call.
enum PlainDuration {
    /// Units a person reads, never raw seconds. "3570" is not an answer to
    /// "how long did it hear nothing".
    ///
    /// Zero and below is "none" rather than "0 seconds": the question was how
    /// long, and none is the answer to it. A negative can only be a clock that
    /// moved backwards, and there is no honest duration to report from that.
    static func words(_ seconds: Int) -> String {
        if seconds <= 0 { return "none" }
        if seconds < 60 { return "\(seconds) seconds" }
        let minutes = seconds / 60
        if minutes < 60 { return "\(minutes) min" }
        let hours = minutes / 60
        let rest = minutes % 60
        return rest == 0 ? "\(hours) hr" : "\(hours) hr \(rest) min"
    }
}
