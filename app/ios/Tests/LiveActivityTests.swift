import Foundation

// WHAT THE LOCK SCREEN MAY SAY, walked. Compiled by run_live_activity_tests.sh
// against the production policy; this file is that suite's main.swift, so it
// may hold top-level code.

var failures = 0
func check(_ ok: Bool, _ name: String, _ detail: @autoclosure () -> String = "") {
    if ok { print("PASS: \(name)") } else { failures += 1; print("FAIL: \(name) \(detail())") }
}

typealias L = LiveActivityPolicy

// ==================================================== IT NEVER QUOTES ANYBODY
// The rule this file exists for. `face` takes a COUNT and a DURATION and has
// no parameter that could carry a sentence — the signature is the proof, and
// this walk is what notices if somebody adds one.
let everyReason: [L.Reason] = [.listening, .paused, .offline, .working, .waiting]
for reason in everyReason {
    for heard in [0, 1, 2, 47, 999] {
        let f = L.face(reason, heard: heard, elapsed: 125)
        check(f.title == "Anticipy", "title is always the product's name", f.title)
        check(!f.detail.isEmpty, "every reason has something to say", "\(reason)")
        // The only digits that may appear are the count and the clock.
        let digits = f.detail.filter { $0.isNumber }
        let allowed = Set("\(heard)2 05".filter { $0.isNumber })
        check(digits.allSatisfy { allowed.contains($0) },
              "no number on the lock screen that is not the count or the clock",
              "\(reason) heard=\(heard): \(f.detail)")
    }
}

// ====================================================== AND IT NEVER APPROVES
// `Action` has two cases and neither of them commits anything. If a third
// appears, this stops compiling or stops passing — which is the point.
for reason in everyReason {
    let a = L.face(reason, heard: 3, elapsed: 60).action
    check(a == .stopListening || a == .openApp,
          "the only actions are stop and open", "\(reason) -> \(a)")
}
check(L.face(.waiting, heard: 0, elapsed: 0).action == .openApp,
      "something waiting on you OPENS the app rather than approving from the lock screen")
check(L.face(.working, heard: 0, elapsed: 0).action == .openApp,
      "and so does work in flight")

// ============================================== THE MARK MOVES ONLY WHEN LIVE
// A breathing indicator over a microphone that is not on is the same lie here
// as it is in the app.
check(L.face(.listening, heard: 0, elapsed: 0).alive, "listening breathes")
check(L.face(.offline, heard: 0, elapsed: 0).alive, "offline is still hearing, so it breathes")
check(!L.face(.paused, heard: 4, elapsed: 90).alive, "paused does not")
check(!L.face(.working, heard: 0, elapsed: 0).alive, "neither does work")
check(!L.face(.waiting, heard: 0, elapsed: 0).alive, "nor something waiting")

// ================================================================== THE COUNT
check(L.heardLine(0, elapsed: 0) == "Listening",
      "nothing heard yet and no clock reads as plain listening", L.heardLine(0, elapsed: 0))
check(L.heardLine(0, elapsed: 65) == "Listening · 1:05",
      "nothing heard yet, but the clock is honest", L.heardLine(0, elapsed: 65))
check(L.heardLine(1, elapsed: 65) == "1 thing heard · 1:05",
      "one is singular", L.heardLine(1, elapsed: 65))
check(L.heardLine(2, elapsed: 65) == "2 things heard · 1:05",
      "two is not", L.heardLine(2, elapsed: 65))
check(!L.heardLine(0, elapsed: 0).contains("0"),
      "a zero count is never printed as a zero")

// ================================================================== THE CLOCK
check(L.clock(0) == "", "under a second is nothing, so a fresh start never flashes 0:00")
check(L.clock(0.4) == "", "still nothing")
check(L.clock(1) == "0:01", "one second")
check(L.clock(59) == "0:59", "under a minute")
check(L.clock(60) == "1:00", "a minute")
check(L.clock(605) == "10:05", "ten minutes")
check(L.clock(3600) == "1:00:00", "an hour grows a third field")
check(L.clock(3661) == "1:01:01", "and keeps its padding")
check(L.clock(.infinity) == "", "a non-finite duration prints nothing rather than crashing")
check(L.clock(-5) == "", "and so does a negative one")

