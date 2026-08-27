import SwiftUI

/// Whether she is listening, what she has heard nothing for, and the way to
/// stop her.
///
/// Screens 6 and 7 of the seven: two-line rows whose height follows their own
/// text, and a pick-one group marked by a CHECKMARK rather than hidden behind a
/// menu. The pause durations used to live in a `Menu`, which is the jam-shelf
/// problem in miniature — a person had to tap to find out what the choices even
/// were. They are on the screen now.
///
/// FIX 19 IS NOT UNDONE. That menu also carried "Until I turn it back on",
/// which called the identical function as the Stop button four lines above it.
/// It was deleted for being a second copy of a control already on screen, and
/// it does not come back here: the durations are durations, and stopping is
/// stopping.
///
/// FIX 8'S LINE IS CARRIED WHOLE, including the argument under it. `capturing`
/// is `isListening && !suspended` — the app's own INTENT flags — so the state
/// row above can say "I'm listening on this phone" during exactly the
/// thirty-hour-deaf case `CLAUDE.md` records. The measured line is the only
/// thing on this screen that can contradict it, and it is allowed to: no
/// threshold, no colour, no verdict. The same sentence reads "Nothing heard for
/// 4 min" on a healthy phone and "Nothing heard for 6 hr 20 min" on a dead one,
/// and the reader judges.
struct SettingsListeningView: View {
    @ObservedObject var session: AnticipySession
    @Environment(\.dismiss) private var dismiss

    @AppStorage("listeningPauseUntil") private var pauseUntil: Double = 0
    @State private var unheardLine: String?
    @State private var resumeTask: Task<Void, Never>?
    @State private var showDiagnostics = false

    private var pauseEnds: Date? {
        guard pauseUntil != 0 else { return nil }
        let d = Date(timeIntervalSinceReferenceDate: pauseUntil)
        return d > Date() ? d : nil
    }

    /// The two flags that decide what silence MEANS, and both are needed.
    /// `capturing` alone cannot see the stop-while-interrupted case at all:
    /// `suspended` already made it false, so turning listening off does not
    /// change it, and the line would go on describing a gap the owner just
    /// chose.
    private var listeningIntent: [Bool] {
        [session.listener.isListening, session.listener.suspended]
    }

    var body: some View {
        SheetChrome(title: "Listening", leading: .back) {
            dismiss()
        } content: {
            GroupedCard {
                StateRow("Right now", state: stateWord)
            }

            // Recomputed on the intent flags, never captured once. She opens
            // this screen during an interruption, reads "Nothing heard for
            // 12 min", taps Stop — the reaction the line is FOR — and a
            // captured number would go on saying it over silence she chose.
            // Inverted it is worse: the call ends, the watchdog takes the
            // microphone back, words are being transcribed in front of her, and
            // the row still claims nothing has been heard since before lunch.
            if let unheardLine {
                FootnoteText(unheardLine)
            }

            GroupedCard {
                if session.listener.isListening {
                    DestructiveRow("Stop listening", systemImage: "stop.circle") {
                        Haptics.engage()
                        stopNow()
                    }
                } else {
                    NavRow("Start listening", systemImage: "waveform") {
                        Haptics.engage()
                        startNow()
                    }
                }
            }

            SectionHeader("Pause for a while")

            // A pick-one group with the choices ON the screen. `isSelected`
            // reads the live deadline rather than a local pick, so a pause
            // armed on a previous visit shows as chosen when this reopens.
            GroupedCard {
                SelectRow("15 minutes",
                          subtitle: "Then she starts again on her own.",
                          isSelected: isPaused(minutes: 15)) {
                    Haptics.engage()
                    pause(minutes: 15)
                }
                SelectRow("1 hour",
                          subtitle: "Then she starts again on her own.",
                          isSelected: isPaused(minutes: 60)) {
                    Haptics.engage()
                    pause(minutes: 60)
                }
            }

            if let ends = pauseEnds {
                FootnoteText("Paused. She starts again at "
                             + ends.formatted(date: .omitted, time: .shortened)
                             + ", unless you start her sooner.")
            }

            // Ships in RELEASE, unlike the haptics panel. The stranger week is
            // a release build on somebody else's phone, and the day worth
            // reading is the day something went wrong on it — a DEBUG-only
            // diagnostic cannot be read from the one device in question.
            GroupedCard {
                DisclosureRow("Find out what listening actually did",
                              subtitle: "Every start, stop and silence, with the "
                                  + "log behind it.",
                              systemImage: "list.bullet.rectangle") {
                    Haptics.engage()
                    showDiagnostics = true
                }
            }
        }
        .navigationDestination(isPresented: $showDiagnostics) {
            ListeningDiagnosticsView()
        }
        .task(id: listeningIntent) { unheardLine = await Self.unheardLine() }
        .onAppear(perform: syncPause)
    }

    /// What the state row says. Three answers, because "not listening" is two
    /// different states and a paused phone is not a stopped one.
    private var stateWord: String {
        if pauseEnds != nil { return "Paused" }
        if session.listener.suspended { return "Interrupted" }
        return session.listener.isListening ? "Listening" : "Off"
    }

    private func isPaused(minutes: Int) -> Bool {
        guard let ends = pauseEnds else { return false }
        // Within half a minute of the deadline this duration would have set:
        // the stored value is an absolute instant, so the only honest way to
        // ask "was it this one" is to compare what it would have produced.
        return abs(ends.timeIntervalSinceNow - Double(minutes) * 60) < 30
            || ends.timeIntervalSinceNow < Double(minutes) * 60
    }

    /// What this phone has heard nothing for, as of right now.
    ///
    /// Off the main actor: `persistedEvents` parses up to 512KB off disk, and
    /// this screen must not do that on the thread drawing it.
    private static func unheardLine() async -> String? {
        await Task.detached(priority: .utility) {
            UnheardLine.words(ListenTally.of(ListenJournal.shared.persistedEvents,
                                             now: Date()))
        }.value
    }

    private func startNow() {
        endPause()
        session.startListening()
    }

    private func stopNow() {
        endPause()
        session.stopListening()
    }

    private func pause(minutes: Int) {
        let deadline = Date().addingTimeInterval(Double(minutes) * 60)
        session.stopListening()
        pauseUntil = deadline.timeIntervalSinceReferenceDate
        armResume(at: deadline)
    }

    private func endPause() {
        resumeTask?.cancel()
        resumeTask = nil
        pauseUntil = 0
    }

    /// Re-arm (or clear) the timer when this screen appears — the pause can
    /// outlive the view that started it, and a second visit should not leave
    /// the promise unattended. A deadline that expired while the app was gone
    /// is simply dropped: she stays off until asked, which is the safe way for
    /// this to fail.
    private func syncPause() {
        if let ends = pauseEnds {
            armResume(at: ends)
        } else if pauseUntil != 0 {
            pauseUntil = 0
        }
    }

    private func armResume(at deadline: Date) {
        resumeTask?.cancel()
        let stamp = deadline.timeIntervalSinceReferenceDate
        resumeTask = Task { @MainActor in
            let seconds = deadline.timeIntervalSinceNow
            if seconds > 0 {
                try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
            }
            // Only the timer that still owns this deadline gets to act, so a
            // re-armed duplicate can never restart her behind a cancel.
            guard !Task.isCancelled, pauseUntil == stamp else { return }
            pauseUntil = 0
            session.startListening()
        }
    }
}
