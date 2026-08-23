import SwiftUI
import UIKit
import CoreImage

/// Anticipy brand system, pulled from anticipy.ai, in TWO themes.
///
/// Every colour in this app comes through this enum — there is not one raw
/// colour literal in any other file — so the tokens below are the whole
/// product's palette, and making them dynamic is what gives the app a light
/// mode. No call site decides a colour, which also means no call site can be
/// missed.
///
/// LIGHT IS THE DEFAULT and the system setting is deliberately NOT followed:
/// AnticipyApp forces a scheme with .preferredColorScheme, so the app opens the
/// same way for everyone rather than a different way for whoever runs their
/// phone dark. Dark is one switch away in Settings and remembered. See
/// AppTheme.
///
/// Light is a WHITE page with near-black letters; dark is TRUE BLACK. Both
/// DARKEN or keep the accent accordingly, because champagne #C8A97E measures
/// 2.23:1 on white — in light mode champagne is a FILL, never a letter.
///
/// On white there is no tone left above the page, so elevation stops being a
/// lighter fill and becomes the hairline plus the shadow: `card` and `raised`
/// are both #FFFFFF on purpose, and CardBackground always draws a shadow. The extension and the web pages carry the identical
/// values (extension/popup.html, backend/pb_public/site.css).
enum Theme {
    // ---------------------------------------------------------- surfaces
    /// The page. Was `ink`, and the rename is the point: in light mode this is
    /// paper, so a token called ink would be a lie every reader has to decode.
    static let bg = themed(0xFFFFFF, 0x000000)
    /// Recessed — a field, a chip, something set INTO the page.
    static let surface = themed(0xF2F2F0, 0x0D0D0D)
    static let card = themed(0xFFFFFF, 0x141414)
    /// The hairline. Was `stroke` at a flat #252525, which measured 1.09:1 on
    /// card and was therefore optically absent on all eleven cards; it is an
    /// alpha over the surface now, so it holds its weight in both themes.
    static let edge = themed(0x111111, 0xFFFFFF, lightAlpha: 0.14, darkAlpha: 0.11)

    // ------------------------------------------------------------ letters
    /// Anything she is SAYING. 18.9:1 on white, 18.6:1 on black.
    static let text = themed(0x111111, 0xF5F0EB)
    /// Supporting explanation under a control. 8.5:1 / 13.5:1.
    static let text2 = themed(0x4D4D4D, 0xD4CEC7)
    /// Labels, counts, timestamps, and a disabled control. 5.3:1 on white.
    /// Dark keeps #8A8A8A: 6.1:1 on black but 4.9:1 on `raised`, which is why
    /// nothing that carries a sentence may use it.
    static let muted = themed(0x6B6B6B, 0x8A8A8A)

    // ------------------------------------------------------------- accent
    /// The accent as a LETTER or a stroke: champagne on ink, a darkened bronze
    /// on white (5.8:1 on the darkest ground it sits on). Anything the eye has
    /// to READ or a line it has to FOLLOW uses this.
    static let accent = themed(0x7C5729, 0xC8A97E)
    /// The accent as a FILL, and the brand's signature: champagne in both
    /// themes, because #C8A97E carries #0C0C0C at 8.8:1. A filled button
    /// therefore needs no per-theme label colour.
    static let fill = Color(hex: 0xC8A97E)
    /// What sits ON a filled surface.
    static let onFill = Color(hex: 0x000000)
    /// Done, finished, no longer the point. On white champagne IS the dim form
    /// of the accent; on black it is the accent at 45%.
    static let accentDim = themed(0xC8A97E, 0xC8A97E, darkAlpha: 0.45)

    /// Serif display type that SCALES with the reader's text size.
    ///
    /// Reached as a font DESIGN, not a lookup by name. `Font.custom("New York")`
    /// resolves to nil — New York is not a family you can name — and SwiftUI
    /// falls back to SF Pro SILENTLY. Every headline in this app has therefore
    /// been rendering in the system sans, which is to say the brand's voice has
    /// been absent on device the whole time. `design: .serif` is how iOS
    /// actually exposes it.
    ///
    /// UIFontMetrics keeps the Dynamic Type scaling that `relativeTo:` gave us,
    /// so headlines still grow with the reader's text size.
    static func display(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        let scaled = UIFontMetrics(forTextStyle: .largeTitle).scaledValue(for: size)
        return .system(size: scaled, weight: weight, design: .serif)
    }

