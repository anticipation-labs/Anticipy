import SwiftUI

/// THE PENDANT'S BEAT IN FIRST RUN, and the flow behind it.
///
/// Drawn in the same grammar as the rest of first run — `OnboardingKit`'s
/// stepper, question type, pills and FAB — so it reads as one product rather
/// than as a hardware detour bolted on. `PendantOnboardingPolicy` decides
/// everything this file draws; the spec is
/// `research/2026-09-06-pendant-onboarding-design.md`.
///
/// ── THE SHAPE, AND WHY IT IS THIS WAY ROUND ───────────────────────────────
///
/// The offer screen's PRIMARY control is "Continue without one". Owning a
/// pendant is the quiet second line. Oura does the opposite — "Start" means
/// owning a ring there — and they are right to, because they sell rings. This
/// product works completely on the phone, so the person without hardware is
/// not taking a lesser path and must not be shown one: no "skip", no "maybe
/// later", nothing greyed.
///
/// Everything behind the offer keeps a way out on screen at all times, because
/// somebody who tapped "I have a pendant" by mistake must never be held behind
/// a device they do not own.
///
/// ── NO RADIO IS TOUCHED UNTIL THE PERSON ASKS ─────────────────────────────
///
/// `PendantManager.startScan()` is called from exactly one place — `look()` —
/// and only once the looking beat is on screen. Same rule as the microphone:
/// the permission iOS raises is raised where it has just been explained, never
/// before somebody chose to go looking. The runner holds that.
struct PendantOnboarding: View {
    /// Called when the person is finished with the pendant, either way.
    var onFinished: () -> Void

    @EnvironmentObject private var pendant: PendantManager
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    @State private var beat: PendantOnboardingPolicy.Beat = .offer
    @State private var lookingSince: Date?
    @State private var asked = false

    private typealias P = PendantOnboardingPolicy

    var body: some View {
        ZStack {
            OnboardTheme.ground.ignoresSafeArea()
            switch beat {
            case .offer:   offer
            case .wake:    wake
            case .looking: looking
            case .pairing: looking          // the same screen; the radio's face changes
            case .wearing: wearing
            case .done:    done
            }
        }
        .animation(reduceMotion ? nil : Theme.springSlow, value: beat)
        .onChange(of: pendant.state) { state in
            // Arriving at connected is the only thing that moves the flow on by
            // itself. Everything else waits for a person.
            if state == .connected, beat == .looking || beat == .pairing {
                Haptics.taskDone()
                withAnimation(Theme.springSlow) { beat = .wearing }
            }
        }
    }

    // MARK: - 1. The offer, which almost everybody leaves from

