import Foundation

/// The model supplies meaning; this policy only checks the verdict and consent.
/// An unavailable judgment cannot open a permission prompt.
enum ContextTrigger {
    struct Verdict: Decodable, Equatable {
        let verdict: String
        var source: String? = nil
        var subject: String? = nil
        var reason: String? = nil
    }

    static func ask(verdict: Verdict, grants: ContextGrants = ContextGrants())
        -> (source: ContextSource, subject: String?)? {
        guard verdict.verdict == "request", let raw = verdict.source,
              let source = ContextSource(rawValue: raw), source.isOnDevice,
              grants.mayAsk(source), let reason = verdict.reason, !reason.isEmpty
        else { return nil }
        return (source, verdict.subject)
    }
}