    /// Anything she is SAYING. 17pt with real leading, in ivory — not 13pt grey.
    /// Grey is for counts, timestamps and error codes; it should never carry a
    /// sentence.
    static let voice = Font.system(size: 17)
    /// Supporting explanation sitting under a control.
    static let aside = Font.system(size: 15)
    /// Labels, counts, timestamps.
    static let meta = Font.system(size: 12, weight: .semibold)

    /// Level-2 elevation. On black the ladder is bg -> card -> raised in rising
    /// tone; on white all three are #FFFFFF and the SHADOW carries the
    /// elevation, because there is nothing lighter than a white page.
    static let raised = themed(0xFFFFFF, 0x1C1C1C)
    /// Destructive, in the brand's register. systemRed appears nowhere else in
    /// this product and reads as borrowed from Apple. 6.6:1 on white.
    static let alarm = themed(0xA03D28, 0xC96A5A)

    /// One spacing scale. There were 23 distinct padding values and no ratio
    /// between them, which is most of why the app read as a list rather than a
    /// layout: space BETWEEN groups must be ~2.5-3x space WITHIN a group.
    enum Space {
        static let hair: CGFloat = 4
        static let tight: CGFloat = 8
        static let snug: CGFloat = 12
        static let base: CGFloat = 16
        static let card: CGFloat = 20
        static let roomy: CGFloat = 24
        static let section: CGFloat = 32
        static let wide: CGFloat = 40
        static let hero: CGFloat = 72
    }
    enum Radius {
        static let small: CGFloat = 12
        static let card: CGFloat = 20
        static let hero: CGFloat = 28
    }

    /// The one motion signature the whole app shares. A response of 0.35 with
    /// 0.8 damping lands inside the 200–350 ms window that reads as premium —
    /// slower feels sluggish, faster feels jumpy.
    static let spring = Animation.spring(response: 0.35, dampingFraction: 0.8)
    static let springSlow = Animation.spring(response: 0.55, dampingFraction: 0.85)
    /// The only curve allowed to overshoot, and it is rationed: pairing
    /// success, onboarding completion, a transcript line flipping to "act",
    /// and the Settings save confirmation. Damping 0.62 on ordinary UI reads
    /// as a toy; on a rare peak it reads as joy — the difference is entirely
    /// how seldom it fires.
    static let springJoy = Animation.spring(response: 0.30, dampingFraction: 0.62)

    // ------------------------------------------------------------- glass
    //
    // THE LIQUID GLASS MATERIAL, measured off the owner's Framer component
    // (`Liquid-Glass-Navbar-6gh01a`, sub-components `Glass CTA` and
    // `Nav Link`). Every button and link in the product — iOS, extension,
    // marketing site — is built from these seventeen names and nothing else,
    // which is what lets `extension/tests/test_theme_contract.mjs` prove the
    // web surfaces and this file describe one material.
    //
    // THEME-DEPENDENT ON PURPOSE. The component's fill is near-black
    // (#26262A -> #08080A). On this app's dark theme the page is TRUE BLACK,
    // so that button is a black pill on a black page: invisible. Dark mode
    // therefore inverts to the LIGHT-METAL glass the navbar shell itself
    // uses. That ramp — #FFF 0%, #E4E4E4 4.5%, #969696 50%, #E4E4E4 95.5%,
    // #FFF 100% — is not five arbitrary stops; it decomposes exactly into
    // rim + fill + rim, so the pure-white 0%/100% stops become `glassRim`
    // and `glassUnder` here and the 4.5%-50% band becomes the fill. Same
    // material, same construction, opposite polarity, contrast either way.

