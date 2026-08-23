import SwiftUI

/// THE CONTROLS. Everything tappable in this app is one of these.
///
/// They are a translation of the owner's Framer components
/// (`Liquid-Glass-Navbar-6gh01a` → `Glass CTA` and `Nav Link`,
/// `Text-Arrow-CTA-qdMepe` → the text CTA, and `Glassy-button-wkgf` → the
/// icon button) into SwiftUI, measured value by value, not an interpretation
/// of them. The colours all come from the `glass*` / `ghost*` / `off*` /
/// `shine` block in Theme.swift, so this file names no colour and the
/// material stays one decision made in one place.
///
/// WHY A ButtonStyle AND NOT A MODIFIER. A modifier cannot see the press. The
/// component's whole character is in its engaged state — the fill brightens,
/// the rim doubles, the shadow drops further, and a specular band sweeps
/// across — and on iOS the only thing that can observe that is the style.
///
/// HOVER BECOMES PRESS, AND THAT IS THE WHOLE MAPPING. The component is a web
/// component, so every one of its second states is a `:hover`. iOS has no
/// hover: a finger is either off the glass or on it. So the `*Hi` tokens —
/// `glassTopHi`, `glassRimHi`, `glassCastHi`, and the entire `ghost*` set,
/// which is transparent until hovered — are wired to `isPressed` here. That is
/// why nothing in the token block is unused despite iOS having half the states.
///
/// WHAT COULD NOT BE COPIED. CSS `box-shadow: inset` has no SwiftUI
/// equivalent; there is no way to paint a 1px light INSIDE an edge. The rim
/// and the floor are therefore drawn as a single 1pt `strokeBorder` carrying a
/// vertical gradient — `glassRim` at the top, `glassUnder` at the bottom —
/// which puts the same two lines in the same two places with one draw. It is
/// a translation, not a copy, and it is the honest one: a real inner shadow
/// would need a blurred, masked, offset copy of the shape per edge. The icon
/// button's DISABLED state is three inset layers at once and gets the same
/// treatment for the same reason — see GlassyIconStyle.
///
/// AND NO SOUND. `Glassy-button-wkgf` ships an mp3 and fires it on every
/// press. Not translated, and not an oversight: this product's whole posture
/// is that she works in a collapsed background tab group and never comes to
/// the foreground on her own. An app built to stay out of the way does not
/// make a noise every time it is touched. The press has a haptic, which is
/// the private form of the same acknowledgement.

// MARK: - The primary

