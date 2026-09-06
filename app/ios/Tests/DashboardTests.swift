import Foundation

// The conversation dashboard's decisions, walked. Compiled by
// run_dashboard_tests.sh against the production DashboardPolicy.swift; this
// file is that suite's main.swift, so it may hold top-level code.

var failures = 0
func check(_ ok: Bool, _ name: String, _ detail: @autoclosure () -> String = "") {
    if ok { print("PASS: \(name)") } else { failures += 1; print("FAIL: \(name) \(detail())") }
}

typealias P = DashboardPolicy

// ---------------------------------------------------------------- capture
// The order is the point: a phone with the microphone switched off in iOS is
// not "paused", and saying "Listening…" over a dead microphone is the one
// sentence this screen must never print.
check(P.captureState(micBlocked: true, listening: true, suspended: false, reachable: true) == .blocked,
      "a blocked microphone outranks a listener that thinks it is running")
check(P.captureState(micBlocked: true, listening: false, suspended: true, reachable: false) == .blocked,
      "and outranks everything else too")
check(P.captureState(micBlocked: false, listening: true, suspended: true, reachable: true) == .interrupted,
      "a call taking the microphone is an interruption, not a pause")
check(P.captureState(micBlocked: false, listening: false, suspended: false, reachable: true) == .paused,
      "not listening and nothing wrong is a pause")
check(P.captureState(micBlocked: false, listening: true, suspended: false, reachable: true) == .listening,
      "listening, with a server to send it to")
check(P.captureState(micBlocked: false, listening: true, suspended: false, reachable: false) == .offline,
      "listening with nowhere to send it is still listening, and says so")

check(P.captureFace(.listening, heardAnything: false).alive,
      "the wave moves while she is hearing")
check(P.captureFace(.offline, heardAnything: false).alive,
      "and while she is hearing but cannot reach her side")
check(!P.captureFace(.paused, heardAnything: true).alive,
      "a paused capture has a still wave")
check(!P.captureFace(.blocked, heardAnything: false).alive,
      "so does a blocked one")
check(!P.captureFace(.interrupted, heardAnything: false).alive,
      "so does an interrupted one")
check(P.captureFace(.listening, heardAnything: false).subtitle
        != P.captureFace(.listening, heardAnything: true).subtitle,
      "the invitation changes once she has heard something")
for state in [P.CaptureState.listening, .paused, .interrupted, .blocked, .offline] {
    let f = P.captureFace(state, heardAnything: false)
    check(!f.title.isEmpty && !f.subtitle.isEmpty, "\(state) says what it is and what to do")
}
check(P.captureFace(.offline, heardAnything: false).title == "Listening…",
      "an unreachable server does not stop her listening")
check(P.captureFace(.blocked, heardAnything: false).title != "Listening…",
      "a switched-off microphone does")

// ------------------------------------------------------------------ thread
let heard = [
    P.HeardRow(id: "h1", text: "call the plumber tomorrow", at: "2026-09-05T10:00:00Z"),
    P.HeardRow(id: "h2", text: "", at: "2026-09-05T10:01:00Z"),
]
let said = [
    P.SaidRow(id: "s1", text: "Booked for 9am.", at: "2026-09-05T10:05:00Z", decision: "done"),
    P.SaidRow(id: "s2", text: "Which number should I use?", at: "2026-09-05T10:06:00Z", decision: "ask"),
    P.SaidRow(id: "s3", text: "Waiting until Monday.", at: "2026-09-05T10:07:00Z", decision: "clock"),
    P.SaidRow(id: "s4", text: "", at: "2026-09-05T10:08:00Z", decision: "done"),
]
let jobs = [
    P.JobRow(id: "j1", goal: "Text Sam that you're running late", consequence: "Sends a message",
             at: "2026-09-05T10:02:00Z", placement: .needsYou),
    P.JobRow(id: "j2", goal: "Looking up the plumber", consequence: nil,
             at: "2026-09-05T10:03:00Z", placement: .handling),
]
let turns = P.thread(heard: heard, said: said, jobs: jobs)

check(turns.count == 6, "an empty line is not a turn, and a finished job is not one either",
      "got \(turns.count)")
check(turns.map(\.at) == turns.map(\.at).sorted(), "the thread is in time order")
check({ if case .owner = turns[0] { return true }; return false }(),
      "the oldest turn is the thing that was said first")

func kind(_ t: P.Turn) -> String {
    switch t {
    case .owner: return "owner"
    case .working: return "working"
    case .said: return "said"
    case .approval: return "approval"
    case .question: return "question"
    }
}
check(turns.map(kind) == ["owner", "approval", "working", "said", "question", "question"],
      "every row becomes the turn its own verdict says it is", "got \(turns.map(kind))")

check({ if case .said(_, _, _, let done) = turns[3] { return done }; return false }(),
      "a done event is a said turn, marked done")
check(!turns.contains { if case .said(let id, _, _, _) = $0 { return id == "j3" }; return false },
      "a finished JOB is not in the thread at all — the deck at the foot owns it, "
      + "because that is where the shelf rule lives")