    /// The primary fill, top stop to bottom stop. Lit from above in both
    /// themes: light gets the component's near-black glass, dark gets metal.
    static let glassTop = themed(0x26262A, 0xE4E4E4)
    static let glassBottom = themed(0x08080A, 0x969696)
    /// The inset highlight along the top edge (CSS `inset 0 1px 0`) and the
    /// inset floor along the bottom (CSS `inset 0 -1px 1px`). `glassUnder`
    /// INVERTS with the theme — black at 50% seats a dark pill, and is a
    /// bruise under a light one, where the metal ramp's own 100% stop is
    /// white.
    static let glassRim = themed(0xFFFFFF, 0xFFFFFF, lightAlpha: 0.28, darkAlpha: 0.95)
    static let glassUnder = themed(0x000000, 0xFFFFFF, lightAlpha: 0.5, darkAlpha: 0.55)
    /// The cast shadow under the control. Inverts to a white halo on dark:
    /// a black drop shadow on a #000000 page is arithmetically invisible, so
    /// the only honest way to lift a light object off true black is light.
    static let glassCast = themed(0x000000, 0xFFFFFF, lightAlpha: 0.38, darkAlpha: 0.18)
    /// What sits ON the primary. White on the dark glass, near-black ink on
    /// the metal — each is the other's fill, which is the definition of an
    /// inverted material rather than two unrelated buttons.
    static let glassLabel = themed(0xFFFFFF, 0x08080A)

    /// The engaged (CSS `:hover`) form: the fill brightens and goes slightly
    /// translucent, the rim doubles, the cast deepens and drops further.
    static let glassTopHi = themed(0x252529, 0xFFFFFF, lightAlpha: 0.85, darkAlpha: 0.92)
    static let glassBottomHi = themed(0x08080A, 0xA8A8A8, lightAlpha: 0.85, darkAlpha: 0.92)
    static let glassRimHi = themed(0xFFFFFF, 0xFFFFFF, lightAlpha: 0.45, darkAlpha: 1.0)
    static let glassCastHi = themed(0x000000, 0xFFFFFF, lightAlpha: 0.58, darkAlpha: 0.30)

    /// The secondary control (`Nav Link`): nothing at rest, a frosted film
    /// when engaged. Every value is transparent at rest in the component too,
    /// so the shadow animates IN rather than appearing — see GhostLinkStyle.
    static let ghostFill = themed(0xFFFFFF, 0xFFFFFF, lightAlpha: 0.4, darkAlpha: 0.10)
    static let ghostRim = themed(0xFFFFFF, 0xFFFFFF, lightAlpha: 0.85, darkAlpha: 0.38)
    /// The cool grey drop (`0 8px 20px -6px`) and the warm light bounce off
    /// the top-left (`-4px -4px 12px`). The hue is the component's own
    /// #94A0B5; on dark it weakens rather than flips, because a cool glow
    /// still reads as depth on black.
    static let ghostCast = themed(0x94A0B5, 0x94A0B5, lightAlpha: 0.45, darkAlpha: 0.28)
    static let ghostGlow = themed(0xFFFFFF, 0xFFFFFF, lightAlpha: 0.5, darkAlpha: 0.18)
    /// The secondary's label, rest then engaged. Dark uses the app's own
    /// ivory at the component's 55% so a link matches the paragraph it sits
    /// under.
    static let ghostLabel = themed(0x141419, 0xF5F0EB, lightAlpha: 0.55, darkAlpha: 0.55)
    static let ghostLabelHi = themed(0x0A0A0C, 0xF5F0EB)

    /// The midpoint of the sweep that crosses the primary when it is engaged.
    /// White in both themes: a specular highlight is white on near-black
    /// glass and white on brushed metal — the one token with no polarity.
    static let shine = themed(0xFFFFFF, 0xFFFFFF, lightAlpha: 0.7, darkAlpha: 0.7)

    // -------------------------------------------------- the icon button
    //
    // The PRESS-AND-REFUSE half of the material, measured off the owner's
    // second Framer component (`Glassy-button-wkgf`) — an icon button with
    // four real states where the pill has two.
    //
    // THE FACE IS LIGHT METAL IN BOTH THEMES, and getting that wrong is what
    // made the settings gear a black disc on a white page.
    //
    // The first pass reused `glassTop`/`glassBottom` on the reasoning that the
    // component's shell ramp (#FFF -> #C9C9C9 -> #A1A1A1 -> #757575 -> #FFF)
    // IS the light metal this file already decomposed for the navbar shell.
    // That is true of those tokens' DARK values and false of their light ones:
    // in light theme `glassTop`/`glassBottom` are the Glass CTA's near-black
    // #26262A -> #08080A, because a primary pill on paper has to be dark to
    // read. Wiring an icon button to them painted it with the pill's fill.
    //
    // `Glassy-button-wkgf` has ONE appearance, not two. A brushed metal disc
    // has enough internal contrast to sit on white and on true black alike -
    // which is exactly why the ramp runs from #FFF to #757575 and back inside a
    // single control - so these are theme-INVARIANT on purpose. That is also
    // why the glyph on it is dark in both themes: the face it sits on is light
    // in both.

