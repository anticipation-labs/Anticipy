import SwiftUI
import Speech

/// First-run walkthrough: welcome → how it works → may I listen → where to
/// reach you → your browser.
///
/// Two things used to be wrong at the shape level. The pendant was presented as
/// the microphone, so a stranger with no hardware finished believing they
/// couldn't use the product — the phone in their hand IS the product. And the
/// microphone was asked for by iOS with no explanation at all, so the first
/// thing the app ever said to anyone was a system alert. The primer is here to
/// stop that. Every step is still skippable; nothing blocks the app.
struct OnboardingView: View {
    @EnvironmentObject var session: AnticipySession
    @AppStorage("hasOnboarded") private var hasOnboarded = false

    @State private var step = 0
    /// The step we were on before the last change, so a *swipe* off the number
    /// step can save it too. Only the Continue button ever used to save.
    @State private var lastStep = 0

    // Phone number
    @State private var phone = ""
    @State private var phoneSaved = false
    @State private var phoneSaveFailed = false
    @State private var savingPhone = false
    @State private var phoneSkipped = false
    // Her name and email were never asked for anywhere in onboarding, only
    // buried in Settings. That is why she invents them: a booking form wants a
    // name and an email, and with none on file she fills the blank rather than
    // admitting it. Asked here, once, beside the number — all three skippable.
    @State private var firstName = ""
    @State private var email = ""

    // Microphone
    @State private var micAsked = false

    // Browser agent
    @State private var agentCode = ""
    @State private var pairOutcome: AnticipySession.PairOutcome?
    @State private var pairing = false

    private enum Step {
        static let welcome = 0
        static let howItWorks = 1
        static let mic = 2
        static let phone = 3
        static let browser = 4
        static let count = 5
    }

    /// The last four seconds of the flow — the peak-end moment — used to be a
    /// Bool flipping. This holds the celebration scene while she says goodbye.
    @State private var finishing = false

    var body: some View {
        ZStack {
            Theme.ink.ignoresSafeArea()
            VStack(spacing: 0) {
                progressDots
                TabView(selection: $step) {
                    welcome.tag(Step.welcome)
                    howItWorks.tag(Step.howItWorks)
                    micPrimer.tag(Step.mic)
                    yourNumber.tag(Step.phone)
                    browserAgent.tag(Step.browser)
                }
                .tabViewStyle(.page(indexDisplayMode: .never))
                .animation(Theme.springSlow, value: step)
                footer
            }
            if finishing { finale }
        }
        .grainOverlay()
        // Leaving the number step by ANY route — Continue, Skip, or a swipe —
        // saves it. A swipe used to throw a perfectly good number away on a
        // perfect connection, silently.
        .onChange(of: step) { newStep in
            Haptics.pageTurn()
            let previous = lastStep
            lastStep = newStep
            guard previous == Step.phone, newStep != Step.phone else { return }
            savePhoneOnLeaving()
        }
    }

