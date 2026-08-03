import SwiftUI

extension AgentJob {
    /// Goals are free-form model strings ("prepare Devon invoice email").
    /// Show them as a sentence — capitalize the first word, leave the rest
    /// human — instead of Title Casing Every Single Word.
    var humanGoal: String {
        let s = goal.replacingOccurrences(of: "_", with: " ")
        guard let first = s.first else { return s }
        return first.uppercased() + s.dropFirst()
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
            return "The page wouldn't load — that's usually the connection on your computer."
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
    private var handling: [AgentJob] { session.jobs.filter { $0.status == "queued" || $0.status == "running" } }
    private var finished: [AgentJob] { session.jobs.filter { $0.status == "done" || $0.status == "failed" } }

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
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        statusStrip
                        if micNeedsHelp { micRecoveryCard }
                        // Her briefing only appears over a verified read. She
                        // does not get to say "I've got the watch" from an app
                        // that has never once reached its own server.
                        if verified { anticipyCardView }
                        listenCard
                        if feedIsEmpty {
                            switch session.connection {
                            case .loading:          loadingState
                            case .offline:          offlineState
                            case .refused(let s):   refusedState(s)
                            case .ready:            emptyState
                            }
                        } else {
                            if !verified { staleNotice }
                            if !needsOK.isEmpty {
                                sectionHeader("Needs your OK")
                                    .onAppear { Haptics.engage() }
                                ForEach(needsOK) { ConfirmJobCard(job: $0) }
                            }
                            if !handling.isEmpty {
                                // Honest about WHY nothing is moving: with Chrome
                                // shut there are no hands, and saying "Handling"
                                // over a stalled queue is a small daily lie.
                                sectionHeader(session.agentOnline ? "Handling" : "Waiting for your browser")
                                if !session.agentOnline {
                                    Text(session.agentPaired
                                         ? "Open Chrome and these pick up on their own."
                                         : "Link Chrome in Settings and these pick up on their own.")
                                        .font(.caption)
                                        .foregroundStyle(Theme.gray)
                                }
                                ForEach(handling) { HandlingCard(job: $0) }
                            }
                            if !session.transcript.isEmpty {
                                sectionHeader("Heard")
                                ForEach(session.transcript.suffix(30).reversed()) { TranscriptRow(line: $0) }
                            }
                            if !finished.isEmpty {
                                sectionHeader("Done")
                                ForEach(finished.prefix(8)) { DoneCard(job: $0) }
                            }
                        }
                    }
                    .padding(.horizontal)
                    .padding(.bottom, 30)
                    // New cards ease in instead of teleporting — the feed
                    // should feel alive, not like a page reload.
                    .animation(Theme.spring, value: session.jobs)
                    .animation(Theme.spring, value: session.transcript)
                }
                .refreshable { await session.refresh() }
            }
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    HStack(spacing: 10) {
                        LogoMark(size: 26)
                            .accessibilityHidden(true)
                        Text("Anticipy")
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
            .toolbarBackground(Theme.ink, for: .navigationBar)
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
                        detail: pendant.battery.map { "\($0)%" },
                        note: pendantNote
                    )
                    statusPill(
                        icon: "macbook",
                        label: agentLabel,
                        active: session.agentOnline,
                        detail: session.agentLastSeenSeconds.map { "\($0)s" },
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
        if !verified { return "Chrome — can't check" }
        if !session.agentPaired { return "Chrome not linked" }
        return session.agentOnline ? "Chrome ready" : "Chrome asleep"
    }

    private var agentNote: String {
        if !verified { return "I can't reach my own server, so I can't tell you what Chrome is doing right now." }
        if !session.agentPaired { return "Chrome isn't linked to your phone yet. Linking it in Settings is what lets me actually do things on the web for you." }
        if session.agentOnline { return "Chrome is open and linked. That's where I do the doing." }
        return "Chrome is linked, but it isn't open. Anything I've queued waits there until you open it."
    }

    /// The pendant connects, and then nothing happens to what it hears — the
    /// audio frames are reassembled and dropped, because there is no
    /// transcription path behind them yet. Saying "Listening" here was the
    /// single most confident untrue thing on the screen.
    private var pendantLabel: String {
        switch pendant.state {
        case .connected: return "Pendant · not capturing"
        case .connecting: return "Pendant connecting"
        case .reconnecting: return "Pendant reconnecting"
        case .searching: return "Looking for pendant"
        case .unavailable: return "Bluetooth off"
        case .off: return pendant.hasPairedPendant ? "Pendant away" : "No pendant"
        }
    }

    private var pendantNote: String {
        switch pendant.state {
        case .connected: return "Your pendant is connected, but I can't turn what it hears into words yet. Use Listen with phone and I'll hear you that way."
        case .connecting, .reconnecting, .searching: return "I'm looking for your pendant. Listen with phone works right now either way."
        case .unavailable: return "Bluetooth is off, so I can't see the pendant."
        case .off: return pendant.hasPairedPendant
            ? "Your pendant is out of range or switched off."
            : "You don't have a pendant set up — you don't need one. Your phone is the microphone."
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
            Text("The microphone is switched off for Anticipy, so tapping Listen won't do anything. iOS only asks once — turn it back on and I'll start the moment you come back.")
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
            .accessibilityHint("Opens Anticipy's page in the iOS Settings app, where Microphone and Speech Recognition can be switched back on.")
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
                    Label(listenButtonLabel, systemImage: listenButtonIcon)
                        .font(.callout.weight(.semibold))
                        .padding(.horizontal, 14)
                        .padding(.vertical, 9)
                        .background(Capsule().fill(session.listener.isListening ? Theme.champagne : Theme.surface))
                        .foregroundStyle(listenButtonTint)
                }
                .buttonStyle(.pressable)
                // A tap that iOS will instantly refuse is worse than no
                // button: it reads as the app being broken.
                .disabled(micNeedsHelp)
                .accessibilityHint(micNeedsHelp ? "Unavailable until the microphone is switched back on in Settings." : "")
                if session.listener.isListening && !session.listener.suspended {
                    ProgressView().tint(Theme.champagne)
                }
                Spacer()
            }
            // Honesty over pretense: when iOS takes the mic (call, Siri,
            // route change), say so while recovery runs — never glow
            // "Listening" over a dead microphone.
            if session.listener.suspended {
                Label("Mic interrupted — taking it back…", systemImage: "exclamationmark.triangle")
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
                        HStack(alignment: .top, spacing: 6) {
                            Image(systemName: line.received ? "checkmark.circle.fill" : "circle.dotted")
                                .font(.caption)
                                .foregroundStyle(line.received ? Theme.champagne : Theme.gray)
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
                                    .accessibilityLabel("I'm acting on this")
                            }
                            Spacer(minLength: 0)
                        }
                    }
                }
                .padding(10)
                .background(RoundedRectangle(cornerRadius: 12).fill(Theme.surface.opacity(0.6)))
            }
            if !session.listener.partial.isEmpty {
                Text(session.listener.partial)
                    .font(.footnote)
                    .foregroundStyle(Theme.gray)
                    .italic()
            }
            HStack(spacing: 8) {
                TextField("Or tell Anticipy something…", text: $typedLine)
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
        return session.listener.isListening ? Theme.ink : Theme.sand
    }

    private func submitTyped() {
        let line = typedLine.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !line.isEmpty else { return }
        // heard() owns the haptic — a second tap here reads as a stutter-bug.
        typedLine = ""
        Task { await session.heard(line) }
    }

    /// Anticipy speaks first: a first-person briefing of what she heard and
    /// what she's handling, rebuilt live from the real job queue.
    private var anticipyCardView: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                LogoMark(size: 22)
                    .accessibilityHidden(true)
                Text("Anticipy")
                    .font(Theme.display(18))
                    .foregroundStyle(Theme.champagne)
                // Breathing means "she is doing something right now". A
                // connected pendant is not that: it captures nothing.
                if session.listener.isListening || !handling.isEmpty {
                    BreathingDot(size: 7)
                }
            }
            briefingView
            if let says = session.freshAnticipySays {
                Text(says)
                    .font(.footnote)
                    .foregroundStyle(Theme.sand)
                    .padding(.top, 2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
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
                    .font(.callout)
                    .foregroundStyle(Theme.ivory)
                    .fixedSize(horizontal: false, vertical: true)
                    .animation(Theme.spring, value: briefingText)
            } else {
                TypewriterText(text: briefingShown, font: .callout, color: Theme.ivory, speed: 45) {
                    briefingTyped = true
                }
            }
        }
        .onAppear {
            if briefingShown.isEmpty { briefingShown = briefingText }
        }
    }

    private var briefingText: String {
        var parts: [String] = [greeting]
        // Only the phone mic actually hears anything today.
        if session.listener.isListening {
            parts.append("I'm listening.")
        }
        if !needsOK.isEmpty {
            parts.append("I've got \(needsOK.count) thing\(needsOK.count == 1 ? "" : "s") ready — just say the word.")
        }
        if !handling.isEmpty {
            parts.append("I'm handling \(handling.count) task\(handling.count == 1 ? "" : "s") right now.")
        }
        if needsOK.isEmpty && handling.isEmpty {
            parts.append(session.listener.isListening ? idleLine : offLine)
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
            "Nothing needs you right now — I've got it covered.",
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
            : "I'm not listening yet — tap Listen with phone and I'll start picking things up."
    }

    private func sectionHeader(_ text: String) -> some View {
        Text(text)
            .font(Theme.display(21))
            .foregroundStyle(Theme.ivory)
            .padding(.top, 4)
    }

    // MARK: - The four empty screens

    /// Still asking. The first probe can take the full timeout, and this is
    /// the window in which the app used to paint the finished empty state.
    private var loadingState: some View {
        VStack(spacing: 14) {
            ProgressView()
                .tint(Theme.champagne)
                .scaleEffect(1.3)
                .padding(.top, 70)
                .padding(.bottom, 4)
            Text("One moment.")
                .font(Theme.display(26))
                .foregroundStyle(Theme.ivory)
            Text("I'm catching up on your day. This takes a second.")
                .font(.callout)
                .foregroundStyle(Theme.gray)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 24)
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
                .padding(.top, 70)
                .accessibilityHidden(true)
            Text("I can't reach my side.")
                .font(Theme.display(26))
                .foregroundStyle(Theme.ivory)
                .multilineTextAlignment(.center)
            Text(offlineBody)
                .font(.callout)
                .foregroundStyle(Theme.gray)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 24)
            retryButton("Try again")
        }
        .frame(maxWidth: .infinity)
    }

    private var offlineBody: String {
        let base = "Your phone can't get through to Anticipy right now — it's almost always the connection. You can keep talking to me either way."
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
                .padding(.top, 70)
                .accessibilityHidden(true)
            Text("Anticipy won't let me in.")
                .font(Theme.display(26))
                .foregroundStyle(Theme.ivory)
                .multilineTextAlignment(.center)
            Text(session.agentPaired
                 ? "I reached my server and it turned me away, so I can't show you your day. My key went stale — I'm getting a new one now. This should clear itself in a moment."
                 : "I reached my server and it turned me away. My phone gets its key from your linked Chrome, and nothing is linked yet — so I can't read your day until that's done. Settings › Browser agent.")
                .font(.callout)
                .foregroundStyle(Theme.gray)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 24)
            Text("Error \(status)")
                .font(.caption2)
                .foregroundStyle(Theme.stroke)
            retryButton("Try again")
        }
        .frame(maxWidth: .infinity)
    }

    /// The finished, confident screen. It is only ever allowed to appear over
    /// a read that actually succeeded and came back with nothing.
    private var emptyState: some View {
        VStack(spacing: 16) {
            LogoMark(size: 72)
                .padding(.top, 70)
                .accessibilityHidden(true)
            Text("Live your day.")
                .font(Theme.display(28))
                .foregroundStyle(Theme.ivory)
            Text("Anticipy listens, understands, and handles the follow-through — asking before anything is sent.")
                .font(.callout)
                .foregroundStyle(Theme.gray)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 24)
            retryButton("Check again")
        }
        .frame(maxWidth: .infinity)
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
                     ? "I can't reach Anticipy right now, so this is what I had a moment ago."
                     : "Anticipy turned me away just now, so this is what I had a moment ago.")
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

    private var stuck: Bool { job.status == "needs_user" }
    private var sending: Bool { session.inFlight.contains(job.id) }
    private var failed: Bool { session.failedWrites.contains(job.id) }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label(stuck ? "Stuck — I need you" : "Ready — say the word",
                  systemImage: stuck ? "hand.raised" : "checkmark.seal")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Theme.champagne)
            Text(job.humanGoal)
                .font(.body.weight(.semibold))
                .foregroundStyle(Theme.ivory)
            if let r = job.result, !r.isEmpty {
                Text(r).font(.footnote).foregroundStyle(Theme.sand)
            }
            // The write failed and the card is still sitting here. Without
            // this row that reads as a UI glitch, and the natural next move
            // is to tap Send again — which is how one email goes twice.
            if failed {
                Label("That didn't go through — I couldn't reach Anticipy. Nothing was sent.", systemImage: "exclamationmark.triangle")
                    .font(.caption)
                    .foregroundStyle(Theme.sand)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 10) {
                Button {
                    // No haptic here: confirm() buzzes only after the server
                    // has actually accepted it. This one used to buzz success
                    // before the request had even left the phone.
                    Task { await session.confirm(job) }
                } label: {
                    Group {
                        if sending {
                            HStack(spacing: 8) {
                                ProgressView().tint(Theme.ink)
                                Text("Sending…")
                            }
                        } else {
                            Text(failed ? "Try again" : (stuck ? "Try again" : "Send it"))
                        }
                    }
                    .font(.callout.weight(.semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 11)
                    .background(Capsule().fill(Theme.champagne))
                    .foregroundStyle(Theme.ink)
                }
                .buttonStyle(.pressable)
                .disabled(sending)
                Button {
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

/// A job the agent is working on right now.
struct HandlingCard: View {
    let job: AgentJob

    var body: some View {
        HStack(spacing: 12) {
            if job.status == "running" {
                ProgressView().tint(Theme.champagne)
            } else {
                Image(systemName: "hourglass")
                    .foregroundStyle(Theme.gray)
                    .accessibilityHidden(true)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(job.status == "running" ? "I'm handling it" : "Queued for your browser")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Theme.champagne)
                Text(job.humanGoal)
                    .font(.callout)
                    .foregroundStyle(Theme.ivory)
            }
            Spacer()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
    }
}

/// A completed job with its result — or a failed one, which gets a plain
/// sentence and a way forward instead of a shrug and a stack trace.
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
                Text(job.humanGoal)
                    .font(.callout.weight(.medium))
                    .foregroundStyle(Theme.ivory)
                if succeeded {
                    if let r = job.result, !r.isEmpty {
                        Text(r).font(.footnote).foregroundStyle(Theme.gray)
                            .lineLimit(expanded ? nil : 3)
                            .contentShape(Rectangle())
                            .onTapGesture {
                                Haptics.tap()
                                withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() }
                            }
                    }
                } else {
                    Text(job.failureLine)
                        .font(.footnote)
                        .foregroundStyle(Theme.sand)
                        .fixedSize(horizontal: false, vertical: true)
                    if retryFailed {
                        Text("I couldn't even queue it back up — I can't reach Anticipy.")
                            .font(.caption)
                            .foregroundStyle(Theme.gray)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    HStack(spacing: 10) {
                        // Failure was the one outcome in the whole app with no
                        // way forward. This puts it back in the queue.
                        Button {
                            Task { await session.confirm(job) }
                        } label: {
                            Group {
                                if retrying {
                                    HStack(spacing: 8) {
                                        ProgressView().tint(Theme.ink)
                                        Text("Queueing…")
                                    }
                                } else {
                                    Text("Try again")
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
                        Button {
                            Task { await session.decline(job) }
                        } label: {
                            Text("Let it go")
                                .font(.caption.weight(.semibold))
                                .padding(.horizontal, 16)
                                .padding(.vertical, 8)
                                .background(Capsule().strokeBorder(Theme.stroke))
                                .foregroundStyle(Theme.sand)
                        }
                        .buttonStyle(.pressable)
                        .disabled(retrying)
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
                                .background(RoundedRectangle(cornerRadius: 10).fill(Theme.surface))
                        }
                    }
                }
            }
            Spacer()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
    }
}

struct TranscriptRow: View {
    let line: AnticipySession.TranscriptLine
    @EnvironmentObject var session: AnticipySession
    /// "Thinking…" used to sit on a line for hours if the worker stalled,
    /// with nothing to tap. After a minute and a half it stops pretending.
    @State private var waitedTooLong = false

    private var local: Bool { line.id.hasPrefix("local-") }

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(line.text)
                .font(.callout)
                .foregroundStyle(Theme.ivory)
            switch line.decision {
            case "act":
                HStack(spacing: 5) {
                    Image(systemName: "bolt.fill").accessibilityHidden(true)
                    Text("On it")
                }
                .font(.caption.weight(.medium))
                .foregroundStyle(Theme.champagne)
            case "ask":
                HStack(spacing: 5) {
                    Image(systemName: "questionmark.circle").accessibilityHidden(true)
                    Text("Quick question for you")
                }
                .font(.caption.weight(.medium))
                .foregroundStyle(Theme.champagne)
            case "ignore":
                // Silence used to look like the app doing nothing at all;
                // say plainly that it heard and chose to leave it alone.
                Text("Noted — nothing needed")
                    .font(.caption)
                    .foregroundStyle(Theme.gray)
            default:
                if waitedTooLong {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(local
                             ? "This one is still on your phone — it hasn't reached me yet."
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
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
        .task(id: line.id) {
            waitedTooLong = false
            guard line.decision == nil else { return }
            try? await Task.sleep(nanoseconds: 90_000_000_000)
            waitedTooLong = true
        }
    }
}
