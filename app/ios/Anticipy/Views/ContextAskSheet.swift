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
///
/// TWO STATES, AND THE SECOND ONE IS THE POINT. A yes used to close this sheet
/// the instant iOS answered: she took the address book and the surface that
/// asked for it disappeared, which is the shape of a thing that got what it
/// came for. The grant now stays on screen long enough to show what actually
/// travelled — the posted lines themselves, and a count of any that did not
/// fit. `design/day-zero.md` §2-3 already requires exactly this of the
/// supervised read ("watching her open a tab … teaches, in one gesture"); the
/// two sources read on this phone owe it just as much, precisely because they
/// are read in milliseconds with nothing to watch.
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
    /// The lines she just sent herself. Nil is the ask state — nothing taken
    /// yet, so there is nothing to show back — and it is the only flag the two
    /// states need: a receipt exists exactly when a grant has landed.
    @State private var receipt: [String]? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Space.base) {
            LogoMark(size: 56)
                .accessibilityHidden(true)
                .padding(.bottom, Theme.Space.tight)

            if let receipt {
                proof(receipt)
            } else {
                question
            }

            Spacer(minLength: Theme.Space.base)

            if receipt == nil {
                Button {
                    asking = true
                    Task {
                        let ok = await session.grantContext(source)
                        asking = false
                        guard ok else {
                            withAnimation(Theme.spring) { refused = true }
                            return
                        }
                        // OFF-DEVICE SOURCES CLOSE AS THEY ALWAYS DID. There is
                        // nothing to show back at this moment: mail is read in
                        // the browser while you watch and its facts arrive by a
                        // different path entirely (`ContextGrant.swift:22-42`),
                        // so a receipt here would be this screen reporting a
                        // read that has not happened.
                        guard source.isOnDevice else {
                            dismiss()
                            return
                        }
                        let lines = await Self.justRead(source)
                        withAnimation(Theme.spring) { receipt = lines }
                    }
                } label: {
                    // The label names what this yes buys, per source
                    // (`ContextGrant.swift`, `yesButton`). "Yes, go ahead" was
                    // the same six words for the calendar, the address book and
                    // a supervised read of a mailbox.
                    Text(asking ? "Asking iPhone…" : source.yesButton)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.glass)
                // Disabled dimming belongs to the style, so it is the same 0.45
                // on every screen instead of a per-sheet guess.
                .disabled(asking)

                // Said BEFORE the decision rather than after it, and it is a
                // description of the code rather than a reassurance about it:
                // the revoke in Settings is one tap behind no confirmation
                // alert, on purpose (`SettingsView`'s "Stop reading …" row).
                // Named rather than line-numbered: that file is long and moves.
                Text("One tap in Settings stops this any time.")
                    .font(Theme.aside)
                    .foregroundStyle(Theme.muted)
                    .fixedSize(horizontal: false, vertical: true)

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
            } else {
                // ONE button in this state, and it closes nothing but the
                // sheet. A second control beside it would have to be either a
                // false undo — the read already happened and the lines are
                // already hers — or a decline that contradicts the grant it
                // sits underneath.
                Button {
                    dismiss()
                } label: {
                    Text("That's fine")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.glass)
            }
        }
        .padding(.horizontal, 28)
        .padding(.top, Theme.Space.section)
        .padding(.bottom, 18)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Theme.bg.ignoresSafeArea())
        .grainOverlay()
    }

    // MARK: - The ask

    private var question: some View {
        VStack(alignment: .leading, spacing: Theme.Space.base) {
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
        }
    }

    // MARK: - What she just took

    /// The receipt. Same column, same tokens, one state later.
    private func proof(_ lines: [String]) -> some View {
        VStack(alignment: .leading, spacing: Theme.Space.base) {
            // Still the one lit thing on the surface; it is an answer now
            // instead of a question.
            Text(ContextReceipt.heading)
                .font(Theme.display(28))
                .foregroundStyle(Theme.text)
                .fixedSize(horizontal: false, vertical: true)

            VStack(alignment: .leading, spacing: Theme.Space.snug) {
                // Indexed rather than keyed on the string: two identical
                // events in one week are two real rows, and `id: \.self`
                // would silently render one of them.
                ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                    // Serif at 19, the type `SupervisedReadView`'s `factList`
                    // already gives a fact she has concluded. These are the
                    // read lines word for word, not a description of them.
                    Text(line)
                        .font(Theme.display(19))
                        .foregroundStyle(Theme.text)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            // BOTH HALVES ARE TRUE, and the second half is why the first is
            // not enough on its own. Revoking is one tap and stops the reading
            // (`SettingsView.revokeContext`); it deliberately does not delete
            // what has already been sent, which is why that screen's own note
            // says "stays on my server until you delete it below" and why the
            // delete is a separate control on the same page. Saying only the
            // first half here would let "stops this" be read as "takes that
            // back", on the one screen that has just shown what was taken.
            Text("One tap in Settings stops this any time. Anything I've sent myself stays on my server until you delete it there.")
                .font(Theme.aside)
                .foregroundStyle(Theme.text2)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// Read back what the grant just sent, off the main actor.
    ///
    /// A recompute rather than a hand-off, and it is the one part of this that
    /// costs anything: `LifeContext.names()` is a `CNContactStore` fetch, so a
    /// contacts grant now makes two of them a second apart. It is bounded (the
    /// fetch stops at `maxNames`), it happens once per source per install, and
    /// it happens while a sheet the person is reading is already up. The
    /// cheaper shape is for `grantContext` to hand back the facts it just
    /// posted; that lives in `AnticipyApp.swift`, which this change does not
    /// own, and it is recorded as the follow-up.
    private static func justRead(_ source: ContextSource) async -> [String] {
        await Task.detached(priority: .userInitiated) { () -> [String] in
            // Exhaustive on purpose: a new on-device source has to say what
            // its receipt is made of, rather than quietly showing nothing on
            // the one screen that promises to show everything.
            switch source {
            case .calendar:
                return ContextReceipt.lines(for: .calendar,
                                            facts: LifeContext.facts(for: .calendar))
            case .contacts:
                return ContextReceipt.lines(for: .contacts, names: LifeContext.names())
            case .mail:
                return ContextReceipt.lines(for: .mail)
            }
        }.value
    }
}
