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
    @State private var explainingBluetooth = false

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
            // A slow breath on the offer screen: it draws the eye to the one
            // hole in the object, which is the whole product.
            PendantHeroImage(art: .hero, maxHeight: 360)
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
            // Here the copy says "hold it until the light breathes", so the
            // picture had better be breathing.
            PendantHeroImage(art: .resting, maxHeight: 330)

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
            VStack(spacing: 10) {
                // Oura's "Why we ask", in this product's voice. Reachable
                // BEFORE iOS raises its dialog, so nobody refuses a permission
                // they were never given a reason for.
                Button { explainingBluetooth = true } label: {
                    Label(P.Copy.whyBluetooth, systemImage: "info.circle")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(OnboardTheme.champagneInk)
                        .frame(maxWidth: .infinity, minHeight: 44)
                }
                .buttonStyle(OnboardPressStyle())
            }
            .padding(.horizontal, 24)
            footer(primary: nil)
        }
        .onAppear { if lookingSince == nil { lookingSince = Date() } }
        .sheet(isPresented: $explainingBluetooth) {
            BluetoothPromises()
        }
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

/// WHERE THE MICROPHONE HOLE IS IN EACH RENDER.
///
/// Found by blob analysis over the 4K originals rather than by eye: the hole is
/// the one small, round, well-filled dark region sitting inside the metal, and
/// it was located at (1730, 2082) of 3584x4800 in the hero and (1824, 2704) in
/// the resting shot, then verified by cropping both and looking. Stored
/// normalised so it survives any later resize of the asset — but NOT any
/// re-render. A regenerated image moves the hole, and these two numbers are the
/// only thing that would then be wrong, silently. If you replace an asset,
/// re-run the detector.
struct PendantArt {
    let asset: String
    /// Pixel size of the underlying image, needed to place the glow exactly
    /// once the view has scaled it to fill.
    let size: CGSize
    /// The microphone hole, in unit space of the image.
    let hole: UnitPoint

    static let hero = PendantArt(asset: "PendantHero",
                                 size: CGSize(width: 3584, height: 4800),
                                 hole: UnitPoint(x: 0.4827, y: 0.4338))
    static let resting = PendantArt(asset: "PendantConnect",
                                    size: CGSize(width: 3584, height: 4800),
                                    hole: UnitPoint(x: 0.5089, y: 0.5633))
}

/// A product photograph that MELTS INTO THE PAGE, with the pendant's own light
/// breathing in its microphone hole.
///
/// The renders are lit on their own cream, which is close to `OnboardTheme.ground`
/// but not identical, so dropped in plainly they read as a pasted rectangle with
/// four visible edges. Oura's heroes have no edges at all — the vignette runs
/// off the screen. This feathers all four sides so the object floats on the same
/// ground the words sit on.
///
/// THE GLOW IS PLACED, NOT GUESSED. `scaledToFill` crops, so the hole's unit
/// point has to be carried through the same transform the image gets: fill
/// scale, then the centring offset. Anything simpler puts the light beside the
/// hole on one screen size and inside it on another.
private struct PendantHeroImage: View {
    let art: PendantArt
    var maxHeight: CGFloat
    /// Whether the light is breathing. A still pendant on a screen that has not
    /// asked anybody to wake it is the honest drawing.
    var alive: Bool = true

    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        GeometryReader { geo in
            let fill = max(geo.size.width / art.size.width,
                           geo.size.height / art.size.height)
            let shown = CGSize(width: art.size.width * fill, height: art.size.height * fill)
            let origin = CGPoint(x: (geo.size.width - shown.width) / 2,
                                 y: (geo.size.height - shown.height) / 2)
            let hole = CGPoint(x: origin.x + art.hole.x * shown.width,
                               y: origin.y + art.hole.y * shown.height)

            ZStack {
                Image(art.asset)
                    .resizable()
                    .scaledToFill()
                    .frame(width: geo.size.width, height: geo.size.height)
                    .clipped()
                PendantGlow(alive: alive && !reduceMotion)
                    .position(hole)
                    .allowsHitTesting(false)
            }
            .frame(width: geo.size.width, height: geo.size.height)
            .mask(
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
        }
        .frame(height: maxHeight)
        .accessibilityHidden(true)
    }
}

/// What Bluetooth is for, before iOS asks rather than after. The same shape as
/// the microphone beat's promises sheet, because it is the same promise made
/// about a different radio.
private struct BluetoothPromises: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text(PendantOnboardingPolicy.Copy.whyBluetoothTitle)
                    .font(OnboardFont.question(24))
                    .foregroundStyle(OnboardTheme.ink)
                    .padding(.top, 8)
                ForEach(PendantOnboardingPolicy.Copy.whyBluetoothPoints, id: \.self) { line in
                    HStack(alignment: .top, spacing: 12) {
                        Circle()
                            .fill(OnboardTheme.champagne)
                            .frame(width: 5, height: 5)
                            .padding(.top, 8)
                        Text(line)
                            .font(.system(size: 15))
                            .foregroundStyle(OnboardTheme.text2)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                Button { dismiss() } label: { Text("Done") }
                    .buttonStyle(OnboardPillStyle(kind: .soft))
                    .padding(.top, 6)
            }
            .padding(24)
        }
        .background(OnboardTheme.ground)
        .presentationDetents([.medium, .large])
    }
}

/// The pendant's light, breathing in its own microphone hole.
///
/// Three layers, because one blurred circle reads as a smudge: a wide soft halo
/// that spills onto the metal, a tight core the size of the hole itself, and a
/// hairline rim that keeps the hole's edge legible while it is lit. The whole
/// thing is champagne, the product's own accent, so it looks like the object's
/// light rather than a UI element parked on top of a photograph.
///
/// Still under Reduce Motion, and still on any screen that has not asked
/// somebody to wake the pendant — a light that breathes on a device nobody has
/// touched is the same lie as a moving waveform over a closed microphone.
private struct PendantGlow: View {
    var alive: Bool

    var body: some View {
        TimelineView(.animation(paused: !alive)) { context in
            let t = context.date.timeIntervalSinceReferenceDate
            // Slow — a breath, near enough to a resting human one, not a blink.
            let breath = alive ? (sin(t * 1.35) + 1) / 2 : 0.45
            ZStack {
                Circle()
                    .fill(RadialGradient(
                        colors: [OnboardTheme.champagne.opacity(0.55 * (0.35 + 0.65 * breath)),
                                 OnboardTheme.champagne.opacity(0)],
                        center: .center, startRadius: 0, endRadius: 26))
                    .frame(width: 52, height: 52)
                    .blur(radius: 4)
                Circle()
                    .fill(OnboardTheme.champagne.opacity(0.72 + 0.24 * breath))
                    .frame(width: 7.5, height: 7.5)
                    .blur(radius: 1.4)
                Circle()
                    .strokeBorder(OnboardTheme.champagne.opacity(0.30 + 0.30 * breath),
                                  lineWidth: 0.7)
                    .frame(width: 11, height: 11)
            }
        }
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
                VStack(alignment: .leading, spacing: 2) {
                    Text(candidate.name)
                        .font(.system(size: 16, weight: .medium))
                        .foregroundStyle(OnboardTheme.ink)
                        .lineLimit(1)
                    // THE IDENTIFIER, the way Oura prints a ring's MAC under
                    // its name. It is the only way to tell two pendants apart
                    // in one room, and printing it is more honest than asking
                    // somebody to guess.
                    if let id = candidate.shortID {
                        Text(id)
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundStyle(OnboardTheme.muted)
                            .lineLimit(1)
                    }
                }
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
