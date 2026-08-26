import Foundation

// What a field says about itself, and the silence this type was built to end.
//
// Settings' number field had two captions where it needed four. `e164` returns
// nil without a country code, `saveOwnerPhone` opens with
// `guard let e = e164(raw) else { return false }`, and the screen's only state
// was a `phoneSaved` bool — so typing "+44" and pressing Save set false over
// false and the caption went on showing its neutral default. Nothing on the
// screen said anything had happened. This suite is the four states, the order
// they resolve in, and the two sentences that must not vary between the three
// fields in this app that take a phone number.
//
// The enum under test is LIFTED out of Theme.swift by the runner, never copied.
// A copy is honest exactly until somebody edits one side of it.

var failures = 0
func check(_ name: String, _ ok: Bool) {
    print("\(ok ? "PASS" : "FAIL"): \(name)")
    if !ok { failures += 1 }
}

// The words Settings actually ships. `valid` is nil: a dialable-but-unsaved
// number has nothing extra to say on a screen where saving is its own button.
let settings = FieldCaption.Words(
    neutral: "Where I text you when something needs your word.",
    saved: "Saved. I'll reach you here.")

// The first-run beat's shape, for the adoption this component is built for.
let firstRun = FieldCaption.Words(
    neutral: "",
    saved: "Saved. I'll text you there.",
    valid: "That's you")

// ---------------------------------------------------------------- the states

// An empty field is neutral, never wrong. Nobody has typed anything, and
// telling somebody what is missing from nothing is the app arguing with its
// own blank.
check("an empty field is neutral even under a rule that would refuse it",
      FieldCaption.state(text: "", complete: false, attempt: .untried) == .neutral)
check("an empty field with no rule at all is neutral",
      FieldCaption.state(text: "", complete: nil, attempt: .untried) == .neutral)

// THE BUG, in one line. This is the state that did not exist.
check("a country code on its own is not yet valid",
      FieldCaption.state(text: "+44", complete: false, attempt: .untried) == .notYetValid)
check("a whole number is valid",
      FieldCaption.state(text: "+447700900123", complete: true, attempt: .untried) == .valid)

// A field with no completeness rule cannot be incomplete. Passing `true` there
// would be this type claiming a name had been checked when nothing checked it.
check("a field with no rule never reports not-yet-valid",
      FieldCaption.state(text: "Jose", complete: nil, attempt: .untried) == .neutral)

// The server's answer outranks anything the field can say about itself: it is
// newer, and every caller clears the attempt on a keystroke, so it is always
// about this exact text.
check("a save that landed outranks the text",
      FieldCaption.state(text: "+44", complete: false, attempt: .saved) == .saved)
check("a save that failed outranks a valid number",
      FieldCaption.state(text: "+447700900123", complete: true, attempt: .failed) == .saveFailed)
check("a save that failed outranks an empty field",
      FieldCaption.state(text: "", complete: false, attempt: .failed) == .saveFailed)

// -------------------------------------------------------------- the fallback

// The champagne tick means one thing in this app. Beside "Where I text you
// when something needs your word." it would mean two — dialable, and SAVED —
// on the one screen where saving is a separate button.
check("a valid value with nothing to say for it falls back to neutral",
      FieldCaption.rendered(.valid, hasValidWords: false) == .neutral)
check("a valid value with its own sentence keeps it",
      FieldCaption.rendered(.valid, hasValidWords: true) == .valid)
check("a landed save is never collapsed",
      FieldCaption.rendered(.saved, hasValidWords: false) == .saved)
check("a refused value is never collapsed",
      FieldCaption.rendered(.notYetValid, hasValidWords: false) == .notYetValid)
check("a failed save is never collapsed",
      FieldCaption.rendered(.saveFailed, hasValidWords: false) == .saveFailed)

// --------------------------------------------------------------- the wording

check("neutral says what the field is for",
      FieldCaption.sentence(.neutral, settings) == "Where I text you when something needs your word.")
