// What first run SAYS, and whether it is true when it says it.
//
// Three decisions, all of them about words, all of them previously made inline
// in a SwiftUI body where nothing could read them:
//
//   FirstRunTrack   — which beat you are on, out of how many. It opened at
//                     "1 of 4" over somebody who had just typed an email, a
//                     password and a phone number at the door, and counted all
//                     of that as zero.
//   ConfirmBeat     — what the last beat may claim it already holds. The one
//                     fixed sentence this screen was prescribed ("Your email
//                     and number came in at the door.") is false on the sign-in
//                     path and false again on an account with no number, so the
//                     sentence is built from what is actually on file.
//   FirstRunEnding  — how first run ends. "Give me a day. You'll see." played
//                     over the person who had declined the microphone thirty
//                     seconds earlier, and over the person iOS had refused on
//                     their behalf.
//
// Every one of them is compiled from the real production source by the runner,
// against Foundation ALONE — so the moment a copy decision reaches for a Color,
// a Font or a View, this suite stops building. A sentence whose truth cannot be
// checked without a simulator is a sentence nobody is checking.
//
// Run: sh app/ios/Tests/run_first_run_copy_tests.sh
import Foundation

var failures = 0
func check(_ name: String, _ ok: Bool) {
    print("\(ok ? "PASS" : "FAIL"): \(name)")
    if !ok { failures += 1 }
}

// The four pages OnboardingView actually has. Written once here, so that if the
// walkthrough gains or loses a page these checks move with it rather than
// quietly testing a shape the app no longer has.
let pages = 4

// ===================================================== THE TRACK, AND THE DOOR
//
// The whole fix in one line: the first thing this track can say about somebody
// is no longer that they are at the beginning.

check("the track counts five beats, not four", FirstRunTrack.count == 5)
check("the first beat is the account they already made",
      FirstRunTrack.beatNames.first == "Your account")
check("one beat is behind the first page of this view",
      FirstRunTrack.offset(pageCount: pages) == 1)

// The honest delta the audit named: "How I work" was 2 of 4 and is now 3 of 5.
check("the welcome beat is Hello, second of five",
      FirstRunTrack.name(step: 0, pageCount: pages) == "Hello"
        && FirstRunTrack.ordinal(step: 0, pageCount: pages) == 2)
check("how-it-works is third of five, not second of four",
      FirstRunTrack.name(step: 1, pageCount: pages) == "How I work"
        && FirstRunTrack.ordinal(step: 1, pageCount: pages) == 3)
check("the microphone beat is fourth of five",
      FirstRunTrack.name(step: 2, pageCount: pages) == "May I listen?"
        && FirstRunTrack.ordinal(step: 2, pageCount: pages) == 4)
check("the number beat is last of five",
      FirstRunTrack.name(step: 3, pageCount: pages) == "Where to reach you"
        && FirstRunTrack.ordinal(step: 3, pageCount: pages) == 5)

// THE RULE, stated as a rule rather than as four examples. While the door is
// behind this view, no page of it may be called the first thing that happened.
for step in 0 ..< pages {
    check("step \(step) is never announced as the beginning",
          FirstRunTrack.ordinal(step: step, pageCount: pages) > 1)
}

// EVERY NAME MOVED WITH THE COUNT. Leaving `beatNames[step]` against a
// five-element array is the shape of this fix going half-done: the numbers
// would read 2, 3, 4, 5 while every beat wore the name of the one before it.
check("no beat wears the name of the beat before it",
      (0 ..< pages).allSatisfy {
          FirstRunTrack.name(step: $0, pageCount: pages)
            == FirstRunTrack.beatNames[$0 + 1]
      })

// The spoken count and the printed count are built from one place, so they
// cannot drift into disagreeing about which beat somebody is standing on.
check("VoiceOver hears the same count the screen prints",
      FirstRunTrack.spokenLabel(step: 1, pageCount: pages) == "Step 3 of 5, How I work")

// CLAMPED, NOT TRUSTED. A fifth Step added without a fifth name is a subscript
// out of range — a crash, on a stranger's first run, out of a copy change.
check("a step past the end does not walk off the array",
      FirstRunTrack.name(step: 99, pageCount: pages) == "Where to reach you")
check("a negative step does not walk off the array",
      FirstRunTrack.name(step: -5, pageCount: pages) == "Your account")
check("more pages than names still answers",
      FirstRunTrack.name(step: 0, pageCount: 40) == "Your account")

// ============================================== WHAT THE LAST BEAT MAY CLAIM
//
// The load-bearing property, and it is not any single sentence: across every
// combination of what is and is not on file, this page never names a fact it
// does not hold. That is the whole difference between a confirmation and a
// confident lie, on the screen that decides whether she can ever reach you.