/// The primary action: one per screen, the thing the sentence above it asked
/// you to do. Continue, Send it, Yes go ahead, Open my mail.
///
/// Geometry straight off the component: a full pill (`999px`), `11pt/24pt`
/// padding, a 14pt/600 label at `0.01em`. Press is `scale(0.9)` on the
/// navbar's own tap spring (`bounce .2, duration .25` → response .25 /
/// damping .8).
struct GlassCTAStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        PressBody(configuration: configuration)
    }

    /// The press watcher lives in its OWN view with real `@State`. A
    /// ButtonStyle's body is rebuilt with unstable identity, so an `.onChange`
    /// hung directly off `configuration.label` can lose the value it compares
    /// against and silently stop firing — the defect `Pressable` documented
    /// before this file replaced it.
    ///
    /// NOT named `Body`: that is `ButtonStyle`'s own associated type, and a
    /// nested type of that name is picked up as the conformance instead of
    /// being inferred from `makeBody`, which fails to compile.
    private struct PressBody: View {
        let configuration: ButtonStyleConfiguration
        @Environment(\.isEnabled) private var isEnabled
        @State private var wasPressed = false

        private var down: Bool { configuration.isPressed }

        var body: some View {
            configuration.label
                // A DEFAULT, not a decree: a label that sets its own font
                // wins, which is how the one hero control on the home screen
                // keeps its display type while wearing the same material.
                .font(.system(size: 14, weight: .semibold))
                // 0.01em at 14pt.
                .tracking(0.14)
                .foregroundStyle(isEnabled ? Theme.glassLabel : Theme.offInk)
                // The component is 36pt tall. iOS asks for 44 (HIG, Layout),
                // and a 36pt primary is a genuinely harder tap on glass than
                // in a browser, so the label carries the difference and the
                // 11/24 padding stays exactly as measured.
                .frame(minHeight: 22)
                .padding(.vertical, 11)
                .padding(.horizontal, 24)
                .background { plate }
                .scaleEffect(down ? 0.9 : 1)
                // Not Theme.spring: the navbar gives its tap its own faster
                // spring, and a 0.9 scale on the app's 0.35 response reads as
                // a lag rather than a press.
                .animation(.spring(response: 0.25, dampingFraction: 0.8), value: down)
                .onChange(of: configuration.isPressed) { pressed in
                    if pressed && !wasPressed { Haptics.tap() }
                    wasPressed = pressed
                }
        }

        /// REFUSING LOOKS LIKE SOMETHING NOW. This was `.opacity(0.45)` — a
        /// blunt instrument that dimmed the glass, the rim, the label and the
        /// cast by the same amount, so a disabled primary was a faint LIVE
        /// button rather than a dead one. `Glassy-button-wkgf` says what dead
        /// is, and it is not translucency: the gradient collapses to one flat
        /// fill, the cast goes entirely, and the only light left is a hard
        /// rim under the bottom edge, which seats the control INTO the page.
        /// The icon button says it the same way, in the same tokens — the two
        /// styles refuse in one voice, which is the point of them sharing a
        /// material at all.
        @ViewBuilder private var plate: some View {
            if isEnabled {
                ZStack {
                    Capsule().fill(
                        LinearGradient(colors: down ? [Theme.glassTopHi, Theme.glassBottomHi]
                                                    : [Theme.glassTop, Theme.glassBottom],
                                       startPoint: .top, endPoint: .bottom))
                    Sweep(sweeping: down)
                }
                // The sweep is 70x90 and the button is neither: the component
                // sets `overflow: clip` for exactly this.
                .clipShape(Capsule())
                .overlay {
                    Capsule().strokeBorder(
                        LinearGradient(colors: [down ? Theme.glassRimHi : Theme.glassRim,
                                                Theme.glassUnder],
                                       startPoint: .top, endPoint: .bottom),
                        lineWidth: 1)
                }
                // CSS blur is twice SwiftUI's radius, and the -6px spread is
                // folded in: `0 7px 16px -6px` → radius 5, y 7;
                // `0 12px 24px -6px` → radius 9, y 12.
                .shadow(color: down ? Theme.glassCastHi : Theme.glassCast,
                        radius: down ? 9 : 5, x: 0, y: down ? 12 : 7)
            } else {
                DeadPlate(shape: Capsule())
            }
        }
    }
}

/// The specular band. 70x90, `left:-70px; top:-20px`, rotated 20°, and on
/// engage it travels to `right:-70px` — i.e. from just off one end to just off
/// the other — over 0.8s on `cubic-bezier(.25,.1,.25,1)`.
///
/// A tap is usually shorter than 0.8s, so the band normally gets partway
/// across and glides back. That is correct rather than a compromise: on the
/// web the sweep also reverses the moment the pointer leaves.
private struct Sweep: View {
    let sweeping: Bool

    var body: some View {
        GeometryReader { geo in
            Rectangle()
                .fill(LinearGradient(
                    colors: [Theme.shine.opacity(0), Theme.shine, Theme.shine.opacity(0)],
                    startPoint: .leading, endPoint: .trailing))
                .frame(width: 70, height: 90)
                .rotationEffect(.degrees(20))
                // `right:-70px` on a 70-wide band puts its leading edge at
                // the container's trailing edge, so the travel is -70 → width.
                .offset(x: sweeping ? geo.size.width : -70, y: -20)
                .opacity(sweeping ? 1 : 0)
                .animation(.timingCurve(0.25, 0.1, 0.25, 1, duration: 0.8), value: sweeping)
        }
        .allowsHitTesting(false)
    }
}

// MARK: - What refusing looks like

/// `Glassy-button-wkgf`'s disabled state, said ONCE and generic over its
/// shape, so the pill and the icon button refuse identically: one flat
/// `offFill` — the gradient is gone, because a dead control has no light
/// source — the component's three `inset` layers folded into a single 2pt
/// inner border from the top-left, its `1px 2px 0` bright rim hard under the
/// bottom edge, and NO cast at all, because a control that refuses is not
/// lifted off anything.
///
/// WHY `onFill` CARRIES THE SEAM. An inset shadow is dark on a light face in
/// BOTH themes, and `onFill` is the only role in Theme that is dark and does
/// not flip: `glassUnder` and `glassCast` each invert to white on dark, which
/// would LIGHT the inner edge of a dead control instead of recessing it. On
/// the light theme's near-black face the seam is nearly invisible — which is
/// also what a shadow inside a dark object looks like — and there the flat
/// fill and the bottom rim carry the message on their own.
private struct DeadPlate<S: InsettableShape>: View {
    let shape: S

