import SwiftUI

/// The door. Everything before this is a stranger; everything after is a person
/// with a name, whose day belongs to them.
///
/// It is deliberately not a form. One question per screen — your email, a
/// password, your number — with a thin bar under the mark counting the three
/// as the first beat of first run, and the account made on the third with a
/// button that says so. Returning people get the same chrome without the bar:
/// sign in, or the two screens that get a forgotten password back by text.
struct AuthView: View {
    @EnvironmentObject var session: AnticipySession
    @AppStorage(AppPreferences.postSignOutNoticeKey) private var postSignOutNotice = ""

    enum SignUpStep: Int, Equatable { case email, password, phone }
    enum Mode: Equatable { case signUp(SignUpStep), signIn, forgot, code, newPassword }
    /// MOTION SENSITIVITY. Read so the animations below can stand down; the
    /// beat is kept either way, so a flow under Reduce Motion takes the same
    /// time and simply shows its finished frame rather than travelling to it.
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var mode: Mode = .signUp(.email)
    /// Which way the next page turn slides.
    @State private var forward = true

    @State private var email = ""
    @State private var password = ""
    @State private var phoneCode = DiallingCode.forThisPhone().trimmingCharacters(in: .whitespaces)
    @State private var phoneDigits = ""
    @State private var resetCode = ""
    @State private var busy = false
    @State private var problem: String?
    @State private var note: String?
    @FocusState private var focus: Field?
    private enum Field { case email, password, phone, newPassword }

    /// THE COUNTRY IS IN THE FIELD, NOT IN THE APP'S HEAD. `e164` no longer
    /// guesses a country from a bare ten digits, because guessing wrote a US
    /// number onto a London stranger's account. So the code sits in its own
    /// box, seeded from this phone's region and one tap to change.
    private var phone: String { "\(phoneCode) \(phoneDigits)" }

    var body: some View {
        ZStack {
            OnboardTheme.ground.ignoresSafeArea()
            VStack(spacing: 0) {
                StepperHeader(progress: progress, spokenLabel: spokenProgress)
                ZStack {
                    content
                        .id(pageKey)
                        .transition(.asymmetric(
                            insertion: .move(edge: forward ? .trailing : .leading).combined(with: .opacity),
                            removal: .move(edge: forward ? .leading : .trailing).combined(with: .opacity)))
                }
                .animation(Theme.springSlow, value: mode)
            }
        }
        .overlay(alignment: .bottom) { footer }
        // A failure is felt, not just read.
        .onChange(of: problem) { p in
            if p != nil { Haptics.warning() }
        }
        .task {
            // A returning person's email is already known — open the sign-in
            // door with it filled in, and put the cursor where they'll type.
            if !session.ownerEmail.isEmpty, email.isEmpty {
                email = session.ownerEmail
                mode = .signIn
            }
            try? await Task.sleep(nanoseconds: 450_000_000)
            focusFirstField()
        }
        .onChange(of: mode) { _ in
            Task {
                try? await Task.sleep(nanoseconds: 420_000_000)
                focusFirstField()
            }
        }
    }

    // MARK: - Chrome

    /// The three sign-up screens are the first beat of first run, counted as
    /// thirds of it: nothing done, one done, two done. Everything else shares
    /// the header without a bar — a returning person is not on a journey.
    private var progress: Double? {
        switch mode {
        case .signUp(let step):
            return Double(step.rawValue) / Double(FirstRunTrack.count)
        default:
            return nil
        }
    }

    private var spokenProgress: String {
        guard case .signUp(let step) = mode else { return "" }
        return "Your account, part \(step.rawValue + 1) of 3"
    }

    private var pageKey: String {
        switch mode {
        case .signUp(let step): return "signUp.\(step.rawValue)"
        case .signIn: return "signIn"
        case .forgot: return "forgot"
        case .code: return "code"
        case .newPassword: return "newPassword"
        }
    }

    /// Commits the direction on its own body pass, THEN turns the page, so
    /// the outgoing page leaves the way the incoming one arrives. A problem
    /// set beside a move survives it: only the move itself clears the old one.
    private func move(to next: Mode, back: Bool = false) {
        note = nil
        problem = nil
        forward = !back
        DispatchQueue.main.async {
            withAnimation(reduceMotion ? nil : Theme.springSlow) { mode = next }
        }
    }

    private func focusFirstField() {
        switch mode {
        case .signUp(.email), .signIn, .forgot: focus = .email
        case .signUp(.password): focus = .password
        case .signUp(.phone): focus = .phone
        case .newPassword: focus = .newPassword
        case .code: break   // OTPBoxes owns its own focus
        }
    }

    // MARK: - Pages

