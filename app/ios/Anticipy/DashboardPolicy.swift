import Foundation

/// THE CONVERSATION DASHBOARD, decided in one pure place.
///
/// The screen where somebody talks to Anticipy has three faces — the thread
/// they read, the capture moment while she is listening, and the history of
/// past conversations — and which one is up, what it is titled, and what sits
/// in it are decisions rather than pixels. They live here so
/// `run_dashboard_tests.sh` can walk every state that a person can be in,
/// including the ones nobody can reach by tapping in a simulator: a refused
/// microphone mid-capture, a signal that dies with half a sentence
/// unsent, a thread whose newest row is an approval nobody has answered.
///
/// ── WHAT THIS FILE MAY NOT DO ─────────────────────────────────────────────
///
/// It may not read the WORDS. HARNESS-LAWS law 1: no regex, word list or
/// threshold may decide what a sentence MEANS. Every row that arrives here has
/// already been decided by the brain — a job carries `status` and `lane`, an
/// event carries `decision` — and this file arranges those verdicts in time.
/// It never looks for "remind me", never counts keywords, never guesses that a
/// line is a commitment because of how it reads. The runner greps this source
/// for exactly that and fails on it, because the tempting version of a
/// dashboard that "picks out your to-dos as you speak" is a keyword matcher
/// wearing a nice animation.
///
/// ── THE SEATBELT ──────────────────────────────────────────────────────────
///
/// Anything that needs the owner's OK enters the thread as its own turn and
/// may never be collapsed, summarised, or scrolled past silently:
/// `Turn.approval` is ordered like every other turn but `pendingApproval`
/// answers separately, so the screen can keep it in front of the person no
/// matter how far back in time it sits. Nothing sends without your OK is the
/// product's promise; a design that buries it is a design that broke it.
enum DashboardPolicy {

    // MARK: - Which face is up

    enum Mode: String, Equatable, CaseIterable {
        /// What she heard and what she did about it, read as a conversation.
        case thread
        /// She is listening right now, and this is the moment that says so.
        case capture
        /// Past conversations, newest first.
        case history
    }

    // MARK: - The capture moment

    /// What the listening screen says about itself. Four states, because a
    /// person mid-sentence needs to know which one they are in before they
    /// keep talking: a paused capture and a refused microphone look identical
    /// from the outside and mean opposite things.
    enum CaptureState: Equatable {
        /// The microphone is ours and running.
        case listening
        /// The owner pressed pause. Nothing is being heard, and that is on
        /// purpose, so the screen must not look broken.
        case paused
        /// iOS took the microphone away — a call, another app, a Setting.
        case interrupted
        /// iOS has the microphone switched off for this app entirely.
        case blocked
        /// Heard, but with nowhere to send it yet.
        case offline
    }

    struct CaptureFace: Equatable {
        let title: String
        let subtitle: String
        /// Whether the wave should move. A still wave under the word
        /// "Listening" is the one combination that lies.
        let alive: Bool
    }

    static func captureFace(_ state: CaptureState, heardAnything: Bool) -> CaptureFace {
        switch state {
        case .listening:
            return CaptureFace(
                title: "Listening…",
                subtitle: heardAnything
                    ? "Keep going. I'll bring forward only what matters."
                    : "Say anything. I'll keep track of what needs doing.",
                alive: true)
        case .paused:
            return CaptureFace(
                title: "Paused",
                subtitle: "I'm not hearing anything right now. Press play when you're ready.",
                alive: false)
        case .interrupted:
            return CaptureFace(
                title: "Something took the microphone",
                subtitle: "A call or another app has it. I'll pick up the moment it's free.",
                alive: false)
        case .blocked:
            return CaptureFace(
                title: "iOS has my microphone off",
                subtitle: "Switch it back on in Settings and I can listen again.",
                alive: false)
        case .offline:
            return CaptureFace(
                title: "Listening…",
                subtitle: "I can't reach my side, so I'm keeping this on your phone until I can.",
                alive: true)
        }
    }

