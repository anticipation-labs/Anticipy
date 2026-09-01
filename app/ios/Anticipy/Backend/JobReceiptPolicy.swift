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
///
/// -- What `hasReceipt` used to mean, and why that was the bug --------------
///
/// It meant "the result string is not empty". A sentence is not a receipt. The
/// backend has refused to move ANY job to `done` without a receipt carrying
/// `verified: true` and non-empty `evidence` since workflow_guard.pb.js:662 —
/// and the app decoded none of it, so the card led with free text the browser
/// composed ABOUT ITS OWN SUCCESS while the thing that had actually been
/// checked sat unread in the same row. A stranger had no way to tell those
/// apart, which is the entire promise of that card and moment 31 of the fifty:
/// "Done without proof doesn't exist."
///
/// So `hasReceipt` now means what its name says: THE SERVER VERIFIED THIS. The
/// engine's words are still the lead — ex 77 wants the confirmation number
/// first, and ex 126 forbids editing it — but they no longer decide whether the
/// card reads as proven.
enum JobReceiptPolicy {
    struct Card: Equatable {
        /// The prominent line - what the person came to read.
        let lead: String
        /// Quiet context underneath, or nil when the lead is already the goal.
        let context: String?
        /// TRUE ONLY when the row carries the receipt the SERVER verified: the
        /// `verified` flag, non-empty evidence, and — when the row says which
        /// effect it is — a receipt bound to that same effect.
        let hasReceipt: Bool
        /// What was actually checked. Present exactly when `hasReceipt`.
        let proof: Proof?
        /// Said out loud when a row is done and nothing verifiable stands
        /// behind it. nil when there is proof, and nil when the card is
        /// already saying nothing came back — one sentence, not two.
        let unproven: String?
    }

    /// The receipt, in the pieces a card draws. Every value is verbatim from
    /// the row: this type carries evidence, it does not compose prose about it.
    struct Proof: Equatable {
        /// The page the claim was checked against, if the receipt names one.
        let url: String?
        let title: String?
        /// A photograph of the finished page was deposited.
        let photographed: Bool
        /// Every entry, in the order the row holds them, verbatim.
        let items: [String]
        let recordedAt: String?
    }

    /// - Parameters:
    ///   - goal: the human-readable goal, already de-underscored by the caller.
    ///   - result: whatever the engine came back with, verbatim.
    ///   - receipt: the `receipt` column as the row holds it.
    ///   - effectKey: the row's own `effect_key`, so a receipt can be checked
    ///     against the effect it claims to prove. Rows predate that column, so
    ///     nil or empty means "this row does not say" — which is not a
    ///     mismatch, and must not be read as one.
    static func doneCard(goal: String, result: String?, receipt: String? = nil,
                         effectKey: String? = nil) -> Card {
        let said = (result ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let parsed = JobReceipt.parse(receipt)

        // The server binds a receipt to an exact effect (workflow_guard
        // demands `receipt.effect_key === effect`), because a photograph of one
        // action must never be able to vouch for a different one. Re-checked
        // here rather than trusted: this row and this receipt travelled
        // separately to get to the phone.
        let rowEffect = (effectKey ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let boundToThisEffect = rowEffect.isEmpty || parsed?.effectKey == rowEffect

        guard let parsed, parsed.isProof, boundToThisEffect else {
            guard !said.isEmpty else {
                // Named plainly, and the goal stays visible so the person still
                // knows which errand this was.
                return Card(lead: "Marked done, but nothing came back to show for it.",
                            context: goal, hasReceipt: false, proof: nil,
                            unproven: nil)
            }
            // The sentence is still shown — it is what the engine said, and
            // deleting it would lose the only account of what happened. What
            // changes is that it stops wearing a receipt's clothes.
            return Card(lead: said, context: goal, hasReceipt: false, proof: nil,
                        unproven: "I can't show you proof of this one. There's no verified record behind it.")
        }

        // A row can carry a verified receipt and an empty `result` — the two
        // are different columns written by different steps. Falling back to
        // "nothing came back to show for it" beside real evidence would be the
        // card calling its own proof nothing.
        let lead = !said.isEmpty ? said
            : (!parsed.summary.isEmpty ? parsed.summary
               : "Done — and I checked it before saying so.")

        return Card(
            lead: lead, context: goal, hasReceipt: true,
            proof: Proof(url: parsed.url,
                         title: parsed.title,
                         photographed: parsed.photographed,
                         items: parsed.items.map(\.raw),
                         recordedAt: parsed.recordedAt.isEmpty ? nil : parsed.recordedAt),
            unproven: nil)
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
            return "It may already have gone through before it stopped. Worth checking the site before I try again, so you don't end up with two."
        }
        return "Nothing you told me was lost. A fresh attempt starts from the beginning rather than changing this record."
    }
}
