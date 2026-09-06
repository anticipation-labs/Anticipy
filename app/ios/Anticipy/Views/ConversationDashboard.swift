import SwiftUI

/// THE CONVERSATION DASHBOARD — where somebody talks to Anticipy and watches
/// her keep up.
///
/// One surface with three faces, because they are three moments in one
/// activity rather than three screens:
///
///   * THE THREAD is the resting face. What you said, what she is doing about
///     it, what she found, and — inline, never folded away — anything that
///     cannot happen until you say yes. Her answers are prose against the
///     page rather than a fourth rounded rectangle; your own words are a
///     tinted bubble on the right, the way every conversation on this phone
///     is set.
///   * THE CAPTURE is what the thread becomes while she is listening. The
///     ground warms, what she hears arrives as cards while you keep talking,
///     and the foot of the screen is one row: hold, the live wave, done.
///   * THE HISTORY is the days before this one, newest first.
///
/// ── WHAT THIS FILE DOES NOT DECIDE ────────────────────────────────────────
///
/// Which turns exist, what they are, and what the capture moment says are all
/// `DashboardPolicy`'s, walked by `run_dashboard_tests.sh`. This file scales
/// and draws. In particular it never reads the WORDS of a line to decide what
/// kind of turn it is — every row arrives already decided by the brain, and
/// law 1 is the reason (`HARNESS-LAWS.md`).
///
/// ── THE SEATBELT IS NOT A SECTION ─────────────────────────────────────────
///
/// An approval used to be a heading two thirds of the way down a scroll. Here
/// it is a turn in the conversation AND a bar that stays under the title while
/// one is unanswered, because "nothing sends without your OK" is a promise the
/// screen keeps or breaks. `pendingApproval` picks the OLDEST, so the one that
/// has been waiting longest is the one in front of you.
/// The scroll anchor at the foot of the thread. File scope because a generic
/// type may not hold a static stored property.
private let dashboardFoot = "dashboard.foot"

struct ConversationDashboard<Notices: View, Approval: View, Deck: View, SettingsLink: View>: View {

    // What to draw
    let turns: [DashboardPolicy.Turn]
    let captureState: DashboardPolicy.CaptureState
    let listening: Bool
    /// Whether iOS has taken the microphone away. Passed in rather than read
    /// here so the one control at the foot can be derived from
    /// `ListenControlPolicy` — a screen that assumes the mic is available shows
    /// a start button over a live listener, which is the defect this closed.
    var micBlocked: Bool = false
    let everListened: Bool
    let history: [DashboardPolicy.Day]

    // What to do
    let onStartListening: () -> Void
    let onHoldListening: () -> Void
    let onStopListening: () -> Void
    let onSend: (String) -> Void
    let onOpenSession: (DashboardPolicy.Session) -> Void
    let onRefresh: () async -> Void

    /// The notices and offers Home already owns — the microphone recovery, the
    /// unreachable sentence, the interview and browser asks. They live in
    /// `ContentView.swift`, where their own suites read them, and arrive here
    /// as a slot rather than being copied.
    @ViewBuilder let notices: () -> Notices
    /// One approval, drawn by the card that already carries the consequence
    /// and the two buttons.
    @ViewBuilder let approval: (String) -> Approval
    /// Finished work, drawn by the deck that already carries the shelf rule.
    /// At the foot of the thread, after the newest turn, because it is the
    /// part of the day that is over.
    @ViewBuilder let doneDeck: () -> Deck
    /// Settings is a push, and the destination belongs to Home. Passed in as a
    /// link rather than a callback so the navigation stack stays where it is.
    @ViewBuilder let settingsLink: () -> SettingsLink

