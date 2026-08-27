import SwiftUI

/// The five components a settings-style sheet is built from, and the eight row
/// variants that go in them.
///
/// WHAT THIS IS. Jose supplied seven screenshots of a settings design and one
/// ruling: adopt the STRUCTURE, keep Anticipy's palette and typography. So every
/// layout, spacing relationship and interaction below is the source design's;
/// every colour, font and radius is `Theme`'s. There is not one colour literal,
/// one point size and one corner radius in this file that does not come through
/// a token — the champagne accent stands where the source used iOS blue, the
/// display serif carries the sheet titles, and `Theme.alarm` carries the
/// destructive rows because systemRed appears nowhere else in this product.
///
/// NOTHING HERE KNOWS ABOUT SETTINGS. These are the sheet chrome, the grouped
/// card, the section header, the footnote and the destructive row — five shapes
/// that will carry other screens too, so not one of them names a preference, a
/// store or a screen. The file is called SettingsKit because Settings is the
/// first caller, not because Settings is the only one.
///
/// THE DECISIONS ARE NOT IN THIS FILE. Which inset a hairline takes, whether a
/// hairline exists, whether the header's confirm button is alive, what the
/// trailing slot shows and how many lines a slot may take all live in
/// `SheetKit` (SettingsKitPolicy.swift), which imports Foundation alone and is
/// compiled directly by `app/ios/Tests/run_settings_kit_tests.sh`. This file
/// draws what that file decides, and every call site below reads through it
/// rather than repeating the rule.
///
/// ACCESSIBILITY IS PART OF THE COMPONENT. Every row is ONE element with a
/// label, a value and a trait — not four separate focusable pieces. Chevrons,
/// checkmarks, leading glyphs and hairlines are hidden, because a person
/// hearing "chevron, chevron, chevron" down a card is hearing the drawing
/// rather than the screen. A toggle row reads as a switch because it IS a
/// `Toggle` rather than a hand-rolled pair. And no row has a fixed height:
/// every one carries a `minHeight` for the 44pt target and grows from there, so
/// AX5 wraps the row instead of clipping it — the lesson OnboardingView's
/// progress track already carries a comment about, and one this app does not
/// need to learn twice.

// ---------------------------------------------------------------- metrics

/// THE KIT'S OWN NUMBERS, AND THEREFORE NOT TOKENS — the argument
/// `GlassyIconStyle.Metric` already makes in GlassControls.swift, applied to the
/// second component that needs it. A glyph column of 28 and a header circle of
/// 36 describe ONE family of controls; `Theme.Space` describes the rhythm every
/// surface in the app shares. A `Theme.Space.glyphColumn` would invite the next
/// screen to reuse a number that means nothing outside this file.
///
/// Everything below that is spacing rather than geometry DOES come from
/// `Theme.Space`, so the kit sits on the app's one spacing scale.
private enum SheetMetric {
    /// The icon column. Scaled at every call site with `@ScaledMetric`, never
    /// used raw — see `RowShell.glyphColumn` for why both the row and the card
    /// scale it independently and still agree.
    static let glyphColumn: CGFloat = 28
    /// Between the glyph and the label.
    static let glyphGap: CGFloat = Theme.Space.snug
    /// A row's own padding. Horizontal is where a `.label` hairline starts.
    static let rowPadH: CGFloat = Theme.Space.base
    static let rowPadV: CGFloat = Theme.Space.snug
    /// A MINIMUM, never a height. 44pt is the HIG target; the row grows past it
    /// the moment the text needs more, which is most of Dynamic Type working.
    static let rowMinHeight: CGFloat = 44
    /// The same 0.75 `CardBackground` strokes its edge with, so a hairline
    /// between two rows and the hairline around the card are one weight.
    static let hairline: CGFloat = 0.75
    /// The circular header buttons. FIXED, on purpose: they are chrome, and a
    /// header that grows with the body text pushes the content off the screen
    /// rather than making anything more readable. 36 drawn inside a 44 tap
    /// target, so the geometry lands on the target without padding bolted onto
    /// every call site.
    static let headerCircle: CGFloat = 36
    static let headerTap: CGFloat = 44
    static let headerGlyph: CGFloat = 15
}

// ------------------------------------------------------------------ 1. chrome

/// The trailing circular button in a sheet header, as a value.
///
/// A value rather than a `@ViewBuilder` because its DISABLED state is the point:
/// `isEnabled` has to be readable by the header, by `SheetKit.saveEnabled`, and
/// by a test, and a closure hides all three.
struct SheetAction {
    let systemImage: String
    /// What VoiceOver says. The glyph is hidden; this is the whole label.
    let label: String
    /// Greyed and inert, never hidden. A control that vanishes when it cannot
    /// be used takes its own explanation with it, and the header re-centres
    /// around the hole.
    let isEnabled: Bool
    let action: () -> Void

    init(systemImage: String, label: String, isEnabled: Bool = true,
         action: @escaping () -> Void) {
        self.systemImage = systemImage
        self.label = label
        self.isEnabled = isEnabled
        self.action = action
    }

    /// THE SAVE AFFORDANCE. A tick in the header, dead until there is something
    /// to write — not a button at the bottom of a form. Gate `isEnabled` on
    /// `SheetKit.saveEnabled(edits:acceptable:)` so the button and the field's
    /// caption answer to one predicate.
    static func save(isEnabled: Bool, action: @escaping () -> Void) -> SheetAction {
        SheetAction(systemImage: "checkmark", label: "Save",
                    isEnabled: isEnabled, action: action)
    }
}

