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

    private let totalSteps = 5

    var body: some View {
        ZStack {
            Theme.ink.ignoresSafeArea()
            VStack(spacing: 0) {
                progressDots
                TabView(selection: $step) {
                    welcome.tag(0)
                    howItWorks.tag(1)
                    pairPendant.tag(2)
                    browserAgent.tag(3)
                    transcription.tag(4)
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
                if step < totalSteps - 1 {
                    step += 1
                } else {
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
            if step > 0, step < totalSteps - 1 {
                Button("Skip for now") { step += 1 }
                    .font(.footnote)
                    .foregroundStyle(Theme.gray)
            }
        }
        .padding(.horizontal, 28)
        .padding(.bottom, 26)
    }

    // MARK: - Steps

    private var welcome: some View {
        VStack(spacing: 22) {
            Spacer()
            LogoMark(size: 120)
            Text("Anticipy")
                .font(Theme.display(44))
                .foregroundStyle(Theme.ivory)
            Text("Meet Annie. She listens, remembers\nwhat matters, and quietly does the work.")
                .font(.body)
                .foregroundStyle(Theme.sand)
                .multilineTextAlignment(.center)
            Spacer()
            Spacer()
        }
        .padding(.horizontal, 30)
    }

    private var howItWorks: some View {
        VStack(alignment: .leading, spacing: 18) {
            Spacer()
            Text("How it works")
                .font(Theme.display(32))
                .foregroundStyle(Theme.ivory)
            stepCard(icon: "waveform", title: "She listens",
                     text: "Your pendant hears your day and transcribes it — on-device if you prefer.")
            stepCard(icon: "sparkles", title: "She remembers",
                     text: "Annie catches commitments like “I'll send that over” and keeps them until they're done.")
            stepCard(icon: "cursorarrow.click.2", title: "She acts",
                     text: "Annie prepares the work in your browser — and always asks before anything is sent.")
            Spacer()
            Spacer()
        }
        .padding(.horizontal, 28)
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
                    Circle()
                        .stroke(Theme.champagne.opacity(0.5), lineWidth: 2)
                        .frame(width: 130, height: 130)
                        .scaleEffect(1.15)
                        .opacity(0.5)
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
            } else {
                Button {
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
            numbered(1, "On your computer, visit anticipy.ai/agent")
            numbered(2, "Add Anticipy to Chrome")
            numbered(3, "It links to this phone automatically")
            HStack(spacing: 8) {
                Circle()
                    .fill(session.backendReachable ? Theme.champagne : Theme.stroke)
                    .frame(width: 8, height: 8)
                Text(session.backendReachable ? "Agent link ready" : "Waiting for your computer…")
                    .font(.footnote)
                    .foregroundStyle(Theme.gray)
            }
            .padding(.top, 4)
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
            engine = value
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
            )
        }
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
