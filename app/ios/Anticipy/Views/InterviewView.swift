import SwiftUI

/// Her asking about your life, one question at a time.
///
/// A CONVERSATION, NOT A SURVEY (`design/briefs/08-day-zero.md:29`). The
/// difference is not decoration — it is the whole reason this exists rather than
/// a settings form:
///
///   - ONE question on screen. Never a scrollable stack of labelled fields.
///   - Her question is TYPED OUT, because it is a thing she is saying. The
///     typewriter is banned on permission copy and error text
///     (`CONSUMER-FEEL-DIRECTION` §2.7) — this is neither.
///   - Every answer she keeps appears immediately as a line she now knows. That
///     visible accumulation is what makes the screen legible to somebody with no
///     idea what this product is: you can watch it learn.
///   - Skip is a real button at a real size, and a skip records NOTHING.
struct InterviewView: View {
    @EnvironmentObject var session: AnticipySession
    @Environment(\.dismiss) private var dismiss
    /// MOTION SENSITIVITY. Read so the animations below can stand down; the
    /// beat is kept either way, so a flow under Reduce Motion takes the same
    /// time and simply shows its finished frame rather than travelling to it.
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    /// The questions still open, captured once on appear. Recomputing from
    /// progress mid-flow would make the list shrink under the person as they
    /// answer, which is how a five-question conversation starts feeling endless.
    @State private var queue: [InterviewQuestion] = []
    @State private var index = 0
    @State private var answer = ""
    @State private var saving = false
    @State private var failed = false
    /// What she has learned in this sitting, newest last. Shown, not stored —
    /// memory is the single home for what she knows.
    @State private var learned: [String] = []
    @FocusState private var typing: Bool