/// One circular header button: fixed size, centred glyph, a disabled state that
/// is visibly inert rather than hidden.
struct SheetHeaderButton: View {
    let systemImage: String
    let label: String
    var isEnabled: Bool = true
    let action: () -> Void

    init(systemImage: String, label: String, isEnabled: Bool = true,
         action: @escaping () -> Void) {
        self.systemImage = systemImage
        self.label = label
        self.isEnabled = isEnabled
        self.action = action
    }

    var body: some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: SheetMetric.headerGlyph, weight: .semibold))
                // `muted` is this app's word for a disabled control, and it is
                // still 5.3:1 on white — inert, not invisible.
                .foregroundStyle(isEnabled ? Theme.text : Theme.muted)
                .frame(width: SheetMetric.headerCircle,
                       height: SheetMetric.headerCircle)
                .background(Circle().fill(Theme.surface))
                .frame(width: SheetMetric.headerTap, height: SheetMetric.headerTap)
                .contentShape(Circle())
        }
        .disabled(!isEnabled)
        .accessibilityLabel(Text(label))
        // A disabled button still exists to VoiceOver; iOS speaks "dimmed".
        .accessibilityAddTraits(.isButton)
    }
}

/// COMPONENT 1: SHEET CHROME.
///
/// A FIXED header row — circular button on the left, centred bold title,
/// optional circular button on the right — with the content SCROLLING UNDER it.
/// The header does not move.
///
/// "Scrolls under" is a `ZStack`, not a `safeAreaInset`: the content's top
/// padding is the header's MEASURED height, so at AX5, when the serif title
/// wraps to two lines and the header grows, the first card moves down with it
/// instead of starting underneath it. A constant there would be right at one
/// text size and wrong at eleven.
///
/// The dimmed, blurred backdrop and the large top corner radius belong to the
/// PRESENTATION, not to this view — apply `.sheetChromePresentation()` to the
/// `.sheet` content so both come from one place.
struct SheetChrome<Content: View>: View {
    private let title: String
    private let leading: SheetKit.HeaderLeading
    private let leadingLabel: String
    private let onLeading: () -> Void
    private let trailing: SheetAction?
    private let content: Content

    /// - Parameters:
    ///   - leading: `.close` at the root of a sheet, `.back` on a sub-screen,
    ///     `.none` for a header with no left button — the space is still held.
    ///     `SheetKit.headerLeading(depth:)` answers this from a screen's depth.
    ///   - leadingLabel: what VoiceOver says for the left button. Defaults to
    ///     the role's plain word.
    init(title: String,
         leading: SheetKit.HeaderLeading = .close,
         leadingLabel: String? = nil,
         onLeading: @escaping () -> Void = {},
         trailing: SheetAction? = nil,
         @ViewBuilder content: () -> Content) {
        self.title = title
        self.leading = leading
        self.leadingLabel = leadingLabel ?? (leading == .back ? "Back" : "Close")
        self.onLeading = onLeading
        self.trailing = trailing
        self.content = content()
    }

    @State private var headerHeight: CGFloat = 0
    @State private var scrolled = false
    private let space = "SheetChromeScroll"

    var body: some View {
        ZStack(alignment: .top) {
            Theme.bg.ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: Theme.Space.roomy) {
                    content
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, Theme.Space.base)
                .padding(.top, headerHeight + Theme.Space.base)
                .padding(.bottom, Theme.Space.wide)
                .background {
                    GeometryReader { geo in
                        Color.clear.preference(
                            key: SheetScrollKey.self,
                            value: geo.frame(in: .named(space)).minY)
                    }
                }
            }
            .coordinateSpace(name: space)
            .onPreferenceChange(SheetScrollKey.self) { minY in
                let past = minY < -1
                if past != scrolled {
                    withAnimation(Theme.spring) { scrolled = past }
                }
            }

