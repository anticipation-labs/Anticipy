import Foundation

/// Where a typed answer goes — and specifically, when it must go to the brain
/// rather than onto the job.
///
/// docs ex 75 / brief ex 120.
///
/// The card has had an answer box for a while (`HandlingCard`, "Type what I
/// need, or say you handled it"), and Send wrote the answer straight onto the
/// job: status -> queued, authorized -> true. That is a SECOND path to a
/// decision the text lane already owns, and the cost is on the record. On
/// 2026-08-02 two tasks were blocked at once, an answer arrived, and
/// `Conversation._resume_stuck`'s docstring records what happened: it "resumed
/// nothing, and still got met with 'I'll finish the booking now.'" The rule it
/// was fixed to was "only when exactly one thing is blocked", and a card-local
/// write skips that reasoning entirely.
///
/// What the brain does that a job write cannot:
///   - matches the answer against what the task actually said it needed
///     (`_answers_need`), so a partial answer asks for the rest instead of
///     relaunching the run on incomplete information;
///   - keeps what he said about himself as a fact, filed under what it was
///     about, whether or not it was labelled an answer;
///   - decides WHICH blocked task he meant when more than one is waiting.
///
/// So this routes. It does not decide whether SMS or the app is the primary
/// channel — that question is open and this is deliberately silent on it. Both
/// channels arrive at one `on_reply`.
///
/// Pure Foundation on purpose: no SwiftUI, no network, no CoreBluetooth, so it
/// compiles and runs in a second with no simulator (see Tests/run_pendant_tests.sh).
enum AnswerRoutePolicy {

    enum Route: Equatable {
        /// Nothing was typed. The view disables Send for this, but the guard
        /// cannot only live in the view: the old path fell through to writing an
        /// approval whose "owner's exact words" were the empty string, which is
        /// a consent record of nothing.
        case nothingToSend

        /// "skip it", "I already booked it" — the errand is over. Deterministic
        /// and local, on the same cancellation path as "Not now", with his words
        /// kept as the result. Never sent to a model to interpret.
        case endTheErrand(String)

        /// A real answer to a real question. Goes to the brain as one inbound
        /// turn, which resolves the stuck task the same way a text does.
        case toTheBrain(String)

        /// "Say the word" on a ready plan, or continuing after an uncertain
        /// effect. This is CONSENT, not information — invariant 2's approval
        /// belongs on the job, where the browser agent reads it.
        case approval
    }

    /// - Parameters:
    ///   - endsTheErrand: the result of the ending-answer rule, passed in rather
    ///     than recomputed. That rule lives in AnticipyApp.swift and has its own
    ///     runner; a second copy here would be a second answer to "is this over".
    static func route(status: String,
                      workflowState: String? = nil,
                      effectUncertain: Bool,
                      answer: String,
                      endsTheErrand: String?) -> Route {
        let trimmed = answer.trimmingCharacters(in: .whitespacesAndNewlines)

        // Only a task stopped for information takes an answer. `effect_uncertain`
        // is the other thing entirely: she could not tell whether her submit
        // landed, and the tap means "I checked, it did not happen" — an
        // assertion about the world, which the job records.
        let needsDetails = status == "needs_user" || workflowState == "draft"
        guard needsDetails, !effectUncertain else { return .approval }

        if let ending = endsTheErrand { return .endTheErrand(ending) }
        if trimmed.isEmpty { return .nothingToSend }
        return .toTheBrain(trimmed)
    }
}
