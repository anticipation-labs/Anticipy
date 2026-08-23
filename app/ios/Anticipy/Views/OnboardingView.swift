import SwiftUI
import Speech

/// First-run walkthrough: welcome → how it works → may I listen → where to
/// reach you.
///
/// Two things used to be wrong at the shape level. The pendant was presented as
/// the microphone, so a stranger with no hardware finished believing they
/// couldn't use the product — the phone in their hand IS the product. And the
/// microphone was asked for by iOS with no explanation at all, so the first
/// thing the app ever said to anyone was a system alert. The primer is here to
/// stop that. Every step is still skippable; nothing blocks the app.
///
/// The browser used to be a fifth page here, and it was the one page nobody
/// could finish on the phone in their hand. `design/day-zero.md:237-239` moved
/// it out: "It is asked just-in-time, when an errand actually needs hands,
/// which also returns the ~70-second budget and removes a step from what the
/// audit called a six-step wall." The pairing ceremony lives in Settings,
/// where it always did; Home offers it the first time an errand is actually
/// parked for want of hands — see `HomeView.browserOfferCard`.
struct OnboardingView: View {
    @EnvironmentObject var session: AnticipySession
    /// Called the instant the last step is cleared. The CALLER writes the
    /// durable "this person has onboarded" flag and then plays the celebration
    /// over Home — see AnticipyApp.
    ///
    /// This used to be a `hasOnboarded = true` at the tail of a ~2.4s animation
    /// inside this view: the typewriter had to finish, call back, and a further
    /// 1.4s sleep had to elapse before anything was written down. Anything that
    /// interrupted those seconds — backgrounding the app, force-quitting, the
    /// view being torn down — left the flag false, and the person did all five
    /// steps again on the next launch with their name, email and number already
    /// saved. Recording the fact and celebrating it are now two different jobs.
    let onFinished: () -> Void

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
    @State private var detailsSaved = false
    // Her name and email were never asked for anywhere in onboarding, only
    // buried in Settings. That is why she invents them: a booking form wants a
    // name and an email, and with none on file she fills the blank rather than
    // admitting it. Asked here, once, beside the number — all three skippable.
    @State private var firstName = ""
    @State private var email = ""

    // Microphone
    @State private var micAsked = false

    /// Four beats. The browser was a fifth until `design/day-zero.md:237-239`
    /// took it out of first run; nothing here may exceed the ~70-second budget
    /// in `CONSUMER-FEEL-DIRECTION-2026-08-03.md` §5.
    private enum Step {
        static let welcome = 0
        static let howItWorks = 1
        static let mic = 2
        static let phone = 3
        static let count = 4
    }

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()
            VStack(spacing: 0) {
                progressTrack
                TabView(selection: $step) {
                    welcome.tag(Step.welcome)
                    howItWorks.tag(Step.howItWorks)
                    micPrimer.tag(Step.mic)
                    yourNumber.tag(Step.phone)
                }
                .tabViewStyle(.page(indexDisplayMode: .never))
                .animation(Theme.springSlow, value: step)
                footer
            }
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


    /// What each beat is called, in step order. Short because the live one
    /// renders on a single line beside its count on a 375pt phone.
    private static let beatNames = ["Hello", "How I work", "May I listen?", "Where to reach you"]

