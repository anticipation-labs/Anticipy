import Foundation

/// THE PROOF THE SERVER ITSELF DEMANDED, read back on the phone.
///
/// `backend/pb_hooks/workflow_guard.pb.js` refuses to move ANY job to `done`
/// unless the row's `receipt` column parses and carries `verified: true`, an
/// `effect_key` matching the job's, and a NON-EMPTY `evidence` array. So every
/// done row in the product is, by construction, backed by something checked.
///
/// The app decoded none of it. `AgentJob` stopped at `lane`, and the done card
/// was fed `result` — free text the browser composed about itself — so the one
/// screen whose entire job is to be a receipt showed a sentence instead. A
/// stranger had no way to tell those apart, which is moment 31 of the fifty:
/// "Done without proof doesn't exist."
///
/// -- Why parsing these tags is not a Law-1 violation ----------------------
///
/// HARNESS-LAWS Law 1 forbids a pattern-match deciding what a HUMAN'S WORDS
/// MEAN. Nothing here reads anybody's speech. `evidence` is a wire format this
/// product writes to itself: `extension/agent_loop.js:verificationEvidence`
/// emits `url:…`, `title:…`, `page:…`, `facts:…`, `proof:…`, `journal:…`,
/// `captureMilestone` emits `shot:…`, and `background.js:depositEvidence`
/// returns `evidence:<row id>` for a deposited photograph. Splitting a
/// self-emitted entry on its own tag is deserialization — the same category as
/// reading a timestamp — and it is listed under Law 1's "senses" exemption.
///
/// The guard that keeps it honest is that NOTHING here interprets a value. A
/// tag this file does not know becomes `.other` and is still shown, verbatim,
/// in the order the row holds it. No entry is ever rewritten, summarised or
/// dropped for looking wrong — `JobReceiptPolicy` documents at length why the
/// engine's words are promoted and never edited, and evidence is held to the
/// same rule.
struct JobReceipt: Equatable {

    /// One entry of the proof index, as the row holds it.
    struct Item: Equatable {
        /// The tag the entry was written under. Raw values ARE the wire tags,
        /// so this enum cannot drift from the producer without failing to
        /// match — which degrades to `.other`, never to a wrong label.
        enum Kind: String, Equatable {
            /// `evidence:<row id>` — a photograph deposited in the evidence
            /// collection. The one entry nothing else can reconstruct.
            case evidence
            /// `shot:<milestone>@<url>`, or `shot:<milestone>(none)@<url>`
            /// when the capture failed. "There is no photo of this" is itself
            /// something a person should be able to read off a receipt.
            case shot
            case url
            case title
            case page
            case facts
            case proof
            case journal
            /// Any tag this build does not know, including an entry with no
            /// tag at all. Shown verbatim rather than hidden.
            case other
        }

        let kind: Kind
        /// Everything after the tag. Verbatim, never rewritten.
        let value: String
        /// The entry exactly as the row holds it, tag included.
        let raw: String

        init(raw: String) {
            self.raw = raw
            // FIRST colon only: a `url:` entry is full of them.
            guard let cut = raw.firstIndex(of: ":") else {
                self.kind = .other
                self.value = raw
                return
            }
            let tag = String(raw[raw.startIndex..<cut])
            self.kind = Kind(rawValue: tag) ?? .other
            self.value = String(raw[raw.index(after: cut)...])
        }
    }

    let effectKey: String
    /// The engine's own one-line summary as the receipt recorded it. Kept
    /// because a row can carry a receipt whose `result` column was later
    /// emptied, and a summary the server stored is still better evidence than
    /// nothing at all.
    let summary: String
    let items: [Item]
    let verified: Bool
    let recordedAt: String

    /// Does this receipt meet what the server demanded — verified, with
    /// evidence? Same two conditions as `workflow_guard.pb.js`, deliberately
    /// re-stated here rather than assumed: a row written before that guard
    /// existed can carry a receipt that would not pass it today, and showing
    /// such a row as proven would be the app vouching for something nothing
    /// ever checked.
    ///
    /// The third condition the guard applies — that `effect_key` matches the
    /// job's — needs the job, so it lives in `JobReceiptPolicy` where the job
    /// is in hand.
    var isProof: Bool { verified && !items.isEmpty }

    /// A photograph of the finished page was deposited and can be fetched.
    var photographed: Bool { items.contains { $0.kind == .evidence } }

    /// The page the claim was checked against, if the receipt names one.
    var url: String? { firstValue(.url) }
    var title: String? { firstValue(.title) }

    private func firstValue(_ kind: Item.Kind) -> String? {
        guard let hit = items.first(where: { $0.kind == kind }) else { return nil }
        let trimmed = hit.value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    /// Read the column. Returns nil when there is nothing readable there —
    /// which is a real state, not an error: rows predating the column, rows
    /// that never reached `done`, and the `""` the app itself writes on
    /// approve and cancel all land here.
    ///
    /// Nothing is inferred from a malformed receipt. A phone is not the place
    /// to decide what half a proof means.
    static func parse(_ raw: String?) -> JobReceipt? {
        guard let raw, !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let data = raw.data(using: .utf8),
              let any = try? JSONSerialization.jsonObject(with: data),
              let obj = any as? [String: Any]
        else { return nil }

        // Only genuine strings become entries. The producer writes strings
        // (`workflow_state.js` maps every entry through `String(x).trim()`),
        // and coercing a number or an object into one here would manufacture
        // an entry the server never verified.
        let entries = (obj["evidence"] as? [Any] ?? []).compactMap { $0 as? String }
        let items = entries
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .map(Item.init(raw:))

        return JobReceipt(
            effectKey: obj["effect_key"] as? String ?? "",
            summary: (obj["summary"] as? String ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines),
            items: items,
            // Anything other than a real JSON `true` is not a verification.
            // PocketBase hands back what was stored; a string "true" would be
            // somebody's hand-written row, and this must not vouch for it.
            verified: obj["verified"] as? Bool ?? false,
            recordedAt: obj["recorded_at"] as? String ?? "")
    }
}