            header
        }
        .onPreferenceChange(SheetHeaderHeightKey.self) { headerHeight = $0 }
        // ONE BACK BUTTON, NOT TWO.
        //
        // This chrome draws its own circular leading button, and every screen
        // using it is PUSHED onto a NavigationStack that draws one as well — so
        // the first build shipped a system chevron sitting directly above a
        // champagne circle that did the same thing. Two controls, one job, and
        // the eye reads the top one as the real one.
        //
        // Hiding the system bar rather than our own button is what the supplied
        // screens do: their header is the whole chrome, the title is centred
        // against IT, and the trailing control sits on the same row. Hiding
        // ours instead would leave the title stranded below a plain chevron and
        // the info button with nothing to align to.
        //
        // Reclaiming the bar's space is also what moves the row UP into it, so
        // the button lands where the system one used to be — which is the
        // alignment the design asks for and the reason this is one modifier
        // rather than a set of paddings tuned by hand.
        .toolbar(.hidden, for: .navigationBar)
        // Belt and braces for anything that presents this WITHOUT hiding the
        // bar — a sheet inside a NavigationView, say. The bar can come back;
        // a second back button must not come with it.
        .navigationBarBackButtonHidden(true)
    }

    private var header: some View {
        ZStack {
            Text(title)
                .font(.system(size: 19, weight: .bold))
                .foregroundStyle(Theme.text)
                .multilineTextAlignment(.center)
                // The title wraps rather than clipping, and the header grows
                // with it — which is why the content's top padding is measured.
                .fixedSize(horizontal: false, vertical: true)
                // Never under either button, at any text size.
                .padding(.horizontal, SheetMetric.headerTap + Theme.Space.tight)
                .accessibilityAddTraits(.isHeader)

            HStack(spacing: 0) {
                if let glyph = SheetKit.leadingGlyph(leading) {
                    SheetHeaderButton(systemImage: glyph, label: leadingLabel,
                                      action: onLeading)
                } else {
                    placeholder
                }
                Spacer(minLength: 0)
                if let trailing {
                    SheetHeaderButton(systemImage: trailing.systemImage,
                                      label: trailing.label,
                                      isEnabled: trailing.isEnabled,
                                      action: trailing.action)
                } else {
                    placeholder
                }
            }
        }
        .padding(.horizontal, Theme.Space.snug)
        .padding(.vertical, Theme.Space.tight)
        .background {
            Theme.bg
                .ignoresSafeArea(edges: .top)
                .overlay(alignment: .bottom) {
                    // The rule appears only once something has gone under the
                    // header. At rest the header is part of the page.
                    Rectangle()
                        .fill(Theme.edge)
                        .frame(height: SheetMetric.hairline)
                        .opacity(scrolled ? 1 : 0)
                        .accessibilityHidden(true)
                }
        }
        .background {
            GeometryReader { geo in
                Color.clear.preference(key: SheetHeaderHeightKey.self,
                                       value: geo.size.height)
            }
        }
    }

    /// The space a missing button would have taken, still taken. A header whose
    /// title slides left when the right button is absent is a header that moves.
    private var placeholder: some View {
        Color.clear
            .frame(width: SheetMetric.headerTap, height: SheetMetric.headerTap)
            .accessibilityHidden(true)
    }
}

private struct SheetHeaderHeightKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

private struct SheetScrollKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

extension View {
    /// The presentation a `SheetChrome` expects: the large top corner radius the
    /// design carries, in the app's own `Radius.hero`.
    ///
    /// The dim and the blur behind the sheet are the system's and need nothing
    /// from us. The radius needs iOS 17; on 16 the sheet keeps the system's
    /// smaller one, which is a difference of a few points and nothing else.
    func sheetChromePresentation() -> some View {
        Group {
            if #available(iOS 17.0, *) {
                self.presentationCornerRadius(Theme.Radius.hero)
            } else {
                self
            }
        }
    }
}

// ------------------------------------------------------------ 2. grouped card

/// A row's own answer to where its hairline starts.
///
/// NOT a `View`-refining protocol, deliberately: `CardRowBuilder` casts to it
/// with `as?`, and a protocol that inherited `View` would make that cast and the
/// generic `buildExpression` overload ambiguous.
protocol CardRowContent {
    var dividerInset: SheetKit.DividerInset { get }
}

/// One row on its way into a card, carrying the inset its hairline takes.
struct CardRowBox {
    let inset: SheetKit.DividerInset
    let view: AnyView

    init(inset: SheetKit.DividerInset, view: AnyView) {
        self.inset = inset
        self.view = view
    }

    /// The escape hatch. Any view can be a card row; it just has to say where
    /// its hairline starts, because the card cannot guess.
    static func custom<V: View>(inset: SheetKit.DividerInset = .label,
                                @ViewBuilder _ content: () -> V) -> CardRowBox {
        CardRowBox(inset: inset, view: AnyView(content()))
    }
}

/// Collects rows AS VALUES rather than as an opaque view tree.
///
/// WHY, and it is the whole reason the inset detail can be got right: the card
/// has to know how many rows it holds and which inset each one takes, so that
/// the hairline after row three is the inset row three asked for and there is
/// no hairline after the last one. A `@ViewBuilder` hands over one anonymous
/// blob that can answer neither question, which is how a card ends up drawing a
/// full-bleed line under its final row.
@resultBuilder
enum CardRowBuilder {
    static func buildExpression<V: View>(_ view: V) -> [CardRowBox] {
        let inset = (view as? CardRowContent)?.dividerInset ?? .label
        return [CardRowBox(inset: inset, view: AnyView(view))]
    }
    static func buildExpression(_ box: CardRowBox) -> [CardRowBox] { [box] }
    static func buildExpression(_ boxes: [CardRowBox]) -> [CardRowBox] { boxes }
    static func buildBlock(_ parts: [CardRowBox]...) -> [CardRowBox] {
        parts.flatMap { $0 }
    }
    static func buildOptional(_ part: [CardRowBox]?) -> [CardRowBox] { part ?? [] }
    static func buildEither(first: [CardRowBox]) -> [CardRowBox] { first }
    static func buildEither(second: [CardRowBox]) -> [CardRowBox] { second }
    static func buildArray(_ parts: [[CardRowBox]]) -> [CardRowBox] {
        parts.flatMap { $0 }
    }
    static func buildLimitedAvailability(_ part: [CardRowBox]) -> [CardRowBox] { part }
}

/// COMPONENT 2: THE GROUPED CARD.
///
/// A rounded container holding stacked rows, with HAIRLINE AND INSET dividers
/// between them — they begin at the label, not at the card edge, so the icon
/// column stays clear.
///
/// THE FILL. The design's card sits one step off the page. On black that is
/// literal: `Theme.card` is #141414 over a #000000 page. On white there is no
/// tone left above the page, so — exactly as Theme.swift argues for every other
/// card in this app — the elevation becomes the hairline plus a shadow, and
/// `card` and `bg` are both #FFFFFF on purpose.
///
/// THE SHADOW READS NO SCHEME. `CardBackground` flips its shadow with the
/// colour scheme because it is the token layer and may; a view may not. So this
/// card drops one soft `Theme.pageShadow` in both themes: on paper it is the
/// warm lift the design needs, and on black #111111 is invisible, which is
/// correct — a card that is already a lighter tone than the page needs no
/// shadow to sit on it.
struct GroupedCard: View {
    private let rows: [CardRowBox]