    /// Progress in one line: the beat you are on, and which of four it is.
    ///
    /// `design/day-zero.md:230-231` asked for "a rule list with a live marker,
    /// not wizard dots", and this was four 2px rules laid on their side — the
    /// live one in the accent, finished ones dimmer, still-to-come quiet, and
    /// only the live beat's text at full strength. The golden bars are out of
    /// the product now, and the COLOUR of those rules was the position, so the
    /// position moved into type rather than leaving with them: the live beat
    /// says its name at full strength, and its number sits beside it in the
    /// quiet register counts belong in.
    ///
    /// Not four dimmed names in a row instead. The four of them are 46
    /// characters; on a 375pt phone with 28pt gutters they only fit by
    /// shrinking to illegible, and at accessibility sizes they would wrap and
    /// shove the TabView down the screen — the same reason only the live beat
    /// has ever said its name here.
    private var progressTrack: some View {
        HStack(alignment: .firstTextBaseline, spacing: Theme.Space.tight) {
            Text(Self.beatNames[step])
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(Theme.text)
                .lineLimit(1)
                // A clipped progress label is survivable at AX5; a wrapped one
                // would shove the TabView down the screen on every step that
                // has a long name.
                .minimumScaleFactor(0.75)
                // A new identity per beat, so the name still crossfades on the
                // page turn the way it did when it belonged to a live rule.
                .id(step)
                .transition(.opacity)
            Text("\(step + 1) of \(Step.count)")
                .font(Theme.meta)
                .foregroundStyle(Theme.muted)
                .lineLimit(1)
            Spacer(minLength: 0)
        }
        .animation(Theme.spring, value: step)
        .padding(.horizontal, 28)
        .padding(.top, 18)
        // Let the product introduce itself before it starts counting — the
        // track turned her introduction into step 1 of 4 of a wizard.
        .opacity(step == Step.welcome ? 0 : 1)
        .animation(Theme.springSlow, value: step)
        .accessibilityElement(children: .ignore)
        // "Step N of M" is what a screen-reader user needs to know; the beat
        // name is what the live marker adds for everyone else, so it says
        // both rather than trading one for the other.
        .accessibilityLabel("Step \(step + 1) of \(Step.count), \(Self.beatNames[step])")
        // An element drawn at zero opacity that still announces "Step 1 of 4"
        // is a wizard for VoiceOver users only.
        .accessibilityHidden(step == Step.welcome)
    }

    // MARK: - Footer

