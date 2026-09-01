import SwiftUI

/// One conversation. Front: what she made of it. Back: every word she heard.
///
/// The register is chosen by weight — an object when it asks something of you,
/// a line on the ink when it does not. Nothing is deleted: the raw lines move
/// from the front of the feed to one tap away.
///
/// Every decision about WHAT this shows lives in `HeardGroup.front`; this type
/// only decides how it looks.
struct ConversationCard: View {
    let group: HeardGroup
    @State private var showingRecord = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var front: HeardFront { group.front }

    private var hasFrontContent: Bool { front.verb != nil || !front.rows.isEmpty }

    // The vertical stripe that used to grade this card by weight is gone with
    // every other golden bar, and NOTHING replaced it, because the weight was
    // never only in the stripe: `frontFace` says it in words she already uses
    // ("Quick question for you", "On it", "Looking into it"), and
    // `HeardRegister(carded:)` says it in register — an object at `.acting`
    // and above, a line on the ink below. The stripe was the third telling of
    // one fact, and the quietest one at that.
    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Space.snug) {
            if let t = front.title { titleRow(t) }
            // Emitted only when there is a face to show, so a title-only
            // card cannot pick up a phantom row of stack spacing.
            // .clipped() because the two faces cross-move: neither may
            // paint over its neighbours on the way past.
            if showingRecord {
                recordFace.clipped()
            } else if hasFrontContent {
                frontFace.clipped()
            }
            if !front.isComplete { affordanceRow }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(HeardRegister(carded: group.isCarded))
        .modifier(Flippable(active: !front.isComplete,
                            showingRecord: showingRecord,
                            flip: flip))
    }

    private func flip() {
        Haptics.pageTurn()            // a page turn is a selection
        // Theme.spring, the state curve — NOT springJoy, which is rationed to
        // four moments app-wide and this is not one of them.
        withAnimation(reduceMotion ? nil : Theme.spring) { showingRecord.toggle() }
    }

    // MARK: Faces

    @ViewBuilder private func titleRow(_ text: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: Theme.Space.tight) {
            if front.titleIsHers {
                Text(text)
                    .font(Theme.display(22))
                    .tracking(-0.2)
                    .foregroundStyle(Theme.text)
            } else {
                // Her words, not a summary she never wrote. The voice register,
                // so it reads as speech. lineLimit truncates the RENDERING and
                // never the string — the full text is on the record face and
                // still in session.transcript.
                Text(text)
                    .font(.system(size: 17))
                    .lineSpacing(3)
                    .foregroundStyle(Theme.text)
                    .lineLimit(showingRecord ? nil : 2)
            }
            Spacer(minLength: Theme.Space.tight)
            // Provenance sits at the same visual weight as the clock, because
            // that is what it is: metadata about the capture, not something she
            // decided. Nil for a typed, unknown or MIXED-ear conversation —
            // HeardGroup.ear refuses to pick a side.
            if let ear = CaptureSourcePolicy.badge(for: front.ear) {
                Image(systemName: ear.glyph)
                    .font(.system(size: 11))
                    .foregroundStyle(Theme.muted)
                    .accessibilityLabel(CaptureSourcePolicy.accessibilityLabel(for: ear))
            }
            if let t = clockTime {
                Text(t)
                    .font(.system(size: 12))
                    .foregroundStyle(Theme.muted)
                    .accessibilityHidden(true)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    /// The verb row is copied word for word from `TranscriptRow`, so the card
    /// introduces no claim that does not already exist in this app.
    @ViewBuilder private var frontFace: some View {
        VStack(alignment: .leading, spacing: Theme.Space.snug) {
            switch front.verb {
            case .asking:
                HStack(spacing: 5) {
                    Image(systemName: "questionmark.circle").accessibilityHidden(true)
                    Text("Quick question for you")
                }
                .font(.caption.weight(.medium))
                .foregroundStyle(Theme.accent)
            case .acting:
                HStack(spacing: 5) {
                    Image(systemName: "bolt.fill").accessibilityHidden(true)
                    Text("On it")
                }
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(Theme.accent)
            case .looking:
                HStack(spacing: 5) {
                    Image(systemName: "magnifyingglass").accessibilityHidden(true)
                    Text("Looking into it. I'll bring the result back here.")
                }
                .font(.caption.weight(.medium))
                .foregroundStyle(Theme.accent.opacity(0.85))
            case .noted, .none:
                EmptyView()
            }
            ForEach(front.rows) { line in
                TranscriptRow(line: line)
            }
        }
        .transition(.move(edge: .leading).combined(with: .opacity))
    }

    /// Every line, rendered by the unmodified row this app already ships — so
    /// every per-line truth survives untouched, including "Noted — nothing
    /// needed", which moves from twelve places on the front to one place here.
    @ViewBuilder private var recordFace: some View {
        VStack(alignment: .leading, spacing: Theme.Space.card) {
            ForEach(group.lines) { line in
                TranscriptRow(line: line)
            }
        }
        .transition(.move(edge: .trailing).combined(with: .opacity))
    }

    /// The "you can check me" handle.
    private var affordanceRow: some View {
        HStack(spacing: Theme.Space.hair) {
            Text(showingRecord
                 ? "hide what she heard"
                 : (group.lines.count == 1
                    ? "what she heard"
                    : "\(group.lines.count) lines she heard"))
            Image(systemName: showingRecord ? "chevron.up" : "chevron.down")
                .accessibilityHidden(true)
        }
        .font(.system(size: 12))
        .foregroundStyle(Theme.muted)
    }

    /// The clock time of the newest line we can actually read a date off. Local
    /// lines carry no date and no row is required to have one — when none does,
    /// the time is simply not drawn.
    private var clockTime: String? {
        for line in group.lines.reversed() {
            guard !line.created.isEmpty,
                  let date = AnticipySession.parsePBDate(line.created) else { continue }
            return HeardClock.time.string(from: date)
        }
        return nil
    }
}

private enum HeardClock {
    static let time: DateFormatter = {
        let f = DateFormatter()
        f.locale = .current
        f.setLocalizedDateFormatFromTemplate("jmm")   // 4:12 PM / 16:12, by locale
        return f
    }()
}

/// `.anticipyCard()` when the conversation earned being an object; the house
/// rule register — a row on the ink — when it did not.
private struct HeardRegister: ViewModifier {
    let carded: Bool
    @ViewBuilder func body(content: Content) -> some View {
        if carded {
            content.anticipyCard().padding(.vertical, Theme.Space.tight)
        } else {
            content.padding(.vertical, Theme.Space.base)
        }
    }
}

/// Tap or throw sideways to turn the card over. Applied only when there is
/// actually something behind it — a card whose front already shows every word
/// stays exactly as inert as the row it replaced.
private struct Flippable: ViewModifier {
    let active: Bool
    let showingRecord: Bool
    let flip: () -> Void

    @ViewBuilder func body(content: Content) -> some View {
        if active {
            content
                .contentShape(Rectangle())
                .onTapGesture(perform: flip)
                // Only a dominantly-horizontal throw flips. Both recognisers
                // fire simultaneously, so the ScrollView keeps vertical
                // scrolling; the swipe is additive, never load-bearing.
                .simultaneousGesture(
                    DragGesture(minimumDistance: 24).onEnded { v in
                        guard abs(v.translation.width) > 44,
                              abs(v.translation.width) > abs(v.translation.height) * 1.5
                        else { return }
                        flip()
                    }
                )
                .accessibilityElement(children: .contain)
                .accessibilityAction(named: showingRecord ? "Hide what she heard"
                                                          : "Show what she heard",
                                     flip)
        } else {
            content
        }
    }
}
