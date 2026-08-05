import SwiftUI

/// She learns your voice — the one time you ever have to help her with it.
///
/// One lit thing on a dark screen: a sentence to read, a breathing dot, and
/// her promise that the recording never leaves the phone. No waveform
/// science, no percentages, no developer language.
struct VoiceEnrollView: View {
    @EnvironmentObject var session: AnticipySession
    @Environment(\.dismiss) private var dismiss

    /// Long enough for a stable voiceprint, short enough that nobody minds.
    private let seconds: Double = 12
    /// Phonetically varied so a few seconds carry a lot of voice. Reading
    /// beats free speech here: everyone stalls when told "just talk".
    private let script = "Hey — it's me. I'm the one you're listening for. "
        + "Tomorrow's a long day, so keep an ear out for anything I promise "
        + "someone, and I'll take it from there."

    @State private var phase: Phase = .intro
    @State private var remaining: Double = 0
    @State private var ticker: Timer?

    private enum Phase { case intro, recording, done, failed, unavailable }

    var body: some View {
        ZStack {
            Theme.ink.ignoresSafeArea()
            Theme.bloom(0.10, radius: 260).ignoresSafeArea()
            VStack(alignment: .leading, spacing: Theme.Space.roomy) {
                Spacer(minLength: 0)
                content
                Spacer(minLength: 0)
                footer
            }
            .padding(.horizontal, Theme.Space.card)
            .padding(.vertical, Theme.Space.roomy)
        }
        .onAppear {
            if !session.speakerTagger.available { phase = .unavailable }
        }
        .onDisappear { stop() }
    }

    @ViewBuilder private var content: some View {
        switch phase {
        case .intro:
            VStack(alignment: .leading, spacing: Theme.Space.base) {
                Text("Let me learn your voice.")
                    .font(Theme.display(30))
                    .foregroundStyle(Theme.ivory)
                Text("Then I can tell when it's you talking and when it's "
                     + "someone else — so I never mistake their plans for yours.")
                    .font(.system(size: 17))
                    .foregroundStyle(Theme.sand)
                    .fixedSize(horizontal: false, vertical: true)
                Text("This stays on your phone. Not the recording, not a copy, "
                     + "nothing. Only I ever use it, right here.")
                    .font(.system(size: 15))
                    .foregroundStyle(Theme.gray)
                    .fixedSize(horizontal: false, vertical: true)
            }
        case .recording:
            VStack(alignment: .leading, spacing: Theme.Space.roomy) {
                HStack(spacing: Theme.Space.snug) {
                    BreathingDot(size: 10)
                    Text("Listening")
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(Theme.champagne)
                }
                Text(script)
                    .font(Theme.display(24))
                    .lineSpacing(6)
                    .foregroundStyle(Theme.ivory)
                    .fixedSize(horizontal: false, vertical: true)
                Text("Read that out, in your normal voice.")
                    .font(.system(size: 15))
                    .foregroundStyle(Theme.gray)
            }
        case .done:
            VStack(alignment: .leading, spacing: Theme.Space.base) {
                Text("I've got you.")
                    .font(Theme.display(30))
                    .foregroundStyle(Theme.ivory)
                Text("I'll know your voice from now on — and I'll start "
                     + "learning the people you talk to most, so I can keep "
                     + "their promises separate from yours.")
                    .font(.system(size: 17))
                    .foregroundStyle(Theme.sand)
                    .fixedSize(horizontal: false, vertical: true)
            }
        case .failed:
            VStack(alignment: .leading, spacing: Theme.Space.base) {
                Text("That didn't take.")
                    .font(Theme.display(28))
                    .foregroundStyle(Theme.ivory)
                Text("I couldn't hear enough of you. Somewhere quieter, and "
                     + "a little closer to the phone.")
                    .font(.system(size: 17))
                    .foregroundStyle(Theme.sand)
                    .fixedSize(horizontal: false, vertical: true)
            }
        case .unavailable:
            VStack(alignment: .leading, spacing: Theme.Space.base) {
                Text("Not yet on this phone.")
                    .font(Theme.display(28))
                    .foregroundStyle(Theme.ivory)
                Text("Learning voices needs a piece I don't have here yet. "
                     + "Everything else works exactly as it does now.")
                    .font(.system(size: 17))
                    .foregroundStyle(Theme.sand)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    @ViewBuilder private var footer: some View {
        switch phase {
        case .intro:
            primary("Start") { begin() }
        case .recording:
            VStack(alignment: .leading, spacing: Theme.Space.snug) {
                ProgressView(value: max(0, seconds - remaining), total: seconds)
                    .tint(Theme.champagne)
                Text("\(Int(remaining.rounded()))s")
                    .font(.system(size: 13))
                    .foregroundStyle(Theme.gray)
            }
        case .done:
            primary("Done") { dismiss() }
        case .failed:
            primary("Try again") { phase = .intro }
        case .unavailable:
            primary("Alright") { dismiss() }
        }
    }

    private func primary(_ title: String, _ action: @escaping () -> Void) -> some View {
        Button(action: { Haptics.tap(); action() }) {
            Text(title)
                .font(.system(size: 17, weight: .semibold))
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(Capsule().fill(Theme.champagne))
                .foregroundStyle(Theme.ink)
        }
        .buttonStyle(.pressable)
    }

    // MARK: - the recording itself

    private func begin() {
        guard session.speakerTagger.available else { phase = .unavailable; return }
        // Start from silence so nothing said before "Start" is in the profile.
        _ = session.speakerTagger.drainWindow()
        session.listener.startForEnrollment()
        phase = .recording
        remaining = seconds
        ticker?.invalidate()
        ticker = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { t in
            remaining -= 0.1
            guard remaining <= 0 else { return }
            t.invalidate()
            finish()
        }
    }

    private func finish() {
        let samples = session.speakerTagger.drainWindow()
        session.listener.stopAfterEnrollment()
        let ok = session.speakerTagger.enrollOwner(from: samples)
        Haptics.taskDone()
        phase = ok ? .done : .failed
    }

    private func stop() {
        ticker?.invalidate()
        ticker = nil
        if phase == .recording { session.listener.stopAfterEnrollment() }
    }
}
