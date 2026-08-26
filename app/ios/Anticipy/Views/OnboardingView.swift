import SwiftUI
import Speech

/// First-run walkthrough: welcome → how it works → may I listen → where to
/// reach you — and the sign-in door now stands between the second and the
/// third of them.
///
/// This view is instantiated with a `FirstRunSegment` and carries only that
/// segment's pages. The reason it is split at all is that a stranger used to
/// type an email, a password AND a phone number before the product had
/// produced one single thing of its own; the two beats that ask for nothing
/// moved in front of the door and the two that need an account stayed behind
/// it. Which segment shows on which launch is `FirstRunRoute.decide`, and the
/// microphone beat may never be moved into `.intro` — `heard` pushes live
/// before it queues, so that is a stranger's room on the server, not a demo.
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

    /// WHICH BEATS THIS INSTANCE IS CARRYING. The walkthrough is split across
    /// the sign-in door now: `.intro` is the two beats in front of it, `.rest`
    /// is the two behind it, and `.whole` is all four for somebody who reached
    /// the tour without the introduction — a second person signing in on a
    /// handed-on phone. `AnticipyApp` picks one through `FirstRunRoute`.
    let segment: FirstRunSegment

    /// Whether the two pre-auth beats have been cleared on this device. Written
    /// HERE as well as by the caller, because the beat is cleared here and a
    /// durable fact belongs on the line that makes it true rather than at the
    /// tail of whatever animation happens to follow.
    @AppStorage(FirstRunOwnership.introKey) private var hasSeenIntro = false

    /// THE ABSOLUTE BEAT INDEX, in every segment. `.rest` starts at
    /// `Step.mic` = 2 rather than at 0, which is what lets the progress track
    /// stay a plain function of `step` and lets every `Step.x` comparison in
    /// this file keep meaning what it meant.
    @State private var step: Int
    /// The step we were on before the last change, so a *swipe* off the number
    /// step can save it too. Only the Continue button ever used to save.
    ///
    /// SEEDED FROM THE SAME PLACE AS `step`. Left at 0 in `.rest` it would
    /// record a `previous` that nobody was ever on; that cannot produce a
    /// wrong save today, because only `previous == Step.phone` matters and
    /// 0 is not 3, but it is a wrong value one edit away from mattering.
    @State private var lastStep: Int

    init(segment: FirstRunSegment, onFinished: @escaping () -> Void) {
        self.segment = segment
        self.onFinished = onFinished
        _step = State(initialValue: segment.firstStep)
        _lastStep = State(initialValue: segment.firstStep)
    }

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
    /// Whether the person has asked to change a fact she already holds. Both
    /// start false: the number beat is a confirmation now, and a confirmation
    /// that opens with every box already open is the interrogation it replaced.
    @State private var editingEmail = false
    @State private var editingPhone = false
    @FocusState private var focus: OpenField?
    private enum OpenField { case firstName, email, phone }

    // Microphone
    @State private var micAsked = false

    /// The voice invite, raised once the four beats are cleared. NOT a fifth
    /// beat: `design/day-zero.md:237-239` already removed one page from this
    /// walkthrough for exceeding the ~70-second budget, so the four keep their
    /// names, their count and their progress track, and this is a screen after
    /// them rather than inside them.
    ///
    /// Raised only when `EnrollmentOfferPolicy` says it can work. On the
    /// shipping build sherpa-onnx is unlinked, `SpeakerTagger.available` is
    /// false, and this stays false forever — first run costs a stranger nothing
    /// it cannot pay back. See EnrollmentInvite for the whole argument.
    @State private var inviting = false

    /// Four beats, and they live in `FirstRunRoute.swift` now — the routing
    /// has to name them too, and Foundation-only is what lets the six launch
    /// states be walked without a simulator. The alias is what keeps every
    /// `Step.mic`, `.tag(Step.phone)` and `step += 1` in this file untouched.
    ///
    /// The browser was a fifth beat until `design/day-zero.md` took it out of
    /// first run; nothing here may exceed the ~70-second budget in
    /// `CONSUMER-FEEL-DIRECTION-2026-08-03.md` §5.
    private typealias Step = FirstRunBeat

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()
            VStack(spacing: 0) {
                // NO NUMBER IS HONEST IN FRONT OF THE DOOR, so no number is
                // shown there. On how-it-works pre-auth the person has one
                // beat behind them, and the track's rule is that it never
                // opens at 1; the other available number, the absolute
                // "3 of 5", counts an account nobody has made yet. Both
                // permitted numbers are forbidden. `FirstRunSegment.showsTrack`
                // carries the derivation so it can be read without a screen.
                //
                // This does NOT replace the opacity modifier inside
                // `progressTrack`. That one is about `.whole`, where welcome
                // is a real page and must still not be counted. Two
                // mechanisms, two different reasons, both needed.
                if segment.showsTrack {
                    progressTrack
                }
                TabView(selection: $step) {
                    // The pages this segment carries, and only those. A
                    // `micPrimer` rendered in `.intro` is not a cosmetic
                    // mistake — it is a microphone in front of an account,
                    // and `heard` pushes live before it queues.
                    ForEach(segment.pages, id: \.self) { beat in
                        page(beat).tag(beat)
                    }
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
        // ENROLMENT, OFFERED AT LAST. Until this existed the app presented
        // VoiceEnrollView from exactly one place - a sheet three scrolls down
        // in Settings - and `speaker` sat at 0% across 221 production events
        // with the cause recorded as "enrollment unreachable".
        //
        // Whichever way it ends, onFinished() runs: nothing about learning a
        // voice may be able to strand somebody outside the app.
        .fullScreenCover(isPresented: $inviting) {
            EnrollmentInvite(onDone: {
                inviting = false
                onFinished()
            })
            .environmentObject(session)
        }
    }

    /// One beat by its absolute index. `default` is unreachable while
    /// `FirstRunSegment.pages` only ever holds these four, which
    /// `run_first_run_route_tests.sh` asserts along with `FirstRunBeat.count`
    /// — a fifth beat added to the indices and not to this switch goes red
    /// there rather than rendering a blank page on a stranger's first run.
    @ViewBuilder
    private func page(_ beat: Int) -> some View {
        switch beat {
        case Step.welcome:    welcome
        case Step.howItWorks: howItWorks
        case Step.mic:        micPrimer
        case Step.phone:      yourNumber
        default:              EmptyView()
        }
    }

    /// The last beat is cleared. Offer the voice invite if it can actually
    /// work, otherwise end the walkthrough exactly as it always did.
    ///
    /// The policy is asked here, once, rather than re-derived from
    /// `speakerTagger.available` at each of the two exits below - which is how
    /// two exits come to disagree about whether a tour is over.
    @MainActor
    private func finish() {
        // IN FRONT OF THE DOOR, "the last beat is cleared" means the door is
        // next — not that first run is over. A voice-enrolment offer raised
        // here would be asking a stranger to record their voice for an account
        // that does not exist. On the shipping build EnrollmentOfferPolicy
        // returns false anyway, because sherpa-onnx is unlinked and
        // `SpeakerTagger.available` is therefore false — but leaning on that
        // is accidental safety, and accidental safety is what this whole
        // change is about.
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


    /// Progress in one line: the beat you are on, and which of five it is.
    ///
    /// FIVE, BECAUSE THE ACCOUNT COUNTED. This opened at "1 of 4" over
    /// somebody who had just typed an email, a password and a phone number at
    /// the door and watched three rules turn champagne as they did it. Told
    /// they were at the start, with the hardest screen of first run already
    /// behind them, the count was not merely unflattering — it was wrong. The
    /// names and the arithmetic live in `FirstRunTrack` at the foot of this
    /// file, where they can be read without a simulator.
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
    ///
    /// -- THE INVARIANT THE NEXT AGENT WILL OTHERWISE "FIX" ---------------
    ///
    /// `pageCount` is ALWAYS `Step.count`, never `segment.pages.count`, and
    /// `step` is always the absolute beat index. So the microphone beat reads
    /// "May I listen?  4 of 5" whichever way the person got there, and that is
    /// true of both of them rather than a rounding error: the ordinal counts
    /// the beats BEHIND you, not a position in a fixed order. A fresh stranger
    /// arrives having done Hello, How I work and Your account; somebody whose
    /// tour replayed after a second person signed in arrives having done Your
    /// account, Hello and How I work. Three beats each, so four is right for
    /// each.
    ///
    /// `beatNames` is only ever RENDERED IN ORDER in `.whole`, where its order
    /// is the true one. No screen ever shows a name in an order that is false
    /// for the person reading it, which is why the array does not need — and
    /// must not get — a per-segment permutation.
    private var progressTrack: some View {
        HStack(alignment: .firstTextBaseline, spacing: Theme.Space.tight) {
            Text(FirstRunTrack.name(step: step, pageCount: Step.count))
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
            Text("\(FirstRunTrack.ordinal(step: step, pageCount: Step.count)) of \(FirstRunTrack.count)")
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
        .accessibilityLabel(FirstRunTrack.spokenLabel(step: step, pageCount: Step.count))
        // An element drawn at zero opacity that still announces its step is a
        // wizard for VoiceOver users only.
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
        // NAMES THE PAGE, BECAUSE IT DOES NOT SKIP. This read "Skip for now",
        // and "for now" promises a second pass that does not exist: the branch
        // below sets `phoneSkipped`, saves, and calls `finish()` — it ends
        // first run. All three fields on this beat really do live in Settings:
        // first name and email in its `Section("You")`, the number in its
        // `Section("Your number")`. So the honest label is the page, not the
        // delay.
        //
        // CITED BY SECTION NAME RATHER THAN LINE NUMBER, deliberately. This
        // comment used to give two line ranges in SettingsView, and both were
        // wrong on the day they were written — one landed on a status pill,
        // the other on a caption. The next agent checking whether this label
        // tells the truth would have found no fields there and reverted a
        // correct fix. Section titles are user-visible copy, they move with
        // their fields, and `run_first_run_copy_tests.sh` greps for them.
        case Step.phone: return "I'll do this in Settings."
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
                        finish()
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
            // AND UNCHANGED IS ALREADY SAVED — the same bug the number got a
            // guard for one branch up, left open here in the same function.
            // Both boxes are SEEDED from the account (`firstName` from
            // `session.ownerFirstName`, `email` from `session.ownerEmail`,
            // which `signIn` always writes), so somebody who signs in, leaves
            // the first-name box alone and taps "Start living your day" was
            // re-sending facts already on their record. On a good connection
            // that is a wasted round trip; on a bad one the `guard ok` below
            // holds them on the last page of first run under "I couldn't save
            // that just now" — over an email their account already has. A
            // false failure, and the last thing first run does.
            //
            // Compared at the point of sending rather than latched at seed
            // time like `phoneSaved`, because `.onChange(of: firstName)` fires
            // after this view's `.task` and would clear a flag set there.
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

        // THIS SEGMENT'S LAST PAGE, not the fourth beat. `Step.count - 1` is
        // 3, so in `.intro` how-it-works (1) is less than it and Continue used
        // to step to a page tagged 2 that this segment does not carry: a blank
        // screen, in front of the door, with no way forward. That dead end is
        // exactly what a routing-only version of this change produces.
        if step < segment.lastStep {
            withAnimation(Theme.spring) { step += 1 }
        } else {
            // THE DURABLE FACT FIRST, then anything decorative — the rule the
            // caller's own `onFinished` comment argues, applied one level
            // down. Clearing the last page of `.intro` is what "they have been
            // introduced" MEANS, and it is written synchronously here rather
            // than left to a closure that a torn-down view may never call.
            //
            // AND ONLY THERE, which is the guard rather than a tidy-up. In the
            // two segments that END the tour the caller writes both flags on
            // consecutive lines, and writing this one first opened a window
            // between them: `decide(hasSeenIntro: true, isSignedIn: true,
            // hasOnboarded: false)` is `.tour(.rest)`, so in `.whole` this line
            // changed `segment` under a live view while the person was still
            // standing on the number beat. Nothing broke, but only because
            // `.tour(.whole)` and `.tour(.rest)` land in the same
            // `case .tour(let segment):` arm and SwiftUI therefore kept the
            // @State `step` — view identity, not a guarantee, and the enrolment
            // invite below is raised from inside that window. Idempotent in
            // `.rest` by definition: nothing routes there without the flag
            // already set.
            if !segment.endsTheTour { hasSeenIntro = true }
            // The last step is cleared. Say so and let the caller write it
            // down; nothing about the celebration can strand anyone now.
            finish()
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

            // Five promises as a rule list — speech-shaped, not form-shaped.
            // Evenly spaced symbol-and-card rows are the most recognisable
            // AI-built layout there is, and this is where someone decides
            // whether to hand over their microphone. The count is not what
            // that argument is about; the treatment is.
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
            // THE COST, WITH THE RECEIPT FOR IT, at the moment of consent.
            // The largest cost in the product is stated two lines above this
            // one — "I keep going in the background" — with no bound on it, and
            // a reader with no anchor supplies their own worst case. The phone
            // has been measuring the real one all along and this screen never
            // said so.
            //
            // Every clause is a row that exists in `ListeningDiagnosticsView`:
            // "Battery used while listening", "Time spent listening" and "The
            // log" — reached from Settings' "Find out what listening actually
            // did", and that file ships in RELEASE deliberately ("SHIPS IN
            // RELEASE", in its own header) — a receipt only a debug build can
            // show is not a receipt. Each of those rows is grepped by
            // `run_first_run_copy_tests.sh`; the route is too.
            //
            // Named, not numbered. The line numbers this comment used to carry
            // for the Settings route were wrong on the day of writing.
            //
            // NO PERCENTAGE, AND NO "TODAY". Not a percentage because
            // `ListeningDiagnosticsView`'s "NO VERDICT" note states there is
            // not one recorded
            // drain figure in this repo to draw a line from, and an invented
            // number on the consent screen is what law 1 exists to stop. Not
            // "today" because it would not be true: `ListenTally.of` folds
            // every event still on disk and `ListenJournal` rotates on BYTES,
            // at 256KB, never at midnight — so on a quiet phone those rows
            // cover several days. The screen's "Today" heading is a heading,
            // not a window, and this sentence may not borrow a scope the
            // arithmetic underneath it does not have.
            promiseLine(title: "You can see exactly what I cost",
                        text: "Settings shows how much battery I used and how long I listened, and the log behind it. You don't have to take my word for it.")

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

    /// Held only if it is a number she could actually text. `ownerPhone` is
    /// written as E.164 everywhere the app writes it, but it is also read back
    /// off the server on sign-in, and "I have your number" over something
    /// `e164` refuses is the same false confidence in a friendlier voice.
    private var hasStoredPhone: Bool { session.e164(session.ownerPhone) != nil }
    private var hasStoredEmail: Bool { !session.ownerEmail.isEmpty }
    /// A box is open when there is nothing to confirm, or when they asked to
    /// change what there was.
    private var showingEmailField: Bool { !hasStoredEmail || editingEmail }
    private var showingPhoneField: Bool { !hasStoredPhone || editingPhone }

    /// THE CONFIRMATION THE REPO SPECIFIED TWO DOCUMENTS AGO, finally whole.
    ///
    /// `CONSUMER-FEEL-DIRECTION-2026-08-03.md:615-616` asked for this beat by
    /// name — "she has it from the door … the step becomes a confirmation, not
    /// a second interrogation" — and half of it shipped: the seed below, under
    /// a comment reading "Already told us at the door? Confirm, don't
    /// re-interrogate." The FRAMING half never did, so the page went on wearing
    /// a question over three identical open boxes, one of them holding an email
    /// address the person had never typed on this screen. The same doc at `:464`
    /// had already logged that as "the clearest possible evidence nobody walked
    /// the flow end to end".
    ///
    /// So the facts she already holds are shown as SETTLED, with the change
    /// affordance the spec itself wrote down — "I'll reach you at" and a quiet
    /// "Change it" — and the one thing she genuinely cannot work out is the
    /// only box left open.
    ///
    /// WHAT IT SAYS ABOUT THEM IS CHECKED, NEVER ASSUMED. `ConfirmBeat` at the
    /// foot of this file builds the sentence out of what is actually on file,
    /// so there is no path where this page claims an email or a number it does
    /// not have. It says "already on your account" rather than the more natural
    /// "came in at the door" for the same reason: on the sign-in path the
    /// number never came in at any door — `AnticipySession.signIn` reads it
    /// back off the account record into `ownerPhone` — and a confirmation
    /// screen that is wrong about where it got your number is worse than one
    /// that never mentioned it.
    ///
    /// (That parenthesis carried a line number until this pass, and the line
    /// number had already drifted onto the middle of an unrelated comment.)
    ///
    /// LEADING, like `howItWorks` and `micPrimer`. Centred prose was survivable
    /// over three identical boxes; over rows carrying a label, a value and a
    /// change affordance it is not, and the page was the odd one out of four.
    private var yourNumber: some View {
        stepBody(alignment: .leading, spacing: 18) {
            LogoMark(size: 72)
                .frame(maxWidth: .infinity)
                .accessibilityHidden(true)
            Text(ConfirmBeat.title(hasEmail: hasStoredEmail, hasPhone: hasStoredPhone))
                .font(Theme.display(30))
                .tracking(-0.5)
                .foregroundStyle(Theme.text)
                .fixedSize(horizontal: false, vertical: true)
            Text(ConfirmBeat.lead(hasEmail: hasStoredEmail,
                                  hasPhone: hasStoredPhone,
                                  hasFirstName: !session.ownerFirstName.isEmpty))
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.text2)
                .fixedSize(horizontal: false, vertical: true)

            if showingEmailField {
                TextField("you@example.com", text: $email)
                    .keyboardType(.emailAddress)
                    .textContentType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .font(.title3)
                    .foregroundStyle(Theme.text)
                    .focused($focus, equals: .email)
                    .padding(.vertical, 12)
                    .padding(.horizontal, 12)
                    .background(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous).fill(Theme.surface))
                    .overlay(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                        .strokeBorder(Theme.edge, lineWidth: 1))
                    // Opening a box and putting the cursor in it are one gesture
                    // to the person doing it. Gated on `editingEmail` so this
                    // fires only for a box they asked for: the TabView builds
                    // every page up front, so an ungated focus here would take
                    // the keyboard on the welcome screen.
                    .onAppear { if editingEmail { focus = .email } }
                    .onChange(of: email) { _ in detailsSaved = false; phoneSaveFailed = false }
            } else {
                confirmedRow(label: "Your email",
                             value: session.ownerEmail,
                             changeLabel: "Change your email") {
                    editingEmail = true
                }
            }

            if showingPhoneField {
                TextField("+1 604 555 0123", text: $phone)
                    .keyboardType(.phonePad)
                    .textContentType(.telephoneNumber)
                    .font(.title3.monospacedDigit())
                    .foregroundStyle(Theme.text)
                    .focused($focus, equals: .phone)
                    .padding(.vertical, 12)
                    .padding(.horizontal, 12)
                    .background(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous).fill(Theme.surface))
                    .overlay(
                        RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                            .strokeBorder(session.e164(phone) != nil ? Theme.accent : Theme.edge,
                                          lineWidth: session.e164(phone) != nil ? 1.5 : 1)
                            .animation(Theme.spring, value: session.e164(phone) != nil)
                    )
                    .onAppear { if editingPhone { focus = .phone } }
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
                    Text("That doesn't look like a full number yet — country code and all.")
                        .font(.system(size: 15))
                        .foregroundStyle(Theme.muted)
                }
            } else {
                // "I'll reach you at" is the spec's own wording, word for word.
                //
                // THE TREATMENT IS NOT THE SPEC'S, and saying so cost this
                // comment its previous sentence. The spec asks for "the number
                // in monospace"; what ships is `.title3.monospacedDigit()`,
                // which is not a monospaced face at all — it is the same system
                // font this whole flow already uses, with fixed-width DIGITS.
                // The standing constraint on this pass is no new font, so a
                // real monospaced face was not available to spend. Digits of
                // equal width are the part of the spec's intent that a phone
                // number actually needs: the number stops shuffling sideways
                // as it is typed or re-read. `.monospacedDigit()` is already
                // the idiom here — `AuthView` sets it on the pairing code and
                // `SettingsView` on its one measured number.
                //
                // So: the spec's wording, and as much of the spec's treatment
                // as the constraint left on the table. Not the same claim.
                confirmedRow(label: "I'll reach you at",
                             value: session.ownerPhone,
                             monospaced: true,
                             changeLabel: "Change your number") {
                    editingPhone = true
                }
            }

            // THE ONE OPEN BOX, and it is last on purpose: it is the only thing
            // on this page anybody has to do, so it sits next to the button
            // that ends first run. The two rows above it are there to be read.
            TextField("First name", text: $firstName)
                .textContentType(.givenName)
                .autocorrectionDisabled()
                .font(.title3)
                .foregroundStyle(Theme.text)
                .focused($focus, equals: .firstName)
                .padding(.vertical, 12)
                .padding(.horizontal, 12)
                .background(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous).fill(Theme.surface))
                .overlay(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                    .strokeBorder(Theme.edge, lineWidth: 1))
                .onChange(of: firstName) { _ in detailsSaved = false; phoneSaveFailed = false }

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
        // SEEDED HERE, NOT ON THE BOXES. These three `.task`s used to hang off
        // the three TextFields; two of those boxes are conditional now, so a
        // seed left on them would never run for the person whose facts are
        // already on file — which is everybody this beat was rewritten for.
        .task {
            if firstName.isEmpty { firstName = session.ownerFirstName }
            if email.isEmpty { email = session.ownerEmail }
            guard phone.isEmpty else { return }
            // Already told us at the door? Confirm, don't re-interrogate.
            // Otherwise start from this phone's own dialling code, so the
            // country is in front of the person rather than assumed behind
            // them — `e164` refuses to guess one now, and a blank field plus a
            // refusal is a dead end wearing a different hat.
            phone = session.ownerPhone.isEmpty
                ? DiallingCode.forThisPhone() : session.ownerPhone
            // AND IT IS ALREADY SAVED, so say so to the one thing that asks.
            // `advance()` re-sent this number on every first run, because
            // `phoneSaved` began false over a value that had come off the
            // account. On a good connection that was one wasted round trip. On
            // a bad one it was a person held at the last page of first run by
            // "I couldn't save that just now" over a number already on their
            // record — a false failure, and the confirmation framing above
            // would have been sitting right on top of it.
            phoneSaved = hasStoredPhone && phone == session.ownerPhone
        }
        .animation(Theme.spring, value: session.e164(phone) != nil)
        .animation(Theme.spring, value: showingEmailField)
        .animation(Theme.spring, value: showingPhoneField)
    }

    /// A fact she already holds, shown as settled instead of asked for again.
    ///
    /// EVERY PIECE OF THIS IS ALREADY IN THE PRODUCT. The tick, the accent and
    /// the semibold are the treatment the number's own "That's you" line has
    /// used since this beat shipped, lifted up into the row so that the row
    /// itself is the confirmation. The container is `anticipyCard()`, the same
    /// one the primer's Settings card and the save-failure card use. And
    /// "Change it" is a ghost PILL, which `GhostLinkStyle` names as its own
    /// job: "a pill hugs its two words — Skip, Not now, a link at the end of a
    /// sentence."
    ///
    /// The whole card is the tap target as well as the pill, because a person
    /// reading "I'll reach you at" and a wrong number reaches for the number.
    /// The pill stays visible regardless: an affordance you have to guess at is
    /// not one, and this row is otherwise indistinguishable from a label.
    private func confirmedRow(label: String,
                              value: String,
                              monospaced: Bool = false,
                              changeLabel: String,
                              change: @escaping () -> Void) -> some View {
        // Annotated rather than inferred: this is a multi-statement closure
        // handed to two different call sites, and it is the one thing in this
        // file no parse check can prove for me.
        let open: () -> Void = { Haptics.tap(); withAnimation(Theme.spring) { change() } }
        return VStack(alignment: .leading, spacing: Theme.Space.hair) {
            Text(label)
                .font(.caption)
                .foregroundStyle(Theme.muted)
            HStack(alignment: .firstTextBaseline, spacing: Theme.Space.tight) {
                Label {
                    Text(value)
                        .font(monospaced ? .title3.monospacedDigit() : .title3)
                        .foregroundStyle(Theme.text)
                        .fixedSize(horizontal: false, vertical: true)
                } icon: {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundStyle(Theme.accent)
                }
                Spacer(minLength: Theme.Space.tight)
                Button(action: open) { Text("Change it") }
                    .buttonStyle(.ghost)
                    .accessibilityLabel(changeLabel)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
        .contentShape(Rectangle())
        .onTapGesture(perform: open)
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

// MARK: - The two decisions this walkthrough makes about words

/// Which beat you are on, out of how many — counting the one that already
/// happened.
///
/// PURE, and lifted out of this file by `run_first_run_copy_tests.sh` rather
/// than copied into it. This is arithmetic that renumbers every beat of the
/// highest-stakes flow in the product, and an off-by-one here misnames the
/// screen a person is standing on. It has to be answerable without a simulator.
///
/// THE FIRST NAME IS NOT A PAGE IN THIS VIEW. It is the door, cleared before
/// `OnboardingView` exists. Counting it is the entire point: the track used to
/// open at "1 of 4" over somebody who had just typed an email, a password and a
/// phone number, and told them they were at the start.
///
/// Every index goes through `index(step:pageCount:)`, which CLAMPS. A fifth
/// `Step` added without a fifth name would otherwise be a subscript out of
/// range — a crash, on a stranger's first run, from a copy change.
enum FirstRunTrack {
    /// Short because the live one renders on a single line beside its count on
    /// a 375pt phone.
    static let beatNames = ["Your account", "Hello", "How I work",
                            "May I listen?", "Where to reach you"]

    static var count: Int { beatNames.count }

    /// How many beats are behind somebody standing on this view's first page.
    /// DERIVED, never written down twice: a beat added to both `Step` and
    /// `beatNames` keeps this correct on its own, and a beat added to only one
    /// of them is wrong somewhere a test can see it rather than on a phone.
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
    /// the live marker adds for everyone else. It says both rather than trading
    /// one for the other, and it is built here so the spoken count and the
    /// printed count cannot drift apart.
    static func spokenLabel(step: Int, pageCount: Int) -> String {
        "Step \(ordinal(step: step, pageCount: pageCount)) of \(count), "
            + name(step: step, pageCount: pageCount)
    }
}

/// What the last beat may honestly say it already has.
///
/// The prescription for this screen was one fixed sentence: "Your email and
/// number came in at the door." It is a good sentence and it is not always
/// true. On the sign-in path the number never came in at any door — `signIn`
/// reads it back off the account record — and if the account has no number at
/// all, the field holds nothing but this phone's dialling code and the sentence
/// is describing something that does not exist. A confirmation screen is worth
/// exactly its accuracy; one that confidently names a fact it does not hold is
/// worse than the interrogation it replaced.
///
/// So the sentence is BUILT from what is on file. Pure, and lifted by
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
                                  hasFirstName: hasFirstName)]
            .compactMap { $0 }
            .joined(separator: " ")
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
