import SwiftUI

/// What she may read, as a list of sources wearing their current answer.
///
/// THE SHAPE IS THE POINT, and it is not a restyle of what was here. The old
/// section rendered every source EXPANDED — name, then all of its promises,
/// then a revoke, then a watch link — so three sources filled a screen and the
/// one question a person actually arrives with, "what can she see right now",
/// had to be assembled by reading four paragraphs.
///
/// Now each source is one row carrying its answer as a trailing word, and the
/// promises live one tap in. That is the design Jose supplied (screen 3, the
/// permissions list: `Location — Allowed >`, `Health — Never >`), and it suits
/// this product better than it suits the one it came from, because here the
/// answer is not a system setting somebody set once — it is a grant she asked
/// for out loud and can be taken back in one tap.
///
/// NOTHING WAS DROPPED IN THE MOVE. Every promise, the revoke, and the way back
/// in to watch her read all survive on `SettingsSourceView`. The two arguments
/// attached to them survive with them: the revoke takes ONE TAP WITH NO ALERT
/// on purpose (`ContextGrants.revoke`'s own doc comment forbids making taking
/// it back harder than giving it), and the watch link exists because the Home
/// offer card disappears once a grant lands, so without it saying yes once was
/// the last time you could ever watch her read.
struct SettingsAccessView: View {
    @ObservedObject var session: AnticipySession
    @Environment(\.dismiss) private var dismiss

    /// Read fresh on every pass rather than held: a grant can land from the ask
    /// sheet while this screen sits behind it, and there is no observation
    /// graph on `ContextGrants`. The old section carried this same note.
    @State private var opened: ContextSource?

    var body: some View {
        SheetChrome(title: "What I can see", leading: .back) {
            dismiss()
        } content: {
            GroupedCard {
                ForEach(ContextSource.allCases) { source in
                    StateRow(source.label,
                             systemImage: Self.glyph(for: source),
                             state: Self.answer(for: source)) {
                        Haptics.engage()
                        opened = source
                    }
                }
            }

            FootnoteText("She only reads a source after you say yes, and you "
                         + "can stop any of them in one tap.")
        }
        // `navigationDestination(item:)` would read better and is iOS 17. The
        // floor here is 16 — the same floor `LifeContext` still writes its
        // `NSCalendarsUsageDescription` for — so this is the isPresented form
        // over a derived binding rather than a version check that would leave
        // one of the two paths untested on every device anyone actually has.
        .navigationDestination(isPresented: Binding(
            get: { opened != nil },
            set: { if !$0 { opened = nil } }
        )) {
            if let source = opened {
                SettingsSourceView(session: session, source: source)
            }
        }
    }

    /// The row's glyph, kept HERE and not on `ContextSource`.
    ///
    /// `ContextGrant.swift` carries a standing order that a source's own
    /// properties are the promises she made about it, kept in one place so they
    /// cannot drift from what the consent sheet showed. A picture is not a
    /// promise, and adding a look to that type would invite the next screen to
    /// add a colour and the one after that to add a layout. The design this
    /// came from uses each system's own app icon; Anticipy has no icon for a
    /// grant, so these are SF Symbols in the same outline register as the rest
    /// of the app's rows.
    static func glyph(for source: ContextSource) -> String {
        switch source {
        case .calendar: return "calendar"
        case .contacts: return "person.crop.circle"
        case .mail: return "envelope"
        }
    }

    /// The trailing word, and it says only what is true.
    ///
    /// Three answers, not two, because "not granted" is two different states
    /// and collapsing them is the confident-wrong-default this product keeps
    /// having to fix. A source she has never raised is not one you turned down.
    /// `mayAsk` is the same predicate the Home offer reads, so this row and
    /// that card can never disagree about whether the question is still open.
    static func answer(for source: ContextSource) -> String {
        let grants = ContextGrants()
        if grants.granted(source) { return "Allowed" }
        return grants.mayAsk(source) ? "She'll ask" : "Not now"
    }
}

/// One source, with the promises she made about it.
///
/// The promises are printed VERBATIM from `ContextSource.promises` rather than
/// described again here. That is a standing order in `ContextGrant.swift`: a
/// second description of what she reads is a copy that drifts from the one the
/// consent sheet showed, and there must be one place to keep honest, not two.
struct SettingsSourceView: View {
    @ObservedObject var session: AnticipySession
    let source: ContextSource
    @Environment(\.dismiss) private var dismiss
    @State private var granted = false
    @State private var watching = false

    var body: some View {
        SheetChrome(title: source.label, leading: .back) {
            dismiss()
        } content: {
            GroupedCard {
                StateRow("Right now",
                         state: SettingsAccessView.answer(for: source))
            }

            if granted {
                SectionHeader("What she reads")
                GroupedCard {
                    ForEach(source.promises, id: \.self) { promise in
                        InfoRow(promise)
                    }
                }

                // Off-device only. There is nothing to watch for a source read
                // on this phone in a few milliseconds, and offering a seat at
                // something instantaneous teaches people the offer is decorative.
                if !source.isOnDevice {
                    GroupedCard {
                        NavRow("Watch me read \(source.label.lowercased())",
                               systemImage: "eye") {
                            Haptics.engage()
                            watching = true
                        }
                    }
                }

                // ONE TAP, NO ALERT. `revoke`'s doc comment forbids making
                // taking it back harder than giving it. The destructive alerts
                // elsewhere in Settings guard things that cannot be undone;
                // this can be undone by asking again.
                GroupedCard {
                    DestructiveRow("Stop reading \(source.label.lowercased())",
                                   systemImage: "hand.raised") {
                        Haptics.engage()
                        ContextGrants().revoke(source)
                        granted = false
                    }
                }
            } else {
                FootnoteText("She hasn't read this. She'll ask when something "
                             + "you said needs it, and you can say no.")
            }
        }
        .navigationDestination(isPresented: $watching) {
            SupervisedReadView(session: session)
        }
        .onAppear { granted = ContextGrants().granted(source) }
    }
}
