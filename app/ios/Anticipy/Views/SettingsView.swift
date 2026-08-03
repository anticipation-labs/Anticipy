import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var pendant: PendantManager
    @EnvironmentObject var session: AnticipySession
    // Observed, so the readout below refreshes the moment the engine starts,
    // stops, or reports why — otherwise it goes stale exactly while he is
    // standing on this screen testing it.
    @ObservedObject private var haptics = HapticEngine.shared
    @AppStorage("transcriptionEngine") private var engine = "local"
    @AppStorage("proactivityLevel") private var proactivity = 1.0
    @AppStorage("backendURL") private var backendURL = "https://backend-production-61e0a.up.railway.app"
    @AppStorage("hasOnboarded") private var hasOnboarded = true
    @State private var pairCode = ""
    @State private var pairResult: Bool?
    @State private var phoneField = ""
    @State private var phoneSaved = false
    @State private var firstName = ""
    @State private var lastName = ""
    @State private var email = ""
    @State private var birthday = ""
    @State private var detailsSaved = false

    var body: some View {
        Form {
            Section("Pendant") {
                HStack {
                    Text("Status")
                    Spacer()
                    Text(pendant.state.rawValue.capitalized)
                        .foregroundStyle(Theme.gray)
                }
                if let b = pendant.battery {
                    HStack {
                        Text("Battery")
                        Spacer()
                        Text("\(b)%").foregroundStyle(Theme.gray)
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
                if pendant.hasPairedPendant {
                    Button("Forget this pendant", role: .destructive) {
                        pendant.forgetPendant()
                    }
                } else {
                    Button("Pair a pendant") { pendant.startScan() }
                }
            }

            Section("Transcription") {
                Picker("Engine", selection: $engine) {
                    Label("On this iPhone — private, offline", systemImage: "iphone").tag("local")
                    Label("Cloud — fastest, most accurate", systemImage: "cloud").tag("cloud")
                }
                .pickerStyle(.inline)
                Text(engine == "local"
                    ? "Audio never leaves your phone."
                    : "Audio is streamed securely and not stored.")
                    .font(.caption)
                    .foregroundStyle(Theme.gray)
            }

            Section("Proactivity") {
                Slider(value: $proactivity, in: 0 ... 2, step: 1)
                Text(["Only when I ask", "Balanced", "Act on everything"][Int(proactivity)])
                    .font(.caption)
                    .foregroundStyle(Theme.gray)
            }

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
                    Task { detailsSaved = await session.saveOwnerDetails(
                        first: firstName, last: lastName, email: email, birthday: birthday) }
                }
                .foregroundStyle(Theme.champagne)
                Text(detailsSaved ? "Saved — I can fill booking forms myself now."
                                  : "Every booking and signup form asks for these. Payment details are never stored or filled.")
                    .font(.caption)
                    .foregroundStyle(Theme.gray)
            }
            .onAppear {
                if firstName.isEmpty { firstName = session.ownerFirstName }
                if lastName.isEmpty { lastName = session.ownerLastName }
                if email.isEmpty { email = session.ownerEmail }
                if birthday.isEmpty { birthday = session.ownerBirthday }
            }

            Section("Your number") {
                HStack {
                    TextField("+1 604 555 0123", text: $phoneField)
                        .keyboardType(.phonePad)
                        .textContentType(.telephoneNumber)
                        .font(.callout.monospacedDigit())
                        .foregroundStyle(Theme.ivory)
                    Button("Save") {
                        Task { phoneSaved = await session.saveOwnerPhone(phoneField) }
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
            .onAppear { if phoneField.isEmpty { phoneField = session.ownerPhone } }

            Section("Browser agent") {
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
                            .font(.body.monospaced())
                        Button("Pair") {
                            Task { pairResult = await session.pairAgent(code: pairCode) }
                        }
                        .disabled(pairCode.count != 6)
                    }
                    if pairResult == false {
                        Text("That code didn't match — check the Anticipy extension popup.")
                            .font(.caption)
                            .foregroundStyle(.red)
                    }
                }
                TextField("Backend URL", text: $backendURL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .font(.footnote.monospaced())
            }

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

            Section {
                Button("Replay the welcome tour") { hasOnboarded = false }
            } footer: {
                // The one question that must never be ambiguous again:
                // "which build am I actually running?"
                Text("Anticipy v\(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?") (build \(Bundle.main.infoDictionary?["CFBundleVersion"] as? String ?? "?"))")
                    .font(.footnote.monospaced())
                    .foregroundStyle(Theme.gray)
            }
        }
        .scrollContentBackground(.hidden)
        .background(Theme.ink)
        .navigationTitle("Settings")
    }
}
