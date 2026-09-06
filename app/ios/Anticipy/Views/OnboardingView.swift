import SwiftUI
import Speech
import UIKit

/// First-run walkthrough: welcome → a three-page tour → the sign-in door →
/// your name → your computer → may I listen — one screen, one question, and a
/// circular arrow to the next.
///
/// This view is instantiated with a `FirstRunSegment` and carries only that
/// segment's pages. The reason it is split at all is that a stranger used to
/// type an email, a password AND a phone number before the product had
/// produced one single thing of its own; the two beats that ask for nothing
/// sit in front of the door and the three that need an account stay behind it.
/// Which segment shows on which launch is `FirstRunRoute.decide`, and the
/// microphone beat may never be moved into `.intro` — `heard` pushes live
/// before it queues, so that is a stranger's room on the server, not a demo.
///
/// The pages do not swipe between beats. Each beat is committed with its own
/// control, and the page turn is a slide on the app's slow spring. Only the
/// tour's three pages swipe, because they are three views of one idea.
struct OnboardingView: View {
    @EnvironmentObject var session: AnticipySession
    /// Called the instant the last step is cleared. The CALLER writes the
    /// durable "this person has onboarded" flag and then plays the celebration
    /// over Home — see AnticipyApp.
    ///
    /// This used to be a `hasOnboarded = true` at the tail of a ~2.4s animation
    /// inside this view: anything that interrupted those seconds left the flag
    /// false, and the person did every step again on the next launch.
    /// Recording the fact and celebrating it are two different jobs.
    let onFinished: () -> Void

    /// WHICH BEATS THIS INSTANCE IS CARRYING. `.intro` is the two in front of
    /// the door, `.rest` is the three behind it, and `.whole` is all five for
    /// somebody who reached the tour without the introduction — a second
    /// person signing in on a handed-on phone. `AnticipyApp` picks one through
    /// `FirstRunRoute`.
    let segment: FirstRunSegment

    /// Whether the two pre-auth beats have been cleared on this device. Written
    /// HERE as well as by the caller, because the beat is cleared here and a
    /// durable fact belongs on the line that makes it true.
    @AppStorage(FirstRunOwnership.introKey) private var hasSeenIntro = false

    /// THE ABSOLUTE BEAT INDEX, in every segment. `.rest` starts at
    /// `Step.name` rather than at 0, which is what lets the progress bar stay a
    /// plain function of `step`.
    @State private var step: Int
    /// The step we were on before the last change, so leaving the name beat by
    /// ANY route saves what was typed on it.
    @State private var lastStep: Int

    init(segment: FirstRunSegment, onFinished: @escaping () -> Void) {
        self.segment = segment
        self.onFinished = onFinished
        _step = State(initialValue: segment.firstStep)
        _lastStep = State(initialValue: segment.firstStep)
    }

    // The tour
    @State private var tourPage = 0

    // Your name — and, only when the account is missing them, email and number
    @State private var firstName = ""
    @State private var email = ""
    @State private var phoneCode = DiallingCode.forThisPhone().trimmingCharacters(in: .whitespaces)
    @State private var phoneDigits = ""
    @State private var phoneSaved = false
    @State private var phoneSaveFailed = false
    @State private var savingPhone = false
    @State private var phoneSkipped = false
    @State private var detailsSaved = false
    @FocusState private var focus: OpenField?
    private enum OpenField { case firstName, email, phone }

    // May I listen?
    @State private var micAsked = false
    @State private var micWanted = false
    @State private var notificationsWanted = false
    @State private var showingPromises = false

    // Your computer. Pairing itself — the six-digit ceremony — lives in
    // Settings; this beat only hands the setup pages to the right machine.
    @AppStorage("backendURL") private var backendURL = "https://api.anticipy.ai"

    /// The voice invite, raised once the walkthrough is cleared. Raised only
    /// when `EnrollmentOfferPolicy` says it can work; on the shipping build
    /// sherpa-onnx is unlinked and this stays false forever.
    @State private var inviting = false

    /// Five beats, and they live in `FirstRunRoute.swift` — the routing has to
    /// name them too, and Foundation-only is what lets the launch states be
    /// walked without a simulator.
    private typealias Step = FirstRunBeat

