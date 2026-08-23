// The consent gate for day-zero context, and the limits on what leaves the
// phone. Both are the kind of rule that fails silently: a gate that returns
// true by default reads exactly like a gate that works, right up until it has
// handed somebody's address book to a server.
//
// Run: sh app/ios/Tests/run_context_grant_tests.sh

import Foundation

var failures = 0
func check(_ ok: Bool, _ what: String) {
    if ok { print("PASS: \(what)") } else { failures += 1; print("FAIL: \(what)") }
}

// A clean, isolated defaults domain per case. UserDefaults.standard would leak
// state between assertions and, worse, between this suite and the simulator.
func freshGrants() -> ContextGrants {
    let suite = "context.grant.tests.\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suite)!
    return ContextGrants(defaults: defaults)
}

// ---------------------------------------------------------------- 0: closed
// The default has to be "no". This is the assertion that matters most: every
// other rule here is downstream of the gate starting shut.
for source in ContextSource.allCases {
    let g = freshGrants()
    check(!g.granted(source), "\(source.rawValue): a fresh install has NOT been granted access")
    check(g.mayAsk(source), "\(source.rawValue): a fresh install is allowed to ask once")
}

// ------------------------------------------------------------- 1: one at a time
// Granting one source must never open another. There is deliberately no
// "grant everything" — PREMIUM-FEEL:43-47 requires one toggle per source, and a
// bulk switch is the same thing in disguise.
do {
    let g = freshGrants()
    g.grant(.calendar)
    check(g.granted(.calendar), "granting the calendar grants the calendar")
    check(!g.granted(.contacts), "granting the calendar does NOT grant contacts")
}

// ------------------------------------------------------------ 2: skip is not a no
// A decline stops her asking again, but it must not be permanent — the person
// can still open the door themselves later.
do {
    let g = freshGrants()
    g.decline(.contacts)
    check(!g.granted(.contacts), "declining leaves the source ungranted")
    check(!g.mayAsk(.contacts), "declining stops her asking again unprompted")
    g.grant(.contacts)
    check(g.granted(.contacts), "a later yes still works after a no")
    check(!g.declined(.contacts), "granting clears the earlier decline")
}

// --------------------------------------------------------------- 3: revocable
// Revoking must take effect immediately, and must not re-arm the ask — being
// asked again the moment you switch something off is how a leash reads as a nag.
do {
    let g = freshGrants()
    g.grant(.calendar)
    g.revoke(.calendar)
    check(!g.granted(.calendar), "revoking takes the grant away")
}

// ------------------------------------------------------------ 4: the ask is a question
// One question, and it names the words that provoked it. An ask that cannot
// explain itself is the anti-pattern CONSUMER-READINESS T4 records.
for source in ContextSource.allCases {
    check(source.ask().hasSuffix("?"), "\(source.rawValue): the ask is phrased as a question")
    check(source.ask().filter { $0 == "?" }.count == 1,
          "\(source.rawValue): exactly one question is asked")
    let reason = source.because("dinner with Priya Thursday")
    check(reason.contains("dinner with Priya Thursday"),
          "\(source.rawValue): the reason quotes what was actually heard")
}

// --------------------------------------------------- 5: promises name a refusal
// PREMIUM-FEEL:43-47 requires promising what she will NOT do. A list of only
// capabilities is a data-collection notice wearing a friendly voice.
for source in ContextSource.allCases {
    let promises = source.promises
    check(promises.count >= 3, "\(source.rawValue): enough promises to be worth reading")
    check(promises.contains { $0.contains("never") },
          "\(source.rawValue): at least one promise is something she will NEVER do")
    // The person must be told BOTH what is sent and what is not. Testing for
    // the literal words "this phone" was the earlier version of this check and
    // it was brittle: the calendar promise now states the boundary as "Never
    // the calendar itself", which is the same guarantee in truer words.
    check(promises.contains { $0.contains("I send myself") },
          "\(source.rawValue): the person is told what actually leaves the phone")
    // Each source names ITS OWN boundary, and the switch is exhaustive on
    // purpose. This used to be one OR-chain of every source's phrasing, which
    // was weaker twice over: the calendar could have passed on the contacts
    // sentence, and both strings encoded an assumption that a source lives on
    // this device. `.mail` does not - it is read in the browser, and per
    // `design/day-zero.md` §4 the page slice reaches the model provider - so
    // "never leave this phone" would have been a FALSE promise, which is the
    // one defect the promise strings have already been rewritten once to fix.
    // A new source now has to state what it will not touch to compile.
    let boundary: String
    switch source {
    case .calendar: boundary = "never the calendar itself"
    case .contacts: boundary = "never leave this phone"
    case .mail: boundary = "never the mailbox"
    }
    check(promises.contains { $0.lowercased().contains(boundary) },
          "\(source.rawValue): the person is told what never leaves it (\"\(boundary)\")")
}

// ------------------------------------------------------------- 6: bounded reads
// The store has no embeddings (brain/memory.py:9): recall is keyword plus a
// graph walk, so volume actively degrades it. These caps are the difference
// between seeding memory and flooding it.
check(LifeContext.horizonDays == 30,
      "the calendar horizon is the month brief 08 specifies, not everything")
