import SwiftUI

struct SettingsConnectorsView: View {
    @ObservedObject var session: AnticipySession
    @EnvironmentObject private var pendant: PendantManager
    @Environment(\.dismiss) private var dismiss
    @State private var route: Route?

    private enum Route: Hashable {
        case calendar, contacts, mail, browser, mac, pendant
    }

    var body: some View {
        SheetChrome(title: "Connectors", leading: .back) {
            dismiss()
        } content: {
            SectionHeader("On this iPhone")
            GroupedCard {
                connectorRow(for: .calendar, route: .calendar)
                connectorRow(for: .contacts, route: .contacts)
                connectorRow(for: .mail, route: .mail)
            }

            SectionHeader("Other devices")
            GroupedCard {
                NavRow("Browser", systemImage: "safari",
                       value: browserState) {
                    Haptics.engage()
                    route = .browser
                }
                NavRow("Mac app", systemImage: "laptopcomputer") {
                    Haptics.engage()
                    route = .mac
                }
                NavRow("Pendant", systemImage: "wave.3.right",
                       value: pendant.hasPairedPendant ? pendant.state.plainWords : "Not paired") {
                    Haptics.engage()
                    route = .pendant
                }
            }

            FootnoteText("Open a connector to see what it can access, its current status, and how to disconnect it.")
        }
        .navigationDestination(isPresented: Binding(
            get: { route != nil },
            set: { if !$0 { route = nil } }
        )) {
            switch route {
            case .calendar:
                SettingsSourceView(session: session, source: .calendar)
            case .contacts:
                SettingsSourceView(session: session, source: .contacts)
            case .mail:
                SettingsSourceView(session: session, source: .mail)
            case .browser:
                SettingsBrowserConnectorView(session: session)
            case .mac:
                SettingsMacConnectorView()
            case .pendant:
                SettingsPendantConnectorView()
            case nil:
                EmptyView()
            }
        }
    }

    private func connectorRow(for source: ContextSource, route next: Route) -> NavRow {
        NavRow(source.label,
               systemImage: SettingsAccessView.glyph(for: source),
               value: SettingsAccessView.answer(for: source)) {
            Haptics.engage()
            route = next
        }
    }

    private var browserState: String {
        guard session.agentPaired else { return "Not connected" }
        return session.agentOnline ? "Ready" : "Offline"
    }
}

private struct SettingsBrowserConnectorView: View {
    @ObservedObject var session: AnticipySession
    @Environment(\.dismiss) private var dismiss
    @AppStorage("backendURL") private var backendURL = "https://api.anticipy.ai"
    @State private var pairCode = ""
    @State private var pairOutcome: AnticipySession.PairOutcome?
    @State private var pairing = false