    var body: some View {
        ZStack {
            OnboardTheme.ground.ignoresSafeArea()
            VStack(spacing: 0) {
                // NO NUMBER IS HONEST IN FRONT OF THE DOOR, so no bar is shown
                // there. `FirstRunSegment.showsTrack` carries the derivation;
                // the second clause keeps the bar off the two pre-auth pages
                // when `.whole` carries them behind the door as well.
                if segment.showsTrack, step >= Step.name {
                    StepperHeader(progress: progress,
                                  spokenLabel: FirstRunTrack.spokenLabel(step: step, pageCount: Step.count))
                        .opacity(step == Step.welcome ? 0 : 1)
                        .accessibilityHidden(step == Step.welcome)
                        .transition(.opacity)
                }
                ZStack {
                    // The pages this segment carries, and only those. A
                    // `micPrimer` rendered in `.intro` is not a cosmetic
                    // mistake — it is a microphone in front of an account,
                    // and `heard` pushes live before it queues.
                    ForEach(segment.pages, id: \.self) { beat in
                        if beat == step {
                            page(beat)
                                .transition(.asymmetric(
                                    insertion: .move(edge: .trailing).combined(with: .opacity),
                                    removal: .move(edge: .leading).combined(with: .opacity)))
                        }
                    }
                }
                .animation(Theme.springSlow, value: step)
            }
        }
        .overlay(alignment: .bottom) { footer }
        // Leaving the name beat by ANY route — the arrow, the opt-out — saves
        // what was typed on it.
        .onChange(of: step) { newStep in
            Haptics.pageTurn()
            let previous = lastStep
            lastStep = newStep
            guard previous == Step.name, newStep != Step.name else { return }
            savePhoneOnLeaving()
        }
        // The switch starts and stops listening; the arrow is the only thing
        // that ends the beat. Flipping it off re-arms the ask, so a second
        // "on" asks again rather than falling through to the finish.
        .onChange(of: micWanted) { on in
            guard step == Step.mic else { return }
            if on {
                askForMicrophone()
            } else {
                if session.listener.isListening { session.stopListening() }
                micAsked = false
            }
        }
        .onChange(of: notificationsWanted) { on in
            guard step == Step.mic, on else { return }
            Task {
                await session.notifier.askIfNeeded()
                // iOS said no, or said no once before: the switch may not
                // stay on over nothing.
                if !session.notifier.authorized {
                    withAnimation(Theme.spring) { notificationsWanted = false }
                }
            }
        }
        .onChange(of: session.listener.isListening) { on in
            // Mirror the fact into the switch without treating it as a flip.
            if step == Step.mic, micWanted != on { micWanted = on }
        }
        .sheet(isPresented: $showingPromises) { promises }
        // ENROLMENT, OFFERED AT LAST. Whichever way it ends, onFinished() runs:
        // nothing about learning a voice may be able to strand somebody outside
        // the app.
        .fullScreenCover(isPresented: $inviting) {
            EnrollmentInvite(onDone: {
                inviting = false
                onFinished()
            })
            .environmentObject(session)
        }
    }

    /// The bar counts beats BEHIND you over the six the track names, the
    /// account included — so the name beat sits at three of six whichever way
    /// the person arrived at it.
    private var progress: Double {
        Double(FirstRunTrack.ordinal(step: step, pageCount: Step.count) - 1)
            / Double(FirstRunTrack.count)
    }

    /// One beat by its absolute index. `default` is unreachable while
    /// `FirstRunSegment.pages` only ever holds these five, which
    /// `run_first_run_route_tests.sh` asserts along with `FirstRunBeat.count`.
    @ViewBuilder
    private func page(_ beat: Int) -> some View {
        switch beat {
        case Step.welcome:  welcome
        case Step.tour:     tour
        case Step.name:     yourName
        case Step.computer: computerSetup
        case Step.mic:      micPrimer
        default:            EmptyView()
        }
    }

    /// The last beat is cleared. Offer the voice invite if it can actually
    /// work, otherwise end the walkthrough exactly as it always did.
    @MainActor
    private func finish() {
        // IN FRONT OF THE DOOR, "the last beat is cleared" means the door is
        // next — not that first run is over. A voice-enrolment offer raised
        // here would be asking a stranger to record their voice for an account
        // that does not exist.
        guard segment.endsTheTour else {
            onFinished()
            return
        }
        if EnrollmentOfferPolicy.presents(
            engineAvailable: session.speakerTagger.available,
            hasOwnerProfile: session.speakerTagger.hasOwnerProfile) {
            inviting = true
            return
        }
        onFinished()
    }

    private func go(_ to: Int) {
        withAnimation(Theme.springSlow) { step = to }
    }

    /// The page after this one in THIS segment.
    private var nextPage: Int? {
        guard let i = segment.pages.firstIndex(of: step), i + 1 < segment.pages.count else { return nil }
        return segment.pages[i + 1]
    }

    // MARK: - Footer

