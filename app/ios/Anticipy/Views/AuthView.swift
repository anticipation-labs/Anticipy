import SwiftUI

/// The door. Everything before this is a stranger; everything after is a person
/// with a name, whose day belongs to them.
///
/// It is deliberately not a form. A form is what a bank makes you fill in; this
/// is her introducing herself and asking who you are. Two fields, one button,
/// nothing else on screen — and the thing people actually fear ("what if I
/// forget my password") answered in the same breath rather than hidden behind
/// a link they have to hunt for.
struct AuthView: View {
    @EnvironmentObject var session: AnticipySession

    enum Mode { case signUp, signIn, forgot, code }
    @State private var mode: Mode = .signUp

    @State private var email = ""
    @State private var password = ""
    @State private var phone = ""
    @State private var resetCode = ""
    @State private var busy = false
    @State private var problem: String?
    @State private var note: String?
    @FocusState private var focus: Field?
    private enum Field { case email, password, phone, code }

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()
            // GrainLayer, not a hand-rolled copy. This was
            // `.blendMode(.plusLighter)` with the dark opacity baked in — on the
            // FIRST screen a new person ever sees, which in the light default is
            // a white haze over a white page eating the contrast of everything
            // under it. GrainLayer reads the scheme.
            GrainLayer()

            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    header
                    fields
                    // A failure painted in the success colour reads correct
                    // at a glance and wrong on reading. Sand, in a card, with
                    // no SF Symbol — a sentence, not an alert.
                    if let problem {
                        VStack(alignment: .leading, spacing: 10) {
                            Text(problem)
                                .font(.system(size: 17))
                                .lineSpacing(3)
                                .foregroundStyle(Theme.text2)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .anticipyCard()
                        .transition(.opacity.combined(with: .move(edge: .top)))
                    }
                    if let note {
                        Text(note)
                            .font(.callout)
                            .foregroundStyle(Theme.text2)
                            .fixedSize(horizontal: false, vertical: true)
                            .transition(.opacity)
                    }
                    primaryButton
                    switcher
                }
                .padding(.horizontal, 28)
                .padding(.top, 72)
                .padding(.bottom, 40)
                .animation(Theme.spring, value: mode)
                .animation(Theme.spring, value: problem)
                .animation(Theme.spring, value: note)
            }
            .scrollDismissesKeyboard(.interactively)
        }
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
            try? await Task.sleep(nanoseconds: 400_000_000)
            focus = .email
        }
    }

    // MARK: - Pieces

    private var header: some View {
        VStack(alignment: .center, spacing: 14) {
            // The mark lands at the same size, centred, as the onboarding
            // welcome that follows — the eye tracks one object across the
            // boundary. It stands on the page by itself: the champagne haze
            // that used to sit behind it is gone from every surface, and the
            // ZStack that existed only to hold it went with it.
            LogoMark(size: 72)
                .frame(height: 90)
                .frame(maxWidth: .infinity)
                .accessibilityHidden(true)
            Text(title)
                .font(Theme.display(30))
                .tracking(-0.5)
                .foregroundStyle(Theme.text)
                .fixedSize(horizontal: false, vertical: true)
            Text(subtitle)
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.text2)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity)
    }

    private var title: String {
        switch mode {
        case .signUp: return "I'm Anticipy."
        case .signIn: return "Welcome back."
        case .forgot: return "Let's get you back in."
        case .code:   return "Check your phone."
        }
    }

    private var subtitle: String {
        switch mode {
        case .signUp: return "Make an account and I'll start keeping your day for you. It takes about ten seconds."
        case .signIn: return "Your email and password, and everything's where you left it."
        case .forgot: return "Tell me the email you signed up with and I'll text you a code."
        case .code:   return "I've sent a 6-digit code to your phone. Enter it and pick a new password."
        }
    }

    @ViewBuilder private var fields: some View {
        VStack(spacing: 14) {
            switch mode {
            case .signUp:
                field("Email", text: $email, focus: .email, kind: .email)
                field("Password", text: $password, focus: .password, kind: .newPassword)
                field("Your number", text: $phone, focus: .phone, kind: .phone)
                    // THE COUNTRY IS IN THE FIELD, NOT IN THE APP'S HEAD.
                    // `e164` no longer guesses a country from a bare ten
                    // digits, because guessing wrote a US number onto a
                    // London stranger's account. So the field arrives with
                    // this phone's own dialling code already in it — visible,
                    // and one tap to change if iOS's region is not where they
                    // live. Empty-check first: nothing here overwrites a
                    // number the keyboard's own autofill put in.
                    .task { if phone.isEmpty { phone = DiallingCode.forThisPhone() } }
                // Two small rewards before commitment instead of one silent
                // refusal: the rules turn champagne, with a tick in the hand,
                // the moment each is satisfied.
                ruleLine("A real email", satisfied: email.contains("@"))
                ruleLine("Eight characters or more", satisfied: password.count >= 8)
                // Says "country code and all" whether or not it is satisfied.
                // The rule used to read "A number I can text", which is the
                // one thing a refused number still looks like: ten digits of
                // a real London number sit there failing a rule they appear
                // to pass, with the reason nowhere on screen.
                ruleLine("A number I can text, country code and all",
                         satisfied: reachable)
                Text("Your number is how I reach you when something needs your word, and how you get back in if you forget your password.")
                    .font(.system(size: 15))
                    .lineSpacing(2)
                    .foregroundStyle(Theme.text2)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
            case .signIn:
                field("Email", text: $email, focus: .email, kind: .email)
                field("Password", text: $password, focus: .password, kind: .password)
            case .forgot:
                field("Email", text: $email, focus: .email, kind: .email)
            case .code:
                field("6-digit code", text: $resetCode, focus: .code, kind: .code)
                field("New password", text: $password, focus: .password, kind: .newPassword)
            }
        }
    }

    /// A discoverable rule: grey while unmet, champagne with a checkmark and
    /// a light tap the moment it's satisfied.
    private func ruleLine(_ text: String, satisfied: Bool) -> some View {
        HStack(spacing: 6) {
            Image(systemName: satisfied ? "checkmark.circle.fill" : "circle")
                .font(.caption)
                .accessibilityHidden(true)
            Text(text).font(.system(size: 15))
            Spacer(minLength: 0)
        }
        .foregroundStyle(satisfied ? Theme.accent : Theme.muted)
        .animation(Theme.spring, value: satisfied)
        .onChange(of: satisfied) { ok in
            if ok { Haptics.tap() }
        }
    }

    private enum Kind { case email, password, newPassword, phone, code }

    /// The prompt carries the label — an 11pt uppercase caps tag over an
    /// empty grey rectangle is a Stripe-dashboard form, not her asking.
    private func prompt(for kind: Kind) -> String {
        switch kind {
        case .email: return "you@email.com"
        case .password: return "Your password"
        case .newPassword: return "At least 8 characters"
        case .phone: return "+1 604 555 0123"
        case .code: return "6-digit code"
        }
    }

    private func field(_ label: String, text: Binding<String>,
                       focus f: Field, kind: Kind) -> some View {
        Group {
            if kind == .password || kind == .newPassword {
                SecureField("", text: text,
                            prompt: Text(prompt(for: kind)).foregroundColor(Theme.muted))
                    .textContentType(kind == .newPassword ? .newPassword : .password)
            } else {
                TextField("", text: text,
                          prompt: Text(prompt(for: kind)).foregroundColor(Theme.muted))
                    .textContentType(kind == .email ? .emailAddress
                                     : kind == .phone ? .telephoneNumber : .oneTimeCode)
                    .keyboardType(kind == .email ? .emailAddress
                                  : kind == .phone ? .phonePad
                                  : kind == .code ? .numberPad : .default)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
            }
        }
        .font(kind == .code ? .title2.monospacedDigit() : .body)
        .foregroundStyle(Theme.text)
        .focused($focus, equals: f)
        .submitLabel(kind == .newPassword || kind == .password ? .go : .next)
        .onSubmit {
            switch f {
            case .email: focus = mode == .forgot ? nil : .password
            case .password: focus = nil; Task { await go() }
            case .phone, .code: focus = nil
            }
        }
        .padding(.vertical, 14)
        .padding(.horizontal, 16)
        .background(
            RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                .fill(Theme.surface)
                .overlay(
                    RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                        .stroke(focus == f ? Theme.accent.opacity(0.7) : Theme.edge,
                                lineWidth: focus == f ? 1.5 : 1)
                )
        )
        .animation(Theme.spring, value: focus)
        .accessibilityLabel(label)
    }

    /// The label never moves; a 2pt sweep under it reads as work, where a
    /// spinner shoving the label sideways reads as a stall.
    ///
    /// The bar is drawn in `glassLabel` because that token is defined as
    /// whatever contrasts the glass in this theme — the old `Theme.text` bar
    /// disappeared into the dark fill the moment the material changed. It
    /// hangs off the BUTTON rather than the label so it sits on the pill's
    /// bottom edge, which is where the 24pt inset was measured from.
    ///
    /// The not-yet-ready state is the style's `.disabled` dim now, not a
    /// different fill: one material, one geometry, whether or not the form
    /// validates.
    @State private var sweep = false

    private var primaryButton: some View {
        Button {
            Task { await go() }
        } label: {
            Text(buttonLabel)
                .frame(maxWidth: .infinity)
        }
        .buttonStyle(.glass)
        .overlay(alignment: .bottom) {
            if busy {
                Capsule()
                    .fill(Theme.glassLabel.opacity(0.5))
                    .frame(height: 2)
                    .scaleEffect(x: sweep ? 1 : 0.02, anchor: .leading)
                    .padding(.horizontal, 24)
                    .padding(.bottom, 7)
                    .animation(.linear(duration: 1.2).repeatForever(autoreverses: false), value: sweep)
                    .onAppear { sweep = true }
                    .onDisappear { sweep = false }
                    .allowsHitTesting(false)
            }
        }
        .disabled(!canGo || busy)
        .animation(Theme.spring, value: canGo)
    }

    private var buttonLabel: String {
        switch mode {
        case .signUp: return busy ? "Setting you up…" : "Start"
        case .signIn: return busy ? "One moment…" : "Sign in"
        case .forgot: return busy ? "Sending…" : "Text me a code"
        case .code:   return busy ? "Saving…" : "Set my new password"
        }
    }

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

    /// THE ONE PREDICATE THE RULE LINE AND THE BUTTON BOTH READ.
    ///
    /// They were the same thing only for as long as `e164` accepted whatever
    /// `looksReachable` accepted. It no longer does — a bare ten-digit number
    /// with no country code is refused now instead of being quietly moved to
    /// the United States — so a rule line reading `looksReachable` alone would
    /// tick champagne, with the tick in the hand, over a number the Start
    /// button will not accept and nothing on screen would say why. And a Start
    /// button reading `looksReachable` alone would create the account with NO
    /// number on it: `signUp` passes `e164(phone)` straight through, and nil
    /// there is an account that can never be texted, made silently, at the door.
    private var reachable: Bool {
        Self.looksReachable(phone) && session.e164(phone) != nil
    }

    private var canGo: Bool {
        switch mode {
        // A NUMBER IS NOT OPTIONAL, BECAUSE IT IS THE ONLY WAY OUT.
        //
        // This asked for email and password only. A customer could sign up
        // leaving the number blank — and this app has no notifications at
        // all, so a text is the ONLY way the product can ever reach them.
        // notify_owner returns nothing without a number, so every question
        // it needed to ask went nowhere and their work parked forever, in
        // silence, with nothing on any screen saying why.
        //
        // The copy under this field already promises "your number is how I
        // reach you when something needs your word". This makes that true.
        case .signUp:
            return email.contains("@") && password.count >= 8 && reachable
        case .signIn: return email.contains("@") && !password.isEmpty
        case .forgot: return email.contains("@")
        case .code:   return resetCode.count >= 4 && password.count >= 8
        }
    }

    private var switcher: some View {
        VStack(spacing: 16) {
            switch mode {
            case .signUp:
                swap("Already have an account?", "Sign in") { mode = .signIn }
            case .signIn:
                swap("Forgotten your password?", "Text me a code") { mode = .forgot }
                swap("New here?", "Make an account") { mode = .signUp }
            case .forgot, .code:
                swap("Remembered it?", "Back to sign in") { mode = .signIn }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 4)
    }

    /// The mode switcher: a question and the word that answers it. It hugs the
    /// sentence rather than spanning the column — a full-width frosted plate on
    /// press would read as a second primary.
    ///
    /// The only text CTA in the app that sits in running layout, so it is the
    /// one that gets `.arrow`: every one of these four moves the person to the
    /// next step of getting in. The lead takes the style's own label token, and
    /// only the action word keeps the accent, because that is the part you are
    /// being asked to tap. The rule under it inherits the lead's colour rather
    /// than the accent, so the wipe reads as an underline, not a second
    /// highlight.
    private func swap(_ lead: String, _ action: String, _ go: @escaping () -> Void) -> some View {
        Button {
            problem = nil; note = nil
            go()
        } label: {
            HStack(spacing: 6) {
                Text(lead)
                Text(action).foregroundStyle(Theme.accent).fontWeight(.semibold)
            }
        }
        .buttonStyle(.arrow)
    }

    // MARK: - Doing it

    private func go() async {
        busy = true
        problem = nil
        note = nil
        defer { busy = false }
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
            // The answer is deliberately the same whether or not that account
            // exists, so this screen says the same thing too.
            note = "If that's an account with a number on it, a code is on its way. It works for ten minutes."
            mode = .code
        case .code:
            if let err = await session.confirmPasswordReset(email: email, code: resetCode,
                                                            newPassword: password) {
                problem = err
            } else {
                Haptics.success()
                note = "Done. Signing you in…"
                if let err = await session.signIn(email: email, password: password) {
                    problem = err
                    mode = .signIn
                }
            }
        }
    }
}