check(LifeContext.maxEvents <= 15, "events are capped so recall is not drowned")
check(LifeContext.maxNames <= 40, "names are capped")

// -------------------------------------------------- 7: nothing without a grant
// The gate again, this time at the read. Without a grant recorded, the fact
// list must be empty even on a device where iOS would happily answer — because
// the OS is only ever asked after our own screen has explained itself.
for source in ContextSource.allCases {
    let facts = LifeContext.facts(for: source)
    check(facts.isEmpty,
          "\(source.rawValue): no facts are produced in a context with no OS authorization")
}


// ------------------------------------------------------- 8: when she may ask
// The trigger is a rule, not a model. It must fire on a real plan and stay
// quiet on a word in passing, or a just-in-time ask becomes a nag.
do {
    let g = freshGrants()
    check(ContextTrigger.source(for: "dinner with Priya on Thursday", grants: g) == .calendar,
          "a plan plus a time asks for the calendar")
    check(ContextTrigger.source(for: "book a table tomorrow", grants: g) == .calendar,
          "a booking plus a time asks for the calendar")
    // A day of the week alone is conversation, not a commitment.
    let bare = ContextTrigger.source(for: "Thursday was rough", grants: g)
    check(bare != .calendar, "a bare day of the week does NOT ask for the calendar")
}
do {
    // Once declined, the same sentence must not ask again.
    let g = freshGrants()
    g.decline(.calendar)
    let again = ContextTrigger.source(for: "dinner with Marcus on Friday", grants: g)
    check(again != .calendar, "a declined source is never asked for again")
}
do {
    // An unfamiliar name is a reason to want the address book; a known one is not.
    let g = freshGrants()
    g.decline(.calendar)   // isolate the contacts branch
    check(ContextTrigger.source(for: "ask Priya about it", knownNames: [], grants: g) == .contacts,
          "an unknown name asks for contacts")
    check(ContextTrigger.source(for: "ask Priya about it", knownNames: ["Priya"], grants: g) == nil,
          "a name she already knows asks for nothing")
    check(ContextTrigger.unknownName(in: "see you in August", knownNames: []) == nil,
          "a month is not a person")
}

// ------------------------------------- 9: the false positives that burn the ask
// ContextGrants allows exactly ONE ask per source, ever. So a trigger that
// fires on ordinary conversation does not merely annoy — it spends the only
// chance the product gets. "am" used to be a time word matched as a SUBSTRING,
// which fired on family, amazing, Sam, campaign, and on the bare words of
// "I am busy".
do {
    let g = freshGrants()
    for innocent in ["call my family", "that party was amazing", "coffee with sam",
                     "I am busy", "I am free", "busy with the campaign",
                     "the interview came up"] {
        check(ContextTrigger.source(for: innocent, knownNames: [], grants: g) != .calendar,
              "\"\(innocent)\" does NOT burn the calendar ask")
    }
}
do {
    // And the real ones still fire.
    let g = freshGrants()
    check(ContextTrigger.source(for: "dinner at 7:30pm", grants: g) == .calendar,
          "a clock time with am/pm fires")
    check(ContextTrigger.source(for: "meeting at 09:15", grants: g) == .calendar,
          "an HH:MM time fires")
    check(ContextTrigger.source(for: "lunch next week", grants: g) == .calendar,
          "a multi-word phrase fires (it used to be unreachable)")
}

// ------------------------------------------------- 10: the ask names the thing
// CLAUDE-ONBOARDING.md's voice law wants the specific thing, not a category.
do {
    let g = freshGrants()
    g.decline(.calendar)
    guard let hit = ContextTrigger.ask(for: "ask Priya about it", knownNames: [], grants: g) else {
        failures += 1; print("FAIL: no ask returned for an unknown name"); exit(1)
    }
    check(hit.subject == "Priya", "the trigger returns the name it matched on")
    check(hit.source.ask(subject: hit.subject).contains("Priya"),
          "the question names the person instead of saying 'your contacts'")
    check(hit.source.because("ask Priya about it", subject: hit.subject).contains("Priya"),
          "the reason names the person too")
    // Without a subject it must still be a sensible question, not a broken one.
    check(ContextSource.contacts.ask(subject: nil).hasSuffix("?"),
          "the generic fallback is still one question")
}

// --------------------------------------------- 11: promises match the reader
// Two promises used to describe behaviour the code did not have. A consent
// screen is the worst place in the product to assert something untrue.
do {
    // The calendar reader uploads the event TITLE, so no promise may imply that
    // only a derived conclusion leaves.
    let calendar = ContextSource.calendar.promises.joined(separator: " ")
    check(!calendar.contains("Only what I conclude"),
          "the calendar promise no longer claims only conclusions travel")
    check(calendar.lowercased().contains("title"),
          "the calendar promise says the title is what gets sent")
    // The contacts reader sends up to maxNames in ONE fact, immediately.
    let contacts = ContextSource.contacts.promises.joined(separator: " ")
    check(!contacts.contains("only when it matters"),
          "the contacts promise no longer claims names travel only when needed")
    check(contacts.lowercased().contains("list of names"),
          "the contacts promise says a list is sent, not a single name")
}

print(failures == 0 ? "context grant tests: all passed" : "context grant tests: \(failures) FAILED")
exit(failures == 0 ? 0 : 1)