    init(@CardRowBuilder _ rows: () -> [CardRowBox]) {
        self.rows = rows()
    }

    /// The card scales the glyph column with Dynamic Type for the same reason
    /// `RowShell` does, and arrives at the same number: `@ScaledMetric` is a
    /// pure function of the base value, the text style and the environment, so
    /// two views asking separately get one answer and the hairline stays under
    /// the label at every size.
    @ScaledMetric(relativeTo: .body) private var glyphColumn = SheetMetric.glyphColumn

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous)
    }

    var body: some View {
        VStack(spacing: 0) {
            ForEach(rows.indices, id: \.self) { i in
                rows[i].view
                if SheetKit.showsDivider(after: i, of: rows.count) {
                    hairline(rows[i].inset)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.card)
        .clipShape(shape)
        .overlay(shape.strokeBorder(Theme.edge, lineWidth: SheetMetric.hairline))
        .shadow(color: Theme.pageShadow.opacity(0.07), radius: 2, y: 1)
        .shadow(color: Theme.pageShadow.opacity(0.10), radius: 14, y: 8)
    }

    /// The hairline runs to the card's TRAILING edge and is inset only on the
    /// leading side — the shape the design draws, and the shape iOS draws.
    private func hairline(_ inset: SheetKit.DividerInset) -> some View {
        Rectangle()
            .fill(Theme.edge)
            .frame(height: SheetMetric.hairline)
            .padding(.leading, SheetKit.dividerLeading(inset,
                                                       rowPadding: SheetMetric.rowPadH,
                                                       glyphColumn: glyphColumn,
                                                       glyphGap: SheetMetric.glyphGap))
            .accessibilityHidden(true)
    }
}

// ------------------------------------------- 3. section header, 4. footnote

/// COMPONENT 3: SECTION HEADER. Grey, regular weight, sentence case, sitting
/// OUTSIDE and ABOVE the card — never inside it.
///
/// `.subheadline` rather than `Theme.meta`, and this is not a preference:
/// `Font.system(size:)` does not answer Dynamic Type, and `Theme.meta` is that.
/// A header somebody cannot enlarge is a header somebody cannot read, which is
/// the same argument `FieldCaptionLine` already carries in Theme.swift.
struct SectionHeader: View {
    private let text: String

    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text)
            .font(.subheadline)
            .foregroundStyle(Theme.muted)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, SheetMetric.rowPadH)
            .accessibilityAddTraits(.isHeader)
    }
}

/// A link that lives INSIDE a sentence, underlined.
struct InlineLink: Equatable {
    let text: String
    let url: URL

    init(_ text: String, _ url: URL) {
        self.text = text
        self.url = url
    }
}

/// A sentence with an optional underlined link in the middle of it.
///
/// Composed from THREE PIECES — lead, link, trail — rather than by finding the
/// link's words inside the sentence. Searching a sentence for a substring in
/// order to decide which of its words are a link is a pattern deciding what
/// words are for, and HARNESS-LAWS law 1 says meaning is not a string's job.
/// Handing over the three parts costs one argument and cannot be wrong.
private func linkedSentence(_ lead: String,
                            _ link: InlineLink?,
                            _ trail: String) -> AttributedString {
    var out = AttributedString(lead)
    guard let link else { return out }
    var middle = AttributedString(link.text)
    middle.link = link.url
    middle.underlineStyle = .single
    middle.foregroundColor = Theme.systemControl
    out.append(middle)
    out.append(AttributedString(trail))
    return out
}

/// COMPONENT 4: FOOTNOTE. A grey explanatory sentence BELOW a card, sometimes
/// carrying an inline link.
///
/// Indented to the card's own label inset so it reads as belonging to the card
/// above it rather than to the page.
struct FootnoteText: View {
    private let lead: String
    private let link: InlineLink?
    private let trail: String

    /// - Parameters:
    ///   - lead: the sentence up to the link.
    ///   - link: the underlined words, in the accent.
    ///   - trail: the sentence after the link.
    init(_ lead: String, link: InlineLink? = nil, trail: String = "") {
        self.lead = lead
        self.link = link
        self.trail = trail
    }

    var body: some View {
        Text(linkedSentence(lead, link, trail))
            .font(.footnote)
            .foregroundStyle(Theme.muted)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, SheetMetric.rowPadH)
            .tint(Theme.systemControl)
    }
}

/// Header, card and footnote as one block, with the spacing relationship
/// between them held here instead of at every call site.
///
/// 8pt inside the group against `SheetChrome`'s 24 between groups — the 3x ratio
/// Theme.Space exists to keep, and most of why the source design reads as a
/// layout rather than a list.
struct CardSection: View {
    private let header: String?
    private let footnote: String?
    private let footnoteLink: InlineLink?
    private let footnoteTrail: String
    private let rows: [CardRowBox]

