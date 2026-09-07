import SwiftUI

/// THE PEEK CARD, and the page behind it.
///
/// Research: `research/2026-09-06-insights-retention.md`. `InsightsPolicy`
/// decides every sentence and every omission; this draws them.
///
/// The card sits where the "Done" heading was, with the deck unchanged beneath
/// it, so the section still reads as one thing: here is what came back to you,
/// and here is what it adds up to.
///
/// ── WHAT THIS SCREEN IS NOT ALLOWED TO DO ─────────────────────────────────
///
/// No count-up animation, no badge, no notification, no milestone, and no
/// number that can fall. All five are named in the research as the line between
/// a screen somebody is glad to find and one they feel worked on. A number
/// rolling up from zero is a small casino; a number that goes down is an
/// accusation. There is no streak here for the same reason — the ears went deaf
/// for thirty hours once and nothing noticed, and a streak would have billed
/// that to the person.
struct InsightsPeekCard: View {
    let counts: InsightsPolicy.Counts
    /// The namespace this card shares with the page it opens. Optional so the
    /// card still renders anywhere that has no transition to offer.
    var namespace: Namespace.ID? = nil
    /// True while the page is open. The source of a matched pair must stand
    /// down while the destination holds the geometry, or both draw and the
    /// effect logs a duplicate.
    var hidden: Bool = false
    var onOpen: () -> Void

    /// The id both ends agree on. A constant rather than a computed string:
    /// the pair is one specific card and one specific header, forever.
    static let heroID = "insights.hero"

    var body: some View {
        if let peek = InsightsPolicy.peek(counts), !hidden {
            Button(action: onOpen) {
                HStack(alignment: .center, spacing: 14) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(peek.headline)
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundStyle(OnboardTheme.ink)
                            .fixedSize(horizontal: false, vertical: true)
                        if let detail = peek.detail {
                            Text(detail)
                                .font(.system(size: 14))
                                .foregroundStyle(OnboardTheme.text2)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    Spacer(minLength: 4)
                    Image(systemName: "chevron.right")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(OnboardTheme.muted)
                }
                .padding(.horizontal, 18)
                .padding(.vertical, 16)
                .background(
                    RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .fill(OnboardTheme.card)
                        .overlay(
                            RoundedRectangle(cornerRadius: 18, style: .continuous)
                                .strokeBorder(OnboardTheme.track, lineWidth: 1)
                        )
                )
                .contentShape(Rectangle())
                // THE SOURCE of the matched pair. `isSource: true` and the
                // destination false, so SwiftUI knows which rectangle the other
                // is travelling to rather than guessing between two claimants.
                .modifier(Hero(namespace: namespace, isSource: true))
            }
            .buttonStyle(OnboardPressStyle())
            .accessibilityElement(children: .combine)
            .accessibilityHint("Opens what this adds up to")
        }
    }
}

/// The page. Rows in one column, each a number and the plain sentence it
/// answers, with a caveat under the two that would otherwise overstate
/// themselves.
struct InsightsView: View {
    let counts: InsightsPolicy.Counts
    /// The finished errands already on Home, so somebody arriving here can read
    /// the individual things rather than only the total. The deck stays
    /// swipeable, which is how it already works and how it is already liked.
    let finished: [AgentJob]
    /// The open loops, decided by RingsPolicy before they get here. Passed in
    /// rather than computed: the counts live on two different objects and this
    /// view owns neither.
    var rings: [RingsPolicy.Face] = []
    /// Shared with the peek card, so the card GROWS into this page rather than
    /// the page cutting over it. Optional: the page renders fine without one.
    var namespace: Namespace.ID? = nil
    var onClose: () -> Void

    private typealias P = InsightsPolicy