    private var primaryLabel: String {
        switch step {
        case Step.mic:
            if session.listener.isListening || session.micBlocked || micAsked { return "Continue" }
            return "Yes, start listening"
        case Step.phone:
            // The last page, now the browser has left first run, so the button
            // has to read like an ending instead of promising another page.
            return savingPhone ? "Saving…" : "Start living your day"
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
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.glass)
            // No hand-rolled .opacity beside this: the style dims what is
            // disabled, so every control in the app dims by the same amount.
            .disabled(savingPhone)

            if let skip = skipLabel {
                Button {
                    // The number is the last page now, so "Skip for now" has
                    // nowhere to advance to — it ends the walkthrough instead.
                    // It still saves the name and email they DID type: the
                    // onChange(of: step) hook that normally does that on the
                    // way out cannot fire when the step never changes.
                    if step == Step.phone {
                        phoneSkipped = true
                        savePhoneOnLeaving()
                        onFinished()
                        return
                    }
                    withAnimation(Theme.spring) { step += 1 }
                } label: {
                    Text(skip)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.ghost)
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

        // This is one profile checkpoint, not three optimistic fields. The
        // flow advances only after every non-empty fact is durably stored.
        if step == Step.phone {
            savingPhone = true
            if !phoneSaved, session.e164(phone) != nil {
                let ok = await session.saveOwnerPhone(phone)
                guard ok else {
                    savingPhone = false
                    withAnimation(Theme.spring) { phoneSaveFailed = true }
                    return
                }
                phoneSaved = true
            }
            let first = firstName.trimmingCharacters(in: .whitespaces)
            let mail = email.trimmingCharacters(in: .whitespaces)
            if !detailsSaved, !first.isEmpty || !mail.isEmpty {
                let ok = await session.saveOwnerDetails(first: first, last: "", email: mail)
                guard ok else {
                    savingPhone = false
                    withAnimation(Theme.spring) { phoneSaveFailed = true }
                    return
                }
                detailsSaved = true
            }
            savingPhone = false
            phoneSaveFailed = false
        }

        if step < Step.count - 1 {
            withAnimation(Theme.spring) { step += 1 }
        } else {
            // The last step is cleared. Say so and let the caller write it
            // down; nothing about the celebration can strand anyone now.
            onFinished()
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
            Task {
                let ok = await session.saveOwnerDetails(first: first, last: "", email: mail)
                if ok { detailsSaved = true }
            }
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
            // The mark alone. This is the screen the champagne haze was
            // asked off three times: a full-screen wash behind a logo is
            // wallpaper, and the product has no ambient gradient anywhere now.
            LogoMark(size: 120)
                .scaleEffect(welcomeStage >= 1 ? 1 : 0.6)
                .opacity(welcomeStage >= 1 ? 1 : 0)
                .accessibilityHidden(true)
                .frame(height: 130)
            Text("Anticipy")
                .font(Theme.display(40))
                .tracking(-1.0)
                .foregroundStyle(Theme.text)
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
                .foregroundStyle(Theme.text)
            // Phone-first. The pendant used to be described as the thing that
            // hears you, in an app whose microphone is the phone's.
            stepCard(icon: "iphone", title: "I listen through your phone",
                     text: "Your phone's microphone is my ears. You switch me on, and I turn what I hear into text.")
                .opacity(cardsShown >= 1 ? 1 : 0)
                .offset(y: cardsShown >= 1 ? 0 : 14)
            stepCard(icon: "sparkles", title: "I remember what matters",
                     text: "I catch the things you say you'll do (“I'll send that over”) and hold them until they're done.")
                .opacity(cardsShown >= 2 ? 1 : 0)
                .offset(y: cardsShown >= 2 ? 0 : 14)
            stepCard(icon: "cursorarrow.click.2", title: "I do the work",
                     text: "I set things up in Chrome on your computer, using accounts you're already signed in to. I ask you here first. Nothing goes out until you say yes.")
                .opacity(cardsShown >= 3 ? 1 : 0)
                .offset(y: cardsShown >= 3 ? 0 : 14)
            Text("If you ever have an Anticipy pendant, you can pair it in Settings. You don't need one. Your phone is enough.")
                .font(.system(size: 15))
                .lineSpacing(2)
                .foregroundStyle(Theme.text2)
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
    // Computed live, never cached: on-device speech support FLIPS when iOS
    // finishes downloading the recognition assets, and a static let froze the
    // answer at process start — so onboarding said "audio goes to Apple"
    // while Settings (computing live) said "stays on this iPhone" on the
    // same device the same night (2026-08-14). The listener follows the live
    // value, so the live value is the only honest copy.
    private var keepsAudioOnDevice: Bool {
        SFSpeechRecognizer(locale: Locale(identifier: "en_US"))?.supportsOnDeviceRecognition ?? false
    }

    /// One typed line before the OS alerts, so the app conducts the
    /// permission moment instead of being ambushed by iOS mid-sentence.
    @State private var micPriming = false

    private var micPrimer: some View {
        stepBody(alignment: .leading, spacing: 16) {
            // The thing the page is about, sitting above the promises: the
            // mark alone, dim until permission lands. No haze under it —
            // the ambient champagne is gone from the whole product.
            LogoMark(size: 88)
                .frame(maxWidth: .infinity)
                .frame(height: 110)
                .opacity(session.listener.isListening ? 1.0 : 0.35)
                .animation(Theme.springJoy, value: session.listener.isListening)

            Text("May I listen?")
                .font(Theme.display(30))
                .tracking(-0.5)
                .foregroundStyle(Theme.text)
            Text("This is the whole product, so here's exactly what happens.")
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.text)

            // Four promises as a rule list — speech-shaped, not form-shaped.
            // Four evenly spaced symbol-and-card rows is the most
            // recognisable AI-built layout there is, and this is where
            // someone decides whether to hand over their microphone.
            promiseLine(title: "What's said near your phone becomes text",
                        text: "You, and the people talking with you. That's how I catch what you've promised and what you need.")
            promiseLine(title: "I keep going in the background",
                        text: "Your phone can be in your pocket or on another app. I stay on until you stop me.")
            promiseLine(title: keepsAudioOnDevice ? "The audio stays on this iPhone" : "This iPhone needs Apple to do the transcribing",
                        text: keepsAudioOnDevice
                           ? "Only the text comes to me, because text is what I can act on."
                           : "So the audio goes to Apple, not to me. The text comes to me, because text is what I can act on.")
            promiseLine(title: "You decide when I'm on",
                        text: "I'm off until you tap. There's a switch on the home screen, and off means off.")

            if micPriming {
                TypewriterText(text: "Two taps from iOS. Both of them are me.",
                               font: .system(size: 15), color: Theme.text2)
                    .transition(.opacity)
            }

            if session.listener.isListening {
                HStack(spacing: 8) {
                    BreathingDot(size: 8)
                    Text("I'm listening. Thank you.")
                        .font(.callout.weight(.semibold))
                        .foregroundStyle(Theme.accent)
                }
                .transition(.scale.combined(with: .opacity))
            } else if session.micBlocked {
                VStack(alignment: .leading, spacing: 10) {
                    Text("iOS has my microphone switched off. I can't ask again from here. It's one tap in Settings, under Microphone and Speech Recognition.")
                        .font(.footnote)
                        .foregroundStyle(Theme.text2)
                    // Inside a card, so it is the card's action, not the
                    // page's: ghost, and the page's own primary keeps being
                    // the only glass CTA on screen.
                    Button {
                        Haptics.engage()
                        session.openSystemSettings()
                    } label: {
                        Label("Open Settings", systemImage: "gear")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.ghost)
                }
                .anticipyCard()
            } else if !micPriming {
                Text("When you say yes, iOS asks twice, once for speech, once for the microphone. Both are me.")
                    .font(.system(size: 15))
                    .lineSpacing(2)
                    .foregroundStyle(Theme.text2)
            }
        }
        .animation(Theme.spring, value: session.listener.isListening)
    }

    /// The rule-list register, now without the rule: a title, her sentence,
    /// and the space between one promise and the next. No fill, no border, no
    /// icon column, and no champagne edge — that edge came out with every
    /// other golden bar, and the indent it needed came out with it.
    private func promiseLine(title: String, text: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Theme.text)
            Text(text)
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.text2)
        }
        .fixedSize(horizontal: false, vertical: true)
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
                .foregroundStyle(Theme.text)
                .multilineTextAlignment(.center)
            Text("When something needs your word, I'll text you. The rest is what every booking form asks for, so I never have to guess it.")
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.text2)
                .multilineTextAlignment(.center)
            TextField("First name", text: $firstName)
                .textContentType(.givenName)
                .autocorrectionDisabled()
                .font(.title3)
                .foregroundStyle(Theme.text)
                .multilineTextAlignment(.center)
                .padding(.vertical, 12)
                .padding(.horizontal, 12)
                .background(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous).fill(Theme.surface))
                .overlay(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                    .strokeBorder(Theme.edge, lineWidth: 1))
                .task { if firstName.isEmpty { firstName = session.ownerFirstName } }
                .onChange(of: firstName) { _ in detailsSaved = false; phoneSaveFailed = false }
            TextField("you@example.com", text: $email)
                .keyboardType(.emailAddress)
                .textContentType(.emailAddress)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .font(.title3)
                .foregroundStyle(Theme.text)
                .multilineTextAlignment(.center)
                .padding(.vertical, 12)
                .padding(.horizontal, 12)
                .background(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous).fill(Theme.surface))
                .overlay(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                    .strokeBorder(Theme.edge, lineWidth: 1))
                .task { if email.isEmpty { email = session.ownerEmail } }
                .onChange(of: email) { _ in detailsSaved = false; phoneSaveFailed = false }
            TextField("+1 604 555 0123", text: $phone)
                .keyboardType(.phonePad)
                .textContentType(.telephoneNumber)
                .font(.title3.monospacedDigit())
                .foregroundStyle(Theme.text)
                .multilineTextAlignment(.center)
                .padding(.vertical, 12)
                .padding(.horizontal, 12)
                .background(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous).fill(Theme.surface))
                .overlay(
                    RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                        .strokeBorder(session.e164(phone) != nil ? Theme.accent : Theme.edge,
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
                Label("Saved. I'll text you there.", systemImage: "checkmark.circle.fill")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(Theme.accent)
            } else if !phone.isEmpty, session.e164(phone) != nil {
                Label("That's you", systemImage: "checkmark.circle.fill")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(Theme.accent)
                    .transition(.scale.combined(with: .opacity))
                    .onAppear { Haptics.tap() }
            } else if !phone.isEmpty {
                Text("That doesn't look like a full number yet.")
                    .font(.system(size: 15))
                    .foregroundStyle(Theme.muted)
            }
            if phoneSaveFailed {
                VStack(spacing: 10) {
                    Text("I couldn't save that just now. I need a connection to keep it. Everything you entered is still here.")
                        .font(.footnote)
                        .foregroundStyle(Theme.text2)
                        .multilineTextAlignment(.center)
                    Button {
                        Task { await advance() }
                    } label: {
                        Text("Try again")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.ghost)
                    .disabled(savingPhone)
                }
                .anticipyCard()
            }
        }
        .animation(Theme.spring, value: session.e164(phone) != nil)
    }

    private func stepCard(icon: String, title: String, text: String) -> some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(Theme.accent)
                .frame(width: 30)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.body.weight(.semibold)).foregroundStyle(Theme.text)
                Text(text).font(.footnote).foregroundStyle(Theme.muted)
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
            .stroke(Theme.accent.opacity(0.5), lineWidth: 2)
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
