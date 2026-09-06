import SwiftUI
import LocalAuthentication
import Speech

/// The settings index. Every row opens one focused page, so a chevron always
/// means navigation and no preference changes accidentally on the index.
struct SettingsHomeView: View {
    @EnvironmentObject var session: AnticipySession
    /// THE ONE CONNECT IN FLIGHT, held at the app root because the callback
    /// comes back through `onOpenURL`, which only the App has. This screen is
    /// where a connect STARTS; it reaches the same object rather than making a
    /// second one, or an attempt begun here would be finished by nobody.
    @EnvironmentObject var connect: ConnectSession
    @Environment(\.dismiss) private var dismiss

    @State private var route: Route?
    /// The app being connected right now, and how far it has got. Nil is the
    /// normal state; the sheet is drawn from it.
    @State private var connecting: ConnectFlow?
    /// Bumped ONLY when a connect actually finished. See `connectedApps`.
    @State private var connectedCount = 0
    @AppStorage(AppTheme.key) private var themeChoice = AppTheme.light.rawValue

    /// CONNECTORS AND CONNECTED APPS ARE TWO ROWS AND MUST STAY TWO ROWS.
    ///
    /// `connectors` is about THIS iPhone and the machines around it — the
    /// calendar, contacts and mail on the handset, the browser, the Mac, the
    /// pendant. `connectedApps` is about the owner's own accounts ELSEWHERE,
    /// connected through the catalog and revocable one at a time. Folding them
    /// into one row would put "turn on calendar access on this phone" beside
    /// "let Anticipy make changes in an account of yours", which are not the
    /// same promise, do not fail the same way, and are not undone the same way.
    private enum Route: Hashable {
        case profile, listening, notifications, connectors, connectedApps
        case personalization
        case privacyData, advanced, about
    }

    /// The root now carries the appearance choice inline — the design puts it on
    /// the settings root, not behind a row. It writes the same @AppStorage key
    /// the Appearance sub-screen used, so the whole app repaints through the
    /// dynamic `themed(...)` tokens with no observation graph. There is no
    /// "System" case, on purpose — see AppTheme.swift.
    private var appearanceBinding: Binding<AppTheme> {
        Binding(
            get: { AppTheme(rawValue: themeChoice) },
            set: { newValue in
                Haptics.engage()
                themeChoice = newValue.rawValue
            }
        )
    }

