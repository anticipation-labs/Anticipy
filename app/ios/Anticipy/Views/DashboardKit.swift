import SwiftUI

/// THE CONVERSATION DASHBOARD'S PARTS.
///
/// Two references, one screen. The capture moment takes its grammar from a
/// voice-capture sheet — a warm ground, the things you said appearing as cards
/// while you keep talking, and one row of controls: hold, the live wave, done.
/// The thread takes its grammar from an assistant conversation — your line as
/// a tinted bubble, her working state as a quiet line with a spinner, her
/// answer as PROSE rather than a fourth rounded rectangle, and one ask bar at
/// the foot.
///
/// Every colour is a Theme role (`run_theme_contract_tests.sh`), and the two
/// grounds are the product's own cream and champagne rather than the
/// references' red and blue: this is Anticipy's screen, drawn in Anticipy's
/// paint. Red stays reserved for alarm, which is why the affirmative in the
/// capture row is ink and not the reference's red circle.
enum DashMetric {
    static let gutter: CGFloat = 20
    static let cardRadius: CGFloat = 20
    static let bubbleRadius: CGFloat = 20
    static let control: CGFloat = 56
    static let bar: CGFloat = 52
    /// How much room the foot of the screen needs, so the last turn is never
    /// under the ask bar.
    static let footClearance: CGFloat = 132
}

// MARK: - Grounds

/// The thread's ground: cream with a slow champagne bloom low in the frame.
/// Still by default — a page you read should not move — and it is the capture
/// ground that comes alive.
struct ThreadGround: View {
    var body: some View {
        ZStack {
            OnboardTheme.ground
            RadialGradient(colors: [OnboardTheme.champagne.opacity(0.16), .clear],
                           center: .init(x: 0.5, y: 1.02), startRadius: 8, endRadius: 460)
            RadialGradient(colors: [OnboardTheme.champagne.opacity(0.10), .clear],
                           center: .init(x: 0.08, y: 0.72), startRadius: 4, endRadius: 300)
            GrainLayer()
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
    }
}

/// The capture ground: the same cream, lifted by a warm bloom that breathes
/// while she is actually hearing something. The breath is the honest signal —
/// it stops when the microphone does.
struct CaptureGround: View {
    var alive: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        ZStack {
            OnboardTheme.ground
            TimelineView(.animation(paused: !alive || reduceMotion)) { context in
                let t = context.date.timeIntervalSinceReferenceDate
                let breath = alive && !reduceMotion ? (sin(t * 0.8) + 1) / 2 : 0.5
                ZStack {
                    RadialGradient(
                        colors: [OnboardTheme.Welcome.poolAmber.opacity(0.30 + 0.10 * breath), .clear],
                        center: .init(x: 0.5, y: 0.92), startRadius: 10, endRadius: 520)
                    RadialGradient(
                        colors: [OnboardTheme.champagne.opacity(0.20 + 0.08 * (1 - breath)), .clear],
                        center: .init(x: 0.16, y: 0.30), startRadius: 8, endRadius: 340)
                    RadialGradient(
                        colors: [OnboardTheme.Welcome.poolCream.opacity(0.24), .clear],
                        center: .init(x: 0.88, y: 0.16), startRadius: 6, endRadius: 300)
                }
            }
            GrainLayer()
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
    }
}

// MARK: - The live wave

/// The wave in the capture row. It is driven by the clock, not by a level
/// meter, and says so: a bar chart that claims to be your voice while reading
/// nothing is a lie a person can catch by covering the microphone. Still when
/// nothing is being heard.
struct LiveWave: View {
    var alive: Bool
    var bars: Int = 26
    var color: Color = OnboardTheme.champagne
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        TimelineView(.animation(paused: !alive || reduceMotion)) { context in
            let t = context.date.timeIntervalSinceReferenceDate
            HStack(alignment: .center, spacing: 3) {
                ForEach(0..<bars, id: \.self) { i in
                    Capsule()
                        .fill(color.opacity(alive ? 0.95 : 0.35))
                        .frame(width: 3, height: height(i, t))
                }
            }
        }
        .frame(height: 34)
        .accessibilityHidden(true)
    }

    private func height(_ i: Int, _ t: TimeInterval) -> CGFloat {
        guard alive, !reduceMotion else { return 5 }
        // Two travelling waves, so the row never falls into a visible loop.
        let p = Double(i)
        let a = sin(t * 6.2 + p * 0.55)
        let b = sin(t * 3.1 - p * 0.31)
        // Taper the ends, the way a spoken burst tapers.
        let edge = sin(Double.pi * p / Double(max(bars - 1, 1)))
        let v = (a * 0.6 + b * 0.4 + 1) / 2
        return 5 + CGFloat(v * edge) * 27
    }
}

