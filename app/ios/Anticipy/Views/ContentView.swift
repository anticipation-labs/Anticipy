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
}

/// Home = the proactive feed: what Anticipy heard, what it's handling,
/// what needs your OK, and what's done — plus live connection health.
struct HomeView: View {
    @EnvironmentObject var pendant: PendantManager
    @EnvironmentObject var session: AnticipySession
    @Environment(\.scenePhase) private var scenePhase
    @State private var typedLine = ""

    private var needsOK: [AgentJob] { session.jobs.filter { $0.status == "awaiting_confirm" } }
    private var handling: [AgentJob] { session.jobs.filter { $0.status == "queued" || $0.status == "running" } }
    private var finished: [AgentJob] { session.jobs.filter { $0.status == "done" || $0.status == "failed" } }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.ink.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        statusStrip
                        anticipyCardView
                        listenCard
                        if needsOK.isEmpty && handling.isEmpty && finished.isEmpty && session.transcript.isEmpty {
                            emptyState
                        }
                        if !needsOK.isEmpty {
                            sectionHeader("Needs your OK")
                                .onAppear { Haptics.engage() }
                            ForEach(needsOK) { ConfirmJobCard(job: $0) }
                        }
                        if !handling.isEmpty {
                            sectionHeader("Handling")
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
                    .padding(.horizontal)
                    .padding(.bottom, 30)
                    // New cards ease in instead of teleporting — the feed
                    // should feel alive, not like a page reload.
                    .animation(.easeInOut(duration: 0.25), value: session.jobs)
                    .animation(.easeInOut(duration: 0.25), value: session.transcript)
                }
                .refreshable { await session.refresh() }
            }
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    HStack(spacing: 10) {
                        LogoMark(size: 26)
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
                }
            }
            .toolbarBackground(Theme.ink, for: .navigationBar)
            // If listening was on when the app closed or backgrounded, she
            // picks it back up herself — no button-press chore per open.
            .onAppear { session.resumeListeningIfWanted() }
            .onChange(of: scenePhase) { phase in
                if phase == .active { session.resumeListeningIfWanted() }
            }
        }
    }

    // MARK: - Status

    private var statusStrip: some View {
        HStack(spacing: 10) {
            statusPill(
                icon: "dot.radiowaves.left.and.right",
                label: pendantLabel,
                active: pendant.state == .connected,
                detail: pendant.battery.map { "\($0)%" }
            )
            statusPill(
                icon: "macbook",
                label: agentLabel,
                active: session.agentOnline,
                detail: session.agentLastSeenSeconds.map { "\($0)s" }
            )
            Spacer()
        }
        .padding(.top, 6)
    }

    private var agentLabel: String {
        if !session.backendReachable { return "Agent offline" }
        if !session.agentPaired { return "Agent unpaired" }
        return session.agentOnline ? "Agent live" : "Agent away"
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
                    Label(
                        session.listener.isListening ? "Listening with phone" : "Listen with phone",
                        systemImage: session.listener.isListening ? "mic.fill" : "mic"
                    )
                    .font(.callout.weight(.semibold))
                    .padding(.horizontal, 14)
                    .padding(.vertical, 9)
                    .background(Capsule().fill(session.listener.isListening ? Theme.champagne : Theme.surface))
                    .foregroundStyle(session.listener.isListening ? Theme.ink : Theme.sand)
                }
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
            // Revoked permission previously no-opped in total silence — the
            // one state she genuinely cannot fix herself, so she says so.
            if !session.listener.authorized {
                Label("I need microphone & speech access — Settings › Anticipy", systemImage: "mic.slash")
                    .font(.caption)
                    .foregroundStyle(Theme.gray)
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
                            Text(line.text)
                                .font(.footnote)
                                .foregroundStyle(Theme.sand)
                            if line.decision == "act" {
                                Image(systemName: "bolt.fill")
                                    .font(.caption2)
                                    .foregroundStyle(Theme.champagne)
                                    .padding(.top, 2)
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
                .disabled(typedLine.isEmpty)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 9)
            .background(RoundedRectangle(cornerRadius: 12).fill(Theme.surface))
        }
    }

    private func submitTyped() {
        let line = typedLine.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !line.isEmpty else { return }
        // heard() owns the haptic — a second tap here reads as a stutter-bug.
        typedLine = ""
        Task { await session.heard(line) }
    }

    private var pendantLabel: String {
        switch pendant.state {
        case .connected: return "Listening"
        case .connecting: return "Connecting"
        case .reconnecting: return "Reconnecting"
        case .searching: return "Searching"
        case .unavailable: return "Bluetooth off"
        case .off: return pendant.hasPairedPendant ? "Pendant away" : "No pendant"
        }
    }

    private func statusPill(icon: String, label: String, active: Bool, detail: String?) -> some View {
        HStack(spacing: 6) {
            Circle()
                .fill(active ? Theme.champagne : Theme.stroke)
                .frame(width: 7, height: 7)
            Image(systemName: icon).font(.caption)
            Text(label).font(.caption.weight(.medium))
            if let detail { Text(detail).font(.caption2).foregroundStyle(Theme.gray) }
        }
        .foregroundStyle(active ? Theme.ivory : Theme.gray)
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(Capsule().fill(Theme.surface))
    }

    /// Anticipy speaks first: a first-person briefing of what she heard and
    /// what she's handling, rebuilt live from the real job queue.
    private var anticipyCardView: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                LogoMark(size: 22)
                Text("Anticipy")
                    .font(Theme.display(18))
                    .foregroundStyle(Theme.champagne)
            }
            Text(briefingText)
                .font(.callout)
                .foregroundStyle(Theme.ivory)
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

    private var briefingText: String {
        var parts: [String] = [greeting]
        if pendant.state == .connected || session.listener.isListening {
            parts.append("I'm listening.")
        }
        if !needsOK.isEmpty {
            parts.append("I've got \(needsOK.count) thing\(needsOK.count == 1 ? "" : "s") ready — just say the word.")
        }
        if !handling.isEmpty {
            parts.append("I'm handling \(handling.count) task\(handling.count == 1 ? "" : "s") right now.")
        }
        if needsOK.isEmpty && handling.isEmpty {
            parts.append(idleLine)
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

    private func sectionHeader(_ text: String) -> some View {
        Text(text)
            .font(Theme.display(21))
            .foregroundStyle(Theme.ivory)
            .padding(.top, 4)
    }

    private var emptyState: some View {
        VStack(spacing: 16) {
            LogoMark(size: 72)
                .padding(.top, 70)
            Text("Live your day.")
                .font(Theme.display(28))
                .foregroundStyle(Theme.ivory)
            Text("Anticipy listens, understands, and handles the follow-through — asking before anything is sent.")
                .font(.callout)
                .foregroundStyle(Theme.gray)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 24)
        }
        .frame(maxWidth: .infinity)
    }
}

