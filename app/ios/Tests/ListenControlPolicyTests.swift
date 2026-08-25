import Foundation

// Checks for ListenControlPolicy — what the listening control says, what
// tapping it does, and whether the screen may show her as hearing you.
//
// The failure being closed, 2026-08-25. The button's label was made honest and
// its action was not. `ContentView` read:
//
//     Button { if isListening { stopListening() } else { startListening() } }
//     label: { Text(suspended ? "Waiting for the microphone" : ...) }
//
// `suspended` is set while `isListening` stays true, so during a phone call the
// biggest type on the home screen was a passive status sentence sitting on a
// control that turns listening off for the rest of the day. Tapping a sentence
// to hurry it along is a reasonable thing for a person to do, and nothing in
// the app brings listening back afterwards.
//
// A CONTROL'S LABEL DESCRIBES WHAT TAPPING IT DOES. Taking the microphone away
// does not change what this button does, so it must not change what the button
// says it does — that is the invariant the sweep at the end holds over every
// state, and it is the one the shipped code failed.
//
// Pure Foundation on purpose, like ListenResumePolicy and ListenWatchdogPolicy:
// swiftc alone. No simulator, no scheme, no signing — and no device that has to
// receive a real phone call before the answer can be checked.

@main
struct ListenControlPolicyTests {
    static func main() {
        var checks = 0
        var failures: [String] = []

        func check(_ name: String, _ ok: Bool) {
            checks += 1
            if ok {
                print("  ok    \(name)")
            } else {
                failures.append(name)
                print("  FAIL  \(name)")
            }
        }

        func face(blocked: Bool = false, listening: Bool, suspended: Bool)
            -> ListenControlPolicy.Face {
            ListenControlPolicy.face(micBlocked: blocked,
                                     isListening: listening,
                                     suspended: suspended)
        }

        // ------------------------------------------------------- 1. the off state
        // The only state where the label names something the screen is not
        // already doing, and it reads as an instruction because it is one.
        check("listening is off, so the control offers to start it",
              face(listening: false, suspended: false)
              == .init(label: "Listen with phone", tap: .start,
                       glyph: .symbol("mic")))

        // -------------------------------------------------------- 2. listening
        // The breathing dot is the screen's claim about the present tense, and
        // here it is true.
        check("listening and hearing, so the control offers to stop and the dot breathes",
              face(listening: true, suspended: false)
              == .init(label: "Stop listening", tap: .stop, glyph: .breathingDot))

        // ------------------------------------------------------------ 3. THE DOOR
        // The whole finding, in one line. If the label moves when the
        // microphone is taken, a status sentence has landed on the control
        // again — and the tap under it still ends the day.
        check("the label does not change when the microphone is taken, because the tap does not",
              face(listening: true, suspended: true).label
              == face(listening: true, suspended: false).label)

        check("...and the tap really is unchanged, so the label above is honest",
              face(listening: true, suspended: true).tap
              == face(listening: true, suspended: false).tap)

        // ------------------------------------------- 4. and it stops pretending
        // The one thing that MUST change while a call holds the input. Same
        // rule as the wave bars beside it, which already got this right.
        check("the microphone is taken, so nothing on the control breathes",
              face(listening: true, suspended: true).glyph == .symbol("mic"))

        // ------------------------------------------------ 5. iOS said no
        // A tap iOS will instantly refuse reads as the app being broken, so
        // there is no tap — and the label names the blocker instead of an
        // action, because a disabled control promises nothing.
        check("the microphone is switched off in Settings, so there is nothing to tap",
              face(blocked: true, listening: false, suspended: false)
              == .init(label: "Microphone is off", tap: .nothing,
                       glyph: .symbol("mic.slash")))

        // --------------------------------------------- 6. the sweep: label = tap
        // Every combination of the three inputs, because the defect was never
        // one wrong string — it was a label answering a different question from
        // the action underneath it, in a state nobody enumerated.
        var labelPromisesWhatItDoes = true
        var breathesOnlyWhenHearing = true
        var stopsWheneverListening = true
        for blocked in [false, true] {
            for listening in [false, true] {
                for suspended in [false, true] {
                    let f = face(blocked: blocked, listening: listening,
                                 suspended: suspended)
                    switch f.tap {
                    case .start:
                        if f.label != "Listen with phone" { labelPromisesWhatItDoes = false }
                    case .stop:
                        if f.label != "Stop listening" { labelPromisesWhatItDoes = false }
                    case .nothing:
                        // Nothing happens, so nothing may be promised.
                        if f.label == "Listen with phone" || f.label == "Stop listening" {
                            labelPromisesWhatItDoes = false
                        }
                    }
                    let hearing = ListenControlPolicy.capturing(isListening: listening,
                                                                suspended: suspended)
                    if (f.glyph == .breathingDot) != (hearing && !blocked) {
                        breathesOnlyWhenHearing = false
                    }
                    if !blocked, listening, f.tap != .stop { stopsWheneverListening = false }
                }
            }
        }
        check("in all 8 states the label names exactly the tap underneath it",
              labelPromisesWhatItDoes)
        check("in all 8 states the dot breathes only while she is actually hearing",
              breathesOnlyWhenHearing)
        check("in all 8 states a tap while listening stops listening, and says so",
              stopsWheneverListening)

        // ------------------------------------------------------- 7. capturing
        // The fact four different views used to spell out of `isListening`
        // alone. `isListening` is the owner's standing wish and survives a
        // whole phone call; this is the microphone.
        check("the mic is ours, so she is hearing you",
              ListenControlPolicy.capturing(isListening: true, suspended: false))
        check("something else has the mic, so she is not hearing you however much she wants to",
              !ListenControlPolicy.capturing(isListening: true, suspended: true))
        check("listening is off, so she is not hearing you",
              !ListenControlPolicy.capturing(isListening: false, suspended: false))

        // ------------------------------------------------------------- result
        print("")
        if failures.isEmpty {
            print("ListenControlPolicy: all \(checks) checks passed")
        } else {
            print("ListenControlPolicy: \(failures.count)/\(checks) FAILED")
            for f in failures { print("  - \(f)") }
            exit(1)
        }
    }
}
