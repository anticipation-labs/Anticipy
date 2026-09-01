import SwiftUI

/// The places where a person deliberately teaches Anticipy. These were lost
/// when Settings moved from one long form to subpages; putting them together
/// restores the controls without mixing them into profile or diagnostics.
struct SettingsPersonalizationView: View {
    @ObservedObject var session: AnticipySession
    @Environment(\.dismiss) private var dismiss

    @AppStorage(FirstRunOwnership.flagKey) private var hasOnboarded = false
    @AppStorage(FirstRunOwnership.introKey) private var hasSeenIntro = false

    @State private var showInterview = false
    @State private var showVoiceEnrollment = false
    @State private var confirmReplay = false

    var body: some View {
        SheetChrome(title: "Personalization", leading: .back) {
            dismiss()
        } content: {
            SectionHeader("What matters to you")
            GroupedCard {
                DisclosureRow(interviewAction,
                              subtitle: interviewState,
                              systemImage: "quote.bubble") {
                    Haptics.engage()
                    if InterviewProgress().isComplete {
                        InterviewProgress().reopenAll()
                    }
                    showInterview = true
                }
            }
            FootnoteText("Your answers become profile memory on your account. Re-answering corrects what Anticipy knows instead of creating another survey record.")

            if session.speakerTagger.available {
                SectionHeader("Your voice")
                GroupedCard {
                    DisclosureRow(session.speakerTagger.hasOwnerProfile
                                      ? "Re-learn my voice"
                                      : "Learn my voice",
                                  subtitle: voiceState,
                                  systemImage: "waveform.badge.mic") {
                        Haptics.engage()
                        showVoiceEnrollment = true
                    }
                }
                FootnoteText("The recording and voiceprint stay on this iPhone. Only a speaker label can leave the device with a transcript line.")
            }

            SectionHeader("Welcome tour")
            GroupedCard {
                ActionRow("Replay the welcome tour",
                          subtitle: "See the introduction and setup guidance again.",
                          systemImage: "arrow.counterclockwise") {
                    confirmReplay = true
                }
            }
            FootnoteText("Replaying the tour does not change your profile, phone number, pairings, or saved preferences.")
        }
        .navigationDestination(isPresented: $showInterview) {
            InterviewView().environmentObject(session)
        }
        .navigationDestination(isPresented: $showVoiceEnrollment) {
            VoiceEnrollView().environmentObject(session)
        }
        .alert("Replay the welcome tour?", isPresented: $confirmReplay) {
            Button("Replay it") {
                hasOnboarded = false
                hasSeenIntro = false
                dismiss()
            }
            Button("Not now", role: .cancel) { }
        } message: {
            Text("It is the introduction and setup guidance you saw when you first opened Anticipy. Your existing setup stays as it is.")
        }
    }

    private var interviewAction: String {
        let progress = InterviewProgress()
        return InterviewInvitation.buttonLabel(
            remaining: progress.remaining.count,
            total: InterviewQuestion.script.count)
    }

    private var interviewState: String {
        let progress = InterviewProgress()
        let answered = progress.answeredCount
        if answered == 0 {
            let grants = ContextGrants()
            return InterviewInvitation.nothingAnswered(
                name: !session.ownerFirstName.isEmpty,
                number: !session.ownerPhone.isEmpty,
                calendar: grants.granted(.calendar),
                contacts: grants.granted(.contacts))
        }
        if progress.isComplete {
            return "All six are answered. Open this to go over them again."
        }
        return "\(answered) of \(InterviewQuestion.script.count) answered. Continue with what is still open."
    }

    private var voiceState: String {
        session.speakerTagger.hasOwnerProfile
            ? "This iPhone has a voice profile for you."
            : "Teach this iPhone which nearby voice is yours."
    }
}