// MARK: - Cards

/// A job the agent prepared and is holding for your explicit go-ahead.
struct ConfirmJobCard: View {
    let job: AgentJob
    @EnvironmentObject var session: AnticipySession

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Label("Ready — say the word", systemImage: "checkmark.seal")
                .font(.caption.weight(.semibold))
                .foregroundStyle(Theme.champagne)
            Text(job.humanGoal)
                .font(.body.weight(.semibold))
                .foregroundStyle(Theme.ivory)
            if let r = job.result, !r.isEmpty {
                Text(r).font(.footnote).foregroundStyle(Theme.sand)
            }
            HStack(spacing: 10) {
                Button {
                    Haptics.success()
                    Task { await session.confirm(job) }
                } label: {
                    Text("Send it")
                        .font(.callout.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 11)
                        .background(Capsule().fill(Theme.champagne))
                        .foregroundStyle(Theme.ink)
                }
                Button {
                    Haptics.warning()
                    Task { await session.decline(job) }
                } label: {
                    Text("Not now")
                        .font(.callout.weight(.semibold))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 11)
                        .background(Capsule().strokeBorder(Theme.stroke))
                        .foregroundStyle(Theme.sand)
                }
            }
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
                Image(systemName: "hourglass").foregroundStyle(Theme.gray)
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

/// A completed (or failed) job with its result. Tapping expands the full
/// result text; failed jobs say so plainly.
struct DoneCard: View {
    let job: AgentJob
    @State private var expanded = false

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: job.status == "done" ? "checkmark.circle.fill" : "exclamationmark.circle")
                .foregroundStyle(job.status == "done" ? Theme.champagne : Theme.gray)
            VStack(alignment: .leading, spacing: 3) {
                Text(job.humanGoal)
                    .font(.callout.weight(.medium))
                    .foregroundStyle(Theme.ivory)
                if job.status != "done" {
                    Text("Couldn't finish this one")
                        .font(.caption.weight(.medium))
                        .foregroundStyle(Theme.gray)
                }
                if let r = job.result, !r.isEmpty {
                    Text(r).font(.footnote).foregroundStyle(Theme.gray)
                        .lineLimit(expanded ? nil : 3)
                }
            }
            Spacer()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
        .contentShape(Rectangle())
        .onTapGesture {
            Haptics.tap()
            withAnimation(.easeInOut(duration: 0.2)) { expanded.toggle() }
        }
    }
}

struct TranscriptRow: View {
    let line: AnticipySession.TranscriptLine

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(line.text)
                .font(.callout)
                .foregroundStyle(Theme.ivory)
            switch line.decision {
            case "act":
                HStack(spacing: 5) {
                    Image(systemName: "bolt.fill")
                    Text("On it")
                }
                .font(.caption.weight(.medium))
                .foregroundStyle(Theme.champagne)
            case "ask":
                HStack(spacing: 5) {
                    Image(systemName: "questionmark.circle")
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
                Text("Thinking…")
                    .font(.caption)
                    .foregroundStyle(Theme.gray)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .anticipyCard()
    }
}