    /// The machined rim, as the component paints it: white lip, two greys, a
    /// dark underside, white again. Five stops rather than two, because the
    /// second white at 100% is what makes the bottom edge read as a turned
    /// surface catching light rather than as a shadow.
    static let iconShellLip = themed(0xFFFFFF, 0xFFFFFF)
    static let iconShellHigh = themed(0xC9C9C9, 0xC9C9C9)
    static let iconShellMid = themed(0xA1A1A1, 0xA1A1A1)
    static let iconShellLow = themed(0x757575, 0x757575)

    /// The face. `150deg` in the component: mostly down, tilted right, and
    /// almost flat in value (#D0D0D0 -> #CCCCCC -> #C8C8C8) because the drama
    /// belongs to the rim around it, not to the plate itself.
    static let iconFace = themed(0xD0D0D0, 0xD0D0D0)
    static let iconFaceMid = themed(0xCCCCCC, 0xCCCCCC)
    static let iconFaceLow = themed(0xC8C8C8, 0xC8C8C8)

    /// Engaged. The component lifts only the MIDPOINT, to #E8E8E8 - the plate
    /// catches more light across its middle while its edges stay put.
    static let iconFaceMidHi = themed(0xE8E8E8, 0xE8E8E8)

    /// The glyph on that face, and its echo. Dark in both themes for the
    /// reason above. 6.1:1 against the #C8C8C8 corner, the worst case.
    static let iconInk = themed(0x0A0A0C, 0x0A0A0C)

    // iOS-ONLY, DELIBERATELY. None of these have a CSS counterpart: no web
    // surface has a pure icon button - the extension's controls are text
    // pills and a glyph-plus-text toggle - and a declaration with no
    // consumer is weightless code. Adding them to the three CSS blocks
    // would also move bytes `extension/tests/test_theme_contract.mjs`
    // requires to be byte-identical, for a rule nothing reads.

    /// The cast under a control being pressed INTO the page rather than
    /// lifted off it. The component ramps its eight cast layers to a
    /// NEGATIVE spread and flattens every alpha to ~0.03 at the same time:
    /// the halo stops growing and pulls in. So this is one FLAT value, not a
    /// ramp — GlassyIconStyle spends it uniformly across its three draws,
    /// because uniform is what a pressed shadow is.
    ///
    /// 0.08 is the component's own 0.03 folded eight layers into three
    /// (0.03 x 8/3). Not `glassCast`'s much larger fold: that one collapses a
    /// whole ramp into a SINGLE draw, and three tightly-stacked draws at
    /// 0.12+ compose into a hard dark seam on paper rather than the flat one
    /// the component presses in. Polarity is `glassCast`'s, for `glassCast`'s
    /// reason: black on true black is arithmetically nothing.
    static let sinkCast = themed(0x000000, 0xFFFFFF, lightAlpha: 0.08, darkAlpha: 0.05)

