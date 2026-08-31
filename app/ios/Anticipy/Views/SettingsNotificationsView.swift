import SwiftUI

struct SettingsNotificationsView: View {
    @Environment(\.dismiss) private var dismiss
    @AppStorage(AppPreferences.notificationsKey) private var notifications = true
    @AppStorage(AppPreferences.notificationSoundKey) private var sound = true
    @AppStorage(AppPreferences.quietScheduleKey)
    private var quietSchedule = NotificationQuietSchedule.tenToEight.rawValue

    var body: some View {
        SheetChrome(title: "Notifications", leading: .back) {
            dismiss()
        } content: {
            GroupedCard {
                ToggleRow("Work that needs you",
                          subtitle: "Notify you when an approval or answer is required.",
                          isOn: $notifications)
                ToggleRow("Sound",
                          subtitle: "Play a sound with those notifications.",
                          isOn: $sound)
            }

            SectionHeader("Quiet hours")
            GroupedCard {
                ForEach(NotificationQuietSchedule.allCases, id: \.rawValue) { schedule in
                    SelectRow(schedule.title,
                              subtitle: schedule.subtitle,
                              isSelected: quietSchedule == schedule.rawValue) {
                        Haptics.engage()
                        quietSchedule = schedule.rawValue
                    }
                }
            }

            FootnoteText("Alerts held during quiet hours are delivered when the window ends.")
        }
    }
}
