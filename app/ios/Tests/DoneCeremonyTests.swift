import Foundation

// HOW AN ERRAND COMING BACK DONE IS ALLOWED TO ARRIVE, walked. Compiled by
// run_done_ceremony_tests.sh against the production policy; this file is that
// suite's main.swift, so it may hold top-level code.

var failures = 0
func check(_ ok: Bool, _ name: String, _ detail: @autoclosure () -> String = "") {
    if ok { print("PASS: \(name)") } else { failures += 1; print("FAIL: \(name) \(detail())") }
}

typealias C = DoneCeremonyPolicy

func decide(_ outcome: C.Outcome = .succeeded, lines: Int = 3,
            reduceMotion: Bool = false, ambient: Bool = true,
            played: Bool = false, onScreen: Bool = false) -> C.Decision {
    C.decide(outcome: outcome, evidenceLines: lines, reduceMotion: reduceMotion,
             ambientMotionOn: ambient, alreadyPlayed: played, ceremonyOnScreen: onScreen)
}

// ================================================ THE FACT OUTRANKS THE THEATRE
// The single rule this file exists to hold. A person waiting to learn whether
// their errand ran may never be made to wait on an animation, so the plan
// COMPRESSES to fit the budget rather than growing past it.
check(C.maximumDelay <= 1.5, "the budget is under a second and a half", "\(C.maximumDelay)")
for n in 0...C.evidenceHardCap {
    let plan = C.plan(revealSteps: n)
    check(plan.total <= C.maximumDelay + 0.0001,
          "\(n) lines still fits the budget", "total \(plan.total)")
}
// The compression is real: more lines means a tighter stagger, never a longer show.
let three = C.plan(revealSteps: 3), twelve = C.plan(revealSteps: 12)
check(twelve.stagger < three.stagger, "twelve lines stagger faster than three",
      "\(twelve.stagger) vs \(three.stagger)")
check(twelve.total <= C.maximumDelay, "and the whole thing still lands inside the budget")
// A receipt bigger than the server can write is clamped rather than trusted.
check(C.plan(revealSteps: 500).revealSteps == C.evidenceHardCap,
      "a receipt past the server's own cap is clamped", "\(C.plan(revealSteps: 500).revealSteps)")
check(C.plan(revealSteps: -4).revealSteps == 0, "and a negative count cannot underflow")

// One line has nothing to stagger against, so its whole ceremony is the breath.
check(C.plan(revealSteps: 1).stagger == 0, "one line gets no stagger")
check(abs(C.plan(revealSteps: 1).total - C.afterglow) < 0.0001,
      "and its total is exactly the afterglow")

// ============================================ THE CEREMONY REACHES ONE ARM ONLY
// DoneCard has three mutually exclusive branches and only one is a completion.
// A failed errand arriving with a reveal sequence would be the product
// performing delight over bad news — and job.safetyLine ("it may already have
// gone out") is the most time-critical sentence in the app.
check(decide(.failed) == .skip(.notACompletion(.failed)),
      "a failure gets no ceremony")
check(decide(.calledOff) == .skip(.notACompletion(.calledOff)),
      "and neither does something called off")
if case .play = decide(.succeeded) {} else { check(false, "only a success gets one") }
check(true, "only a success gets one")

// ================================================================ MOTION IS OFF
// Skipped ENTIRELY rather than degraded: a degraded ceremony is still motion,
// and the app honours the pair `reduceMotion || !ambientMotion` everywhere else.
check(decide(reduceMotion: true) == .skip(.motionIsOff), "Reduce Motion skips it")
check(decide(ambient: false) == .skip(.motionIsOff), "so does the owner's own switch")
check(decide(.failed, reduceMotion: true) == .skip(.motionIsOff),
      "and motion is asked FIRST, so the reason given is the one the owner set")

// ========================================================= ONCE PER JOB, EVER
check(decide(played: true) == .skip(.alreadyHadItsMoment),
      "a job that has had its moment does not get another")
// Six at once is a hostage situation: the rest simply appear.
check(decide(onScreen: true) == .skip(.oneAtATime),
      "only one ceremony runs at a time")

// ==================================================== NOTHING TO REVEAL IS FINE
// Not every done card has proof: the guard skips the receipt file entirely for
// a row with no workflow, so a job can legitimately reach done with none.
check(decide(lines: 0) == .skip(.nothingToReveal),
      "a card with no proof rows still shows, it just has no sequence")
check(decide(lines: -1) == .skip(.nothingToReveal), "and a nonsense count is the same")

// ========================================================== THE BREATHING RATE
// A job running and a device listening are the same fact wearing two faces, so
// they breathe at one rate rather than two.
check(abs(C.breathPeriod - 2.99) < 0.001, "the pulse is the pendant's own period")
check(abs(C.breathOmega - 2.0 * Double.pi / 2.99) < 0.0001,
      "and omega is derived from it rather than written twice", "\(C.breathOmega)")
check(abs(C.breathOmega - 2.1) < 0.01,
      "which lands on the same 2.1 the pendant's own view uses", "\(C.breathOmega)")

check(C.breathes(status: "running"), "a running job breathes")
check(!C.breathes(status: "queued"),
      "a queued one does NOT — a pulse over it would claim activity we cannot see")
for status in ["done", "failed", "cancelled", "awaiting_confirm", ""] {
    check(!C.breathes(status: status), "nothing else breathes", status)
}

// ====================================================== NOTHING HERE IS A WORD
// The compatibility proof with run_insights_tests.sh: this policy emits TIMINGS.
// Every string it can produce is a diagnostic, and none of them applauds.
let sayings = [C.words(decide()), C.words(decide(.failed)), C.words(decide(.calledOff)),
               C.words(decide(reduceMotion: true)), C.words(decide(played: true)),
               C.words(decide(onScreen: true)), C.words(decide(lines: 0))]
for said in sayings {
    check(!said.isEmpty, "every decision can be printed", said)
    let lower = said.lowercased()
    for banned in ["congratulat", "well done", "keep it up", "nice work", "great job", "!"] {
        check(!lower.contains(banned), "and none of them applauds", "\(said) contains \(banned)")
    }
}

print(failures == 0 ? "\nAll done-ceremony checks passed."
                    : "\n\(failures) done-ceremony check(s) failed.")
exit(failures == 0 ? 0 : 1)