    var body: some View {
        shape
            .fill(Theme.offFill)
            .overlay {
                shape.strokeBorder(
                    LinearGradient(colors: [Theme.onFill.opacity(0.16), .clear],
                                   startPoint: .topLeading, endPoint: .center),
                    lineWidth: 2)
            }
            // Zero blur, so this is a LINE and not a glow.
            .shadow(color: Theme.offRim, radius: 0, x: 1, y: 2)
    }
}

// MARK: - The icon

/// A control whose entire label is a glyph: the settings gear in the Home
/// toolbar, the send arrow on the compose line. The owner's second component,
/// `Glassy-button-wkgf` — the same material as the pill, with FOUR real
/// states where the pill has two: at rest, engaged, pressed IN, and refusing.
///
/// WHY A SEPARATE STYLE AND NOT A FLAG ON THE PRIMARY. A pill is sized by its
/// words and a glyph has none, so every geometry value differs: a square face
/// instead of a hugging capsule, a 3pt machined rim instead of a 1pt stroke,
/// a cast that TIGHTENS instead of dropping further, and a second copy of the
/// label under the first. An `iconOnly` flag on GlassCTAStyle would branch on
/// all five and describe neither control.
///
/// PRESSED IS NOT SCALED DOWN. The pill takes `scale(0.9)`; this one does not
/// move at all. Its cast collapses instead — the component ramps all eight
/// shadow layers to a NEGATIVE spread and flattens their alphas in the same
/// keyframe, so the halo pulls in under the object rather than the object
/// shrinking away from the finger. That is what "pressed into the surface"
/// means and it is a different gesture from the primary's, deliberately: one
/// is a thing you push, the other is a thing you poke.
struct GlassyIconStyle: ButtonStyle {
    /// THE COMPONENT'S OWN NUMBERS, AND THEREFORE NOT TOKENS. 40 shell
    /// radius, 37 face radius, 3 rim: three measurements that describe ONE
    /// control, where `Theme.Radius` describes the palette every surface
    /// shares. A `Theme.Radius.icon` would invite the next control to reuse a
    /// number that means nothing outside this file.
    ///
    /// 38 + 3 + 3 = 44, the HIG minimum, so the geometry lands ON the tap
    /// target instead of needing padding bolted onto every call site.
    ///
    /// SwiftUI clamps a corner radius to half the shorter side, so at 44pt
    /// the 40 resolves to a circle and the component's squircle appears only
    /// if a label ever grows the control past 80pt. That clamp is the
    /// framework's; the measurement is unreinterpreted.
    private enum Metric {
        static let face: CGFloat = 38
        static let rim: CGFloat = 3
        static let shell: CGFloat = 40
        static let inner: CGFloat = 37
    }

    func makeBody(configuration: Configuration) -> some View {
        PressBody(configuration: configuration)
    }

    /// Its own view with real `@State`, for the primary's reason: a
    /// ButtonStyle body is rebuilt with unstable identity and an `.onChange`
    /// hung off `configuration.label` can silently stop firing.
    private struct PressBody: View {
        let configuration: ButtonStyleConfiguration
        @Environment(\.isEnabled) private var isEnabled
        @State private var wasPressed = false

        private var down: Bool { configuration.isPressed }

        var body: some View {
            glyph
                .frame(minWidth: Metric.face, minHeight: Metric.face)
                // The rim's 3pt stays on the DISABLED control too. The
                // component sets `padding: 0` there — its face swallowing the
                // rim, which here is the plate becoming one shape — but its
                // two states are variants of a fixed 149x146 frame, where a
                // button on a phone sits in a live layout. A control that
                // resizes when it is disabled shoves everything beside it.
                .padding(Metric.rim)
                .background { plate }
                // `bounce .1, duration .4`. Framer's bounce is the INVERSE of
                // the damping ratio — bounce 0 is critically damped — so .1
                // is a damping fraction of 0.9, which is the same arithmetic
                // the primary's `bounce .2 → damping .8` above already used.
                // High damping is the point: this control settles almost
                // without overshoot, because a 3pt rim wobbling around a
                // glyph reads as a loose part.
                .animation(.spring(response: 0.4, dampingFraction: 0.9), value: down)
                .animation(.spring(response: 0.4, dampingFraction: 0.9), value: isEnabled)
                .onChange(of: configuration.isPressed) { pressed in
                    if pressed && !wasPressed { Haptics.tap() }
                    wasPressed = pressed
                }
        }