    /// The floating footer for the three beats behind the door: nothing on the
    /// left (there is no going back to a beat already saved), a quiet link in
    /// the middle when the beat has an opt-out, the arrow on the right.
    @ViewBuilder private var footer: some View {
        switch step {
        case Step.name:
            OnboardFooter {
                HStack(spacing: 12) {
                    OnboardFABSpacer()
                    ZStack {
                        Color.clear.frame(height: 1)
                        // NAMES THE CONSEQUENCE, BECAUSE THAT IS WHAT THE
                        // CHOICE DOES: no number means no text messages. Only
                        // offered while the number box is open. Otherwise the
                        // quiet exit for somebody who will not give a name.
                        if showingPhoneField {
                            Button("Use in-app alerts only") { skipCurrentStep() }
                                .font(OnboardFont.helper)
                                .foregroundStyle(OnboardTheme.text2)
                                .accessibilityIdentifier("onboarding-skip")
                        } else if !nameCanContinue, !savingPhone {
                            Button("Not right now") { skipCurrentStep() }
                                .font(OnboardFont.helper)
                                .foregroundStyle(OnboardTheme.text2)
                                .accessibilityIdentifier("onboarding-skip")
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .animation(Theme.spring, value: nameCanContinue)
                    OnboardFAB(enabled: nameCanContinue, label: "Continue") {
                        Task { await advance() }
                    }
                }
            }
        case Step.computer:
            OnboardFooter {
                HStack(spacing: 12) {
                    OnboardFABSpacer()
                    Spacer()
                    OnboardFAB(label: "Continue") { Task { await advance() } }
                }
            }
        case Step.mic:
            // The switches carry the answer; the arrow finishes either way.
            OnboardFooter {
                HStack(spacing: 12) {
                    OnboardFABSpacer()
                    Spacer()
                    OnboardFAB(label: "Finish") { Task { await advance() } }
                }
            }
        default:
            EmptyView()
        }
    }

    /// Skip is explicit per beat instead of incrementing an arbitrary tag.
    @MainActor
    private func skipCurrentStep() {
        Haptics.engage()
        switch step {
        case Step.name:
            // Save anything they did provide, then take the same path as the
            // arrow.
            phoneSkipped = true
            savePhoneOnLeaving()
            if let next = nextPage { go(next) } else { finish() }
        default:
            assertionFailure("Only the name beat can be skipped")
        }
    }

    /// THE AFFIRMATIVE FLIP. iOS is asked for the microphone here and ONLY
    /// here, and only on the beat that explains it: never in front of the
    /// door, never from a switch being seeded, never from a widget URL
    /// arriving while somebody is typing their name. `heard` pushes live
    /// before it queues, so this gate is a safety property, not a preference.
    @MainActor
    private func askForMicrophone() {
        if step == Step.mic, !micAsked, !session.micBlocked, !session.listener.isListening {
            micAsked = true
            session.startListening()
        }
    }

    /// "Get started" on the welcome: past the tour, and on to whatever is
    /// next — the door in front of it, the name beat behind it.
    @MainActor
    private func skipTour() {
        Haptics.engage()
        if segment.endsTheTour {
            go(Step.name)
        } else {
            hasSeenIntro = true
            finish()
        }
    }

    @MainActor
    private func advance() async {
        Haptics.engage()

        // The microphone is never asked for from here: the switch on the
        // last beat does that through `askForMicrophone()`. The arrow only
        // ever moves on.

        // One profile checkpoint, not three optimistic fields. The flow
        // advances only after every non-empty fact is durably stored.
        if step == Step.name {
            savingPhone = true
            if showingPhoneField, !phoneSaved, session.e164(phone) != nil {
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
            // AND UNCHANGED IS ALREADY SAVED. Both boxes are seeded from the
            // account, so somebody who leaves the first-name box alone is not
            // re-sending facts already on their record — on a bad connection
            // that was a false failure on the last page of first run.
            let detailsChanged = first != session.ownerFirstName
                || mail != session.ownerEmail
            if !detailsSaved, detailsChanged, !first.isEmpty || !mail.isEmpty {
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

        // THIS SEGMENT'S LAST PAGE, not the fifth beat: in `.intro` the tour
        // is the last page and Continue must walk to the door, not to a page
        // this segment does not carry.
        if step < segment.lastStep, let next = nextPage {
            go(next)
        } else {
            // THE DURABLE FACT FIRST, then anything decorative. Clearing the
            // last page of `.intro` is what "they have been introduced"
            // MEANS, and it is written synchronously here. AND ONLY THERE: in
            // the two segments that END the tour the caller writes both flags
            // on consecutive lines, and writing this one first re-routes
            // `.whole` to `.rest` under a live view.
            if !segment.endsTheTour { hasSeenIntro = true }
            finish()
        }
    }

    @MainActor
    private func savePhoneOnLeaving() {
        // Name and email save INDEPENDENTLY of the number.
        let first = firstName.trimmingCharacters(in: .whitespaces)
        let mail = email.trimmingCharacters(in: .whitespaces)
        let detailsChanged = first != session.ownerFirstName || mail != session.ownerEmail
        if !detailsSaved, detailsChanged, !first.isEmpty || !mail.isEmpty {
            Task {
                let ok = await session.saveOwnerDetails(first: first, last: "", email: mail)
                if ok { detailsSaved = true }
            }
        }
        guard showingPhoneField, !phoneSaved, !savingPhone, session.e164(phone) != nil else { return }
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
                if !phoneSkipped { go(Step.name) }
            }
        }
    }

    /// Every beat behind the door scrolls, because at accessibility sizes a
    /// beat that cannot scroll is a beat with its bottom cut off.
    private func stepBody<Content: View>(
        spacing: CGFloat = 16,
        @ViewBuilder content: @escaping () -> Content
    ) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: spacing) {
                content()
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, OnboardMetric.gutter)
            .padding(.top, 34)
            .padding(.bottom, OnboardMetric.footerClearance)
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private func question(_ text: String) -> some View {
        Text(text)
            .font(OnboardFont.question())
            .tracking(-0.6)
            .foregroundStyle(OnboardTheme.ink)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func lead(_ text: String, muted: Bool = false) -> some View {
        Text(text)
            .font(OnboardFont.body)
            .lineSpacing(4)
            .foregroundStyle(muted ? OnboardTheme.muted : OnboardTheme.text2)
            .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: - Welcome

    @State private var welcomeStage = 0

    private static let welcomeLine =
        "Capture conversations, keep track of commitments, and turn them into follow-ups."

    /// Warm light, the mark in white, the one sentence, and two pills.
    private var welcome: some View {
        ZStack {
            WelcomeAtmosphere()
            VStack(spacing: 16) {
                OnboardMark(size: 48, stroke: .white, dot: OnboardTheme.dot)
                    .shadow(color: .black.opacity(0.35), radius: 18, y: 6)
                    .scaleEffect(welcomeStage >= 1 ? 1 : 0.7)
                Text(Self.welcomeLine)
                    .font(.system(size: 21, weight: .medium))
                    .lineSpacing(4)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.white)
                    .shadow(color: .black.opacity(0.35), radius: 14, y: 2)
                    .fixedSize(horizontal: false, vertical: true)
                    .opacity(welcomeStage >= 2 ? 1 : 0)
                    .offset(y: welcomeStage >= 2 ? 0 : 10)
            }
            .padding(.horizontal, 44)
            .opacity(welcomeStage >= 1 ? 1 : 0)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .offset(y: -50)
            VStack(spacing: 10) {
                Button("Take a quick tour") {
                    Haptics.engage()
                    tourPage = 0
                    go(Step.tour)
                }
                .buttonStyle(.onboardWhite)
                Button("Get started") { skipTour() }
                    .buttonStyle(.onboardBlack)
            }
            .padding(.horizontal, OnboardMetric.gutter)
            .padding(.bottom, 22)
            .opacity(welcomeStage >= 3 ? 1 : 0)
            .offset(y: welcomeStage >= 3 ? 0 : 16)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottom)
        }
        .ignoresSafeArea(edges: .top)
        .task {
            guard welcomeStage == 0 else { return }
            withAnimation(Theme.springSlow) { welcomeStage = 1 }
            Haptics.herMessage()
            try? await Task.sleep(nanoseconds: 320_000_000)
            withAnimation(Theme.spring) { welcomeStage = 2 }
            try? await Task.sleep(nanoseconds: 260_000_000)
            withAnimation(Theme.spring) { welcomeStage = 3 }
        }
    }

    // MARK: - Tour

    private static let tourHeadlines = [
        "Capture every conversation",
        "Keep track of commitments",
        "And turn them into follow-ups",
    ]

    /// Three pages, one idea each: a framed scene, a headline, the dots, and
    /// the same commit pill under all of them.
    private var tour: some View {
        GeometryReader { geo in
            // The scene is drawn at 314×370 and scaled down only when the
            // phone is too short to hold it, so a small phone gets the same
            // composition rather than a cropped one. The chrome reserved is
            // what is actually there: the top inset, the headline and its
            // gap (three lines at the largest default size), dots, pill.
            let chrome: CGFloat = 90 + 56 + 84 + 36 + 72
            let scale = min(1, max(0.62, (geo.size.height - chrome) / 370))
            VStack(spacing: 0) {
                TabView(selection: $tourPage) {
                    ForEach(0 ..< 3, id: \.self) { i in
                        VStack(spacing: 0) {
                            Group {
                                switch i {
                                case 0: TourTranscriptHero(on: tourPage == 0)
                                case 1: TourCommitmentsHero(on: tourPage == 1)
                                default: TourNotificationHero(on: tourPage == 2)
                                }
                            }
                            .scaleEffect(scale)
                            .frame(width: 314 * scale, height: 370 * scale)
                            Text(Self.tourHeadlines[i])
                                .font(OnboardFont.question())
                                .tracking(-0.6)
                                .foregroundStyle(OnboardTheme.ink)
                                .multilineTextAlignment(.center)
                                .fixedSize(horizontal: false, vertical: true)
                                .frame(minHeight: 84, alignment: .top)
                                .padding(.top, 56 * scale)
                                .padding(.horizontal, 24)
                            Spacer(minLength: 0)
                        }
                        .frame(maxWidth: .infinity)
                        .tag(i)
                    }
                }
                .tabViewStyle(.page(indexDisplayMode: .never))
                .padding(.top, 90 * scale)
                .onChange(of: tourPage) { _ in Haptics.pageTurn() }
                PagerDots(count: 3, index: tourPage) { i in
                    withAnimation(Theme.spring) { tourPage = i }
                }
                .padding(.bottom, 36)
                Button("Get started") { Task { await advance() } }
                    .buttonStyle(.onboardBlack)
                    .padding(.horizontal, OnboardMetric.gutter)
                    .padding(.bottom, 22)
            }
        }
    }

    // MARK: - Your name

    /// Held only if it is a number she could actually text. `ownerPhone` is
    /// written as E.164 everywhere the app writes it, but it is also read back
    /// off the server on sign-in, and "I have your number" over something
    /// `e164` refuses is the same false confidence in a friendlier voice.
    private var hasStoredPhone: Bool { session.e164(session.ownerPhone) != nil }
    private var hasStoredEmail: Bool { !session.ownerEmail.isEmpty }
    /// A box is open only when there is nothing on file for it. The facts the
    /// account already holds are not asked for again.
    private var showingEmailField: Bool { !hasStoredEmail }
    private var showingPhoneField: Bool { !hasStoredPhone }
    private var phone: String { "\(phoneCode) \(phoneDigits)" }

    private var nameCanContinue: Bool {
        guard !savingPhone else { return false }
        let first = firstName.trimmingCharacters(in: .whitespaces)
        guard !first.isEmpty else { return false }
        if showingEmailField, !email.contains("@") { return false }
        return true
    }

    /// WHAT IT SAYS ABOUT THEM IS CHECKED, NEVER ASSUMED. `ConfirmBeat` at the
    /// foot of this file builds the sentence out of what is actually on file,
    /// so there is no path where this page claims an email or a number it does
    /// not have. Ordinarily both are on file from the door and the only thing
    /// asked for is a first name — the one fact she cannot work out.
    private var yourName: some View {
        stepBody {
            question(hasStoredEmail && hasStoredPhone
                     ? "What's your name?"
                     : ConfirmBeat.title(hasEmail: hasStoredEmail, hasPhone: hasStoredPhone))
            QuestionField(label: "First name", text: $firstName, placeholder: "First name",
                          kind: .givenName, focus: $focus, tag: .firstName,
                          submit: showingEmailField || showingPhoneField ? .next : .done) {
                if showingEmailField { focus = .email }
                else if showingPhoneField { focus = .phone }
                else if nameCanContinue { Task { await advance() } }
            }
            .onChange(of: firstName) { _ in detailsSaved = false; phoneSaveFailed = false }

            if showingEmailField {
                QuestionField(label: "Email", text: $email, placeholder: "you@email.com",
                              kind: .email, focus: $focus, tag: .email,
                              submit: showingPhoneField ? .next : .done) {
                    if showingPhoneField { focus = .phone } else if nameCanContinue { Task { await advance() } }
                }
                .onChange(of: email) { _ in detailsSaved = false; phoneSaveFailed = false }
            }

            if showingPhoneField {
                HStack(spacing: 8) {
                    CountryCodeBox(code: $phoneCode)
                    QuestionField(label: "Phone number", text: $phoneDigits, placeholder: "Phone number",
                                  kind: .phone, focus: $focus, tag: .phone, submit: .done) {
                        if nameCanContinue { Task { await advance() } }
                    }
                }
                .onChange(of: phoneDigits) { value in
                    let digits = String(value.filter(\.isNumber).prefix(14))
                    if digits != value { phoneDigits = digits }
                    phoneSaved = false
                    phoneSaveFailed = false
                }
                // The four things this field can say, in the app's own words —
                // the refusal sentence is FieldCaption's, one copy for every
                // screen that takes a number.
                if phoneSaved {
                    OnboardHelper(text: "Saved. Texts and in-app alerts are on.", satisfied: true)
                } else if session.e164(phone) != nil {
                    OnboardHelper(text: "That's you", satisfied: true)
                } else if !phoneDigits.isEmpty {
                    OnboardHelper(text: "That doesn't look like a full number yet — country code and all.")
                } else {
                    OnboardHelper(text: "A number I can text, country code and all")
                }
            }

            // The ordinary path — email and number on file, no name yet —
            // says the one thing that is missing and why. Anything less
            // ordinary is built by `ConfirmBeat` from what is actually held.
            OnboardHelper(text: hasStoredEmail && hasStoredPhone && session.ownerFirstName.isEmpty
                          ? "The one thing I'm missing is your first name — \(ConfirmBeat.bookingForm)."
                          : ConfirmBeat.lead(hasEmail: hasStoredEmail,
                                             hasPhone: hasStoredPhone,
                                             hasFirstName: !session.ownerFirstName.isEmpty),
                          lock: true)

            if phoneSaveFailed {
                OnboardCard {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("I couldn't save that just now. I need a connection to keep it. Everything you entered is still here.")
                            .font(OnboardFont.helper)
                            .lineSpacing(3)
                            .foregroundStyle(OnboardTheme.text2)
                            .fixedSize(horizontal: false, vertical: true)
                        Button("Try again") { Task { await advance() } }
                            .buttonStyle(.onboardSoft)
                            .disabled(savingPhone)
                    }
                }
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
            if savingPhone {
                OnboardStatus(text: "Saving…")
            }
        }
        // SEEDED HERE, NOT ON THE BOXES: two of the boxes are conditional, so
        // a seed left on them would never run for the person whose facts are
        // already on file — which is everybody this beat is for.
        .task {
            if firstName.isEmpty { firstName = session.ownerFirstName }
            if email.isEmpty { email = session.ownerEmail }
            // AND IT IS ALREADY SAVED, so say so to the one thing that asks:
            // `advance()` otherwise re-sends the number on every first run.
            phoneSaved = hasStoredPhone
        }
        .task(id: step) {
            guard step == Step.name else { return }
            try? await Task.sleep(nanoseconds: 450_000_000)
            focus = .firstName
        }
        // The phone pad has no return key, so the commit sits above it.
        .toolbar {
            PhonePadDoneBar(label: nameCanContinue ? "Continue" : "Done",
                            enabled: true) {
                if nameCanContinue, focus == .phone { Task { await advance() } } else { focus = nil }
            }
        }
        .animation(Theme.spring, value: phoneSaveFailed)
        .animation(Theme.spring, value: savingPhone)
    }

    // MARK: - Your computer

    /// One optional beat, two hosted destinations. The phone does not pretend
    /// it can install either computer surface: Open lets somebody inspect the
    /// guide, and Send uses iOS's own share sheet.
    private var computerSetup: some View {
        stepBody {
            question("Your computer")
            lead("Send each setup to the computer where you’ll use it. You can do either one now or come back in Settings.")
            browserHandoffCard
            macHandoffCard
        }
    }

    private var browserHandoffCard: some View {
        OnboardCard {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 10) {
                    Image(systemName: session.agentPaired ? "checkmark.circle.fill" : "safari")
                        .font(.system(size: 19, weight: .medium))
                        .foregroundStyle(session.agentPaired ? OnboardTheme.champagneInk : OnboardTheme.ink)
                        .frame(width: 24)
                        .accessibilityHidden(true)
                    Text("Browser")
                        .font(.system(size: 19, weight: .semibold))
                        .foregroundStyle(OnboardTheme.ink)
                    Spacer(minLength: 8)
                    Text(session.agentPaired ? "Connected" : "Not connected")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(OnboardTheme.muted)
                }
                Text("The setup page installs the Chrome extension, shows your six-digit code, and confirms when this browser is linked.")
                    .font(.system(size: 15.5))
                    .lineSpacing(3)
                    .foregroundStyle(OnboardTheme.text2)
                    .fixedSize(horizontal: false, vertical: true)
                if let url = ComputerSetupLinks.browser(baseURL: backendURL) {
                    HStack(spacing: 8) {
                        Link("Open browser setup", destination: url)
                            .buttonStyle(.onboardSoft)
                        ShareLink(item: url,
                                  subject: Text("Set up Anticipy in Chrome"),
                                  message: Text("Open this on your computer to connect Anticipy to Chrome.")) {
                            Text("Send to computer")
                        }
                        .buttonStyle(.onboardSoft)
                    }
                    .padding(.top, 4)
                }
            }
        }
    }

