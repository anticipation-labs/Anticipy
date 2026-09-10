import Foundation

struct FixtureEvent {
    let id: String
    let text: String?
    let external_event_id: String?
    var kind = "transcript"
    var decision: String? = nil
    var goal: String? = nil
    var speaker: String? = nil
    var segment: String? = nil
    var created = "2026-09-09 12:00:00Z"
    var source: String? = "typed"
}
enum Haptics {
    static var engagements = 0
    static func engage() { engagements += 1 }
}
final class EchoHarness {
    var transcript: [TranscriptLine] = []
    var sessionLines: [SessionLine] = []
}
private var checks = 0
private var failures = 0
private func check(_ name: String, _ ok: Bool) {
    checks += 1
    if !ok { failures += 1 }
    print("\(ok ? "PASS" : "FAIL"): \(name)")
}
@main struct TranscriptEchoIdentityTests {
    static func main() {
        let localID = "local-transcript-owner-new"
        let h = EchoHarness()
        h.transcript = [TranscriptLine(id: localID, text: "Same words", decision: nil)]
        h.sessionLines = [SessionLine(text: "Same words")]
        h.reconcile([FixtureEvent(id: "older-row", text: "Same words",
                                  external_event_id: "transcript-owner-old", decision: "act")])
        check("older identical text cannot hide a new pending local echo", h.transcript.contains { $0.id == localID })
        check("text alone cannot mark a local session line received", !h.sessionLines[0].received)
        check("text alone cannot borrow an older decision", h.sessionLines[0].decision == nil)
        let missing = EchoHarness()
        missing.transcript = [TranscriptLine(id: localID, text: "Same words", decision: nil)]
        missing.reconcile([FixtureEvent(id: "legacy-row", text: "Same words", external_event_id: nil)])
        check("legacy row without an identity cannot acknowledge new input", missing.transcript.contains { $0.id == localID })
        for invalid in [nil, ""] as [String?] {
            let noIdentity = EchoHarness()
            noIdentity.transcript = [TranscriptLine(id: localID, text: "Same words", decision: nil)]
            noIdentity.sessionLines = [SessionLine(text: "Same words", externalEventID: "transcript-owner-new")]
            noIdentity.reconcile([FixtureEvent(id: "unknown", text: "Same words", external_event_id: invalid)])
            check("absent/empty server identity preserves pending echo", noIdentity.transcript.contains { $0.id == localID })
            check("absent/empty server identity never confirms the session line", !noIdentity.sessionLines[0].received)
        }
        let repeated = EchoHarness()
        repeated.transcript = [
            TranscriptLine(id: "local-first", text: "Same words", decision: nil),
            TranscriptLine(id: "local-second", text: "Same words", decision: nil)]
        repeated.sessionLines = [SessionLine(text: "Same words", externalEventID: "first"),
                                 SessionLine(text: "Same words", externalEventID: "second")]
        let second = FixtureEvent(id: "second-row", text: "Same words", external_event_id: "second", decision: "ignore")
        repeated.reconcile([second])
        check("out-of-order receipt removes only its own echo", Set(repeated.transcript.map(\.id)) == ["local-first", "second-row"])
        check("out-of-order receipt acknowledges only its own session line", !repeated.sessionLines[0].received && repeated.sessionLines[1].received)
        check("out-of-order verdict belongs to the same identity", repeated.sessionLines[0].decision == nil && repeated.sessionLines[1].decision == "ignore")
        let first = FixtureEvent(id: "first-row", text: "Normalized words", external_event_id: "first", decision: "act")
        repeated.reconcile([second, first])
        check("exact identity acknowledges even when server text differs", repeated.sessionLines.allSatisfy(\.received))
        check("both acknowledged echoes are replaced by their exact server rows", Set(repeated.transcript.map(\.id)) == ["first-row", "second-row"])
        let stable = repeated.transcript
        repeated.reconcile([second, first])
        check("repeated identical refresh is stable", repeated.transcript == stable)
        let wrongKind = EchoHarness()
        wrongKind.transcript = [TranscriptLine(id: localID, text: "Same words", decision: nil)]
        wrongKind.reconcile([FixtureEvent(id: "answer", text: "Same words", external_event_id: "transcript-owner-new", kind: "anticipy_text")])
        check("a reply event cannot acknowledge a transcript", wrongKind.transcript.map(\.id) == [localID])

        let progressing = EchoHarness()
        progressing.sessionLines = [SessionLine(text: "a pending message", externalEventID: "progressing")]
        Haptics.engagements = 0
        for decision in ["reply_processing", "reply_error_pending", "act"] {
            progressing.reconcile([FixtureEvent(id: "progressing-row", text: "a pending message",
                external_event_id: "progressing", decision: decision)])
            check("the same receipt advances its diagnostic decision to \(decision)",
                  progressing.sessionLines[0].decision == decision)
        }
        check("a later action produces its first haptic", Haptics.engagements == 1)
        progressing.reconcile([FixtureEvent(id: "progressing-row", text: "a pending message",
            external_event_id: "progressing", decision: "act")])
        check("unchanged action refresh does not repeat the haptic", Haptics.engagements == 1)
        progressing.reconcile([FixtureEvent(id: "progressing-row", text: "a pending message",
            external_event_id: "progressing", decision: nil)])
        check("an absent verdict does not erase a known decision", progressing.sessionLines[0].decision == "act")
        progressing.reconcile([FixtureEvent(id: "other-row", text: "a pending message",
            external_event_id: "other-identity", decision: "unavailable")])
        check("another identity cannot replace the diagnostic decision", progressing.sessionLines[0].decision == "act")
        print("Transcript echo identity: \(checks) checks, \(failures) failures")
        if failures > 0 { exit(1) }
    }
}
