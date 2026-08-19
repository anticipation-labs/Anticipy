import SwiftUI

/// "41207s" is a number, not an answer. Anyone who opens the phone before the
/// laptop saw the raw seconds since the browser last checked in — found by
/// the demo-readiness audit, 2026-08-17.
func humanGap(_ seconds: Int) -> String {
    if seconds < 60 { return "just now" }
    if seconds < 3600 { return "\(seconds / 60)m ago" }
    if seconds < 86400 { return "\(seconds / 3600)h ago" }
    return "\(seconds / 86400)d ago"
}

extension AgentJob {
    /// Goals are free-form model strings ("prepare Devon invoice email").
    /// Show them as a sentence — capitalize the first word, leave the rest
    /// human — instead of Title Casing Every Single Word.
    var humanGoal: String {
        let s = goal.replacingOccurrences(of: "_", with: " ")
        guard let first = s.first else { return s }
        return first.uppercased() + s.dropFirst()
    }

    /// The exact owner-authored words bound into this plan's approval. The
    /// concise goal is model-written; this is shown whenever the model left
    /// anything out, so “Send it” never approves invisible context.
    var approvalSource: String? {
        guard let root = try? JSONSerialization.jsonObject(with: Data(params.utf8))
                as? [String: Any] else { return nil }
        let workflow = root["_workflow"] as? [String: Any]
        let raw = (workflow?["authority_text"] as? String)
            ?? (root["source"] as? String) ?? ""
        let source = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !source.isEmpty else { return nil }
        let normalize: (String) -> String = { value in
            value.lowercased().split(whereSeparator: { !$0.isLetter && !$0.isNumber })
                .joined(separator: " ")
        }
        return normalize(source) == normalize(goal) ? nil : source
    }

    /// docs ex 78's middle answer - is my stuff safe - delegated to a policy
    /// that can be tested without SwiftUI. `effect_uncertain` is the engine's
    /// own admission that it could not confirm whether the submit landed.
    var safetyLine: String {
        JobReceiptPolicy.safetyLine(effectUncertain: effect_uncertain)
    }

    /// What actually went wrong, said the way a person would say it.
    ///
    /// A failed job used to render one fixed shrug ("Couldn't finish this
    /// one") followed by `result` printed verbatim — and what lands in there
    /// is a raw JavaScript exception from the extension. The raw string still
    /// exists, behind a disclosure, for the one person in a hundred who wants
    /// it; everyone else gets a sentence and a way forward.
    var failureLine: String {
        let r = (result ?? "").lowercased()
        if r.isEmpty { return "I couldn't finish this one, and nothing came back to tell me why." }
        if r.contains("captcha") || r.contains("not a robot") || r.contains("verify you are human") {
            return "The site asked me to prove I'm a person. That part has to be you."
        }
        if r.contains("login") || r.contains("log in") || r.contains("sign in") || r.contains("signin") || r.contains("password") || r.contains("401") || r.contains("403") {
            return "It wanted a login I don't have. Sign in to that site in Chrome and I can pick this straight back up."
        }
        if r.contains("timeout") || r.contains("timed out") || r.contains("deadline") {
            return "The page took too long to answer, so I stopped waiting rather than sit there forever."
        }
        if r.contains("net::") || r.contains("failed to fetch") || r.contains("networkerror") || r.contains("err_") || r.contains("offline") {
            return "The page wouldn't load. That's usually the connection on your computer."
        }
        if r.contains("debugger") || r.contains("detached") || r.contains("cancel") {
            return "Chrome cut me off partway through. If you clicked Cancel on the yellow bar, that's what did it."
        }
        if r.contains("closed") || r.contains("no tab") {
            return "The tab I was working in closed before I finished."
        }
        if r.contains("not found") || r.contains("404") || r.contains("no such element") || r.contains("selector") {
            return "The page wasn't laid out the way I expected, so I couldn't find what I needed."
        }
        return "I couldn't finish this one."
    }
}

/// Home = the proactive feed: what Anticipy heard, what it's handling,
/// what needs your OK, and what's done — plus live connection health.
struct HomeView: View {
    @EnvironmentObject var pendant: PendantManager
    @EnvironmentObject var session: AnticipySession
    @Environment(\.scenePhase) private var scenePhase
    @State private var typedLine = ""
    /// The sentence the typewriter is committed to, captured ONCE. See
    /// `briefingView` — the poll runs every 3 seconds and used to wipe and
    /// re-type her whole briefing, with a haptic, every time a job count moved.
    @State private var briefingShown = ""
    @State private var briefingTyped = false
    /// Plain-English explanation of whichever status pill was last tapped.
    @State private var pillNote: String?

    // needs_user (login wall, CAPTCHA, refused site) used to render in NO
    // section at all — the job silently disappeared while the card said
    // "Nothing needs you right now". It belongs in the attention section.
    private var needsOK: [AgentJob] { session.jobs.filter { $0.status == "awaiting_confirm" || $0.status == "needs_user" } }
    /// Finished quiet work — anticipy_says events the brain marked done.
    /// Newest first, capped so the desk never becomes a landfill.
    private var foundForYou: [BrainEvent] {
        let done = session.anticipySays.filter { ev in
            ev.kind == "anticipy_says" && ev.decision == "done"
                && (ev.text?.isEmpty == false)
        }
        return Array(done.prefix(5))
    }
    private var handling: [AgentJob] { session.jobs.filter { $0.status == "queued" || $0.status == "running" } }
    private var finished: [AgentJob] { session.jobs.filter { $0.status == "done" || $0.status == "failed" } }

    /// What she heard, as conversations rather than as a wall of lines.
    ///
    /// The window is the same newest-30 lines the feed has always shown; only
    /// the grouping is new, and it groups on the one field that exists —
    /// `events.segment`. A line the segmenter never stamped is a conversation
    /// of one, so with no segments at all this renders the identical list of
    /// rows it renders today. Newest conversation first, the way "Heard" has
    /// always been chronological.
    private var heardGroups: [HeardGroup] {
        Array(HeardGroup.build(Array(session.transcript.suffix(30))).reversed())
    }

    /// Nothing to show at all. WHY there's nothing is a separate question, and
    /// the answer decides which of four very different screens you get.
    private var feedIsEmpty: Bool {
        needsOK.isEmpty && handling.isEmpty && finished.isEmpty && session.transcript.isEmpty
    }

