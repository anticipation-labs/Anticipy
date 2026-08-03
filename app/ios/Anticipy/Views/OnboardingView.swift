import SwiftUI

/// First-run walkthrough: welcome → how it works → pair the pendant →
/// connect the browser agent → choose transcription → done.
/// Every step is skippable; nothing blocks the user from reaching the app.
struct OnboardingView: View {
    @EnvironmentObject var pendant: PendantManager
    @EnvironmentObject var session: AnticipySession
    @AppStorage("hasOnboarded") private var hasOnboarded = false
    @AppStorage("transcriptionEngine") private var engine = "local"
    @State private var step = 0
    @State private var agentCode = ""
    @State private var agentPairFailed = false
    @State private var phone = ""

    private let totalSteps = 6

    var body: some View {
        ZStack {
            Theme.ink.ignoresSafeArea()
            VStack(spacing: 0) {
                progressDots
                TabView(selection: $step) {
                    welcome.tag(0)
                    howItWorks.tag(1)
                    yourNumber.tag(2)
                    pairPendant.tag(3)
                    browserAgent.tag(4)
                    transcription.tag(5)
                }
                .tabViewStyle(.page(indexDisplayMode: .never))
                .animation(.easeInOut, value: step)
                footer
            }
        }
    }

    private var progressDots: some View {
        HStack(spacing: 8) {
            ForEach(0 ..< totalSteps, id: \.self) { i in
                Capsule()
                    .fill(i <= step ? Theme.champagne : Theme.stroke)
                    .frame(width: i == step ? 22 : 8, height: 6)
                    .animation(.spring(duration: 0.3), value: step)
            }
        }
        .padding(.top, 18)
    }