    /// The ending someone will describe to a friend: the mark, two rings
    /// collapsing inward, a rising bloom, two haptics, one typed sentence,
    /// and a dissolve into Home.
    private var finale: some View {
        ZStack {
            Theme.ink.ignoresSafeArea()
            Theme.bloom(0.24, radius: 300)
            VStack(spacing: Theme.Space.roomy) {
                ZStack {
                    RadarRipple(inward: true)
                    RadarRipple(inward: true, delay: 0.8)
                    LogoMark(size: 132)
                }
                .frame(height: 190)
                TypewriterText(text: "Give me a day. You'll see.",
                               font: Theme.display(30),
                               color: Theme.ivory) {
                    Task { @MainActor in
                        try? await Task.sleep(nanoseconds: 1_400_000_000)
                        hasOnboarded = true
                    }
                }
                .multilineTextAlignment(.center)
            }
            .padding(.horizontal, 28)
        }
        .transition(.opacity)
        .onAppear {
            Haptics.pairing()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.55) { Haptics.taskDone() }
        }
    }

    private var progressDots: some View {
        HStack(spacing: 8) {
            ForEach(0 ..< Step.count, id: \.self) { i in
                Capsule()
                    // Steps still to come used to be drawn in Theme.stroke on
                    // Theme.ink — 1.28:1, invisible — so the flow read as
                    // endless. Theme.gray is 5.6:1 and quiet.
                    .fill(i <= step ? Theme.champagne : Theme.gray)
                    .frame(width: i == step ? 22 : 8, height: 6)
                    .animation(Theme.spring, value: step)
            }
        }
        .padding(.top, 18)
        // Let the product introduce itself before it starts counting — the
        // dots turned her introduction into step 1 of 5 of a wizard.
        .opacity(step == Step.welcome ? 0 : 1)
        .animation(Theme.springSlow, value: step)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Step \(step + 1) of \(Step.count)")
    }

    // MARK: - Footer

    private var primaryLabel: String {
        switch step {
        case Step.mic:
            if session.listener.isListening || session.micBlocked || micAsked { return "Continue" }
            return "Yes — start listening"
        case Step.phone:
            return savingPhone ? "Saving…" : "Continue"
        case Step.browser:
            return session.agentPaired ? "Start living your day" : "I'll do this later"
        default:
            return "Continue"
        }
    }

    /// Only the two steps that ask something of the user get an opt-out. It
    /// used to render on four, in 13pt grey, with a tap target under 44pt.
    private var skipLabel: String? {
        switch step {
        case Step.mic: return "Not right now"
        case Step.phone: return "Skip for now"
        default: return nil
        }
    }

    private var footer: some View {
        VStack(spacing: 4) {
            Button {
                Task { await advance() }
            } label: {
                Text(primaryLabel)
                    .id(primaryLabel)
                    .transition(.opacity)
                    .animation(Theme.spring, value: primaryLabel)
                    .font(.body.weight(.semibold))
                    .frame(maxWidth: .infinity, minHeight: 26)
                    .padding(.vertical, 14)
                    .background(Capsule().fill(Theme.champagne))
                    .foregroundStyle(Theme.ink)
            }
            .buttonStyle(.pressable)
            .disabled(savingPhone)
            .opacity(savingPhone ? 0.6 : 1)

            if let skip = skipLabel {
                Button {
                    Haptics.tap()
                    if step == Step.phone { phoneSkipped = true }
                    withAnimation(Theme.spring) { step += 1 }
                } label: {
                    Text(skip)
                        .font(.callout)
                        .foregroundStyle(Theme.sand)
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.pressable)
            } else {
                // The one control that must be the same object on every page
                // was the one thing that moved: reserve the skip row's height
                // so the primary capsule never jumps 44pt on a page turn.
                Color.clear.frame(height: 44)
            }
        }
        .padding(.horizontal, 28)
        .padding(.bottom, 18)
    }

    @MainActor
    private func advance() async {
        Haptics.engage()

        // The affirmative tap. iOS is never asked for the microphone until
        // someone has read what it's for and said yes here — and she gets one
        // typed line in before the system alerts appear.
        if step == Step.mic, !micAsked, !session.micBlocked, !session.listener.isListening {
            micAsked = true
            withAnimation(Theme.spring) { micPriming = true }
            try? await Task.sleep(nanoseconds: 500_000_000)
            session.startListening()
            return
        }

        // The number is the one thing she genuinely cannot work out on her own,
        // so it advances only when the server confirms it landed.
        if step == Step.phone, !phoneSaved, session.e164(phone) != nil {
            savingPhone = true
            let ok = await session.saveOwnerPhone(phone)
            savingPhone = false
            guard ok else {
                withAnimation(Theme.spring) { phoneSaveFailed = true }
                return
            }
            phoneSaved = true
            phoneSaveFailed = false
        }

        if step < Step.count - 1 {
            withAnimation(Theme.spring) { step += 1 }
        } else {
            withAnimation(Theme.springSlow) { finishing = true }
        }
    }

    @MainActor
    private func savePhoneOnLeaving() {
        // Name and email save INDEPENDENTLY of the number. They used to sit
        // behind the phone's validity guard, so skipping the number — or
        // mistyping it — silently threw away the two facts that stop her
        // inventing an address on a booking form.
        let first = firstName.trimmingCharacters(in: .whitespaces)
        let mail = email.trimmingCharacters(in: .whitespaces)
        if !first.isEmpty || !mail.isEmpty {
            Task { _ = await session.saveOwnerDetails(first: first, last: "", email: mail) }
        }
        guard !phoneSaved, !savingPhone, session.e164(phone) != nil else { return }
        Task {
            savingPhone = true
            let ok = await session.saveOwnerPhone(phone)
            savingPhone = false
            if ok {
                phoneSaved = true
                phoneSaveFailed = false
            } else {
                withAnimation(Theme.spring) { phoneSaveFailed = true }
                // Bring them back once so a good number can't vanish quietly.
                // Once they've seen why, or once they've said skip, let them go.
                if !phoneSkipped {
                    withAnimation(Theme.spring) { step = Step.phone }
                }
            }
        }
    }

    /// Every step scrolls and every step centres. None of them used to sit in a
    /// ScrollView, so at large text sizes the bottom of a step was simply cut
    /// off with nothing to scroll.
    private func stepBody<Content: View>(
        alignment: HorizontalAlignment = .center,
        spacing: CGFloat = 18,
        @ViewBuilder content: @escaping () -> Content
    ) -> some View {
        GeometryReader { geo in
            ScrollView {
                VStack(alignment: alignment, spacing: spacing) {
                    content()
                }
                .frame(maxWidth: .infinity, alignment: alignment == .leading ? .leading : .center)
                .padding(.horizontal, 28)
                .padding(.vertical, 20)
                .frame(minHeight: geo.size.height, alignment: .center)
            }
        }
    }

    // MARK: - Welcome

    @State private var welcomeStage = 0

    private static let welcomeLine =
        "I'm Anticipy. I listen, I remember what matters, and I quietly do the work."

    private var welcome: some View {
        stepBody(spacing: 22) {
            ZStack {
                Theme.bloom(0.12, radius: 300)
                LogoMark(size: 120)
                    .scaleEffect(welcomeStage >= 1 ? 1 : 0.6)
                    .opacity(welcomeStage >= 1 ? 1 : 0)
                    .accessibilityHidden(true)
            }
            .frame(height: 130)
            Text("Anticipy")
                .font(Theme.display(40))
                .tracking(-1.0)
                .foregroundStyle(Theme.ivory)
                .opacity(welcomeStage >= 2 ? 1 : 0)
                .offset(y: welcomeStage >= 2 ? 0 : 10)
            // The real string, invisible, reserves the full height — so the
            // logo and wordmark hold perfectly still while she types instead
            // of creeping upward for the entire first sentence.
            Text(Self.welcomeLine)
                .font(.system(size: 17))
                .lineSpacing(3)
                .multilineTextAlignment(.center)
                .opacity(0)
                .overlay(alignment: .topLeading) {
                    if welcomeStage >= 3 {
                        TypewriterText(text: Self.welcomeLine)
                            .lineSpacing(3)
                            .multilineTextAlignment(.center)
                    }
                }
        }
        .task {
            guard welcomeStage == 0 else { return }
            withAnimation(Theme.springSlow) { welcomeStage = 1 }
            Haptics.herMessage()
            // Both beats sit inside the 400ms Doherty window — outside it the
            // intro reads as the app thinking.
            try? await Task.sleep(nanoseconds: 320_000_000)
            withAnimation(Theme.spring) { welcomeStage = 2 }
            try? await Task.sleep(nanoseconds: 260_000_000)
            welcomeStage = 3
        }
    }

    // MARK: - How it works

    @State private var cardsShown = 0

    private var howItWorks: some View {
        stepBody(alignment: .leading) {
            Text("How it works")
                .font(Theme.display(30))
                .tracking(-0.5)
                .foregroundStyle(Theme.ivory)
            // Phone-first. The pendant used to be described as the thing that
            // hears you, in an app whose microphone is the phone's.
            stepCard(icon: "iphone", title: "I listen through your phone",
                     text: "Your phone's microphone is my ears. You switch me on, and I turn what I hear into text.")
                .opacity(cardsShown >= 1 ? 1 : 0)
                .offset(y: cardsShown >= 1 ? 0 : 14)
            stepCard(icon: "sparkles", title: "I remember what matters",
                     text: "I catch the things you say you'll do — “I'll send that over” — and hold them until they're done.")
                .opacity(cardsShown >= 2 ? 1 : 0)
                .offset(y: cardsShown >= 2 ? 0 : 14)
            stepCard(icon: "cursorarrow.click.2", title: "I do the work",
                     text: "I set things up in Chrome on your computer, using accounts you're already signed in to. I ask you here first — nothing goes out until you say yes.")
                .opacity(cardsShown >= 3 ? 1 : 0)
                .offset(y: cardsShown >= 3 ? 0 : 14)
            Text("If you ever have an Anticipy pendant, you can pair it in Settings. You don't need one — your phone is enough.")
                .font(.system(size: 15))
                .lineSpacing(2)
                .foregroundStyle(Theme.sand)
                .opacity(cardsShown >= 3 ? 1 : 0)
        }
        .task(id: step) {
            guard step == Step.howItWorks, cardsShown == 0 else { return }
            for i in 1 ... 3 {
                withAnimation(Theme.spring) { cardsShown = i }
                // 210ms total: still legible as a cascade, no longer a wait.
                try? await Task.sleep(nanoseconds: 70_000_000)
            }
        }
    }

    // MARK: - Microphone primer

    /// Whether this iPhone can turn speech into text without sending audio
    /// anywhere. Mirrors the recogniser the listener actually uses. On a device
    /// where it's false the sentence below has to change — Apple gets the audio,
    /// and saying otherwise would be a promise the product can't keep.
    private static let keepsAudioOnDevice: Bool =
        SFSpeechRecognizer(locale: Locale(identifier: "en_US"))?.supportsOnDeviceRecognition ?? false

    private var keepsAudioOnDevice: Bool { Self.keepsAudioOnDevice }

    /// One typed line before the OS alerts, so the app conducts the
    /// permission moment instead of being ambushed by iOS mid-sentence.
    @State private var micPriming = false

    private var micPrimer: some View {
        stepBody(alignment: .leading, spacing: 16) {
            // The thing the page is about, sitting above the promises: the
            // mark over a bloom, dim until permission lands.
            ZStack {
                Theme.bloom(0.14, radius: 260)
                LogoMark(size: 88)
            }
            .frame(maxWidth: .infinity)
            .frame(height: 110)
            .opacity(session.listener.isListening ? 1.0 : 0.35)
            .animation(Theme.springJoy, value: session.listener.isListening)

            Text("May I listen?")
                .font(Theme.display(30))
                .tracking(-0.5)
                .foregroundStyle(Theme.ivory)
            Text("This is the whole product, so here's exactly what happens.")
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.ivory)

            // Four promises as a rule list — speech-shaped, not form-shaped.
            // Four evenly spaced symbol-and-card rows is the most
            // recognisable AI-built layout there is, and this is where
            // someone decides whether to hand over their microphone.
            promiseRule(title: "What's said near your phone becomes text",
                        text: "You, and the people talking with you. That's how I catch what you've promised and what you need.")
            promiseRule(title: "I keep going in the background",
                        text: "Your phone can be in your pocket or on another app. I stay on until you stop me.")
            promiseRule(title: keepsAudioOnDevice ? "The audio stays on this iPhone" : "This iPhone needs Apple to do the transcribing",
                        text: keepsAudioOnDevice
                           ? "Only the text comes to me, because text is what I can act on."
                           : "So the audio goes to Apple, not to me. The text comes to me, because text is what I can act on.")
            promiseRule(title: "You decide when I'm on",
                        text: "I'm off until you tap. There's a switch on the home screen, and off means off.")

            if micPriming {
                TypewriterText(text: "Two taps from iOS. Both of them are me.",
                               font: .system(size: 15), color: Theme.sand)
                    .transition(.opacity)
            }

            if session.listener.isListening {
                HStack(spacing: 8) {
                    BreathingDot(size: 8)
                    Text("I'm listening. Thank you.")
                        .font(.callout.weight(.semibold))
                        .foregroundStyle(Theme.champagne)
                }
                .transition(.scale.combined(with: .opacity))
            } else if session.micBlocked {
                VStack(alignment: .leading, spacing: 10) {
                    Text("iOS has my microphone switched off. I can't ask again from here — it's one tap in Settings, under Microphone and Speech Recognition.")
                        .font(.footnote)
                        .foregroundStyle(Theme.sand)
                    Button {
                        Haptics.engage()
                        session.openSystemSettings()
                    } label: {
                        Label("Open Settings", systemImage: "gear")
                            .font(.callout.weight(.semibold))
                            .frame(maxWidth: .infinity, minHeight: 44)
                            .background(Capsule().fill(Theme.surface))
                            .foregroundStyle(Theme.ivory)
                    }
                    .buttonStyle(.pressable)
                }
                .anticipyCard()
            } else if !micPriming {
                Text("When you say yes, iOS asks twice — once for speech, once for the microphone. Both are me.")
                    .font(.system(size: 15))
                    .lineSpacing(2)
                    .foregroundStyle(Theme.sand)
            }
        }
        .animation(Theme.spring, value: session.listener.isListening)
    }

    /// The rule-list register: a champagne edge, a title, her sentence.
    /// No fill, no border, no icon column.
    private func promiseRule(title: String, text: String) -> some View {
        HStack(alignment: .top, spacing: 14) {
            Capsule()
                .fill(Theme.champagne.opacity(0.35))
                .frame(width: 2)
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(Theme.ivory)
                Text(text)
                    .font(.system(size: 17))
                    .lineSpacing(3)
                    .foregroundStyle(Theme.sand)
            }
            .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, Theme.Space.hair)
    }

    // MARK: - Your number

    /// The one thing she genuinely cannot work out on her own. Without it she
    /// can hear and prepare but can never reach you.
    private var yourNumber: some View {
        stepBody(spacing: 18) {
            LogoMark(size: 72)
                .accessibilityHidden(true)
            Text("Where should I reach you?")
                .font(Theme.display(30))
                .tracking(-0.5)
                .foregroundStyle(Theme.ivory)
                .multilineTextAlignment(.center)
            Text("When something needs your word, I'll text you. The rest is what every booking form asks for — so I never have to guess it.")
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.sand)
                .multilineTextAlignment(.center)
            TextField("First name", text: $firstName)
                .textContentType(.givenName)
                .autocorrectionDisabled()
                .font(.title3)
                .foregroundStyle(Theme.ivory)
                .multilineTextAlignment(.center)
                .padding(.vertical, 12)
                .padding(.horizontal, 12)
                .background(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous).fill(Theme.surface))
                .overlay(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                    .strokeBorder(Theme.stroke, lineWidth: 1))
                .task { if firstName.isEmpty { firstName = session.ownerFirstName } }
            TextField("you@example.com", text: $email)
                .keyboardType(.emailAddress)
                .textContentType(.emailAddress)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .font(.title3)
                .foregroundStyle(Theme.ivory)
                .multilineTextAlignment(.center)
                .padding(.vertical, 12)
                .padding(.horizontal, 12)
                .background(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous).fill(Theme.surface))
                .overlay(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                    .strokeBorder(Theme.stroke, lineWidth: 1))
                .task { if email.isEmpty { email = session.ownerEmail } }
            TextField("+1 604 555 0123", text: $phone)
                .keyboardType(.phonePad)
                .textContentType(.telephoneNumber)
                .font(.title3.monospacedDigit())
                .foregroundStyle(Theme.ivory)
                .multilineTextAlignment(.center)
                .padding(.vertical, 12)
                .padding(.horizontal, 12)
                .background(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous).fill(Theme.surface))
                .overlay(
                    RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                        .strokeBorder(session.e164(phone) != nil ? Theme.champagne : Theme.stroke,
                                      lineWidth: session.e164(phone) != nil ? 1.5 : 1)
                        .animation(Theme.spring, value: session.e164(phone) != nil)
                )
                // Already told us at the door? Confirm, don't re-interrogate.
                .task { if phone.isEmpty { phone = session.ownerPhone } }
                .onChange(of: phone) { _ in
                    phoneSaved = false
                    phoneSaveFailed = false
                }
            if phoneSaved {
                Label("Saved — I'll text you there.", systemImage: "checkmark.circle.fill")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(Theme.champagne)
            } else if !phone.isEmpty, session.e164(phone) != nil {
                Label("That's you", systemImage: "checkmark.circle.fill")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(Theme.champagne)
                    .transition(.scale.combined(with: .opacity))
                    .onAppear { Haptics.tap() }
            } else if !phone.isEmpty {
                Text("That doesn't look like a full number yet.")
                    .font(.system(size: 15))
                    .foregroundStyle(Theme.gray)
            }
            if phoneSaveFailed {
                VStack(spacing: 10) {
                    Text("I couldn't save that just now — I need a connection to keep it. Your number is still here.")
                        .font(.footnote)
                        .foregroundStyle(Theme.sand)
                        .multilineTextAlignment(.center)
                    Button {
                        Task { await advance() }
                    } label: {
                        Text("Try again")
                            .font(.callout.weight(.semibold))
                            .frame(maxWidth: .infinity, minHeight: 44)
                            .background(Capsule().fill(Theme.surface))
                            .foregroundStyle(Theme.ivory)
                    }
                    .buttonStyle(.pressable)
                    .disabled(savingPhone)
                }
                .anticipyCard()
            }
        }
        .animation(Theme.spring, value: session.e164(phone) != nil)
    }

    // MARK: - Browser agent

    private var browserAgent: some View {
        stepBody(alignment: .leading, spacing: 16) {
            Text("Your hands on\nthe computer")
                .font(Theme.display(30))
                .tracking(-0.5)
                .foregroundStyle(Theme.ivory)
            Text("I work inside your own Chrome, using the accounts you're already signed in to. I never ask for a password.")
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.ivory)
            // The truth. This used to say Chrome "walks you through it", which
            // set someone up for a developer sideload with no warning.
            Text("It takes about two minutes, it has to happen on a computer, and there's one Chrome setting to flip. The guide shows you where.")
                .font(.system(size: 15))
                .lineSpacing(2)
                .foregroundStyle(Theme.sand)

            numbered(1, "On your computer, open the guide I send you")
            numbered(2, "Follow it — you'll turn on one Chrome setting to add me")
            numbered(3, "Type the 6-digit code it shows you, here")

            if let setup = URL(string: "https://backend-production-61e0a.up.railway.app/setup.html") {
                ShareLink(item: setup) {
                    Label("Send the guide to my computer", systemImage: "square.and.arrow.up")
                        .font(.callout.weight(.semibold))
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .background(Capsule().fill(Theme.surface))
                        .foregroundStyle(Theme.ivory)
                }
                .padding(.top, 2)
            }

            if session.agentPaired {
                // Two devices finding each other is the one genuinely magical
                // thing in this flow — it takes over the step instead of
                // rendering smaller than the instructions above it.
                VStack(spacing: Theme.Space.base) {
                    ZStack {
                        Theme.bloom(0.18, radius: 220)
                        RadarRipple(inward: true)
                        RadarRipple(inward: true, delay: 0.8)
                        LogoMark(size: 104)
                    }
                    .frame(maxWidth: .infinity)
                    .frame(height: 170)
                    TypewriterText(text: "Your browser is mine now. In a good way.",
                                   font: .system(size: 17), color: Theme.ivory)
                        .multilineTextAlignment(.center)
                }
                .anticipyCard()
                .padding(.top, 4)
                .transition(.scale(scale: 0.9).combined(with: .opacity))
                .onAppear { Haptics.pairing() }
            } else {
                // The six-digit code is a ceremony, not a form: six boxes, a
                // hidden field, and it pairs itself on the sixth digit.
                codeBoxes
                    .padding(.top, 4)
                    // The red line used to stay on screen while they retyped.
                    // Clear it the moment the code changes.
                    .onChange(of: agentCode) { code in
                        if pairOutcome != nil {
                            withAnimation(Theme.spring) { pairOutcome = nil }
                        }
                        if code.count > 6 { agentCode = String(code.prefix(6)) }
                        if agentCode.count == 6 { pair() }
                        else if !code.isEmpty { Haptics.tap() }
                    }

                // A blip, a plane or hotel wifi used to be reported as a wrong
                // code — so people retyped a code that was right all along.
                switch pairOutcome {
                case .noMatch:
                    Text("That code didn't match. It's the six digits on the Anticipy page in Chrome.")
                        .font(.system(size: 15))
                        .lineSpacing(2)
                        .foregroundStyle(Theme.alarm)
                        .onAppear { Haptics.warning() }
                case .unreachable:
                    VStack(alignment: .leading, spacing: 10) {
                        Text("I can't reach Anticipy right now, so I couldn't check that code. It's probably the connection, not you.")
                            .font(.footnote)
                            .foregroundStyle(Theme.sand)
                        Button {
                            pair()
                        } label: {
                            Text("Try again")
                                .font(.callout.weight(.semibold))
                                .frame(maxWidth: .infinity, minHeight: 44)
                                .background(Capsule().fill(Theme.surface))
                                .foregroundStyle(Theme.ivory)
                        }
                        .buttonStyle(.pressable)
                        .disabled(pairing)
                    }
                    .anticipyCard()
                case .paired, .none:
                    EmptyView()
                }
            }
        }
    }

    @MainActor
    private func pair() {
        guard agentCode.count == 6, !pairing else { return }
        Haptics.engage()
        Task {
            pairing = true
            let outcome = await session.pairAgent(code: agentCode)
            pairing = false
            withAnimation(Theme.spring) { pairOutcome = outcome }
        }
    }

    @FocusState private var codeFocused: Bool

    private var codeBoxes: some View {
        ZStack {
            // One hidden field holds the string; the boxes are the display.
            TextField("", text: $agentCode)
                .keyboardType(.numberPad)
                .textContentType(.oneTimeCode)
                .focused($codeFocused)
                .opacity(0.02)
                .frame(width: 1, height: 1)
            HStack(spacing: Theme.Space.tight) {
                ForEach(0 ..< 6, id: \.self) { i in
                    let digits = Array(agentCode)
                    let active = i == min(agentCode.count, 5) && !pairing
                    Text(i < digits.count ? String(digits[i]) : "")
                        .font(.system(size: 24, weight: .medium, design: .monospaced))
                        .foregroundStyle(Theme.ivory)
                        .frame(width: 44, height: 54)
                        .background(
                            RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                                .fill(Theme.surface)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                                .strokeBorder(active ? Theme.champagne : Theme.stroke,
                                              lineWidth: active ? 1.5 : 1)
                        )
                        .scaleEffect(active ? 1.06 : 1)
                        .animation(Theme.spring, value: agentCode)
                }
                if pairing {
                    BreathingDot(size: 8)
                        .padding(.leading, Theme.Space.hair)
                }
            }
            .contentShape(Rectangle())
            .onTapGesture { codeFocused = true }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func numbered(_ n: Int, _ text: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Text("\(n)")
                .font(.callout.weight(.bold))
                .frame(width: 28, height: 28)
                .background(Circle().fill(Theme.surface))
                .foregroundStyle(Theme.champagne)
            Text(text)
                .font(.callout)
                .foregroundStyle(Theme.ivory)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func stepCard(icon: String, title: String, text: String) -> some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(Theme.champagne)
                .frame(width: 30)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.body.weight(.semibold)).foregroundStyle(Theme.ivory)
                Text(text).font(.footnote).foregroundStyle(Theme.gray)
            }
            .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
    }
}

/// A repeating radar ripple for scanning states — one ring expanding and
/// fading out from the logo, until the searching state ends. A forever-looping
/// ring is exactly what Reduce Motion exists to stop, so with it on the ring
/// simply sits there.
struct RadarRipple: View {
    /// Scanning expands outward; arrival collapses inward.
    var inward = false
    var delay: Double = 0
    @State private var expand = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        Circle()
            .stroke(Theme.champagne.opacity(0.5), lineWidth: 2)
            .frame(width: 130, height: 130)
            .scaleEffect(expand ? (inward ? 1.0 : 1.45) : (inward ? 1.45 : 1.0))
            .opacity(expand ? 0 : 0.8)
            .animation(
                reduceMotion ? .default
                    // 3.2s: twice the app's 1.6s ambient harmonic, so the
                    // ring and the breathing dot move as one organism.
                    : .easeOut(duration: 3.2).repeatForever(autoreverses: false).delay(delay),
                value: expand
            )
            .onAppear { if !reduceMotion { expand = true } }
            .accessibilityHidden(true)
    }
}