    private var macHandoffCard: some View {
        OnboardCard {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 10) {
                    Image(systemName: "laptopcomputer")
                        .font(.system(size: 19, weight: .medium))
                        .foregroundStyle(OnboardTheme.ink)
                        .frame(width: 24)
                        .accessibilityHidden(true)
                    Text("Mac app")
                        .font(.system(size: 19, weight: .semibold))
                        .foregroundStyle(OnboardTheme.ink)
                    Spacer(minLength: 8)
                    Text("Meeting recorder")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(OnboardTheme.muted)
                }
                Text("The Mac app records your microphone and meeting audio as separate local tracks, then syncs transcript text to this account.")
                    .font(.system(size: 15.5))
                    .lineSpacing(3)
                    .foregroundStyle(OnboardTheme.text2)
                    .fixedSize(horizontal: false, vertical: true)
                if let url = ComputerSetupLinks.mac(baseURL: backendURL) {
                    HStack(spacing: 8) {
                        Link("Open Mac setup", destination: url)
                            .buttonStyle(.onboardSoft)
                        ShareLink(item: url,
                                  subject: Text("Get Anticipy for Mac"),
                                  message: Text("Open this on your Mac to install Anticipy.")) {
                            Text("Send to Mac")
                        }
                        .buttonStyle(.onboardSoft)
                    }
                    .padding(.top, 4)
                }
            }
        }
    }

    // MARK: - May I listen?

    /// Whether this iPhone can turn speech into text without sending audio
    /// anywhere. Computed live, never cached: on-device speech support FLIPS
    /// when iOS finishes downloading the recognition assets, and a static let
    /// froze the answer at process start.
    private var keepsAudioOnDevice: Bool {
        SFSpeechRecognizer(locale: Locale(identifier: "en_US"))?.supportsOnDeviceRecognition ?? false
    }

    /// The last beat: two cards with a switch each, the promise under them,
    /// and the whole page ends with the arrow. Flipping the microphone on is
    /// the affirmative — iOS asks the moment it is flipped, on this page,
    /// with the reason still on screen.
    private var micPrimer: some View {
        stepBody {
            question("May I listen?")
            lead("Anticipy uses your microphone only while listening is on.", muted: true)

            if session.micBlocked {
                OnboardCard(fill: OnboardTheme.warnCard) {
                    VStack(alignment: .leading, spacing: 10) {
                        Text("iOS has my microphone switched off. I can't ask again from here. It's one tap in Settings, under Microphone and Speech Recognition.")
                            .font(.system(size: 15.5))
                            .lineSpacing(3)
                            .foregroundStyle(OnboardTheme.text2)
                            .fixedSize(horizontal: false, vertical: true)
                        Button("Open Settings") {
                            Haptics.engage()
                            session.openSystemSettings()
                        }
                        .buttonStyle(.onboardSoft)
                    }
                }
            } else {
                PermissionCard(icon: "mic",
                               title: "Microphone",
                               text: Text("Nearby speech becomes text. This can include other people in the room, so ")
                                   + Text("let them know").fontWeight(.semibold).foregroundColor(OnboardTheme.ink)
                                   + Text(" when listening is on. It stays on until you stop or pause it from the app.")) {
                    OnboardToggle(label: "Microphone", isOn: $micWanted)
                }
            }

            PermissionCard(icon: "bell",
                           title: "Notifications",
                           text: Text("Work that needs you: a booking waiting on your OK, a result to check. This adds a nudge when the app is closed.")) {
                OnboardToggle(label: "Notifications", isOn: $notificationsWanted)
            }

            if session.listener.isListening {
                HStack(spacing: 8) {
                    BreathingDot(size: 8)
                    Text("Listening is on.")
                        .font(.callout.weight(.semibold))
                        .foregroundStyle(OnboardTheme.champagneInk)
                }
                .transition(.scale.combined(with: .opacity))
            } else if !session.micBlocked {
                Text("When you say yes, iOS asks twice, once for speech, once for the microphone. Both are me.")
                    .font(OnboardFont.helper)
                    .lineSpacing(3)
                    .foregroundStyle(OnboardTheme.text2)
                    .fixedSize(horizontal: false, vertical: true)
            }

            VStack(spacing: 6) {
                Text(keepsAudioOnDevice
                     ? "Microphone audio is turned into text on this iPhone, then the text is sent to Anticipy's server so it can create and complete work."
                     : "This iPhone may use Apple's speech service to turn microphone audio into text. Anticipy then sends the text—not an audio recording—to its server so it can create and complete work.")
                    .font(.system(size: 14.5))
                    .lineSpacing(3)
                    .foregroundStyle(OnboardTheme.muted)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                Button("Learn more") {
                    Haptics.tap()
                    showingPromises = true
                }
                .font(.system(size: 14.5, weight: .semibold))
                .foregroundStyle(OnboardTheme.ink)
                .underline()
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 4)
        }
        .animation(Theme.spring, value: session.listener.isListening)
        .animation(Theme.spring, value: session.micBlocked)
        .onAppear {
            // Seed both switches from the facts. A phone already listening
            // has already been asked, so the seed must not re-enter the ask.
            micWanted = session.listener.isListening
            if micWanted { micAsked = true }
            notificationsWanted = session.notifier.authorized
        }
    }

    /// What listening costs, and the receipt for it — the five promises, one
    /// tap behind "Learn more". Every clause of the last one names a row that
    /// exists in `ListeningDiagnosticsView`, reached from Settings' "Find out
    /// what listening actually did".
    private var promises: some View {
        ZStack {
            OnboardTheme.ground.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    question("What listening means")
                    promiseLine(title: "Nearby speech becomes text",
                                text: "This can include other people in the room, so let them know when listening is on.")
                    promiseLine(title: "Listening can continue in the background",
                                text: "It stays on until you stop or pause it from the app.")
                    promiseLine(title: keepsAudioOnDevice ? "Audio stays on this iPhone" : "Apple provides speech recognition on this iPhone",
                                text: keepsAudioOnDevice
                                   ? "Anticipy sends the resulting text to its server to create follow-ups."
                                   : "Audio is handled by Apple for transcription. Anticipy receives the resulting text.")
                    promiseLine(title: "You control listening",
                                text: "Listening starts only after you turn it on. Stop and pause controls are always available in Settings.")
                    promiseLine(title: "Review usage and activity",
                                text: "Settings shows listening time, battery use, starts, stops, and silent periods.")
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 22)
                .padding(.top, 34)
                .padding(.bottom, 40)
            }
        }
        .presentationDetents([.medium, .large])
    }

    private func promiseLine(title: String, text: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(OnboardTheme.ink)
            Text(text)
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(OnboardTheme.text2)
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - The two decisions this walkthrough makes about words

/// Which beat you are on, out of how many — counting the one that already
/// happened.
///
/// PURE, and lifted out of this file by `run_first_run_copy_tests.sh` rather
/// than copied into it. This is the arithmetic behind the progress bar of the
/// highest-stakes flow in the product, and an off-by-one here misplaces the
/// bar under a person's thumb. It has to be answerable without a simulator.
///
/// THE ACCOUNT IS NOT A PAGE IN THIS VIEW. It is the door, cleared before
/// `OnboardingView` exists. Counting it is the entire point: the bar used to
/// open at nothing over somebody who had just typed an email, a password and a
/// phone number, and told them they were at the start.
///
/// Every index goes through `index(step:pageCount:)`, which CLAMPS. A beat
/// added without a name would otherwise be a subscript out of range — a
/// crash, on a stranger's first run, from a copy change.
enum FirstRunTrack {
    static let beatNames = ["Your account", "Hello", "How I work",
                            "Your name", "Your computer", "May I listen?"]

    static var count: Int { beatNames.count }

    /// How many beats are behind somebody standing on this view's first page.
    static func offset(pageCount: Int) -> Int {
        max(0, beatNames.count - max(0, pageCount))
    }

    static func index(step: Int, pageCount: Int) -> Int {
        min(max(0, step + offset(pageCount: pageCount)), beatNames.count - 1)
    }

    static func name(step: Int, pageCount: Int) -> String {
        beatNames[index(step: step, pageCount: pageCount)]
    }

    static func ordinal(step: Int, pageCount: Int) -> Int {
        index(step: step, pageCount: pageCount) + 1
    }

    /// "Step N of M" is what a screen-reader user needs; the beat name is what
    /// the bar adds for everyone else. Built here so the spoken count and the
    /// drawn bar cannot drift apart.
    static func spokenLabel(step: Int, pageCount: Int) -> String {
        "Step \(ordinal(step: step, pageCount: pageCount)) of \(count), "
            + name(step: step, pageCount: pageCount)
    }
}

/// What the name beat may honestly say it already has.
///
/// The sentence is BUILT from what is on file. Pure, and lifted by
/// `run_first_run_copy_tests.sh`, because "is this claim true" is a decision
/// and decisions belong where they can be read without a screen.
///
/// It reads the STORED facts, never the live fields. A lead paragraph that
/// rewrote itself under somebody's thumb as they typed their first name would
/// be a worse screen than either version of it.
enum ConfirmBeat {
    /// A page claiming "This is what I have." while holding nothing is the same
    /// class of falsehood one register quieter, so with nothing on file the
    /// beat asks its old question instead.
    static func title(hasEmail: Bool, hasPhone: Bool) -> String {
        (hasEmail || hasPhone) ? "This is what I have." : "Where should I reach you?"
    }

    /// Why a name and not something she can work out: every booking form asks
    /// for one, and with none on file she fills the blank rather than admitting
    /// it. That is the argument the beat has carried since it shipped.
    static let bookingForm = "it's what a booking form asks for that I can't work out"

    static func lead(hasEmail: Bool, hasPhone: Bool, hasFirstName: Bool) -> String {
        let held: String?
        switch (hasEmail, hasPhone) {
        case (true, true):   held = "Your email and number are already on your account."
        case (true, false):  held = "Your email is already on your account."
        case (false, true):  held = "Your number is already on your account."
        case (false, false): held = nil
        }
        return [held, stillNeeded(hasEmail: hasEmail,
                                  hasPhone: hasPhone,
                                  hasFirstName: hasFirstName),
                reachChannel(hasPhone: hasPhone)]
            .compactMap { $0 }
            .joined(separator: " ")
    }

    /// The account can exist without a number, so the consequence of that
    /// choice belongs on the choice screen.
    static func reachChannel(hasPhone: Bool) -> String {
        hasPhone
            ? "I'll use text messages and in-app alerts."
            : "Without a number, approvals and results stay in the app. Add one later if you want text messages too."
    }

    /// "The one thing I'm missing" is only allowed to be said when one thing is
    /// missing. It is the whole reason this is a function rather than a string.
    static func stillNeeded(hasEmail: Bool, hasPhone: Bool, hasFirstName: Bool) -> String {
        var missing: [String] = []
        if !hasFirstName { missing.append("your first name") }
        if !hasEmail { missing.append("your email") }
        if !hasPhone { missing.append("a number to text you on") }
        switch missing.count {
        case 0:
            return "Have a look before we start."
        case 1 where !hasFirstName:
            return "The one thing I'm missing is your first name — \(bookingForm)."
        case 1:
            return "The one thing I'm missing is \(missing[0])."
        default:
            let list = missing.dropLast().joined(separator: ", ")
                + " and " + (missing.last ?? "")
            return "I still need \(list)."
        }
    }
}
