import Foundation

/// What the listening control says, what tapping it does, and whether the
/// screen may show her as hearing you right now.
///
/// THE DOOR THIS CLOSES, 2026-08-25. The interruption work made the button's
/// label honest — "Waiting for the microphone" instead of "Listening with
/// phone" while a call held the input — and left its ACTION alone. The action
/// was keyed on `isListening`, which stays true for the whole of a call, so the
/// tap still called `stopListening()`. The biggest type on the home screen
/// became a passive status sentence sitting on the control that ends the day:
/// an owner who opens the app during a call, sees a pulsing dot beside a
/// sentence and taps it to hurry things along has turned listening off until
/// they toggle it back by hand. That is the exact ending the interruption work
/// set out to close, reached through a door the same commit installed.
///
/// THE RULE THIS FILE ENFORCES: **a control's label describes what tapping it
/// does.** Not what is happening. Taking the microphone away does not change
/// what this button does, so it must not change what the button says it does —
/// and `face` returning one value for the label, the tap and the glyph
/// together is what stops those three drifting apart again. "Stop listening" is
/// the same words the Settings screen has always used for the same action.
///
/// WHERE THE STATE WENT INSTEAD. Nowhere new: the home card's banner already
/// reads "Mic interrupted, taking it back…" while `suspended`, the briefing
/// says "Something else has the microphone right now.", and `capturing` below
/// stops the dot and the bars from claiming otherwise. Three honest statements
/// and no fourth one on the button — a status sentence repeated onto the
/// control is what invited the tap.
///
/// Pure Foundation, like `ListenResumePolicy` and `ListenWatchdogPolicy`: a
/// decision that can be shown to fail with `swiftc` alone, with no simulator
/// and no device that has to receive a real phone call. Labels are strings and
/// glyphs are symbol names, so all four facts about the control fit in one
/// value that a test can sweep — which is the point, because the defect was
/// never one wrong string. It was two right answers to different questions
/// rendered on the same control.
struct ListenControlPolicy {
    /// What a tap does. `.nothing` is a real answer, not an absence: iOS
    /// refuses a start with the microphone switched off in Settings, and a
    /// button that reads as broken is worse than one that is plainly disabled.
    enum Tap: Equatable {
        case start
        case stop
        case nothing
    }

    /// What sits beside the words. The breathing dot means "she is doing
    /// something right now" — it is the screen's one claim about the present
    /// tense, so it is decided here with the label rather than beside it.
    enum Glyph: Equatable {
        case breathingDot
        case symbol(String)
    }

    struct Face: Equatable {
        let label: String
        let tap: Tap
        let glyph: Glyph
    }

    /// THE ORDER IS THE BEHAVIOUR. Each line is only meaningful because the
    /// ones above it did not fire.
    static func face(micBlocked: Bool,
                     isListening: Bool,
                     suspended: Bool) -> Face {
        // A microphone iOS has switched off outranks everything: there is no
        // action to name, only the reason there isn't one. The one label here
        // that is not a verb, and the only one on a control that cannot be
        // tapped — a disabled control promises nothing, so it is free to say
        // what is wrong instead.
        if micBlocked {
            return Face(label: "Microphone is off", tap: .nothing,
                        glyph: .symbol("mic.slash"))
        }

        // Off, and a tap turns her on.
        if !isListening {
            return Face(label: "Listen with phone", tap: .start,
                        glyph: .symbol("mic"))
        }

        // On — and the label is the same whether or not the microphone is
        // ours this second, BECAUSE THE TAP IS THE SAME. What changes is the
        // glyph: hollow and still while something else holds the input, since
        // a dot that breathes over a call is the screen claiming to hear.
        return Face(label: "Stop listening", tap: .stop,
                    glyph: suspended ? .symbol("mic") : .breathingDot)
    }

    /// Is she actually hearing you at this moment?
    ///
    /// `isListening` is the owner's standing WISH and it stays true for the
    /// whole of a phone call, so four screens spelling this out of it spoke
    /// over a microphone something else was holding: the listening control's
    /// own dot, the greeting dot, the settings headline ("I'm listening on this
    /// phone.") — in her own first-person voice, directly above the sentence
    /// admitting it — and the briefing's idle line ("All quiet on my end. I've
    /// got the watch."). One line, in one place, so they cannot drift again.
    ///
    /// A FIFTH SITE ASKS `isListening` AND SHOULD KEEP ASKING IT: onboarding's
    /// "I'm listening. Thank you." answers whether PERMISSION landed, not
    /// whether the microphone is ours this second, and moving it here would
    /// drop someone who had just granted the microphone into the copy that asks
    /// them to grant it. `run_control_policy_tests.sh` scopes its scan away
    /// from that file for the same reason and says so there. The count is spelt
    /// out because the previous version of this note said four places and left
    /// the fifth unmentioned, which reads as a closed count that is open.
    static func capturing(isListening: Bool, suspended: Bool) -> Bool {
        isListening && !suspended
    }
}
