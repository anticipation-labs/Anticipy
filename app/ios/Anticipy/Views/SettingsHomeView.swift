import SwiftUI

/// Settings, as the seven supplied screens have it: an identity pill, sections
/// of navigation rows outside their cards, an appearance picker that SHOWS the
/// choice rather than naming it, and an info button carrying the version and
/// the legal pages.
///
/// WHY A NEW FILE RATHER THAN A REWRITE IN PLACE. `SettingsView` is 1427 lines
/// and holds five areas nobody has migrated yet — the pendant, the voiceprint,
/// the browser, the SMS thread and the haptics panel. Rewriting all of it in
/// one pass is how a redesign quietly drops a control, and four UX audit fixes
/// shipped inside that file this week. So the migrated areas move to their own
/// screens, this becomes the root, and the un-migrated ones are reached through
/// one honest row until they get the same treatment. Nothing is deleted, and
/// nothing is half-moved.
struct SettingsHomeView: View {
    @EnvironmentObject var session: AnticipySession
    @AppStorage(AppTheme.key) private var themeChoice = AppTheme.light.rawValue
    @Environment(\.dismiss) private var dismiss

    @State private var route: Route?
    @State private var showInfo = false

    private enum Route: Hashable { case profile, access, listening, rest }

    var body: some View {
        SheetChrome(
            title: "Settings",
            leading: .back,
            onLeading: { dismiss() },
            trailing: SheetAction(systemImage: "info.circle",
                                  label: "About Anticipy") { showInfo = true }
        ) {
            // The identity pill. It is the one thing on this screen that is not
            // a control: it answers "whose settings are these", which on a
            // handset that has been passed along is the first question and used
            // to be unanswerable here.
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

            SectionHeader("App")
            GroupedCard {
                NavRow("Listening", systemImage: "waveform",
                       value: session.listener.isListening ? "On" : "Off") {
                    Haptics.engage(); route = .listening
                }
                NavRow("What I can see", systemImage: "eye") {
                    Haptics.engage(); route = .access
                }
                // NO "Haptic feedback" TOGGLE, though the design has one.
                // `HapticEngine` publishes `engineRunning`, `lastError` and
                // `lastStoppedReason` — it is a diagnostics panel, not a
                // preference, and there is no stored setting behind it. A
                // switch here would either do nothing or invent a feature under
                // cover of a restyle, and the second is worse than the first.
            }

            SectionHeader("Appearance")
            // TWO CARDS, NOT THREE, and that is deliberate rather than
            // unfinished. The design this copies offers Light / Dark / System.
            // `AppTheme` has exactly two cases and its `init(rawValue:)`
            // carries a written argument that anything which is not "dark"
            // fails toward light — a default that cannot be corrupted into a
            // third state. Adding "System" is a product decision that would
            // hand the app's first impression to a setting nobody chose for it,
            // and the sibling `theme.js` says so in as many words. It is one
            // case and one row away if the owner wants it; it is not something
            // to smuggle in under a restyle.
            GroupedCard {
                SelectRow("Light",
                          subtitle: "The way she looks by default.",
                          isSelected: AppTheme(rawValue: themeChoice) == .light) {
                    Haptics.engage(); themeChoice = AppTheme.light.rawValue
                }
                SelectRow("Dark",
                          subtitle: "Remembered, once you pick it.",
                          isSelected: AppTheme(rawValue: themeChoice) == .dark) {
                    Haptics.engage(); themeChoice = AppTheme.dark.rawValue
                }
            }

            SectionHeader("Everything else")
            GroupedCard {
                NavRow("Pendant, voice, browser and the rest",
                       systemImage: "ellipsis.circle") {
                    Haptics.engage(); route = .rest
                }
            }
            FootnoteText("These haven't moved to the new layout yet. Every "
                         + "control still works exactly as it did.")
        }
        .navigationDestination(isPresented: Binding(
            get: { route != nil },
            set: { if !$0 { route = nil } }
        )) {
            switch route {
            case .profile:   SettingsProfileView(session: session)
            case .access:    SettingsAccessView(session: session)
            case .listening: SettingsListeningView(session: session)
            case .rest:      SettingsView()
            case nil:        EmptyView()
            }
        }
        .sheet(isPresented: $showInfo) { AboutSheet() }
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
private struct AboutSheet: View {
    @Environment(\.dismiss) private var dismiss

    private var version: String {
        let v = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
        let b = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "?"
        return "Anticipy \(v) (\(b))"
    }

    var body: some View {
        SheetChrome(title: "About", leading: .close) {
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

            FootnoteText("She listens on this phone and keeps the audio on it. "
                         + "Only what she has understood ever leaves.")
        }
    }
}
