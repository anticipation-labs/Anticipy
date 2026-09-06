import Foundation

// What Anticipy may truthfully say about itself, walked. Compiled by
// run_insights_tests.sh against the production policy; this file is that
// suite's main.swift, so it may hold top-level code.

var failures = 0
func check(_ ok: Bool, _ name: String, _ detail: @autoclosure () -> String = "") {
    if ok { print("PASS: \(name)") } else { failures += 1; print("FAIL: \(name) \(detail())") }
}

typealias P = InsightsPolicy

// ============================================================ NEVER PRINT ZERO
// The rule the whole file exists for. An absent line says "not yet"; a line
// reading 0 says "it doesn't work".
let empty = P.Counts.nothing
check(P.rows(empty).isEmpty, "nothing counted, nothing printed")
check(P.peek(empty) == nil, "and no peek card at all")
check(P.ears(empty).isEmpty, "and no ear bars")
check(!P.worthOpening(empty), "and the page is not worth opening")

var zeros = P.Counts.nothing
zeros.days = 0; zeros.lines = 0; zeros.pickedUp = 0; zeros.errandsFinished = 0
zeros.askedFirst = 0; zeros.conversations = 0; zeros.notYetJudged = 0
check(P.rows(zeros).isEmpty, "an explicit zero is still not printed")
check(P.peek(zeros) == nil, "a zero-day owner gets no card rather than a card saying 0")
for row in P.rows(zeros) { check(false, "leaked a zero row: \(row.id)") }

// A single real number brings its own row and nothing else.
var oneDay = P.Counts.nothing
oneDay.days = 1
check(P.rows(oneDay).count == 1, "one fact, one row")
check(P.peek(oneDay)?.headline.contains("one day") == true,
      "and one day is written as a word, not as '1 days'",
      P.peek(oneDay)?.headline ?? "nil")
check(P.peek(oneDay)?.detail == nil, "with no invented second line")

// ================================================================ THE HEADLINE
// Days, and it is forced rather than chosen: while the brain is capped, every
// verdict-derived number renders as its cold-start apology for every real owner.
var busy = P.Counts.nothing
busy.days = 43; busy.lines = 12431; busy.pickedUp = 312
let peek = P.peek(busy)
check(peek?.headline == "You've talked to Anticipy on 43 days.",
      "the headline is days", peek?.headline ?? "nil")
check(peek?.detail == "312 of 12,431 lines turned into something.",
      "and the catch ratio always carries its denominator", peek?.detail ?? "nil")
check(peek?.detail?.contains("12,431") == true, "numbers are grouped for reading")
check(P.number(1234567) == "1,234,567", "and grouped at every scale")
check(!P.number(1200).contains("k") && !P.number(1_200_000).contains("M"),
      "never abbreviated — an abbreviation is a rounding nobody can check")

// A day count with no lines at all still gets its headline, without a filler
// second line.
var daysOnly = P.Counts.nothing
daysOnly.days = 9
check(P.peek(daysOnly)?.detail == nil, "no lines, no second line")

// ============================================================== THE COLD START
// A CLOSED SET OF FOUR. The whole reason this is an enum is that a suite can
// walk it exhaustively; "show whatever is non-empty" has nothing to walk.
check(P.stage(P.Counts.nothing) == .heardNothing, "nothing heard")
var heard = P.Counts.nothing; heard.lines = 400
check(P.stage(heard) == .heardNothingJudged, "heard, but nothing judged")
var judged = heard; judged.pickedUp = 12
check(P.stage(judged) == .judgedNothingFinished, "judged, but nothing finished")
var steady = judged; steady.errandsFinished = 3
check(P.stage(steady) == .steady, "and steady")

for stage in [P.Stage.heardNothing, .heardNothingJudged, .judgedNothingFinished] {
    let line = P.emptyLine(stage)
    check(!line.isEmpty, "\(stage) says something")
    // No unlock countdown: nobody has measured where a real owner's first
    // finished errand lands, so any number in that sentence is a guess dressed
    // as a milestone.
    check(!line.contains(where: { $0.isNumber }),
          "\(stage) counts down to nothing — no invented unlock threshold", line)
}
check(P.emptyLine(.steady).isEmpty, "a steady owner is told nothing extra")

// THE STATE EVERY REAL OWNER IS IN TODAY. The brain is capped, so rows carry no
// verdict, and this sentence must never read as "nothing was worth catching".
let capped = P.emptyLine(.heardNothingJudged).lowercased()
check(capped.contains("verdict"), "the unjudged state says it has not judged, not that it found nothing")
check(!capped.contains("0") && !capped.contains("none"),
      "and never phrases it as a zero", P.emptyLine(.heardNothingJudged))