    @ViewBuilder private var content: some View {
        switch mode {
        case .signUp(.email): emailPage
        case .signUp(.password): passwordPage
        case .signUp(.phone): phonePage
        case .signIn: signInPage
        case .forgot: forgotPage
        case .code: codePage
        case .newPassword: newPasswordPage
        }
    }

    private func page<Content: View>(@ViewBuilder content: @escaping () -> Content) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                content()
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, OnboardMetric.gutter)
            .padding(.top, 34)
            .padding(.bottom, OnboardMetric.footerClearance)
            .animation(Theme.spring, value: problem)
            .animation(Theme.spring, value: note)
            .animation(Theme.spring, value: busy)
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

    private func lead(_ text: String) -> some View {
        Text(text)
            .font(OnboardFont.body)
            .lineSpacing(4)
            .foregroundStyle(OnboardTheme.text2)
            .fixedSize(horizontal: false, vertical: true)
    }

    /// THE GREETING MOVED, SO THE DOOR STOPPED SAYING IT TWICE. This read
    /// "I'm Anticipy." and the welcome beat comes BEFORE it now. By the time
    /// somebody reaches this screen they have been introduced; what they have
    /// not done is make the thing theirs.
    ///
    /// TWO NUMBERS, BECAUSE ONE OF THEM WAS BEING READ AS BOTH. This said "It
    /// takes about ten seconds", and ten seconds became the ruler for the whole
    /// run. `CONSUMER-FEEL-DIRECTION-2026-08-03.md` §5 opens the door at 0:00
    /// and leaves it at 0:20, and lands on Home at 1:00. Both figures survive
    /// the split across three screens: it is still about twenty seconds of
    /// typing, and the whole run is still about a minute.
    private var emailPage: some View {
        page {
            question("Let's make it yours.")
            lead("Create your account with an email, password, and phone number. About twenty seconds here and one minute from start to finish.")
            if !postSignOutNotice.isEmpty {
                OnboardCard {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(postSignOutNotice)
                            .font(OnboardFont.helper)
                            .lineSpacing(3)
                            .foregroundStyle(OnboardTheme.text2)
                            .fixedSize(horizontal: false, vertical: true)
                        Button("Got it") { postSignOutNotice = "" }
                            .buttonStyle(.onboardSoft)
                    }
                }
                .accessibilityElement(children: .contain)
                .accessibilityLabel("Device forget result")
            }
            QuestionField(label: "Email", text: $email, placeholder: "you@email.com",
                          kind: .email, focus: $focus, tag: .email, submit: .next) {
                if emailOK { move(to: .signUp(.password)) }
            }
            if let problem { OnboardProblem(text: problem) }
        }
    }

    private var passwordPage: some View {
        page {
            question("Pick a password")
            QuestionField(label: "Password", text: $password, placeholder: "At least 8 characters",
                          kind: .newPassword, focus: $focus, tag: .password, submit: .next) {
                if passwordOK { move(to: .signUp(.phone)) }
            }
            OnboardHelper(text: "Eight characters or more", satisfied: passwordOK)
        }
    }

    private var phonePage: some View {
        page {
            question("What's your phone number?")
            HStack(spacing: 8) {
                CountryCodeBox(code: $phoneCode)
                QuestionField(label: "Phone number", text: $phoneDigits, placeholder: "Phone number",
                              kind: .phone, focus: $focus, tag: .phone, submit: .go) {
                    if canGo { Task { await go() } }
                }
            }
            .onChange(of: phoneDigits) { value in
                let digits = String(value.filter(\.isNumber).prefix(14))
                if digits != value { phoneDigits = digits }
            }
            // Says "country code and all" whether or not it is satisfied: ten
            // digits of a real London number used to sit there failing a rule
            // they appeared to pass, with the reason nowhere on screen.
            OnboardHelper(text: "A number I can text, country code and all", satisfied: reachable)
            OnboardHelper(text: "Your phone number is used for recovery and time-sensitive approvals.")
            if let problem { OnboardProblem(text: problem) }
            if busy { OnboardStatus(text: "Setting you up…") }
        }
        // The phone pad has no return key, so the commit sits above it.
        .toolbar {
            PhonePadDoneBar(label: canGo ? "Start" : "Done", enabled: !busy) {
                if canGo { Task { await go() } } else { focus = nil }
            }
        }
    }

    private var signInPage: some View {
        page {
            question("Welcome back.")
            lead("Enter the email and password for your Anticipy account.")
            if !postSignOutNotice.isEmpty {
                OnboardCard {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(postSignOutNotice)
                            .font(OnboardFont.helper)
                            .lineSpacing(3)
                            .foregroundStyle(OnboardTheme.text2)
                            .fixedSize(horizontal: false, vertical: true)
                        Button("Got it") { postSignOutNotice = "" }
                            .buttonStyle(.onboardSoft)
                    }
                }
                .accessibilityElement(children: .contain)
                .accessibilityLabel("Device forget result")
            }
            VStack(spacing: 8) {
                QuestionField(label: "Email", text: $email, placeholder: "you@email.com",
                              kind: .email, focus: $focus, tag: .email, submit: .next) {
                    focus = .password
                }
                QuestionField(label: "Password", text: $password, placeholder: "Your password",
                              kind: .password, focus: $focus, tag: .password, submit: .go) {
                    if canGo { Task { await go() } }
                }
            }
            if let problem { OnboardProblem(text: problem) }
            if busy { OnboardStatus(text: "One moment…") }
        }
    }

    private var forgotPage: some View {
        page {
            question("Let's get you back in.")
            lead("Enter your account email to receive a recovery code by text.")
            QuestionField(label: "Email", text: $email, placeholder: "you@email.com",
                          kind: .email, focus: $focus, tag: .email, submit: .go) {
                if canGo { Task { await go() } }
            }
            if let problem { OnboardProblem(text: problem) }
            if busy { OnboardStatus(text: "Sending…") }
        }
    }

    private var codePage: some View {
        page {
            question("Check your phone.")
            lead("Enter the 6-digit code from your phone, then choose a new password.")
            OTPBoxes(code: $resetCode)
                .onChange(of: resetCode) { value in
                    if value.count == 6 { Haptics.tap() }
                }
            // The answer is deliberately the same whether or not that account
            // exists, so this screen says the same thing too.
            OnboardHelper(text: note ?? "If that's an account with a number on it, a code is on its way. It works for ten minutes.")
        }
    }

    private var newPasswordPage: some View {
        page {
            question("Choose a new password")
            QuestionField(label: "New password", text: $password, placeholder: "At least 8 characters",
                          kind: .newPassword, focus: $focus, tag: .newPassword, submit: .go) {
                if canGo { Task { await go() } }
            }
            OnboardHelper(text: "Eight characters or more", satisfied: passwordOK)
            if let problem { OnboardProblem(text: problem) }
            if busy { OnboardStatus(text: note ?? "Saving…") }
        }
    }

    // MARK: - Footers

    @ViewBuilder private var footer: some View {
        switch mode {
        case .signUp(.email):
            OnboardFooter {
                HStack(spacing: 12) {
                    OnboardFABSpacer()
                    swap("Already have an account?", "Sign in") { move(to: .signIn) }
                        .frame(maxWidth: .infinity)
                    OnboardFAB(enabled: emailOK, label: "Continue") {
                        Haptics.engage()
                        move(to: .signUp(.password))
                    }
                }
            }
        case .signUp(.password):
            OnboardFooter {
                HStack(spacing: 12) {
                    OnboardFAB(direction: .back, label: "Back") { move(to: .signUp(.email), back: true) }
                    Spacer()
                    OnboardFAB(enabled: passwordOK, label: "Continue") {
                        Haptics.engage()
                        move(to: .signUp(.phone))
                    }
                }
            }
        case .signUp(.phone):
            OnboardFooter {
                VStack(spacing: 14) {
                    swap("Forgotten your password?", "Text me a code") { move(to: .forgot) }
                    HStack(spacing: 12) {
                        OnboardFAB(direction: .back, label: "Back") { move(to: .signUp(.password), back: true) }
                        primaryButton
                    }
                }
            }
        case .signIn:
            OnboardFooter {
                VStack(spacing: 8) {
                    swap("Forgotten your password?", "Text me a code") { move(to: .forgot) }
                    swap("New here?", "Make an account") { move(to: .signUp(.email), back: true) }
                    HStack(spacing: 12) {
                        OnboardFAB(direction: .back, label: "Back") { move(to: .signUp(.email), back: true) }
                        primaryButton
                    }
                    .padding(.top, 6)
                }
            }
        case .forgot:
            OnboardFooter {
                VStack(spacing: 14) {
                    swap("Remembered it?", "Back to sign in") { move(to: .signIn, back: true) }
                    primaryButton
                }
            }
        case .code:
            OnboardFooter {
                HStack(spacing: 12) {
                    OnboardFAB(direction: .back, label: "Back") { move(to: .forgot, back: true) }
                    VStack(spacing: 2) {
                        Text("Experiencing issues? Email our team:")
                        if let mail = URL(string: "mailto:hello@anticipy.ai") {
                            Link("hello@anticipy.ai", destination: mail)
                                .foregroundStyle(OnboardTheme.text2)
                                .underline()
                        }
                    }
                    .font(.system(size: 13))
                    .foregroundStyle(OnboardTheme.muted)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: .infinity)
                    OnboardFAB(enabled: resetCode.count == 6, label: "Continue") {
                        Haptics.engage()
                        password = ""
                        move(to: .newPassword)
                    }
                }
            }
        case .newPassword:
            OnboardFooter {
                VStack(spacing: 14) {
                    swap("Remembered it?", "Back to sign in") { move(to: .signIn, back: true) }
                    HStack(spacing: 12) {
                        OnboardFAB(direction: .back, label: "Back") { move(to: .code, back: true) }
                        primaryButton
                    }
                }
            }
        }
    }

    /// The commit: a black pill that says what it does, and while it is doing
    /// it, says that instead.
    private var primaryButton: some View {
        Button {
            Task { await go() }
        } label: {
            Text(buttonLabel)
                .id(buttonLabel)
                .transition(.opacity)
        }
        .buttonStyle(.onboardBlack)
        .disabled(!canGo || busy)
        .animation(Theme.spring, value: buttonLabel)
    }

    private var buttonLabel: String {
        switch mode {
        case .signUp: return busy ? "Setting you up…" : "Start"
        case .signIn: return busy ? "One moment…" : "Sign in"
        case .forgot: return busy ? "Sending…" : "Text me a code"
        case .code: return "Continue"
        case .newPassword: return busy ? "Saving…" : "Set my new password"
        }
    }

    /// The mode switcher: a question and the word that answers it, quiet,
    /// centred in the footer.
    private func swap(_ lead: String, _ action: String, _ go: @escaping () -> Void) -> some View {
        Button {
            Haptics.tap()
            problem = nil; note = nil
            // A password typed for one door is not carried to another.
            password = ""
            go()
        } label: {
            HStack(spacing: 5) {
                Text(lead)
                    .foregroundStyle(OnboardTheme.muted)
                Text(action)
                    .foregroundStyle(OnboardTheme.champagneInk)
                    .fontWeight(.semibold)
            }
            .font(.system(size: 14))
        }
        .buttonStyle(OnboardPressStyle(scale: 0.97))
    }

    // MARK: - What is enough

    private var emailOK: Bool { email.contains("@") }
    private var passwordOK: Bool { password.count >= 8 }

    /// Enough of a number to actually deliver a text to.
    ///
    /// Deliberately permissive about SHAPE — people type "(604) 555-0142",
    /// "+1 604 555 0142", "604.555.0142" — and strict about there being a
    /// real number there at all. Ten digits is the floor for a deliverable
    /// number in this market; below that it is a typo or an empty field,
    /// and either one leaves the customer permanently unreachable.
    static func looksReachable(_ raw: String) -> Bool {
        let digits = raw.filter(\.isNumber)
        guard digits.count >= 10, digits.count <= 15 else { return false }
        return !digits.allSatisfy { $0 == digits.first }   // 0000000000
    }

    /// THE ONE PREDICATE THE HELPER LINE AND THE BUTTON BOTH READ. A helper
    /// reading `looksReachable` alone would turn champagne over a number the
    /// Start button will not accept; a Start button reading it alone would
    /// create the account with NO number on it.
    private var reachable: Bool {
        Self.looksReachable(phone) && session.e164(phone) != nil
    }

    private var canGo: Bool {
        switch mode {
        // A NUMBER IS NOT OPTIONAL, BECAUSE IT IS THE ONLY WAY OUT. A text is
        // the one way the product can reach somebody whose phone is in their
        // pocket; an account without one parks every question forever.
        case .signUp: return emailOK && passwordOK && reachable
        case .signIn: return emailOK && !password.isEmpty
        case .forgot: return emailOK
        case .code: return resetCode.count == 6
        case .newPassword: return passwordOK
        }
    }

    // MARK: - Doing it

    private func go() async {
        guard !busy else { return }
        busy = true
        problem = nil
        note = nil
        defer { busy = false }
        Haptics.engage()
        switch mode {
        case .signUp:
            if let err = await session.signUp(email: email, password: password, phone: phone) {
                problem = err
            } else {
                Haptics.success()
            }
        case .signIn:
            if let err = await session.signIn(email: email, password: password) {
                problem = err
            } else {
                Haptics.success()
            }
        case .forgot:
            await session.requestPasswordReset(email: email)
            Haptics.tap()
            resetCode = ""
            move(to: .code)
        case .code:
            password = ""
            move(to: .newPassword)
        case .newPassword:
            if let err = await session.confirmPasswordReset(email: email, code: resetCode,
                                                            newPassword: password) {
                problem = err
            } else {
                Haptics.success()
                note = "Done. Signing you in…"
                if let err = await session.signIn(email: email, password: password) {
                    // AFTER the move, so the move's own clear cannot eat it.
                    move(to: .signIn, back: true)
                    problem = err
                }
            }
        }
    }
}