    var body: some View {
        ZStack {
            OnboardTheme.ground
                .ignoresSafeArea()
                // THE DESTINATION. The page's own ground is what the card
                // becomes — the card is literally a smaller version of this
                // surface, so growing one into the other is the honest
                // rendering of what the tap did.
                .modifier(Hero(namespace: namespace, isSource: false))
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    header
                    RingsSection(faces: rings)
                    let rows = P.rows(counts)
                    if rows.isEmpty {
                        Text(P.emptyLine(P.stage(counts)))
                            .font(.system(size: 16))
                            .foregroundStyle(OnboardTheme.text2)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.horizontal, 24)
                            .padding(.top, 30)
                    } else {
                        VStack(spacing: 0) {
                            ForEach(rows) { row in
                                InsightRowView(row: row)
                                if row.id != rows.last?.id {
                                    Rectangle().fill(OnboardTheme.track).frame(height: 0.5)
                                        .padding(.leading, 24)
                                }
                            }
                        }
                        .padding(.top, 18)

                        // The stage sentence stays under the rows whenever the
                        // page is not yet steady, so a half-filled page explains
                        // its own gaps instead of looking broken.
                        let line = P.emptyLine(P.stage(counts))
                        if !line.isEmpty {
                            Text(line)
                                .font(.system(size: 14))
                                .foregroundStyle(OnboardTheme.muted)
                                .fixedSize(horizontal: false, vertical: true)
                                .padding(.horizontal, 24)
                                .padding(.top, 22)
                        }
                    }

                    let ears = P.ears(counts)
                    if !ears.isEmpty {
                        sectionTitle("How it reached me")
                        VStack(spacing: 12) {
                            ForEach(ears) { ear in EarBar(ear: ear) }
                        }
                        .padding(.horizontal, 24)
                    }

                    if !finished.isEmpty {
                        sectionTitle("What came back")
                        Text("Swipe through the ones that finished.")
                            .font(.system(size: 14))
                            .foregroundStyle(OnboardTheme.muted)
                            .padding(.horizontal, 24)
                            .padding(.bottom, 12)
                        InsightsDoneStrip(jobs: finished)
                    }

                    Color.clear.frame(height: 40)
                }
            }
        }
    }

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 6) {
                Text("What this adds up to")
                    .font(OnboardFont.question(27))
                    .foregroundStyle(OnboardTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 12)
            Button(action: onClose) {
                Image(systemName: "xmark")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(OnboardTheme.ink)
                    .frame(width: 44, height: 44)
                    .background(Circle().fill(OnboardTheme.card))
            }
            .buttonStyle(OnboardPressStyle())
            .accessibilityLabel("Close")
        }
        .padding(.horizontal, 24)
        .padding(.top, 18)
    }

    private func sectionTitle(_ s: String) -> some View {
        Text(s)
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(OnboardTheme.muted)
            .padding(.horizontal, 24)
            .padding(.top, 34)
            .padding(.bottom, 12)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// One number and the sentence it answers. The number leads, at a size that
/// makes it the thing you read first, in the serif the product uses for its own
/// voice.
private struct InsightRowView: View {
    let row: InsightsPolicy.Row

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(row.value)
                    .font(Theme.display(30))
                    .foregroundStyle(OnboardTheme.champagneInk)
                    .monospacedDigit()
                Text(row.label)
                    .font(.system(size: 16))
                    .foregroundStyle(OnboardTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
            }
            if let caveat = row.caveat {
                Text(caveat)
                    .font(.system(size: 13))
                    .foregroundStyle(OnboardTheme.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }
}

/// One ear, as a proportion. A lane with nothing in it never reaches here —
/// `InsightsPolicy.ears` drops it — because a row reading 0% reads as a broken
/// device rather than one that was never used.
private struct EarBar: View {
    let ear: InsightsPolicy.Ear

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                Text(ear.label)
                    .font(.system(size: 15))
                    .foregroundStyle(OnboardTheme.ink)
                Spacer()
                Text("\(ear.share)%")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(OnboardTheme.champagneInk)
                    .monospacedDigit()
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(OnboardTheme.track)
                    Capsule().fill(OnboardTheme.champagne)
                        .frame(width: max(3, geo.size.width * CGFloat(ear.share) / 100))
                }
            }
            .frame(height: 6)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(ear.label), \(ear.share) percent, \(InsightsPolicy.number(ear.count)) of them")
    }
}

