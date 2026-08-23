import SwiftUI

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
struct OnboardingFinale: View {
    /// Fired when the scene has said its piece, so the caller can take it down.
    /// Nothing depends on it: drop it and the app is merely stuck showing a
    /// finished animation, not stuck outside its own front door.
    let onDone: () -> Void

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
                TypewriterText(text: "Give me a day. You'll see.",
                               font: Theme.display(30),
                               color: Theme.text)
                    .multilineTextAlignment(.center)
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
