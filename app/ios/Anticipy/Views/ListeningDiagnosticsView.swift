import SwiftUI

/// What listening actually did today, and the log behind it.
///
/// SHIPS IN RELEASE, deliberately, unlike the haptics panel below it in
/// Settings. The stranger week is a release build installed by cable, and the
/// day worth reading is the day something went wrong on somebody else's phone.
/// A diagnostic that only exists in DEBUG cannot be read from the one device
/// whose behaviour is in question.
///
/// It also makes three comments in this codebase true. `ListenJournal`,
/// `PhoneListener` and `AnticipyApp` each already say the journal is
/// "exportable from Settings" — and until this screen existed, it was not.
/// Those comments are the privacy argument for what may be written into the
/// journal at all, so a claim that was not yet true was load-bearing.
///
/// Voice follows the haptics diagnostic: plain sentences, numbers with their
/// units, and no percentage dressed up as a score. Nobody is being graded here;
/// a person is being told what happened.
struct ListeningDiagnosticsView: View {
    @State private var lines: [String] = []
    @State private var tally = ListenTally()

    /// The last stretch worth reading. The whole file can be shared; the screen
    /// shows the tail, because a screen you must scroll for a minute to reach
    /// the end of is not a screen anybody reads.
    private let shown = 60

    var body: some View {
        List {
            Section("Today") {
                row("Times listening started", "\(tally.sessions)")
                row("Time spent listening", duration(tally.listeningSeconds))
                // The number this screen exists for. A call that ended
                // listening and was never restarted appears here as one
                // enormous stretch and almost nowhere else.
                row("Longest stretch hearing nothing", duration(tally.longestSilenceSeconds))
                row("Words sent", "\(tally.wordsFlushed)")
                if tally.flushes > 0 {
                    row("Sentences cut off by the clock",
                        "\(tally.flushesByReason["ceiling"] ?? 0) of \(tally.flushes)")
                }
                if tally.postsFailed > 0 {
                    // A day that heard everything and delivered nothing looks
                    // exactly like a microphone that heard nothing at all.
                    row("Lines that did not reach the server", "\(tally.postsFailed)")
                }
            }

            if !tally.stopsByCause.isEmpty || !tally.swapsByCause.isEmpty {
                Section("Why it stopped or restarted") {
                    ForEach(tally.stopsByCause.sorted(by: { $0.key < $1.key }), id: \.key) {
                        row(stopWording($0.key), "\($0.value)")
                    }
                    ForEach(tally.swapsByCause.sorted(by: { $0.key < $1.key }), id: \.key) {
                        row(swapWording($0.key), "\($0.value)")
                    }
                }
            }

            if !tally.notes.isEmpty {
                Section("What the phone reported") {
                    // The audio session as it ACTUALLY came back, not as it was
                    // asked for; low power mode; audio dropped while swapping.
                    // Deduped because a session fact repeats on every start and
                    // the same sentence twelve times is noise, not a finding.
                    ForEach(Array(NSOrderedSet(array: tally.notes)) as? [String] ?? [],
                            id: \.self) { note in
                        Text(note)
                            .font(Theme.aside)
                            .foregroundStyle(Theme.text2)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }

            Section("The log") {
                if lines.isEmpty {
                    Text("Nothing recorded yet. This fills in while I'm listening.")
                        .font(Theme.aside)
                        .foregroundStyle(Theme.muted)
                } else {
                    // Monospaced and verbatim: this is the raw record, and the
                    // point of showing it is that it has not been interpreted.
                    Text(lines.suffix(shown).joined(separator: "\n"))
                        .font(.system(.caption, design: .monospaced))
                        .foregroundStyle(Theme.text2)
                        .textSelection(.enabled)
                }
                if let file = ListenJournal.shared.fileURL {
                    ShareLink(item: file) { Text("Send me the whole log") }
                        .arrowRow()
                }
            }
        }
        .navigationTitle("Listening")
        .onAppear(perform: reload)
    }

    private func reload() {
        // The file, not the ring: the ring dies with the process and the
        // session worth reading is often the one that ended when it did.
        lines = ListenJournal.shared.persistedLines
        tally = ListenTally.of(ListenJournal.shared.persistedEvents)
    }

    private func row(_ name: String, _ value: String) -> some View {
        HStack {
            Text(name).font(.callout).foregroundStyle(Theme.text)
            Spacer(minLength: 12)
            Text(value).font(.callout).foregroundStyle(Theme.text2)
        }
    }

    /// Plain words, because the cause is the whole finding. "It stopped" is the
    /// useless half of the report, and the owner stopping it and iOS taking the
    /// microphone away are not the same event.
    private func stopWording(_ cause: String) -> String {
        switch cause {
        case "owner": return "You stopped it"
        case "interruption": return "A call or another app took the microphone"
        case "routeChange": return "Headphones or a speaker changed"
        case "authorizationLost": return "Permission was taken away"
        case "unrecoveredFailure": return "It failed and could not recover"
        default: return "Stopped: \(cause)"
        }
    }

    private func swapWording(_ cause: String) -> String {
        switch cause {
        case "error": return "Restarted after an error"
        case "taskLimit": return "Restarted at Apple's time limit"
        case "routeChange": return "Restarted after an audio change"
        case "silenceRotation": return "Restarted after a long silence"
        default: return "Restarted: \(cause)"
        }
    }

    /// Units a person reads, never raw seconds. "3570" is not an answer to
    /// "how long did it hear nothing".
    private func duration(_ seconds: Int) -> String {
        if seconds <= 0 { return "none" }
        if seconds < 60 { return "\(seconds) seconds" }
        let minutes = seconds / 60
        if minutes < 60 { return "\(minutes) min" }
        let hours = minutes / 60
        let rest = minutes % 60
        return rest == 0 ? "\(hours) hr" : "\(hours) hr \(rest) min"
    }
}
