import Foundation

var failures = 0
func check(_ name: String, _ ok: Bool, _ detail: String = "") {
    print("\(ok ? "PASS" : "FAIL"): \(name)\(ok || detail.isEmpty ? "" : "  -> \(detail)")")
    if !ok { failures += 1 }
}

let a1 = AppReplyWritePolicy.pending(accountID: "account-A", eventID: "question-1")!
let a1Again = AppReplyWritePolicy.pending(accountID: "account-A", eventID: "question-1")!
let a2 = AppReplyWritePolicy.pending(accountID: "account-A", eventID: "question-2")!
let b1 = AppReplyWritePolicy.pending(accountID: "account-B", eventID: "question-1")!

check("the same account/question has one stable client id",
      a1.externalEventID == a1Again.externalEventID, a1.externalEventID)
check("another question cannot collide", a1.externalEventID != a2.externalEventID)
check("another account cannot collide", a1.externalEventID != b1.externalEventID)
check("empty identity cannot mint a durable reply",
      AppReplyWritePolicy.pending(accountID: "", eventID: "question-1") == nil)

check("committed response loss reconciles as accepted",
      AppReplyWritePolicy.reconcile(.present) == .accepted)
check("a proven-absent reply becomes safe to retry",
      AppReplyWritePolicy.reconcile(.absent) == .safeToRetry)
check("an unreadable canonical result stays unverified",
      AppReplyWritePolicy.reconcile(.unknown) == .unverified)
check("a server-side validation refusal is a verified refusal",
      ActionWritePolicy.isVerifiedRefusal(status: 422))
check("transport timeout is not called a refusal",
      !ActionWritePolicy.isVerifiedRefusal(status: 408))

let stored = AppReplyWritePolicy.upserting(a1, in: [])
let replaced = AppReplyWritePolicy.upserting(a1Again, in: stored)
check("persisting the same pending reply is idempotent", replaced == [a1])
let mixed = AppReplyWritePolicy.upserting(b1, in: replaced)
check("restart restores only account A's unknown card",
      AppReplyWritePolicy.eventIDsToRestore(accountID: "account-A", from: mixed)
        == Set(["question-1"]))
check("account B cannot inherit account A's unknown card",
      AppReplyWritePolicy.eventIDsToRestore(accountID: "account-B", from: mixed)
        == Set(["question-1"]) && mixed.filter { $0.accountID == "account-B" } == [b1])

let encoded = try! JSONEncoder().encode(mixed)
let afterRestart = try! JSONDecoder().decode(
    [AppReplyWritePolicy.Pending].self, from: encoded)
check("unknown identity survives a real encode/decode restart", afterRestart == mixed)
check("accepted reconciliation removes the persisted unknown identity",
      AppReplyWritePolicy.removing(a1, from: afterRestart) == [b1])

if failures > 0 {
    print("AppReplyWriteTests: \(failures) failed")
    exit(1)
}
print("AppReplyWriteTests: all passed")