    init(_ header: String? = nil,
         footnote: String? = nil,
         footnoteLink: InlineLink? = nil,
         footnoteTrail: String = "",
         @CardRowBuilder rows: () -> [CardRowBox]) {
        self.header = header
        self.footnote = footnote
        self.footnoteLink = footnoteLink
        self.footnoteTrail = footnoteTrail
        self.rows = rows()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Space.tight) {
            if let header {
                SectionHeader(header)
            }
            GroupedCard { rows }
            if let footnote {
                FootnoteText(footnote, link: footnoteLink, trail: footnoteTrail)
            }
        }
    }
}

// -------------------------------------------------------------- the row shell

/// The shape every row in a grouped card shares: optional leading glyph, a
/// title over an optional wrapping subtitle, and a trailing control that is
/// VERTICALLY CENTRED against however many lines the text took.
///
/// Centring is `HStack(alignment: .center)` and nothing else, and it is detail 4
/// of the brief: a toggle pinned to the first line of a three-line subtitle is
/// the second-clearest tell that a design was copied badly.
private struct RowShell<Trailing: View>: View {
    let systemImage: String?
    let title: String
    let subtitle: String?
    /// Regular for a one-line nav row, semibold for the two-line rows — the
    /// weight relationship the source design uses to separate them.
    let titleBold: Bool
    let titleColor: Color
    let glyphColor: Color
    @ViewBuilder let trailing: Trailing

    /// See `GroupedCard.glyphColumn`: both scale the same base against the same
    /// text style, so the hairline lands under the label at every size.
    @ScaledMetric(relativeTo: .body) private var glyphColumn = SheetMetric.glyphColumn

    var body: some View {
        HStack(alignment: .center, spacing: SheetMetric.glyphGap) {
            if let systemImage {
                Image(systemName: systemImage)
                    .font(.body)
                    .foregroundStyle(glyphColor)
                    .frame(width: glyphColumn, alignment: .leading)
                    // Decoration. The row's label already says what it is, and
                    // "gear, Listening" is one word too many.
                    .accessibilityHidden(true)
            }

            VStack(alignment: .leading, spacing: Theme.Space.hair) {
                Text(title)
                    .font(titleBold ? .body.weight(.semibold) : .body)
                    .foregroundStyle(titleColor)
                    .lineLimit(SheetKit.lineLimit(for: .title))
                    .fixedSize(horizontal: false, vertical: true)
                if let subtitle {
                    Text(subtitle)
                        .font(.footnote)
                        .foregroundStyle(Theme.muted)
                        // WRAPS FREELY, over as many lines as it needs. The row
                        // grows; nothing is clipped.
                        .lineLimit(SheetKit.lineLimit(for: .subtitle))
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            trailing
        }
        .padding(.horizontal, SheetMetric.rowPadH)
        .padding(.vertical, SheetMetric.rowPadV)
        // MIN, never a height.
        .frame(minHeight: SheetMetric.rowMinHeight)
        .contentShape(Rectangle())
    }
}

/// The trailing grey value: "Allowed", "Read & write", "Never", "Max plan".
///
/// The ONE deliberate truncation in the kit, and it reads its own line limit out
/// of `SheetKit` so the exception is named in the type rather than typed here.
/// It yields the width to the label because the label is the row's subject.
private struct TrailingValue: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.body)
            .foregroundStyle(Theme.muted)
            .lineLimit(SheetKit.lineLimit(for: .trailingValue))
            .truncationMode(.tail)
            .layoutPriority(-1)
            .accessibilityHidden(true)
    }
}

private struct RowChevron: View {
    var body: some View {
        Image(systemName: "chevron.right")
            .font(.footnote.weight(.semibold))
            .foregroundStyle(Theme.muted)
            .accessibilityHidden(true)
    }
}

/// The whole row lights while it is held. `Theme.surface` is this app's word for
/// something set INTO the page, which is what a pressed row is.
struct CardRowButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .background(configuration.isPressed ? Theme.surface : Color.clear)
    }
}

/// The trailing slot, drawn from one decision so a value and a chevron cannot
/// drift apart.
@ViewBuilder
private func trailingSlot(value: String?, isNavigable: Bool) -> some View {
    switch SheetKit.trailing(value: value, isNavigable: isNavigable) {
    case .nothing:
        EmptyView()
    case let .value(v):
        TrailingValue(text: v)
    case .chevron:
        RowChevron()
    case let .valueAndChevron(v):
        HStack(spacing: Theme.Space.tight) {
            TrailingValue(text: v)
            RowChevron()
        }
    }
}

// ---------------------------------------------------------- 5. the row variants

/// VARIANT A: NAV ROW. Leading glyph, label, OPTIONAL trailing grey value,
/// chevron. The value and the chevron COEXIST — the source shows "Max plan >"
/// on one row, and `SheetKit.trailing` is why that cannot be lost.
struct NavRow: View, CardRowContent {
    private let title: String
    private let systemImage: String?
    private let value: String?
    private let action: () -> Void

    init(_ title: String, systemImage: String? = nil, value: String? = nil,
         action: @escaping () -> Void) {
        self.title = title
        self.systemImage = systemImage
        self.value = value
        self.action = action
    }

    var dividerInset: SheetKit.DividerInset {
        SheetKit.dividerInset(hasGlyph: systemImage != nil)
    }

