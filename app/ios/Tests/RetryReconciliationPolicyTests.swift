// After a crash, the phone cites what the extension found — never a constant.
//
// Audit #90, correction (E). Until 2026-09-05 `approvalFields` turned the
// owner's Try again into conclusion "not_applied" and evidence "owner
// explicitly checked the destination before retry" for every uncertain row,
// which is exactly what the DB guard's retry leg reads. The extension now
// writes `params._reconciliation = {verdict, evidence, at}` in four states,
// and this policy is the phone's floor over it.
//
// Three legs:
//   1. THE PARSE   the four verdicts read as themselves, and every other shape
//                  — absent, decorated, uppercase, a near-miss, not a dict —
//                  reads as nothing-checked or unreadable, never as a verdict
//   2. THE FLOOR   evidence is handed out only for a positive not_applied with
//                  something behind it, and it is the row's list plus the tap
//   3. THE WORDS   six states, six sentences; no refusing sentence claims the
//                  submission did not go through
//
// The mutation that turns leg 2 red: map `.unclear`, `.noVerdict` or an absent
// row to a retry (the pre-fix behaviour, where the tap alone was enough).
//
// Run: sh app/ios/Tests/run_retry_reconciliation_tests.sh
import Foundation

// Compiled against the REAL production source by the runner — the policy is
// pure Foundation, so there is no copy of it to drift.
var failures = 0
func check(_ name: String, _ ok: Bool) {
    print("\(ok ? "PASS" : "FAIL"): \(name)")
    if !ok { failures += 1 }
}

typealias P = RetryReconciliationPolicy

/// The row exactly as `extension/reconcile.js` `reconciliationParams` writes
/// it: a verdict token, a short structural evidence list, an ISO stamp.
func row(_ verdict: String, evidence: [Any]? = nil,
         at: Any? = "2026-09-05T18:02:11.000Z") -> [String: Any] {
    let list: [Any] = evidence
        ?? ["host:fixture.test", "control:Clicking Book table on fixture.test", "verdict:\(verdict)"]
    var r: [String: Any] = ["verdict": verdict, "evidence": list]
    if let at { r["at"] = at }
    return ["_workflow": ["plan_id": "wf-1"], "_reconciliation": r]
}

// ================================================================ 1. THE PARSE
for (word, expected) in [("applied", P.Verdict.applied), ("not_applied", .notApplied),
                         ("unclear", .unclear), ("no_verdict", .noVerdict)] {
    if case .checked(let r) = P.read(row(word)) {
        check("\"\(word)\" reads as itself", r.verdict == expected)
        check("\"\(word)\" carries the row's evidence verbatim",
              r.evidence == ["host:fixture.test", "control:Clicking Book table on fixture.test", "verdict:\(word)"])
        check("\"\(word)\" carries when the page was read", r.at == "2026-09-05T18:02:11.000Z")
    } else {
        check("\"\(word)\" reads as a checked row", false)
    }
}

check("no _reconciliation at all is nothing-checked, not unreadable",
      P.read(["_workflow": ["plan_id": "wf-1"]]) == .nothingChecked)
check("empty params are nothing-checked", P.read([:]) == .nothingChecked)

// A token WE specified, compared whole. The extension's own reader treats
// "APPLIED — I think" as no verdict; the phone must not be looser than the
// thing that wrote the row.
for near in ["NOT_APPLIED", "Not_Applied", "not applied", "not_applied ", "notapplied",
             "not_applied — I think", "applied\n", "", "no verdict", "unclear?"] {
    check("\"\(near.replacingOccurrences(of: "\n", with: "\\n"))\" is unreadable, not the nearest verdict",
          P.read(row(near)) == .unreadable)
}
check("a verdict that is not a string is unreadable",
      P.read(["_reconciliation": ["verdict": 1, "evidence": ["x"]]]) == .unreadable)
check("a row with no verdict is unreadable",
      P.read(["_reconciliation": ["evidence": ["x"], "at": "y"]]) == .unreadable)
check("a _reconciliation that is not a dictionary is unreadable",
      P.read(["_reconciliation": "not_applied"]) == .unreadable
          && P.read(["_reconciliation": ["not_applied"]]) == .unreadable
          && P.read(["_reconciliation": NSNull()]) == .unreadable)

if case .checked(let r) = P.read(row("not_applied", evidence: ["host:a", 7, NSNull(), "", "  "], at: nil)) {
    check("non-string evidence entries are dropped, blanks are dropped",
          r.evidence == ["host:a", "  "] || r.evidence == ["host:a"])
    check("a missing stamp reads as empty rather than failing the row", r.at == "")
} else {
    check("a row with odd evidence entries still reads", false)
}

