// What a grant says back, and what the yes button says before it.
//
// Both are consent copy on the one screen where somebody hands over their
// address book, and both fail silently: a receipt that shows three of fifteen
// lines under the words "it's all I've got" reads exactly like a receipt that
// is complete, and a per-source button label reads exactly like a generic one
// until you notice it never changed.
//
// Run: sh app/ios/Tests/run_context_receipt_tests.sh

import Foundation

var failures = 0
func check(_ ok: Bool, _ what: String) {
    if ok { print("PASS: \(what)") } else { failures += 1; print("FAIL: \(what)") }
}

// Stand-ins shaped exactly like `LifeContext.facts(for: .calendar)` output.
func events(_ n: Int) -> [String] {
    (1...max(n, 1)).prefix(n).map { "On their calendar: \"Thing \($0)\", Thursday 7 May, 7:30pm." }
}
let people = ["Aisha Bello", "Marcus Reed", "Priya Nair", "Sam Okafor", "Tomas Lind"]

// ------------------------------------------------------- 0: nothing came back
// The empty read must say the thing this type KNOWS — nothing arrived — and
// nothing about the phone. An empty calendar and a calendar iOS has not
// finished handing over produce the identical empty array here.
for source in [ContextSource.calendar, .contacts] {
    let lines = ContextReceipt.lines(for: source)
    check(lines == [ContextReceipt.nothing],
          "\(source.rawValue): an empty read says nothing came back, once")
    check(!lines.joined().lowercased().contains("empty"),
          "\(source.rawValue): it does not claim the source itself is empty")
}

// ------------------------------------------------ 1: the lines are the lines
// Verbatim, not summarised. A receipt for what left the phone that paraphrases
// what left the phone is not a receipt.
do {
    let facts = events(2)
    check(ContextReceipt.lines(for: .calendar, facts: facts) == facts,
          "two events are shown word for word, with nothing added")
    let three = events(3)
    check(ContextReceipt.lines(for: .calendar, facts: three) == three,
          "exactly three events are all shown, with no remainder line")
}

// ------------------------------------------- 2: the heading stays true at 15
// "Here's everything I've got, and it's all I've got:" is false the moment
// three lines stand in for fifteen with nothing said about the other twelve.
do {
    let facts = events(15)
    let lines = ContextReceipt.lines(for: .calendar, facts: facts)
    check(lines.count == ContextReceipt.shown + 1,
          "fifteen events are shown as three lines and a remainder")
    check(Array(lines.prefix(3)) == Array(facts.prefix(3)),
          "the three shown are the first three, unaltered")
    check(lines.last?.contains("12") == true,
          "the remainder counts the twelve that are not on the screen")
    check(lines.last?.contains("title and a time") == true,
          "the remainder says what kind of thing the twelve are")
    check(lines.last?.contains("sent") != true && lines.last?.contains("went") != true,
          "the remainder counts what she has, and claims no delivery she may not have made")
    // The screen must not become the calendar.
    check(lines.count < facts.count, "the sheet does not print the whole month")
}
do {
    // One left over is one, not "1 more … each one".
    let lines = ContextReceipt.lines(for: .calendar, facts: events(4))
    check(lines.count == 4 && lines.last == "And 1 more, a title and a time.",
          "a single remainder is worded as one thing")
}
// Every size from empty to the cap accounts for every event, and never shows
// more than `shown` of them. No threshold, no special case in the middle.
for n in 0...LifeContext.maxEvents {
    let lines = ContextReceipt.lines(for: .calendar, facts: events(n))
    let shownLines = lines.filter { $0.hasPrefix("On their calendar:") }
    check(shownLines.count == min(n, ContextReceipt.shown),
          "\(n) events: at most three are on the screen")
    if n > ContextReceipt.shown {
        check(lines.last?.contains("\(n - ContextReceipt.shown)") == true,
              "\(n) events: the ones not shown are counted out loud")
    }
}