// ============================================================== WHO WINS, AND WHY
// Listening outranks everything with a microphone open. A capsule that said
// "Waiting on you" while the mic was live would hide the more important fact
// behind the more interesting one.
check(L.reason(listening: true, paused: false, reachable: true,
               working: true, waiting: true) == .listening,
      "listening beats both work and a question")
check(L.reason(listening: true, paused: true, reachable: true,
               working: false, waiting: false) == .paused,
      "hold shows as paused rather than vanishing, which would read as a crash")
check(L.reason(listening: true, paused: false, reachable: false,
               working: false, waiting: false) == .offline,
      "no server, and it says so")
check(L.reason(listening: true, paused: true, reachable: false,
               working: false, waiting: false) == .paused,
      "paused outranks offline: a stopped mic has nothing to send anywhere")
check(L.reason(listening: false, paused: false, reachable: true,
               working: true, waiting: true) == .waiting,
      "with the mic off, a question beats work in flight")
check(L.reason(listening: false, paused: false, reachable: true,
               working: true, waiting: false) == .working,
      "work alone shows as work")
check(L.reason(listening: false, paused: false, reachable: true,
               working: false, waiting: false) == nil,
      "and nothing happening ENDS the activity rather than lingering")
check(L.reason(listening: false, paused: true, reachable: false,
               working: false, waiting: false) == nil,
      "a pause with no listening is not a reason to be on somebody's lock screen")

// ============================================== THE OFFLINE LINE IS NOT A COMFORT
let off = L.face(.offline, heard: 3, elapsed: 30).detail
check(off.contains("this phone"),
      "offline says where the words are actually going", off)
check(!off.lowercased().contains("don't worry") && !off.lowercased().contains("all good"),
      "and does not reassure instead of informing", off)

// The qualifier is separable BECAUSE the live view does not print `detail` —
// it draws the count beside a clock it ticks itself, and that optimisation ate
// this line once. A capsule reading "3 things heard · 2:12" on a phone with no
// signal is exactly the reassuring lie `.offline` exists to refuse.
check(L.qualifier(.offline) != nil, "offline has a qualifier the clock must not swallow")
check(off.hasSuffix(L.qualifier(.offline)!),
      "and `face` composes that same piece rather than spelling it twice", off)
check(off.hasPrefix(L.heardLine(3, elapsed: 30)),
      "on top of the ordinary count line", off)
for reason in everyReason where reason != .offline {
    check(L.qualifier(reason) == nil, "nothing else qualifies its line", "\(reason)")
}
check(L.face(.offline, heard: 0, elapsed: 0).detail == "Listening · keeping it on this phone",
      "and it still says it with nothing heard yet",
      L.face(.offline, heard: 0, elapsed: 0).detail)

// ================================================================ THE ISLAND
// A handful of characters. A count is the only thing that survives being that
// small and still means something — and it is still never a word.
check(L.compact(.listening, heard: 0) == "", "no count yet, nothing shown")
check(L.compact(.listening, heard: 7) == "7", "the count, alone")
check(L.compact(.offline, heard: 7) == "7", "same offline")
check(!L.compact(.paused, heard: 0).isEmpty, "paused still shows something")
check(L.compact(.waiting, heard: 0) == "!", "a question is one character")
for reason in everyReason {
    check(L.compact(reason, heard: 12).count <= 4,
          "nothing in the island is longer than the island", "\(reason)")
}

// ========================================================= IT LEAVES BY ITSELF
check(L.lingerAfterEnding > 0, "a finish is visible for a moment")
check(L.lingerAfterEnding <= 15,
      "and then it goes — this is a lock screen, not a home for the app",
      "\(L.lingerAfterEnding)")

// ============================================================ THE WIRE ROUND-TRIP
// The reason crosses a process boundary as a string. A value that did not
// survive the trip would draw the wrong face on a locked phone.
for reason in everyReason {
    check(ActivityReason.from(ActivityReason.wire(reason)) == reason,
          "\(reason) survives the wire")
}
check(ActivityReason.from("something-a-later-build-invented") == .listening,
      "an unknown reason fails to LISTENING, so nobody is left with a microphone they cannot see")
check(ActivityReason.from("") == .listening, "and so does an empty one")

print(failures == 0 ? "\nAll live-activity checks passed."
                    : "\n\(failures) live-activity check(s) failed.")
exit(failures == 0 ? 0 : 1)