    var body: some View {
        SheetChrome(
            title: "Settings",
            leading: .back,
            onLeading: { dismiss() },
            trailing: SheetAction(systemImage: "info", label: "About") {
                Haptics.engage(); route = .about
            }
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
                NavRow("Notifications", systemImage: "bell") {
                    Haptics.engage(); route = .notifications
                }
                NavRow("Privacy & Data", systemImage: "hand.raised") {
                    Haptics.engage(); route = .privacyData
                }
                NavRow("Personalization", systemImage: "person.text.rectangle") {
                    Haptics.engage(); route = .personalization
                }
            }

            SectionHeader("App")
            GroupedCard {
                NavRow("Listening", systemImage: "waveform",
                       value: session.listener.isListening ? "On" : "Off") {
                    Haptics.engage(); route = .listening
                }
                NavRow("Connectors", systemImage: "link") {
                    Haptics.engage(); route = .connectors
                }
                // The screen's own title, read from the one place it is
                // written, so the row and the page it opens cannot come to
                // disagree about what this is called.
                NavRow(ConnectedAppsModel.Copy.title, systemImage: "square.on.square") {
                    Haptics.engage(); route = .connectedApps
                }
                NavRow("Advanced", systemImage: "slider.horizontal.3") {
                    Haptics.engage(); route = .advanced
                }
            }

            SectionHeader("Appearance")
            SelectGroup(
                [AppTheme.light, AppTheme.dark],
                selection: appearanceBinding,
                title: { $0 == .light ? "Light" : "Dark" },
                subtitle: {
                    $0 == .light
                        ? "A white background with dark text."
                        : "A black background with light text."
                }
            )
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
            case .connectedApps: connectedApps
            case .personalization: SettingsPersonalizationView(session: session)
            case .privacyData: SettingsPrivacyDataView(session: session)
            case .advanced: SettingsAdvancedView()
            case .about: SettingsAboutView()
            case nil:        EmptyView()
            }
        }
    }

    /// SETTINGS → CONNECTED APPS, and the reason this destination is spelled
    /// out rather than written inline like its neighbours.
    ///
    /// The screen takes two things the rest of this index does not have to
    /// think about, and both are constructed here:
    ///
    ///   THE STORE. `ConnectedAppsClient`, the real one, reading this owner's
    ///   connections off the server with the session this app already holds.
    ///   It replaced `UnreachableConnectedAppsStore`, whose every method threw.
    ///   That type stays where it is: the model's suite drives it to pin the
    ///   `.trouble` side of "empty is not broken" — a store that answered `[]`
    ///   would render "Nothing is connected yet" to somebody with two apps
    ///   connected — and nothing in the shipping app is built with it.
    ///
    ///   STARTING A CONNECTION. `startConnect` used to be an
    ///   `assertionFailure`: the button that begins the only flow in the
    ///   product where somebody hands over a key did nothing at all. It now
    ///   runs the whole handoff — sentences, the sheet, our single-use link,
    ///   the tap, the browser — through `ConnectSession`, which is the only
    ///   object in the app allowed to open one.
    ///
    /// `.id(connectedCount)` IS THE REFRESH, and it is blunt on purpose.
    /// `ConnectDone.connected` is a HINT, not a record: the truth is whatever
    /// the server says this owner has, and `SettingsConnectedAppsView` reads
    /// that once, into a model it keeps for its own lifetime, with no handle
    /// anything out here can pull. Changing this identity rebuilds that screen
    /// against a fresh model, which re-reads the list — so an app connected a
    /// moment ago is on it. It changes ONLY on a connect that actually
    /// finished, so nothing else on this index can make the list flicker.
    @ViewBuilder
    private var connectedApps: some View {
        SettingsConnectedAppsView(
            session: session,
            store: connectedAppsClient(),
            startConnect: startConnect)
            .id(connectedCount)
            .sheet(item: $connecting) { flow in
                connectSheet(flow)
            }
            // The hint, turned into the one thing it licenses: go and ask.
            .onChange(of: connect.outcome) { outcome in
                guard case .connected = outcome else { return }
                connectedCount += 1
                connect.clearOutcome()
            }
            // A sheet whose attempt has gone — abandoned, expired, or taken
            // away by a sign-out — is a sheet with a dead button on it.
            .onChange(of: connect.prompt == nil) { gone in
                if gone, connecting?.stage == .asking { connecting = nil }
            }
    }

    /// THE STORE, BUILT PER ACCESS AND CREDENTIALED PER CALL.
    ///
    /// `session.backend` is this app's one place for "which server, whose
    /// session" — the same computed property every other screen reaches for —
    /// and the closure below reads it AT THE MOMENT OF EACH REQUEST rather than
    /// closing over a token. `SettingsConnectedAppsView` builds its model once
    /// and keeps it across a sign-out and a second person signing in on the
    /// same phone; a client holding one account's token would go on answering
    /// under the next person's name.
    ///
    /// `session.accountID` is the owner ROW id, and `ConnectedAppsCredential`
    /// refuses anything else — `session.ownerID` is this app's pre-accounts
    /// device UUID, and a connection bound to that is bound to a handset.
    private func connectedAppsClient() -> ConnectedAppsClient {
        ConnectedAppsClient(credential: { [session] in
            let backend = session.backend
            return ConnectedAppsCredential(baseURL: backend.baseURL,
                                           accountID: backend.accountID,
                                           authToken: backend.authToken)
        })
    }

    /// THE TAP ON A CATALOG RESULT — the beginning of the only flow in this
    /// product where somebody hands over a key to something of theirs.
    ///
    /// The order is the spec's and is not this file's to rearrange: the
    /// disclosure goes up FIRST, with the app's own sentences on it, and the
    /// link is fetched behind it. `ConnectSession` refuses a sheet with nothing
    /// on it, refuses a tap that arrives before the link, and spends the
    /// acknowledgement as the browser opens.
    private func startConnect(_ app: ToolkitMeta) {
        guard let owner = OwnerId(session.accountID) else { return }
        connecting = ConnectFlow(app: app, stage: .settingUp)
        Task { await runConnect(app, owner: owner) }
    }

    /// The two server calls the handoff needs, in the order it needs them.
    ///
    /// Every step re-checks that the sheet on screen is still THIS app's: a
    /// second tap on a second app starts a second flow, and an answer for the
    /// first one landing afterwards must not be adopted under it. A failure at
    /// any point says so plainly and nothing is opened.
    private func runConnect(_ app: ToolkitMeta, owner: OwnerId) async {
        let client = connectedAppsClient()
        do {
            let sentences = try await client.permissionSentences(toolkit: app.slug,
                                                                 owner: owner)
            guard connecting?.app.slug == app.slug else { return }
            guard let prompt = connect.begin(owner: owner.raw, toolkit: app.slug,
                                             sentences: sentences) else {
                connecting?.stage = .trouble
                return
            }
            connecting?.stage = .asking
            let link = try await client.connectLink(toolkit: app.slug, owner: owner,
                                                    attemptID: prompt.attemptID)
            guard connecting?.app.slug == app.slug else { return }
            // A link the handoff will not adopt is a link nothing may open. The
            // attempt goes with it: an attempt left in flight is an attempt
            // whose callback would be believed later.
            guard connect.adopt(link: link) else {
                connect.ownerChanged()
                connecting?.stage = .trouble
                return
            }
        } catch {
            guard connecting?.app.slug == app.slug else { return }
            connect.ownerChanged()
            connecting?.stage = .trouble
        }
    }

    /// THE DISCLOSURE SHEET. Google's Workspace policy asks for the owner to be
    /// told what will be read, in context, with a real affirmative action,
    /// immediately before the sign-in flow — and `DisclosureGate` enforces all
    /// three, including a floor under the word "tap".
    ///
    /// NO APP IS NAMED HERE AND ALMOST NOTHING IS WRITTEN HERE. The heading and
    /// the button are `ConnectedAppsModel.Copy.connectAction(app:)`, the claims
    /// are the catalog's own sentences (through the register gate on the way
    /// in), and the line saying this is optional is
    /// `ConnectedAppsModel.Copy.optional`. The only two sentences this flow adds
    /// live in `ConnectStartCopy`, where the suite reads them.
    @ViewBuilder
    private func connectSheet(_ flow: ConnectFlow) -> some View {
        let name = ConnectionsPolicy.appName(flow.app, fallback: flow.app.slug)
        SheetChrome(title: ConnectedAppsModel.Copy.connectAction(app: name),
                    leading: .close,
                    onLeading: { connecting = nil }) {
            switch flow.stage {
            case .settingUp:
                GroupedCard { InfoRow(ConnectStartCopy.settingUp, systemImage: "clock") }
            case .trouble:
                GroupedCard {
                    InfoRow(ConnectStartCopy.couldNotStart,
                            systemImage: "exclamationmark.circle")
                }
            case .asking:
                if let prompt = connect.prompt {
                    GroupedCard {
                        for sentence in prompt.sentences {
                            InfoRow(sentence, systemImage: "checkmark.circle")
                        }
                    }
                    GroupedCard {
                        ActionRow(ConnectedAppsModel.Copy.connectAction(app: name),
                                  systemImage: "arrow.up.right.square",
                                  isEnabled: prompt.linkReady) {
                            tapped(prompt)
                        }
                    }
                    FootnoteText(ConnectedAppsModel.Copy.optional)
                } else {
                    GroupedCard {
                        InfoRow(ConnectStartCopy.couldNotStart,
                                systemImage: "exclamationmark.circle")
                    }
                }
            }
        }
    }

    /// The affirmative control, and the ONLY place this screen hands a consent
    /// back. `signedInOwner` is read again here rather than trusted from the
    /// tap that started this: a sign-out can happen in between, and an attempt
    /// that outlived one is dead.
    ///
    /// A refusal leaves the sheet standing — `ConnectSession` puts the same
    /// sentences back with a fresh consent — because the usual cause is a tap
    /// that arrived a moment early, and closing the sheet would cost the owner
    /// their place.
    private func tapped(_ prompt: DisclosurePrompt) {
        Haptics.engage()
        switch connect.ownerTapped(prompt.consent, signedInOwner: session.accountID) {
        case .openedInSignInSession, .openedInSystemBrowser:
            connecting = nil
        case .refused:
            break
        }
    }
}

