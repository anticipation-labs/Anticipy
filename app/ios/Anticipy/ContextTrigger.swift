import Foundation

/// WHEN she is allowed to ask for a connection, decided by a rule rather than
/// by a model.
///
/// `CLAUDE-ONBOARDING.md:16-17` — "that gate lives in deterministic code, never
/// in the model" — and `design/briefs/04-three-lane-delivery.md:16-19` is the
/// precedent for the shape: "The model may propose; the rule decides."
///
/// This exists so a just-in-time ask can never become nagging. It fires on
/// something the person actually said, once per source, and it does not fire on
/// a keyword sitting alone: "Thursday" in isolation is not a reason to want a
/// calendar, but "dinner Thursday" is.
enum ContextTrigger {

    /// Single words that mean a moment in time.
    ///
    /// "am" and "pm" are DELIBERATELY ABSENT. They were here, and they made
    /// "I am busy" a calendar request — `busy` is a plan word and `am` was a
    /// time word, so an ordinary sentence burned the one ask this source ever
    /// gets. A clock time is detected on the original string instead, where a
    /// digit has to sit next to it (see `hasClockTime`).
    private static let timeWords: Set<String> = [
        "today", "tonight", "tomorrow", "monday", "tuesday", "wednesday",
        "thursday", "friday", "saturday", "sunday", "weekend", "morning",
        "afternoon", "evening", "o'clock",
    ]

    /// Multi-word phrases, which the word split above can never match. They
    /// used to sit in `timeWords` where they were simply dead, and the
    /// substring fallback that reached them also matched "am" inside "family",
    /// "amazing", "Sam" and "campaign".
    private static let timePhrases = ["next week", "this week", "next month"]

    /// A real clock time: a digit adjacent to am/pm, or HH:MM.
    private static func hasClockTime(_ lower: String) -> Bool {
        if lower.range(of: #"\d\s?[ap]\.?m\b"#, options: .regularExpression) != nil { return true }
        return lower.range(of: #"\b\d{1,2}:\d{2}\b"#, options: .regularExpression) != nil
    }

    /// Words that mean something is being COMMITTED to, not merely mentioned.
    /// A calendar is worth asking for when there is a plan, not when a day of
    /// the week goes past in conversation.
    private static let planWords: Set<String> = [
        "dinner", "lunch", "breakfast", "coffee", "drinks", "meeting", "call",
        "appointment", "flight", "train", "booking", "reservation", "birthday",
        "party", "interview", "deadline", "due", "free", "busy", "available",
        "schedule", "reschedule", "book",
    ]

    /// Which source — if any — this sentence justifies asking for, and the word
    /// from the sentence that justifies it.
    ///
    /// The subject is returned rather than discarded because the ask is
    /// required to name the specific thing (`CLAUDE-ONBOARDING.md:19-20`, voice
    /// law at `:28-29`). An earlier version computed the name and threw it
    /// away, which left the contacts ask in exactly the generic form that law
    /// bans.
    ///
    /// `knownNames` is what she has already been told; a name she recognises is
    /// not a reason to open the address book. Passing it in rather than reading
    /// memory keeps this function pure and therefore testable.
    static func ask(for line: String,
                    knownNames: Set<String> = [],
                    grants: ContextGrants = ContextGrants()) -> (source: ContextSource, subject: String?)? {
        let lower = line.lowercased()
        let words = Set(lower.split(whereSeparator: { !$0.isLetter && $0 != "'" }).map(String.init))

        // Calendar: a plan AND a time. Both, deliberately — a day of the week
        // on its own is conversation, not a commitment.
        let saysWhen = !words.isDisjoint(with: timeWords)
            || timePhrases.contains(where: { lower.contains($0) })
            || hasClockTime(lower)
        if grants.mayAsk(.calendar), !words.isDisjoint(with: planWords), saysWhen {
            return (.calendar, nil)
        }

        // Contacts: a capitalised name she has never been told. Checked on the
        // ORIGINAL casing, because that is the only signal that a word is a
        // person rather than a noun.
        if grants.mayAsk(.contacts), let who = unknownName(in: line, knownNames: knownNames) {
            return (.contacts, who)
        }
        return nil
    }

    /// Convenience for callers that only need to know whether to ask.
    static func source(for line: String,
                       knownNames: Set<String> = [],
                       grants: ContextGrants = ContextGrants()) -> ContextSource? {
        ask(for: line, knownNames: knownNames, grants: grants)?.source
    }

    /// The first capitalised word that looks like somebody's name and is not
    /// already known. Sentence-initial words are skipped — every sentence
    /// starts capitalised, so the first word carries no signal.
    static func unknownName(in line: String, knownNames: Set<String>) -> String? {
        let known = Set(knownNames.map { $0.lowercased() })
        let tokens = line.split(whereSeparator: { !$0.isLetter && $0 != "'" }).map(String.init)
        for (index, token) in tokens.enumerated() where index > 0 {
            guard token.count > 2,
                  let first = token.first, first.isUppercase,
                  token.dropFirst().allSatisfy({ $0.isLowercase })
            else { continue }
            let lower = token.lowercased()
            if known.contains(lower) { continue }
            // Days and months are capitalised too, and they are not people.
            if timeWords.contains(lower) || monthWords.contains(lower) { continue }
            return token
        }
        return nil
    }

    private static let monthWords: Set<String> = [
        "january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december",
    ]
}
