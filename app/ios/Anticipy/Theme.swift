import SwiftUI
import UIKit
import CoreImage

/// Anticipy brand system, pulled from anticipy.ai:
/// ink #0C0C0C, surfaces #161616/#1E1E1E, ivory #F5F0EB, champagne #C8A97E.
/// Display type is serif (DM Serif Display on the web; New York on iOS).
enum Theme {
    static let ink = Color(hex: 0x0C0C0C)
    static let surface = Color(hex: 0x161616)
    static let card = Color(hex: 0x1E1E1E)
    static let stroke = Color(hex: 0x252525)
    static let ivory = Color(hex: 0xF5F0EB)
    static let sand = Color(hex: 0xD4CEC7)
    static let gray = Color(hex: 0x8A8A8A)
    static let champagne = Color(hex: 0xC8A97E)

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

    /// Level-2 elevation. The dark ladder is ink -> card -> raised; the third
    /// rung was missing, so nothing could ever sit visibly on top of anything.
    static let raised = Color(hex: 0x262626)
    /// Destructive, in the brand's register. systemRed appears nowhere else in
    /// this product and reads as borrowed from Apple.
    static let alarm = Color(hex: 0xC96A5A)

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

    /// The eye-anchor. ONE per screen, always behind the mark. Two is wallpaper.
    static func bloom(_ opacity: Double = 0.12, radius: CGFloat = 300) -> some View {
        RadialGradient(colors: [Theme.champagne.opacity(opacity), .clear],
                       center: .center, startRadius: 8, endRadius: radius)
            .blur(radius: 30)
            .allowsHitTesting(false)
    }
}

/// The anti-synthetic texture. Flat #0C0C0C is the flattest surface a phone
/// can render and reads as an absence of pixels; a whisper of grain makes it
/// a material. Generated at runtime, never bundled — a shipped PNG always
/// ends up looking like a downloaded stock texture.
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

extension View {
    /// One call per screen root, above Theme.ink. `.plusLighter`, never
    /// `.overlay`: overlay-blend multiplies toward black on a dark base and
    /// collapses to nothing at this luminance.
    func grainOverlay() -> some View {
        overlay(
            Grain.image
                .opacity(0.035)
                .blendMode(.plusLighter)
                .allowsHitTesting(false)
                .ignoresSafeArea()
        )
    }
}

/// The card, with an edge you can actually see and a light source above it.
///
/// The old border was Theme.stroke #252525 on Theme.card #1E1E1E — a contrast
/// ratio of 1.09:1, i.e. optically absent on all eleven cards. And the app had
/// no shadows, no materials and no blur anywhere, so nothing ever sat ON
/// anything; everything was painted flat onto the same black.
struct CardBackground: ViewModifier {
    var elevated = false
    private var r: CGFloat { elevated ? Theme.Radius.hero : Theme.Radius.card }

    func body(content: Content) -> some View {
        content
            .padding(elevated ? Theme.Space.roomy : Theme.Space.card)
            .background(
                RoundedRectangle(cornerRadius: r, style: .continuous)
                    .fill(elevated ? Theme.raised : Theme.card)
                    .overlay(
                        RoundedRectangle(cornerRadius: r, style: .continuous)
                            // 9% white at the top fading to 2% at the bottom is
                            // one light source above, which is what makes a
                            // dark surface read as a physical object.
                            .strokeBorder(
                                LinearGradient(colors: [.white.opacity(0.09), .white.opacity(0.02)],
                                               startPoint: .top, endPoint: .bottom),
                                lineWidth: 0.75)
                    )
            )
            // Two soft layers rather than one heavy one: a single big shadow
            // goes muddy against near-black.
            .shadow(color: .black.opacity(elevated ? 0.55 : 0.35), radius: 2, y: 1)
            .shadow(color: .black.opacity(elevated ? 0.45 : 0.25), radius: 14, y: 8)
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

/// The Anticipy pendant mark: an ivory pill outline with a champagne dot,
/// exactly the proportions of the anticipy.ai logo SVG.
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
                    .strokeBorder(Theme.ivory, lineWidth: lineWidth)
                    .frame(width: pillW, height: pillH)
                Circle()
                    .fill(Theme.champagne)
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

/// Every button in the app responds within a frame: a 0.97 press-scale, a
/// slight dim, and a light haptic the moment the finger lands. Perceived
/// responsiveness is the whole game — the work can take seconds as long as
/// the touch is acknowledged instantly.
struct Pressable: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        // The press watcher lives in its OWN view, not on configuration.label.
        // A ButtonStyle's body is rebuilt with unstable identity, so an
        // .onChange hung directly off the label can lose the previous value it
        // compares against and silently stop firing. A real view with @State
        // gives SwiftUI something stable to hold the press state on.
        PressBody(configuration: configuration)
    }

    private struct PressBody: View {
        let configuration: ButtonStyleConfiguration
        @State private var wasPressed = false

        var body: some View {
            configuration.label
                // 3% scale on a 56pt capsule sits below the perception
                // threshold; on a dark UI the brightness lift is what the
                // eye actually registers.
                .scaleEffect(configuration.isPressed ? 0.96 : 1)
                .brightness(configuration.isPressed ? 0.04 : 0)
                .opacity(configuration.isPressed ? 0.85 : 1)
                .animation(Theme.spring, value: configuration.isPressed)
                .onChange(of: configuration.isPressed) { pressed in
                    if pressed && !wasPressed { Haptics.tap() }
                    wasPressed = pressed
                }
        }
    }
}

extension ButtonStyle where Self == Pressable {
    static var pressable: Pressable { Pressable() }
}

/// Her words appear the way a person's would: typed, quickly, with a cursor.
/// People trust what they can watch being made (the labor illusion) — a block
/// of instant text reads as a machine; typing reads as her. Tap to finish.
struct TypewriterText: View {
    let text: String
    // She IS this component — it defaults to her voice register, not the
    // secondary one. One tempo everywhere: two speeds is two voices.
    var font: Font = .system(size: 17)
    var color: Color = Theme.ivory
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
                        .foregroundColor(Theme.champagne)
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
                    let base = 1_000_000_000.0 / 40.0
                    let mult: Double = ".?!".contains(ch) ? 8
                                     : ",;:—".contains(ch) ? 4 : 1
                    try? await Task.sleep(nanoseconds: UInt64(base * mult))
                }
                typing = false
                onDone?()
            }
    }
}

/// A listening app shows a waveform, never a spinner. Three champagne
/// capsules moving on the 0.8s harmonic — half the app's 1.6s breath.
struct WaveBars: View {
    @State private var up = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        HStack(spacing: 3) {
            ForEach(0 ..< 3, id: \.self) { i in
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(Theme.champagne)
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
            .fill(Theme.champagne)
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
            .fill(Theme.champagne)
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