check("a valid value with no sentence of its own borrows neutral's",
      FieldCaption.sentence(.valid, settings) == settings.neutral)
check("a valid value with its own sentence uses it",
      FieldCaption.sentence(.valid, firstRun) == "That's you")
check("saved says what saving bought",
      FieldCaption.sentence(.saved, settings) == "Saved. I'll reach you here.")

// The two that must be identical on all three fields, spelled out here rather
// than referenced, so an edit to the constant has to be an edit to this file
// too. The runner separately checks that both still match what OnboardingView
// ships.
check("the refusal names what is missing",
      FieldCaption.sentence(.notYetValid, settings)
      == "That doesn't look like a full number yet — country code and all.")
check("the failure names the cause and blames nobody",
      FieldCaption.sentence(.saveFailed, settings)
      == "I couldn't save that just now. I need a connection to keep it.")
check("the refusal is the same sentence on the first-run beat",
      FieldCaption.sentence(.notYetValid, firstRun) == FieldCaption.sentence(.notYetValid, settings))
check("the failure is the same sentence on the first-run beat",
      FieldCaption.sentence(.saveFailed, firstRun) == FieldCaption.sentence(.saveFailed, settings))

// ------------------------------------------------- the Settings journey, end to end

/// What the screen renders, exactly as `FieldCaptionLine.init` composes it.
func shown(_ text: String, _ complete: Bool?, _ attempt: FieldCaption.Attempt,
           _ words: FieldCaption.Words) -> (FieldCaption.State, String) {
    let s = FieldCaption.rendered(
        FieldCaption.state(text: text, complete: complete, attempt: attempt),
        hasValidWords: words.valid != nil)
    return (s, FieldCaption.sentence(s, words))
}

// Open Settings having never saved a number: the field arrives holding this
// phone's own dialling code, and the caption says what is still missing.
let opened = shown("+44", false, .untried, settings)
check("opening on a bare dialling code reports what is missing",
      opened.0 == .notYetValid
      && opened.1 == "That doesn't look like a full number yet — country code and all.")

// Type the rest. Nothing is claimed until Save is pressed, so the caption goes
// back to saying what the field is for — no tick, because nothing is saved.
let typed = shown("+447700900123", true, .untried, settings)
check("a whole unsaved number claims nothing",
      typed.0 == .neutral && typed.1 == "Where I text you when something needs your word.")

// Press Save with no connection. THIS is the sentence that did not exist: the
// old screen showed the line above and the person learned nothing.
let offline = shown("+447700900123", true, .failed, settings)
check("a save that never reached the server says so",
      offline.0 == .saveFailed
      && offline.1 == "I couldn't save that just now. I need a connection to keep it.")

// Press Save with one.
let landed = shown("+447700900123", true, .saved, settings)
check("a save that landed says so",
      landed.0 == .saved && landed.1 == "Saved. I'll reach you here.")

// And the two failures that used to arrive as one silent `false` are now two
// different sentences, which is the whole of fix 7.
check("a refused number and a refused connection do not read the same",
      opened.1 != offline.1)

// ------------------------------------------------------------------ the details field

let details = FieldCaption.Words(
    neutral: "Every booking and signup form asks for these. Payment details are never stored or filled.",
    saved: "Saved. I can fill booking forms myself now.")

// `complete: nil` — nothing in this app validates a name, an email or a
// birthday, so the field must never claim one is wrong.
for text in ["", "Jose", "  ", "not-an-email"] {
    check("details with \"\(text)\" never reads as refused",
          shown(text, nil, .untried, details).0 == .neutral)
}
check("details still report a save that did not land",
      shown("Jose", nil, .failed, details).1
      == "I couldn't save that just now. I need a connection to keep it.")

if failures > 0 {
    print("\(failures) check(s) failed")
    exit(1)
}
print("field caption: four states, one order, two sentences that cannot drift")
