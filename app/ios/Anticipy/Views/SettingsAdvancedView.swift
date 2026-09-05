import SwiftUI

struct SettingsAdvancedView: View {
    @EnvironmentObject private var session: AnticipySession
    @Environment(\.dismiss) private var dismiss
    @AppStorage(AppPreferences.hapticsKey) private var haptics = true
    @AppStorage(AppPreferences.ambientMotionKey) private var ambientMotion = true
    @AppStorage(AppPreferences.typedResponsesKey) private var typedResponses = true
    @AppStorage(ListenEnginePolicy.legacyFlagKey) private var compatibilityRecognizer = false
    @AppStorage(AppPreferences.developerModeKey) private var developerMode = false
    #if DEBUG
    @AppStorage("backendURL") private var backendURL = "https://api.anticipy.ai"
    #endif
    @State private var showListeningActivity = false
    @State private var showDeveloperDiagnostics = false

    var body: some View {
        SheetChrome(title: "Advanced", leading: .back) {
            dismiss()
        } content: {
            SectionHeader("Feedback")
            GroupedCard {
                ToggleRow("Haptic feedback",
                          subtitle: "Use short taps to confirm controls and completed actions.",
                          isOn: $haptics)
                ToggleRow("Ambient motion",
                          subtitle: "Animate listening indicators and progress effects.",
                          isOn: $ambientMotion)
                ToggleRow("Typed responses",
                          subtitle: "Reveal longer Anticipy responses a few words at a time.",
                          isOn: $typedResponses)
            }

            SectionHeader("Listening")
            GroupedCard {
                ToggleRow("Compatibility speech engine",
                          subtitle: "Use the older recognizer if current transcription is unreliable on this iPhone.",
                          isOn: $compatibilityRecognizer)
                DisclosureRow("Listening activity",
                              subtitle: "Review starts, stops, silent periods, and battery readings.",
                              systemImage: "list.bullet.rectangle") {
                    Haptics.engage()
                    showListeningActivity = true
                }
            }

            #if DEBUG
            SectionHeader("Development")
            GroupedCard {
                ValueRow("Backend", text: $backendURL,
                         placeholder: "https://backend.example.com")
            }
            #endif

            if developerMode {
                SectionHeader("Developer mode")
                GroupedCard {
                    DisclosureRow("Developer diagnostics",
                                  subtitle: "Inspect this build, its server, browser hand, queue, and loaded jobs.",
                                  systemImage: "wrench.and.screwdriver") {
                        Haptics.engage()
                        showDeveloperDiagnostics = true
                    }
                }
            }

            FootnoteText("These controls change live app behaviour and are saved on this iPhone.")
        }
        .navigationDestination(isPresented: $showListeningActivity) {
            ListeningDiagnosticsView()
        }
        .navigationDestination(isPresented: $showDeveloperDiagnostics) {
            DeveloperDiagnosticsView(session: session)
        }
    }
}
