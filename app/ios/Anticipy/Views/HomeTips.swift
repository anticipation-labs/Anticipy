import SwiftUI

/// Where Home's listen control is, reported up the tree so the coach mark can
/// point at it without Home knowing the coach mark exists.
struct ListenControlAnchorKey: PreferenceKey {
    static var defaultValue: Anchor<CGRect>? = nil
    static func reduce(value: inout Anchor<CGRect>?, nextValue: () -> Anchor<CGRect>?) {
        value = nextValue() ?? value
    }
}

/// The last three things first run says, over Home, then a pointer at the one
/// control that matters. Played once — the caller writes
/// `AppPreferences.homeTipsSeenKey` when this ends — and never on a phone whose
/// owner has already been listening, because a tip about a switch that is
/// already on is a tip about nothing.
///
/// Three cards over a dimmed Home: a small scene, a headline, one sentence, a
/// black pill, three dots. Then, if listening is not yet on, the dim lifts to
/// half and a bubble points at "Listen with phone". Tapping the switch itself
/// ends the scene; so does tapping the bubble, or waiting.
struct HomeTipsOverlay: View {
    /// The listen control's frame in this overlay's space, when Home has
    /// reported one. Without it the coach mark is skipped rather than guessed.
    let listenFrame: CGRect?
    /// The owner's standing wish. True means the coach mark has nothing to say.
    let listening: Bool
    /// iOS has the microphone switched off: Home's switch is inert, so a
    /// bubble telling somebody to tap it would point at a dead control.
    let micBlocked: Bool
    let onDone: () -> Void

    private enum Phase: Equatable { case tips, coach }
    @State private var phase: Phase = .tips
    @State private var index = 0
    @State private var shown = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private struct Tip {
        let headline: String
        let body: String
        let button: String
    }

    private static let tips: [Tip] = [
        Tip(headline: "Just talk. I'm listening.",
            body: "Turn listening on from Home whenever you want a conversation captured.",
            button: "Next"),
        Tip(headline: "Nothing sends without your OK",
            body: "Anticipy asks before anything is sent. Approve with a tap, or say not now.",
            button: "Next"),
        Tip(headline: "Bring in what you already use",
            body: "Connect your calendar, mail and contacts in Settings whenever you're ready.",
            button: "Done"),
    ]

    var body: some View {
        GeometryReader { geo in
            ZStack {
                // The dim. Under the tips it swallows every tap; under the
                // coach mark it lets them through so the switch it points at
                // is the switch you can press.
                OnboardTheme.dim
                    .opacity(phase == .tips ? 0.78 : 0.5)
                    .ignoresSafeArea()
                    .allowsHitTesting(phase == .tips)
                    .animation(Theme.springSlow, value: phase)

                if phase == .tips {
                    card
                        .padding(.horizontal, OnboardMetric.gutter)
                        .padding(.top, 176)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                        .transition(.opacity.combined(with: .move(edge: .bottom)))
                } else if let listenFrame {
                    // NOT modal: the whole point is that the control under
                    // it stays reachable, for VoiceOver as much as a thumb.
                    Button {
                        finish()
                    } label: {
                        CoachMark(text: "Start by tapping Listen with phone")
                    }
                    .buttonStyle(OnboardPressStyle(scale: 0.98))
                    .frame(width: geo.size.width - 2 * OnboardMetric.gutter)
                    .position(x: geo.size.width / 2,
                              y: max(60, listenFrame.minY - 12 - 26))
                    .transition(.opacity.combined(with: .move(edge: .bottom)))
                    .accessibilityHint("Dismisses this tip")
                }
            }
            .opacity(shown ? 1 : 0)
            .animation(Theme.springSlow, value: phase)
        }
        .onAppear {
            withAnimation(Theme.springSlow) { shown = true }
        }
        // Once the switch under the bubble is on, the bubble has been obeyed.
        .onChange(of: listening) { on in
            if on, phase == .coach { finish() }
        }
        .task(id: phase) {
            guard phase == .coach else { return }
            try? await Task.sleep(nanoseconds: 7_000_000_000)
            if phase == .coach { finish() }
        }
    }

    private var tip: Tip { Self.tips[min(index, Self.tips.count - 1)] }

