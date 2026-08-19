import Foundation

/// What a finished card leads with.
///
/// docs ex 77: "A job finishes. -> The done card leads with the result a human
/// wants: 'Booked: Earls West Van · Thu 7:30 · 4 people · conf #R7K2.'"
///
/// The card led with the GOAL - "Book a table for two" - in callout weight, and
/// put the result underneath in grey footnote with a three-line clamp. So the
/// one thing the person opened the app to see, the confirmation number, was the
/// small grey text under the restated question. This decides the order instead.
///
/// -- Why this never rewrites the result ----------------------------------
///
/// It would be easy to parse the result into a tidy "Booked: X · Y · conf #Z"
/// line, and that is exactly what ex 126 forbids: "paraphrase into something she
/// didn't say - a misquote is an invented memory." The words the engine came
/// back with are evidence (ex 44: "Done requires evidence tied to the exact
/// effect"). So this promotes them verbatim and never edits them.
///
/// -- Done with nothing to show for it ------------------------------------
///
/// A job marked done whose result is empty is a claim with no receipt, and ex
/// 106 is blunt about it: "Tempted to say 'done.' Only with the receipt in
/// hand." The old card silently fell back to showing just the goal, which reads
/// as success. It says so now instead.
enum JobReceiptPolicy {
    struct Card: Equatable {
        /// The prominent line - what the person came to read.
        let lead: String
        /// Quiet context underneath, or nil when the lead is already the goal.
        let context: String?
        /// False when the engine returned nothing to show. The card should not
        /// look like an unqualified success.
        let hasReceipt: Bool
    }

    /// - Parameters:
    ///   - goal: the human-readable goal, already de-underscored by the caller.
    ///   - result: whatever the engine came back with, verbatim.
    static func doneCard(goal: String, result: String?) -> Card {
        let receipt = (result ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        guard !receipt.isEmpty else {
            // Named plainly, and the goal stays visible so the person still
            // knows which errand this was.
            return Card(lead: "Marked done, but nothing came back to show for it.",
                        context: goal,
                        hasReceipt: false)
        }
        return Card(lead: receipt, context: goal, hasReceipt: true)
    }

    /// The middle of docs ex 78's three answers: is my stuff safe.
    ///
    /// The failed card answered what happened (`failureLine`) and what to do
    /// next (the retry button) and said nothing at all about this, so someone
    /// reading "I couldn't finish this one" had no way to know whether twenty
    /// minutes of filled form still existed. Part 3 promises "work is never
    /// destroyed", which is worth nothing to a person who cannot tell.
    ///
    /// Two things this deliberately does NOT say:
    ///
    /// - It never claims the next attempt resumes where this one stopped. The
    ///   retry button calls `requestFreshRetry`, and that starts a NEW request -
    ///   the card's own comment says "a terminal attempt stays immutable".
    ///   Promising a resume would be the confident lie of ex 108.
    /// - When the engine could not tell whether the submit landed, it says so.
    ///   Ex 36: saying "nothing was done" there "is the sentence that buys a
    ///   duplicate booking nobody checks for", and ex 50 calls the duplicate
    ///   booking the cardinal sin of the product.
    static func safetyLine(effectUncertain: Bool?) -> String {
        if effectUncertain == true {
            return "It may already have gone through before it stopped — worth checking the site before I try again, so you don't end up with two."
        }
        return "Nothing you told me was lost. A fresh attempt starts from the beginning rather than changing this record."
    }
}
