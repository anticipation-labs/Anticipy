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
    @AppStorage("hasOnboarded") private var hasOnboarded = false
    /// When a timed pause is due to end, as seconds since the reference date;
    /// 0 means "not paused". On disk rather than in @State so the deadline
    /// survives walking away from this screen — the promise on the label has
    /// to outlive the view that made it.
    @AppStorage("listeningPauseUntil") private var pauseUntil: Double = 0
    /// The same key AnticipyApp reads to pin the scheme, so flipping it here
    /// repaints the whole app — the tokens are dynamic colours resolving off
    /// that trait, so nothing has to be told about the change.
    @AppStorage(AppTheme.key) private var themeChoice = AppTheme.light.rawValue

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
    @State private var showInterview = false
    @State private var confirmServerDelete = false
    @State private var serverDeleteNote: String?
    @State private var serverDeleteFailed = false
    /// What just changed about one source, and which one. A revoke is a real
    /// consequence, so it is said out loud under that row rather than left to
    /// a silent re-render — and holding the source with it stops the line
    /// appearing under a source it isn't about.
    @State private var contextNote: (source: ContextSource, text: String)?

    var body: some View {
        Form {
            // Listening is a standing state that survives relaunches, so the
            // one screen people open when they want it to STOP has to be able
            // to stop it. It sits first because that is the reason they came.
            Section("Listening") {
                Text(listeningState)
                    .font(.callout)
                    .foregroundStyle(Theme.text)

                if session.micBlocked {
                    Text("iPhone has microphone access switched off for me. It won't ask again. Only you can turn it back on.")
                        .font(.caption)
                        .foregroundStyle(Theme.muted)
                    Button("Open iPhone Settings") { session.openSystemSettings() }
                        .ghostRow()
                } else if session.listener.isListening {
                    Button("Stop listening") { stopNow() }
                        .ghostRow()
                    Menu("Pause for a while") {
                        Button("15 minutes") { pause(minutes: 15) }
                        Button("1 hour") { pause(minutes: 60) }
                        Button("Until I turn it back on") { stopNow() }
                    }
                    .foregroundStyle(Theme.accent)
                    Text("Everything said near you is turned into text while this is on.")
                        .font(.caption)
                        .foregroundStyle(Theme.muted)
                } else if let ends = pauseEnds {
                    Button("Start listening now") { startNow() }
                        .ghostRow()
                    Button("Keep it off, cancel the timer") { stopNow() }
                        .ghostRow()
                    Text("If iPhone closes the app before \(clock(ends)), I'll stay off until you start me again. I'd rather be quiet than come back when you didn't expect me.")
                        .font(.caption)
                        .foregroundStyle(Theme.muted)
                } else {
                    Button("Start listening") { startNow() }
                        .ghostRow()
                    Text("Nothing is being heard, and nothing is being written down.")
                        .font(.caption)
                        .foregroundStyle(Theme.muted)
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
                        .foregroundStyle(Theme.muted)
                }
                // Same function as the status pill, so the two surfaces cannot
                // drift into telling the person different things (docs ex 90).
                if let battery = PendantBatteryPolicy.detail(percent: pendant.battery) {
                    HStack {
                        Text("Battery")
                        Spacer()
                        Text(battery)
                            .foregroundStyle(PendantBatteryPolicy.warning(percent: pendant.battery) == .critical
                                             ? Theme.text2 : Theme.muted)
                    }
                }
                if let r = pendant.rssi {
                    HStack {
                        Text("Signal")
                        Spacer()
                        Text(r > -60 ? "Strong" : r > -80 ? "OK" : "Weak")
                            .foregroundStyle(Theme.muted)
                    }
                }
                if pendant.state == .connected {
                    Text(session.pendantCapturing
                         ? "Pendant audio goes to Deepgram for live transcription; finalized text then follows the same Anticipy path as phone speech."
                         : "The pendant is connected, but its transcription stream is not live yet.")
                        .font(.caption)
                        .foregroundStyle(Theme.muted)
                }
                if pendant.hasPairedPendant {
                    // Destructive keeps `alarm` for the WORD and takes the
                    // same glass for its geometry. It also stops borrowing
                    // iOS's own red, which appears nowhere else in the brand.
                    Button(role: .destructive) {
                        pendant.forgetPendant()
                    } label: {
                        Text("Forget this pendant")
                            .foregroundStyle(Theme.alarm)
                    }
                    .ghostRow()
                } else {
                    Button("Pair a pendant") { pendant.startScan() }
                        .ghostRow()
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
                .ghostRow()
                Text(detailsSaved ? "Saved. I can fill booking forms myself now."
                                  : "Every booking and signup form asks for these. Payment details are never stored or filled.")
                    .font(.caption)
                    .foregroundStyle(Theme.muted)
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
                    .foregroundStyle(Theme.text2)
                if session.speakerTagger.available {
                    Button(session.speakerTagger.hasOwnerProfile
                           ? "Teach me again" : "Teach me your voice") {
                        showVoiceEnroll = true
                    }
                    .ghostRow()
                    let known = session.speakerTagger.roster.unnamedPeople
                    if !known.isEmpty {
                        Text(known.count == 1
                             ? "I've started recognising one other voice around you."
                             : "I've started recognising \(known.count) other voices around you.")
                            .font(.caption)
                            .foregroundStyle(Theme.muted)
                    }
                    Text("Your voice never leaves this phone. Not the recording, not a copy. Only the word \"you\" or \"someone else\" travels.")
                        .font(.caption)
                        .foregroundStyle(Theme.muted)
                }
            }
            .listRowBackground(Theme.card)

            Section("Your number") {
                HStack {
                    TextField("+1 604 555 0123", text: $phoneField)
                        .keyboardType(.phonePad)
                        .textContentType(.telephoneNumber)
                        .font(.callout.monospacedDigit())
                        .foregroundStyle(Theme.text)
                    // Inline beside the field, so it hugs its own word rather
                    // than spanning the row.
                    Button("Save") {
                        Task {
                            phoneSaved = await session.saveOwnerPhone(phoneField)
                            if phoneSaved { Haptics.success() }
                        }
                    }
                    .buttonStyle(.ghost)
                    .disabled(phoneField.isEmpty)
                }
                Text(phoneSaved ? "Saved. I'll reach you here."
                                : "Where I text you when something needs your word.")
                    .font(.caption)
                    .foregroundStyle(Theme.muted)
            }
            .listRowBackground(Theme.card)
            .onAppear { if phoneField.isEmpty { phoneField = session.ownerPhone } }

            Section("Your computer") {
                HStack {
                    Text("Status")
                    Spacer()
                    if let secs = session.agentLastSeenSeconds {
                        Text(session.agentOnline ? "Live · seen \(secs)s ago" : "Away · seen \(secs)s ago")
                            .foregroundStyle(session.agentOnline ? Theme.accent : Theme.muted)
                    } else {
                        Text(session.agentPaired ? "Paired" : "Not paired")
                            .foregroundStyle(Theme.muted)
                    }
                }
                if !session.agentPaired {
                    if let setup = URL(string: backendURL + "/setup.html") {
                        Link(destination: setup) {
                            Label("Set up your browser, step-by-step guide", systemImage: "safari")
                        }
                        .ghostRow()
                    }
                    HStack {
                        TextField("6-digit code from the extension", text: $pairCode)
                            .keyboardType(.numberPad)
                            .font(Theme.display(24))
                            .foregroundStyle(Theme.accent)
                        if pairing {
                            WaveBars()
                        }
                    }
                    // A code that was right and a network that was down used to
                    // read as the same sentence, so people retyped a correct
                    // code for ten minutes. These are now two different truths.
                    switch pairOutcome {
                    case .noMatch:
                        Text("That code didn't match. Check the Anticipy extension popup for the current one.")
                            .font(.caption)
                            .foregroundStyle(.red)
                    case .unreachable:
                        Text("I can't reach Anticipy right now. That's my end, not your code.")
                            .font(.caption)
                            .foregroundStyle(.orange)
                        Button("Try again") { pair() }
                            .ghostRow()
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
                        Label("Release this browser, pair a different one",
                              systemImage: "laptopcomputer.slash")
                            .foregroundStyle(Theme.alarm)
                    }
                    .ghostRow()
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

            // One row, and it names what the tap DOES rather than what the app
            // currently is: a control that reads "Light" while the screen is
            // light is a status line people tap expecting nothing to happen.
            Section("Appearance") {
                Button {
                    Haptics.engage()
                    themeChoice = AppTheme(rawValue: themeChoice).other.rawValue
                } label: {
                    HStack {
                        Label(AppTheme(rawValue: themeChoice).actionLabel,
                              systemImage: AppTheme(rawValue: themeChoice).icon)
                        Spacer()
                    }
                }
                .ghostRow()
                Text("She opens in light unless you say otherwise, on this phone and in the browser extension. Your iPhone's own Dark Mode setting is left alone.")
                    .font(.caption)
                    .foregroundStyle(Theme.muted)
            }

            Section("Between us") {
                Text(voicePath)
                    .font(.callout)
                    .foregroundStyle(Theme.text2)
                Text("The words (the text, not the sound) go to my server. That's how I know what you need.")
                    .font(.callout)
                    .foregroundStyle(Theme.text2)
                Text("If you use a pendant, its Opus audio goes to Deepgram to become text. My backend gives this phone a short-lived token; the Deepgram account key stays on the server.")
                    .font(.callout)
                    .foregroundStyle(Theme.text2)
                Text("Anyone near you is heard too, and they haven't agreed to any of this. Please tell them, or stop me while they're around.")
                    .font(.callout)
                    .foregroundStyle(Theme.text2)
                Text("I text you at your number when something needs your word.")
                    .font(.callout)
                    .foregroundStyle(Theme.text2)
                Text("When you say yes to a task, I open Chrome on your computer and do that one thing. Never before you've said yes.")
                    .font(.callout)
                    .foregroundStyle(Theme.text2)

                if let mail = supportMail {
                    Link(destination: mail) {
                        Label("Ask me anything, hello@anticipationlabs.com", systemImage: "envelope")
                    }
                    .ghostRow()
                }

                if session.pendingCount > 0 {
                    Button(role: .destructive) {
                        clearPending()
                    } label: {
                        Text("Delete the \(pendingWords) still waiting to send")
                            .foregroundStyle(Theme.alarm)
                    }
                    .ghostRow()
                    Text("These never left your phone. Deleting them here means they never will.")
                        .font(.caption)
                        .foregroundStyle(Theme.muted)
                }

                Button(role: .destructive) { confirmForget = true } label: {
                    Text("Forget me on this phone")
                        .foregroundStyle(Theme.alarm)
                }
                .ghostRow()
                .alert("Forget you on this phone?", isPresented: $confirmForget) {
                    Button("Forget me", role: .destructive) { forgetMeOnThisPhone() }
                    Button("Cancel", role: .cancel) { }
                } message: {
                    Text("I'll stop listening, delete anything still waiting to send, clear your name, email, birthday and number from this phone, and give this phone a brand-new identity so nothing new is tied to the old one. Your browser will need pairing again. What I've already sent to my server stays there until I delete it by hand.")
                }

                if forgotten {
                    Text("Done. This phone doesn't know you any more.")
                        .font(.caption)
                        .foregroundStyle(Theme.accent)
                }

                // The gap this used to apologise for is closed. It said "I can't
                // yet delete what's already on my server from in here. I'm
                // building that", and offered a mailto — while
                // `POST /me/delete` sat built and unreachable.
                // CONSUMER-READINESS §5 gates every consent surface on a delete
                // that works, and two consent surfaces (the context asks, the
                // interview) now exist.
                Button(role: .destructive) {
                    confirmServerDelete = true
                } label: {
                    Text("Delete everything on my server")
                        .foregroundStyle(Theme.alarm)
                }
                .ghostRow()
                .alert("Delete everything?", isPresented: $confirmServerDelete) {
                    Button("Delete it all", role: .destructive) { deleteEverything() }
                    Button("Keep it", role: .cancel) { }
                } message: {
                    Text("Every transcript, memory, errand and receipt I hold for you, and your account itself. It can't be undone, and I'll be signed out when it's finished.")
                }
                if let note = serverDeleteNote {
                    Text(note)
                        .font(.caption)
                        .foregroundStyle(serverDeleteFailed ? Theme.alarm : Theme.accent)
                }
                if let privacy = URL(string: "https://backend-production-61e0a.up.railway.app/privacy.html") {
                    Link(destination: privacy) {
                        Label("Read the privacy policy", systemImage: "hand.raised")
                    }
                    .ghostRow()
                }
            }
            .listRowBackground(Theme.card)

            #if DEBUG
            Section("Haptics, find out what's wrong") {
                let r = haptics.report(listening: session.listener.isListening)

                // Two buttons, because the whole question is WHICH path works.
                // Neither wears .glass or .ghost: both styles buzz on
                // press-down, so a test button wearing one would fire both
                // paths at once and tell us nothing. The only two unstyled
                // controls in the app, and they ship in DEBUG only.
                Button("1 · Buzz the normal way") { Haptics.engage() }
                Button("2 · Buzz the other way") {
                    haptics.start()
                    haptics.playTest(double: true)
                }

                Text("Turn Listening OFF, try both. Then turn it ON and try both again. If they buzz only with Listening off, the microphone is what's muting them, that tells me exactly what to fix.")
                    .font(.footnote).foregroundStyle(Theme.muted)

                if !r.hardware {
                    Text("This iPhone reports no Taptic Engine. Nothing can buzz.")
                        .font(.footnote).foregroundStyle(.red)
                }
                if r.lowPowerMode {
                    // The one blocker that IS readable. Stated plainly.
                    Text("Low Power Mode is ON. iPhone switches haptics off while it is. Turn it off in Settings › Battery.")
                        .font(.footnote).foregroundStyle(.orange)
                }
                if r.listening && !r.allowsHapticsWhileRecording {
                    // The smoking gun, if it ever shows up: build 33 asked for
                    // this and the request was made with try? — so a refusal
                    // was invisible until now.
                    Text("Found it: the microphone is refusing to let haptics play. That's mine to fix. Tell me you saw this.")
                        .font(.footnote).foregroundStyle(.red)
                }
                if r.hardware && !r.lowPowerMode {
                    Text("If nothing buzzes either way: iPhone Settings › Sounds & Haptics › System Haptics must be ON. No app is allowed to read or change that switch. Only you can.")
                        .font(.footnote).foregroundStyle(Theme.muted)
                }

                Text("""
                     mic-allows-haptics \(r.allowsHapticsWhileRecording ? "YES" : "NO")
                     engine \(r.engineRunning ? "running" : "idle")\(r.stoppedReason.map { " · stopped: \($0)" } ?? "")
                     audio \(r.sessionCategory)/\(r.sessionMode) · \(r.listening ? "listening" : "not listening")
                     """)
                    .font(.caption2.monospaced()).foregroundStyle(Theme.muted)
                if let err = r.error {
                    Text(err).font(.caption2.monospaced()).foregroundStyle(.red)
                }
            }
            #endif

            // The other half of consent, and until now it did not exist.
            // `ContextGrant.swift:112-113` has said since it was written that
            // revoking "must be as easy as granting" while `revoke` had no
            // caller anywhere in the app: somebody who let her into their
            // calendar could not take it back on any screen, and nothing told
            // them what she was holding. This is `design/day-zero.md:23` phase
            // 3, "the sources, one toggle at a time", read back afterwards.
            //
            // There is deliberately NO on-switch here, for any source.
            // Granting happens where a reason is on screen: the just-in-time
            // `ContextAskSheet` for the on-device sources, the supervised read
            // for the rest. A bare toggle in Settings is the context-free ask
            // `CONSUMER-READINESS` T4 calls the canonical anti-pattern, and it
            // would also be the "ask before value" `PREMIUM-FEEL.md:43` bans.
            Section("What I can see") {
                ForEach(ContextSource.allCases) { source in
                    contextSourceRow(source)
                }
            }
            .listRowBackground(Theme.card)

            // The interview, reachable on purpose. The Home card offers it once
            // and takes "not now" for an answer permanently — so this is the
            // only way back in, and the card's own comment promises it exists.
            Section("What I know about you") {
                Button {
                    Haptics.engage()
                    // Offering "go over them again" and then opening a screen
                    // with nothing to ask is an offer that does nothing. If
                    // every question is answered, reopen them all — answers
                    // merge on the server (remember_fact dedupes restatements),
                    // so re-answering corrects rather than duplicates.
                    if InterviewProgress().isComplete { InterviewProgress().reopenAll() }
                    showInterview = true
                } label: {
                    Label(InterviewProgress().isComplete
                          ? "Go over my questions again"
                          : "Let me ask you six questions",
                          systemImage: "quote.bubble")
                }
                .ghostRow()
                Text(interviewState)
                    .font(.caption)
                    .foregroundStyle(Theme.muted)
            }

            Section {
                Button("Replay the welcome tour") { confirmReplay = true }
                    .ghostRow()
                    .alert("Replay the welcome tour?", isPresented: $confirmReplay) {
                        Button("Replay it") { hasOnboarded = false }
                        Button("Not now", role: .cancel) { }
                    } message: {
                        Text("It's the few screens you saw when you first opened me. Nothing you've set up changes. Your number, your details and your pendant all stay exactly as they are.")
                    }
            } footer: {
                // The one question that must never be ambiguous again:
                // "which build am I actually running?"
                Text("Anticipy \(versionString)")
                    .font(.footnote.monospaced())
                    .foregroundStyle(Theme.muted)
            }
            .listRowBackground(Theme.card)
        }
        .headerProminence(.increased)
        .sheet(isPresented: $showInterview) {
            InterviewView().environmentObject(session)
        }
        .scrollContentBackground(.hidden)
        .background(
            ZStack {
                Theme.bg
                // The second hand-rolled copy of the grain. Same dark-only
                // blend mode, same white haze once light mode existed.
                GrainLayer()
            }
            .ignoresSafeArea()
        )
        .tint(Theme.accent)
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

    // MARK: - What I can see

    /// One source, in three states that each have to read as true: she holds
    /// it, she has never asked, or she was turned away.
    ///
    /// Every sentence is derived from the gate itself (`ContextGrants`) rather
    /// than from a status kept beside it, so this screen cannot drift out of
    /// agreement with the reader — the same reason `ContextGrants` is a plain
    /// struct over UserDefaults instead of an observed store.
    @ViewBuilder
    private func contextSourceRow(_ source: ContextSource) -> some View {
        // Read fresh on every pass: a grant can land from the ask sheet while
        // this screen sits behind it, and there is no observation graph here.
        let grants = ContextGrants()
        VStack(alignment: .leading, spacing: Theme.Space.tight) {
            Text(source.label)
                .font(.callout.weight(.semibold))
                .foregroundStyle(Theme.text)

            if grants.granted(source) {
                // Her own promises, verbatim. A second description of what she
                // reads would be a copy that drifts from the one the consent
                // sheet showed, and `ContextSource.promises` carries a standing
                // order that every line be true of the code — one place to keep
                // honest, not two.
                ForEach(source.promises, id: \.self) { promise in
                    // Her own promises, one per line — a rule list without the
                    // rule (`CONSUMER-FEEL-DIRECTION` §3d still forbids the
                    // evenly spaced symbol-and-card rows; it never asked for a
                    // hairline). The leading inset went with the hairline so
                    // these sit flush under the source's name.
                    Text(promise)
                        .font(.callout)
                        .foregroundStyle(Theme.text2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                // One tap, no "are you sure?". An alert here would make taking
                // it back harder than giving it, which is the one thing
                // `revoke`'s own doc comment forbids. The destructive alerts
                // elsewhere in this file guard things that cannot be undone;
                // this can be undone by asking again.
                Button(role: .destructive) {
                    revokeContext(source)
                } label: {
                    Text("Stop reading \(source.label.lowercased())")
                        .foregroundStyle(Theme.alarm)
                }
                .ghostRow()
                // The way back IN. Without this the screen is a dead end after
                // the first grant: the Home offer card correctly disappears once
                // `granted(.mail)` is true, and nothing else linked here - so
                // saying yes once was the last time you could ever watch her
                // read. Off-device only; there is nothing to watch for a source
                // read on this phone in a few milliseconds.
                if !source.isOnDevice {
                    NavigationLink {
                        SupervisedReadView(session: session)
                    } label: {
                        Text("Watch me read \(source.label.lowercased())")
                    }
                    // Forward: it opens a screen. `arrowRow` over `ghostRow`
                    // for exactly that reason, and the arrow is the row's
                    // disclosure chevron doing double duty.
                    .arrowRow()
                }
            } else {
                Text(cannotSee(source))
                    .font(.callout)
                    .foregroundStyle(Theme.text2)
                    .fixedSize(horizontal: false, vertical: true)

                if grants.declined(source), source.isOnDevice {
                    // The door out of "no". Before this, `decline` was
                    // permanent: only `grant` cleared `declinedKey`, so a
                    // source she once waved off had `mayAsk` false forever and
                    // could never come up again — while `mayAsk`'s own doc
                    // promised "unless the person opens the door themselves in
                    // Settings". This is that door.
                    //
                    // It grants NOTHING. It restores permission to ask, which
                    // is why it is not labelled as an allow: at the moment of
                    // the tap she still cannot see a thing, and a row that read
                    // "Allow your calendar" would be both a lie and the
                    // context-free toggle T4 warns about.
                    Button("Ask me again when it comes up") { reopenContext(source) }
                        // Forward: the next step is her asking again. It is
                        // the one control in this whole section that opens
                        // something rather than closing it, so it is the one
                        // that carries the arrow; "Stop reading ..." above
                        // stays ghost.
                        .arrowRow()
                }
            }

            if let note = contextNote, note.source == source {
                Text(note.text)
                    .font(.caption)
                    .foregroundStyle(Theme.accent)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.vertical, Theme.Space.hair)
    }

    /// The ungranted truth, and it cannot be one sentence for every source.
    /// `ContextTrigger.ask` only ever returns the on-device sources, so
    /// "I'll ask when something you say needs it" is a promise no code keeps
    /// for the rest of them.
    private func cannotSee(_ source: ContextSource) -> String {
        let object = source.label.lowercased()
        guard source.isOnDevice else {
            // One sentence, whatever the decline flag says. "Watch me read" is
            // a screen you navigate to on purpose, so arriving there IS opening
            // the door: it never checks `declined` and never records one, and
            // an earlier "not now" therefore locks nobody out of it.
            return "I can't see \(object). It begins on \"Watch me read\", where you watch me read it the first time."
        }
        if ContextGrants().declined(source) {
            return "I can't see \(object). You said not now, and I left it there. I won't bring it up again unless you let me."
        }
        return "I can't see \(object). If something you say needs it, I'll ask you then, once. No is a fine answer."
    }

    /// The production caller `ContextGrants.revoke` was written for and never
    /// had. Takes effect before the next read, because the reader asks the same
    /// gate this just wrote.
    private func revokeContext(_ source: ContextSource) {
        ContextGrants().revoke(source)
        // The medium tap, not the page-turn tick: this is a standing state she
        // has just changed, the same weight as flipping the theme above.
        Haptics.engage()
        // `revoke` clears the grant and leaves `declinedKey` alone, so
        // `mayAsk` is true again the moment this returns — the on-device
        // sentence below is what the gate will actually do, not a kindness.
        let object = source.label.lowercased()
        let asksAgain = source.isOnDevice
            ? " If something you say needs it later, I'll ask you again, once."
            : " \"Watch me read\" is still there if you want it back."
        contextNote = (source,
                       "That's off now. I've stopped reading \(object)." + asksAgain
                       + " Anything I'd already sent myself stays on my server until you delete it below.")
    }

    /// Clears an earlier "not now" so the just-in-time ask is allowed to
    /// happen again. This is the whole of it: nothing is granted, nothing is
    /// read, and the next word on it is still hers.
    private func reopenContext(_ source: ContextSource) {
        ContextGrants().reopen(source)
        Haptics.engage()
        contextNote = (source,
                       "Done. I still can't see \(source.label.lowercased()). Next time something you say needs it, I'll ask you then.")
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

    /// The delete the privacy page promised for months.
    ///
    /// Signs out on success, because the account is gone and the token that
    /// authorised the call died with it — leaving somebody looking at a signed-in
    /// shell of a deleted account would be its own small lie.
    private func deleteEverything() {
        serverDeleteNote = "Deleting…"
        serverDeleteFailed = false
        Task {
            let outcome = await session.deleteEverythingOnServer()
            serverDeleteFailed = !outcome.ok
            serverDeleteNote = outcome.message
            if outcome.ok {
                Haptics.taskDone()
                try? await Task.sleep(nanoseconds: 1_500_000_000)
                session.signOut()
            }
        }
    }

    /// What she has been told, in a sentence rather than a fraction.
    private var interviewState: String {
        let progress = InterviewProgress()
        let answered = progress.answeredCount
        if answered == 0 {
            return "You haven't told me anything about your life yet. Six questions, all skippable."
        }
        if progress.isComplete {
            return "You've answered all six. I can go over them again any time."
        }
        return "You've answered \(answered) of \(InterviewQuestion.script.count). The rest are still open."
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
        mailto(subject: "Anticipy. I need a hand",
               body: "\n\n, \nMy Anticipy ID: \(session.ownerID)\nApp \(versionString)")
    }

    private var deleteMail: URL? {
        mailto(subject: "Anticipy, please delete my data",
               body: "Please delete everything Anticipy has heard for me.\n\nMy Anticipy ID: \(session.ownerID)\nApp \(versionString)")
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