    private var card: some View {
        VStack(spacing: 0) {
            hero
                .frame(height: 250)
                .frame(maxWidth: .infinity)
                .background(OnboardTheme.ground)
                .background(MarkPattern())
                .clipped()
            VStack(spacing: 10) {
                Text(tip.headline)
                    .font(.system(size: 26, weight: .semibold))
                    .tracking(-0.5)
                    .foregroundStyle(OnboardTheme.ink)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .id("h\(index)")
                    .transition(.opacity)
                Text(tip.body)
                    .font(.system(size: 16))
                    .lineSpacing(3)
                    .foregroundStyle(OnboardTheme.text2)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .id("b\(index)")
                    .transition(.opacity)
                Button {
                    Haptics.engage()
                    if index < Self.tips.count - 1 {
                        withAnimation(Theme.spring) { index += 1 }
                    } else if listening || micBlocked || listenFrame == nil {
                        finish()
                    } else {
                        withAnimation(Theme.springSlow) { phase = .coach }
                    }
                } label: {
                    Text(tip.button)
                        .id("p\(index)")
                        .transition(.opacity)
                }
                .buttonStyle(OnboardPillStyle(kind: .black, height: 46))
                .padding(.top, 8)
                PagerDots(count: Self.tips.count, index: index, stretches: false) { i in
                    withAnimation(Theme.spring) { index = i }
                }
                .padding(.top, 2)
            }
            .padding(.horizontal, 22)
            .padding(.top, 24)
            .padding(.bottom, 20)
            .background(OnboardTheme.card)
        }
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
        .shadow(color: .black.opacity(0.35), radius: 30, y: 30)
        .animation(Theme.spring, value: index)
        .accessibilityElement(children: .contain)
        .accessibilityAddTraits(.isModal)
    }

    @ViewBuilder private var hero: some View {
        ZStack {
            switch index {
            case 0:
                VStack(spacing: 16) {
                    HeroWave(color: OnboardTheme.ink, barWidth: 6, height: 60, bars: 9, gap: 6)
                    VStack(spacing: 4) {
                        Text("HEARD")
                            .font(.system(size: 12, weight: .semibold))
                            .tracking(1.6)
                            .foregroundStyle(OnboardTheme.muted)
                        Text("\u{201C}Let's do Thursday at two.\u{201D}")
                            .font(.system(size: 16))
                            .foregroundStyle(OnboardTheme.ink)
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                    .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(OnboardTheme.card))
                    .shadow(color: OnboardTheme.inkFixed.opacity(0.10), radius: 10, y: 8)
                }
            case 1:
                VStack(alignment: .leading, spacing: 4) {
                    Text("READY TO SEND")
                        .font(.system(size: 12, weight: .semibold))
                        .tracking(1.6)
                        .foregroundStyle(OnboardTheme.muted)
                    Text("The deck to Priya")
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(OnboardTheme.ink)
                    Text("Proposal_v3.pdf \u{00B7} to priya@\u{2026}")
                        .font(.system(size: 14))
                        .foregroundStyle(OnboardTheme.text2)
                    HStack(spacing: 8) {
                        Text("Send it")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(OnboardTheme.onInk)
                            .frame(maxWidth: .infinity)
                            .frame(height: 40)
                            .background(Capsule().fill(OnboardTheme.ink))
                        Text("Not now")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(OnboardTheme.ink)
                            .frame(maxWidth: .infinity)
                            .frame(height: 40)
                            .background(Capsule().fill(OnboardTheme.track))
                    }
                    .padding(.top, 12)
                }
                .padding(16)
                .frame(width: 270)
                .background(RoundedRectangle(cornerRadius: 20, style: .continuous).fill(OnboardTheme.card))
                .shadow(color: OnboardTheme.inkFixed.opacity(0.14), radius: 14, y: 10)
            default:
                VStack(spacing: 10) {
                    HStack(spacing: 10) {
                        connector("Calendar"); connector("Mail"); connector("Contacts")
                    }
                    HStack(spacing: 10) {
                        connector("Chrome"); connector("Mac app")
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .id(index)
        .transition(.opacity)
        .accessibilityHidden(true)
    }

    private func connector(_ name: String) -> some View {
        HStack(spacing: 8) {
            Circle().fill(OnboardTheme.champagne).frame(width: 8, height: 8)
            Text(name).font(.system(size: 15, weight: .semibold)).foregroundStyle(OnboardTheme.ink)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Capsule().fill(OnboardTheme.card))
        .shadow(color: OnboardTheme.inkFixed.opacity(0.08), radius: 8, y: 6)
    }

    private func finish() {
        withAnimation(Theme.springSlow) { shown = false }
        DispatchQueue.main.asyncAfter(deadline: .now() + (reduceMotion ? 0 : 0.45)) { onDone() }
    }
}
