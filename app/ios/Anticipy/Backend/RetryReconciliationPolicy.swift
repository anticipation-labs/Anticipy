import Foundation

/// WHAT THE PHONE MAY SAY ABOUT A SUBMISSION THAT MAY ALREADY HAVE GONE OUT.
/// Audit #90, correction (E).
///
/// A browser worker reclaimed between a consequential click and its receipt
/// leaves the row `effect_uncertain`. The DB guard
/// (`backend/pb_hooks/workflow_guard.pb.js`, the retry leg) then refuses to
/// let that row back to `queued` unless the write carries a `reconciliation`
/// whose `conclusion` is `not_applied`, with evidence behind it. Until
/// 2026-09-05 the phone satisfied that leg with a string literal: the owner
/// tapped Try again, and `approvalFields` wrote conclusion `not_applied`,
/// evidence "owner explicitly checked the destination before retry" and a
/// sentence he never said — whether or not anyone had checked anything. A
/// crash plus a tap re-sent the submission. That is the duplicate booking the
/// Brief's moment 49 names outright.
///
/// Since 2026-09-05 the extension LOOKS (`extension/reconcile.js`): the
/// surviving tab is read once, one question is asked of a model on its own,
/// and the answer is written beside the intent as
/// `params._reconciliation = { verdict, evidence, at }` in four states. This
/// file is the phone's half: it reads that row and decides what a retry may
/// cite. The rule is a FLOOR, the same polarity the extension keeps — a retry
/// needs a POSITIVE `not_applied`. "Applied" refuses because the page showed
/// it went through; "unclear" and "no_verdict" refuse because nobody could say
/// it did not; an absent row refuses because nobody looked at all. The owner's
/// tap is real and is written down as its own line of evidence, but it is
/// never the only line, because a tap is not a check.
///
/// Pure Foundation, like `AnswerRoutePolicy` and `JobReceiptPolicy`: the
/// parse and the floor are exercised by `Tests/run_retry_reconciliation_tests.sh`
/// with `swiftc` alone, and `tests/test_retry_cites_the_reconciliation.py`
/// drives the guard's leg with what this file lets through.
enum RetryReconciliationPolicy {
    /// The four states `extension/reconcile.js` exports, spelled exactly as it
    /// writes them. A raw-value enum rather than string comparisons at the call
    /// site: a spelling the extension never wrote reads as nothing, never as
    /// the nearest one.
    enum Verdict: String, Equatable {
        /// The page positively showed this submission's outcome.
        case applied
        /// The page positively showed it did not go through.
        case notApplied = "not_applied"
        /// The model looked and could not tell — an answer, not an absence.
        case unclear
        /// Nobody answered: no intent, no surviving tab, the wrong host, an
        /// unreadable page, a model down, or a reply that was not a token.
        case noVerdict = "no_verdict"
    }

    /// The row as the extension wrote it.
    struct Row: Equatable {
        let verdict: Verdict
        /// Structural lines — host, the intent's sentence, the page's
        /// url/title/fingerprint, the token. Never page text, never a field.
        /// Cited on the retry VERBATIM, so the reconciliation the guard sees is
        /// the one the extension recorded, not a paraphrase.
        let evidence: [String]
        /// When the extension looked, as it stamped it. Empty when the row did
        /// not say.
        let at: String
    }

    /// What the row says, in three shapes rather than an optional, because
    /// "nobody looked" and "somebody looked and wrote a shape this build
    /// cannot read" are different sentences to the owner and different
    /// findings in the log — and both refuse the retry.
    enum Reading: Equatable {
        /// No `_reconciliation` on the row at all: a crash the extension never
        /// reconciled (a build before 2026-09-05, or a recovery path that
        /// never ran).
        case nothingChecked
        /// The field is there and is not `{verdict, evidence, at}` with a
        /// verdict this build knows. A renamed verdict on the extension side
        /// lands here, which fails closed and is meant to be noticed.
        case unreadable
        case checked(Row)
    }

    /// The params key `extension/workflow_state.js` and `reconcile.js` write.
    static let key = "_reconciliation"

    /// How many evidence lines the extension may write (`reconciliationParams`
    /// caps at 12 of 300 characters); the phone keeps the same bound so the
    /// cited list is the written list, not a longer one somebody appended to.
    static let maxEvidenceLines = 12
    static let maxEvidenceLength = 300

    /// Read the row off the job's parsed `params`.
    static func read(_ params: [String: Any]) -> Reading {
        guard let raw = params[key] else { return .nothingChecked }
        guard let row = raw as? [String: Any],
              let word = row["verdict"] as? String,
              let verdict = Verdict(rawValue: word) else { return .unreadable }
        let evidence = ((row["evidence"] as? [Any]) ?? [])
            .compactMap { $0 as? String }
            .map { String($0.prefix(maxEvidenceLength)) }
            .filter { !$0.isEmpty }
            .prefix(maxEvidenceLines)
        let at = (row["at"] as? String) ?? ""
        return .checked(Row(verdict: verdict, evidence: Array(evidence), at: at))
    }

    /// The evidence a retry may carry, or nil when it may not carry any.
    ///
    /// THE FLOOR. Non-nil only for a row whose verdict is exactly
    /// `not_applied` AND whose evidence is not empty — a verdict with nothing
    /// behind it cannot be cited, and the extension never writes one. The
    /// owner's tap is appended as one line of its own, timestamped: it is real,
    /// and it is what the guard's `owner_words` half is about. It is appended,
    /// never substituted, so the list the guard reads is the extension's list
    /// plus his gesture and never his gesture alone.
    static func retryEvidence(_ reading: Reading, tappedAt: String) -> [String]? {
        guard case .checked(let row) = reading,
              row.verdict == .notApplied,
              !row.evidence.isEmpty else { return nil }
        return row.evidence + ["owner tapped \"I checked, try again\" on the phone at \(tappedAt)"]
    }

    /// Whether the card may offer a retry at all. The same floor as
    /// `retryEvidence`, asked as a Bool so the view and the writer cannot
    /// disagree about it.
    static func mayRetry(_ reading: Reading) -> Bool {
        retryEvidence(reading, tappedAt: "") != nil
    }

    /// What the card says above its buttons, per reading. Six sentences for
    /// six states, because the owner is told different things: what the page
    /// showed, or why nothing could be said. Every sentence that refuses the
    /// retry says what to do instead, and none of them claims the submission
    /// did not go through when nothing showed that.
    static func explanation(_ reading: Reading) -> String {
        switch reading {
        case .nothingChecked:
            return "Nobody has checked whether this went through: I could not look, and a tap is not a check. "
                + "If you looked and it did not happen, tap Not now and ask me again from the start."
        case .unreadable:
            return "The record of what I found is in a shape this version of the app cannot read, so I will not try again from it. "
                + "If you looked and it did not happen, tap Not now and ask me again from the start."
        case .checked(let row):
            switch row.verdict {
            case .applied:
                return "The page showed this already went through, so I am not sending it again. "
                    + "Check the site before deciding anything."
            case .notApplied:
                return "The page showed it did not go through. If you have checked too, I can try again."
            case .unclear:
                return "I looked at the page afterwards and could not tell either way, so I will not try again from here. "
                    + "If you checked and it did not happen, tap Not now and ask me again from the start."
            case .noVerdict:
                return "I could not look at the page after I lost it, so I cannot say it did not go through. "
                    + "If you checked and it did not happen, tap Not now and ask me again from the start."
            }
        }
    }
}