        /// THE ICON ECHO. The component draws the glyph TWICE: the real one,
        /// and a white copy at 0.4 nudged to `left:53%, top:54%` — 3% and 4%
        /// of the face off centre, so 1.1pt and 1.5pt here. It is not an
        /// accident of the export; it is a soft light UNDER the letterform,
        /// and it is most of why the glyph reads as cut into the metal rather
        /// than printed on it. It goes out entirely when the control refuses,
        /// because a dead control has no light left to echo.
        private var glyph: some View {
            ZStack {
                configuration.label
                    .foregroundStyle(Theme.iconEcho)
                    .offset(x: Metric.face * 0.03, y: Metric.face * 0.04)
                    .opacity(isEnabled ? 1 : 0)
                configuration.label
                    // `iconInk`, NOT `glassLabel`. The pill's label is white
                    // because the pill is near-black; this face is light metal
                    // in both themes, so a white glyph on it was invisible the
                    // moment the face stopped being the pill's fill.
                    .foregroundStyle(isEnabled ? Theme.iconInk : Theme.offInk)
            }
            // A DEFAULT, not a decree: a label that sets its own font wins,
            // exactly as on the primary.
            .font(.system(size: 17, weight: .semibold))
            // The component takes the icon to 0.8 on press, so the glyph
            // settles INTO the brightening face instead of riding on it.
            .opacity(down ? 0.8 : 1)
        }

        @ViewBuilder private var plate: some View {
            if isEnabled {
                RoundedRectangle(cornerRadius: Metric.shell, style: .continuous)
                    .fill(shell)
                    .overlay {
                        RoundedRectangle(cornerRadius: Metric.inner, style: .continuous)
                            // The face, and the hover brightening that iOS
                            // spends on the press: the component lifts its
                            // midpoint to #E8E8E8, which is what the
                            // `glassTopHi`/`glassBottomHi` pair already means
                            // on the primary. `150deg` is mostly down, tilted
                            // right.
                            .fill(LinearGradient(
                                colors: [Theme.iconFace,
                                         down ? Theme.iconFaceMidHi : Theme.iconFaceMid,
                                         Theme.iconFaceLow],
                                startPoint: UnitPoint(x: 0.25, y: 0),
                                endPoint: UnitPoint(x: 0.75, y: 1)))
                            .padding(Metric.rim)
                    }
                    // THE CAST, AND THE HONEST PART. Eight CSS layers folded
                    // into three draws — near, middle, floor — because eight
                    // blurred offscreen passes per button is a real cost for
                    // ink the eye cannot separate.
                    //
                    // Each draw is the ALPHA-WEIGHTED CENTROID of the pair it
                    // replaces, not that pair's outermost member: the last two
                    // layers are `2.2px 32.97px` at 0.05 and `4px 60px` at
                    // 0.10, whose centre of ink is 15pt down here, not 18.
                    // Folding to the outer edge instead is how a stack of soft
                    // layers turns into one detached blob. The fractions of
                    // `glassCast` restore the component's own summed alphas
                    // (0.02 / 0.05 / 0.15) out of a token whose value is the
                    // primary's single-draw fold.
                    //
                    // CSS blur is twice SwiftUI's radius, and every offset and
                    // blur is then scaled 44/146: a 60px drop under a 146px
                    // object is 0.41 of its own height, so carried across
                    // literally it would put the shadow entirely below a 44pt
                    // button. The RADII above are not scaled — a corner is a
                    // shape, not a distance.
                    //
                    // Pressed has no `spread` to copy; SwiftUI has no such
                    // parameter. So the tightening is reproduced by what
                    // spread actually does to the picture: each layer's offset
                    // pulls in to ~45%, its blur halves, and every alpha
                    // flattens to the one `sinkCast`. Less ink, closer in, no
                    // ramp. A translation, not a copy.
                    // THE FLOOR LAYER WAS 15pt DOWN, which on a 44pt control is a
                    // third of its own height: the ink cleared the button
                    // entirely and read as a second pale plate lying under it
                    // rather than as the button's own shadow. The component's
                    // 60px drop is under a 146px object (0.41 of its height),
                    // and that ratio is what does not survive the trip - a
                    // shadow you can see SEPARATELY from the thing casting it
                    // is not depth, it is two objects.
                    //
                    // So the stack is re-proportioned to this control: the
                    // floor sits at 6pt with a wider blur, which keeps the same
                    // quantity of ink and the same softness while the shape
                    // stays attached to its object.
                    .shadow(color: down ? Theme.sinkCast : Theme.glassCast.opacity(0.06),
                            radius: down ? 0.3 : 0.6, x: 0, y: down ? 0.5 : 1)
                    .shadow(color: down ? Theme.sinkCast : Theme.glassCast.opacity(0.13),
                            radius: down ? 0.9 : 1.8, x: 0, y: down ? 1 : 2.5)
                    .shadow(color: down ? Theme.sinkCast : Theme.glassCast.opacity(0.40),
                            radius: down ? 2.6 : 5.2, x: 0, y: down ? 2.5 : 6)
            } else {
                DeadPlate(shape: RoundedRectangle(cornerRadius: Metric.shell,
                                                  style: .continuous))
            }
        }