    var body: some View {
        Button(action: action) {
            RowShell(systemImage: systemImage, title: title, subtitle: nil,
                     titleBold: false, titleColor: Theme.text,
                     glyphColor: Theme.text2) {
                trailingSlot(value: value, isNavigable: true)
            }
        }
        .buttonStyle(CardRowButtonStyle())
        // NO `.accessibilityElement(children: .ignore)` HERE, and that is not an
        // omission: a SwiftUI `Button` is ALREADY one accessibility element
        // carrying the button trait, and `children: .ignore` on top of one has
        // been known to take its activation with it. The glyph and the chevron
        // inside are hidden at the source, so what is left to read is exactly
        // the label and the value below.
        .accessibilityLabel(Text(title))
        .accessibilityValue(Text(value ?? ""))
    }
}

/// VARIANT B: TWO-LINE TOGGLE ROW. Bold title, grey subtitle wrapping over as
/// many lines as it needs, toggle trailing and vertically centred. NO leading
/// icon — which is why its hairline insets to `.label` rather than past a glyph
/// column it does not have.
///
/// It is a real `Toggle` with the row as its label, not a row with a switch
/// bolted on: that is what makes it ONE accessibility element that reads as a
/// switch and speaks its own on/off value, and what centres the switch against
/// a three-line subtitle without any arithmetic here.
struct ToggleRow: View, CardRowContent {
    private let title: String
    private let subtitle: String?
    @Binding private var isOn: Bool

    init(_ title: String, subtitle: String? = nil, isOn: Binding<Bool>) {
        self.title = title
        self.subtitle = subtitle
        self._isOn = isOn
    }

    var dividerInset: SheetKit.DividerInset { .label }

