import SwiftUI

/// Which of the two palettes the app is in.
///
/// Two rules, and both are deliberate.
///
/// LIGHT IS THE DEFAULT. The app used to pin `.preferredColorScheme(.dark)` at
/// its root, so it was dark for everyone with no way out. It is now light for
/// everyone until somebody says otherwise.
///
/// THE SYSTEM SETTING IS NOT FOLLOWED. There is no `.unspecified`/nil case here
/// on purpose: `preferredColorScheme(nil)` hands the first impression of the
/// product to a switch in iOS Settings that the owner set for a different
/// reason, on a different day. The extension's two surfaces and the hosted web
/// pages take the same position, under the same key name, so the whole product
/// behaves one way. Do not "improve" this by adding a `system` case.
enum AppTheme: String, CaseIterable {
    case light
    case dark

    /// The @AppStorage key. Named here rather than typed as a literal at each
    /// use site, because a misspelled key is a silent revert to the default.
    static let key = "anticipy.theme"

    /// Anything that is not exactly "dark" is light, so a value from a future
    /// build — or a corrupted one — can only ever fail toward the default.
    init(rawValue: String) {
        self = rawValue == AppTheme.dark.rawValue ? .dark : .light
    }

    var colorScheme: ColorScheme {
        switch self {
        case .light: return .light
        case .dark: return .dark
        }
    }

    /// What the row says it will DO, which is the only thing anyone wants from
    /// a control they will touch once.
    var actionLabel: String {
        switch self {
        case .light: return "Switch to dark"
        case .dark: return "Switch to light"
        }
    }

    var icon: String {
        switch self {
        case .light: return "moon.fill"
        case .dark: return "sun.max.fill"
        }
    }

    var other: AppTheme {
        self == .dark ? .light : .dark
    }
}
