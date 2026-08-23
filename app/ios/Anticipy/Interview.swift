import Foundation

/// The five human questions, plus the one no scrape can answer.
///
/// `design/PRODUCTION-ROADMAP.md:167-171` and `design/briefs/08-day-zero.md:5-10`
/// specify this and it has never been built: the shipped flow is five steps
/// (welcome, howItWorks, mic, phone, browser) and none of them ask anything
/// about the person's life.
///
/// It is a CONVERSATION, NOT A SURVEY (`briefs/08-day-zero.md:29`). That has
/// three consequences in the code below:
///
///   - one question on screen at a time, never a scrollable form;
///   - her question is her voice, so it is typed out — the typewriter is banned
///     on permission copy, not on the things she actually says;
///   - a skip records NOTHING (`:30`). Never an empty fact, never a "declined"
///     fact. The absence of an answer is not information about somebody.
///
/// The sixth question is the one the owner asked for out loud and the one no
/// amount of reading their mail could answer: which tools they actually live
/// in. A scrape can see where somebody has an account; only they can say what
/// they open every morning.
struct InterviewQuestion: Identifiable, Equatable {
    let id: String
    /// What she asks. One question, in her voice.
    let asks: String
    /// The quiet line under it, saying why she wants it. Never a disclaimer.
    let why: String
    /// What a person might type, so the field is never a blank stare.
    let hint: String
    /// How the answer is turned into a fact. The subject is always "they", to
    /// match `seed_profile_identity`'s existing wording ("Their name is X.") so
    /// recall reads consistently.
    let fact: (String) -> String
    /// 5 is identity — the things that change how she treats everything else.
    /// 4 is context. `brain/memory.py` ranks recall on importance.
    let importance: Int

    static func == (a: InterviewQuestion, b: InterviewQuestion) -> Bool { a.id == b.id }

    static let script: [InterviewQuestion] = [
        InterviewQuestion(
            id: "people",
            asks: "Who matters most to you?",
            why: "So when you say a name, I know who you mean.",
            hint: "Priya, my sister Dana, Marcus at work",
            fact: { "The people who matter most to them: \($0)." },
            importance: 5),
        InterviewQuestion(
            id: "work",
            asks: "What do you do?",
            why: "It tells me what most of your day is probably about.",
            hint: "I run product at a design studio",
            fact: { "What they do: \($0)." },
            importance: 5),
        InterviewQuestion(
            id: "tools",
            // The owner's own question, and the one a scrape genuinely cannot
            // answer: an inbox shows where you have an account, not what you
            // open every morning.
            asks: "What do you actually live in all day?",
            why: "The apps and sites you'd want me to know my way around.",
            hint: "Gmail, Notion, Linear, Instacart",
            fact: { "The tools they use day to day: \($0)." },
            importance: 4),
        InterviewQuestion(
            id: "offlimits",
            asks: "What should I never touch?",
            why: "I'll treat it as a wall, not a preference.",
            hint: "anything to do with my bank, work email after 7",
            fact: { "They asked me never to touch: \($0)." },
            // Highest, deliberately: a boundary must outrank everything it is
            // a boundary on, because recall is ranked and this is the one fact
            // that must never be the one that fell off the end.
            importance: 5),
        InterviewQuestion(
            id: "reach",
            asks: "How do you like to be reached?",
            why: "When something needs your word, I'll use this.",
            hint: "text me, but not before 9am",
            fact: { "How they like to be reached: \($0)." },
            importance: 4),
        InterviewQuestion(
            id: "coming",
            asks: "Anything big coming up this month?",
            why: "So I'm not surprised by it, and neither are you.",
            hint: "moving flat on the 20th, Dana's wedding",
            fact: { "Coming up for them this month: \($0)." },
            importance: 4),
    ]
}

/// Which questions have been answered, so she never asks twice.
///
/// Answers themselves are NOT stored here — they go to memory and memory is the
/// single home for what she knows. Keeping a second copy on the phone would be
/// the split-brain `design/day-zero.md` §3 already warns about.
struct InterviewProgress {
    static let key = "interview.answered"
    private let defaults: UserDefaults
    init(defaults: UserDefaults = .standard) { self.defaults = defaults }

    private var answered: Set<String> {
        Set(defaults.stringArray(forKey: Self.key) ?? [])
    }

    func isAnswered(_ id: String) -> Bool { answered.contains(id) }

    func markAnswered(_ id: String) {
        defaults.set(Array(answered.union([id])), forKey: Self.key)
    }

    /// A skip records nothing at all — not the question, not a blank. So a
    /// skipped question is simply still open, and she may raise it again the
    /// next time the person opens the interview themselves.
    var remaining: [InterviewQuestion] {
        InterviewQuestion.script.filter { !isAnswered($0.id) }
    }

    var answeredCount: Int { InterviewQuestion.script.count - remaining.count }

    var isComplete: Bool { remaining.isEmpty }

    /// Put every question back on the table.
    ///
    /// Only for an explicit "go over them again": the answers themselves live in
    /// memory, not here, and `remember_fact` merges restatements — so somebody
    /// correcting "what do you do" replaces the fact rather than leaving her
    /// believing both.
    func reopenAll() {
        defaults.removeObject(forKey: Self.key)
    }
}