    /// A read actually succeeded. Everything the app claims about your day
    /// hangs off this — reachability alone means nothing, because /api/health
    /// isn't behind the same guard the data API is.
    private var verified: Bool { session.connection == .ready }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.ink.ignoresSafeArea()
                Grain.image
                    .opacity(0.035)
                    .blendMode(.plusLighter)
                    .ignoresSafeArea()
                    .allowsHitTesting(false)
                ScrollView {
                    // Rhythm is driven explicitly: space BETWEEN groups is
                    // 2.5–3x space WITHIN one, which is what makes this read
                    // as a layout instead of a list.
                    VStack(alignment: .leading, spacing: 0) {
                        if micNeedsHelp { micRecoveryCard.padding(.top, Theme.Space.tight) }
                        // Her briefing only appears over a verified read. She
                        // does not get to say "I've got the watch" from an app
                        // that has never once reached its own server — and on
                        // day one the empty state carries the whole screen.
                        if verified && !feedIsEmpty {
                            anticipyCardView.padding(.top, Theme.Space.snug)
                        }
                        // What she found — the quiet work, delivered. Lives
                        // at the top because Omar's words were exact: "it
                        // should text you the results and pull it up at the
                        // top of the app." Before this section existed her
                        // finished research sat in the database and nowhere
                        // else a human looks.
                        if verified && !foundForYou.isEmpty {
                            foundHeader
                                .padding(.top, Theme.Space.section)
                                .padding(.bottom, Theme.Space.tight)
                            VStack(spacing: Theme.Space.snug) {
                                ForEach(foundForYou, id: \.id) { ev in
                                    FoundCard(event: ev)
                                        .transition(.asymmetric(
                                            insertion: .move(edge: .top).combined(with: .opacity),
                                            removal: .opacity))
                                }
                            }
                        }
                        listenCard.padding(.top, feedIsEmpty ? Theme.Space.tight : Theme.Space.roomy)
                        if feedIsEmpty {
                            switch session.connection {
                            case .loading:          loadingState
                            case .offline:          offlineState
                            case .refused(let s):   refusedState(s)
                            case .ready:            emptyState
                            }
                        } else {
                            if !verified { staleNotice.padding(.top, Theme.Space.section) }
                            if !needsOK.isEmpty {
                                needsOKHeader
                                    .padding(.top, Theme.Space.section)
                                    .padding(.bottom, Theme.Space.tight)
                                VStack(spacing: Theme.Space.snug) {
                                    ForEach(Array(needsOK.enumerated()), id: \.element.id) { i, job in
                                        ConfirmJobCard(job: job)
                                            .transition(.asymmetric(
                                                insertion: .move(edge: .top).combined(with: .opacity),
                                                removal: .opacity.combined(with: .scale(scale: 0.96))))
                                            .animation(Theme.spring.delay(min(Double(i) * 0.05, 0.25)), value: session.jobs)
                                    }
                                }
                            }
                            if !handling.isEmpty {
                                // Honest about WHY nothing is moving: with Chrome
                                // shut there are no hands, and saying "Handling"
                                // over a stalled queue is a small daily lie.
                                sectionHeader(session.agentOnline ? "Handling" : "Waiting for your browser")
                                    .padding(.top, Theme.Space.section)
                                    .padding(.bottom, Theme.Space.tight)
                                if !session.agentOnline {
                                    Text(session.agentPaired
                                         ? "Open Chrome and these pick up on their own."
                                         : "Link Chrome in Settings and these pick up on their own.")
                                        .font(.system(size: 15))
                                        .foregroundStyle(Theme.sand)
                                        .padding(.bottom, Theme.Space.tight)
                                }
                                // He has had to ASK whether his extension was
                                // current — twice — and once a whole retest
                                // ran against a stale one while everybody
                                // believed the fixes were live. Chrome already
                                // reports its version on every heartbeat, so
                                // the answer was always here to be shown.
                                // AN UNREACHABLE CUSTOMER NEVER FINDS OUT
                                // THEY ARE UNREACHABLE. Sign-up never
                                // required a number, this app has no
                                // notifications at all, and a text is the
                                // only channel there is — so an account with
                                // no number on file gets asked nothing, ever,
                                // and its work parks forever in silence.
                                // Anyone who signed up before the sign-up
                                // gate is in exactly that state right now.
                                if session.ownerPhone.isEmpty {
                                    Text("I have no number for you, so I can't tell you when "
                                         + "something needs your word. These will just wait. "
                                         + "Add it in Settings and I'll start reaching you.")
                                        .font(.system(size: 15))
                                        .foregroundStyle(Theme.champagne)
                                        .padding(.bottom, Theme.Space.tight)
                                }
                                if let stale = session.staleExtensionVersion {
                                    Text("Chrome is running the old extension (\(stale)). "
                                         + "Open chrome://extensions and press Reload to get \(AnticipySession.expectedExtensionVersion)"
                                         + "until then it's working from old instructions.")
                                        .font(.system(size: 15))
                                        .foregroundStyle(Theme.champagne)
                                        .padding(.bottom, Theme.Space.tight)
                                }
                                VStack(spacing: 0) {
                                    ForEach(Array(handling.enumerated()), id: \.element.id) { i, job in
                                        if i > 0 { Rectangle().fill(Theme.stroke).frame(height: 0.5) }
                                        HandlingCard(job: job)
                                            .transition(.asymmetric(
                                                insertion: .move(edge: .top).combined(with: .opacity),
                                                removal: .opacity.combined(with: .scale(scale: 0.96))))
                                            .animation(Theme.spring.delay(min(Double(i) * 0.05, 0.25)), value: session.jobs)
                                    }
                                }
                            }
                            heardSection
                            if !finished.isEmpty {
                                sectionHeader("Done")
                                    .padding(.top, Theme.Space.section)
                                    .padding(.bottom, Theme.Space.tight)
                                VStack(spacing: 0) {
                                    ForEach(Array(finished.prefix(8).enumerated()), id: \.element.id) { i, job in
                                        if i > 0 { Rectangle().fill(Theme.stroke).frame(height: 0.5) }
                                        DoneCard(job: job)
                                            .transition(.asymmetric(
                                                insertion: .move(edge: .top).combined(with: .opacity),
                                                removal: .opacity))
                                            .animation(Theme.spring.delay(min(Double(i) * 0.05, 0.25)), value: session.jobs)
                                    }
                                }
                            }
                        }
                        // Diagnostics belong at the foot, not as the opening
                        // statement of the whole product.
                        statusStrip.padding(.top, Theme.Space.wide)
                    }
                    .padding(.horizontal)
                    .padding(.bottom, 30)
                }
                .refreshable { await session.refresh() }
            }
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    HStack(spacing: 10) {
                        LogoMark(size: 26)
                            .accessibilityHidden(true)
                        Text("Anticipy Claude Version")
                            .font(Theme.display(24))
                            .foregroundStyle(Theme.ivory)
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    NavigationLink { SettingsView() } label: {
                        Image(systemName: "slider.horizontal.3")
                            .foregroundStyle(Theme.sand)
                    }
                    // An icon on its own is announced as "button" and nothing
                    // else. VoiceOver users got two unnamed controls on Home.
                    .accessibilityLabel("Settings")
                }
            }
            // The single clearest "this is a real, current iOS app" signal
            // available: content blurs as it passes under the header.
            .toolbarBackground(.ultraThinMaterial, for: .navigationBar)
            .toolbarColorScheme(.dark, for: .navigationBar)
            // If listening was on when the app closed or backgrounded, she
            // picks it back up herself — no button-press chore per open.
            .onAppear {
                Haptics.warmUp()
                session.resumeListeningIfWanted()
            }
            .onChange(of: scenePhase) { phase in
                if phase == .active {
                    Haptics.warmUp()
                    session.resumeListeningIfWanted()
                }
            }
        }
    }

    // MARK: - Status

    private var statusStrip: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Long, honest labels don't fit two-across on a small phone, and
            // truncating "not capturing yet" back into "Listening" is exactly
            // the lie this is here to stop.
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    statusPill(
                        icon: "dot.radiowaves.left.and.right",
                        label: pendantLabel,
                        active: pendant.state == .connected,
                        // A percentage alone made the person work out what 12%
                        // means for hardware they have owned a week. The policy
                        // owns both the threshold and the words (docs ex 90).
                        detail: PendantBatteryPolicy.detail(percent: pendant.battery),
                        note: pendantNote
                    )
                    statusPill(
                        icon: "macbook",
                        label: agentLabel,
                        active: session.agentOnline,
                        detail: session.agentLastSeenSeconds.map(humanGap),
                        note: agentNote
                    )
                }
                .padding(.vertical, 1)
            }
            if let pillNote {
                Text(pillNote)
                    .font(.caption)
                    .foregroundStyle(Theme.sand)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.top, 6)
        .animation(Theme.spring, value: pillNote)
    }

    /// "Agent unpaired" means nothing to a stranger. This is the same state,
    /// said in words they already own.
    private var agentLabel: String {
        if !verified { return "Chrome, can't check" }
        if !session.agentPaired { return "Chrome not linked" }
        return session.agentOnline ? "Chrome ready" : "Chrome asleep"
    }

    private var agentNote: String {
        if !verified { return "I can't reach my own server, so I can't tell you what Chrome is doing right now." }
        if !session.agentPaired { return "Chrome isn't linked to your phone yet. Linking it in Settings is what lets me actually do things on the web for you." }
        if session.agentOnline { return "Chrome is open and linked. That's where I do the doing." }
        return "Chrome is linked, but it isn't open. Anything I've queued waits there until you open it."
    }

    private var pendantLabel: String {
        switch pendant.state {
        case .connected:
            return session.pendantCapturing
                ? "Pendant · listening"
                : "Pendant · starting transcription"
        case .connecting: return "Pendant connecting"
        case .reconnecting: return "Pendant reconnecting"
        case .warmingUp: return "Turning on Bluetooth"
        case .searching: return "Looking for pendant"
        case .unavailable: return "Bluetooth off"
        case .off: return pendant.hasPairedPendant ? "Pendant away" : "No pendant"
        }
    }

    private var pendantNote: String {
        switch pendant.state {
        case .connected:
            return session.pendantCapturing
                ? "Your pendant audio is being securely transcribed by Deepgram. Finalized words come back to Anticipy Claude Version; the long-lived provider key never enters this phone."
                : "Your pendant is connected and I'm opening its secure transcription stream. If that service is unavailable, I say so here instead of dropping audio behind a Listening label."
        case .warmingUp: return "Bluetooth is still waking up. I'll start looking for your pendant the moment it's ready. Nothing for you to do."
        case .connecting, .reconnecting, .searching: return "I'm looking for your pendant. Listen with phone works right now either way."
        case .unavailable: return "Bluetooth is off, so I can't see the pendant."
        case .off: return pendant.hasPairedPendant
            ? "Your pendant is out of range or switched off."
            : "You don't have a pendant set up. You don't need one. Your phone is the microphone."
        }
    }

    private func statusPill(icon: String, label: String, active: Bool, detail: String?, note: String) -> some View {
        Button {
            Haptics.tap()
            pillNote = (pillNote == note) ? nil : note
        } label: {
            HStack(spacing: 6) {
                Circle()
                    .fill(active ? Theme.champagne : Theme.stroke)
                    .frame(width: 7, height: 7)
                    // Pure decoration: the label right beside it says the
                    // same thing in words.
                    .accessibilityHidden(true)
                Image(systemName: icon).font(.caption)
                    .accessibilityHidden(true)
                Text(label).font(.caption.weight(.medium)).lineLimit(1)
                if let detail { Text(detail).font(.caption2).foregroundStyle(Theme.gray) }
            }
            .foregroundStyle(active ? Theme.ivory : Theme.gray)
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .background(Capsule().fill(Theme.surface))
        }
        .buttonStyle(.pressable)
        .accessibilityLabel(label)
        .accessibilityHint("Explains what this means.")
    }

    // MARK: - Microphone

    /// iOS has been told no, or told no earlier in this session. Either way
    /// the system alert will never appear again and only Settings can undo it.
    private var micNeedsHelp: Bool { session.micBlocked || !session.listener.authorized }

    /// The whole recovery route used to be one line of grey caption text with
    /// nothing to tap, in an app that contained no route to Settings at all —
    /// so a single "Don't Allow" was the end of the product.
    private var micRecoveryCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("I can't hear you", systemImage: "mic.slash")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Theme.champagne)
            Text("The microphone is switched off for Anticipy Claude Version, so tapping Listen won't do anything. iOS only asks once. Turn it back on and I'll start the moment you come back.")
                .font(.callout)
                .foregroundStyle(Theme.sand)
                .fixedSize(horizontal: false, vertical: true)
            Button {
                session.openSystemSettings()
            } label: {
                Text("Open Settings")
                    .font(.callout.weight(.semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 11)
                    .background(Capsule().fill(Theme.champagne))
                    .foregroundStyle(Theme.ink)
            }
            .buttonStyle(.pressable)
            .accessibilityHint("Opens Anticipy Claude Version's page in the iOS Settings app, where Microphone and Speech Recognition can be switched back on.")
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
    }

    /// Pendant-less listening: phone mic → on-device transcription → brain.
    private var listenCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 12) {
                Button {
                    Haptics.engage()
                    if session.listener.isListening {
                        session.stopListening()
                    } else {
                        session.startListening()
                    }
                } label: {
                    // The switch that turns the entire product on is the one
                    // lit object on this screen — not a dim capsule smaller
                    // than the button that approves one email.
                    HStack(spacing: Theme.Space.snug) {
                        if session.listener.isListening {
                            BreathingDot(size: 10)
                        } else {
                            Image(systemName: listenButtonIcon)
                                .font(.system(size: 18, weight: .medium))
                        }
                        Text(listenButtonLabel)
                            .font(Theme.display(22))
                            .tracking(-0.2)
                    }
                    .padding(.horizontal, Theme.Space.card)
                    .frame(height: 60)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(
                        RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous)
                            .fill(session.listener.isListening ? Theme.champagne : Theme.card)
                            .overlay(
                                RoundedRectangle(cornerRadius: Theme.Radius.card, style: .continuous)
                                    .strokeBorder(session.listener.isListening ? .clear : Theme.champagne.opacity(0.45),
                                                  lineWidth: 1)
                            )
                    )
                    .foregroundStyle(listenButtonTint)
                }
                .buttonStyle(.pressable)
                // A tap that iOS will instantly refuse is worse than no
                // button: it reads as the app being broken.
                .disabled(micNeedsHelp)
                .accessibilityHint(micNeedsHelp ? "Unavailable until the microphone is switched back on in Settings." : "")
                Spacer()
                // A listening app shows a waveform, never a spinner.
                if session.listener.isListening && !session.listener.suspended {
                    WaveBars()
                }
            }
            // Honesty over pretense: when iOS takes the mic (call, Siri,
            // route change), say so while recovery runs — never glow
            // "Listening" over a dead microphone.
            if session.listener.suspended {
                Label("Mic interrupted, taking it back…", systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(Theme.gray)
            }
            // Nothing you said is lost when the network is: say the count out
            // loud rather than let it look like she stopped hearing you.
            if session.pendingCount > 0 {
                Label(
                    session.pendingCount == 1
                        ? "One thing you said is waiting for a signal. I'll send it the moment there is one."
                        : "\(session.pendingCount) things you said are waiting for a signal. I'll send them the moment there is one.",
                    systemImage: "tray.and.arrow.up"
                )
                .font(.caption)
                .foregroundStyle(Theme.gray)
                .fixedSize(horizontal: false, vertical: true)
            }
            // The current session's spoken lines stay visible right here —
            // words move DOWN into this list when you pause, they are never
            // deleted. ✓ means Anticipy's brain has them.
            if session.listener.isListening && !session.sessionLines.isEmpty {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(session.sessionLines.suffix(4)) { line in
                        SessionLineRow(line: line)
                    }
                }
                .padding(10)
                .background(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous).fill(Theme.surface.opacity(0.6)))
            }
            // Your own voice becoming text is the demo — it renders big,
            // above the settled record, never as fine print below it.
            if !session.listener.partial.isEmpty {
                Text(session.listener.partial)
                    .font(.system(size: 20))
                    .lineSpacing(3)
                    .foregroundStyle(Theme.ivory.opacity(0.55))
                    .fixedSize(horizontal: false, vertical: true)
                    .transition(.opacity)
            }
            HStack(spacing: 8) {
                TextField("Or tell Anticipy Claude Version something…", text: $typedLine)
                    .font(.callout)
                    .foregroundStyle(Theme.ivory)
                    .textFieldStyle(.plain)
                    .onSubmit(submitTyped)
                Button(action: submitTyped) {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title3)
                        .foregroundStyle(typedLine.isEmpty ? Theme.stroke : Theme.champagne)
                }
                .buttonStyle(.pressable)
                .disabled(typedLine.isEmpty)
                .accessibilityLabel("Send")
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 9)
            .background(RoundedRectangle(cornerRadius: 12).fill(Theme.surface))
        }
    }

    private var listenButtonLabel: String {
        if micNeedsHelp { return "Microphone is off" }
        return session.listener.isListening ? "Listening with phone" : "Listen with phone"
    }

    private var listenButtonIcon: String {
        if micNeedsHelp { return "mic.slash" }
        return session.listener.isListening ? "mic.fill" : "mic"
    }

    private var listenButtonTint: Color {
        if micNeedsHelp { return Theme.gray }
        return session.listener.isListening ? Theme.ink : Theme.ivory
    }

    private func submitTyped() {
        let line = typedLine.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !line.isEmpty else { return }
        // heard() owns the haptic — a second tap here reads as a stutter-bug.
        typedLine = ""
        Task { await session.heard(line, explicit: true) }
    }

    /// Anticipy speaks first: a first-person briefing of what she heard and
    /// what she's handling, rebuilt live from the real job queue.
    private var anticipyCardView: some View {
        VStack(alignment: .leading, spacing: Theme.Space.tight) {
            // She OPENS with "Evening." in serif — the nav bar two inches
            // above already says Anticipy, so the wordmark row is gone and
            // the greeting takes the headline slot.
            HStack(spacing: Theme.Space.tight) {
                Text(greeting)
                    .font(Theme.display(30))
                    .tracking(-0.5)
                    .foregroundStyle(Theme.champagne)
                // Breathing means "she is doing something right now". A
                // connected pendant is not that: it captures nothing.
                if session.listener.isListening || !handling.isEmpty {
                    BreathingDot(size: 7)
                }
            }
            briefingView
            if let says = session.freshAnticipySays {
                Rectangle()
                    .fill(Theme.champagne.opacity(0.14))
                    .frame(height: 1)
                    .padding(.vertical, Theme.Space.snug)
                Text(says)
                    .font(.system(size: 15))
                    .lineSpacing(2)
                    .foregroundStyle(Theme.sand)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .cardSurface(elevated: true)
        .background(Theme.bloom(0.10, radius: 300))
    }

    /// She types her opening line ONCE.
    ///
    /// `TypewriterText` restarts whenever its string changes, and the briefing
    /// is rebuilt from job counts that the 3-second poll moves all day — so
    /// the whole sentence wiped itself and re-typed, with a haptic, while you
    /// were reading it. The typewriter now gets a string captured on appear
    /// and never touched again; every later change lands as plain text.
    private var briefingView: some View {
        Group {
            if briefingTyped {
                Text(briefingText)
                    .font(.system(size: 17))
                    .lineSpacing(3)
                    .foregroundStyle(Theme.ivory)
                    .fixedSize(horizontal: false, vertical: true)
                    .animation(Theme.spring, value: briefingText)
            } else {
                TypewriterText(text: briefingShown) {
                    briefingTyped = true
                }
            }
        }
        .onAppear {
            if briefingShown.isEmpty { briefingShown = briefingText }
        }
    }

    private var briefingText: String {
        var parts: [String] = []
        // Only the phone mic actually hears anything today.
        if session.listener.isListening {
            parts.append("I'm listening.")
        }
        if !needsOK.isEmpty {
            parts.append("I've got \(needsOK.count) thing\(needsOK.count == 1 ? "" : "s") ready. Just say the word.")
        }
        if !handling.isEmpty {
            parts.append("I'm handling \(handling.count) task\(handling.count == 1 ? "" : "s") right now.")
        }
        if needsOK.isEmpty && handling.isEmpty {
            // EARS ARE EARS, WHICHEVER ONES THEY ARE. This asked only the
            // phone mic, so with the pendant live and the phone mic off the
            // screen said "I'm not listening yet — tap Listen with phone"
            // directly above a status bar reading "Pendant · listening".
            // Demoing the pendant, the product contradicted itself on one
            // screen and took the pendant's side away.
            parts.append(session.listener.isListening || session.pendantCapturing
                         ? idleLine : offLine)
        }
        return parts.joined(separator: " ")
    }

    /// She knows what time it is, and she doesn't say the same sentence
    /// every single time you look at her. Statements only — a question from
    /// an always-listening device reads wrong at night.
    private var greeting: String {
        switch Calendar.current.component(.hour, from: Date()) {
        case 5..<12: return "Morning."
        case 12..<17: return "Afternoon."
        case 17..<23: return "Evening."
        default: return "Late one."
        }
    }

    /// Time-neutral idle lines — "go live your day" belongs to the
    /// empty-state brand moment, and reads absurd at 2am.
    private var idleLine: String {
        let lines = [
            "Nothing needs you right now. I've got it covered.",
            "All quiet on my end. I've got the watch.",
            "Nothing waiting on you. I'll speak up when something matters.",
        ]
        let day = Calendar.current.ordinality(of: .day, in: .year, for: Date()) ?? 0
        return lines[day % lines.count]
    }

    /// With the mic off she is not covering anything, so she doesn't claim to.
    /// She points at the one control that starts her instead.
    private var offLine: String {
        micNeedsHelp
            ? "I can't hear anything until the microphone is back on."
            : "I'm not listening yet, tap Listen with phone, or wake your pendant, "
              + "and I'll start picking things up."
    }

    /// What she heard — one card per conversation, newest first.
    ///
    /// The groups are built ONCE here rather than per row: `heardGroups` is a
    /// computed property, and the separator rule below has to look at the
    /// previous sibling.
    @ViewBuilder private var heardSection: some View {
        let groups = heardGroups
        if !groups.isEmpty {
            sectionHeader("Heard")
                .padding(.top, Theme.Space.section)
                .padding(.bottom, Theme.Space.tight)
            VStack(spacing: 0) {
                ForEach(Array(groups.enumerated()), id: \.element.id) { i, group in
                    // A hairline belongs between two rows on the ink. It does
                    // not belong beside a card, which has its own edge already.
                    if i > 0, !group.isCarded, !groups[i - 1].isCarded {
                        Rectangle().fill(Theme.stroke).frame(height: 0.5)
                    }
                    ConversationCard(group: group)
                        .transition(.asymmetric(
                            insertion: .move(edge: .top).combined(with: .opacity),
                            removal: .opacity))
                        .animation(Theme.spring.delay(min(Double(i) * 0.05, 0.25)),
                                   value: session.transcript)
                }
            }
        }
    }

    /// Chronology sections — a tracked uppercase micro-label beside the
    /// serif is an editorial move: it gives the big type something to be
    /// big against.
    private func sectionHeader(_ text: String) -> some View {
        Text(text.uppercased())
            .font(.system(size: 12, weight: .semibold))
            .tracking(1.2)
            .foregroundStyle(Theme.gray)
    }

    /// The one section that demands an action gets the display register and
    /// a count.
    private var needsOKHeader: some View {
        HStack(spacing: Theme.Space.tight) {
            Text("Needs your OK")
                .font(Theme.display(22))
                .tracking(-0.2)
                .foregroundStyle(Theme.ivory)
            Text("\(needsOK.count)")
                .font(.system(size: 12, weight: .bold))
                .padding(.horizontal, 7)
                .padding(.vertical, 3)
                .background(Capsule().fill(Theme.champagne))
                .foregroundStyle(Theme.ink)
        }
    }

    private var foundHeader: some View {
        HStack(spacing: Theme.Space.tight) {
            Text("Found for you")
                .font(Theme.display(22))
                .tracking(-0.2)
                .foregroundStyle(Theme.ivory)
            Text("\(foundForYou.count)")
                .font(.system(size: 12, weight: .bold))
                .padding(.horizontal, 7)
                .padding(.vertical, 3)
                .background(Capsule().fill(Theme.champagne))
                .foregroundStyle(Theme.ink)
        }
    }

    // MARK: - The four empty screens

    /// Still asking. The first probe can take the full timeout, and this is
    /// the window in which the app used to paint the finished empty state.
    private var loadingState: some View {
        VStack(spacing: 14) {
            BreathingDot(size: 10)
                .padding(.top, Theme.Space.hero)
                .padding(.bottom, 4)
            Text("One moment.")
                .font(Theme.display(30))
                .tracking(-0.5)
                .foregroundStyle(Theme.ivory)
            Text("I'm catching up on your day. This takes a second.")
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.sand)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 300)
            retryButton("Check again")
        }
        .frame(maxWidth: .infinity)
    }

    /// The phone cannot get to Anticipy at all.
    private var offlineState: some View {
        VStack(spacing: 14) {
            Image(systemName: "wifi.slash")
                .font(.system(size: 34))
                .foregroundStyle(Theme.champagne)
                .padding(.top, Theme.Space.hero)
                .accessibilityHidden(true)
            Text("I can't reach my side.")
                .font(Theme.display(30))
                .tracking(-0.5)
                .foregroundStyle(Theme.ivory)
                .multilineTextAlignment(.center)
            Text(offlineBody)
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.sand)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 300)
            retryButton("Try again")
        }
        .frame(maxWidth: .infinity)
    }

    private var offlineBody: String {
        let base = "Your phone can't get through to Anticipy Claude Version right now. It's almost always the connection. You can keep talking to me either way."
        guard session.pendingCount > 0 else { return base }
        return base + " I'm holding \(session.pendingCount) thing\(session.pendingCount == 1 ? "" : "s") you said, and I'll send \(session.pendingCount == 1 ? "it" : "them") the moment we're back."
    }

    /// We reached the server and it said no. That is mine to fix, not yours —
    /// and it is a completely different problem from being offline.
    private func refusedState(_ status: Int) -> some View {
        VStack(spacing: 14) {
            Image(systemName: "lock")
                .font(.system(size: 34))
                .foregroundStyle(Theme.champagne)
                .padding(.top, Theme.Space.hero)
                .accessibilityHidden(true)
            Text("Anticipy Claude Version won't let me in.")
                .font(Theme.display(30))
                .tracking(-0.5)
                .foregroundStyle(Theme.ivory)
                .multilineTextAlignment(.center)
            Text("I reached my server and it turned me away. I'm sorting my own key out. This should clear itself in a moment.")
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.sand)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 300)
            Text("Error \(status)")
                .font(.system(size: 12))
                .foregroundStyle(Theme.gray)
            retryButton("Try again")
        }
        .frame(maxWidth: .infinity)
    }

    /// The finished, confident screen. It is only ever allowed to appear over
    /// a read that actually succeeded and came back with nothing.
    /// Day one: the ghost of tomorrow — a living manifest of what she is
    /// listening for, and the real components showing what a catch will look
    /// like. No "Check again": this branch is only reachable when the read
    /// SUCCEEDED, and offering a retry tells a first-timer something broke.
    private var emptyState: some View {
        VStack(spacing: 16) {
            ZStack {
                Theme.bloom(0.14, radius: 260)
                LogoMark(size: 96)
            }
            .frame(height: 120)
            .padding(.top, Theme.Space.wide)
            .accessibilityHidden(true)
            Text(greeting)
                .font(Theme.display(40))
                .tracking(-1.0)
                .foregroundStyle(Theme.ivory)
            Text("Live your day. I listen, I understand, and I handle the follow-through, asking before anything is sent.")
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.sand)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: 300)
            // Motion is the only thing that distinguishes WAITING from
            // BROKEN: three dots pulsing in sequence beside what she's
            // listening for.
            VStack(alignment: .leading, spacing: Theme.Space.snug) {
                manifestRow("things you say you'll do", delay: 0)
                manifestRow("names and dates you mention", delay: 0.53)
                manifestRow("anything that needs a reply", delay: 1.07)
            }
            .padding(.top, Theme.Space.tight)
            Rectangle().fill(Theme.stroke).frame(height: 0.5)
                .padding(.vertical, Theme.Space.snug)
            Text("WHEN I CATCH SOMETHING, IT LOOKS LIKE THIS")
                .font(.system(size: 12, weight: .semibold))
                .tracking(1.2)
                .foregroundStyle(Theme.gray)
                .frame(maxWidth: .infinity, alignment: .leading)
            // The REAL components, fed fixtures — using the actual views
            // guarantees the promise matches the delivery.
            VStack(spacing: Theme.Space.snug) {
                TranscriptRow(line: AnticipySession.TranscriptLine(
                    id: "demo-1",
                    text: "I'll get that invoice over to you tonight",
                    decision: "act"))
                ConfirmJobCard(job: AgentJob(
                    id: "demo-2", goal: "Draft the invoice email to Devon",
                    params: "", status: "awaiting_confirm", result: nil, created: ""))
            }
            .opacity(0.42)
            .blur(radius: 0.4)
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
        .frame(maxWidth: .infinity)
    }

    private func manifestRow(_ text: String, delay: Double) -> some View {
        HStack(spacing: Theme.Space.snug) {
            PulseDot(delay: delay)
            Text(text)
                .font(.system(size: 17))
                .foregroundStyle(Theme.sand)
        }
    }

    /// Pull-to-refresh has always been here and nobody has ever found it.
    private func retryButton(_ title: String) -> some View {
        Button {
            Task { await session.refresh() }
        } label: {
            Label(title, systemImage: "arrow.clockwise")
                .font(.callout.weight(.semibold))
                .padding(.horizontal, 20)
                .padding(.vertical, 11)
                .background(Capsule().strokeBorder(Theme.stroke))
                .foregroundStyle(Theme.sand)
        }
        .buttonStyle(.pressable)
        .padding(.top, 4)
    }

    /// There IS something on screen, but it's what we had before we lost
    /// touch. Say so rather than let it read as live.
    private var staleNotice: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: session.connection == .offline ? "wifi.slash" : "lock")
                .foregroundStyle(Theme.champagne)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 8) {
                Text(session.connection == .offline
                     ? "I can't reach Anticipy Claude Version right now, so this is what I had a moment ago."
                     : "Anticipy Claude Version turned me away just now, so this is what I had a moment ago.")
                    .font(.footnote)
                    .foregroundStyle(Theme.sand)
                    .fixedSize(horizontal: false, vertical: true)
                Button {
                    Task { await session.refresh() }
                } label: {
                    Label("Try again", systemImage: "arrow.clockwise")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(Theme.champagne)
                }
                .buttonStyle(.pressable)
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
    }
}