// A tie in time is broken by id, so two rows written in the same second do not
// swap places between two redraws of the same screen.
let tied = P.thread(
    heard: [P.HeardRow(id: "b", text: "second", at: "2026-09-05T10:00:00Z"),
            P.HeardRow(id: "a", text: "first", at: "2026-09-05T10:00:00Z")],
    said: [], jobs: [])
check(tied.map(\.id) == ["a", "b"], "a tie in time is broken the same way every draw")
check(P.thread(heard: [], said: [], jobs: []).isEmpty, "nothing in, nothing out")

// ---------------------------------------------------------------- seatbelt
check(P.pendingApproval(in: turns)?.id == "j1", "the approval is found wherever it sits")
let twoApprovals = P.thread(heard: [], said: [], jobs: [
    P.JobRow(id: "late", goal: "later", consequence: nil, at: "2026-09-05T12:00:00Z", placement: .needsYou),
    P.JobRow(id: "early", goal: "earlier", consequence: nil, at: "2026-09-05T09:00:00Z", placement: .needsYou),
])
check(P.pendingApproval(in: twoApprovals)?.id == "early",
      "the one that has been waiting longest is the one in front of you")
check(P.pendingApproval(in: P.thread(heard: heard, said: [], jobs: [])) == nil,
      "no approval, no bar")
check(turns.filter { $0.waitsOnTheOwner }.count == 3,
      "an approval and two questions all wait on the owner",
      "got \(turns.filter { $0.waitsOnTheOwner }.count)")
check({ if case .approval = P.pendingApproval(in: turns) { return true }; return false }(),
      "and the bar only ever shows an approval")

// ----------------------------------------------------------------- history
// A FIXED CALENDAR IN A FIXED ZONE. `Calendar(identifier:)` carries the
// machine's own timezone, so the same instant is a different day on a laptop
// in Vancouver and a runner in UTC — which is exactly how this suite passed
// here and failed in CI.
var cal = Calendar(identifier: .gregorian)
cal.timeZone = TimeZone(identifier: "UTC")!
// Eight in the evening of a fixed day, and every stamp below is placed
// against the START of that day rather than against `now`. An earlier version
// subtracted 2.4 hours from "now" and called the result "also today", which is
// only true when the suite does not run near midnight — a test that passes on
// the machine that wrote it and fails at 1am is worse than no test.
let dayStart = cal.startOfDay(for: Date(timeIntervalSince1970: 1_788_600_000))
let now = dayStart.addingTimeInterval(20 * 3_600)
let iso = ISO8601DateFormatter()
func atHour(_ h: Double, daysAgo: Double = 0) -> String {
    iso.string(from: dayStart.addingTimeInterval(h * 3_600 - daysAgo * 86_400))
}
let days = P.history([
    P.Session(id: "a", title: "The plumber", at: atHour(14)),
    P.Session(id: "b", title: "Standup", at: atHour(9)),
    P.Session(id: "c", title: "Yesterday's errand", at: atHour(14, daysAgo: 1)),
    P.Session(id: "d", title: "Last week", at: atHour(14, daysAgo: 9)),
], now: now, calendar: cal)
check(days.count >= 3, "conversations are grouped by day", "got \(days.count)")
check(days.first?.heading == "Today", "today is called Today")
check(days.first?.sessions.count == 2, "both of today's conversations are under it")
check(days.first?.sessions.first?.id == "a", "newest first inside a day")
check(days.dropFirst().first?.heading == "Yesterday", "yesterday is called Yesterday")
check(days.last?.heading != "Today" && days.last?.heading != "Yesterday",
      "a conversation from last week gets a date")
check(P.history([], now: now, calendar: cal).isEmpty, "no conversations, no days")
check(P.history([P.Session(id: "x", title: "junk", at: "not a date")], now: now, calendar: cal).isEmpty,
      "a row with no readable date is dropped rather than shown under a guess")

// THE SHAPE THE STORE ACTUALLY WRITES. Rows arrive "2026-09-06 11:43:07.000Z"
// — a space where ISO-8601 wants a T — and the first version of `history`
// parsed none of them, so History said "Nothing here yet" over a phone full of
// conversations. The thread hid the bug because it sorts the strings and never
// parses them.
let pbStyle = iso.string(from: dayStart.addingTimeInterval(11 * 3_600))
    .replacingOccurrences(of: "T", with: " ")
let pbDays = P.history([P.Session(id: "pb", title: "Written by the store", at: pbStyle)],
                       now: now, calendar: cal)
check(pbDays.count == 1 && pbDays[0].heading == "Today",
      "a timestamp with a space instead of a T is still today",
      "got \(pbDays.map(\.heading))")
check(pbDays.first?.sessions.first?.id == "pb", "and the row survives to be shown")

// -------------------------------------------------------------- empty line
check(P.emptyLine(listening: true, everListened: true) != P.emptyLine(listening: false, everListened: true),
      "the empty screen says something different while she is listening")
check(P.emptyLine(listening: false, everListened: false)
        != P.emptyLine(listening: false, everListened: true),
      "and something different to somebody who has never turned it on")
check(!P.emptyLine(listening: false, everListened: false).isEmpty, "and is never blank")

if failures == 0 {
    print("DashboardTests: all passed")
} else {
    print("DashboardTests: \(failures) case(s) came back wrong")
    exit(1)
}