// MARK: - Capture

/// A thing she heard, appearing while you keep talking. The circle is not a
/// checkbox: nothing on this screen is completed by tapping it, and a control
/// that looks tappable and is not is worse than no control — so it is drawn as
/// a mark, and the whole card is the tap target for opening it later.
struct CaptureCard: View {
    var title: String
    var meta: [CaptureChip] = []

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Circle()
                .strokeBorder(OnboardTheme.champagne.opacity(0.55),
                              style: StrokeStyle(lineWidth: 1.5, dash: [3, 3]))
                .frame(width: 20, height: 20)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 6) {
                Text(title)
                    .font(.system(size: 17, weight: .medium))
                    .foregroundStyle(OnboardTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                if !meta.isEmpty {
                    HStack(spacing: 12) {
                        ForEach(meta) { chip in
                            Label {
                                Text(chip.text).font(.system(size: 13))
                            } icon: {
                                Image(systemName: chip.icon).font(.system(size: 11))
                            }
                            .foregroundStyle(chip.tinted ? OnboardTheme.champagneInk : OnboardTheme.muted)
                        }
                    }
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .background(RoundedRectangle(cornerRadius: DashMetric.cardRadius, style: .continuous)
            .fill(OnboardTheme.card))
        .shadow(color: OnboardTheme.inkFixed.opacity(0.07), radius: 14, y: 8)
        .accessibilityElement(children: .combine)
    }
}

struct CaptureChip: Identifiable, Equatable {
    let id = UUID()
    var icon: String
    var text: String
    var tinted: Bool = false
}

/// Hold, the wave, done. Three targets, all at least 44pt, and the done
/// button is the only filled one because it is the only one that ends
/// something.
struct CaptureControls: View {
    var alive: Bool
    var paused: Bool
    var onHold: () -> Void
    var onDone: () -> Void

    var body: some View {
        HStack(spacing: 16) {
            Button(action: onHold) {
                Image(systemName: paused ? "play.fill" : "pause.fill")
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(OnboardTheme.ink)
                    .frame(width: DashMetric.control, height: DashMetric.control)
                    .background(Circle().fill(OnboardTheme.field))
            }
            .buttonStyle(OnboardPressStyle())
            .accessibilityLabel(paused ? "Resume listening" : "Hold listening")

            LiveWave(alive: alive)
                .frame(maxWidth: .infinity)

            Button(action: onDone) {
                Image(systemName: "checkmark")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundStyle(OnboardTheme.onInk)
                    .frame(width: DashMetric.control, height: DashMetric.control)
                    .background(Circle().fill(OnboardTheme.ink))
            }
            .buttonStyle(OnboardPressStyle())
            .accessibilityLabel("Done listening")
        }
    }
}

// MARK: - Thread turns

/// Something the owner said. Tinted and set to the right, the way every
/// conversation on this phone sets the reader's own words.
struct OwnerTurn: View {
    var text: String
    /// The tagger's verdict: "owner", "other", or nil when the phone could not
    /// say. Every line used to render on the right in the owner's own bubble
    /// regardless of who spoke it, so a meeting with three people read back as
    /// one person's monologue with everybody else's words in their mouth.
    var speaker: String? = nil

    /// Only an explicit "other" moves a line across. nil is NOT other — it is
    /// the phone saying it could not tell, and guessing in either direction
    /// would put words in somebody's mouth. An untagged line stays where the
    /// app has always drawn it, and says nothing about who spoke.
    private var isSomebodyElse: Bool { speaker == "other" }

    var body: some View {
        HStack {
            if !isSomebodyElse { Spacer(minLength: 48) }
            VStack(alignment: isSomebodyElse ? .leading : .trailing, spacing: 3) {
                if isSomebodyElse {
                    // NOT A NAME. The tagger says "owner" or "other" and the
                    // roster holds no names, so this says exactly what is
                    // known and no more. Claiming a name the product does not
                    // have would be worse than saying nothing.
                    Text("Someone else")
                        .font(.system(size: 11, weight: .semibold))
                        .tracking(0.6)
                        .foregroundStyle(OnboardTheme.muted)
                }
                Text(text)
                    .font(.system(size: 16))
                    .foregroundStyle(OnboardTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 11)
                    .background(RoundedRectangle(cornerRadius: DashMetric.bubbleRadius,
                                                 style: .continuous)
                        .fill(isSomebodyElse ? OnboardTheme.card : OnboardTheme.field))
            }
            if isSomebodyElse { Spacer(minLength: 48) }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(isSomebodyElse ? "Someone else said: \(text)"
                                           : "You said: \(text)")
    }
}

/// SPEECH SHE HAS NOT COME BACK ON — a count, never the words.
///
/// The owner asked for this on 2026-09-06: "hide the transcript and only show
/// the task." Between a sentence leaving the phone and the brain stamping a
/// goal there are at least five seconds, and this row is what stands in that
/// window. It says what the PHONE knows — how many, and that nothing has come
/// back — and nothing about what was said, because the phone does not know
/// that and is not allowed to guess.
///
/// Deliberately the quietest thing on the thread. It is not news; it is the
/// absence of news, and a row that shouted would make every ordinary pause
/// look like a problem.
struct PendingTurn: View {
    var count: Int

    private var line: String {
        count == 1 ? "Heard you. Nothing back on it yet."
                   : "Heard \(count) things. Nothing back on them yet."
    }

    var body: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(OnboardTheme.muted.opacity(0.5))
                .frame(width: 5, height: 5)
            Text(line)
                .font(.system(size: 13))
                .foregroundStyle(OnboardTheme.muted)
            Spacer(minLength: 0)
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(line)
    }
}

/// SPEECH SHE HEARD AND LEFT ALONE — the count, and the way to the words.
///
/// Separate from `PendingTurn` because they are opposite facts wearing the
/// same silence: one is still coming, this one is finished. Tapping opens
/// `ListeningHistoryView`, which is where the transcript moved to — so this row
/// is also the promise that nothing was thrown away, which is the only thing
/// that makes hiding the words honest rather than lossy.
struct QuietTurn: View {
    var count: Int
    var open: () -> Void

    private var line: String {
        count == 1 ? "1 thing heard, nothing needed"
                   : "\(count) things heard, nothing needed"
    }

    var body: some View {
        Button(action: open) {
            HStack(spacing: 8) {
                Text(line)
                    .font(.system(size: 13))
                    .foregroundStyle(OnboardTheme.muted)
                Image(systemName: "chevron.right")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(OnboardTheme.muted.opacity(0.7))
                Spacer(minLength: 0)
            }
            .padding(.vertical, 4)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(line)
        .accessibilityHint("Opens everything she heard")
    }
}

/// She is working. A quiet line with a turning mark — never a card, because a
/// card implies something finished.
struct WorkingTurn: View {
    var text: String
    /// Whether the server is working on this RIGHT NOW, or it is only queued.
    /// Defaults true so every existing call site keeps its current behaviour;
    /// `DoneCeremonyPolicy.breathes` is the one place that decides what the
    /// word means.
    var running: Bool = true
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    /// The owner's own switch, which every other ambient motion in this app
    /// honours alongside Reduce Motion as `reduceMotion || !ambientMotion`.
    @AppStorage(AppPreferences.ambientMotionKey) private var ambientMotion = true
    @State private var spin = false

    /// THE ANTICIPATION STAGE of the done ceremony. A job that is running
    /// breathes; the reveal and the afterglow happen later, on the card it
    /// becomes. The spinner beside it says "working" to somebody LOOKING; this
    /// says it to somebody glancing, which is the whole difference between a
    /// status and an anticipation.
    private var breathes: Bool {
        DoneCeremonyPolicy.breathes(status: running ? "running" : "queued")
            && !reduceMotion && ambientMotion
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 10) {
            Image(systemName: "circle.dotted")
                .font(.system(size: 14, weight: .medium))
                .foregroundStyle(OnboardTheme.champagne)
                .rotationEffect(.degrees(spin ? 360 : 0))
                .animation(reduceMotion ? nil
                           : .linear(duration: 3.6).repeatForever(autoreverses: false),
                           value: spin)
            Text(text)
                .font(.system(size: 15))
                .foregroundStyle(OnboardTheme.text2)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        // A hairline edge, not a glow — the strongest thing this product does
        // to a row is still nothing much. TimelineView rather than
        // `.repeatForever`, which is banned for anything touching layout: a
        // repeatForever transaction once interpolated a bar's LAYOUT POSITION
        // when the parent ScrollView settled and three bars wandered across the
        // screen. Capped at 30fps like every other ambient view here, because
        // this can breathe for forty minutes.
        .overlay(alignment: .leading) {
            TimelineView(.animation(minimumInterval: DoneCeremonyPolicy.redrawInterval,
                                    paused: !breathes)) { context in
                let t = context.date.timeIntervalSinceReferenceDate
                let breath = breathes
                    ? (sin(t * DoneCeremonyPolicy.breathOmega) + 1) / 2 : 0.0
                RoundedRectangle(cornerRadius: 1, style: .continuous)
                    .fill(OnboardTheme.champagne.opacity(0.10 + 0.26 * breath))
                    .frame(width: 2)
                    .padding(.vertical, 2)
                    .offset(x: -10)
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
        .onAppear { spin = true }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Working on: \(text)")
    }
}

/// Her answer: prose against the page, not a bubble. The action row underneath
/// is the reference's, minus the share sheet this product has no use for yet.
struct SaidTurn: View {
    var text: String
    var done: Bool
    var onCopy: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if done {
                Label("Done", systemImage: "checkmark")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(OnboardTheme.champagneInk)
                    .accessibilityHidden(true)
            }
            Text(text)
                .font(.system(size: 16))
                .foregroundStyle(OnboardTheme.ink)
                .lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)
            Button(action: onCopy) {
                Image(systemName: "square.on.square")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(OnboardTheme.muted)
                    .frame(width: 44, height: 44, alignment: .leading)
            }
            .buttonStyle(OnboardPressStyle())
            .accessibilityLabel("Copy")
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// A question she is waiting on.
struct QuestionTurn: View {
    var text: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "questionmark.circle")
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(OnboardTheme.champagneInk)
                .padding(.top, 1)
            Text(text)
                .font(.system(size: 16))
                .foregroundStyle(OnboardTheme.ink)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(16)
        .background(RoundedRectangle(cornerRadius: DashMetric.cardRadius, style: .continuous)
            .fill(OnboardTheme.card))
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Chrome

/// The title, with the switch between this conversation and the ones before
/// it. A menu rather than a segmented control because there are two
/// destinations now and a third would not change the shape.
struct DashTitle: View {
    var title: String
    var onPick: (DashboardPolicy.Mode) -> Void

    var body: some View {
        Menu {
            Button { onPick(.thread) } label: { Label("Today", systemImage: "bubble.left.and.text.bubble.right") }
            Button { onPick(.history) } label: { Label("History", systemImage: "clock") }
        } label: {
            HStack(spacing: 6) {
                Text(title)
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundStyle(OnboardTheme.ink)
                Image(systemName: "chevron.down")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(OnboardTheme.muted)
            }
            .padding(.vertical, 8)
            .contentShape(Rectangle())
        }
        .accessibilityLabel("\(title). Switch view")
    }
}

/// The ask bar. One line, one send, and the send is inert until there is
/// something to send.
struct AskBar: View {
    @Binding var text: String
    var placeholder: String
    var onSend: () -> Void
    var focus: FocusState<Bool>.Binding

    var body: some View {
        HStack(spacing: 10) {
            TextField(placeholder, text: $text, axis: .vertical)
                .lineLimit(1...4)
                .font(.system(size: 16))
                .foregroundStyle(OnboardTheme.ink)
                .textFieldStyle(.plain)
                .focused(focus)
                .submitLabel(.send)
                .onSubmit(onSend)
            Button(action: onSend) {
                Image(systemName: "arrow.up")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(text.isEmpty ? OnboardTheme.muted : OnboardTheme.onInk)
                    .frame(width: 34, height: 34)
                    .background(Circle().fill(text.isEmpty ? OnboardTheme.track : OnboardTheme.ink))
            }
            .buttonStyle(OnboardPressStyle())
            .disabled(text.isEmpty)
            .accessibilityLabel("Send")
        }
        .padding(.leading, 18)
        .padding(.trailing, 9)
        .padding(.vertical, 9)
        .background(Capsule().fill(OnboardTheme.card))
        .overlay(Capsule().strokeBorder(OnboardTheme.track, lineWidth: 1))
        .shadow(color: OnboardTheme.inkFixed.opacity(0.06), radius: 14, y: 6)
    }
}

/// One past conversation.
struct HistoryRow: View {
    var title: String
    var when: String
    var onOpen: () -> Void

    var body: some View {
        Button(action: onOpen) {
            HStack(spacing: 12) {
                Text(title)
                    .font(.system(size: 16))
                    .foregroundStyle(OnboardTheme.ink)
                    .lineLimit(1)
                Spacer(minLength: 12)
                Text(when)
                    .font(.system(size: 14))
                    .foregroundStyle(OnboardTheme.muted)
            }
            .padding(.vertical, 14)
            .contentShape(Rectangle())
        }
        .buttonStyle(OnboardPressStyle())
    }
}
