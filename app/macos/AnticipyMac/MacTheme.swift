import AppKit
import SwiftUI

/// The Anticipy brand on macOS: the same tokens the phone, the extension and
/// anticipy.ai carry (app/ios/Anticipy/Theme.swift is the reference), resolved
/// by AppKit at draw time so a switch in Settings repaints every window.
///
/// EVERY colour in the Mac app comes through this enum. There is not one raw
/// colour literal in any other Mac file, and run_app_shell_tests.sh scans for
/// that, so no view can decide a colour and no view can be missed.
///
/// Light is the default, as on the phone, and the system setting is not
/// followed: the app opens the same way for everyone and dark is one switch
/// away, remembered under the same key the phone uses.
enum MacTheme {
    // ---------------------------------------------------------- surfaces
    /// The page: white, or true black.
    static let bg = themed(0xFFFFFF, 0x000000)
    /// Recessed: a field, a chip, the sidebar.
    static let surface = themed(0xF2F2F0, 0x0D0D0D)
    static let card = themed(0xFFFFFF, 0x141414)
    static let raised = themed(0xFFFFFF, 0x1C1C1C)
    /// The hairline, as an alpha over whatever it sits on.
    static let edge = themed(0x111111, 0xFFFFFF, lightAlpha: 0.14, darkAlpha: 0.11)
    /// A row the pointer is over, or the selected row's ground.
    static let hover = themed(0x111111, 0xFFFFFF, lightAlpha: 0.05, darkAlpha: 0.07)
    static let selected = themed(0xC8A97E, 0xC8A97E, lightAlpha: 0.22, darkAlpha: 0.20)

    // ----------------------------------------------------------- letters
    static let text = themed(0x111111, 0xF5F0EB)
    static let text2 = themed(0x4D4D4D, 0xD4CEC7)
    /// Labels, counts, timestamps. Never a sentence.
    static let muted = themed(0x6B6B6B, 0x8A8A8A)

    // ------------------------------------------------------------ accent
    /// The accent as a LETTER or a stroke: bronze on white, champagne on ink.
    static let accent = themed(0x7C5729, 0xC8A97E)
    /// The accent as a FILL: champagne in both themes, and what sits on it.
    static let fill = Color(hex: 0xC8A97E)
    static let onFill = Color(hex: 0x0C0C0C)
    /// The ink pill: near-black on paper, ivory on black; and its label.
    static let ink = themed(0x111111, 0xF5F0EB)
    static let onInk = themed(0xFFFFFF, 0x0C0C0C)
    /// Destructive, and the one colour a live recording wears. In the brand's
    /// register rather than systemRed, which appears nowhere in the product.
    static let alarm = themed(0xA03D28, 0xC96A5A)
    static let onAlarm = Color(hex: 0xFFFFFF)
    /// A warning that is not destruction: a lane that dropped, a permission
    /// that is off.
    static let caution = themed(0x8A6B44, 0xD6B27A)

    /// The onboarding ground, the phone's cream, so the first screen on the
    /// Mac is the first screen on the phone.
    static let onboardGround = themed(0xF2EEE7, 0x100E0C)
    static let onboardCard = themed(0xFCFBF8, 0x181512)

    // -------------------------------------------------------------- type
    /// Serif display type, the brand's voice. Reached as a font DESIGN: the
    /// family cannot be named, and naming it falls back to sans silently.
    static func display(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .serif)
    }
    /// Anything she is saying, and every transcript line.
    static let voice = Font.system(size: 15)
    /// Supporting explanation under a control.
    static let aside = Font.system(size: 13)
    /// Labels, counts, timestamps.
    static let meta = Font.system(size: 11, weight: .semibold)
    static let mono = Font.system(size: 11, weight: .medium, design: .monospaced)

    enum Space {
        static let hair: CGFloat = 4
        static let tight: CGFloat = 8
        static let snug: CGFloat = 12
        static let base: CGFloat = 16
        static let card: CGFloat = 20
        static let roomy: CGFloat = 24
        static let section: CGFloat = 32
        static let wide: CGFloat = 40
        static let hero: CGFloat = 64
    }
    enum Radius {
        static let small: CGFloat = 8
        static let control: CGFloat = 10
        static let card: CGFloat = 16
        static let hero: CGFloat = 24
    }

    static let spring = Animation.spring(response: 0.35, dampingFraction: 0.8)
}

/// Which of the two palettes the app is in. Same key and same two rules as
/// the phone's AppTheme: light unless chosen otherwise, and never the
/// system's own setting.
enum MacAppearance: String, CaseIterable {
    case light
    case dark

    static let key = "anticipy.theme"

    init(rawValue: String) {
        self = rawValue == MacAppearance.dark.rawValue ? .dark : .light
    }

    var colorScheme: ColorScheme {
        self == .dark ? .dark : .light
    }

    var label: String {
        self == .dark ? "Dark" : "Light"
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(red: Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255)
    }
}

extension NSColor {
    convenience init(hex: UInt32, alpha: CGFloat = 1) {
        self.init(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255,
                  green: CGFloat((hex >> 8) & 0xFF) / 255,
                  blue: CGFloat(hex & 0xFF) / 255,
                  alpha: alpha)
    }
}

/// A token whose VALUE depends on the appearance, resolved by AppKit at draw
/// time. The window's appearance is pinned by MainWindowView through
/// .preferredColorScheme, so this reads the choice, not the system.
func themed(_ light: UInt32, _ dark: UInt32,
            lightAlpha: CGFloat = 1, darkAlpha: CGFloat = 1) -> Color {
    Color(nsColor: NSColor(name: nil) { appearance in
        let match = appearance.bestMatch(from: [.aqua, .darkAqua])
        return match == .darkAqua
            ? NSColor(hex: dark, alpha: darkAlpha)
            : NSColor(hex: light, alpha: lightAlpha)
    })
}