/// ONE CONNECT, AS THIS SCREEN DRAWS IT.
///
/// The app is carried rather than looked up so the sheet can name and picture
/// it in every state, including the two where `ConnectSession` holds nothing
/// yet. `Identifiable` by slug: a second connect on a second app is a second
/// sheet, and starting one while another is up replaces it.
struct ConnectFlow: Equatable, Identifiable {
    enum Stage: Equatable {
        /// The sentences and the link are being fetched. Nothing has been asked
        /// of the owner and nothing has been minted for them.
        case settingUp
        /// The disclosure is on screen. `ConnectSession` holds the prompt.
        case asking
        /// It could not be started. Nothing was opened and nothing changed.
        case trouble
    }

    let app: ToolkitMeta
    var stage: Stage

    var id: String { app.slug }
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
    @AppStorage(AppPreferences.developerModeKey) private var developerMode = false
    @State private var buildTaps = 0
    @State private var tapGeneration = 0
    @State private var authenticating = false
    @State private var authenticationContext: LAContext?
    @State private var unlockError: String?

    private var version: String {
        let v = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
        let b = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "?"
        return "Anticipy \(v) (\(b))"
    }

    /// Mirrors the recognizer decision used by PhoneListener. Some older
    /// devices cannot perform speech recognition locally; on those devices iOS
    /// may send microphone audio to Apple's speech service, so About must say
    /// that plainly instead of making an unconditional local-audio promise.
    private var speechPrivacyPath: String {
        let onDevice = SFSpeechRecognizer(locale: Locale(identifier: "en_US"))?
            .supportsOnDeviceRecognition ?? false
        return onDevice
            ? "Microphone audio is turned into text on this iPhone, then the text is sent to Anticipy's server so it can create and complete work."
            : "This iPhone may use Apple's speech service to turn microphone audio into text. Anticipy then sends the text—not an audio recording—to its server so it can create and complete work."
    }