// -------------------------------------------------- 3: contacts is ONE line
// `LifeContext.facts(for: .contacts)` joins every name into a single fact row,
// so forty lines here would report a shape the server never received.
do {
    check(ContextReceipt.lines(for: .contacts, names: people).count == 1,
          "however many names travelled, one row travelled")
    check(ContextReceipt.lines(for: .contacts, names: ["Aisha Bello"]) == ["1 name: Aisha Bello."],
          "one name is a name, not names")
    check(ContextReceipt.lines(for: .contacts, names: Array(people.prefix(2)))
            == ["2 names: Aisha Bello and Marcus Reed."],
          "two names are both shown, joined with and")
    check(ContextReceipt.lines(for: .contacts, names: Array(people.prefix(3)))
            == ["3 names: Aisha Bello, Marcus Reed and Priya Nair."],
          "three names are all shown, so nothing is held back that would fit")
}
do {
    // The cap the promise names, at the size it actually arrives.
    let forty = (1...LifeContext.maxNames).map { "Person \($0)" }
    let line = ContextReceipt.lines(for: .contacts, names: forty)[0]
    check(line.hasPrefix("\(LifeContext.maxNames) names."),
          "the count comes first, because the count is the promise being kept")
    check(line.contains("The first three are Person 1, Person 2 and Person 3."),
          "three names stand for the rest, in the order they were read")
    // A consent sheet that prints the address book has handed the address book
    // to whoever is looking over your shoulder.
    check(!line.contains("Person 4"), "the fourth name is not on the screen")
    check(!line.contains("Person 40"), "nor is the fortieth")
}

// ---------------------------------------------------- 4: mail has no receipt
// Mail is never granted from the ask sheet, and its facts are distilled in the
// browser afterwards. A "nothing came back" here would report a read that had
// not happened yet.
check(ContextReceipt.lines(for: .mail).isEmpty,
      "mail produces no receipt at the moment of the grant")
check(ContextReceipt.lines(for: .mail, facts: events(3), names: people).isEmpty,
      "and cannot be made to produce one by handing it somebody else's read")

// -------------------------------------------- 5: the words and the cap agree
// "The first three are" is spelled out. If `shown` stops being three, that
// sentence is a lie and this is the leg that says so.
check(ContextReceipt.shown == 3,
      "the receipt shows three lines, which is what its sentences say")
check(ContextReceipt.heading.hasSuffix(":"),
      "the heading leads into the lines rather than standing alone")

// ------------------------------------------------ 6: the yes names its limit
// One button, three different things being handed over. The generic label was
// the only line on the screen that did not say what the tap buys.
do {
    var seen = Set<String>()
    for source in ContextSource.allCases {
        let label = source.yesButton
        check(label.hasPrefix("Yes"), "\(source.rawValue): the yes still reads as a yes")
        check(label != "Yes, go ahead", "\(source.rawValue): it is not the generic label")
        check(seen.insert(label).inserted,
              "\(source.rawValue): no two sources share a label")
    }
}
check(ContextSource.calendar.yesButton.contains("the next month"),
      "the calendar button says the horizon the promise and the Info.plist both say")
// A third phrasing of the same thirty days is the drift the standing order at
// ContextGrant.swift:106-112 exists to stop.
check(!ContextSource.calendar.yesButton.lowercased().contains("day"),
      "and does not respell that month as days")
check(ContextSource.contacts.yesButton.lowercased().contains("names"),
      "the contacts button names what is read, which is names")
check(ContextSource.mail.yesButton.lowercased().contains("watch"),
      "the mail button says the watching, which is what its yes actually buys")

// ------------------------------------- 7: the promises carry the real numbers
// Both caps were enforced in code and absent from the sentence a person reads
// before saying yes. Spelled from the constants, so raising a cap fails here
// until the promise catches up.
func spelled(_ n: Int) -> String {
    let f = NumberFormatter()
    f.numberStyle = .spellOut
    f.locale = Locale(identifier: "en_US")
    return f.string(from: NSNumber(value: n)) ?? "\(n)"
}
do {
    let calendar = ContextSource.calendar.promises.joined(separator: " ")
    check(calendar.contains(spelled(LifeContext.maxEvents)),
          "the calendar promise says how many lines at most: \(spelled(LifeContext.maxEvents))")
    let contacts = ContextSource.contacts.promises.joined(separator: " ")
    check(contacts.contains(spelled(LifeContext.maxNames)),
          "the contacts promise says how many names at most: \(spelled(LifeContext.maxNames))")
}

print(failures == 0 ? "context receipt tests: all passed" : "context receipt tests: \(failures) FAILED")
exit(failures == 0 ? 0 : 1)