    /// A control that is REFUSING. The component drops both the shell ramp
    /// and the face gradient to one flat #CFCFCF and closes the 3px rim up:
    /// a dead control has no lit edge and no depth, which is the whole
    /// message. #CFCFCF is the DARK theme's value here, dark being the
    /// light-metal polarity; light gets the near-black face's own midpoint
    /// (#17171A) flattened and lifted a touch, so the same object dies the
    /// same way in both themes.
    /// LIGHT GREY IN BOTH THEMES, and the light value used to be #1A1A1E.
    /// Same mistake as the face: a dark disabled plate was chosen to sit under
    /// the near-black PILL, but `DeadPlate` is shared with the icon button,
    /// whose face is light metal — so a disabled send arrow rendered as a black
    /// disc on a white page. The component's own disabled is rgb(207,207,207),
    /// one flat grey, and it is the right answer for both: a refusing control
    /// has to look INERT, and a dark pill that stays dark looks enabled.
    static let offFill = themed(0xCFCFCF, 0xCFCFCF)
    /// The one bright line a dead control keeps: the component's
    /// `1px 2px 0 rgba(255,255,255,0.7)` bottom rim, which is what makes it
    /// read as seated INTO the page instead of merely grey. 0.7 on dark
    /// only — on the light theme's near-black control a 0.7 white rim
    /// outshines `glassRim` (0.28), and the disabled button would be the
    /// brightest-edged thing on the screen.
    static let offRim = themed(0xFFFFFF, 0xFFFFFF, lightAlpha: 0.35, darkAlpha: 0.7)
    /// The glyph on a refusing control: `glassLabel` at the component's own
    /// 0.4. That measures 3.8:1 on the light face and 2.6:1 on the metal
    /// one — deliberately under AA, because a glyph you can see but not
    /// quite read is precisely what "you cannot press this" looks like.
    /// Nothing wearing this ever carries a sentence; the words are in the
    /// label beside it.
    /// The glyph on a refusing control, at the component's 0.4. Dark in both
    /// themes now, because the plate under it is light in both — white at 40%
    /// on #CFCFCF is very nearly nothing.
    static let offInk = themed(0x08080A, 0x08080A, lightAlpha: 0.4, darkAlpha: 0.4)
    /// The soft white copy of the glyph the component draws UNDER the real
    /// one, offset to 53%/54%. White in both themes and the second token
    /// with no polarity, for `shine`'s reason: it is a highlight, not a
    /// letter. It only has to be PERCEPTIBLE — a 3.8:1 step against the
    /// light face and 1.3:1 against the metal one, which is a lift you can
    /// see and never read.
    static let iconEcho = themed(0xFFFFFF, 0xFFFFFF, lightAlpha: 0.4, darkAlpha: 0.4)
}

/// The anti-synthetic texture. Flat #000000 is the flattest surface a phone can
/// render and reads as an absence of pixels; flat white reads as a stock
/// template. A whisper of generated grain makes either one a material.
/// Generated at runtime, never bundled — a shipped PNG always ends up looking
/// like a downloaded stock texture.
enum Grain {
    static let image: Image = {
        let noise = CIFilter(name: "CIRandomGenerator")!.outputImage!
        let mono = noise.applyingFilter("CIColorControls",
                     parameters: [kCIInputSaturationKey: 0, kCIInputContrastKey: 1.0])
        let tile = mono.cropped(to: CGRect(x: 0, y: 0, width: 512, height: 512))
        let cg = CIContext().createCGImage(tile, from: tile.extent)!
        return Image(uiImage: UIImage(cgImage: cg)).resizable(resizingMode: .tile)
    }()
}

/// Grain has to ADD light to ink and REMOVE it from paper — same texture,
/// opposite operator. `.plusLighter` on white is a haze that eats the contrast
/// of everything under it; `.multiply` on black collapses to nothing, which is
/// how you conclude grain "doesn't work".
///
/// One view, used by both the overlay modifier and by any screen that needs the
/// texture as a LAYER under its content instead of over it. HomeView had its own
/// copy with `.plusLighter` hard-coded, which survived the light-mode change and
/// put a white haze over a white page — the exact defect this type exists to
/// make impossible to repeat.
struct GrainLayer: View {
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        Grain.image
            .opacity(scheme == .dark ? 0.035 : 0.03)
            .blendMode(scheme == .dark ? .plusLighter : .multiply)
            .allowsHitTesting(false)
            .ignoresSafeArea()
    }
}

struct GrainOverlay: ViewModifier {
    func body(content: Content) -> some View {
        content.overlay(GrainLayer())
    }
}

extension View {
    /// One call per screen root, above Theme.bg.
    func grainOverlay() -> some View { modifier(GrainOverlay()) }
}

/// The card, with an edge you can actually see and a light source above it.
///
/// The old border was a flat #252525 on #1E1E1E — a contrast ratio of 1.09:1,
/// i.e. optically absent on all eleven cards. And the app had no shadows, no
/// materials and no blur anywhere, so nothing ever sat ON anything; everything
/// was painted flat onto the same black.
///
/// Both mechanisms it fixes that with are DARK-ONLY as written: a white top
/// edge is invisible on white, and a 55%-black shadow under a card on paper is
/// a bruise. Each therefore flips with the scheme — the ONE reason this
/// modifier reads the environment.
struct CardBackground: ViewModifier {
    var elevated = false
    @Environment(\.colorScheme) private var scheme
    private var r: CGFloat { elevated ? Theme.Radius.hero : Theme.Radius.card }
    private var dark: Bool { scheme == .dark }