    var body: some View {
        SheetChrome(title: "About", leading: .back) {
            dismiss()
        } content: {
            GroupedCard {
                InfoRow(version)
                    .contentShape(Rectangle())
                    .onTapGesture(perform: registerBuildTap)
            }

            if developerMode {
                FootnoteText("Developer mode is on. Its diagnostics are under Advanced.")
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

            FootnoteText(speechPrivacyPath)
        }
        .alert("Developer mode stayed locked", isPresented: Binding(
            get: { unlockError != nil },
            set: { if !$0 { unlockError = nil } }
        )) {
            Button("OK", role: .cancel) { unlockError = nil }
        } message: {
            Text(unlockError ?? "This iPhone could not verify its owner.")
        }
    }

    /// Seven deliberate taps make the control discoverable to a developer who
    /// knows it is there without turning About into another settings page.
    /// Authentication is the actual gate; the taps merely ask to approach it.
    private func registerBuildTap() {
        guard !developerMode, !authenticating else { return }
        buildTaps += 1
        tapGeneration += 1
        let generation = tapGeneration

        if buildTaps >= 7 {
            buildTaps = 0
            authenticateOwner()
            return
        }

        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            guard generation == tapGeneration else { return }
            buildTaps = 0
        }
    }

    /// Device-owner authentication can use Face ID, Touch ID, or the iPhone's
    /// passcode. It protects a local diagnostics surface; it is not a passkey
    /// and it grants no additional backend permission.
    private func authenticateOwner() {
        let context = LAContext()
        var error: NSError?
        guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &error) else {
            unlockError = "Set a passcode, Face ID, or Touch ID on this iPhone before unlocking diagnostics."
            return
        }

        authenticating = true
        authenticationContext = context
        context.evaluatePolicy(
            .deviceOwnerAuthentication,
            localizedReason: "Unlock Anticipy developer diagnostics"
        ) { success, evaluationError in
            DispatchQueue.main.async {
                authenticating = false
                authenticationContext = nil
                if success {
                    developerMode = true
                    Haptics.success()
                    return
                }
                if let laError = evaluationError as? LAError,
                   laError.code == .userCancel || laError.code == .appCancel {
                    return
                }
                unlockError = "This iPhone could not verify its owner. Nothing changed."
            }
        }
    }
}

#if DEBUG
/// Previews the redesigned settings index with a bare session — no account,
/// no server, no listener running. `PreviewProvider` rather than the `#Preview`
/// macro because the deployment floor is iOS 16 (same reason SupervisedReadView
/// uses it). Populated with sample identity so the pill and Profile row read
/// like a real account; it reaches no network.
struct SettingsHomeView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack { SettingsHomeView() }
            .environmentObject(sampleSession())
            .environmentObject(ConnectSession())
            .previewDisplayName("Settings — light")

        NavigationStack { SettingsHomeView() }
            .environmentObject(sampleSession())
            .environmentObject(ConnectSession())
            // `.environment(\.colorScheme, .dark)`, not `.preferredColorScheme`.
            // The theme gate allows exactly ONE preferredColorScheme pin in the
            // app — the real one in AnticipyApp.swift, which reads the owner's
            // stored choice. A second pin anywhere means two things claim to
            // decide the theme, and the gate cannot tell a preview from the app.
            // This previews dark without adding a pin.
            .environment(\.colorScheme, .dark)
            .previewDisplayName("Settings — dark")
    }

    /// `AnticipySession` is `@MainActor`, like every observable in this app,
    /// and `PreviewProvider` is itself `@MainActor` — so this helper can build
    /// and populate it here.
    @MainActor
    private static func sampleSession() -> AnticipySession {
        let s = AnticipySession()
        s.ownerEmail = "you@anticipy.ai"
        s.ownerFirstName = "Omar"
        return s
    }
}
#endif
