import SwiftUI

/// How first run ends — which is not one sentence, and used to be.
///
/// "Give me a day. You'll see." played over everybody. It played over the
/// person who had tapped "Not right now" on the microphone thirty seconds
/// earlier, and over the person iOS had refused on their behalf. To both of
/// them the last sentence of first run is a promise about a thing that is not
/// happening, and Home's own status line contradicts it one screen later —
/// "I'm not listening yet, tap Listen with phone" in `ContentView.swift`,
/// which gets this right.
///
/// CITED BY ITS WORDS, NOT ITS LINE NUMBER, and so is every reference below.
/// The first draft of this comment gave a line range in `ContentView`, and
/// that range held a toolbar modifier on the day it was written. A citation that
/// sends the next reader to unrelated code trains them out of reading
/// comments at all, and reading the comment above the line is the mechanism
/// this repo relies on most. Quoted copy survives edits above it; line
/// numbers do not. `run_first_run_copy_tests.sh` greps for these quotations,
/// so a citation that goes stale here fails a suite instead of misleading
/// somebody.
///
/// PURE, and lifted out of this file by `run_first_run_copy_tests.sh` rather
/// than copied into it: which of three sentences a phone has earned is a
/// decision, and a decision belongs somewhere it can be read without a
/// simulator.
///
/// IT READS THE OWNER'S STANDING WISH, NOT THE MICROPHONE. `ContentView`
/// warns that `isListening` is "the owner's standing wish, not a fact about
/// the microphone", and that warning is the reason to use it here
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
    /// the microphone beat says so in the same words one screen back.
    case blocked
    /// Nobody refused her. Nobody has said yes yet either.
    case silent

    /// LISTENING OUTRANKS EVERY OTHER FLAG, and the order is DEFENSIVE rather
    /// than corrective.
    ///
    /// AN EARLIER VERSION OF THIS COMMENT WAS FALSE ABOUT THIS CODEBASE, and
    /// it is written out here because somebody reasoning from it would have
    /// gone and "fixed" a problem that does not exist. It said `micBlocked`
    /// "latches on a refusal and is not re-derived from iOS on every read".
    /// It does not latch. `AnticipyApp.micBlocked` is
    /// `listener.permissionDenied`, and `PhoneListener.permissionDenied` is a
    /// COMPUTED property — two `SFSpeechRecognizer.authorizationStatus()`
    /// reads and one `AVAudioSession.recordPermission` read, evaluated on
    /// every access, nothing stored. There is no stale flag here to outrank,
    /// and nothing needs a cache or a refresh path.
    ///
    /// The honest argument is narrower and still holds: `listening &&
    /// micBlocked` is very nearly unreachable. `isListening` is set true in
    /// exactly one place — inside `PhoneListener.begin()` — and `start()`
    /// reaches `begin()` only after BOTH authorizations have come back
    /// granted. So the first branch is a guard against a combination that
    /// should never arrive, it costs nothing, and it means a phone that is
    /// audibly listening can never be told its microphone is switched off.
    /// Each branch below is then a sentence that is true when it is shown.
    static func of(listening: Bool, micBlocked: Bool) -> FirstRunEnding {
        if listening { return .listening }
        return micBlocked ? .blocked : .silent
    }

    var sentence: String {
        switch self {
        case .listening:
            return "Listening is on. You can stop it from Home at any time."
        case .blocked:
            return "Microphone access is off. You can turn it on in iOS Settings."
        case .silent:
            return "Listening is off. Turn it on from Home when you want to capture a conversation."
        }
    }
}

/// The ending: the whole screen turns champagne, three of the mark drift off
/// its edges, the mark itself sits small and white in the middle, and one
/// sentence says what was decided. Two haptics, a breath, and Home.
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
    /// NOT DEFAULTED, AND THAT IS THE FIX. These two shipped as `listening =
    /// true` and `micBlocked = false` while the call site still read
    /// `OnboardingFinale { celebrating = false }`. A trailing closure binds to
    /// the last parameter, so both defaults took hold, every ending collapsed
    /// back to `.listening`, and the exact bug this type was written to kill
    /// was still on the screen — under a green suite.
    ///
    /// A default is also a SECOND place for this answer to be wrong, and a
    /// silent one: changing `true` to `false` on that line rewrote the last
    /// sentence of first run for every person alive, including the one who had
    /// just granted the microphone, and no test could see it.
    ///
    /// Un-defaulted, the memberwise initialiser will not compile without both
    /// facts, so the wiring cannot quietly rot back out — a deleted argument
    /// is a build error, not a wrong sentence. `run_first_run_copy_tests.sh`
    /// additionally greps `AnticipyApp.swift` for the call and this file for a
    /// re-introduced default, because restoring one would make the old broken
    /// call compile again.
    ///
    /// Declared BEFORE `onDone` on purpose: a trailing closure binds to the
    /// last parameter, so `OnboardingFinale(listening:micBlocked:) { … }` keeps
    /// working only while `onDone` stays last.
    let listening: Bool
    /// `session.micBlocked` — iOS has refused, and she cannot ask again.
    let micBlocked: Bool

    /// Fired when the scene has said its piece, so the caller can take it down.
    /// Nothing depends on it: drop it and the app is merely stuck showing a
    /// finished animation, not stuck outside its own front door.
    let onDone: () -> Void

    @State private var arrived = false

    /// Computed off two immutable stored properties, so it is the same answer
    /// for the whole scene.
    private var ending: FirstRunEnding {
        .of(listening: listening, micBlocked: micBlocked)
    }

    var body: some View {
        ZStack {
            OnboardTheme.champagne.ignoresSafeArea()
            GiantMarks()
            VStack(spacing: 26) {
                OnboardMark(size: 48, stroke: .white, dot: .white)
                Text(ending.sentence)
                    .font(.system(size: 22))
                    .lineSpacing(5)
                    .foregroundStyle(.white)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 300)
                    // Two of the three endings are twice the length of the one
                    // this scene was laid out for; the sentence that says she
                    // cannot hear must not be the one that gets clipped.
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 40)
            .opacity(arrived ? 1 : 0)
            .scaleEffect(arrived ? 1 : 0.96)
        }
        .transition(.opacity)
        .onAppear {
            withAnimation(Theme.springSlow) { arrived = true }
            Haptics.pairing()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.55) { Haptics.taskDone() }
        }
        // A fixed curtain, not a chain of callbacks: nothing here can leave
        // the app without a path out of first run.
        .task {
            try? await Task.sleep(nanoseconds: 3_400_000_000)
            onDone()
        }
        // Tapping through is respected: this is the one screen where somebody is
        // being made to watch something.
        .onTapGesture { onDone() }
        .accessibilityAddTraits(.isModal)
    }
}
