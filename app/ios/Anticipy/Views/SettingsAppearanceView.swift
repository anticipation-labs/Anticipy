import SwiftUI

struct SettingsAppearanceView: View {
    @Environment(\.dismiss) private var dismiss
    @AppStorage(AppTheme.key) private var themeChoice = AppTheme.light.rawValue

    var body: some View {
        SheetChrome(title: "Appearance", leading: .back) {
            dismiss()
        } content: {
            GroupedCard {
                SelectRow("Light",
                          subtitle: "A white background with dark text.",
                          isSelected: AppTheme(rawValue: themeChoice) == .light) {
                    Haptics.engage()
                    themeChoice = AppTheme.light.rawValue
                }
                SelectRow("Dark",
                          subtitle: "A black background with light text.",
                          isSelected: AppTheme(rawValue: themeChoice) == .dark) {
                    Haptics.engage()
                    themeChoice = AppTheme.dark.rawValue
                }
            }

            FootnoteText("This choice applies to Anticipy on this iPhone.")
        }
    }
}