// MARK: - Cards

/// A job the agent prepared and is holding for your explicit go-ahead.
struct ConfirmJobCard: View {
    let job: AgentJob
    @EnvironmentObject var session: AnticipySession
    @State private var answer = ""

    private var stuck: Bool { job.status == "needs_user" }
    private var uncertain: Bool { job.effect_uncertain == true }
    private var sending: Bool { session.inFlight.contains(job.id) }
    private var failed: Bool { session.failedWrites.contains(job.id) }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(stuck ? "Stuck. I need you" : "Ready. Say the word",
                  systemImage: stuck ? "hand.raised" : "checkmark.seal")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Theme.champagne)
            Text(job.humanGoal)
                .font(.body.weight(.semibold))
                .foregroundStyle(Theme.ivory)
            if let source = job.approvalSource {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Your exact words")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(Theme.gray)
                    Text(source)
                        .font(.footnote)
                        .foregroundStyle(Theme.sand)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            if let r = job.result, !r.isEmpty {
                Text(r).font(.footnote).foregroundStyle(Theme.sand)
            }
            if uncertain {
                Text("First check the site or app where this was happening. Only continue if the action did not happen.")
                    .font(.caption)
                    .foregroundStyle(Theme.sand)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if stuck && !uncertain {
                TextField("Type what I need, or say you handled it", text: $answer,
                          axis: .vertical)
                    .lineLimit(1...4)
                    .font(.callout)
                    .foregroundStyle(Theme.ivory)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .background(RoundedRectangle(cornerRadius: 10).fill(Theme.surface))
                    .accessibilityLabel("Your answer for this task")
            }
            // The write failed and the card is still sitting here. Without
            // this row that reads as a UI glitch, and the natural next move
            // is to tap Send again — which is how one email goes twice.
            if failed {
                Label("That didn't go through, I couldn't reach Anticipy Claude Version. Nothing was sent.", systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(Theme.sand)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 10) {
                Button {
                    // No haptic here: confirm() buzzes only after the server
                    // has actually accepted it. This one used to buzz success
                    // before the request had even left the phone.
                    Task { await session.confirm(job, ownerAnswer: answer) }
                } label: {
                    Group {
                        if sending {
                            HStack(spacing: 8) {
                                BreathingDot(size: 6)
                                Text("Sending…")
                            }
                        } else {
                            Text(uncertain ? "I checked, try again"
                                 : (failed ? "Try again" : (stuck ? "Send answer" : "Send it")))
                        }
                    }
                    .font(.callout.weight(.semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 11)
                    .background(Capsule().fill(Theme.champagne))
                    .foregroundStyle(Theme.ink)
                }
                .buttonStyle(.pressable)
                .disabled(sending || (stuck && !uncertain
                           && answer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty))
                Button {
                    Haptics.tap()
                    Task { await session.decline(job) }
                } label: {
                    Text("Not now")
                        .font(.callout.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 11)
                        .background(Capsule().strokeBorder(Theme.stroke))
                        .foregroundStyle(Theme.sand)
                }
                .buttonStyle(.pressable)
                .disabled(sending)
            }
            .opacity(sending ? 0.7 : 1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
    }
}

/// One line spoken in the current Listen session. Its own view so the
/// checkmark can spring and the hand can feel the promise being kept —
/// the moment "heard on the phone" becomes "held by her brain".
struct SessionLineRow: View {
    let line: AnticipySession.SessionLine
    @State private var celebrated = false

    var body: some View {
        HStack(alignment: .top, spacing: 6) {
            Image(systemName: line.received ? "checkmark.circle.fill" : "circle.dotted")
                .font(.caption)
                .foregroundStyle(line.received ? Theme.champagne : Theme.gray)
                .scaleEffect(line.received ? 1.0 : 0.9)
                .animation(Theme.springJoy, value: line.received)
                .padding(.top, 2)
                .accessibilityHidden(true)
            Text(line.text)
                .font(.footnote)
                .foregroundStyle(Theme.sand)
            if line.decision == "act" {
                Image(systemName: "bolt.fill")
                    .font(.caption2)
                    .foregroundStyle(Theme.champagne)
                    .padding(.top, 2)
                    .transition(.scale(scale: 0.8).combined(with: .opacity))
                    .accessibilityLabel("I'm acting on this")
            }
            Spacer(minLength: 0)
        }
        .animation(Theme.springJoy, value: line.decision)
        .onChange(of: line.received) { received in
            if received { Haptics.herMessage() }
        }
        .onChange(of: line.decision) { decision in
            // Guarded so the 3s poll can't re-fire the celebration.
            if decision == "act", !celebrated {
                celebrated = true
                Haptics.taskDone()
            }
        }
    }
}

/// A job the agent is working on right now. A row on the ink, not a card —
/// with real data the feed was 30 identical rectangles.
struct HandlingCard: View {
    let job: AgentJob
    @EnvironmentObject private var session: AnticipySession
    @State private var stopping = false

    /// What it is doing RIGHT NOW, in his words.
    ///
    /// The browser writes this to the job every four seconds while it works.
    /// Until it was shown here, a run that can last forty minutes displayed
    /// the words "I'm handling it" and nothing else — so a run going
    /// perfectly and a run that died twenty minutes ago looked exactly the
    /// same from the sofa. That is the whole "why is it always stalling?"
    /// feeling, and the information to answer it already existed.
    ///
    /// The browser guarantees this line names the site rather than the URL
    /// and the field rather than what was typed into it, so it is safe on a
    /// screen someone else can see.
    private var doingNow: String? {
        guard job.status == "running",
              let data = job.params.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let line = obj["_doing"] as? String else { return nil }
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    var body: some View {
        HStack(spacing: 12) {
            if job.status == "running" {
                BreathingDot(size: 8)
            } else {
                Image(systemName: "hourglass")
                    .foregroundStyle(Theme.gray)
                    .accessibilityHidden(true)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(job.status == "running" ? "I'm handling it" : "Queued for your browser")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Theme.champagne)
                Text(job.humanGoal)
                    .font(.system(size: 17))
                    .lineSpacing(3)
                    .foregroundStyle(Theme.ivory)
                if let doingNow {
                    Text(doingNow)
                        .font(.system(size: 13))
                        .foregroundStyle(Theme.sand)
                        .lineLimit(2)
                        .transition(.opacity)
                        .animation(Theme.spring, value: doingNow)
                        .accessibilityLabel("Currently \(doingNow)")
                }
            }
            Spacer()
            // THE ONLY STOP IN THIS PRODUCT WAS ON HIS LAPTOP.
            // HandlingCard carried no controls at all, so away from the desk,
            // watching a run head somewhere wrong, he could do nothing about
            // it. Same cancellation path as "Not now", so a stop from here
            // and a stop from Chrome mean one thing to the rest of the
            // system; the browser loop re-reads liveness immediately before
            // every irreversible action, so this lands before a submit.
            if job.status == "running" || job.status == "queued" {
                Button {
                    stopping = true
                    Task { _ = await session.stopRunning(job) }
                } label: {
                    Text(stopping ? "Stopping…" : "Stop")
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundStyle(stopping ? Theme.sand : Theme.champagne)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 7)
                        .overlay(Capsule().strokeBorder(Theme.stroke, lineWidth: 1))
                }
                .disabled(stopping)
                .accessibilityLabel(stopping ? "Stopping" : "Stop this task")
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, Theme.Space.base)
    }
}

/// A completed job with its result — or a failed one, which gets a plain
/// sentence and a way forward instead of a shrug and a stack trace.
/// Something she quietly looked into, delivered. Her sentence leads —
/// the card IS her speaking, not a log row. Tap to read the whole thing
/// (sources and all); collapsed it stays a glanceable three lines.
struct FoundCard: View {
    let event: BrainEvent
    @State private var expanded = false

    private var headline: String {
        // The goal reads like machine shorthand ("research dinner spots in
        // Vancouver"); soften it into the thing itself. The softening moved to
        // Humanize.goal so this card and the conversation cards share ONE
        // implementation; the fallback below is this card's own and unchanged.
        let g = (event.goal ?? "").trimmingCharacters(in: .whitespaces)
        guard !g.isEmpty else { return "Something you mentioned" }
        return Humanize.goal(g)
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "sparkle")
                .foregroundStyle(Theme.champagne)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 8) {
                Text(headline)
                    .font(.callout.weight(.medium))
                    .foregroundStyle(Theme.ivory)
                Text(event.text ?? "")
                    .font(.footnote)
                    .foregroundStyle(Theme.sand)
                    .lineLimit(expanded ? nil : 3)
                    .fixedSize(horizontal: false, vertical: expanded)
                    .contentShape(Rectangle())
                    .onTapGesture {
                        Haptics.tap()
                        withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() }
                    }
                if !expanded {
                    Text("tap for the full picture")
                        .font(.caption2)
                        .foregroundStyle(Theme.gray)
                }
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
    }
}

struct DoneCard: View {
    let job: AgentJob
    @EnvironmentObject var session: AnticipySession
    @State private var expanded = false
    @State private var showRaw = false

    private var succeeded: Bool { job.status == "done" }
    private var retrying: Bool { session.inFlight.contains(job.id) }
    private var retryFailed: Bool { session.failedWrites.contains(job.id) }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: succeeded ? "checkmark.circle.fill" : "exclamationmark.circle")
                .foregroundStyle(succeeded ? Theme.champagne : Theme.gray)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 8) {
                if succeeded {
                    // docs ex 77: the receipt leads. This used to lead with the
                    // goal in callout weight and put the confirmation number
                    // underneath in grey footnote with a three-line clamp - the
                    // one thing the person opened the app for, rendered as the
                    // small print under a restated question.
                    let card = JobReceiptPolicy.doneCard(goal: job.humanGoal, result: job.result)
                    Text(card.lead)
                        .font(.callout.weight(.medium))
                        .foregroundStyle(card.hasReceipt ? Theme.ivory : Theme.sand)
                        .fixedSize(horizontal: false, vertical: true)
                        .lineLimit(expanded ? nil : 4)
                        .contentShape(Rectangle())
                        .onTapGesture {
                            Haptics.tap()
                            withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() }
                        }
                    if let context = card.context {
                        Text(context)
                            .font(.footnote)
                            .foregroundStyle(Theme.gray)
                    }
                } else {
                    Text(job.humanGoal)
                        .font(.callout.weight(.medium))
                        .foregroundStyle(Theme.ivory)
                    Text(job.failureLine)
                        .font(.footnote)
                        .foregroundStyle(Theme.sand)
                        .fixedSize(horizontal: false, vertical: true)
                    // docs ex 78: a failed card must answer THREE things -
                    // what happened, is my stuff safe, what do I do next.
                    // failureLine answers the first and the retry button the
                    // third; the middle one was simply absent, so a person
                    // reading "I couldn't finish this" had no idea whether
                    // twenty minutes of filled form was still there. Part 3:
                    // "Work is never destroyed" - which is worth nothing if
                    // the person cannot tell.
                    Text(job.safetyLine)
                        .font(.caption)
                        .foregroundStyle(Theme.gray)
                        .fixedSize(horizontal: false, vertical: true)
                    if retryFailed {
                        Text("I couldn't even queue it back up. I can't reach Anticipy Claude Version.")
                            .font(.caption)
                            .foregroundStyle(Theme.gray)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    VStack(alignment: .leading, spacing: 8) {
                        // A terminal attempt stays immutable. Retrying starts
                        // a new request rather than rewriting a failed record.
                        Button {
                            Task { await session.requestFreshRetry(job) }
                        } label: {
                            Group {
                                if retrying {
                                    HStack(spacing: 8) {
                                        BreathingDot(size: 6)
                                        Text("Queueing…")
                                    }
                                } else {
                                    Text("Start a fresh attempt")
                                }
                            }
                            .font(.caption.weight(.semibold))
                            .padding(.horizontal, 16)
                            .padding(.vertical, 8)
                            .background(Capsule().fill(Theme.champagne))
                            .foregroundStyle(Theme.ink)
                        }
                        .buttonStyle(.pressable)
                        .disabled(retrying)
                        Text("This failed attempt stays in history; the retry gets its own approval and result.")
                            .font(.caption2)
                            .foregroundStyle(Theme.gray)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .opacity(retrying ? 0.7 : 1)
                    // The raw string is a JavaScript exception. It stays
                    // available and stops being the headline.
                    if let r = job.result, !r.isEmpty {
                        Button {
                            Haptics.tap()
                            withAnimation(.easeInOut(duration: 0.2)) { showRaw.toggle() }
                        } label: {
                            Label(showRaw ? "Hide the details" : "Show me the details",
                                  systemImage: showRaw ? "chevron.up" : "chevron.down")
                                .font(.caption)
                                .foregroundStyle(Theme.gray)
                        }
                        .buttonStyle(.pressable)
                        if showRaw {
                            Text(r)
                                .font(.caption2.monospaced())
                                .foregroundStyle(Theme.gray)
                                .textSelection(.enabled)
                                .fixedSize(horizontal: false, vertical: true)
                                .padding(10)
                                .background(RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous).fill(Theme.surface))
                        }
                    }
                }
            }
            Spacer()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, Theme.Space.base)
    }
}

