import SwiftUI

/// How first run ends — which is not one sentence, and used to be.
///
/// "Give me a day. You'll see." played over everybody. It played over the
/// person who had tapped "Not right now" on the microphone thirty seconds
/// earlier, and over the person iOS had refused on their behalf. To both of
/// them the last sentence of first run is a promise about a thing that is not
/// happening, and Home's own first sentence contradicts it one screen later
/// (`ContentView.swift:1241-1244`, which gets this right).
///
/// PURE, and lifted out of this file by `run_first_run_copy_tests.sh` rather
/// than copied into it: which of three sentences a phone has earned is a
/// decision, and a decision belongs somewhere it can be read without a
/// simulator.
///
/// IT READS THE OWNER'S STANDING WISH, NOT THE MICROPHONE. `ContentView`
/// warns at `:1172-1176` that `isListening` is "the owner's standing wish, not
/// a fact about the microphone", and that warning is the reason to use it here
/// rather than a reason not to: the wish is precisely what this sentence is
/// about. Read off `capturing` instead, a phone call holding the microphone
/// for four seconds at the wrong moment would make the app call somebody a
/// decliner in the one breath it has to thank them.
///
/// No badge, no countdown, no second ask. Two of these three sentences name a
/// thing that is not working; both name where the switch is and stop. Nobody
/// is being hurried, and nobody is being graded.
enum FirstRunEnding: Equatable {
    /// She was told yes, and iOS agreed.
    case listening
    /// iOS has the microphone switched off. She cannot ask again from here —
    /// `micPrimer` says so in the same words one screen back.
    case blocked
    /// Nobody refused her. Nobody has said yes yet either.
    case silent

    /// LISTENING OUTRANKS EVERY OTHER FLAG, and the order is the argument.
    /// `micBlocked` is `listener.permissionDenied`, which latches on a refusal
    /// and is not re-derived from iOS on every read — so a phone that is
    /// audibly listening must never be told its microphone is switched off,
    /// whatever an older flag still says. Each branch below is then a sentence
    /// that is true at the moment it is shown.
    static func of(listening: Bool, micBlocked: Bool) -> FirstRunEnding {
        if listening { return .listening }
        return micBlocked ? .blocked : .silent
    }

    var sentence: String {
        switch self {
        case .listening:
            return "Give me a day. You'll see."
        case .blocked:
            return "iOS has my microphone switched off, so I can't hear anything yet. It's one tap in Settings."
        case .silent:
            return "I can't hear anything yet. The switch is on the home screen, whenever you're ready."
        }
    }
}

/// The ending someone will describe to a friend: the mark, two rings collapsing
/// inward, two haptics, one typed sentence, and a dissolve. The rising haze
/// this used to open with is gone — the champagne haze is off every surface in
/// the product, and the collapsing rings were always the thing being watched.
///
/// IT RECORDS NOTHING. This scene used to live inside OnboardingView and carried
/// the only `hasOnboarded = true` in the app, at the tail of a chain that had to
/// run uninterrupted for about 2.4 seconds: the typewriter finishing, calling
/// back, and a further 1.4s sleep. Anything that cut those seconds short —
/// backgrounding the app, force-quitting, the view being torn down — left the
/// flag false, so the person did all five steps again on the next launch with
/// their name, email and number already on file. A celebration is decoration; it
/// must never be the thing that decides whether somebody is let into the app.
///
/// So the caller writes the durable flag FIRST and plays this over the top. If
/// it is interrupted, the only thing lost is the animation.
///
/// WHICH IS ALSO WHY THE TWO FACTS ARRIVE AS PARAMETERS rather than off an
/// `@EnvironmentObject`. A missing environment object is a crash, and this view
/// is the last screen of first run: nothing decorative here may be able to take
/// the app down at the finish line. Two inert booleans cannot.
struct OnboardingFinale: View {
    /// Whether the owner's standing wish is to be listening — `isListening`,
    /// not `capturing`. See `FirstRunEnding`.
    ///
    /// DEFAULTED TO TODAY'S BEHAVIOUR, AND UNWIRED. The call site is
    /// `AnticipyApp.swift`, which this change does not own; until it passes
    /// these, every ending is `.listening` and this screen behaves exactly as
    /// it shipped. One line closes it:
    ///
    ///     OnboardingFinale(listening: session.listener.isListening,
    ///                      micBlocked: session.micBlocked) { celebrating = false }
    ///
    /// Declared BEFORE `onDone` on purpose: a trailing closure binds to the
    /// last parameter, so the existing `OnboardingFinale { … }` call keeps
    /// compiling only while `onDone` stays last.
    var listening = true
    /// `session.micBlocked` — iOS has refused, and she cannot ask again.
    var micBlocked = false

    /// Fired when the scene has said its piece, so the caller can take it down.
    /// Nothing depends on it: drop it and the app is merely stuck showing a
    /// finished animation, not stuck outside its own front door.
    let onDone: () -> Void

    /// Computed off two immutable stored properties, so it is the same answer
    /// for the whole 3.2 seconds. That matters more than it looks:
    /// `TypewriterText` keys its typing loop on `.task(id: text)`, so a
    /// sentence that changed mid-scene would restart the typing from empty in
    /// front of the person.
    private var ending: FirstRunEnding {
        .of(listening: listening, micBlocked: micBlocked)
    }

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()
            VStack(spacing: Theme.Space.roomy) {
                ZStack {
                    RadarRipple(inward: true)
                    RadarRipple(inward: true, delay: 0.8)
                    LogoMark(size: 132)
                }
                .frame(height: 190)
                TypewriterText(text: ending.sentence,
                               font: Theme.display(30),
                               color: Theme.text)
                    .multilineTextAlignment(.center)
                    // Two of the three endings are three times the length of
                    // the one this scene was laid out for. A serif at 30pt has
                    // to be allowed its own height or the sentence that says
                    // she cannot hear is the sentence that gets clipped.
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 28)
        }
        .transition(.opacity)
        .onAppear {
            Haptics.pairing()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.55) { Haptics.taskDone() }
        }
        // A fixed curtain, not a chain of callbacks. The old version depended on
        // TypewriterText calling back — and TypewriterText has a `guard typing
        // else { return }` that can leave the loop WITHOUT calling onDone, which
        // silently removed the only path out of onboarding.
        .task {
            try? await Task.sleep(nanoseconds: 3_200_000_000)
            onDone()
        }
        // Tapping through is respected: this is the one screen where somebody is
        // being made to watch something.
        .onTapGesture { onDone() }
        .accessibilityAddTraits(.isModal)
    }
}