    /// Lit from above in both themes: on ink that means white at the top, on
    /// white it means the DARKEST hairline at the bottom, where a real object
    /// occludes the page.
    private var edge: LinearGradient {
        let top = dark ? Color.white.opacity(0.11) : Color.black.opacity(0.07)
        let bottom = dark ? Color.white.opacity(0.03) : Color.black.opacity(0.16)
        return LinearGradient(colors: [top, bottom], startPoint: .top, endPoint: .bottom)
    }

    func body(content: Content) -> some View {
        content
            .padding(elevated ? Theme.Space.roomy : Theme.Space.card)
            .background(
                RoundedRectangle(cornerRadius: r, style: .continuous)
                    .fill(elevated ? Theme.raised : Theme.card)
                    .overlay(
                        RoundedRectangle(cornerRadius: r, style: .continuous)
                            .strokeBorder(edge, lineWidth: 0.75)
                    )
            )
            // Two soft layers rather than one heavy one: a single big shadow
            // goes muddy against near-black. On paper the whole stack drops to
            // about a tenth of that — warm, not grey, because a neutral shadow
            // on a warm page reads as dirt.
            .shadow(color: dark ? .black.opacity(elevated ? 0.70 : 0.50)
                                : Theme.pageShadow.opacity(elevated ? 0.09 : 0.07),
                    radius: 2, y: 1)
            .shadow(color: dark ? .black.opacity(elevated ? 0.60 : 0.40)
                                : Theme.pageShadow.opacity(elevated ? 0.13 : 0.10),
                    radius: 14, y: 8)
    }
}

extension View {
    func cardSurface(elevated: Bool = false) -> some View {
        modifier(CardBackground(elevated: elevated))
    }
    /// The name the eleven existing call sites already use — kept so every one
    /// of them picks up the visible edge and the elevation without being edited.
    func anticipyCard() -> some View { modifier(CardBackground()) }
}

extension Color {
    init(hex: UInt32) {
        self.init(
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255
        )
    }
}

extension UIColor {
    convenience init(hex: UInt32, alpha: CGFloat = 1) {
        self.init(
            red: CGFloat((hex >> 16) & 0xFF) / 255,
            green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255,
            alpha: alpha
        )
    }
}

/// A token whose VALUE depends on the theme, resolved by UIKit at draw time
/// rather than read once at launch — so a switch in Settings repaints the app
/// without anything having to observe anything.
///
/// It resolves off the trait collection, which AnticipyApp pins with
/// .preferredColorScheme. That is what makes "light unless you chose dark" a
/// property of one line in one file instead of a rule every view has to know.
func themed(_ light: UInt32, _ dark: UInt32,
            lightAlpha: CGFloat = 1, darkAlpha: CGFloat = 1) -> Color {
    Color(UIColor { trait in
        trait.userInterfaceStyle == .dark
            ? UIColor(hex: dark, alpha: darkAlpha)
            : UIColor(hex: light, alpha: lightAlpha)
    })
}

extension Theme {
    /// The shadow colour on a white page. Near-black rather than pure black: a
    /// hard black shadow on white reads as a border that slipped.
    static let pageShadow = Color(hex: 0x111111)
}

/// The Anticipy pendant mark: a pill outline in the page's own letter colour
/// with an accent dot, exactly the proportions of the anticipy.ai logo SVG.
/// The outline was `ivory` — an invisible logo the moment the page is paper.
struct LogoMark: View {
    var size: CGFloat = 64
    var lineWidth: CGFloat { size * 0.07 }

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let pillW = w * (11.0 / 32.0)
            let pillH = w * (26.0 / 32.0)
            ZStack {
                RoundedRectangle(cornerRadius: pillW / 2)
                    .strokeBorder(Theme.text, lineWidth: lineWidth)
                    .frame(width: pillW, height: pillH)
                Circle()
                    .fill(Theme.accent)
                    .frame(width: w * (3.6 / 32.0), height: w * (3.6 / 32.0))
                    .offset(y: w * (4.0 / 32.0))
            }
            .frame(width: w, height: geo.size.height)
        }
        .frame(width: size, height: size)
    }
}

