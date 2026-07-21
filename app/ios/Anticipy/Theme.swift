import SwiftUI

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

    static func display(_ size: CGFloat) -> Font {
        .system(size: size, weight: .regular, design: .serif)
    }
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

struct CardBackground: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(16)
            .background(
                RoundedRectangle(cornerRadius: 18)
                    .fill(Theme.card)
                    .overlay(RoundedRectangle(cornerRadius: 18).strokeBorder(Theme.stroke))
            )
    }
}

extension View {
    func anticipyCard() -> some View { modifier(CardBackground()) }
}
