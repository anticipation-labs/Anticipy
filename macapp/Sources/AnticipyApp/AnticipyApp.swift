import SwiftUI

@main
struct AnticipyApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate

    var body: some Scene {
        WindowGroup("Anticipy") {
            RootView()
                .frame(minWidth: 920, minHeight: 640)
        }
        .windowStyle(.hiddenTitleBar)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        // Behave like a normal foreground app even when launched from a bundle
        // assembled without Xcode.
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }
}

/// Scaffold shell: a slim rail to preview the three (inert) screens, in order.
struct RootView: View {
    enum Screen: String, CaseIterable, Identifiable {
        case onboarding = "Onboarding"
        case connect = "Connect"
        case main = "Main"
        var id: String { rawValue }
    }

    @State private var screen: Screen = .onboarding

    var body: some View {
        HStack(spacing: 0) {
            Rail(screen: $screen)
            Rectangle().fill(DS.hairline).frame(width: 1)
            Group {
                switch screen {
                case .onboarding: OnboardingView()
                case .connect: ConnectView()
                case .main: MainView()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(DS.bg)
        .preferredColorScheme(.dark)
    }
}

private struct Rail: View {
    @Binding var screen: RootView.Screen

    var body: some View {
        VStack(alignment: .leading, spacing: DS.s2) {
            HStack(spacing: DS.s1) {
                Circle().fill(DS.accent).frame(width: 8, height: 8)
                Text("Anticipy").font(DS.title()).foregroundColor(DS.textPrimary)
            }
            .padding(.bottom, DS.s2)

            ForEach(RootView.Screen.allCases) { s in
                Button { screen = s } label: {
                    Text(s.rawValue)
                        .font(DS.body(screen == s ? .medium : .regular))
                        .foregroundColor(screen == s ? DS.textPrimary : DS.textSecondary)
                        .padding(.vertical, 6)
                        .padding(.horizontal, DS.s1)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(
                            RoundedRectangle(cornerRadius: DS.controlRadius, style: .continuous)
                                .fill(screen == s ? DS.elevated : Color.clear)
                        )
                }
                .buttonStyle(.plain)
            }
            Spacer()
            Text("scaffold · inert")
                .font(DS.caption())
                .foregroundColor(DS.textSecondary.opacity(0.7))
        }
        .padding(DS.s2)
        .frame(width: 200)
        .background(DS.surface)
    }
}
