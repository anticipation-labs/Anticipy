import SwiftUI

/// The settings index. Every row opens one focused page, so a chevron always
/// means navigation and no preference changes accidentally on the index.
struct SettingsHomeView: View {
    @EnvironmentObject var session: AnticipySession
    @Environment(\.dismiss) private var dismiss

    @State private var route: Route?

    private enum Route: Hashable {
        case profile, listening, notifications, connectors, appearance, advanced, about
    }

    var body: some View {
        SheetChrome(
            title: "Settings",
            leading: .back,
            onLeading: { dismiss() }
        ) {
            GroupedCard {
                InfoRow(session.ownerEmail.isEmpty
                        ? "Signed in on this phone" : session.ownerEmail)
            }

            SectionHeader("Account")
            GroupedCard {
                NavRow("Profile", systemImage: "person.crop.circle",
                       value: session.ownerFirstName.isEmpty
                           ? nil : session.ownerFirstName) {
                    Haptics.engage(); route = .profile
                }
            }

            SectionHeader("Anticipy")
            GroupedCard {
                NavRow("Listening", systemImage: "waveform",
                       value: session.listener.isListening ? "On" : "Off") {
                    Haptics.engage(); route = .listening
                }
                NavRow("Notifications", systemImage: "bell") {
                    Haptics.engage(); route = .notifications
                }
            }

            SectionHeader("Connections")
            GroupedCard {
                NavRow("Connectors", systemImage: "link") {
                    Haptics.engage(); route = .connectors
                }
            }

            SectionHeader("Preferences")
            GroupedCard {
                NavRow("Appearance", systemImage: "circle.lefthalf.filled") {
                    Haptics.engage(); route = .appearance
                }
                NavRow("Advanced", systemImage: "slider.horizontal.3") {
                    Haptics.engage(); route = .advanced
                }
            }

            SectionHeader("About")
            GroupedCard {
                NavRow("About Anticipy", systemImage: "info.circle") {
                    Haptics.engage(); route = .about
                }
            }
        }
        .navigationDestination(isPresented: Binding(
            get: { route != nil },
            set: { if !$0 { route = nil } }
        )) {
            switch route {
            case .profile:   SettingsProfileView(session: session)
            case .listening: SettingsListeningView(session: session)
            case .notifications: SettingsNotificationsView()
            case .connectors: SettingsConnectorsView(session: session)
            case .appearance: SettingsAppearanceView()
            case .advanced: SettingsAdvancedView()
            case .about: SettingsAboutView()
            case nil:        EmptyView()
            }
        }
    }
}

/// Screen 5: the info popover, as a sheet.
///
/// A popover anchored to the header button is what the source does; on a phone
/// UIKit renders that as a sheet anyway, so this is the same thing without
/// pretending the anchor matters.
///
/// The build number is printed beside the version ON PURPOSE. This repo has
/// spent whole days on the question "which build is that phone actually
/// running" — `device_id` IS the build number in the ears pipeline, and builds
/// 76 to 80 delivered zero rows while looking healthy. A version string without
/// the build is the half that cannot answer it.
private struct SettingsAboutView: View {
    @Environment(\.dismiss) private var dismiss

    private var version: String {
        let v = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
        let b = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "?"
        return "Anticipy \(v) (\(b))"
    }

    var body: some View {
        SheetChrome(title: "About", leading: .back) {
            dismiss()
        } content: {
            GroupedCard {
                InfoRow(version)
            }

            GroupedCard {
                if let url = URL(string: "https://anticipy.ai/privacy") {
                    NavRow("Privacy policy", systemImage: "arrow.up.right.square") {
                        UIApplication.shared.open(url)
                    }
                }
                if let url = URL(string: "https://anticipy.ai/terms") {
                    NavRow("Terms of service", systemImage: "arrow.up.right.square") {
                        UIApplication.shared.open(url)
                    }
                }
            }

            FootnoteText("Microphone audio stays on this iPhone. Anticipy sends the resulting text to its server so it can create and complete work.")
        }
    }
}