        /// The 3pt machined rim. The component's ramp is
        /// `#FFF 0%, #C9C9C9 9%, #A1A1A1 32%, #757575 73%, #FFF 100%`, which
        /// is the navbar shell's own light metal — i.e. rim, fill, rim, the
        /// decomposition Theme.swift already made into `glassRim` /
        /// `glassTop` / `glassBottom` / `glassUnder`. Four stops, not five:
        /// only a 3pt ring of this is ever visible, its top and bottom are
        /// the two white stops, and the ramp between them is read as a 3pt
        /// SIDE edge. Interpolating the 32% stop there costs nothing, where
        /// inventing a fifth token would put a colour decision in a view.
        /// THE COMPONENT'S FIVE STOPS, at its own locations. This was four
        /// stops built from the pill's tokens, which in light theme made the
        /// rim a near-black ramp around a near-black face: one dark blob.
        ///
        /// The two whites are not decoration. #FFF at 0 is the lit top lip and
        /// #FFF at 1 is the bottom edge turning back toward the viewer and
        /// catching light again. Drop either and the control stops being a
        /// machined part and becomes a rectangle with a gradient in it.
        private var shell: LinearGradient {
            LinearGradient(stops: [
                .init(color: Theme.iconShellLip, location: 0),
                .init(color: Theme.iconShellHigh, location: 0.0899),
                .init(color: Theme.iconShellMid, location: 0.3188),
                .init(color: Theme.iconShellLow, location: 0.73),
                .init(color: Theme.iconShellLip, location: 1)
            ], startPoint: .top, endPoint: .bottom)
        }
    }
}

// MARK: - The secondary

/// Everything else: Skip, Not now, I'll do this later, a link, a chip, a row
/// in Settings. The component's `Nav Link` — nothing at all at rest, a frosted
/// pill the moment you touch it.
///
/// Geometry off the component: `999px`, `10pt/15pt` padding, 14pt/500 label.
/// Its three shadows are all present-but-transparent at rest in the original
/// so they animate in rather than pop in; here they are simply given the
/// engaged colour on press and a clear one otherwise, which SwiftUI
/// interpolates the same way.
struct GhostLinkStyle: ButtonStyle {
    /// PILL or ROW. A pill hugs its two words — Skip, Not now, a link at the
    /// end of a sentence. A row is a Settings line or a list entry: it spans
    /// its container, keeps its label on the container's own left edge, and
    /// the whole line is the tap target.
    ///
    /// The row form exists because both alternatives are wrong. Left as a
    /// pill, a Settings label sits 15pt further in than the sentence above it
    /// and the alignment reads as broken; and because a custom ButtonStyle
    /// takes over hit testing from the list, only the WORDS would be
    /// tappable, where the system style this replaces gave the whole row.
    var row = false

    func makeBody(configuration: Configuration) -> some View {
        PressBody(configuration: configuration, row: row)
    }

    private struct PressBody: View {
        let configuration: ButtonStyleConfiguration
        let row: Bool
        @Environment(\.isEnabled) private var isEnabled
        @State private var wasPressed = false

        private var down: Bool { configuration.isPressed }

