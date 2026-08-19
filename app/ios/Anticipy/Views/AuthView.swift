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
            Theme.ink.ignoresSafeArea()
            Grain.image
                .opacity(0.035)
                .blendMode(.plusLighter)
                .ignoresSafeArea()
                .allowsHitTesting(false)

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
                                .foregroundStyle(Theme.sand)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .anticipyCard()
                        .transition(.opacity.combined(with: .move(edge: .top)))
                    }
                    if let note {
                        Text(note)
                            .font(.callout)
                            .foregroundStyle(Theme.sand)
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
            // boundary. A tight bloom behind one object reads as light
            // coming OFF the object; a full-screen wash reads as wallpaper.
            ZStack {
                Theme.bloom(0.14, radius: 240)
                LogoMark(size: 72)
            }
            .frame(height: 90)
            .frame(maxWidth: .infinity)
            .accessibilityHidden(true)
            Text(title)
                .font(Theme.display(30))
                .tracking(-0.5)
                .foregroundStyle(Theme.ivory)
                .fixedSize(horizontal: false, vertical: true)
            Text(subtitle)
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.sand)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity)
    }

    private var title: String {
        switch mode {
        case .signUp: return "I'm Anticipy Claude Version."
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
                // Two small rewards before commitment instead of one silent
                // refusal: the rules turn champagne, with a tick in the hand,
                // the moment each is satisfied.
                ruleLine("A real email", satisfied: email.contains("@"))
                ruleLine("Eight characters or more", satisfied: password.count >= 8)
                ruleLine("A number I can text", satisfied: Self.looksReachable(phone))
                Text("Your number is how I reach you when something needs your word, and how you get back in if you forget your password.")
                    .font(.system(size: 15))
                    .lineSpacing(2)
                    .foregroundStyle(Theme.sand)
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
        .foregroundStyle(satisfied ? Theme.champagne : Theme.gray)
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
                            prompt: Text(prompt(for: kind)).foregroundColor(Theme.gray))
                    .textContentType(kind == .newPassword ? .newPassword : .password)
            } else {
                TextField("", text: text,
                          prompt: Text(prompt(for: kind)).foregroundColor(Theme.gray))
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
        .foregroundStyle(Theme.ivory)
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
                        .stroke(focus == f ? Theme.champagne.opacity(0.7) : Theme.stroke,
                                lineWidth: focus == f ? 1.5 : 1)
                )
        )
        .animation(Theme.spring, value: focus)
        .accessibilityLabel(label)
    }

    /// The label never moves; a 2pt ivory sweep under it reads as work,
    /// where a spinner shoving the label sideways reads as a stall. And the
    /// not-yet-ready button is PRESENT — the old Theme.stroke fill on ink was
    /// a 25-value delta, i.e. no visible button until the form validated.
    @State private var sweep = false

    private var primaryButton: some View {
        Button {
            Task { await go() }
        } label: {
            Text(buttonLabel)
                .font(.callout.weight(.semibold))
                .frame(maxWidth: .infinity, minHeight: 52)
                .background(
                    Capsule().fill(canGo ? Theme.champagne : Theme.surface)
                        .overlay(Capsule().strokeBorder(canGo ? Color.clear : Theme.stroke, lineWidth: 1))
                )
                .overlay(alignment: .bottom) {
                    if busy {
                        Capsule()
                            .fill(Theme.ivory.opacity(0.35))
                            .frame(height: 2)
                            .scaleEffect(x: sweep ? 1 : 0.02, anchor: .leading)
                            .padding(.horizontal, 24)
                            .padding(.bottom, 8)
                            .animation(.linear(duration: 1.2).repeatForever(autoreverses: false), value: sweep)
                            .onAppear { sweep = true }
                            .onDisappear { sweep = false }
                    }
                }
                .foregroundStyle(canGo ? Theme.ink : Theme.sand)
        }
        .buttonStyle(.pressable)
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
            return email.contains("@") && password.count >= 8
                && Self.looksReachable(phone)
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

    private func swap(_ lead: String, _ action: String, _ go: @escaping () -> Void) -> some View {
        Button {
            problem = nil; note = nil
            go()
        } label: {
            HStack(spacing: 6) {
                Text(lead).foregroundStyle(Theme.gray)
                Text(action).foregroundStyle(Theme.champagne).fontWeight(.semibold)
            }
            .font(.footnote)
            .frame(maxWidth: .infinity, minHeight: 44)
        }
        .buttonStyle(.pressable)
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