    private var footer: some View {
        VStack(spacing: 10) {
            Button {
                Haptics.engage()
                // Save the number as we leave its step — skipping is still
                // allowed, it just means she can't text until Settings.
                if step == 2, !phone.isEmpty {
                    Task { _ = await session.saveOwnerPhone(phone) }
                }
                if step < totalSteps - 1 {
                    withAnimation(Theme.spring) { step += 1 }
                } else {
                    Haptics.success()
                    hasOnboarded = true
                }
            } label: {
                Text(step == totalSteps - 1 ? "Start living your day" : "Continue")
                    .font(.body.weight(.semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .background(Capsule().fill(Theme.champagne))
                    .foregroundStyle(Theme.ink)
            }
            .buttonStyle(.pressable)
            if step > 0, step < totalSteps - 1 {
                Button("Skip for now") { withAnimation(Theme.spring) { step += 1 } }
                    .buttonStyle(.pressable)
                    .font(.footnote)
                    .foregroundStyle(Theme.gray)
            }
        }
        .padding(.horizontal, 28)
        .padding(.bottom, 26)
    }

    // MARK: - Steps

    @State private var welcomeStage = 0

    private var welcome: some View {
        VStack(spacing: 22) {
            Spacer()
            LogoMark(size: 120)
                .scaleEffect(welcomeStage >= 1 ? 1 : 0.6)
                .opacity(welcomeStage >= 1 ? 1 : 0)
            Text("Anticipy")
                .font(Theme.display(44))
                .foregroundStyle(Theme.ivory)
                .opacity(welcomeStage >= 2 ? 1 : 0)
                .offset(y: welcomeStage >= 2 ? 0 : 10)
            if welcomeStage >= 3 {
                TypewriterText(
                    text: "I'm Anticipy. I listen, I remember what matters, and I quietly do the work.",
                    font: .body
                )
                .multilineTextAlignment(.center)
                .frame(minHeight: 44, alignment: .top)
            } else {
                Color.clear.frame(height: 44)
            }
            Spacer()
            Spacer()
        }
        .padding(.horizontal, 30)
        .task {
            guard welcomeStage == 0 else { return }
            withAnimation(Theme.springSlow) { welcomeStage = 1 }
            Haptics.herMessage()
            try? await Task.sleep(nanoseconds: 450_000_000)
            withAnimation(Theme.spring) { welcomeStage = 2 }
            try? await Task.sleep(nanoseconds: 400_000_000)
            welcomeStage = 3
        }
    }

    @State private var cardsShown = 0

    private var howItWorks: some View {
        VStack(alignment: .leading, spacing: 18) {
            Spacer()
            Text("How it works")
                .font(Theme.display(32))
                .foregroundStyle(Theme.ivory)
            stepCard(icon: "waveform", title: "She listens",
                     text: "Your pendant hears your day and transcribes it — on-device if you prefer.")
                .opacity(cardsShown >= 1 ? 1 : 0)
                .offset(y: cardsShown >= 1 ? 0 : 14)
            stepCard(icon: "sparkles", title: "She remembers",
                     text: "She catches commitments like “I'll send that over” and keeps them until they're done.")
                .opacity(cardsShown >= 2 ? 1 : 0)
                .offset(y: cardsShown >= 2 ? 0 : 14)
            stepCard(icon: "cursorarrow.click.2", title: "She acts",
                     text: "She prepares the work in your browser — and always asks before anything is sent.")
                .opacity(cardsShown >= 3 ? 1 : 0)
                .offset(y: cardsShown >= 3 ? 0 : 14)
            Spacer()
            Spacer()
        }
        .padding(.horizontal, 28)
        .task(id: step) {
            guard step == 1, cardsShown == 0 else { return }
            for i in 1...3 {
                withAnimation(Theme.spring) { cardsShown = i }
                try? await Task.sleep(nanoseconds: 110_000_000)
            }
        }
    }

    /// The one thing she genuinely cannot work out on her own. Without it she
    /// can hear and prepare but can never reach you — and before this step
    /// existed, the number had to be typed into a server by hand.
    private var yourNumber: some View {
        VStack(spacing: 20) {
            Spacer()
            Image(systemName: "message")
                .font(.system(size: 54))
                .foregroundStyle(Theme.champagne)
            Text("Where should I reach you?")
                .font(Theme.display(28))
                .foregroundStyle(Theme.ivory)
            Text("When something needs your word, I'll text you here. Nothing else uses it.")
                .font(.callout)
                .foregroundStyle(Theme.gray)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 30)
            TextField("+1 604 555 0123", text: $phone)
                .keyboardType(.phonePad)
                .textContentType(.telephoneNumber)
                .font(.title3.monospacedDigit())
                .foregroundStyle(Theme.ivory)
                .multilineTextAlignment(.center)
                .padding(.vertical, 12)
                .background(RoundedRectangle(cornerRadius: 12).fill(Theme.surface))
                .padding(.horizontal, 40)
            if !phone.isEmpty, session.e164(phone) != nil {
                Label("That's you", systemImage: "checkmark.circle.fill")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(Theme.champagne)
                    .transition(.scale.combined(with: .opacity))
                    .onAppear { Haptics.tap() }
            } else if !phone.isEmpty {
                Text("That doesn't look like a full number yet.")
                    .font(.caption)
                    .foregroundStyle(Theme.gray)
            }
            Spacer()
        }
        .animation(Theme.spring, value: session.e164(phone) != nil)
    }

    private var pairPendant: some View {
        VStack(spacing: 20) {
            Spacer()
            ZStack {
                Circle()
                    .fill(Theme.surface)
                    .frame(width: 130, height: 130)
                LogoMark(size: 76)
                if pendant.state == .searching {
                    RadarRipple()
                }
            }
            Text("Pair your pendant")
                .font(Theme.display(32))
                .foregroundStyle(Theme.ivory)
            Text(pairStatusText)
                .font(.callout)
                .foregroundStyle(Theme.sand)
                .multilineTextAlignment(.center)
            if pendant.state == .connected {
                Label(pendant.deviceName ?? "Anticipy", systemImage: "checkmark.circle.fill")
                    .foregroundStyle(Theme.champagne)
                    .font(.body.weight(.semibold))
                    .transition(.scale.combined(with: .opacity))
                    .onAppear { Haptics.pairing() }
            } else {
                Button {
                    Haptics.engage()
                    pendant.startScan()
                } label: {
                    Label(pendant.state == .searching ? "Searching…" : "Search for my pendant",
                          systemImage: "dot.radiowaves.left.and.right")
                        .font(.callout.weight(.semibold))
                        .padding(.horizontal, 22)
                        .padding(.vertical, 12)
                        .background(Capsule().fill(Theme.surface))
                        .foregroundStyle(Theme.ivory)
                }
                .buttonStyle(.pressable)
            }
            Text("No pendant with you? Skip — Anticipy reconnects automatically whenever it's in range.")
                .font(.footnote)
                .foregroundStyle(Theme.gray)
                .multilineTextAlignment(.center)
            Spacer()
            Spacer()
        }
        .padding(.horizontal, 28)
    }

    private var pairStatusText: String {
        switch pendant.state {
        case .connected: return "Connected. It'll stay paired to this iPhone."
        case .searching: return "Hold your pendant close to your phone."
        case .connecting, .reconnecting: return "Found it — connecting…"
        case .unavailable: return "Turn on Bluetooth in Settings to pair."
        case .off: return "Wear it. Charge it. That's the whole manual."
        }
    }

    private var browserAgent: some View {
        VStack(alignment: .leading, spacing: 16) {
            Spacer()
            Text("Your hands on\nthe computer")
                .font(Theme.display(32))
                .foregroundStyle(Theme.ivory)
            Text("The Anticipy browser agent works inside your own Chrome — using your logged-in accounts, never your passwords.")
                .font(.callout)
                .foregroundStyle(Theme.sand)
            numbered(1, "On your computer, open the setup guide below")
            numbered(2, "Add Anticipy to Chrome (it walks you through it)")
            numbered(3, "Type the 6-digit code it shows you here")
            if let setup = URL(string: "https://backend-production-61e0a.up.railway.app/setup.html") {
                ShareLink(item: setup) {
                    Label("Send the setup guide to your computer", systemImage: "square.and.arrow.up")
                        .font(.callout.weight(.semibold))
                }
                .padding(.top, 2)
            }
            if session.agentPaired {
                HStack(spacing: 8) {
                    BreathingDot(size: 8)
                    Text("Paired — your browser is hers now.")
                        .font(.footnote)
                        .foregroundStyle(Theme.gray)
                }
                .padding(.top, 4)
                .transition(.scale.combined(with: .opacity))
                .onAppear { Haptics.pairing() }
            } else {
                HStack(spacing: 10) {
                    TextField("6-digit code", text: $agentCode)
                        .keyboardType(.numberPad)
                        .font(.title3.monospaced())
                        .padding(10)
                        .background(RoundedRectangle(cornerRadius: 10).fill(Theme.surface))
                        .foregroundStyle(Theme.ivory)
                    Button("Pair") {
                        Haptics.engage()
                        Task {
                            let ok = await session.pairAgent(code: agentCode)
                            withAnimation(Theme.spring) { agentPairFailed = !ok }
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(agentCode.count != 6)
                }
                .padding(.top, 4)
                if agentPairFailed {
                    Text("That code didn't match — it's in the Anticipy extension popup.")
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            }
            Spacer()
            Spacer()
        }
        .padding(.horizontal, 28)
    }

    private func numbered(_ n: Int, _ text: String) -> some View {
        HStack(spacing: 12) {
            Text("\(n)")
                .font(.callout.weight(.bold))
                .frame(width: 28, height: 28)
                .background(Circle().fill(Theme.surface))
                .foregroundStyle(Theme.champagne)
            Text(text)
                .font(.callout)
                .foregroundStyle(Theme.ivory)
        }
    }

    private var transcription: some View {
        VStack(alignment: .leading, spacing: 16) {
            Spacer()
            Text("Where should\nwords become text?")
                .font(Theme.display(32))
                .foregroundStyle(Theme.ivory)
            engineOption("local", icon: "iphone", title: "On this iPhone",
                         text: "Private. Audio never leaves your phone.")
            engineOption("cloud", icon: "cloud", title: "In the cloud",
                         text: "Fastest and most accurate. Streamed securely, never stored.")
            Text("You can change this anytime in Settings.")
                .font(.footnote)
                .foregroundStyle(Theme.gray)
            Spacer()
            Spacer()
        }
        .padding(.horizontal, 28)
    }

    private func engineOption(_ value: String, icon: String, title: String, text: String) -> some View {
        Button {
            Haptics.engage()
            withAnimation(Theme.spring) { engine = value }
        } label: {
            HStack(spacing: 14) {
                Image(systemName: icon)
                    .font(.title3)
                    .foregroundStyle(Theme.champagne)
                    .frame(width: 30)
                VStack(alignment: .leading, spacing: 3) {
                    Text(title).font(.body.weight(.semibold)).foregroundStyle(Theme.ivory)
                    Text(text).font(.footnote).foregroundStyle(Theme.gray)
                }
                Spacer()
                Image(systemName: engine == value ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(engine == value ? Theme.champagne : Theme.stroke)
            }
            .padding(16)
            .background(
                RoundedRectangle(cornerRadius: 18)
                    .fill(Theme.card)
                    .overlay(
                        RoundedRectangle(cornerRadius: 18)
                            .strokeBorder(engine == value ? Theme.champagne.opacity(0.6) : Theme.stroke)
                    )
                    .shadow(color: engine == value ? Theme.champagne.opacity(0.15) : .clear,
                            radius: 12, y: 4)
            )
            .scaleEffect(engine == value ? 1.02 : 1)
        }
        .buttonStyle(.pressable)
    }

    private func stepCard(icon: String, title: String, text: String) -> some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(Theme.champagne)
                .frame(width: 30)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.body.weight(.semibold)).foregroundStyle(Theme.ivory)
                Text(text).font(.footnote).foregroundStyle(Theme.gray)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
    }
}

/// A repeating radar ripple for scanning states — one ring expanding and
/// fading out from the logo, forever, until the searching state ends.
struct RadarRipple: View {
    @State private var expand = false

    var body: some View {
        Circle()
            .stroke(Theme.champagne.opacity(0.5), lineWidth: 2)
            .frame(width: 130, height: 130)
            .scaleEffect(expand ? 1.45 : 1.0)
            .opacity(expand ? 0 : 0.8)
            .animation(.easeOut(duration: 1.6).repeatForever(autoreverses: false), value: expand)
            .onAppear { expand = true }
    }
}
