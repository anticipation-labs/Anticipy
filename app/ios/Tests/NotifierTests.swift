import Foundation

// The app had no notification capability at all, so a booking waiting on an OK
// reached its owner only if they happened to open it. These pin the rules that
// stop the new organ becoming the next thing they mute.

var failures = 0
func check(_ name: String, _ ok: Bool, _ detail: String = "") {
    print("\(ok ? "PASS" : "FAIL"): \(name)\(ok || detail.isEmpty ? "" : "  -> \(detail)")")
    if !ok { failures += 1 }
}

// Mirrors Notifier's pure logic.
struct Job { let id: String; let goal: String; let status: String; let result: String? }
let quietStartHour = 22, quietEndHour = 8

func isWaitingOnOwner(_ j: Job) -> Bool {
    j.status == "awaiting_confirm" || j.status == "needs_user"
}
func inQuietHours(_ hour: Int) -> Bool { hour >= quietStartHour || hour < quietEndHour }

func words(for job: Job) -> (String, String) {
    let goal = job.goal.trimmingCharacters(in: .whitespacesAndNewlines)
    let shortGoal = goal.count > 60 ? String(goal.prefix(57)) + "…" : goal
    if job.status == "awaiting_confirm" {
        return ("Ready when you are", shortGoal.isEmpty
                ? "Something's ready for your OK."
                : "\(shortGoal) — say the word and I'll do it.")
    }
    let asked = (job.result ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    let question = asked.isEmpty ? shortGoal : asked
    let trimmed = question.count > 140 ? String(question.prefix(137)) + "…" : question
    return ("I need you for a second", trimmed)
}

// --- only genuine blocks earn the screen ---------------------------------
check("a job waiting for his OK notifies",
      isWaitingOnOwner(Job(id: "1", goal: "book Earls", status: "awaiting_confirm", result: nil)))
check("a job parked on a question notifies",
      isWaitingOnOwner(Job(id: "2", goal: "apply", status: "needs_user", result: "what's your email?")))
for quiet in ["running", "queued", "done", "failed", "cancelled"] {
    check("\(quiet) does NOT notify",
          !isWaitingOnOwner(Job(id: "3", goal: "x", status: quiet, result: nil)))
}

// --- the words are worth unlocking for -----------------------------------
let ok = words(for: Job(id: "1", goal: "book a table at Earls Thursday 7pm for four",
                        status: "awaiting_confirm", result: nil))
check("an approval names the errand, not the app", ok.1.contains("Earls"), ok.1)
check("an approval says what to do", ok.1.contains("say the word"), ok.1)

let q = words(for: Job(id: "2", goal: "apply to Greenhouse", status: "needs_user",
                       result: "A 6-digit code just went to your email to finish this."))
check("a question shows the QUESTION, not the status", q.1.contains("6-digit code"), q.1)
check("a question never shows a status word",
      !q.1.contains("needs_user") && !q.0.contains("needs_user"), "\(q.0) / \(q.1)")

let bare = words(for: Job(id: "3", goal: "renew passport", status: "needs_user", result: ""))
check("with no question recorded it falls back to the errand, not a status",
      bare.1.contains("passport"), bare.1)

let empty = words(for: Job(id: "4", goal: "", status: "awaiting_confirm", result: nil))
check("an empty goal never produces a blank notification", !empty.1.isEmpty, empty.1)

let long = words(for: Job(id: "5", goal: String(repeating: "a", count: 200),
                          status: "awaiting_confirm", result: nil))
check("a huge goal is trimmed for a lock screen", long.1.count < 120, "\(long.1.count) chars")

// --- not in the middle of the night --------------------------------------
check("2am is quiet", inQuietHours(2))
check("11pm is quiet", inQuietHours(23))
check("7am is still quiet", inQuietHours(7))
check("8am is not", !inQuietHours(8))
check("2pm is not", !inQuietHours(14))

if failures > 0 { print("NotifierTests: \(failures) failed"); exit(1) }
print("NotifierTests: all passed")