    @State private var mode: DashboardPolicy.Mode = .thread
    /// The owner pressed hold. The listener stops either way — there is one
    /// microphone and one way to release it — so without this the capture face
    /// could not tell "they paused" from "it ended", and a pause dropped the
    /// person back into the thread as if they had pressed done.
    @State private var held = false
    @State private var typed = ""
    @FocusState private var writing: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        ZStack {
            if mode == .capture {
                CaptureGround(alive: face.alive)
            } else {
                ThreadGround()
            }

            switch mode {
            case .thread:  threadFace
            case .capture: captureFace
            case .history: historyFace
            }
        }
        .animation(reduceMotion ? nil : Theme.springSlow, value: mode)
        // The capture face is what the thread BECOMES: entering it is a state
        // change on one screen, not a sheet sliding over another one.
        .onChange(of: listening) { on in
            withAnimation(Theme.springSlow) {
                if on { held = false; mode = .capture }
                else if mode == .capture, !held { mode = .thread }
            }
        }
    }

    private var face: DashboardPolicy.CaptureFace {
        // A hold is the owner's own doing, so it outranks every state the
        // listener could report about why it is not running.
        DashboardPolicy.captureFace(held ? .paused : captureState,
                                    heardAnything: !captureCards.isEmpty)
    }

    // MARK: - The thread

    private var threadFace: some View {
        VStack(spacing: 0) {
            header
            if let pending = DashboardPolicy.pendingApproval(in: turns),
               case .approval(let id, let goal, _, _) = pending {
                waitingBar(id: id, goal: goal)
            }
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        notices()
                        if turns.isEmpty {
                            emptyLine
                        } else {
                            ForEach(turns, id: \.id) { turn in
                                view(for: turn).id(turn.id)
                            }
                        }
                        doneDeck()
                        Color.clear.frame(height: DashMetric.footClearance).id(dashboardFoot)
                    }
                    .padding(.horizontal, DashMetric.gutter)
                    .padding(.top, 8)
                }
                .refreshable { await onRefresh() }
                .onAppear { proxy.scrollTo(dashboardFoot, anchor: .bottom) }
                .onChange(of: turns.count) { _ in
                    withAnimation(reduceMotion ? nil : Theme.springSlow) {
                        proxy.scrollTo(dashboardFoot, anchor: .bottom)
                    }
                }
            }
        }
        .overlay(alignment: .bottom) { foot }
    }


    @ViewBuilder private func view(for turn: DashboardPolicy.Turn) -> some View {
        switch turn {
        case .owner(_, let text, _):
            OwnerTurn(text: text)
        case .working(_, let text, _):
            WorkingTurn(text: text)
        case .said(_, let text, _, let done):
            SaidTurn(text: text, done: done) { UIPasteboard.general.string = text }
        case .question(_, let text, _):
            QuestionTurn(text: text)
        case .approval(let id, _, _, _):
            approval(id)
        }
    }

    private var emptyLine: some View {
        Text(DashboardPolicy.emptyLine(listening: listening, everListened: everListened))
            .font(.system(size: 17))
            .foregroundStyle(OnboardTheme.text2)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, 40)
    }

    /// The bar that will not let an approval go unseen. Tapping it walks the
    /// scroll to the card rather than answering for the person: a one-tap
    /// "yes" on a bar is exactly the accident the seatbelt exists to prevent.
    private func waitingBar(id: String, goal: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "hand.raised")
                .font(.system(size: 13, weight: .semibold))
            Text("Waiting on you: \(goal)")
                .font(.system(size: 14, weight: .medium))
                .lineLimit(1)
            Spacer(minLength: 0)
            Text("Show").font(.system(size: 14, weight: .semibold))
        }
        .foregroundStyle(OnboardTheme.champagneInk)
        .padding(.horizontal, 16)
        .padding(.vertical, 11)
        .background(RoundedRectangle(cornerRadius: 14, style: .continuous)
            .fill(OnboardTheme.warnCard))
        .padding(.horizontal, DashMetric.gutter)
        .padding(.bottom, 6)
        .accessibilityElement(children: .combine)
        .accessibilityHint("Scrolls to what needs your OK")
    }

    // MARK: - Chrome

    private var header: some View {
        HStack(spacing: 12) {
            DashTitle(title: mode == .history ? "History" : "Today") { picked in
                withAnimation(Theme.springSlow) { mode = picked }
            }
            Spacer(minLength: 0)
            settingsLink()
        }
        .padding(.horizontal, DashMetric.gutter)
        .padding(.top, 4)
    }

    /// The ask bar and the listen control, together, because they are the two
    /// ways to say something and a person should not have to look for the
    /// second one.
    private var foot: some View {
        VStack(spacing: 10) {
            AskBar(text: $typed,
                   placeholder: "Ask Anticipy, or tell her something…",
                   onSend: send,
                   focus: $writing)
            // DERIVED, NEVER HARDWIRED. A button that always says "Listen with
            // phone" is a button that says it over a live microphone — which is
            // how the ✕ above was able to strand a running listener with no way
            // to stop it. `ListenControlPolicy` already answers this question
            // for the whole app; the label, the glyph and what the tap MEANS all
            // come from it now, so the screen cannot offer a start over a
            // session that is already running.
            let control = ListenControlPolicy.face(micBlocked: micBlocked,
                                                   isListening: listening,
                                                   suspended: false)
            Button {
                Haptics.engage()
                switch control.tap {
                case .start:   onStartListening()
                case .stop:    onStopListening()
                case .nothing: break
                }
            } label: {
                HStack(spacing: 10) {
                    // The policy's glyph, except that the landing face has no
                    // room for a breathing dot — it is a foot button, not the
                    // capture face. A live listener gets the stop square there.
                    Image(systemName: {
                        if case .symbol(let name) = control.glyph { return name }
                        return "stop.fill"
                    }())
                        .font(.system(size: 15, weight: .semibold))
                    Text(control.label).font(.system(size: 16, weight: .semibold))
                }
                .foregroundStyle(OnboardTheme.onInk)
                .frame(maxWidth: .infinity)
                .frame(height: DashMetric.bar)
                .background(Capsule().fill(OnboardTheme.ink))
            }
            .buttonStyle(OnboardPressStyle())
            // The onboarding coach mark points here. Home has always reported
            // this anchor; moving the control must not stop it.
            .anchorPreference(key: ListenControlAnchorKey.self, value: .bounds) { $0 }
        }
        .padding(.horizontal, DashMetric.gutter)
        .padding(.bottom, 10)
        .background {
            LinearGradient(colors: [OnboardTheme.ground.opacity(0), OnboardTheme.ground],
                           startPoint: .top, endPoint: .init(x: 0.5, y: 0.42))
                .ignoresSafeArea()
                .allowsHitTesting(false)
        }
    }

    private func send() {
        let line = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !line.isEmpty else { return }
        typed = ""
        writing = false
        onSend(line)
    }

    // MARK: - The capture moment

    /// The cards that appear while she listens: the turns from THIS capture,
    /// which are the ones the thread has not settled yet. Never parsed out of
    /// the audio here — they are rows the brain already decided.
    private var captureCards: [DashboardPolicy.Turn] {
        // WHAT SHE IS HEARING, newest last — including the plain lines. The
        // first version showed only turns that had already become a job or an
        // approval, so somebody talking to a phone that had not finished
        // thinking watched an empty screen and had no reason to believe it was
        // working. The reference this screen is built from puts what you said
        // on the screen as you say it, and that is the whole reassurance.
        //
        // It shows the lines; it does NOT decide which of them mattered. That
        // is law 1 and it belongs to the brain — a card here says "heard this",
        // never "this is a commitment".
        Array(turns.suffix(4))
    }

    private func isWorking(_ t: DashboardPolicy.Turn) -> Bool {
        if case .working = t { return true }
        return false
    }

    private var captureFace: some View {
        VStack(spacing: 0) {
            HStack {
                Button {
                    // IT ENDS THE CAPTURE, NOT JUST THE FACE.
                    //
                    // This used to write `held = false; mode = .thread` and
                    // nothing else — so tapping it took somebody back to the
                    // thread with the microphone STILL RUNNING, the tap still
                    // installed and `keepListening` still true. The landing
                    // face's only listen control calls `onStartListening()`,
                    // which is a no-op on a live listener, so there was then
                    // no control anywhere on Home that could stop it. That is
                    // the "I pressed stop and it kept listening" report, and
                    // this line is the whole of it.
                    //
                    // Guarded on `listening`: a ✕ after a hold must not call
                    // stopListening() a second time and sound `listen-close`
                    // over a session that already closed.
                    if listening { onStopListening() }
                    withAnimation(Theme.springSlow) { held = false; mode = .thread }
                } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(OnboardTheme.ink)
                        .frame(width: 44, height: 44)
                        .background(Circle().fill(OnboardTheme.card))
                }
                .buttonStyle(OnboardPressStyle())
                .accessibilityLabel("Back to the conversation")
                Spacer()
            }
            .padding(.horizontal, DashMetric.gutter)
            .padding(.top, 4)

            VStack(spacing: 12) {
                ForEach(captureCards, id: \.id) { turn in
                    CaptureCard(title: title(of: turn), meta: meta(of: turn))
                        .transition(.asymmetric(
                            insertion: .move(edge: .top).combined(with: .opacity),
                            removal: .opacity))
                }
            }
            .padding(.horizontal, DashMetric.gutter)
            .padding(.top, 12)
            .animation(reduceMotion ? nil : Theme.springSlow, value: captureCards.count)

            Spacer(minLength: 24)

            VStack(spacing: 6) {
                Text(face.title)
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundStyle(OnboardTheme.ink)
                Text(face.subtitle)
                    .font(.system(size: 15))
                    .foregroundStyle(OnboardTheme.text2)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 32)
            .accessibilityElement(children: .combine)

            CaptureControls(alive: face.alive && !held,
                            paused: held || captureState == .paused,
                            onHold: {
                                Haptics.engage()
                                held = !held
                                onHoldListening()
                            },
                            onDone: {
                                Haptics.taskDone()
                                held = false
                                onStopListening()
                            })
                .padding(.horizontal, DashMetric.gutter)
                .padding(.top, 22)
                .padding(.bottom, 18)
        }
    }

    private func title(of turn: DashboardPolicy.Turn) -> String {
        switch turn {
        case .approval(_, let goal, _, _): return goal
        case .working(_, let text, _): return text
        case .said(_, let text, _, _): return text
        case .question(_, let text, _): return text
        case .owner(_, let text, _): return text
        }
    }

    private func meta(of turn: DashboardPolicy.Turn) -> [CaptureChip] {
        switch turn {
        case .approval:
            return [CaptureChip(icon: "hand.raised", text: "Needs your OK", tinted: true)]
        case .working:
            return [CaptureChip(icon: "circle.dotted", text: "Working on it")]
        default:
            return []
        }
    }

    // MARK: - History

    private var historyFace: some View {
        VStack(spacing: 0) {
            header
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    if history.isEmpty {
                        Text("Nothing here yet. Conversations you have with me show up on this list.")
                            .font(.system(size: 16))
                            .foregroundStyle(OnboardTheme.text2)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.top, 40)
                    }
                    ForEach(history, id: \.heading) { day in
                        Text(day.heading)
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundStyle(OnboardTheme.muted)
                            .padding(.top, 22)
                            .padding(.bottom, 2)
                        ForEach(day.sessions, id: \.id) { row in
                            HistoryRow(title: row.title, when: day.heading) {
                                onOpenSession(row)
                            }
                            Rectangle().fill(OnboardTheme.track).frame(height: 0.5)
                        }
                    }
                    Color.clear.frame(height: 40)
                }
                .padding(.horizontal, DashMetric.gutter)
            }
        }
    }
}