/// Haptic vocabulary: light tap for touches, medium for state changes,
/// notification haptics for outcomes, and signature patterns for the moments
/// worth remembering. No-ops gracefully in the simulator.
enum Haptics {
    // Retained, not built per call. A generator created and released inside one
    // statement never gets to warm the Taptic Engine, and a cold engine drops
    // or delays the first tap — which reads exactly like "haptics don't work".
    private static let lightGen = UIImpactFeedbackGenerator(style: .light)
    private static let mediumGen = UIImpactFeedbackGenerator(style: .medium)
    private static let softGen = UIImpactFeedbackGenerator(style: .soft)
    private static let rigidGen = UIImpactFeedbackGenerator(style: .rigid)
    private static let noticeGen = UINotificationFeedbackGenerator()

    /// Wake the engine so the NEXT touch is instant. Cheap; call it when the
    /// app becomes active. Each fire below also re-prepares for the same reason.
    static func warmUp() {
        // The CoreHaptics engine is warmed so the DIAGNOSTIC can use it. The
        // app's own feedback below stays on UIFeedbackGenerator — the
        // documented API for UI feedback — until the diagnostic proves
        // something better. Build 33 shipped one theory; it did not work.
        HapticEngine.shared.start()
        lightGen.prepare(); mediumGen.prepare(); softGen.prepare()
        rigidGen.prepare(); noticeGen.prepare()
    }

    static func tap() { lightGen.impactOccurred(); lightGen.prepare() }
    /// A page turn is a selection, and iOS users expect the tick.
    private static let selectionGen = UISelectionFeedbackGenerator()
    static func pageTurn() { selectionGen.selectionChanged(); selectionGen.prepare() }
    static func engage() { mediumGen.impactOccurred(); mediumGen.prepare() }
    static func success() { noticeGen.notificationOccurred(.success); noticeGen.prepare() }
    static func warning() { noticeGen.notificationOccurred(.warning); noticeGen.prepare() }

    /// Two soft rising taps — the feeling of two things finding each other.
    static func pairing() {
        softGen.impactOccurred(intensity: 0.6)
        mediumGen.prepare()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.18) {
            mediumGen.impactOccurred(intensity: 1.0)
            mediumGen.prepare()
        }
    }

    /// A crisp double-tap: something she promised is now done.
    static func taskDone() {
        rigidGen.impactOccurred(intensity: 0.7)
        rigidGen.prepare()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.12) {
            rigidGen.impactOccurred(intensity: 1.0)
            rigidGen.prepare()
        }
    }

    /// One barely-there tick as her words start to appear.
    static func herMessage() {
        softGen.impactOccurred(intensity: 0.45)
        softGen.prepare()
    }
}

/// The button styles live in Views/GlassControls.swift, on the material the
/// `glass*` / `ghost*` / `off*` tokens above describe: `GlassCTAStyle`
/// (`.glass`), `GhostLinkStyle` (`.ghost`), `GlassyIconStyle` (`.icon`) and
/// `ArrowCTAStyle` (`.arrow`). Four styles, one material — that is the
/// distinction that matters, not the count. `Pressable` — a 0.96 scale and a
/// brightness lift, applied over whatever background each call site had
/// painted for itself — was deleted, because a style that describes no
/// material is how a codebase ends up with two conventions. Every tappable
/// thing in the app now reads one of those four names and decides nothing
/// else.

/// Her words appear the way a person's would: typed, quickly, with a cursor.
/// People trust what they can watch being made (the labor illusion) — a block
/// of instant text reads as a machine; typing reads as her. Tap to finish.
struct TypewriterText: View {
    let text: String
    // She IS this component — it defaults to her voice register, not the
    // secondary one. One tempo everywhere: two speeds is two voices.
    var font: Font = .system(size: 17)
    var color: Color = Theme.text
    var onDone: (() -> Void)? = nil