// ================================================================== THE ROWS
var full = P.Counts.nothing
full.days = 43; full.lines = 12431; full.pickedUp = 312; full.notYetJudged = 94
full.errandsFinished = 41; full.askedFirst = 214; full.conversations = 168
let rows = P.rows(full)
check(rows.count == 7, "every counted fact gets a row", "got \(rows.count)")
check(rows.first?.id == "days", "days leads")
check(rows.map(\.id) == ["days", "lines", "picked", "unjudged", "errands", "asked", "conversations"],
      "in a fixed order, so the page does not reshuffle between refreshes")

// The two rows that would otherwise overstate themselves carry their caveat.
let picked = rows.first { $0.id == "picked" }
check(picked?.caveat != nil, "the catch row admits some of it was only looked into")
let errands = rows.first { $0.id == "errands" }
check(errands?.caveat?.contains("stopped") == true,
      "the errand row admits Home's Done also holds the ones that stopped",
      errands?.caveat ?? "nil")

// The unjudged companion is not optional: without it a capped owner reads a
// confident silence about a day they talked through.
var noCompanion = P.Counts.nothing
noCompanion.days = 3; noCompanion.lines = 500; noCompanion.notYetJudged = 500
check(P.rows(noCompanion).contains { $0.id == "unjudged" },
      "unjudged lines get their own row")

// ONE OF A THING IS NOT "1 things". A screen whose whole claim is exactness
// cannot get its own grammar wrong in front of somebody counting.
var singles = P.Counts.nothing
singles.days = 1; singles.lines = 1; singles.errandsFinished = 1
singles.askedFirst = 1; singles.conversations = 1
for row in P.rows(singles) {
    check(!row.label.hasPrefix("s") && !row.label.contains(" things ")
            && !row.label.hasSuffix("s finished") && !row.label.hasPrefix("times"),
          "the singular row '\(row.id)' reads as one of a thing", row.label)
}
check(P.rows(singles).first { $0.id == "asked" }?.label.hasPrefix("time ") == true,
      "one ask is a time, not times")
check(P.rows(singles).first { $0.id == "errands" }?.label == "errand finished",
      "one errand is an errand")

check(P.worthOpening(full), "a full page is worth opening")
check(P.worthOpening(oneDay), "and so is a single true fact")

// ==================================================================== THE EARS
// A lane with nothing in it is OMITTED. A pendant row reading 0% reads as a
// broken pendant; the pendant has simply never shipped.
var ears = P.Counts.nothing
ears.heardByPhone = 900; ears.typedByYou = 100
let bars = P.ears(ears)
check(bars.count == 2, "only the lanes with something in them", "got \(bars.count)")
check(bars.first?.id == "phone", "the biggest lane leads")
check(bars.first?.share == 90, "shares are of the counted total", "\(bars.first?.share ?? -1)")
check(bars.map(\.share).reduce(0, +) == 100, "and add up")
check(!bars.contains { $0.id == "pendant" }, "no pendant lane at all — it has never shipped")
check(!bars.contains { $0.count == 0 }, "and never a lane at zero")

var oneEar = P.Counts.nothing; oneEar.heardByPhone = 50
check(P.ears(oneEar).first?.share == 100, "one lane is all of it")
var tiedEars = P.Counts.nothing; tiedEars.heardByPhone = 10; tiedEars.typedByYou = 10
check(P.ears(tiedEars).map(\.id) == ["phone", "typed"],
      "a tie breaks by name, so the bars do not swap between draws")

// ============================================================ NOTHING PUNISHES
// Every number only goes up. A streak would break on Anticipy's own outage —
// the ears went deaf for thirty hours and nothing noticed — and bill it to the
// person, so there is no streak here and no word for one.
let allCopy = (P.rows(full).map { $0.label + " " + ($0.caveat ?? "") }
               + [P.peek(full)?.headline ?? "", P.peek(full)?.detail ?? ""]
               + [P.Stage.heardNothing, .heardNothingJudged, .judgedNothingFinished, .steady].map(P.emptyLine))
    .joined(separator: " ").lowercased()
for word in ["streak", "in a row", "don't break", "keep it up", "congratulations", "well done"] {
    check(!allCopy.contains(word), "nothing on this screen says '\(word)'")
}

if failures == 0 {
    print("InsightsTests: all passed")
} else {
    print("InsightsTests: \(failures) case(s) came back wrong")
    exit(1)
}
