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
    /// The same key AnticipyApp routes on and the account lifecycle clears -
    /// declared once, in FirstRunOwnership. This was a second copy of the raw
    /// string, which is exactly how a rename leaves a "Replay the welcome
    /// tour" button that silently replays nothing.
    @AppStorage(FirstRunOwnership.flagKey) private var hasOnboarded = false
    /// AND THE INTRODUCTION, because "Replay the welcome tour" names it. The
    /// two pre-auth beats are in front of the sign-in door now, so clearing
    /// only `hasOnboarded` would replay the microphone and the number and skip
    /// the welcome — the one screen the button and its alert both promise.
    @AppStorage(FirstRunOwnership.introKey) private var hasSeenIntro = false
    /// When a timed pause is due to end, as seconds since the reference date;
    /// 0 means "not paused". On disk rather than in @State so the deadline
    /// survives walking away from this screen — the promise on the label has
    /// to outlive the view that made it.
    @AppStorage("listeningPauseUntil") private var pauseUntil: Double = 0
    /// The same key AnticipyApp reads to pin the scheme, so flipping it here
    /// repaints the whole app — the tokens are dynamic colours resolving off
    /// that trait, so nothing has to be told about the change.
    @AppStorage(AppTheme.key) private var themeChoice = AppTheme.light.rawValue

    /// The measured line under the listening row — "Nothing heard for 6 hr
    /// 20 min" — or nil when there is nothing to report.
    ///
    /// A SENTENCE RATHER THAN AN INT, and that is not tidying. This used to be
    /// an `Int` the body compared against zero and handed to `PlainDuration`
    /// inline, which meant the only thing any check could reach was the SHAPE
    /// of the call: that the row asked `PlainDuration`, sat in a `.task`, ran
    /// detached and passed `now:`. Which field it read and whether the seconds
    /// arrived unchanged were pinned by nothing, and both survived being
    /// mutated — `longestSilenceSeconds` for `unheardForSeconds` renders
    /// "Nothing heard for 11 hr" on a phone that heard speech ten seconds ago,
    /// and every check on this screen stayed green over it. The decision now
    /// lives in `UnheardLine`, which is folded from real journals and compared
    /// string for string by `run_interview_invite_tests.sh`.
    ///
    /// Nil until the `.task` below has read it, and nil again the moment the
    /// owner turns listening off — `ListenTally` hard-zeroes the stretch under
    /// `.stoppedByOwner`, so the row cannot appear over somebody's own
    /// deliberate silence.
    @State private var unheardLine: String?

    @State private var pairCode = ""
    @State private var pairOutcome: AnticipySession.PairOutcome?
    @State private var pairing = false
    @State private var phoneField = ""
    /// What the last save of this field came back with, as one value rather
    /// than a lone `phoneSaved` flag. The flag had no room for a failure, so a
    /// save that never reached the server left the caption on its neutral
    /// default and said nothing at all. See `FieldCaption`.
    @State private var phoneAttempt: FieldCaption.Attempt = .untried
    /// In flight. Two taps used to fire two upserts with nothing on screen
    /// between them; the pair row four sections down already had this.
    @State private var savingPhone = false
    @State private var firstName = ""
    @State private var lastName = ""
    @State private var email = ""
    @State private var birthday = ""
    /// The same shape as `phoneAttempt`, for the same reason: `saveOwnerDetails`
    /// comes back false on a dead connection and this section used to swallow
    /// it exactly as the number section did.
    @State private var detailsAttempt: FieldCaption.Attempt = .untried
    @State private var savingDetails = false
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
                    // ON THIS ROW RATHER THAN ON THE SECTION, and the row is
                    // this one because this is the sentence the measured line
                    // below exists to qualify.
                    //
                    // It was on the `Section`, two lines under a
                    // `.listRowBackground` that reaches every row in the
                    // section because that is what row modifiers do. Nobody
                    // could say from reading it whether `.task` was pushed down
                    // the same way — and if it is, this fold ran once per row,
                    // four to seven times, each one a 512KB `queue.sync` on the
                    // same serial queue `record()` takes from the audio thread.
                    // Pinning it to a single row settles the question instead of
                    // arguing it.
                    //
                    // KEYED, NOT BARE, which is the half that was actually
                    // wrong. A bare `.task` runs on appear and never again, so
                    // the number was captured before anything the owner does on
                    // this screen. She opens Settings during an interruption,
                    // reads "Nothing heard for 12 min", taps Stop listening —
                    // the reaction the line is for — and the row goes on saying
                    // it for the rest of the visit, over silence she just chose.
                    // The same defect inverted is worse: the call ends, the
                    // watchdog takes the microphone back, words are being
                    // transcribed in front of her, and the row still claims
                    // nothing has been heard since before lunch.
                    //
                    // The id is the two flags that decide what silence MEANS,
                    // and both are needed. `capturing` alone cannot see the
                    // stop-while-interrupted case at all: suspended already made
                    // it false, so turning listening off does not change it.
                    .task(id: listeningIntent) { unheardLine = await Self.unheardLine() }

                // Ships in RELEASE, unlike the haptics panel further down. The
                // stranger week is a release build on somebody else's phone,
                // and the day worth reading is the day something went wrong on
                // it. A DEBUG-only diagnostic cannot be read from the one
                // device whose behaviour is in question.
                NavigationLink {
                    ListeningDiagnosticsView()
                } label: {
                    Text("Find out what listening actually did")
                }
                .arrowRow()

                // THE ONE NUMBER THAT CAN CONTRADICT THE HEADLINE ABOVE IT, and
                // it has to be on this row rather than one tap deeper.
                // `listeningState` is built from `capturing`, which is
                // `isListening && !suspended` — the app's own INTENT flags, not
                // a fact about the microphone. So the sentence at the top of
                // this section reads "I'm listening on this phone." for exactly
                // the case CLAUDE.md records: the ears went deaf for thirty
                // hours and nothing noticed. Intent said yes the whole time.
                // This line is the half the phone actually measured.
                //
                // NO THRESHOLD, NO COLOUR, NO VERDICT, and that is the design
                // rather than timidity. The same sentence reads "Nothing heard
                // for 4 min" on a healthy phone and "Nothing heard for 6 hr
                // 20 min" on a deaf one; nothing here decides which of those is
                // bad, because nothing here can — there is no recorded normal
                // for this to be measured against, and a rule invented while the
                // sense is unmeasured is what law 1 exists to stop. That is
                // `ListeningDiagnosticsView.swift:38-43` standing on a second
                // screen, and it holds only while both screens word the same
                // seconds the same way — which is why the wording is
                // `PlainDuration`'s and the reading is `UnheardLine`'s, and
                // neither of them is this file's.
                //
                // WHICH FIELD, WHETHER TO SPEAK AND IN WHAT WORDS ARE ALL ONE
                // DECISION, and it is `UnheardLine.words`. Splitting them left
                // the gate here, the field at the fold and the wording a third
                // place, so a check could see all three and pin none: the row
                // read `longestSilenceSeconds` — a historical maximum over the
                // whole journal, not a stretch anybody is in — and reported
                // eleven hours of silence over a phone that heard speech ten
                // seconds ago, with the suite green. One function, folded from
                // real journals in the tests, is what closes that.
                if let unheardLine {
                    Text(unheardLine)
                        .font(.callout)
                        .foregroundStyle(Theme.text2)
                }

                if session.micBlocked {
                    Text("iPhone has microphone access switched off for me. It won't ask again. Only you can turn it back on.")
                        .font(.caption)
                        .foregroundStyle(Theme.muted)
                    Button("Open iPhone Settings") { session.openSystemSettings() }
                        .ghostRow()
                } else if session.listener.isListening {
                    Button("Stop listening") { stopNow() }
                        .ghostRow()
                    // The menu holds the two REAL durations and nothing else.
                    // It used to carry a third item, "Until I turn it back on",
                    // calling the identical `stopNow()` as the button four
                    // lines above and visible at the same moment — a menu
                    // offering a choice already on screen. Which of the two
                    // durations is the common one is not written down anywhere
                    // in this repo, so neither is promoted out to a button;
                    // that comes from watching somebody use it, not from here.
                    //
                    // Full-width label with a Spacer, so the row is as tappable
                    // as the ghost buttons around it. A bare `Menu("…")` is hit
                    // only on its own letters, which made it the one control in
                    // this section with a smaller target than its neighbours.
                    Menu {
                        Button("15 minutes") { pause(minutes: 15) }
                        Button("1 hour") { pause(minutes: 60) }
                    } label: {
                        HStack {
                            Text("Pause for a while")
                            Spacer()
                        }
                        .contentShape(Rectangle())
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
            // The unheard fold used to sit here beside this, and does not any
            // more — it is on the first row of the section, keyed. The reason it
            // was never in this `onAppear` still stands and is the reason it is
            // not in one now: `syncPause` is three field reads and a timer,
            // while the fold reads up to 512KB off disk through a synchronous
            // `queue.sync` and parses every line of it. That belongs off the
            // main actor on the one screen people open when they want listening
            // to STOP, which is the last screen in the app that may be slow to
            // draw.
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
                    // Said plainly, and permanently, rather than as a state
                    // that might change on its own. "Not live yet" invited
                    // somebody to wait for a stream that was never coming
                    // back: LOCAL-FIRST rule 1 closed that lane for good.
                    Text("Connected, but it can't hear for me yet. Turning its sound into words has to happen on this phone, and that piece doesn't exist yet - so the pendant records nothing and sends nothing. Your phone's microphone does all the listening.")
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
                    guard !savingDetails else { return }
                    savingDetails = true
                    // Read once, like the number field below: what was sent is
                    // what the verdict is about, and typing while the request
                    // is in flight must not collect somebody else's "Saved."
                    let sent = (firstName, lastName, email, birthday)
                    Task {
                        let ok = await session.saveOwnerDetails(
                            first: sent.0, last: sent.1, email: sent.2, birthday: sent.3)
                        savingDetails = false
                        guard (firstName, lastName, email, birthday) == sent else { return }
                        detailsAttempt = ok ? .saved : .failed
                        if ok { Haptics.success() }
                    }
                }
                .ghostRow()
                .disabled(savingDetails)
                // `complete: nil` — there is no completeness rule here and this
                // component will not invent one. A first name is never half a
                // name, an email is not validated anywhere in this app, and a
                // birthday is parsed on the server. So the states reachable are
                // neutral, saved and a save that did not land.
                //
                // THE THIRD ONE IS NEW. `saveOwnerDetails` comes back false on
                // a dead connection and this caption used to fall straight back
                // to its neutral sentence — the same swallow the number field
                // below had, on the same screen, four sections apart.
                FieldCaptionLine(
                    text: firstName,
                    complete: nil,
                    attempt: detailsAttempt,
                    words: .init(
                        neutral: "Every booking and signup form asks for these. Payment details are never stored or filled.",
                        saved: "Saved. I can fill booking forms myself now."))
            }
            .listRowBackground(Theme.card)
            .onAppear {
                if firstName.isEmpty { firstName = session.ownerFirstName }
                if lastName.isEmpty { lastName = session.ownerLastName }
                if email.isEmpty { email = session.ownerEmail }
                if birthday.isEmpty { birthday = session.ownerBirthday }
            }
            // A verdict about the last save must not sit over the next edit.
            .onChange(of: firstName) { _ in detailsAttempt = .untried }
            .onChange(of: lastName) { _ in detailsAttempt = .untried }
            .onChange(of: email) { _ in detailsAttempt = .untried }
            .onChange(of: birthday) { _ in detailsAttempt = .untried }

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
                    // No "+1". The example used to assert a country the app
                    // refuses to assume anywhere else: `e164` will not guess
                    // one and `DiallingCode` reads this phone's own region, so
                    // a North American code printed grey in the field was the
                    // one place left still naming a country for somebody.
                    TextField("604 555 0123", text: $phoneField)
                        .keyboardType(.phonePad)
                        .textContentType(.telephoneNumber)
                        .font(.callout.monospacedDigit())
                        .foregroundStyle(Theme.text)
                    if savingPhone {
                        // The same in-flight sign the pair row uses, so waiting
                        // looks the same on both halves of this screen.
                        WaveBars()
                    }
                    // Inline beside the field, so it hugs its own word rather
                    // than spanning the row.
                    Button("Save") {
                        guard !savingPhone else { return }
                        savingPhone = true
                        // READ ONCE, HERE. The old body read `phoneField`
                        // inside the Task, so a digit typed while the request
                        // was in flight was the digit that got saved — and the
                        // verdict then landed on whatever the field held by the
                        // time it came back. A caption saying "Saved." over a
                        // number nobody saved is the same lie this whole fix is
                        // about, arriving from the other direction.
                        let sent = phoneField
                        Task {
                            let ok = await session.saveOwnerPhone(sent)
                            savingPhone = false
                            guard phoneField == sent else { return }
                            phoneAttempt = ok ? .saved : .failed
                            if ok { Haptics.success() }
                        }
                    }
                    .buttonStyle(.ghost)
                    // GATED ON THE PREDICATE THAT ACTUALLY DECIDES, not on
                    // emptiness. Two things were wrong with `phoneField.isEmpty`
                    // and the prefill below makes the first of them permanent:
                    // the field is never empty now, so that test stopped
                    // meaning anything. And it never matched `saveOwnerPhone`,
                    // which begins `guard let e = e164(raw) else { return false }`
                    // — so "+44" lit the button, returned false, and reported
                    // nothing. This is the same expression the first-run beat
                    // gates its own Next button on.
                    .disabled(session.e164(phoneField) == nil || savingPhone)
                }
                // Four states where there were two. `saveOwnerPhone` returning
                // false can now only be the connection: the button is unreachable
                // while `e164` refuses the text, so the two failures that used to
                // arrive as one silent `false` are two different sentences.
                FieldCaptionLine(
                    text: phoneField,
                    complete: session.e164(phoneField) != nil,
                    attempt: phoneAttempt,
                    words: .init(
                        neutral: "Where I text you when something needs your word.",
                        saved: "Saved. I'll reach you here."))
            }
            .listRowBackground(Theme.card)
            // The expression the first-run beat already runs, and for the same
            // reason: `e164` refuses to invent a country, so a refusal is only
            // a fix if the country is in front of the person rather than
            // missing behind them. Somebody who has never saved a number met an
            // empty field here, typed the number they have typed their whole
            // life, and was refused — with, until now, nothing on screen saying
            // what was missing.
            .onAppear {
                if phoneField.isEmpty {
                    phoneField = session.ownerPhone.isEmpty
                        ? DiallingCode.forThisPhone() : session.ownerPhone
                }
            }
            // A "Saved." from the last number must not sit over the next one.
            .onChange(of: phoneField) { _ in phoneAttempt = .untried }

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
                    // And they now wear two weights rather than iOS's red and
                    // orange — the borrowed red the pendant row above says in as
                    // many words "appears nowhere else in the brand", and which
                    // the theme contract's rule 2 exists to keep out of views.
                    // `alarm` is this app's own word for a thing that is wrong.
                    // The unreachable line is explicitly NOT the reader's fault
                    // and says so, so it takes `text2` rather than a warning
                    // colour arguing with its own sentence.
                    switch pairOutcome {
                    case .noMatch:
                        Text("That code didn't match. Check the Anticipy extension popup for the current one.")
                            .font(.caption)
                            .foregroundStyle(Theme.alarm)
                    case .unreachable:
                        Text("I can't reach Anticipy right now. That's my end, not your code.")
                            .font(.caption)
                            .foregroundStyle(Theme.text2)
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
            // Every other section on this form paints its rows `Theme.card`.
            // This one and "What I know about you" were missed, so they sat on
            // the Form's default material instead — near-invisible on white, a
            // different grey in dark, and in both cases a section that reads as
            // not belonging to the page it is on.
            .listRowBackground(Theme.card)

            Section("Between us") {
                Text(voicePath)
                    .font(.callout)
                    .foregroundStyle(Theme.text2)
                Text("The words (the text, not the sound) go to my server. That's how I know what you need.")
                    .font(.callout)
                    .foregroundStyle(Theme.text2)
                // This sentence was a PROMISE about where somebody's audio
                // went, and closing the lane made it false. Deleting it and
                // leaving silence would be worse still - a stranger reading
                // this section deserves the current answer, not a blank.
                Text("Your pendant's sound goes nowhere. It used to be sent away to be turned into words, and it isn't any more: nothing I do with sound leaves this phone. Until I can do that here, on the phone, the pendant can't hear for me.")
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
                        .font(.footnote).foregroundStyle(Theme.alarm)
                }
                if r.lowPowerMode {
                    // The one blocker that IS readable. Stated plainly.
                    Text("Low Power Mode is ON. iPhone switches haptics off while it is. Turn it off in Settings › Battery.")
                        .font(.footnote).foregroundStyle(Theme.text2)
                }
                if r.listening && !r.allowsHapticsWhileRecording {
                    // The smoking gun, if it ever shows up: build 33 asked for
                    // this and the request was made with try? — so a refusal
                    // was invisible until now.
                    Text("Found it: the microphone is refusing to let haptics play. That's mine to fix. Tell me you saw this.")
                        .font(.footnote).foregroundStyle(Theme.alarm)
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
                    Text(err).font(.caption2.monospaced()).foregroundStyle(Theme.alarm)
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
                    // THREE-WAY ON WHAT IS LEFT, because two-way on `isComplete`
                    // put "Let me ask you six questions" directly above a
                    // caption reading "You've answered 4 of 6". Two halves of
                    // one section, reading one `InterviewProgress`, disagreeing
                    // about it — only the caption ever counted, so somebody who
                    // had answered four was offered six.
                    Label(InterviewInvitation.buttonLabel(
                            remaining: InterviewProgress().remaining.count,
                            total: InterviewQuestion.script.count),
                          systemImage: "quote.bubble")
                }
                .ghostRow()
                Text(interviewState)
                    .font(.caption)
                    .foregroundStyle(Theme.muted)
            }
            // The second of the two sections that were missing this. See the
            // Appearance section above for the argument.
            .listRowBackground(Theme.card)

            Section {
                Button("Replay the welcome tour") { confirmReplay = true }
                    .ghostRow()
                    .alert("Replay the welcome tour?", isPresented: $confirmReplay) {
                        // BOTH FLAGS. The alert below says "It's the few
                        // screens you saw when you first opened me", and two
                        // of those screens are now in front of the door.
                        Button("Replay it") {
                            hasOnboarded = false
                            hasSeenIntro = false
                        }
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
        // ABOVE the `capturing` line, and it has to be: `isListening` is the
        // owner's standing wish and stays true for the whole of a phone call,
        // so this screen's headline — her own first-person voice, on the page
        // about what she hears — read "I'm listening on this phone." while
        // something else held the input. The promise underneath is one the app
        // keeps: the 4s watchdog retries the engine on every tick of an outage,
        // and this screen is in the foreground while it is being read.
        if session.listener.suspended {
            return "Something else has the microphone right now. I'll take it back the moment it's free."
        }
        if session.listener.capturing { return "I'm listening on this phone." }
        if let ends = pauseEnds { return "Paused. I'll start listening again at \(clock(ends))." }
        return "I'm not listening."
    }

    private func clock(_ d: Date) -> String {
        d.formatted(date: .omitted, time: .shortened)
    }

    /// WHAT THE MEASURED LINE HAS TO BE RE-READ ON: whether the owner wants
    /// listening, and whether something has taken it away. Order is fixed and
    /// both are load-bearing.
    ///
    /// Not `capturing`, which is the AND of these two and therefore cannot see
    /// the case that matters most. During an interruption `capturing` is
    /// already false; the owner then taps Stop listening and it is false still,
    /// so a task keyed on it would not re-run, and the row would go on
    /// reporting a stretch of silence at somebody who has just chosen silence.
    /// That is the exact sentence this row must never say.
    private var listeningIntent: [Bool] {
        [session.listener.isListening, session.listener.suspended]
    }

    /// What this phone has heard nothing for, in words, as of right now — or
    /// nil when there is nothing to report.
    ///
    /// Detached, because the fold is file I/O plus a parse of every line the
    /// journal holds and the caller is a view body.
    ///
    /// `now:` IS THE WHOLE POINT OF THE CALL and is not a default worth taking.
    /// A fold that can only measure to the journal's own last line answers
    /// "58 min" for a phone that has been deaf since breakfast, because on that
    /// day the last line IS the failure — a call took the microphone at nine
    /// and nothing wrote another line after it. `ListeningDiagnosticsView`
    /// passes it for the same reason and says so at `:138-145`; a reassuring
    /// wrong number is worse than no number, because it is believed.
    ///
    /// The tally goes to `UnheardLine` whole rather than one field being picked
    /// out here. Picking the field here is what let it be the wrong field, in a
    /// place no check could reach.
    private static func unheardLine() async -> String? {
        await Task.detached(priority: .utility) {
            UnheardLine.words(ListenTally.of(ListenJournal.shared.persistedEvents,
                                             now: Date()))
        }.value
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
            // "You haven't told me anything about your life yet" was false on
            // this screen. It sits under a heading reading "What I know about
            // you", four sections below a field holding her first name, one
            // section below her number, and directly above the list of sources
            // she has let in — and it said she had told us nothing. The
            // interview being untouched is not the same claim as knowing
            // nothing, and only the second one was ever on screen.
            //
            // Read from `session` rather than the `@State` copies above: those
            // are seeded on appear and can hold typing nobody has saved yet, and
            // this sentence is about what she HOLDS, not what is in a text field.
            let grants = ContextGrants()
            return InterviewInvitation.nothingAnswered(
                name: !session.ownerFirstName.isEmpty,
                number: !session.ownerPhone.isEmpty,
                calendar: grants.granted(.calendar),
                contacts: grants.granted(.contacts))
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
        // The successors of the `detailsSaved` / `phoneSaved` bools this method
        // used to clear. Set here rather than left to the `.onChange` handlers
        // above: those fire on a CHANGE, and a person who saved nothing and
        // then tapped forget leaves every field already empty — no change, no
        // reset, and a "Saved." sitting over a field whose value was just
        // deleted. The one state a forget must never end in.
        detailsAttempt = .untried
        phoneAttempt = .untried
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

/// What the interview OFFERS, and what she already holds — as words, from one
/// place, so the two halves of one section cannot contradict each other.
///
/// THEY DID CONTRADICT EACH OTHER, both ways round. The button said "Let me ask
/// you six questions" directly above a caption reading "You've answered 4 of 6",
/// because the button was two-way on `isComplete` and only the caption ever
/// counted. And the caption's own opening said "You haven't told me anything
/// about your life yet" on a screen that reads back her first name, her number
/// and every source she has let in. One section, two sentences, neither of them
/// true of the same person.
///
/// PURE FOUNDATION, and `run_interview_invite_tests.sh` lifts this enum out of
/// this file and compiles it against Foundation alone to keep it that way.
/// Nothing here may reach for a Color, a Font or a View: these are decisions
/// about what is true of somebody's account, and a decision that needs a screen
/// to make is a decision that cannot be tested without one.
///
/// NO FRACTION, NO BAR, NO METER, which is `interviewState`'s standing order
/// and the reason it has always been a sentence. A skip records NOTHING
/// (`Interview.swift:113-118`), so an unanswered question is simply still open
/// — and a meter reading two of six would be grading somebody for declining to
/// answer what they were promised was skippable. Counting is not the same act
/// as scoring, and only the first one happens here.
enum InterviewInvitation {

    /// The button, three-way on what is actually left.
    ///
    /// NOT the audit's proposed "2 questions left" / "1 question left", and the
    /// argument against that copy is written four sections up in this same
    /// file: the Appearance row "names what the tap DOES rather than what the
    /// app currently is", because "a control that reads 'Light' while the
    /// screen is light is a status line people tap expecting nothing to
    /// happen". "2 questions left" is precisely that status line, and the
    /// caption directly beneath this button is already where the count is
    /// reported — so the label would have become the third thing on one screen
    /// saying how many are left, and the only one of the three that had stopped
    /// naming an action. The count goes ON the offer instead, in the grammar
    /// the untouched string already uses.
    static func buttonLabel(remaining: Int, total: Int) -> String {
        // Every question answered. The tap reopens them all rather than opening
        // a screen with nothing to ask, so the label must not promise new ones.
        if remaining <= 0 { return "Go over my questions again" }
        // Nothing answered yet: today's words, character for character. "six"
        // is spelled out here and in `nothingAnswered` below and nowhere else,
        // and `run_interview_invite_tests.sh` goes red the day
        // `InterviewQuestion.script` stops holding exactly six — a prose numeral
        // is only true while the array agrees with it, and this one has no way
        // to find out on its own. `>=` rather than `==` so a count that has
        // somehow overrun the script still lands on the offer instead of
        // falling through to "Let me ask you 7 more questions".
        if remaining >= total { return "Let me ask you six questions" }
        return remaining == 1
            ? "Let me ask you 1 more question"
            : "Let me ask you \(remaining) more questions"
    }

    /// The line under the button when the interview itself is untouched.
    ///
    /// NAMED FROM THE HOLDINGS THEMSELVES, never from a count, and never in the
    /// negative. There is no "but not your contacts" branch and there must not
    /// be one: an absence listed beside three presences is a gap with a shape,
    /// and a gap with a shape on a consent screen is an ask wearing a status
    /// line. She names what she has and stops. Every source she does not hold
    /// is already answered honestly one section up, on its own row, where
    /// "What I can see" says so and offers the way back in.
    ///
    /// The clause is a SEPARATE statement of what she holds and is not counted
    /// toward the six. Knowing somebody's phone number is not two-sixths of an
    /// interview, and folding it into the fraction would build the meter the
    /// type comment above refuses.
    ///
    /// When the list really is empty the old sentence is kept verbatim, because
    /// there it was always true.
    static func nothingAnswered(name: Bool, number: Bool,
                                calendar: Bool, contacts: Bool) -> String {
        var held: [String] = []
        if name { held.append("your name") }
        if number { held.append("your number") }
        if calendar { held.append("what's on your calendar") }
        if contacts { held.append("who's in your contacts") }
        guard !held.isEmpty else {
            return "You haven't told me anything about your life yet. Six questions, all skippable."
        }
        return "I know \(sentenceList(held)). Six questions would tell me the rest, all skippable."
    }

    /// "a", "a and b", "a, b and c" — no serial comma, matching the lists this
    /// app already says out loud.
    static func sentenceList(_ parts: [String]) -> String {
        guard let last = parts.last else { return "" }
        guard parts.count > 1 else { return last }
        return parts.dropLast().joined(separator: ", ") + " and " + last
    }
}

/// The one line on the Settings listening row that reports a MEASUREMENT: how
/// long this phone has heard nothing, or nothing at all.
///
/// WHY IT IS A TYPE, 2026-08-26. The row's decision used to be spread across
/// three places — the fold picked the field, the body compared it against zero,
/// and the interpolation wrote the words — and every check any of them had was
/// a check on the SHAPE of the call: that the row asked `PlainDuration`, sat in
/// a `.task`, ran detached, passed `now:`. Which field it read and whether the
/// seconds arrived unchanged were pinned by nothing. Both were mutated and both
/// survived: `unheardForSeconds` swapped for `longestSilenceSeconds`, and the
/// seconds doubled on the way to the formatter. The first of those is not a
/// cosmetic wrong number. `longestSilenceSeconds` is a historical maximum over
/// the whole journal, so on a day that had one long interruption in the morning
/// the row reads "Nothing heard for 11 hr" all evening — present tense, about a
/// phone that heard speech ten seconds ago. That is the reassuring wrong number
/// `ListenTally`'s own comments were written against, pointed the other way: a
/// number that is believed, and this time an alarming one.
///
/// FOLDED FROM REAL JOURNALS IN THE CHECKS, never from a hand-built tally. A
/// `ListenTally()` with one field set proves nothing about which field the
/// screen would have read — the cases in `run_interview_invite_tests.sh` build
/// event lists where `longestSilenceSeconds` and `unheardForSeconds` are
/// different numbers, so only one of them can produce the expected sentence.
///
/// IT NAMES A MAGNITUDE AND STOPS. Above zero is the only gate, and zero is not
/// a threshold — it is the owner's own off switch, because `ListenTally`
/// hard-zeroes this under `.stoppedByOwner` (`ListenTally.swift:317`): quiet
/// after you turned it off is the ordinary state of a phone nobody is talking
/// to, not a finding. Nothing else is compared against the number, because
/// there is no recorded normal in this repo to draw a line from, and a rule
/// invented while the sense is unmeasured is what law 1 exists to stop. A phone
/// that has heard nothing for eleven hours and one that has heard nothing for
/// four minutes both say so, and the reader judges.
///
/// PURE FOUNDATION, like `InterviewInvitation` above and for the same reason:
/// the runner lifts this enum out of this file and compiles it against
/// Foundation alone. Nothing here may reach for a Color, a Font or a View — a
/// formatter that can reach for a colour is a formatter that will eventually
/// return a red one.
enum UnheardLine {

    /// The sentence, or nil.
    ///
    /// Takes the whole tally rather than an Int, so the field it reads is
    /// inside the thing being tested. That is the whole point: handing this an
    /// already-chosen number would move the mutation that survived back out to
    /// the call site, where nothing can see it.
    ///
    /// The words are `PlainDuration`'s. The diagnostics screen reports these
    /// same seconds one tap deeper, and the no-verdict argument both screens
    /// rest on holds only while "6 hr 20 min" here is not "6.3 hours" there.
    static func words(_ tally: ListenTally) -> String? {
        let seconds = tally.unheardForSeconds
        // Zero is the owner's own silence and negative is a clock that moved
        // backwards. Neither is a stretch anybody is missing, and there is no
        // honest sentence to write about either.
        guard seconds > 0 else { return nil }
        return "Nothing heard for \(PlainDuration.words(seconds))"
    }
}