for hasEmail in [true, false] {
    for hasPhone in [true, false] {
        for hasName in [true, false] {
            let lead = ConfirmBeat.lead(hasEmail: hasEmail, hasPhone: hasPhone,
                                        hasFirstName: hasName)
            let shape = "email:\(hasEmail) phone:\(hasPhone) name:\(hasName)"

            if !hasEmail {
                check("no email on file, none claimed — \(shape)",
                      !lead.contains("Your email is already")
                        && !lead.contains("email and number are already"))
            }
            if !hasPhone {
                check("no number on file, none claimed — \(shape)",
                      !lead.contains("Your number is already")
                        && !lead.contains("email and number are already"))
            }
            // "The one thing I'm missing" is a count, and it is allowed to be
            // said only when the count is one.
            let missing = [hasName, hasEmail, hasPhone].filter { !$0 }.count
            if lead.contains("The one thing I'm missing") {
                check("\"the one thing\" is only said over one thing — \(shape)",
                      missing == 1)
            }
            if missing > 1 {
                check("more than one gap is named as more than one — \(shape)",
                      lead.contains("I still need"))
            }
            check("the lead is never empty — \(shape)", !lead.isEmpty)
        }
    }
}

// THE CASE EVERYBODY ACTUALLY WALKS. Sign-up requires an email and a number
// before the door will open at all, and nothing restores a first name across a
// sign-out, so this is the shape almost every real first run arrives in.
check("the ordinary first run confirms two facts and asks for one",
      ConfirmBeat.lead(hasEmail: true, hasPhone: true, hasFirstName: false)
        == "Your email and number are already on your account. The one thing I'm missing is your first name — it's what a booking form asks for that I can't work out.")

check("with nothing missing it stops asking",
      ConfirmBeat.lead(hasEmail: true, hasPhone: true, hasFirstName: true)
        == "Your email and number are already on your account. Have a look before we start.")

// THE TITLE IS A CLAIM TOO. "This is what I have." over a page holding nothing
// is the same falsehood one register quieter, so with nothing on file the beat
// asks its old question instead.
check("the title claims to hold something only when it does",
      ConfirmBeat.title(hasEmail: true, hasPhone: true) == "This is what I have."
        && ConfirmBeat.title(hasEmail: true, hasPhone: false) == "This is what I have."
        && ConfirmBeat.title(hasEmail: false, hasPhone: true) == "This is what I have."
        && ConfirmBeat.title(hasEmail: false, hasPhone: false) == "Where should I reach you?")

// The reason a first name is asked for at all, kept in the sentence that asks.
check("the first name still says why it cannot be worked out",
      ConfirmBeat.lead(hasEmail: true, hasPhone: true, hasFirstName: false)
        .contains("booking form"))

// ============================================================== THE ENDING
//
// Three endings, and the argument is the ORDER as much as the words.

check("someone listening gets the ending this scene was written for",
      FirstRunEnding.of(listening: true, micBlocked: false) == .listening)
// THIS CHECK USED TO CARRY A FALSE REASON, and the reason mattered more than
// the check: it said `micBlocked` "LATCHES on a refusal and is not re-derived
// from iOS on every read". It does not latch. `AnticipyApp.micBlocked` is
// `listener.permissionDenied`, a COMPUTED property that performs three live
// iOS authorization reads on every access and stores nothing. Anybody
// reasoning from the old sentence would have gone looking for a cache to
// invalidate that was never there.
//
// The true reason for the order is narrower. `isListening` is set true in
// exactly one place, inside `PhoneListener.begin()`, which is reachable only
// after both authorizations come back granted — so `listening && micBlocked`
// should never occur at all. This pins the branch that handles it anyway,
// because a phone that is audibly listening must never be told its microphone
// is switched off.
check("listening outranks a refusal flag it should never see",
      FirstRunEnding.of(listening: true, micBlocked: true) == .listening)
check("iOS having refused is its own ending",
      FirstRunEnding.of(listening: false, micBlocked: true) == .blocked)
check("declining is not the same event as being refused",
      FirstRunEnding.of(listening: false, micBlocked: false) == .silent)

check("the listening ending is unchanged, to the character",
      FirstRunEnding.listening.sentence == "Give me a day. You'll see.")

let endings: [FirstRunEnding] = [.listening, .blocked, .silent]
check("three endings, three sentences",
      Set(endings.map(\.sentence)).count == 3)

// NOTHING HERE MAY BECOME A THREAT. This screen is the last thing first run
// says to a person who has just been asked for their microphone all day, and
// the one principle this whole audit refused to apply literally is the one that
// would put a countdown or a percentage on exactly this surface. A character
// gate, not a reading of meaning: no sentence may carry a number at all.
for ending in endings {
    check("\(ending) states a fact, never a score",
          !ending.sentence.contains("%")
            && !ending.sentence.contains(where: \.isNumber))
}

// AND THE TWO THAT NAME A PROBLEM MUST NAME THE SWITCH. A sentence that says
// she cannot hear and stops there is the guilt-worded dismiss wearing the
// house voice; both of these say where the control is and then stop.
check("the declined ending points at the switch on Home",
      FirstRunEnding.silent.sentence.contains("home screen"))
check("the refused ending points at iOS Settings",
      FirstRunEnding.blocked.sentence.contains("Settings"))
// Neither one asks again. The ask was made one screen back and answered.
for ending in [FirstRunEnding.blocked, FirstRunEnding.silent] {
    check("\(ending) does not ask a second time",
          !ending.sentence.contains("?"))
}

print(failures == 0 ? "all first-run copy checks passed" : "\(failures) FAILED")
exit(failures == 0 ? 0 : 1)