struct TranscriptRow: View {
    let line: AnticipySession.TranscriptLine
    @EnvironmentObject var session: AnticipySession
    /// "Thinking…" used to sit on a line for hours if the worker stalled,
    /// with nothing to tap. After a minute and a half it stops pretending.
    @State private var waitedTooLong = false

    private var local: Bool { line.id.hasPrefix("local-") }

    /// The instant the product becomes real — a line flipping to "act" —
    /// arrives on the joy spring, once.
    @State private var celebrated = false

    var body: some View {
        // Speech looks like speech: a champagne rule at the edge, her words
        // at voice size, no container.
        HStack(alignment: .top, spacing: 12) {
            Capsule()
                .fill(Theme.champagne.opacity(line.decision == "act" && celebrated ? 1.0 : 0.35))
                .frame(width: 2)
                .animation(Theme.spring, value: celebrated)
            VStack(alignment: .leading, spacing: 5) {
            Text(line.text)
                .font(.system(size: 17))
                .lineSpacing(3)
                .foregroundStyle(Theme.ivory)
            switch line.decision {
            case "act":
                HStack(spacing: 5) {
                    Image(systemName: "bolt.fill").accessibilityHidden(true)
                    Text("On it")
                }
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(Theme.champagne)
                .transition(.scale(scale: 0.8).combined(with: .opacity))
            case "ask":
                HStack(spacing: 5) {
                    Image(systemName: "questionmark.circle").accessibilityHidden(true)
                    Text("Quick question for you")
                }
                .font(.caption.weight(.medium))
                .foregroundStyle(Theme.champagne)
            case "ignore":
                // Two different silences, finally told apart. "Ignored with
                // a goal" means she quietly started work because of this
                // line — Omar watched her research Paris flights behind
                // "Noted — nothing needed" and reasonably concluded she was
                // dead. Truly-left-alone keeps the plain label.
                if line.goal?.isEmpty == false {
                    HStack(spacing: 5) {
                        Image(systemName: "magnifyingglass").accessibilityHidden(true)
                        Text("Looking into it. I'll text you what I find")
                    }
                    .font(.caption.weight(.medium))
                    .foregroundStyle(Theme.champagne.opacity(0.85))
                } else {
                    Text("Noted. Nothing needed")
                        .font(.caption)
                        .foregroundStyle(Theme.gray)
                }
            default:
                if waitedTooLong {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(local
                             ? "This one is still on your phone, it hasn't reached me yet."
                             : "I have this, but I haven't come back with anything on it.")
                            .font(.caption)
                            .foregroundStyle(Theme.gray)
                            .fixedSize(horizontal: false, vertical: true)
                        Button {
                            Task { await session.refresh() }
                        } label: {
                            Label(local ? "Send it now" : "Check again", systemImage: "arrow.clockwise")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(Theme.champagne)
                        }
                        .buttonStyle(.pressable)
                    }
                } else {
                    // A line still on this phone hasn't reached the brain yet —
                    // saying "Thinking…" about it would be a lie the moment the
                    // network dropped it.
                    Text(local ? "Sending…" : "Thinking…")
                        .font(.caption)
                        .foregroundStyle(Theme.gray)
                }
            }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .animation(Theme.springJoy, value: line.decision)
        .onChange(of: line.decision) { decision in
            guard decision == "act", !celebrated else { return }
            celebrated = true
            Haptics.taskDone()
            // The rule flashes to full for a moment, then settles.
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
                withAnimation(Theme.spring) { celebrated = false }
            }
        }
        .task(id: line.id) {
            waitedTooLong = false
            guard line.decision == nil else { return }
            try? await Task.sleep(nanoseconds: 90_000_000_000)
            waitedTooLong = true
        }
    }
}
