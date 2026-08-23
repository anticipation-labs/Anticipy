import Foundation

// Where a typed answer goes. Every case below is either a line from the brief's
// examples or a bug that actually shipped.
//
// Plain executable, no XCTest, matching TranscriptCursorTests.swift and
// PendantRadioPolicyTests.swift: this runs in a second with no simulator, no
// signing, no radio and no network.

var failures: [String] = []

func check(_ name: String, _ got: AnswerRoutePolicy.Route,
           _ want: AnswerRoutePolicy.Route) {
    if got == want {
        print("ok \(name)")
    } else {
        failures.append("FAIL \(name)\n     got \(got), want \(want)")
        print("FAIL \(name): got \(got), want \(want)")
    }
}

func route(_ status: String, answer: String, uncertain: Bool = false,
           ending: String? = nil) -> AnswerRoutePolicy.Route {
    AnswerRoutePolicy.route(status: status, effectUncertain: uncertain,
                            answer: answer, endsTheErrand: ending)
}

@main
struct AnswerRoutePolicyTests {
    static func main() {
        runAnswerRoutes()
        print(failures.isEmpty
              ? "\nall answer-route cases hold"
              : "\n\(failures.count) answer-route case(s) came back wrong")
        exit(failures.isEmpty ? 0 : 1)
    }
}

func runAnswerRoutes() {
    // ---- a real answer must reach the brain, not the job --------------------
    // The whole point of ex 75. Writing this onto the job skips whether the answer
    // covers what the task needed, which is the 2026-08-02 two-blocked-tasks bug.
    check("a plain answer to a stuck task goes to the brain",
          route("needs_user", answer: "the 4th at 7pm"),
          .toTheBrain("the 4th at 7pm"))

    check("the answer is trimmed on its way there",
          route("needs_user", answer: "  Omar Ebrahim  "),
          .toTheBrain("Omar Ebrahim"))

    check("a one-word answer still counts as an answer",
          route("needs_user", answer: "4th"),
          .toTheBrain("4th"))

    // ---- consent is a different thing, and stays on the job ----------------
    // invariant 2: an approval authorises an action, and the browser agent reads it
    // off the job. Routing this to the brain would leave the run waiting at the
    // final button for a conversation to happen.
    check("saying the word on a ready plan is an approval",
          route("awaiting_confirm", answer: ""),
          .approval)

    check("an approval is still an approval when he types something too",
          route("awaiting_confirm", answer: "yes go ahead"),
          .approval)

    // `effect_uncertain` means she could not tell whether her submit landed, and the
    // card asks him to go and look. The tap asserts something about the WORLD, and
    // belongs on the job as evidence -- not as a sentence for her to interpret.
    check("continuing after an uncertain effect is not an answer",
          route("needs_user", answer: "it didn't happen", uncertain: true),
          .approval)

    // ---- an answer that ends the errand ends it locally --------------------
    // "skip it, I don't need the batteries anymore" used to requeue the run, which
    // then Bing-searched those words and hit a CAPTCHA (live, 2026-08-14). It must
    // never become an instruction, and never go to a model to be interpreted.
    check("an answer that calls it off ends the errand",
          route("needs_user", answer: "skip it, I don't need the batteries anymore",
                ending: "You called it off: skip it, I don't need the batteries anymore"),
          .endTheErrand("You called it off: skip it, I don't need the batteries anymore"))

    check("ending the errand wins over sending it to the brain",
          route("needs_user", answer: "i already booked it",
                ending: "You handled it yourself: i already booked it"),
          .endTheErrand("You handled it yourself: i already booked it"))

    // ...but only for a task that is actually waiting on him. A ready plan is not
    // ended by the same words; that is the "Not now" button's job.
    check("the ending rule does not fire on an approval card",
          route("awaiting_confirm", answer: "forget it", ending: "You called it off: forget it"),
          .approval)

    // ---- nothing typed is nothing sent -------------------------------------
    // The view disables Send, but a guard that lives only in the view is one
    // refactor from gone. The old path fell through to writing an approval whose
    // "your exact words" was the empty string -- a consent record of nothing.
    check("an empty answer on a stuck task sends nothing",
          route("needs_user", answer: ""),
          .nothingToSend)

    check("whitespace is not an answer either",
          route("needs_user", answer: "   \n  "),
          .nothingToSend)

    // ---- states that are not waiting on him at all -------------------------
    for status in ["queued", "running", "done", "failed", "cancelled"] {
        check("a \(status) job takes no typed answer",
              route(status, answer: "something"),
              .approval)
    }
}
