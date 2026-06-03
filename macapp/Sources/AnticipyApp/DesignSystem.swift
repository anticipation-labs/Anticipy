import SwiftUI

/// The Anticipy design system (Apple HIG: clarity, deference, depth).
/// Dark-first, one accent, 8pt grid, SF Pro. Palette derived from brushed
/// titanium + "vibe your life" (champagne accent). Swap hex for the real brand
/// values when provided.
enum DS {
    // Palette — dark
    static let bg = Color(0x0E0F11)
    static let surface = Color(0x17191C)
    static let elevated = Color(0x1F2226)
    static let textPrimary = Color(0xF2F1ED)
    static let textSecondary = Color(0xA9ABB0)
    static let hairline = Color(0x2A2D31)
    static let titanium = Color(0xB8BCC2)
    static let accent = Color(0xC8A96A) // champagne, premium-warm

    // Type scale (regular/medium only, generous line-height via spacing)
    static func display(_ w: Font.Weight = .regular) -> Font { .system(size: 28, weight: w) }
    static func title(_ w: Font.Weight = .medium) -> Font { .system(size: 20, weight: w) }
    static func body(_ w: Font.Weight = .regular) -> Font { .system(size: 15, weight: w) }
    static func secondary(_ w: Font.Weight = .regular) -> Font { .system(size: 13, weight: w) }
    static func caption(_ w: Font.Weight = .regular) -> Font { .system(size: 11, weight: w) }

    // Spacing (8pt grid) & radius
    static let s1: CGFloat = 8
    static let s2: CGFloat = 16
    static let s3: CGFloat = 24
    static let s4: CGFloat = 32
    static let cardRadius: CGFloat = 12
    static let controlRadius: CGFloat = 8
}

extension Color {
    /// 0xRRGGBB initializer.
    init(_ hex: UInt, alpha: Double = 1) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255.0,
            green: Double((hex >> 8) & 0xFF) / 255.0,
            blue: Double(hex & 0xFF) / 255.0,
            opacity: alpha
        )
    }
}

/// A calm, hairline-bordered card surface.
struct Card<Content: View>: View {
    var elevated = false
    @ViewBuilder var content: Content
    var body: some View {
        content
            .background(elevated ? DS.elevated : DS.surface)
            .clipShape(RoundedRectangle(cornerRadius: DS.cardRadius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: DS.cardRadius, style: .continuous)
                    .stroke(DS.hairline, lineWidth: 1)
            )
    }
}

/// The single primary action style (one accent, restraint).
struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(DS.body(.medium))
            .foregroundColor(DS.bg)
            .padding(.horizontal, DS.s3)
            .padding(.vertical, DS.s1 + 4)
            .background(DS.accent.opacity(configuration.isPressed ? 0.85 : 1))
            .clipShape(RoundedRectangle(cornerRadius: DS.controlRadius, style: .continuous))
            .animation(.easeInOut(duration: 0.2), value: configuration.isPressed)
    }
}
