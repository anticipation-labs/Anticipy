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
            // A single soft champagne bloom behind her name — the one piece of
            // depth on the screen, so the eye lands in the right place.
            RadialGradient(colors: [Theme.champagne.opacity(0.16), .clear],
                           center: .top, startRadius: 4, endRadius: 420)
                .ignoresSafeArea()
                .allowsHitTesting(false)

            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    header
                    fields
                    if let problem {
                        Label(problem, systemImage: "exclamationmark.circle")
                            .font(.callout)
                            .foregroundStyle(Theme.champagne)
                            .fixedSize(horizontal: false, vertical: true)
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
    }

    // MARK: - Pieces

    private var header: some View {
        VStack(alignment: .leading, spacing: 14) {
            LogoMark(size: 34)
                .accessibilityHidden(true)
            Text(title)
                .font(Theme.display(34))
                .foregroundStyle(Theme.ivory)
                .fixedSize(horizontal: false, vertical: true)
            Text(subtitle)
                .font(.callout)
                .foregroundStyle(Theme.gray)
                .fixedSize(horizontal: false, vertical: true)
        }
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
                Text("Your number is how I reach you when something needs your word — and how you get back in if you forget your password.")
                    .font(.footnote)
                    .foregroundStyle(Theme.gray)
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

    private enum Kind { case email, password, newPassword, phone, code }

    private func field(_ label: String, text: Binding<String>,
                       focus f: Field, kind: Kind) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(label.uppercased())
                .font(.caption2.weight(.semibold))
                .tracking(1.1)
                .foregroundStyle(Theme.gray)
            Group {
                if kind == .password || kind == .newPassword {
                    SecureField("", text: text)
                        .textContentType(kind == .newPassword ? .newPassword : .password)
                } else {
                    TextField("", text: text)
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
            .padding(.vertical, 14)
            .padding(.horizontal, 16)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(Theme.surface)
                    .overlay(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .stroke(focus == f ? Theme.champagne.opacity(0.7) : Theme.stroke,
                                    lineWidth: focus == f ? 1.5 : 1)
                    )
            )
            .animation(Theme.spring, value: focus)
        }
    }

    private var primaryButton: some View {
        Button {
            Task { await go() }
        } label: {
            HStack(spacing: 9) {
                if busy { ProgressView().tint(Theme.ink) }
                Text(buttonLabel)
                    .font(.callout.weight(.semibold))
            }
            .frame(maxWidth: .infinity, minHeight: 52)
            .background(Capsule().fill(canGo ? Theme.champagne : Theme.stroke))
            .foregroundStyle(canGo ? Theme.ink : Theme.gray)
        }
        .buttonStyle(.pressable)
        .disabled(!canGo || busy)
    }

    private var buttonLabel: String {
        switch mode {
        case .signUp: return busy ? "Setting you up…" : "Start"
        case .signIn: return busy ? "One moment…" : "Sign in"
        case .forgot: return busy ? "Sending…" : "Text me a code"
        case .code:   return busy ? "Saving…" : "Set my new password"
        }
    }

    private var canGo: Bool {
        switch mode {
        case .signUp: return email.contains("@") && password.count >= 8
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
