// The interview: a conversation, not a survey, and a skip that records nothing.
//
// `design/briefs/08-day-zero.md:29-30` fixes both rules, and both are the kind
// that fail silently. A survey still "works" — it just stops feeling like
// meeting a person. And a skip stored as an empty fact still "works" — it just
// means the absence of an answer became information about somebody.
//
// Run: sh app/ios/Tests/run_interview_tests.sh

import Foundation

var failures = 0
func check(_ ok: Bool, _ what: String) {
    if ok { print("PASS: \(what)") } else { failures += 1; print("FAIL: \(what)") }
}

func freshProgress() -> InterviewProgress {
    let suite = "interview.tests.\(UUID().uuidString)"
    return InterviewProgress(defaults: UserDefaults(suiteName: suite)!)
}

// ------------------------------------------------------- 0: the script itself
let script = InterviewQuestion.script
check(script.count == 6, "six questions: the roadmap's five plus the tools question")

// The roadmap names five (§8:167-171). Each must actually be present, because
// this list is the deliverable that brief 08 has been waiting on.
for required in ["people", "work", "offlimits", "reach", "coming"] {
    check(script.contains { $0.id == required },
          "the roadmap's \"\(required)\" question is in the script")
}
// And the one no scrape can answer, which is why it is asked rather than read.
check(script.contains { $0.id == "tools" },
      "she asks which tools you live in — an inbox shows accounts, not habits")

check(Set(script.map(\.id)).count == script.count, "no duplicate question ids")

// ------------------------------------------------- 1: it sounds like a person
for q in script {
    check(q.asks.hasSuffix("?"), "\(q.id): it is a question")
    check(q.asks.filter { $0 == "?" }.count == 1, "\(q.id): exactly one question at a time")
    // The voice law: short like a friend. A question long enough to need a
    // comma splice is a form field with a question mark on the end.
    check(q.asks.count <= 60, "\(q.id): short enough to be spoken (\(q.asks.count) chars)")
    check(!q.why.isEmpty, "\(q.id): says why she wants it")
    check(!q.hint.isEmpty, "\(q.id): the field is never a blank stare")
    // Corporate filler is banned outright by CLAUDE-ONBOARDING.md:27-33.
    for banned in ["Just checking in", "In order to", "Please provide", "We value"] {
        check(!q.asks.contains(banned) && !q.why.contains(banned),
              "\(q.id): no corporate filler (\(banned))")
    }
}

// ------------------------------------------- 2: answers become her own words
do {
    let work = script.first { $0.id == "work" }!
    let fact = work.fact("I run product at a design studio")
    check(fact.contains("I run product at a design studio"),
          "the answer survives into the fact verbatim")
    check(fact.hasPrefix("What they do"),
          "the fact is phrased about THEM, matching seed_profile_identity's wording")
    check(fact.hasSuffix("."), "a fact is a sentence")
}

// -------------------------------------- 3: a boundary outranks everything else
do {
    let offlimits = script.first { $0.id == "offlimits" }!
    check(offlimits.importance == 5,
          "\"never touch\" is importance 5 — recall is ranked, and this is the one "
          + "fact that must never be the one that fell off the end")
    for q in script {
        check((4...5).contains(q.importance), "\(q.id): importance is 4 or 5, per brief 08")
    }
}

// ------------------------------------------------- 4: a skip records NOTHING
do {
    let p = freshProgress()
    check(p.remaining.count == 6, "nothing answered on a fresh install")
    check(p.answeredCount == 0, "and nothing counted")
    check(!p.isComplete, "and it is not complete")
    // Skipping is simply not answering. There is no API to record a skip, which
    // is the point: it cannot become a fact even by accident.
    check(p.remaining.count == 6, "skipping leaves the question open, storing nothing")
}

// ------------------------------------------------ 5: answering is remembered
do {
    let p = freshProgress()
    p.markAnswered("work")
    check(p.isAnswered("work"), "an answered question is remembered")
    check(!p.isAnswered("people"), "and only that one")
    check(p.answeredCount == 1, "the count moves")
    check(p.remaining.count == 5, "and it drops out of what is still asked")
    check(!p.remaining.contains { $0.id == "work" }, "she does not ask it twice")
}

// ----------------------------------------------------- 6: it can be finished
do {
    let p = freshProgress()
    for q in script { p.markAnswered(q.id) }
    check(p.isComplete, "answering everything completes it")
    check(p.remaining.isEmpty, "with nothing left to ask")
    check(p.answeredCount == 6, "and all six counted")
}

// ------------------------------------------------------- 7: order is stable
// The queue is captured once on appear; if `remaining` reordered between reads
// the questions would shuffle under somebody mid-conversation.
do {
    let a = freshProgress().remaining.map(\.id)
    let b = freshProgress().remaining.map(\.id)
    check(a == b, "the question order is deterministic")
    check(a == script.map(\.id), "and it is the script's own order")
}

print(failures == 0 ? "interview tests: all passed" : "interview tests: \(failures) FAILED")
exit(failures == 0 ? 0 : 1)