    /// The state, read off the four facts the app already holds. Order is the
    /// whole of it: a blocked microphone outranks everything, because every
    /// other state would be a promise the phone cannot keep.
    static func captureState(micBlocked: Bool,
                             listening: Bool,
                             suspended: Bool,
                             reachable: Bool) -> CaptureState {
        if micBlocked { return .blocked }
        if suspended { return .interrupted }
        if !listening { return .paused }
        return reachable ? .listening : .offline
    }

    // MARK: - The thread

    /// One turn in the conversation. Every case carries a verdict somebody
    /// else made; none of them is inferred from the text.
    enum Turn: Equatable {
        /// Something the owner said or typed.
        case owner(id: String, text: String, at: String)
        /// She is working on it. The sentence is the brain's, not ours.
        case working(id: String, text: String, at: String)
        /// Something she found, did, or wants to say back.
        case said(id: String, text: String, at: String, done: Bool)
        /// Something that cannot happen until the owner says yes.
        case approval(id: String, goal: String, consequence: String?, at: String)
        /// A question she is waiting on an answer to.
        case question(id: String, text: String, at: String)

        var at: String {
            switch self {
            case .owner(_, _, let at), .working(_, _, let at),
                 .said(_, _, let at, _), .approval(_, _, _, let at),
                 .question(_, _, let at):
                return at
            }
        }

        var id: String {
            switch self {
            case .owner(let id, _, _), .working(let id, _, _),
                 .said(let id, _, _, _), .approval(let id, _, _, _),
                 .question(let id, _, _):
                return id
            }
        }

        /// Does this turn hold the person up? Used to keep the seatbelt in
        /// front of them and for nothing else.
        var waitsOnTheOwner: Bool {
            switch self {
            case .approval, .question: return true
            default: return false
            }
        }
    }

    /// The rows as they arrive, already decided, with the fields this screen
    /// reads named explicitly. A struct rather than the app's own types so the
    /// suite can build a thread without a backend.
    struct JobRow: Equatable {
        let id: String
        let goal: String
        let consequence: String?
        let at: String
        /// `HomeFeedPolicy.placement` has already run. This is its answer.
        let placement: Placement

        /// NO `done` CASE, and that is a decision rather than an omission.
        /// Finished work goes to the deck at the foot of the thread, which
        /// carries the shelf rule that keeps the desk from becoming a
        /// landfill (`HomeFeedPolicy.shelved`). A conversation that also
        /// recites every errand it ever finished is a conversation nobody
        /// scrolls to the bottom of.
        enum Placement: String, Equatable { case needsYou, handling }
    }

    struct SaidRow: Equatable {
        let id: String
        let text: String
        let at: String
        /// The brain's own verdict: "done", "ask", "clock".
        let decision: String
    }

    struct HeardRow: Equatable {
        let id: String
        let text: String
        let at: String
    }

    /// Assemble the thread. Oldest first, because a conversation is read
    /// downwards and the newest thing belongs nearest the control that answers
    /// it — the same order every messaging app on the phone uses.
    ///
    /// Ties are broken by id, so two rows written in the same second do not
    /// swap places between two redraws of the same screen.
    static func thread(heard: [HeardRow], said: [SaidRow], jobs: [JobRow]) -> [Turn] {
        var turns: [Turn] = []
        turns.reserveCapacity(heard.count + said.count + jobs.count)

        for row in heard where !row.text.isEmpty {
            turns.append(.owner(id: row.id, text: row.text, at: row.at))
        }
        for row in said where !row.text.isEmpty {
            switch row.decision {
            case "done":
                turns.append(.said(id: row.id, text: row.text, at: row.at, done: true))
            case "ask", "clock":
                turns.append(.question(id: row.id, text: row.text, at: row.at))
            default:
                turns.append(.said(id: row.id, text: row.text, at: row.at, done: false))
            }
        }
        for row in jobs {
            switch row.placement {
            case .needsYou:
                turns.append(.approval(id: row.id, goal: row.goal,
                                       consequence: row.consequence, at: row.at))
            case .handling:
                turns.append(.working(id: row.id, text: row.goal, at: row.at))
            }
        }

        return turns.sorted {
            $0.at == $1.at ? $0.id < $1.id : $0.at < $1.at
        }
    }