    var body: some View {
        SheetChrome(title: "Browser", leading: .back) {
            dismiss()
        } content: {
            GroupedCard {
                StateRow("Status", systemImage: "safari", state: status)
                if let seconds = session.agentLastSeenSeconds {
                    StateRow("Last seen", state: "\(PlainDuration.words(seconds)) ago")
                }
            }

            if let stale = session.staleExtensionVersion {
                GroupedCard {
                    InfoRow("Update the browser extension. Installed version: \(stale).",
                            systemImage: "exclamationmark.triangle")
                }
            }

            if session.agentPaired {
                GroupedCard {
                    DestructiveRow("Disconnect this browser",
                                   systemImage: "laptopcomputer.slash") {
                        Haptics.engage()
                        Task {
                            await session.backend.unpairAgent(owner: session.ownerID)
                            await session.refresh()
                        }
                    }
                }
                FootnoteText("Disconnect before pairing Anticipy with a different browser.")
            } else {
                SectionHeader("Connect")
                GroupedCard {
                    ValueRow("Pairing code", text: $pairCode,
                             placeholder: "6 digits", keyboard: .numberPad)
                    ActionRow(pairing ? "Connecting…" : "Connect browser",
                              systemImage: "link",
                              isEnabled: pairCode.count == 6 && !pairing) {
                        pair()
                    }
                }

                if let message = outcomeMessage {
                    FootnoteText(message)
                } else {
                    FootnoteText("Enter the six-digit code shown by the Anticipy browser extension.")
                }

                if let setup = ComputerSetupLinks.browser(baseURL: backendURL) {
                    GroupedCard {
                        ActionRow("Open browser setup", systemImage: "arrow.up.right.square") {
                            UIApplication.shared.open(setup)
                        }
                        ShareLink(item: setup,
                                  subject: Text("Set up Anticipy in Chrome"),
                                  message: Text("Open this on your computer to connect Anticipy to Chrome.")) {
                            Label("Send setup to computer", systemImage: "square.and.arrow.up")
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .ghostRow()
                    }
                }
            }
        }
        .onChange(of: pairCode) { value in
            pairOutcome = nil
            let digits = String(value.filter(\.isNumber).prefix(6))
            if digits != value { pairCode = digits }
        }
    }

    private var status: String {
        guard session.agentPaired else { return "Not connected" }
        return session.agentOnline ? "Ready" : "Offline"
    }

    private var outcomeMessage: String? {
        switch pairOutcome {
        case .noMatch: return "That code did not match. Check the extension and try again."
        case .unreachable: return "Anticipy could not reach the service. Try again when you have a connection."
        case .paired: return "Browser connected."
        case nil: return nil
        }
    }

    private func pair() {
        guard pairCode.count == 6, !pairing else { return }
        pairing = true
        let code = pairCode
        Task {
            let result = await session.pairAgent(code: code)
            pairOutcome = result
            pairing = false
            if result == .paired { Haptics.pairing() }
        }
    }
}

private struct SettingsMacConnectorView: View {
    @Environment(\.dismiss) private var dismiss
    @AppStorage("backendURL") private var backendURL = "https://api.anticipy.ai"

    var body: some View {
        SheetChrome(title: "Mac app", leading: .back) {
            dismiss()
        } content: {
            GroupedCard {
                InfoRow("The Mac app can capture meetings and nearby speech when you turn its microphone on.",
                        systemImage: "laptopcomputer")
                InfoRow("It signs in with the same Anticipy account as this iPhone.",
                        systemImage: "person.crop.circle")
            }

            if let setup = ComputerSetupLinks.mac(baseURL: backendURL) {
                GroupedCard {
                    ActionRow("Open Mac setup",
                              systemImage: "arrow.up.right.square") {
                        UIApplication.shared.open(setup)
                    }
                    ShareLink(item: setup,
                              subject: Text("Get Anticipy for Mac"),
                              message: Text("Open this on your Mac to install Anticipy.")) {
                        Label("Send setup to Mac", systemImage: "square.and.arrow.up")
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .ghostRow()
                }
            }

            FootnoteText("The Mac microphone stays off until you start it from the menu bar.")
        }
    }
}

private struct SettingsPendantConnectorView: View {
    @EnvironmentObject private var pendant: PendantManager
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        SheetChrome(title: "Pendant", leading: .back) {
            dismiss()
        } content: {
            GroupedCard {
                StateRow("Status", state: pendant.hasPairedPendant
                         ? pendant.state.plainWords : "Not paired")
                if let name = pendant.deviceName {
                    StateRow("Device", state: name)
                }
                if let battery = pendant.battery {
                    StateRow("Battery", state: "\(battery)%")
                }
                if let signal = pendant.rssi {
                    StateRow("Signal", state: signal > -60 ? "Strong" : signal > -80 ? "OK" : "Weak")
                }
            }

            if pendant.hasPairedPendant {
                GroupedCard {
                    DestructiveRow("Forget this pendant", systemImage: "xmark.circle") {
                        Haptics.engage()
                        pendant.forgetPendant()
                    }
                }
            } else {
                GroupedCard {
                    ActionRow("Pair a pendant", systemImage: "wave.3.right") {
                        Haptics.engage()
                        pendant.startScan()
                    }
                }
            }

            FootnoteText("Pendant transcription is not available yet. Until it runs on this iPhone, the pendant does not record or send audio.")
        }
    }
}