    private var offer: some View {
        VStack(spacing: 0) {
            PendantHeroImage(name: "PendantHero", maxHeight: 360)
                .accessibilityLabel("The Anticipy pendant, a small brushed steel capsule")
                .accessibilityHidden(false)

            VStack(alignment: .leading, spacing: 12) {
                Text(P.Copy.offerTitle)
                    .font(OnboardFont.question(27))
                    .foregroundStyle(OnboardTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                Text(P.Copy.offerBody)
                    .font(.system(size: 16))
                    .foregroundStyle(OnboardTheme.text2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 24)
            .padding(.top, 4)

            Spacer(minLength: 16)

            VStack(spacing: 12) {
                // PRIMARY. The road without hardware.
                Button {
                    Haptics.engage()
                    onFinished()
                } label: {
                    Text(P.Copy.offerPrimary)
                }
                .buttonStyle(OnboardPillStyle(kind: .black))

                // Quiet. Deliberately not a pill: this is the branch few take.
                Button {
                    Haptics.engage()
                    withAnimation(Theme.springSlow) { beat = .wake }
                } label: {
                    Text(P.Copy.offerSecondary)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(OnboardTheme.champagneInk)
                        .frame(maxWidth: .infinity, minHeight: 44)
                }
                .buttonStyle(OnboardPressStyle())

                Text(P.Copy.offerFootnote)
                    .font(.system(size: 13))
                    .foregroundStyle(OnboardTheme.muted)
                    .multilineTextAlignment(.center)
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 18)
        }
    }

    // MARK: - 2. Wake it

    private var wake: some View {
        VStack(spacing: 0) {
            // The product sits at the TOP here, the way Oura's connect screen
            // puts the charger above the words: at this moment the person is
            // holding the object and matching it to the picture.
            PendantHeroImage(name: "PendantConnect", maxHeight: 330)

            VStack(alignment: .leading, spacing: 12) {
                Text(P.Copy.wakeTitle)
                    .font(OnboardFont.question(27))
                    .foregroundStyle(OnboardTheme.ink)
                Text(P.Copy.wakeBody)
                    .font(.system(size: 16))
                    .foregroundStyle(OnboardTheme.text2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 24)

            Spacer(minLength: 12)
            footer(primary: "Look for it") { look() }
        }
    }

    // MARK: - 3 & 4. Looking, and pairing

    private var looking: some View {
        let face = P.face(radio)
        return VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 14) {
                PendantPulse(active: face.searching && !reduceMotion)
                VStack(alignment: .leading, spacing: 5) {
                    Text(face.title)
                        .font(.system(size: 21, weight: .semibold))
                        .foregroundStyle(OnboardTheme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(face.body)
                        .font(.system(size: 15))
                        .foregroundStyle(OnboardTheme.text2)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 24)
            .padding(.top, 28)
            .accessibilityElement(children: .combine)

            if !candidates.isEmpty {
                ScrollView {
                    VStack(spacing: 10) {
                        ForEach(P.ordered(candidates)) { c in
                            CandidateRow(candidate: c) { connect(c) }
                        }
                    }
                    .padding(.horizontal, 24)
                    .padding(.top, 22)
                }
            } else {
                Spacer()
            }

            Spacer(minLength: 12)
            footer(primary: nil)
        }
        .onAppear { if lookingSince == nil { lookingSince = Date() } }
    }

    // MARK: - 5. Wear it

    private var wearing: some View {
        ZStack(alignment: .bottom) {
            Image("PendantWorn")
                .resizable()
                .scaledToFill()
                .ignoresSafeArea()
                .accessibilityHidden(true)
            LinearGradient(colors: [.clear, OnboardTheme.ground.opacity(0.92), OnboardTheme.ground],
                           startPoint: .init(x: 0.5, y: 0.34), endPoint: .bottom)
                .ignoresSafeArea()
            VStack(alignment: .leading, spacing: 12) {
                Text(P.Copy.wearTitle)
                    .font(OnboardFont.question(27))
                    .foregroundStyle(OnboardTheme.ink)
                Text(P.Copy.wearBody)
                    .font(.system(size: 16))
                    .foregroundStyle(OnboardTheme.text2)
                    .fixedSize(horizontal: false, vertical: true)
                Button {
                    Haptics.engage()
                    withAnimation(Theme.springSlow) { beat = .done }
                } label: { Text("Got it") }
                    .buttonStyle(OnboardPillStyle(kind: .black))
                    .padding(.top, 8)
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 26)
        }
    }

    // MARK: - 6. Done

    private var done: some View {
        VStack(spacing: 18) {
            Spacer()
            OnboardMark(size: 52)
            Text(P.Copy.doneTitle)
                .font(OnboardFont.question(26))
                .foregroundStyle(OnboardTheme.ink)
            Text(P.doneLine(deviceName: pendant.deviceName))
                .font(.system(size: 16))
                .foregroundStyle(OnboardTheme.text2)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 34)
            Spacer()
            Button { Haptics.engage(); onFinished() } label: { Text("Continue") }
                .buttonStyle(OnboardPillStyle(kind: .black))
                .padding(.horizontal, 24)
                .padding(.bottom, 20)
        }
    }

    // MARK: - Shared foot

    @ViewBuilder private func footer(primary: String?, action: @escaping () -> Void = {}) -> some View {
        VStack(spacing: 10) {
            if let primary {
                Button { Haptics.engage(); action() } label: { Text(primary) }
                    .buttonStyle(OnboardPillStyle(kind: .black))
            }
            // THE WAY OUT, on every screen behind the offer. Somebody who
            // tapped "I have a pendant" by mistake is one tap from the ordinary
            // road, and it is never phrased as a failure.
            Button {
                pendant.disconnect()
                onFinished()
            } label: {
                Text(P.Copy.wayOut)
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(OnboardTheme.muted)
                    .frame(maxWidth: .infinity, minHeight: 44)
            }
            .buttonStyle(OnboardPressStyle())
        }
        .padding(.horizontal, 24)
        .padding(.bottom, 18)
    }

    // MARK: - The radio, read rather than invented

    private var radio: P.Radio {
        switch pendant.state {
        case .warmingUp:    return .warmingUp
        case .unavailable:  return .switchedOff
        case .connecting:   return .connecting(name: pendant.deviceName ?? "your pendant")
        case .connected:    return .connected(name: pendant.deviceName ?? "Your pendant")
        case .searching, .reconnecting, .off:
            if !candidates.isEmpty { return .foundSomething(count: candidates.count) }
            if let since = lookingSince, Date().timeIntervalSince(since) > P.patience {
                return .nothingFound
            }
            return .scanning
        }
    }

    /// What the radio has actually seen. `PendantManager` connects to the first
    /// pendant it recognises rather than listing them, so today this is either
    /// empty or the one device it latched onto — drawn as a list because the
    /// screen must already be right when the manager grows a real inventory.
    private var candidates: [P.Candidate] {
        guard let name = pendant.deviceName, pendant.state != .connected else { return [] }
        return [P.Candidate(id: name, name: name, rssi: pendant.rssi)]
    }

    /// THE ONLY CALL SITE. Nothing before the looking beat may reach the radio.
    private func look() {
        guard !asked else { return }
        asked = true
        lookingSince = Date()
        withAnimation(Theme.springSlow) { beat = .looking }
        pendant.startScan()
    }

    private func connect(_ c: P.Candidate) {
        Haptics.engage()
        withAnimation(Theme.springSlow) { beat = .pairing }
    }
}

/// A product photograph that MELTS INTO THE PAGE.
///
/// The renders are lit on their own cream, which is close to `OnboardTheme.ground`
/// but not identical, so dropped in plainly they read as a pasted rectangle with
/// four visible edges. Oura's heroes have no edges at all — the vignette runs
/// off the screen. This feathers all four sides so the object floats on the same
/// ground the words sit on, and blends multiply-free so the light scheme keeps
/// its warmth.
private struct PendantHeroImage: View {
    let name: String
    var maxHeight: CGFloat

    var body: some View {
        Image(name)
            .resizable()
            .scaledToFill()
            .frame(maxWidth: .infinity)
            .frame(height: maxHeight)
            .clipped()
            .mask(
                // Feathered on every side; the top and bottom fade hardest
                // because that is where the copy and the chrome meet it.
                LinearGradient(stops: [
                    .init(color: .clear, location: 0.00),
                    .init(color: .black, location: 0.14),
                    .init(color: .black, location: 0.80),
                    .init(color: .clear, location: 1.00),
                ], startPoint: .top, endPoint: .bottom)
                .mask(
                    LinearGradient(stops: [
                        .init(color: .clear, location: 0.00),
                        .init(color: .black, location: 0.10),
                        .init(color: .black, location: 0.90),
                        .init(color: .clear, location: 1.00),
                    ], startPoint: .leading, endPoint: .trailing)
                )
            )
            .accessibilityHidden(true)
    }
}

/// A found device. Signal is four quiet bars or nothing at all — never a
/// percentage, because RSSI is not one and a number invites belief.
private struct CandidateRow: View {
    let candidate: PendantOnboardingPolicy.Candidate
    var onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(spacing: 14) {
                OnboardMark(size: 26)
                Text(candidate.name)
                    .font(.system(size: 16, weight: .medium))
                    .foregroundStyle(OnboardTheme.ink)
                    .lineLimit(1)
                Spacer(minLength: 8)
                if let bars = candidate.nearness {
                    HStack(alignment: .bottom, spacing: 2) {
                        ForEach(0..<4) { i in
                            Capsule()
                                .fill(i <= bars ? OnboardTheme.champagne : OnboardTheme.track)
                                .frame(width: 3, height: 6 + CGFloat(i) * 3)
                        }
                    }
                    .accessibilityHidden(true)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 15)
            .background(RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(OnboardTheme.card))
        }
        .buttonStyle(OnboardPressStyle())
        .accessibilityLabel(candidate.name)
        .accessibilityHint("Connect to this pendant")
    }
}

/// The looking indicator: the product's own mark, breathing. Still when nothing
/// is being searched for, because a moving indicator over a stopped radio is
/// the same lie as a moving waveform over a closed microphone.
private struct PendantPulse: View {
    var active: Bool

    var body: some View {
        TimelineView(.animation(paused: !active)) { context in
            let t = context.date.timeIntervalSinceReferenceDate
            let breath = active ? (sin(t * 2.1) + 1) / 2 : 0.5
            ZStack {
                Circle()
                    .fill(OnboardTheme.champagne.opacity(0.10 + 0.10 * breath))
                    .frame(width: 46 + 8 * breath, height: 46 + 8 * breath)
                OnboardMark(size: 26)
            }
            .frame(width: 56, height: 56)
        }
        .accessibilityHidden(true)
    }
}