    /// The one turn the screen keeps in front of the person however far they
    /// have scrolled. The OLDEST unanswered approval, not the newest: the
    /// thing that has been waiting longest is the thing most likely to have
    /// been forgotten, and answering them in order is the only order that
    /// cannot strand one at the bottom forever.
    static func pendingApproval(in turns: [Turn]) -> Turn? {
        turns.first { if case .approval = $0 { return true } else { return false } }
    }

    // MARK: - History

    /// A past conversation, as the list shows it.
    struct Session: Equatable {
        let id: String
        let title: String
        /// ISO-8601, as every row on this phone carries it.
        let at: String
    }

    /// Group by day, newest day first and newest conversation first inside it.
    /// The heading is relative for the two days a person thinks of by name and
    /// a date after that, which is what makes a list of forty rows readable.
    struct Day: Equatable {
        let heading: String
        let sessions: [Session]
    }

    static func history(_ sessions: [Session],
                        now: Date,
                        calendar: Calendar = .current) -> [Day] {
        let parse = ISO8601DateFormatter()
        parse.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]

        func date(_ s: String) -> Date? { parse.date(from: s) ?? plain.date(from: s) }

        var buckets: [(key: Date, heading: String, rows: [Session])] = []
        for row in sessions.sorted(by: { $0.at > $1.at }) {
            guard let when = date(row.at) else { continue }
            let day = calendar.startOfDay(for: when)
            if let i = buckets.firstIndex(where: { $0.key == day }) {
                buckets[i].rows.append(row)
            } else {
                buckets.append((key: day, heading: heading(for: day, now: now, calendar: calendar), rows: [row]))
            }
        }
        return buckets.map { Day(heading: $0.heading, sessions: $0.rows) }
    }

    /// `now` IS THE REFERENCE, not the device clock, and that is the fix.
    /// This asked `calendar.isDateInToday(day)`, which compares against
    /// whatever day the machine is having — so the function took a `now`
    /// argument and then ignored it. In the app the two agree and nothing
    /// looked wrong; in a suite pinned to a fixed instant they disagree, and
    /// on a runner in another timezone they disagree by a whole day. A
    /// heading that cannot be tested without asking what time it is now is a
    /// heading nobody can hold to anything.
    static func heading(for day: Date, now: Date, calendar: Calendar = .current) -> String {
        let today = calendar.startOfDay(for: now)
        if calendar.isDate(day, inSameDayAs: today) { return "Today" }
        if let yesterday = calendar.date(byAdding: .day, value: -1, to: today),
           calendar.isDate(day, inSameDayAs: yesterday) { return "Yesterday" }
        let f = DateFormatter()
        // A day inside the last week is named; older than that needs its date.
        if let days = calendar.dateComponents([.day], from: day, to: now).day, days < 7 {
            f.dateFormat = "EEEE"
        } else {
            f.setLocalizedDateFormatFromTemplate("d MMMM")
        }
        return f.string(from: day)
    }

    // MARK: - What the empty screen says

    /// A dashboard with nothing in it is the screen most people see first, so
    /// it carries the invitation rather than an apology.
    static func emptyLine(listening: Bool, everListened: Bool) -> String {
        if listening { return "I'm listening. Say what's on your mind." }
        if everListened { return "Nothing needs you right now." }
        return "Turn on listening, or type below. I'll keep track of what needs doing."
    }
}