        var body: some View {
            configuration.label
                .font(.system(size: 14, weight: .medium))
                .tracking(0.14)
                .foregroundStyle(down ? Theme.ghostLabelHi : Theme.ghostLabel)
                // 34pt in the component; 44 here for the same HIG reason as
                // the primary.
                .frame(minHeight: 24)
                // A row fills the width; a pill takes its label's.
                .frame(maxWidth: row ? .infinity : nil, alignment: .leading)
                .padding(.vertical, 10)
                .padding(.horizontal, 15)
                .background {
                    Capsule()
                        .fill(down ? Theme.ghostFill : .clear)
                        // `inset 0 1px 0` is a TOP edge only, so the border
                        // gradient fades to nothing by the middle instead of
                        // ringing the pill.
                        .overlay {
                            Capsule().strokeBorder(
                                LinearGradient(colors: [down ? Theme.ghostRim : .clear, .clear],
                                               startPoint: .top, endPoint: .center),
                                lineWidth: 1)
                        }
                        // `0 8px 20px -6px` cool drop, plus the `-4px -4px
                        // 12px` light bouncing onto the top-left.
                        .shadow(color: down ? Theme.ghostCast : .clear, radius: 7, x: 0, y: 8)
                        .shadow(color: down ? Theme.ghostGlow : .clear, radius: 6, x: -4, y: -4)
                }
                // The whole pill is the target, including the transparent
                // part: a control that is invisible at rest must still be
                // tappable everywhere it will appear.
                .contentShape(Capsule())
                // The 15pt comes straight back off a row, so the label lands
                // where an unstyled row's label lands and the capsule — the
                // hit shape — still covers the full line. Net zero for the
                // text, a full-bleed highlight for the press.
                .padding(.horizontal, row ? -15 : 0)
                .animation(.spring(response: 0.25, dampingFraction: 0.8), value: down)
                .opacity(isEnabled ? 1 : 0.45)
                .onChange(of: configuration.isPressed) { pressed in
                    if pressed && !wasPressed { Haptics.tap() }
                    wasPressed = pressed
                }
        }
    }
}

// MARK: - The text CTA

/// The owner's `Text-Arrow-CTA-qdMepe` component: a text-shaped call to
/// action, no plate, with an arrow that SWAPS SIDES and an underline that
/// WIPES. It is the third material in this file and the narrowest: it goes on
/// a control that takes the person FORWARD to a next screen or a next step,
/// and on nothing else. A decline, a stop, a delete and a standing-state
/// toggle all keep `GhostLinkStyle`, because an arrow is a promise of forward
/// motion and those four controls do not make it.
///
/// HOVER BECOMES PRESS, same mapping as the other two styles: every second
/// state in the component is a `:hover`, and a finger is either off the text
/// or on it. So `down` drives the arrow swap, the wipe and the label lift.
///
/// TIMING IS THE ONE DELIBERATE DEVIATION FROM THE COMPONENT. The original
/// runs a `bounce .3, duration 1` spring, which is a HOVER duration: a
/// pointer rests on a link for as long as it likes. On iOS this fires on a
/// tap that usually navigates, so a 1-second animation is cut off mid-flight
/// by the push transition and reads as a glitch rather than as motion. It
/// therefore runs on `Theme.spring` (response .35), the app's own signature.
/// The extension keeps the full second, because hover there is real.
struct ArrowCTAStyle: ButtonStyle {
    /// ROW or PILL, the same distinction `GhostLinkStyle.row` draws and for
    /// the same reason: a custom style takes hit testing over from the List,
    /// so without this only the WORDS of a Settings line would be tappable.
    ///
    /// It widens the HIT AREA ONLY. The label and the rule keep hugging the
    /// words, which the ghost's row form does not need to do but this one
    /// does: a rule spanning a full Settings line stops being an underline,
    /// and arrows parked 200pt apart cannot be read as one swapping sides.
    var row = false

    func makeBody(configuration: Configuration) -> some View {
        PressBody(configuration: configuration, row: row)
    }

    private struct PressBody: View {
        let configuration: ButtonStyleConfiguration
        let row: Bool
        @Environment(\.isEnabled) private var isEnabled
        @State private var wasPressed = false

        private var down: Bool { configuration.isPressed }

        /// The component's arrow box (20x15) plus its 16px gap to the label.
        /// One number, because it is also exactly how far the label travels.
        private static let arrow: CGFloat = 20
        private static let slot = arrow + Theme.Space.base

        /// The component's rule sits at `top: 129%` of a 24px link, centred,
        /// i.e. 4.06px under a 24px line box. This style's label is 14pt, and
        /// 129% of 14 less half of 14 is 4.06pt — the ratio lands on
        /// `Theme.Space.hair` when you scale the label down. Nothing was
        /// rounded to reach the scale.
        private static let drop = Theme.Space.hair