    private var current: InterviewQuestion? {
        index < queue.count ? queue[index] : nil
    }

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()
            if let question = current {
                asking(question)
            } else {
                done
            }
        }
        .grainOverlay()
        .onAppear {
            queue = InterviewProgress().remaining
            // Nothing left to ask. Not an error and not an empty screen —
            // the closing page is the honest answer.
            if queue.isEmpty { index = 0 }
        }
    }

    // MARK: - Asking

    private func asking(_ question: InterviewQuestion) -> some View {
        VStack(alignment: .leading, spacing: Theme.Space.base) {
            header(question)

            // The one lit thing on the screen, and it is her question.
            // Keyed on the id so a new question re-types rather than mutating
            // the sentence already on screen.
            TypewriterText(text: question.asks,
                           font: Theme.display(30),
                           color: Theme.text)
                .id(question.id)
                .fixedSize(horizontal: false, vertical: true)

            Text(question.why)
                .font(Theme.aside)
                .foregroundStyle(Theme.text2)
                .fixedSize(horizontal: false, vertical: true)

            TextField(question.hint, text: $answer, axis: .vertical)
                .font(Theme.voice)
                .foregroundStyle(Theme.text)
                .lineLimit(1...4)
                .focused($typing)
                .padding(.vertical, 12)
                .padding(.horizontal, Theme.Space.base)
                .background(
                    RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                        .fill(Theme.surface)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: Theme.Radius.small, style: .continuous)
                        .strokeBorder(answer.isEmpty ? Theme.edge : Theme.accent,
                                      lineWidth: answer.isEmpty ? 1 : 1.5)
                        .animation(Theme.spring, value: answer.isEmpty)
                )
                .submitLabel(.done)
                .onSubmit { keep(question) }

            if failed {
                Text("That didn't reach me. Try again in a moment.")
                    .font(Theme.aside)
                    .foregroundStyle(Theme.alarm)
            }

            learnedSoFar

            Spacer(minLength: Theme.Space.base)
            footer(question)
        }
        .padding(.horizontal, 28)
        .padding(.top, Theme.Space.roomy)
        .padding(.bottom, 18)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    /// Progress as a rule list with a live marker, not wizard dots. Same gesture
    /// the extension's pairing page uses, and it reads as "how far through a
    /// conversation" rather than "how many forms remain".
    private func header(_ question: InterviewQuestion) -> some View {
        HStack(spacing: 6) {
            ForEach(Array(queue.enumerated()), id: \.element.id) { i, _ in
                Capsule()
                    .fill(i <= index ? Theme.accent : Theme.muted.opacity(0.35))
                    .frame(width: i == index ? 20 : 6, height: 4)
                    .animation(Theme.spring, value: index)
            }
            Spacer()
            // A way out of the conversation, not the point of it: ghost, and
            // it hugs its own words in the corner.
            Button("Done for now") { dismiss() }
                .buttonStyle(.ghost)
        }
        .padding(.bottom, Theme.Space.tight)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Question \(index + 1) of \(queue.count)")
    }

    /// The thing that makes this legible to a stranger: you can watch her learn.
    @ViewBuilder private var learnedSoFar: some View {
        if !learned.isEmpty {
            VStack(alignment: .leading, spacing: Theme.Space.tight) {
                Text("What I've got so far")
                    .font(.system(size: 11, weight: .semibold))
                    .tracking(1.1)
                    .textCase(.uppercase)
                    .foregroundStyle(Theme.muted)
                ForEach(learned, id: \.self) { line in
                    Text(line)
                        .font(Theme.aside)
                        .foregroundStyle(Theme.text2)
                        .fixedSize(horizontal: false, vertical: true)
                        // Each new thing she has got still slides in from the
                        // left, which is what makes the list read as her
                        // learning; it used to slide in beside a hairline.
                        .transition(.asymmetric(insertion: .move(edge: .leading).combined(with: .opacity),
                                                removal: .opacity))
                }
            }
            .animation(Theme.springSlow, value: learned)
        }
    }

    private func footer(_ question: InterviewQuestion) -> some View {
        VStack(spacing: 4) {
            Button { keep(question) } label: {
                Text(saving ? "Remembering…" : "That's it")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.glass)
            // The style dims what is disabled; the call site used to pick its
            // own 0.5 and no two screens agreed.
            .disabled(saving || answer.trimmingCharacters(in: .whitespaces).isEmpty)

            // Equal weight, real tap target. A skip records nothing at all.
            // The touch haptic is the style's now, so this fires none of its
            // own — it used to buzz twice per tap.
            Button {
                advance()
            } label: {
                Text("Skip this one")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.ghost)
        }
    }

    // MARK: - Closing

    private var done: some View {
        VStack(spacing: Theme.Space.roomy) {
            Spacer()
            LogoMark(size: 96)
                .accessibilityHidden(true)
            TypewriterText(
                text: learned.isEmpty
                    ? "Whenever you're ready."
                    : "That's \(learned.count) thing\(learned.count == 1 ? "" : "s") I didn't know.",
                font: Theme.display(28),
                color: Theme.text)
                .multilineTextAlignment(.center)
            Text(learned.isEmpty
                 ? "Nothing written down. Ask me again any time."
                 : "I'll use it the moment it's useful, and never before you've said yes.")
                .font(Theme.aside)
                .foregroundStyle(Theme.text2)
                .multilineTextAlignment(.center)
            Spacer()
            Button { dismiss() } label: {
                Text("Done")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.glass)
        }
        .padding(.horizontal, 28)
        .padding(.bottom, 18)
        .onAppear { Haptics.taskDone() }
    }

    // MARK: - Moving

    private func keep(_ question: InterviewQuestion) {
        let text = answer.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        saving = true
        failed = false
        typing = false
        Task {
            let ok = await session.sendInterviewAnswer(question, answer: text)
            saving = false
            if ok {
                Haptics.engage()
                // Her wording, so what appears on screen is what she will
                // actually recall later — not a prettier version of it.
                withAnimation(reduceMotion ? nil : Theme.springSlow) { learned.append(question.fact(text)) }
                advance()
            } else {
                // The question stays open. Telling somebody she remembered a
                // thing she dropped is worse than telling them it failed.
                withAnimation(reduceMotion ? nil : Theme.spring) { failed = true }
            }
        }
    }

    private func advance() {
        answer = ""
        failed = false
        withAnimation(reduceMotion ? nil : Theme.springSlow) { index += 1 }
    }
}
