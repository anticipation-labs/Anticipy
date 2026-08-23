import SwiftUI

/// One connection, asked for at the moment your own words made it necessary.
///
/// This is a deliberate clone of the shipped `micPrimer`
/// (`OnboardingView.swift:403`), which is the realised form of the canon: one
/// question, the promises as a RULE LIST rather than four symbol-and-card rows,
/// a skip of equal weight, and a recovery route when iOS says no.
///
/// The typewriter is **not** used here. `design/CONSUMER-FEEL-DIRECTION-2026-08-03.md`
/// §2.7 bans it on permission explanations — "where a companion becomes twee".
/// Somebody deciding whether to hand over their address book should not be made
/// to wait for the sentence to finish typing.
struct ContextAskSheet: View {
    let source: ContextSource
    /// The words that provoked the ask, so it can never read as unexpected —
    /// the single highest-leverage variable on whether it is granted.
    let heard: String
    /// The word from that sentence the question should name. Without it the
    /// contacts ask collapses into the generic form the voice law bans.
    var subject: String? = nil
    @EnvironmentObject var session: AnticipySession
    @Environment(\.dismiss) private var dismiss

    @State private var asking = false
    @State private var refused = false

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Space.base) {
            LogoMark(size: 56)
                .accessibilityHidden(true)
                .padding(.bottom, Theme.Space.tight)

            // The one lit thing on the surface, and it is a question.
            Text(source.ask(subject: subject))
                .font(Theme.display(28))
                .foregroundStyle(Theme.text)
                .fixedSize(horizontal: false, vertical: true)

            Text(source.because(heard, subject: subject))
                .font(Theme.voice)
                .foregroundStyle(Theme.text2)
                .fixedSize(horizontal: false, vertical: true)

            VStack(alignment: .leading, spacing: Theme.Space.snug) {
                ForEach(source.promises, id: \.self) { promise in
                    // A rule list still (`CONSUMER-FEEL-DIRECTION` §3d), just
                    // without the rule: one promise per line, held apart by
                    // space and flush with the question above them. The
                    // hairline that stood beside each one is gone from every
                    // surface, and the hanging indent went with it — an indent
                    // clearing nothing is just a crooked left edge.
                    Text(promise)
                        .font(Theme.aside)
                        .foregroundStyle(Theme.text2)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(.top, Theme.Space.tight)

            if refused {
                // A denied permission must never be terminal
                // (`CONSUMER-READINESS` B1: "Deny the microphone once and the
                // app is permanently broken").
                VStack(alignment: .leading, spacing: Theme.Space.tight) {
                    Text("iPhone said no, and it won't ask again. Only you can turn it back on.")
                        .font(Theme.aside)
                        .foregroundStyle(Theme.text)
                        .fixedSize(horizontal: false, vertical: true)
                    // A recovery route inside a card, so it is secondary to
                    // the page's own yes.
                    Button("Open iPhone Settings") { session.openSystemSettings() }
                        .buttonStyle(.ghost)
                }
                .cardSurface()
            }

            Spacer(minLength: Theme.Space.base)

            Button {
                asking = true
                Task {
                    let ok = await session.grantContext(source)
                    asking = false
                    if ok { dismiss() } else { withAnimation(Theme.spring) { refused = true } }
                }
            } label: {
                Text(asking ? "Asking iPhone…" : "Yes, go ahead")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.glass)
            // Disabled dimming belongs to the style, so it is the same 0.45
            // on every screen instead of a per-sheet guess.
            .disabled(asking)

            // Skip is a real button at a real size, not a 13pt grey footnote.
            // `design/PREMIUM-FEEL.md:45` asks for exactly this.
            Button {
                session.declineContext(source)
                dismiss()
            } label: {
                Text("Not now")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.ghost)
        }
        .padding(.horizontal, 28)
        .padding(.top, Theme.Space.section)
        .padding(.bottom, 18)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Theme.bg.ignoresSafeArea())
        .grainOverlay()
    }
}