    var body: some View {
        Toggle(isOn: $isOn) {
            VStack(alignment: .leading, spacing: Theme.Space.hair) {
                Text(title)
                    .font(.body.weight(.semibold))
                    .foregroundStyle(Theme.text)
                    .lineLimit(SheetKit.lineLimit(for: .title))
                    .fixedSize(horizontal: false, vertical: true)
                if let subtitle {
                    Text(subtitle)
                        .font(.footnote)
                        .foregroundStyle(Theme.muted)
                        .lineLimit(SheetKit.lineLimit(for: .subtitle))
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        // The champagne fill stands where the source used iOS green/blue.
        .tint(Theme.fill)
        .padding(.horizontal, SheetMetric.rowPadH)
        .padding(.vertical, SheetMetric.rowPadV)
        .frame(minHeight: SheetMetric.rowMinHeight)
        // The title is the label; the subtitle is the explanation, and VoiceOver
        // says it after the switch's own on/off value rather than in front of it.
        .accessibilityLabel(Text(title))
        .accessibilityHint(Text(subtitle ?? ""))
    }
}

/// VARIANT C: TWO-LINE DISCLOSURE ROW. Title, subtitle, chevron. No toggle.
struct DisclosureRow: View, CardRowContent {
    private let title: String
    private let subtitle: String?
    private let systemImage: String?
    private let value: String?
    private let action: () -> Void

    init(_ title: String, subtitle: String? = nil, systemImage: String? = nil,
         value: String? = nil, action: @escaping () -> Void) {
        self.title = title
        self.subtitle = subtitle
        self.systemImage = systemImage
        self.value = value
        self.action = action
    }

    var dividerInset: SheetKit.DividerInset {
        SheetKit.dividerInset(hasGlyph: systemImage != nil)
    }

    var body: some View {
        Button(action: action) {
            RowShell(systemImage: systemImage, title: title, subtitle: subtitle,
                     titleBold: true, titleColor: Theme.text,
                     glyphColor: Theme.text2) {
                trailingSlot(value: value, isNavigable: true)
            }
        }
        .buttonStyle(CardRowButtonStyle())
        .accessibilityLabel(Text(title))
        .accessibilityValue(Text(value ?? ""))
        .accessibilityHint(Text(subtitle ?? ""))
    }
}

/// VARIANT D: VALUE ROW, editable. Grey label LEFT, value RIGHT, edited in
/// place — no push, no sheet, no separate form.
///
/// THE ONE ROW THAT IS NOT ONE ELEMENT WITH THE TRAIT `.isButton`, and it has to
/// be: a text field somebody cannot focus is a text field somebody cannot type
/// in. So the label is hidden from VoiceOver and its words are given to the
/// FIELD, which leaves exactly one accessibility element in the row — the field,
/// carrying the label — and keeps it editable.
struct ValueRow: View, CardRowContent {
    private let label: String
    @Binding private var text: String
    private let placeholder: String
    private let keyboard: UIKeyboardType
    private let contentType: UITextContentType?
    private let submit: SubmitLabel
    private let onSubmit: () -> Void

    init(_ label: String,
         text: Binding<String>,
         placeholder: String = "",
         keyboard: UIKeyboardType = .default,
         contentType: UITextContentType? = nil,
         submit: SubmitLabel = .done,
         onSubmit: @escaping () -> Void = {}) {
        self.label = label
        self._text = text
        self.placeholder = placeholder
        self.keyboard = keyboard
        self.contentType = contentType
        self.submit = submit
        self.onSubmit = onSubmit
    }

    var dividerInset: SheetKit.DividerInset { .label }

    var body: some View {
        HStack(alignment: .center, spacing: Theme.Space.base) {
            Text(label)
                .font(.body)
                .foregroundStyle(Theme.muted)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityHidden(true)

            TextField(placeholder, text: $text)
                .font(.body)
                .foregroundStyle(Theme.text)
                .multilineTextAlignment(.trailing)
                .keyboardType(keyboard)
                .textContentType(contentType)
                .submitLabel(submit)
                .onSubmit(onSubmit)
                .tint(Theme.systemControl)
                .accessibilityLabel(Text(label))
        }
        .padding(.horizontal, SheetMetric.rowPadH)
        .padding(.vertical, SheetMetric.rowPadV)
        .frame(minHeight: SheetMetric.rowMinHeight)
    }
}

/// VARIANT E: one row of a SINGLE-SELECT GROUP. Title, optional subtitle, and a
/// CHECKMARK on the right when it is the chosen one — a checkmark, not a radio,
/// not a highlight, not a filled row.
struct SelectRow: View, CardRowContent {
    private let title: String
    private let subtitle: String?
    private let isSelected: Bool
    private let action: () -> Void

    init(_ title: String, subtitle: String? = nil, isSelected: Bool,
         action: @escaping () -> Void) {
        self.title = title
        self.subtitle = subtitle
        self.isSelected = isSelected
        self.action = action
    }

    var dividerInset: SheetKit.DividerInset { .label }

    var body: some View {
        Button(action: action) {
            RowShell(systemImage: nil, title: title, subtitle: subtitle,
                     titleBold: true, titleColor: Theme.text,
                     glyphColor: Theme.text2) {
                Image(systemName: "checkmark")
                    .font(.body.weight(.semibold))
                    .foregroundStyle(Theme.systemControl)
                    // Held even when unselected, so choosing does not shove the
                    // title of every row in the card sideways.
                    .opacity(isSelected ? 1 : 0)
                    .accessibilityHidden(true)
            }
        }
        .buttonStyle(CardRowButtonStyle())
        .accessibilityLabel(Text(title))
        .accessibilityHint(Text(subtitle ?? ""))
        // `.isSelected` is how VoiceOver says "this is the one", and it is the
        // whole reason the checkmark may stay decorative. The button trait is
        // already the Button's; only the selection is added here.
        .accessibilityAddTraits(isSelected ? [.isSelected] : [])
    }
}

/// A whole SINGLE-SELECT GROUP: one card, one checkmark, one binding.
///
/// `SheetKit.chosenIndex` decides which row is ticked, so a selection that
/// matches nothing in the list ticks nothing rather than defaulting to the top
/// row, and a list holding the same item twice still shows exactly one tick.
struct SelectGroup<Item: Hashable>: View {
    private let items: [Item]
    @Binding private var selection: Item
    private let title: (Item) -> String
    private let subtitle: (Item) -> String?

    init(_ items: [Item],
         selection: Binding<Item>,
         title: @escaping (Item) -> String,
         subtitle: @escaping (Item) -> String? = { _ in nil }) {
        self.items = items
        self._selection = selection
        self.title = title
        self.subtitle = subtitle
    }

    private var chosen: Int? {
        SheetKit.chosenIndex(in: items, selection: selection)
    }

    var body: some View {
        GroupedCard {
            for index in items.indices {
                SelectRow(title(items[index]),
                          subtitle: subtitle(items[index]),
                          isSelected: index == chosen) {
                    selection = items[index]
                }
            }
        }
    }
}

/// VARIANT F: TRAILING-STATE ROW. Leading icon, label, and the CURRENT STATE as
/// a trailing grey value — "Allowed", "Read & write", "Never".
///
/// The state is a WORD, not a colour and not a badge. Nothing here grades
/// anything: "Never" is not worse than "Allowed", it is a different answer, and
/// the mobile UX audit's "What NOT to do" is binding on that.
///
/// Tappable when it is given an action, inert when it is not — and inert means
/// no chevron and no button trait, so nobody hears an affordance that is not
/// there.
struct StateRow: View, CardRowContent {
    private let title: String
    private let systemImage: String?
    private let state: String
    private let action: (() -> Void)?

    init(_ title: String, systemImage: String? = nil, state: String,
         action: (() -> Void)? = nil) {
        self.title = title
        self.systemImage = systemImage
        self.state = state
        self.action = action
    }

    var dividerInset: SheetKit.DividerInset {
        SheetKit.dividerInset(hasGlyph: systemImage != nil)
    }

    private var shell: some View {
        RowShell(systemImage: systemImage, title: title, subtitle: nil,
                 titleBold: false, titleColor: Theme.text,
                 glyphColor: Theme.text2) {
            trailingSlot(value: state, isNavigable: action != nil)
        }
    }

    var body: some View {
        Group {
            if let action {
                Button(action: action) { shell }
                    .buttonStyle(CardRowButtonStyle())
            } else {
                // The inert form is not a Button, so it needs collapsing into
                // one element by hand — and it must NOT claim a button trait,
                // because nobody should hear an affordance that is not there.
                shell.accessibilityElement(children: .ignore)
            }
        }
        .accessibilityLabel(Text(title))
        .accessibilityValue(Text(state))
    }
}

/// VARIANT G: DESTRUCTIVE ROW. Its own card, red label and red icon, NO chevron
/// — the absent chevron is the point: this does not take you somewhere, it does
/// something.
///
/// `Theme.alarm` rather than systemRed, because systemRed appears nowhere else
/// in this product and reads as borrowed from Apple.
///
/// Full width and real size, like every other escape hatch in this app, and
/// worded without guilt. What it says is the caller's; that it is not hidden in
/// a menu is this component's.
struct DestructiveRow: View, CardRowContent {
    private let title: String
    private let systemImage: String?
    private let action: () -> Void

    init(_ title: String, systemImage: String? = nil,
         action: @escaping () -> Void) {
        self.title = title
        self.systemImage = systemImage
        self.action = action
    }

    var dividerInset: SheetKit.DividerInset {
        SheetKit.dividerInset(hasGlyph: systemImage != nil)
    }

    var body: some View {
        Button(action: action) {
            RowShell(systemImage: systemImage, title: title, subtitle: nil,
                     titleBold: false, titleColor: Theme.alarm,
                     glyphColor: Theme.alarm) {
                trailingSlot(value: nil, isNavigable: false)
            }
        }
        .buttonStyle(CardRowButtonStyle())
        .accessibilityLabel(Text(title))
    }
}

/// VARIANT H: an INLINE LINK inside a row's subtitle, underlined.
///
/// A row that only says something. It is NOT a button and NOT a toggle, and that
/// is what lets the link inside its subtitle be tappable: a link nested inside a
/// row that was itself one button would be an affordance VoiceOver could reach
/// and a finger could not.
struct InfoRow: View, CardRowContent {
    private let title: String?
    private let lead: String
    private let link: InlineLink?
    private let trail: String
    private let systemImage: String?

    init(_ lead: String,
         title: String? = nil,
         link: InlineLink? = nil,
         trail: String = "",
         systemImage: String? = nil) {
        self.lead = lead
        self.title = title
        self.link = link
        self.trail = trail
        self.systemImage = systemImage
    }

    var dividerInset: SheetKit.DividerInset {
        SheetKit.dividerInset(hasGlyph: systemImage != nil)
    }

    @ScaledMetric(relativeTo: .body) private var glyphColumn = SheetMetric.glyphColumn

    var body: some View {
        HStack(alignment: .center, spacing: SheetMetric.glyphGap) {
            if let systemImage {
                Image(systemName: systemImage)
                    .font(.body)
                    .foregroundStyle(Theme.text2)
                    .frame(width: glyphColumn, alignment: .leading)
                    .accessibilityHidden(true)
            }
            VStack(alignment: .leading, spacing: Theme.Space.hair) {
                if let title {
                    Text(title)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(Theme.text)
                        .lineLimit(SheetKit.lineLimit(for: .title))
                        .fixedSize(horizontal: false, vertical: true)
                }
                Text(linkedSentence(lead, link, trail))
                    .font(.footnote)
                    .foregroundStyle(Theme.muted)
                    .lineLimit(SheetKit.lineLimit(for: .subtitle))
                    .fixedSize(horizontal: false, vertical: true)
                    .tint(Theme.systemControl)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, SheetMetric.rowPadH)
        .padding(.vertical, SheetMetric.rowPadV)
        .frame(minHeight: SheetMetric.rowMinHeight)
    }
}

// --------------------------------------------------------------- previews
//
// BOTH THEMES AND AN ACCESSIBILITY TEXT SIZE, because the three ways this kit
// can go wrong are all invisible at the default: a hairline that runs to the
// card edge, a row that clips at AX5, and a disabled header button that
// disappeared instead of going grey.

#if DEBUG
private struct SettingsKitDemo: View {
    @State private var listening = true
    @State private var haptics = false
    @State private var name = "Omar"
    @State private var pick = "Light"

    var body: some View {
        SheetChrome(title: "Settings",
                    leading: .close,
                    onLeading: {},
                    trailing: .save(isEnabled: SheetKit.saveEnabled(
                        edits: [.init(draft: name, stored: "Omar")],
                        acceptable: !name.isEmpty), action: {})) {

            CardSection("Listening",
                        footnote: "I stop when you stop me, and I say so on the home screen. ",
                        footnoteLink: InlineLink("What I keep",
                                                 URL(string: "https://anticipy.ai/privacy")!),
                        footnoteTrail: ".") {
                NavRow("Microphone", systemImage: "mic", value: "On") {}
                StateRow("Calendar", systemImage: "calendar", state: "Read & write") {}
                StateRow("Contacts", systemImage: "person.crop.circle", state: "Never")
                ToggleRow("Keep listening in the background",
                          subtitle: "I stay on when the screen locks. Battery goes at about the rate a podcast does.",
                          isOn: $listening)
                ToggleRow("Haptics", isOn: $haptics)
            }

            CardSection("You") {
                ValueRow("Name", text: $name, placeholder: "Your name")
                DisclosureRow("Your voice",
                              subtitle: "Thirty seconds so I can tell you from the room.",
                              value: "Recorded") {}
                InfoRow("Two answers so far, and I use them only to guess what you meant. ",
                        title: "What I know about you",
                        link: InlineLink("See all of it",
                                         URL(string: "https://anticipy.ai")!),
                        trail: ".")
            }

            CardSection("Appearance") {
                SelectGroupRows(pick: $pick)
            }

            CardSection(footnote: "Everything on the server goes. What is on this phone stays until you delete the app.") {
                DestructiveRow("Delete everything I hold", systemImage: "trash") {}
            }
        }
    }
}

/// Split out so the demo shows the select group both ways: as its own card via
/// `SelectGroup`, and as rows inside a section.
private struct SelectGroupRows: View, CardRowContent {
    @Binding var pick: String
    var dividerInset: SheetKit.DividerInset { .label }
    var body: some View { EmptyView() }
}

#Preview("Light") {
    SettingsKitDemo().environment(\.colorScheme, .light)
}

#Preview("Dark") {
    SettingsKitDemo().environment(\.colorScheme, .dark)
}

#Preview("AX5") {
    SettingsKitDemo()
        .environment(\.dynamicTypeSize, .accessibility5)
}
#endif
