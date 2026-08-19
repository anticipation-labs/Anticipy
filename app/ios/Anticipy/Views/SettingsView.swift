import SwiftUI
import Speech

struct SettingsView: View {
    @EnvironmentObject var pendant: PendantManager
    @EnvironmentObject var session: AnticipySession
    #if DEBUG
    // Observed, so the readout below refreshes the moment the engine starts,
    // stops, or reports why — otherwise it goes stale exactly while he is
    // standing on this screen testing it.
    @ObservedObject private var haptics = HapticEngine.shared
    #endif
    @AppStorage("backendURL") private var backendURL = "https://backend-production-61e0a.up.railway.app"
    @AppStorage("hasOnboarded") private var hasOnboarded = true
    /// When a timed pause is due to end, as seconds since the reference date;
    /// 0 means "not paused". On disk rather than in @State so the deadline
    /// survives walking away from this screen — the promise on the label has
    /// to outlive the view that made it.
    @AppStorage("listeningPauseUntil") private var pauseUntil: Double = 0

    @State private var pairCode = ""
    @State private var pairOutcome: AnticipySession.PairOutcome?
    @State private var pairing = false
    @State private var phoneField = ""
    @State private var phoneSaved = false
    @State private var firstName = ""
    @State private var lastName = ""
    @State private var email = ""
    @State private var birthday = ""
    @State private var detailsSaved = false
    @State private var showVoiceEnroll = false
    /// The live timer behind a timed pause. Held here so a second visit to
    /// this screen can re-arm it rather than leaving a promise unattended.
    @State private var resumeTask: Task<Void, Never>?
    @State private var confirmForget = false
    @State private var confirmReplay = false
    @State private var forgotten = false