let long = String(repeating: "x", count: 1_000)
if case .checked(let r) = P.read(row("not_applied", evidence: Array(repeating: long, count: 40))) {
    check("evidence is bounded the way the extension bounds it (12 lines of 300)",
          r.evidence.count == P.maxEvidenceLines
              && r.evidence.allSatisfy { $0.count == P.maxEvidenceLength })
} else {
    check("a long evidence list still reads", false)
}

// ================================================================ 2. THE FLOOR
let now = "2026-09-05T18:10:00Z"
if let cited = P.retryEvidence(P.read(row("not_applied")), tappedAt: now) {
    check("not_applied hands out the row's evidence first, verbatim",
          Array(cited.prefix(3)) == ["host:fixture.test", "control:Clicking Book table on fixture.test", "verdict:not_applied"])
    check("and the owner's tap as its own last line, stamped",
          cited.count == 4 && cited.last?.contains("tapped") == true && cited.last?.contains(now) == true)
    check("the tap is never the only line", cited.count > 1)
} else {
    check("a positive not_applied may be retried", false)
}
check("mayRetry agrees with retryEvidence on not_applied",
      P.mayRetry(P.read(row("not_applied"))))

// THE PRE-FIX BEHAVIOUR, and the mutation this leg exists to catch: the tap
// alone used to be enough. Every state but a positive not_applied refuses.
for word in ["applied", "unclear", "no_verdict"] {
    check("\"\(word)\" hands out no evidence — a retry would be a claim nothing showed",
          P.retryEvidence(P.read(row(word)), tappedAt: now) == nil)
    check("\"\(word)\" may not be retried", !P.mayRetry(P.read(row(word))))
}
check("nothing checked hands out no evidence", P.retryEvidence(.nothingChecked, tappedAt: now) == nil)
check("nothing checked may not be retried", !P.mayRetry(.nothingChecked))
check("an unreadable row hands out no evidence", P.retryEvidence(.unreadable, tappedAt: now) == nil)
check("an unreadable row may not be retried", !P.mayRetry(.unreadable))
// A verdict with nothing behind it cannot be cited. The extension never
// writes one; a row that says not_applied with an empty list is a row this
// phone did not understand, and the guard would refuse an empty list anyway.
check("not_applied with no evidence behind it may not be retried",
      P.retryEvidence(P.read(row("not_applied", evidence: [])), tappedAt: now) == nil
          && !P.mayRetry(P.read(row("not_applied", evidence: []))))
check("not_applied whose evidence is only non-strings may not be retried",
      P.retryEvidence(P.read(row("not_applied", evidence: [1, 2])), tappedAt: now) == nil)

// ================================================================ 3. THE WORDS
let readings: [P.Reading] = [.nothingChecked, .unreadable] + ["applied", "not_applied", "unclear", "no_verdict"].map { P.read(row($0)) }
let sentences = readings.map(P.explanation)
check("six states are six different sentences", Set(sentences).count == 6)
check("no sentence is empty", sentences.allSatisfy { !$0.isEmpty })
for reading in readings where !P.mayRetry(reading) {
    let said = P.explanation(reading)
    check("a refusing sentence does not claim it did not go through: \(said.prefix(40))…",
          !said.contains("did not go through") || said.contains("cannot say it did not go through"))
    check("a refusing sentence says what to do instead: \(said.prefix(40))…",
          said.contains("Not now") || said.contains("Check the site"))
}
check("applied says it went through and will not be sent again",
      P.explanation(P.read(row("applied"))).contains("went through")
          && P.explanation(P.read(row("applied"))).contains("not sending it again"))
check("not_applied says the page showed it did not go through",
      P.explanation(P.read(row("not_applied"))).contains("did not go through"))
check("nothing checked says a tap is not a check",
      P.explanation(.nothingChecked).contains("a tap is not a check"))

// The four spellings are the extension's. If reconcile.js renames one the phone
// reads every row as unreadable — closed, and silently un-retryable — which the
// Python leg pins against the JS source; this pins the Swift half of it.
check("the verdict spellings are the wire's",
      P.Verdict.applied.rawValue == "applied" && P.Verdict.notApplied.rawValue == "not_applied"
          && P.Verdict.unclear.rawValue == "unclear" && P.Verdict.noVerdict.rawValue == "no_verdict"
          && P.key == "_reconciliation")

if failures > 0 {
    print("RetryReconciliationPolicyTests: \(failures) failed")
    exit(1)
}
print("RetryReconciliationPolicyTests: all passed")