        /// THE STAGGER, AS A RATIO RATHER THAN AS 300ms. The component delays
        /// one half by 0.3s against a 1s spring: 30% of the spring's own
        /// length. Ported as the ratio, not the number — 30% of a 0.35
        /// response is 0.105 — because what makes two halves read as ONE line
        /// being wiped is how much of the rule survives the hand-off, and that
        /// is a function of the ratio, not of the milliseconds.
        ///
        /// Integrating the spring (response, damping, delay) for the worst
        /// moment of the press gives the coverage that is actually left:
        ///
        ///     component, 1.0s / .70 damping, 0.3s delay -> 26.9% of the rule
        ///     this,      0.35s / .80 damping, 0.105s    -> 32.3%
        ///     this, but with a LITERAL 0.3s delay       ->  0.5%
        ///
        /// So the ratio lands within six points of the original's own
        /// character, and the literal 300ms erases the line completely before
        /// the replacement starts — two bars taking turns, which is the exact
        /// failure this number exists to avoid. Rendered and measured, not
        /// estimated: at the worst frame the rule is one contiguous run of
        /// 38pt out of 121 still anchored to its trailing edge, never two
        /// competing bars.
        private static let stagger: Double = 0.105

        var body: some View {
            HStack(spacing: 0) {
                // THE SWAP, AND WHY IT IS TWO COLLAPSING SLOTS. In the
                // component the leading arrow is `position: absolute` at rest
                // and `position: relative` on hover — it ENTERS THE FLOW and
                // pushes the label right; the trailing arrow leaves it. There
                // is no SwiftUI spelling of that, and transliterating
                // `position: absolute` with an offset would slide the arrow
                // without moving the label, which is the one thing the
                // interaction is made of.
                //
                // So each arrow gets a fixed-width slot whose width animates
                // between 0 and `slot`, and exactly one slot is open at a
                // time. Frame width is animatable, so the label is carried
                // `slot` points sideways by the layout system itself, and the
                // control's total width never changes — the rule under it
                // therefore holds still while the arrow crosses over it.
                slotted(open: down) {
                    chevron
                        .padding(.trailing, Theme.Space.base)
                        // Spins IN from -90°, which is the exact value and
                        // sign the component uses for both arrows.
                        .rotationEffect(.degrees(down ? 0 : -90))
                        .scaleEffect(down ? 1 : 0)
                        .opacity(down ? 1 : 0)
                }
                configuration.label
                    .font(.system(size: 14, weight: .medium))
                    // The component's `-0.02em`. Note the SIGN: the glass and
                    // ghost labels open up by 0.01em, this one tightens, and
                    // that is the component's own value rather than a house
                    // default applied to it.
                    .tracking(-0.28)
                    // No `fixedSize` here, and it is not an oversight: the two
                    // slots are driven by the same spring in opposite
                    // directions, so their widths sum to `slot` at every
                    // instant of the swap. The label's own proposal is
                    // therefore identical at rest, mid-flight and pressed —
                    // it can wrap like the ghost's label does, and it will
                    // never re-wrap while the arrow is crossing.
                slotted(open: !down) {
                    chevron
                        .padding(.leading, Theme.Space.base)
                        .rotationEffect(.degrees(down ? -90 : 0))
                        // No opacity on this one, and that is verbatim: the
                        // component animates opacity on the LEFT arrow only,
                        // because scale 0 has already erased the right one.
                        .scaleEffect(down ? 0 : 1)
                }
            }
            // THE WIPE LIVES IN AN OVERLAY, not as a VStack sibling. A rule
            // asking for `maxWidth: .infinity` inside a VStack would drag the
            // whole stack out to the container's width and take the label with
            // it; an overlay is measured by what it sits on, so the rule spans
            // the words and nothing else even when the hit area is a full row.
            .overlay(alignment: .bottom) { wipe.offset(y: Self.drop + 1) }
            // The overlay is outside the layout, so the space it occupies has
            // to be given back or the rule lands on the next row.
            .padding(.bottom, Self.drop + 1)
            // CURRENTCOLOR. The arrows and both halves of the rule are drawn
            // with no fill of their own, so they inherit this — which means
            // the hairline sits at exactly the label's weight at rest AND
            // brightens with it on press, at the moment the wipe is running
            // and needs to be seen. A separate token for the rule would be
            // the same family by a number four surfaces have to keep in sync;
            // inheritance is the same family by construction.
            .foregroundStyle(down ? Theme.ghostLabelHi : Theme.ghostLabel)
            .animation(Theme.spring, value: down)
            // Hit area only. The words stay where an unstyled row's words
            // would be, so a converted Settings line does not shift 15pt.
            .frame(maxWidth: row ? .infinity : nil, alignment: .leading)
            .contentShape(Rectangle())
            .opacity(isEnabled ? 1 : 0.45)
            .onChange(of: configuration.isPressed) { pressed in
                if pressed && !wasPressed { Haptics.tap() }
                wasPressed = pressed
            }
        }