    @State private var shown = ""
    @State private var typing = false
    @State private var caret = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        Text(shown)
            .font(font)
            .foregroundStyle(color)
            // The caret blinks on its own clock rather than being composed
            // into the string, so it does not retrigger text layout.
            .overlay(alignment: .bottomTrailing) {
                if typing {
                    Text("▍")
                        .font(font)
                        .foregroundColor(Theme.accent)
                        .opacity(caret ? 1 : 0)
                        .animation(.easeInOut(duration: 0.53).repeatForever(autoreverses: true),
                                   value: caret)
                        .onAppear { caret = true }
                        .alignmentGuide(.trailing) { d in d.width * 2 }
                }
            }
            .contentShape(Rectangle())
            // VoiceOver was handed an element that mutated ~36 times a second,
            // one character at a time, with a cursor glyph composed into the
            // string. Announce the finished sentence, once.
            .accessibilityLabel(text)
            .onTapGesture {
                shown = text
                typing = false
                onDone?()
            }
            .task(id: text) {
                // Reduce Motion means "don't animate at me" — typing IS an
                // animation, so the whole sentence simply appears.
                if reduceMotion {
                    shown = text
                    typing = false
                    onDone?()
                    return
                }
                shown = ""
                typing = true
                Haptics.herMessage()
                for ch in text {
                    guard typing else { return }
                    shown.append(ch)
                    // She breathes at punctuation — running straight through
                    // a full stop is what makes typed text read as streaming
                    // rather than speaking.
                    //
                    // The em dash is spelled as an escape, not typed: the
                    // app's own copy no longer contains one, but the brain's
                    // sentences arrive from a model and still do, and this is
                    // the pause table for whatever it is handed. Same spelling
                    // as the sentence splitter in `AnticipyApp`.
                    let base = 1_000_000_000.0 / 40.0
                    let mult: Double = ".?!".contains(ch) ? 8
                                     : ",;:\u{2014}".contains(ch) ? 4 : 1
                    try? await Task.sleep(nanoseconds: UInt64(base * mult))
                }
                typing = false
                onDone?()
            }
    }
}

/// A listening app shows a waveform, never a spinner. Three accent capsules
/// moving on the 0.8s harmonic — half the app's 1.6s breath.
struct WaveBars: View {
    @State private var up = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        HStack(spacing: 3) {
            ForEach(0 ..< 3, id: \.self) { i in
                RoundedRectangle(cornerRadius: 1.5)
                    // Theme.accent, not Theme.fill: champagne measures 2.23:1
                    // on white, so a 3pt champagne bar on a white page is a bar
                    // nobody can see. On black it resolves to champagne.
                    .fill(Theme.accent)
                    .frame(width: 3, height: 10)
                    .scaleEffect(y: (up && !reduceMotion) ? 1.0 : 0.4)
                    .animation(
                        reduceMotion ? .default
                            : .easeInOut(duration: 0.8)
                                .repeatForever(autoreverses: true)
                                .delay([0, 0.13, 0.27][i]),
                        value: up
                    )
            }
        }
        .onAppear { up = true }
        .accessibilityHidden(true)
    }
}

/// One dot of a staggered sequence — the same 1.6s breath as BreathingDot,
/// offset so a row of them pulses in order.
struct PulseDot: View {
    var delay: Double = 0
    @State private var up = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        Circle()
            .fill(Theme.accent)
            .frame(width: 6, height: 6)
            .opacity((up && !reduceMotion) ? 1.0 : 0.35)
            .animation(
                reduceMotion ? .default
                    : .easeInOut(duration: 1.6).repeatForever(autoreverses: true).delay(delay),
                value: up
            )
            .onAppear { up = true }
            .accessibilityHidden(true)
    }
}

/// The app's heartbeat: the champagne dot breathing slowly whenever she is
/// listening or working. A still screen reads as dead; a breathing one is her.
struct BreathingDot: View {
    var size: CGFloat = 10
    var active: Bool = true
    @State private var up = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    /// A forever-repeating pulse is exactly what Reduce Motion exists to stop,
    /// and this one sits on the home screen the whole time she is listening.
    private var animates: Bool { active && !reduceMotion }

    var body: some View {
        Circle()
            .fill(Theme.accent)
            .frame(width: size, height: size)
            // 1.16 is a breath; 1.25 was a pulse. 1.6s is the app's one
            // ambient harmonic — everything that loops forever runs on it or
            // a clean multiple of it.
            .scaleEffect(animates && up ? 1.16 : 1.0)
            .opacity(active ? (animates && up ? 1.0 : 0.7) : 0.5)
            .animation(
                animates ? .easeInOut(duration: 1.6).repeatForever(autoreverses: true) : .default,
                value: up
            )
            .onAppear { if animates { up = true } }
            // Decoration: it says nothing a label elsewhere doesn't already say.
            .accessibilityHidden(true)
    }
}
