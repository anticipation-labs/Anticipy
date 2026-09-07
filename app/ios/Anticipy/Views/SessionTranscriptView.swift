import SwiftUI

// LIVES IN ITS OWN FILE, and that is not tidying. `HeardGroup.swift` is
// compiled STANDALONE by run_heard_group_tests.sh with swiftc, so a SwiftUI
// view in it fails that suite with "cannot find 'SheetChrome' in scope" while
// the Xcode build stays green — a break only the gate sees.

// ═══════════════════════════════════════════════════════════════════════════
// THE TRANSCRIPT'S HOME
// ═══════════════════════════════════════════════════════════════════════════


/// One past conversation, read back in full.
///
/// THE PLACE THE TRANSCRIPT LIVES NOW. The capture face shows what she is
/// DOING — the owner asked for that in as many words: "hide the transcript and
/// only show the task". But a transcript that is hidden everywhere is a
/// transcript that was deleted, and this product's whole claim is that it
/// heard you. So the words moved here rather than away: History → a
/// conversation → every line of it.
///
/// Until now tapping a row on the history list did nothing at all —
/// `onOpenSession` was wired to `{ _ in }` with the comment "opening one back
/// up is not built yet". This is that.
struct SessionTranscriptView: View {
    let title: String
    let when: String
    let lines: [AnticipySession.TranscriptLine]
    var onClose: () -> Void

    var body: some View {
        SheetChrome(title: "Conversation", leading: .back) {
            onClose()
        } content: {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(OnboardFont.question(22))
                    .foregroundStyle(OnboardTheme.ink)
                    .fixedSize(horizontal: false, vertical: true)
                Text(when)
                    .font(.system(size: 13))
                    .foregroundStyle(OnboardTheme.muted)
            }
            .padding(.bottom, 10)

            if lines.isEmpty {
                // Absent rather than empty, the way every other surface here
                // handles nothing-to-show.
                FootnoteText("Nothing was written down for this one.")
            } else {
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(lines) { line in
                        TranscriptLineRow(line: line)
                    }
                }
            }
        }
    }
}

/// One line, attributed.
///
/// The same rule the live thread follows: only an explicit "other" is drawn as
/// somebody else. `nil` means the phone could not tell, and guessing would put
/// words in a person's mouth — so an untagged line simply carries no
/// attribution rather than being credited to the owner.
private struct TranscriptLineRow: View {
    let line: AnticipySession.TranscriptLine

    private var isSomebodyElse: Bool { line.speaker == "other" }
    private var isOwner: Bool { line.speaker == "owner" }

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            if isSomebodyElse || isOwner {
                // NOT A NAME — the roster holds none. It says which of the two
                // things the tagger can actually know.
                Text(isSomebodyElse ? "Someone else" : "You")
                    .font(.system(size: 11, weight: .semibold))
                    .tracking(0.6)
                    .foregroundStyle(isSomebodyElse ? OnboardTheme.muted
                                                    : OnboardTheme.champagneInk)
            }
            Text(line.text)
                .font(.system(size: 15))
                .foregroundStyle(OnboardTheme.ink)
                .fixedSize(horizontal: false, vertical: true)
                .textSelection(.enabled)
            // What she made of it, when she made anything. The goal is the
            // brain's own words, never this file's reading of the line.
            if let goal = line.goal?.trimmingCharacters(in: .whitespacesAndNewlines),
               !goal.isEmpty {
                Label(goal, systemImage: "arrow.turn.down.right")
                    .font(.system(size: 13))
                    .foregroundStyle(OnboardTheme.text2)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }
}