        /// One arrow in a slot that is either `slot` wide or gone. Not
        /// clipped: mid-swap the glyph is part-scaled and part-rotated and
        /// overflows its shrinking slot, which is what a spin looks like.
        /// Clipping it would shear the arrow instead.
        private func slotted<C: View>(open: Bool, @ViewBuilder _ content: () -> C) -> some View {
            content().frame(width: open ? Self.slot : 0)
        }

        private var chevron: some View {
            Image(systemName: "chevron.right")
                .font(.system(size: 13, weight: .semibold))
                .frame(width: Self.arrow)
                .accessibilityHidden(true)
        }

        /// TWO HALVES, ONE LINE. The component draws the rule twice and keeps
        /// exactly one of them full: at rest the TRAILING half is the whole
        /// underline and the leading half is a 1% stub; pressed, they exchange.
        /// The trailing half shrinks toward its own trailing edge while the
        /// leading half grows from its leading edge, so the visible end of the
        /// line travels across once. `scaleEffect(x:anchor:)` is that, exactly,
        /// and it beats a GeometryReader for a percentage width.
        ///
        /// THE DELAY ALWAYS BELONGS TO THE HALF THAT IS ARRIVING, never to the
        /// half that is leaving. That is the whole invariant, and it is the one
        /// thing here that is easy to get backwards: put the delay on the
        /// retracting half instead and the growing half is permanently ahead of
        /// it, the union of the two never drops below the full width, and the
        /// rule just sits there. So on press the LEADING half is late — the old
        /// line retreats first and the new one follows it in, so the eye tracks
        /// one moving end rather than watching a line appear on top of a line —
        /// and on release it inverts, exactly as the component inverts it, so
        /// the release is not a rewind of the press. Confirmed against the same
        /// component built for the extension: hover-in there empties the rule
        /// to 24% before refilling, this empties to 32% (a .80 damping is less
        /// bouncy than the component's .70), and both read as one line wiped.
        ///
        /// A ZStack, NOT AN HSTACK, and the component's 32px gap between the
        /// halves is inert for the same reason it is inert in the original: as
        /// a row the two halves would shrink against each other and their used
        /// widths would be pinned to the container, so the late half starts
        /// moving with the early one and the stagger cannot exist at all. Each
        /// half here spans the full width and is anchored to its own end, and
        /// `scaleEffect` is a render transform rather than a layout change, so
        /// neither half can reach the other.
        private var wipe: some View {
            ZStack {
                Rectangle()
                    .frame(height: 1)
                    .scaleEffect(x: down ? 1 : 0.01, anchor: .leading)
                    // The component's `left: -3px` at rest, `0` on hover: the
                    // vanishing stub sits a hair outside the line's own end.
                    .offset(x: down ? 0 : -3)
                    .animation(Theme.spring.delay(down ? Self.stagger : 0), value: down)
                Rectangle()
                    .frame(height: 1)
                    .scaleEffect(x: down ? 0.01 : 1, anchor: .trailing)
                    .offset(x: down ? 3 : 0)
                    .animation(Theme.spring.delay(down ? 0 : Self.stagger), value: down)
            }
            .allowsHitTesting(false)
        }
    }
}

// MARK: - How they are reached

/// `.buttonStyle(.glass)`, `.buttonStyle(.ghost)`, `.buttonStyle(.icon)`,
/// `.buttonStyle(.arrow)`. A call site's only decision is primary, secondary,
/// glyph or forward — never a colour, a radius or a shadow.
extension ButtonStyle where Self == GlassCTAStyle {
    static var glass: GlassCTAStyle { GlassCTAStyle() }
}

extension ButtonStyle where Self == GlassyIconStyle {
    static var icon: GlassyIconStyle { GlassyIconStyle() }
}

extension ButtonStyle where Self == GhostLinkStyle {
    static var ghost: GhostLinkStyle { GhostLinkStyle() }
}

extension ButtonStyle where Self == ArrowCTAStyle {
    static var arrow: ArrowCTAStyle { ArrowCTAStyle() }
}

extension View {
    /// `.ghostRow()` — the secondary as a row. See `GhostLinkStyle.row`.
    func ghostRow() -> some View {
        buttonStyle(GhostLinkStyle(row: true))
    }

    /// `.arrowRow()` — the text CTA with a full-line hit area. The words and
    /// the rule still hug themselves; see `ArrowCTAStyle.row`.
    func arrowRow() -> some View {
        buttonStyle(ArrowCTAStyle(row: true))
    }
}