    var body: some View {
        Form {
            // Listening is a standing state that survives relaunches, so the
            // one screen people open when they want it to STOP has to be able
            // to stop it. It sits first because that is the reason they came.
            Section("Listening") {
                Text(listeningState)
                    .font(.callout)
                    .foregroundStyle(Theme.ivory)

                if session.micBlocked {
                    Text("iPhone has microphone access switched off for me. It won't ask again — only you can turn it back on.")
                        .font(.caption)
                        .foregroundStyle(Theme.gray)
                    Button("Open iPhone Settings") { session.openSystemSettings() }
                        .foregroundStyle(Theme.champagne)
                } else if session.listener.isListening {
                    Button("Stop listening") { stopNow() }
                        .foregroundStyle(Theme.champagne)
                    Menu("Pause for a while") {
                        Button("15 minutes") { pause(minutes: 15) }
                        Button("1 hour") { pause(minutes: 60) }
                        Button("Until I turn it back on") { stopNow() }
                    }
                    .foregroundStyle(Theme.champagne)
                    Text("Everything said near you is turned into text while this is on.")
                        .font(.caption)
                        .foregroundStyle(Theme.gray)
                } else if let ends = pauseEnds {
                    Button("Start listening now") { startNow() }
                        .foregroundStyle(Theme.champagne)
                    Button("Keep it off — cancel the timer") { stopNow() }
                    Text("If iPhone closes the app before \(clock(ends)), I'll stay off until you start me again. I'd rather be quiet than come back when you didn't expect me.")
                        .font(.caption)
                        .foregroundStyle(Theme.gray)
                } else {
                    Button("Start listening") { startNow() }
                        .foregroundStyle(Theme.champagne)
                    Text("Nothing is being heard, and nothing is being written down.")
                        .font(.caption)
                        .foregroundStyle(Theme.gray)
                }
            }
            .listRowBackground(Theme.card)
            .onAppear(perform: syncPause)

            Section("Pendant") {
                HStack {
                    Text("Status")
                    Spacer()
                    // Was `pendant.state.rawValue.capitalized`, which made this
                    // enum's spelling the UI copy and would have rendered
                    // "Warmingup" the moment a case was added (docs ex 83).
                    Text(pendant.state.plainWords)
                        .foregroundStyle(Theme.gray)
                }
                // Same function as the status pill, so the two surfaces cannot
                // drift into telling the person different things (docs ex 90).
                if let battery = PendantBatteryPolicy.detail(percent: pendant.battery) {
                    HStack {
                        Text("Battery")
                        Spacer()
                        Text(battery)
                            .foregroundStyle(PendantBatteryPolicy.warning(percent: pendant.battery) == .critical
                                             ? Theme.sand : Theme.gray)
                    }
                }
                if let r = pendant.rssi {
                    HStack {
                        Text("Signal")
                        Spacer()
                        Text(r > -60 ? "Strong" : r > -80 ? "OK" : "Weak")
                            .foregroundStyle(Theme.gray)
                    }
                }
                if pendant.state == .connected {
                    Text(session.pendantCapturing
                         ? "Pendant audio goes to Deepgram for live transcription; finalized text then follows the same Anticipy path as phone speech."
                         : "The pendant is connected, but its transcription stream is not live yet.")
                        .font(.caption)
                        .foregroundStyle(Theme.gray)
                }
                if pendant.hasPairedPendant {
                    Button("Forget this pendant", role: .destructive) {
                        pendant.forgetPendant()
                    }
                } else {
                    Button("Pair a pendant") { pendant.startScan() }
                }
            }
            .listRowBackground(Theme.card)

            Section("You") {
                TextField("First name", text: $firstName).textContentType(.givenName)
                TextField("Last name", text: $lastName).textContentType(.familyName)
                TextField("Email", text: $email)
                    .textContentType(.emailAddress)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                TextField("Birthday (YYYY-MM-DD)", text: $birthday)
                    .keyboardType(.numbersAndPunctuation)
                    .textInputAutocapitalization(.never)
                Button("Save details") {
                    Task {
                        detailsSaved = await session.saveOwnerDetails(
                            first: firstName, last: lastName, email: email, birthday: birthday)
                        if detailsSaved { Haptics.success() }
                    }
                }
                .foregroundStyle(Theme.champagne)
                Text(detailsSaved ? "Saved — I can fill booking forms myself now."
                                  : "Every booking and signup form asks for these. Payment details are never stored or filled.")
                    .font(.caption)
                    .foregroundStyle(Theme.gray)
            }
            .listRowBackground(Theme.card)
            .onAppear {
                if firstName.isEmpty { firstName = session.ownerFirstName }
                if lastName.isEmpty { lastName = session.ownerLastName }
                if email.isEmpty { email = session.ownerEmail }
                if birthday.isEmpty { birthday = session.ownerBirthday }
            }

            Section("Your voice") {
                Text(session.speakerTagger.available
                     ? (session.speakerTagger.hasOwnerProfile
                        ? "I know your voice. When someone else makes a promise near me, it stays theirs."
                        : "Teach me your voice and I'll stop mixing up your plans with other people's.")
                     : "Learning voices needs a piece I don't have on this phone yet.")
                    .font(.callout)
                    .foregroundStyle(Theme.sand)
                if session.speakerTagger.available {
                    Button(session.speakerTagger.hasOwnerProfile
                           ? "Teach me again" : "Teach me your voice") {
                        showVoiceEnroll = true
                    }
                    .foregroundStyle(Theme.champagne)
                    let known = session.speakerTagger.roster.unnamedPeople
                    if !known.isEmpty {
                        Text(known.count == 1
                             ? "I've started recognising one other voice around you."
                             : "I've started recognising \(known.count) other voices around you.")
                            .font(.caption)
                            .foregroundStyle(Theme.gray)
                    }
                    Text("Your voice never leaves this phone — not the recording, not a copy. Only the word \"you\" or \"someone else\" travels.")
                        .font(.caption)
                        .foregroundStyle(Theme.gray)
                }
            }
            .listRowBackground(Theme.card)

            Section("Your number") {
                HStack {
                    TextField("+1 604 555 0123", text: $phoneField)
                        .keyboardType(.phonePad)
                        .textContentType(.telephoneNumber)
                        .font(.callout.monospacedDigit())
                        .foregroundStyle(Theme.ivory)
                    Button("Save") {
                        Task {
                            phoneSaved = await session.saveOwnerPhone(phoneField)
                            if phoneSaved { Haptics.success() }
                        }
                    }
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(Theme.champagne)
                    .disabled(phoneField.isEmpty)
                }
                Text(phoneSaved ? "Saved — I'll reach you here."
                                : "Where I text you when something needs your word.")
                    .font(.caption)
                    .foregroundStyle(Theme.gray)
            }
            .listRowBackground(Theme.card)
            .onAppear { if phoneField.isEmpty { phoneField = session.ownerPhone } }

            Section("Your computer") {
                HStack {
                    Text("Status")
                    Spacer()
                    if let secs = session.agentLastSeenSeconds {
                        Text(session.agentOnline ? "Live · seen \(secs)s ago" : "Away · seen \(secs)s ago")
                            .foregroundStyle(session.agentOnline ? Theme.champagne : Theme.gray)
                    } else {
                        Text(session.agentPaired ? "Paired" : "Not paired")
                            .foregroundStyle(Theme.gray)
                    }
                }
                if !session.agentPaired {
                    if let setup = URL(string: backendURL + "/setup.html") {
                        Link(destination: setup) {
                            Label("Set up your browser — step-by-step guide", systemImage: "safari")
                        }
                    }
                    HStack {
                        TextField("6-digit code from the extension", text: $pairCode)
                            .keyboardType(.numberPad)
                            .font(Theme.display(24))
                            .foregroundStyle(Theme.champagne)
                        if pairing {
                            WaveBars()
                        }
                    }
                    // A code that was right and a network that was down used to
                    // read as the same sentence, so people retyped a correct
                    // code for ten minutes. These are now two different truths.
                    switch pairOutcome {
                    case .noMatch:
                        Text("That code didn't match — check the Anticipy Claude Version extension popup for the current one.")
                            .font(.caption)
                            .foregroundStyle(.red)
                    case .unreachable:
                        Text("I can't reach Anticipy Claude Version right now — that's my end, not your code.")
                            .font(.caption)
                            .foregroundStyle(.orange)
                        Button("Try again") { pair() }
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(Theme.champagne)
                            .disabled(pairing)
                    case .paired, .none:
                        EmptyView()
                    }
                } else {
                    // The broken-laptop / new-computer journey used to dead-end
                    // here: a paired phone had no way to let go, the fresh
                    // extension's code had nowhere to be typed, and the only
                    // documented fix was reinstalling the app (found live,
                    // 2026-08-14). Releasing falls back to exactly the
                    // not-paired ceremony above — the extension mints a fresh
                    // code, and the code field reappears on its own.
                    Button(role: .destructive) {
                        Task {
                            await session.backend.unpairAgent(owner: session.ownerID)
                            await session.refresh()
                        }
                    } label: {
                        Label("Release this browser — pair a different one",
                              systemImage: "laptopcomputer.slash")
                    }
                }
                #if DEBUG
                // Bound straight to the key every request is built from, and
                // SwiftUI commits it per keystroke — one character points the
                // app at a dead server with no way back. Developers only.
                TextField("Backend URL", text: $backendURL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .font(.footnote.monospaced())
                #endif
            }
            .listRowBackground(Theme.card)
            // Clear the red line the moment they start retyping, rather than
            // leaving a verdict about the last code sitting over the new one.
            // At six digits it goes on its own — a Pair button after typing the
            // code was one press more than the moment deserved.
            .onChange(of: pairCode) { code in
                pairOutcome = nil
                if code.count == 6 { pair() }
            }
            .onChange(of: pairOutcome) { outcome in
                if outcome == .paired { Haptics.pairing() }
            }

            Section("Between us") {
                Text(voicePath)
                    .font(.callout)
                    .foregroundStyle(Theme.sand)
                Text("The words — the text, not the sound — go to my server. That's how I know what you need.")
                    .font(.callout)
                    .foregroundStyle(Theme.sand)
                Text("If you use a pendant, its Opus audio goes to Deepgram to become text. My backend gives this phone a short-lived token; the Deepgram account key stays on the server.")
                    .font(.callout)
                    .foregroundStyle(Theme.sand)
                Text("Anyone near you is heard too, and they haven't agreed to any of this. Please tell them, or stop me while they're around.")
                    .font(.callout)
                    .foregroundStyle(Theme.sand)
                Text("I text you at your number when something needs your word.")
                    .font(.callout)
                    .foregroundStyle(Theme.sand)
                Text("When you say yes to a task, I open Chrome on your computer and do that one thing. Never before you've said yes.")
                    .font(.callout)
                    .foregroundStyle(Theme.sand)

                if let mail = supportMail {
                    Link(destination: mail) {
                        Label("Ask me anything — hello@anticipationlabs.com", systemImage: "envelope")
                    }
                    .foregroundStyle(Theme.champagne)
                }

                if session.pendingCount > 0 {
                    Button("Delete the \(pendingWords) still waiting to send", role: .destructive) {
                        clearPending()
                    }
                    Text("These never left your phone. Deleting them here means they never will.")
                        .font(.caption)
                        .foregroundStyle(Theme.gray)
                }

                Button("Forget me on this phone", role: .destructive) { confirmForget = true }
                    .alert("Forget you on this phone?", isPresented: $confirmForget) {
                        Button("Forget me", role: .destructive) { forgetMeOnThisPhone() }
                        Button("Cancel", role: .cancel) { }
                    } message: {
                        Text("I'll stop listening, delete anything still waiting to send, clear your name, email, birthday and number from this phone, and give this phone a brand-new identity so nothing new is tied to the old one. Your browser will need pairing again. What I've already sent to my server stays there until I delete it by hand.")
                    }

                if forgotten {
                    Text("Done. This phone doesn't know you any more.")
                        .font(.caption)
                        .foregroundStyle(Theme.champagne)
                }

                // The honest gap, said out loud rather than papered over with a
                // button that would do nothing.
                Text("I can't yet delete what's already on my server from in here — I'm building that. Until it exists, ask me and I'll do it myself and write back when it's done.")
                    .font(.caption)
                    .foregroundStyle(Theme.gray)
                if let mail = deleteMail {
                    Link(destination: mail) {
                        Label("Ask me to delete everything on my server", systemImage: "trash")
                    }
                    .foregroundStyle(Theme.champagne)
                }
                if let privacy = URL(string: "https://backend-production-61e0a.up.railway.app/privacy.html") {
                    Link(destination: privacy) {
                        Label("Read the privacy policy", systemImage: "hand.raised")
                    }
                    .foregroundStyle(Theme.champagne)
                }
            }
            .listRowBackground(Theme.card)

            #if DEBUG
            Section("Haptics — find out what's wrong") {
                let r = haptics.report(listening: session.listener.isListening)

                // Two buttons, because the whole question is WHICH path works.
                // Neither uses .pressable: that style buzzes on press-down, so
                // a test button wearing it would fire both paths at once and
                // tell us nothing.
                Button("1 · Buzz the normal way") { Haptics.engage() }
                Button("2 · Buzz the other way") {
                    haptics.start()
                    haptics.playTest(double: true)
                }

                Text("Turn Listening OFF, try both. Then turn it ON and try both again. If they buzz only with Listening off, the microphone is what's muting them — that tells me exactly what to fix.")
                    .font(.footnote).foregroundStyle(Theme.gray)

                if !r.hardware {
                    Text("This iPhone reports no Taptic Engine — nothing can buzz.")
                        .font(.footnote).foregroundStyle(.red)
                }
                if r.lowPowerMode {
                    // The one blocker that IS readable. Stated plainly.
                    Text("Low Power Mode is ON. iPhone switches haptics off while it is — turn it off in Settings › Battery.")
                        .font(.footnote).foregroundStyle(.orange)
                }
                if r.listening && !r.allowsHapticsWhileRecording {
                    // The smoking gun, if it ever shows up: build 33 asked for
                    // this and the request was made with try? — so a refusal
                    // was invisible until now.
                    Text("Found it: the microphone is refusing to let haptics play. That's mine to fix — tell me you saw this.")
                        .font(.footnote).foregroundStyle(.red)
                }
                if r.hardware && !r.lowPowerMode {
                    Text("If nothing buzzes either way: iPhone Settings › Sounds & Haptics › System Haptics must be ON. No app is allowed to read or change that switch — only you can.")
                        .font(.footnote).foregroundStyle(Theme.gray)
                }

                Text("""
                     mic-allows-haptics \(r.allowsHapticsWhileRecording ? "YES" : "NO")
                     engine \(r.engineRunning ? "running" : "idle")\(r.stoppedReason.map { " · stopped: \($0)" } ?? "")
                     audio \(r.sessionCategory)/\(r.sessionMode) · \(r.listening ? "listening" : "not listening")
                     """)
                    .font(.caption2.monospaced()).foregroundStyle(Theme.gray)
                if let err = r.error {
                    Text(err).font(.caption2.monospaced()).foregroundStyle(.red)
                }
            }
            #endif

            Section {
                Button("Replay the welcome tour") { confirmReplay = true }
                    .alert("Replay the welcome tour?", isPresented: $confirmReplay) {
                        Button("Replay it") { hasOnboarded = false }
                        Button("Not now", role: .cancel) { }
                    } message: {
                        Text("It's the few screens you saw when you first opened me. Nothing you've set up changes — your number, your details and your pendant all stay exactly as they are.")
                    }
            } footer: {
                // The one question that must never be ambiguous again:
                // "which build am I actually running?"
                Text("Anticipy Claude Version \(versionString)")
                    .font(.footnote.monospaced())
                    .foregroundStyle(Theme.gray)
            }
            .listRowBackground(Theme.card)
        }
        .headerProminence(.increased)
        .scrollContentBackground(.hidden)
        .background(
            ZStack {
                Theme.ink
                Grain.image
                    .opacity(0.035)
                    .blendMode(.plusLighter)
                    .allowsHitTesting(false)
            }
            .ignoresSafeArea()
        )
        .tint(Theme.champagne)
        .navigationTitle("Settings")
        .sheet(isPresented: $showVoiceEnroll) {
            VoiceEnrollView().environmentObject(session)
        }
    }

    // MARK: - Listening

    /// The end of a live timed pause, or nil if there isn't one.
    private var pauseEnds: Date? {
        guard pauseUntil > 0 else { return nil }
        let d = Date(timeIntervalSinceReferenceDate: pauseUntil)
        return d > Date() ? d : nil
    }

    private var listeningState: String {
        if session.micBlocked { return "I can't hear anything right now." }
        if session.listener.isListening { return "I'm listening on this phone." }
        if let ends = pauseEnds { return "Paused. I'll start listening again at \(clock(ends))." }
        return "I'm not listening."
    }

    private func clock(_ d: Date) -> String {
        d.formatted(date: .omitted, time: .shortened)
    }

    private func startNow() {
        endPause()
        session.startListening()
    }

    private func stopNow() {
        endPause()
        session.stopListening()
    }

    private func pause(minutes: Int) {
        let deadline = Date().addingTimeInterval(Double(minutes) * 60)
        session.stopListening()
        pauseUntil = deadline.timeIntervalSinceReferenceDate
        armResume(at: deadline)
    }

    private func endPause() {
        resumeTask?.cancel()
        resumeTask = nil
        pauseUntil = 0
    }

    /// Re-arm (or clear) the timer when this screen appears — the pause can
    /// outlive the view that started it, and a second visit shouldn't leave
    /// the promise unattended. A deadline that expired while the app was gone
    /// is simply dropped: she stays off until asked, which is the safe way for
    /// this to fail.
    private func syncPause() {
        if let ends = pauseEnds {
            armResume(at: ends)
        } else if pauseUntil != 0 {
            pauseUntil = 0
        }
    }

    private func armResume(at deadline: Date) {
        resumeTask?.cancel()
        let stamp = deadline.timeIntervalSinceReferenceDate
        resumeTask = Task { @MainActor in
            let seconds = deadline.timeIntervalSinceNow
            if seconds > 0 {
                try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
            }
            // Only the timer that still owns this deadline gets to act, so a
            // re-armed duplicate can never restart her behind a cancel.
            guard !Task.isCancelled, pauseUntil == stamp else { return }
            pauseUntil = 0
            session.startListening()
        }
    }

    // MARK: - Pairing

    private func pair() {
        guard !pairing else { return }
        pairing = true
        Task {
            pairOutcome = await session.pairAgent(code: pairCode)
            pairing = false
        }
    }

    // MARK: - Privacy

    /// The same check the listener makes before it demands on-device speech.
    /// Where it's false, iOS sends the audio to Apple to be written down — so
    /// the screen must not promise otherwise on that phone.
    private static let onDevice: Bool =
        SFSpeechRecognizer(locale: Locale(identifier: "en_US"))?.supportsOnDeviceRecognition ?? false

    private var voicePath: String {
        Self.onDevice
            ? "Your voice stays on this iPhone. The sound is turned into words right here and then it's gone."
            : "This iPhone can't turn speech into words on its own, so while I'm listening the sound goes to Apple's speech service to be written down."
    }

    private var pendingWords: String {
        session.pendingCount == 1 ? "1 line" : "\(session.pendingCount) lines"
    }

    private var versionString: String {
        let v = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
        let b = Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "?"
        return "v\(v) (build \(b))"
    }

    private func mailto(subject: String, body: String) -> URL? {
        var c = URLComponents()
        c.scheme = "mailto"
        c.path = "hello@anticipationlabs.com"
        c.queryItems = [
            URLQueryItem(name: "subject", value: subject),
            URLQueryItem(name: "body", value: body),
        ]
        return c.url
    }

    private var supportMail: URL? {
        mailto(subject: "Anticipy Claude Version — I need a hand",
               body: "\n\n—\nMy Anticipy Claude Version ID: \(session.ownerID)\nApp \(versionString)")
    }

    private var deleteMail: URL? {
        mailto(subject: "Anticipy Claude Version — please delete my data",
               body: "Please delete everything Anticipy Claude Version has heard for me.\n\nMy Anticipy Claude Version ID: \(session.ownerID)\nApp \(versionString)")
    }

    /// Lines that never made it off the phone. Deleting these is a real,
    /// complete delete — nothing else in the app can say that yet.
    private func clearPending() {
        // Goes through the session rather than copying its storage key: a
        // rename there would otherwise leave this button deleting nothing
        // while still reporting success.
        session.clearPendingLines()
    }

    /// Everything a delete can honestly reach from here: the queue, the saved
    /// details, and this device's identity. Deliberately does NOT clear the
    /// feed — those rows are rebuilt from the server on the next poll, so
    /// wiping them on screen would be theatre.
    private func forgetMeOnThisPhone() {
        stopNow()
        clearPending()
        session.ownerFirstName = ""
        session.ownerLastName = ""
        session.ownerEmail = ""
        session.ownerBirthday = ""
        session.ownerPhone = ""
        firstName = ""; lastName = ""; email = ""; birthday = ""; phoneField = ""
        detailsSaved = false
        phoneSaved = false
        if pendant.hasPairedPendant { pendant.forgetPendant() }
        // Let go of the browser BEFORE the identity rotates, or the pairing is
        // orphaned: agents.owner is written once, at pairing, with whatever
        // ownerID the phone had then, and NOTHING ever rewrites it — the
        // /auth/claim hook re-owns jobs, owner_profile, segments and events,
        // but never agents. So the row goes on saying paired to an id this
        // phone no longer uses. Seen for real on 2026-08-05: the extension
        // said "Paired with your iPhone" and showed a completed booking while
        // the phone said "Chrome not linked", and no amount of reloading
        // either side could reconcile them, because they were both right.
        let orphan = session.ownerID
        Task { await session.backend.unpairAgent(owner: orphan) }
        // A fresh identity: nothing said from here on is tied to the old one,
        // and the jobs list (which IS scoped by owner) genuinely empties.
        session.ownerID = UUID().uuidString
        session.jobs = []
        session.sessionLines = []
        session.agentPaired = false
        session.agentOnline = false
        session.agentLastSeenSeconds = nil
        forgotten = true
    }
}