/// The finished errands, still swipeable, because that is how they already work
/// and the owner asked for it to stay that way.
private struct InsightsDoneStrip: View {
    let jobs: [AgentJob]

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 12) {
                ForEach(jobs, id: \.id) { job in
                    VStack(alignment: .leading, spacing: 8) {
                        Label("Done", systemImage: "checkmark")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(OnboardTheme.champagneInk)
                        Text(job.goal)
                            .font(.system(size: 15, weight: .medium))
                            .foregroundStyle(OnboardTheme.ink)
                            .fixedSize(horizontal: false, vertical: true)
                        if let result = job.result, !result.isEmpty {
                            Text(result)
                                .font(.system(size: 13))
                                .foregroundStyle(OnboardTheme.text2)
                                .lineLimit(3)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(16)
                    .frame(width: 250, alignment: .topLeading)
                    .frame(minHeight: 130, alignment: .topLeading)
                    .background(RoundedRectangle(cornerRadius: 18, style: .continuous)
                        .fill(OnboardTheme.card))
                    .accessibilityElement(children: .combine)
                }
            }
            .padding(.horizontal, 24)
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// THE RINGS
// ═══════════════════════════════════════════════════════════════════════════

/// One open loop, drawn as the shape a brain wants to close.
///
/// `RingsPolicy` decides whether there is anything here and what it says; this
/// draws an arc. Deliberately the plainest possible rendering of the idea —
/// a track, an arc, and two numbers — because the ring is doing the work and
/// anything else on top of it would be the decoration this screen refuses.
///
/// No count-up, no fill animation on appear, no badge. The arc is simply AT its
/// value from the first frame, for exactly the reason `run_insights_tests.sh`
/// forbids a number rolling up from zero: that is a small casino, and this
/// screen is the one place the product states what is true about itself.
struct RingView: View {
    let face: RingsPolicy.Face

    var body: some View {
        HStack(alignment: .center, spacing: 16) {
            ZStack {
                Circle()
                    .stroke(OnboardTheme.track, lineWidth: 6)
                Circle()
                    .trim(from: 0, to: face.fraction)
                    .stroke(OnboardTheme.champagne,
                            style: StrokeStyle(lineWidth: 6, lineCap: .round))
                    // Twelve o'clock, clockwise. The one place a partial circle
                    // reads as progress rather than as a broken shape.
                    .rotationEffect(.degrees(-90))
                Text("\(face.done)")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(OnboardTheme.ink)
                    .monospacedDigit()
            }
            .frame(width: 46, height: 46)
            .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 3) {
                Text(face.title)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(OnboardTheme.ink)
                Text(face.because)
                    .font(.system(size: 13))
                    .foregroundStyle(OnboardTheme.text2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
            Text("\(face.done) of \(face.total)")
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(OnboardTheme.text2)
                .monospacedDigit()
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 12)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(face.title): \(face.done) of \(face.total). \(face.because)")
    }
}

/// The section, absent rather than empty.
///
/// A heading over no rings is the failure mode `InsightsPolicy` spends its
/// whole file avoiding — an empty state that says "it doesn't work" where a
/// missing one says "not yet".
struct RingsSection: View {
    let faces: [RingsPolicy.Face]

    var body: some View {
        if !faces.isEmpty {
            VStack(alignment: .leading, spacing: 0) {
                Text("STILL OPEN")
                    .font(.system(size: 11, weight: .semibold))
                    .tracking(1.2)
                    .foregroundStyle(OnboardTheme.text2)
                    .padding(.horizontal, 24)
                    .padding(.bottom, 6)
                ForEach(faces, id: \.ring) { face in
                    RingView(face: face)
                }
            }
            .padding(.top, 26)
        }
    }
}


/// One half of the shared element, or nothing at all.
///
/// A modifier rather than an inline `if let` because `matchedGeometryEffect`
/// takes a non-optional namespace, and threading an optional through two views
/// would otherwise mean duplicating both bodies.
private struct Hero: ViewModifier {
    let namespace: Namespace.ID?
    let isSource: Bool

    func body(content: Content) -> some View {
        if let namespace {
            content.matchedGeometryEffect(id: InsightsPeekCard.heroID,
                                          in: namespace,
                                          isSource: isSource)
        } else {
            content
        }
    }
}
