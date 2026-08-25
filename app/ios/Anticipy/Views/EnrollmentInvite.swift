import SwiftUI

/// THE INVITE FIRST RUN NEVER MADE.
///
/// `VoiceEnrollView` is complete and its embedding model ships in every build,
/// and until this file existed the entire app presented it from ONE place: a
/// sheet inside Settings, under "Your voice", below Listening / Pendant / You.
/// To reach it a stranger had to tap the slider glyph in the Home toolbar and
/// scroll past three sections, with nothing anywhere suggesting they should.
///
/// `research/2026-08-24-engine-options.md:254` records what that costs:
/// `speaker` at 0% across 221 production events, cause "enrollment
/// unreachable", confidence "Certain". With no owner profile the tagger returns
/// nil for every line, so every promise anyone makes in the room is attributed
/// to nobody — the named cause of four of the six bad acts on the only call
/// ever scored.
///
/// -- Where this sits, and why not as a fifth beat -------------------------
///
/// First run is four beats — Hello, How I work, May I listen?, Where to reach
/// you — and `design/day-zero.md:237-239` already removed one page from it for
/// exceeding the ~70-second budget in CONSUMER-FEEL-DIRECTION §5. So this is
/// not a fifth page in the TabView: it is raised once the last beat is cleared,
/// before the celebration, and only when the answer can be yes. The four beats
/// keep their names, their count and their progress track.
///
/// -- ON NOT LYING TO A STRANGER -------------------------------------------
///
/// `SpeakerTagger.available` is FALSE in the build this ships in.
/// `project.yml` unlinked sherpa-onnx for the second time (commit d3ccb133)
/// because builds 76-80 delivered zero rows to production and build 75
/// delivered 313, so `VoiceEmbedderFactory.make()` returns nil and enrollment
/// cannot enrol anybody however many screens lead to it.
///
/// `EnrollmentOfferPolicy` is therefore consulted BEFORE this view is raised,
/// and today it answers `.cannot` — so first run offers nothing at all rather
/// than spending twelve seconds of a stranger's attention on a read that can
/// never produce a profile. The day the engine is re-linked, the invite is
/// already standing in front of every new person.
///
/// The check is made twice on purpose. The policy decides whether to RAISE this
/// screen; the screen asks again on appear, because a tagger read when
/// onboarding started is not a promise about the moment somebody taps Start.
/// When the second answer disagrees, this says so plainly instead of handing
/// over to a screen that cannot work — the same sentence Settings uses, and the
/// same one `VoiceEnrollView`'s own `unavailable` phase shows.
struct EnrollmentInvite: View {
    @EnvironmentObject var session: AnticipySession

    /// Fired when the person is done with this screen, whichever way they left
    /// it: enrolled, "not now", or told it cannot work here. The caller ends
    /// onboarding — nothing about learning a voice may be able to strand
    /// somebody outside the app, which is the mistake `hasOnboarded` at the
    /// tail of a 2.4s animation already made once.
    let onDone: () -> Void

    @State private var enrolling = false
    /// Re-read on appear rather than trusted from the caller.
    @State private var canEnrol = true

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()
            VStack(alignment: .leading, spacing: Theme.Space.roomy) {
                Spacer(minLength: 0)
                content
                Spacer(minLength: 0)
                footer
            }
            .padding(.horizontal, Theme.Space.card)
            .padding(.vertical, Theme.Space.roomy)
        }
        .grainOverlay()
        .onAppear { canEnrol = session.speakerTagger.available }
        .sheet(isPresented: $enrolling, onDismiss: onDone) {
            VoiceEnrollView().environmentObject(session)
        }
    }

    @ViewBuilder private var content: some View {
        VStack(alignment: .leading, spacing: Theme.Space.base) {
            if canEnrol {
                Text("One last thing. Let me learn your voice.")
                    .font(Theme.display(30))
                    .foregroundStyle(Theme.text)
                    .fixedSize(horizontal: false, vertical: true)
                Text("Then I can tell when it's you talking and when it's "
                     + "someone else, so I never mistake their plans for yours.")
                    .font(.system(size: 17))
                    .foregroundStyle(Theme.text2)
                    .fixedSize(horizontal: false, vertical: true)
                Text("It takes twelve seconds, and it stays on your phone. "
                     + "Not the recording, not a copy, nothing.")
                    .font(.system(size: 15))
                    .foregroundStyle(Theme.muted)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                // The honest state, in the same words Settings uses. Reached
                // only when the engine went away between the decision and this
                // screen; on the shipping build the invite is never raised.
                Text("That's everything.")
                    .font(Theme.display(30))
                    .foregroundStyle(Theme.text)
                Text("Learning voices needs a piece I don't have on this phone "
                     + "yet, so I won't ask you to read anything. Everything "
                     + "else works exactly as it does now.")
                    .font(.system(size: 17))
                    .foregroundStyle(Theme.text2)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    @ViewBuilder private var footer: some View {
        VStack(spacing: 4) {
            Button {
                Haptics.engage()
                if canEnrol { enrolling = true } else { onDone() }
            } label: {
                Text(canEnrol ? "Teach me your voice" : "Start living your day")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.glass)

            if canEnrol {
                // Skippable like every other beat. Nothing in first run blocks
                // the app, and re-teaching stays in Settings under "Your voice".
                Button("Not right now") { onDone() }
                    .buttonStyle(.ghost)
                    .frame(maxWidth: .infinity)
            } else {
                // Keep the primary capsule from jumping when the skip row is
                // absent, the same way OnboardingView's footer reserves it.
                Color.clear.frame(height: 44)
            }
        }
    }
}