// MARK: - Components every screen shares

/// The Anticipy pendant mark: a pill outline in the page's letter colour with
/// a champagne dot, the proportions of the anticipy.ai logo.
struct BrandMark: View {
    var size: CGFloat = 40
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: size * (11.0 / 64.0), style: .continuous)
                .strokeBorder(MacTheme.text, lineWidth: max(1.5, size * 0.07))
                .frame(width: size * (11.0 / 32.0), height: size * (26.0 / 32.0))
            Circle()
                .fill(MacTheme.fill)
                .frame(width: size * (3.6 / 32.0), height: size * (3.6 / 32.0))
                .offset(y: size * (4.0 / 32.0))
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

/// The primary control: a champagne pill with ink letters.
struct PrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(MacTheme.onFill)
            .padding(.horizontal, MacTheme.Space.base)
            .padding(.vertical, MacTheme.Space.tight)
            .background(
                RoundedRectangle(cornerRadius: MacTheme.Radius.control, style: .continuous)
                    .fill(MacTheme.fill)
            )
            .opacity(enabled ? (configuration.isPressed ? 0.85 : 1) : 0.45)
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(MacTheme.spring, value: configuration.isPressed)
    }
}

/// The destructive control, worn only by Stop recording and Move to Trash.
struct AlarmButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(MacTheme.onAlarm)
            .padding(.horizontal, MacTheme.Space.base)
            .padding(.vertical, MacTheme.Space.tight)
            .background(
                RoundedRectangle(cornerRadius: MacTheme.Radius.control, style: .continuous)
                    .fill(MacTheme.alarm)
            )
            .opacity(configuration.isPressed ? 0.85 : 1)
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(MacTheme.spring, value: configuration.isPressed)
    }
}

/// The secondary control: a hairline, letters in the page's ink.
struct SecondaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var enabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .medium))
            .foregroundStyle(MacTheme.text)
            .padding(.horizontal, MacTheme.Space.base)
            .padding(.vertical, MacTheme.Space.tight)
            .background(
                RoundedRectangle(cornerRadius: MacTheme.Radius.control, style: .continuous)
                    .fill(configuration.isPressed ? MacTheme.hover : MacTheme.card)
                    .overlay(
                        RoundedRectangle(cornerRadius: MacTheme.Radius.control, style: .continuous)
                            .strokeBorder(MacTheme.edge, lineWidth: 1)
                    )
            )
            .opacity(enabled ? 1 : 0.45)
    }
}

/// A link that is only letters: the accent, underlined on hover.
struct GhostButtonStyle: ButtonStyle {
    @State private var hovering = false
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .medium))
            .foregroundStyle(MacTheme.accent)
            .underline(hovering)
            .opacity(configuration.isPressed ? 0.7 : 1)
            .onHover { hovering = $0 }
    }
}

extension ButtonStyle where Self == PrimaryButtonStyle {
    static var primary: PrimaryButtonStyle { PrimaryButtonStyle() }
}
extension ButtonStyle where Self == AlarmButtonStyle {
    static var alarm: AlarmButtonStyle { AlarmButtonStyle() }
}
extension ButtonStyle where Self == SecondaryButtonStyle {
    static var secondary: SecondaryButtonStyle { SecondaryButtonStyle() }
}
extension ButtonStyle where Self == GhostButtonStyle {
    static var ghost: GhostButtonStyle { GhostButtonStyle() }
}

/// The card, with an edge you can see.
struct CardSurface: ViewModifier {
    var padding: CGFloat = MacTheme.Space.card
    var elevated = false
    func body(content: Content) -> some View {
        content
            .padding(padding)
            .background(
                RoundedRectangle(cornerRadius: MacTheme.Radius.card, style: .continuous)
                    .fill(elevated ? MacTheme.raised : MacTheme.card)
                    .overlay(
                        RoundedRectangle(cornerRadius: MacTheme.Radius.card, style: .continuous)
                            .strokeBorder(MacTheme.edge, lineWidth: 1)
                    )
            )
    }
}

extension View {
    func cardSurface(padding: CGFloat = MacTheme.Space.card, elevated: Bool = false) -> some View {
        modifier(CardSurface(padding: padding, elevated: elevated))
    }
}

/// The app's heartbeat: a dot that breathes while something is live and sits
/// still otherwise. Time-driven, so a parent layout can never inherit the
/// animation and carry the dot away from its label.
struct LiveDot: View {
    var active: Bool
    var size: CGFloat = 9
    var color: Color = MacTheme.alarm
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0, paused: !active || reduceMotion)) { tick in
            let t = tick.date.timeIntervalSinceReferenceDate
            let phase = (active && !reduceMotion) ? CGFloat((sin(t * 2 * .pi / 1.6) + 1) / 2) : 0
            Circle()
                .fill(color)
                .frame(width: size, height: size)
                .scaleEffect(1 + 0.18 * phase)
                .opacity(active ? 0.7 + 0.3 * phase : 0.45)
        }
        .frame(width: size * 1.3, height: size * 1.3)
        .accessibilityHidden(true)
    }
}

/// A small caps-style section label.
struct SectionLabel: View {
    let text: String
    var body: some View {
        Text(text.uppercased())
            .font(MacTheme.meta)
            .tracking(0.6)
            .foregroundStyle(MacTheme.muted)
    }
}
