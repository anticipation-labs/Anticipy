import Foundation

/// WHAT ANTICIPY MAY TRUTHFULLY SAY ABOUT ITSELF.
///
/// Research: `research/2026-09-06-insights-retention.md`. Four readers
/// inventoried what this codebase can actually count, three designers proposed
/// metric sets, and three critics went at all of it. Three of the metrics
/// originally asked for did not survive, and the reasons are in that document.
///
/// ── THE RULE THIS FILE EXISTS TO ENFORCE ──────────────────────────────────
///
/// **Never print a zero. Name the empty set instead.** An absent line says "not
/// yet". A line reading 0 says "it doesn't work". Every metric here returns
/// `nil` rather than a zero, and the screen omits what is nil.
///
/// **A count over the newest page is never a lifetime.** This is the likeliest
/// way a screen like this ships a lie: `items.count` is whatever page the phone
/// happens to hold, and printing it as a total is false the moment somebody has
/// talked more than one page's worth. Everything here takes counts that came
/// from `totalItems` on a filtered count request, and `Counts` says so in its
/// own doc comment so nobody wires the wrong number in.
///
/// ── WHAT THIS FILE MAY NOT DO ─────────────────────────────────────────────
///
/// It may not read the WORDS. Law 1. "Things picked up" rests on `goal != ""`,
/// a column the brain wrote, and never on the client looking at text. The
/// runner greps this source for regex and substring matching and fails on it,
/// the same grep `run_dashboard_tests.sh` already carries — this is the second
/// file in the app that will be tempted to look at the words.
///
/// It may not manufacture anxiety. There is no streak here, and that is a
/// finding rather than an omission: the ears went deaf for thirty hours and
/// nothing noticed (`overnight/are_the_ears_live.py` exists because of it), so
/// a streak would break on Anticipy's own outage and bill it to the person.
/// Every number on this screen only goes up, or is a shape rather than a score.
enum InsightsPolicy {

    // MARK: - What the screen is given

    /// Counts that came from the SERVER'S OWN COUNT of a filtered set —
    /// `totalItems` on a `perPage=1` request — never from the length of a page
    /// the phone is holding. Nil means "not counted", which is different from
    /// zero in every case and is drawn differently.
    struct Counts: Equatable {
        /// Distinct local-calendar days on which this owner said something.
        /// Read off capture stamps the PHONE wrote, so it is the one figure
        /// that is true even while the brain is capped and judging nothing.
        var days: Int?
        /// Lines of speech, lifetime.
        var lines: Int?
        /// Lines the brain stamped a goal on. NOT `decision == "act"`: quiet
        /// work is recorded as ignore-with-a-goal, so counting `act` undercounts
        /// by design and would make her look idler than she was.
        var pickedUp: Int?
        /// Lines with no verdict at all yet. Mandatory companion to `pickedUp`:
        /// without it, an owner the brain has never served reads a confident
        /// zero for a day they talked through.
        var notYetJudged: Int?
        /// Errands that reached a terminal, successful end.
        var errandsFinished: Int?
        /// Times she stopped and asked before doing something. Monotone.
        var askedFirst: Int?
        /// Separate conversations.
        var conversations: Int?
        /// Where the words came from. Each nil when not counted.
        var heardByPhone: Int?
        var typedByYou: Int?
        var earNotRecorded: Int?

        static let nothing = Counts()
    }

    // MARK: - The cold start, as a closed set

    /// FOUR STATES, DELIBERATELY CLOSED.
    ///
    /// "Show whatever is non-empty" has no enumeration to test against; four
    /// cases can be walked exhaustively by a suite, the way `DashboardPolicy`'s
    /// modes are. That is the whole reason this is an enum.
    ///
    /// `heardNothingJudged` is where EVERY REAL OWNER LIVES TODAY. The brain is
    /// capped to one served owner, so everybody else's rows carry no verdict at
    /// all. It is simultaneously the genuinely new owner and the owner the fleet
    /// is not serving; the phone cannot tell them apart, and the honest sentence
    /// is the same for both. It is never "0 things caught".
    enum Stage: Equatable {
        case heardNothing
        case heardNothingJudged
        case judgedNothingFinished
        case steady
    }

    static func stage(_ c: Counts) -> Stage {
        let lines = c.lines ?? 0
        if lines == 0 { return .heardNothing }
        if (c.pickedUp ?? 0) == 0 { return .heardNothingJudged }
        if (c.errandsFinished ?? 0) == 0 { return .judgedNothingFinished }
        return .steady
    }

    // MARK: - The peek card on Home

    struct Peek: Equatable {
        let headline: String
        /// Nil when there is no honest second line, rather than a filler one.
        let detail: String?
    }

    /// The card that replaces the "Done" heading. Its headline is DAYS, and
    /// that is forced rather than chosen: every verdict-derived number renders
    /// as its cold-start apology on every real phone while the brain is capped,
    /// so a headline built on one would read "None judged yet" for everybody.
    /// Days reads timestamps the phone itself wrote.
    static func peek(_ c: Counts) -> Peek? {
        guard let days = c.days, days > 0 else { return nil }
        let headline = days == 1
            ? "You've talked to Anticipy on one day."
            : "You've talked to Anticipy on \(number(days)) days."

        // The catch ratio ALWAYS carries its denominator. "312 things caught"
        // alone invites a person to imagine the total; naming both is the
        // honest version and is also the more interesting sentence.
        if let picked = c.pickedUp, picked > 0, let lines = c.lines, lines > 0 {
            return Peek(headline: headline,
                        detail: "\(number(picked)) of \(number(lines)) lines turned into something.")
        }
        if let lines = c.lines, lines > 0 {
            return Peek(headline: headline,
                        detail: "\(number(lines)) lines heard so far.")
        }
        return Peek(headline: headline, detail: nil)
    }

    // MARK: - The page

    struct Row: Equatable, Identifiable {
        let id: String
        let value: String
        let label: String
        /// The sentence under a row that would otherwise overstate itself.
        let caveat: String?
    }

    /// Every row the page may show, in order, with the empty ones already
    /// dropped. Nothing here prints a zero.
    static func rows(_ c: Counts) -> [Row] {
        var out: [Row] = []

        if let days = c.days, days > 0 {
            out.append(Row(id: "days", value: number(days),
                           label: days == 1 ? "day you've talked to me" : "days you've talked to me",
                           caveat: nil))
        }
        if let lines = c.lines, lines > 0 {
            out.append(Row(id: "lines", value: number(lines),
                           label: lines == 1 ? "thing you've said that reached me"
                                             : "things you've said that reached me",
                           caveat: nil))
        }
        if let picked = c.pickedUp, picked > 0 {
            out.append(Row(id: "picked", value: number(picked),
                           label: "of them I picked up and did something about",
                           // Held-back questions land in the same bucket as
                           // genuine quiet work, so the sentence claims the
                           // weaker, true thing.
                           caveat: "Some of these I only looked into quietly."))
        }
        // The companion, and it is not optional. Without it, an owner nobody's
        // brain has served reads a confident silence about a day they talked
        // through.
        if let unjudged = c.notYetJudged, unjudged > 0 {
            out.append(Row(id: "unjudged", value: number(unjudged),
                           label: "I haven't reached a verdict on yet",
                           caveat: nil))
        }
        if let errands = c.errandsFinished, errands > 0 {
            out.append(Row(id: "errands", value: number(errands),
                           label: errands == 1 ? "errand finished" : "errands finished",
                           // Home files done, failed and cancelled under one
                           // heading because all three are terminal, so this
                           // number is smaller than the deck they scroll.
                           caveat: "Only the ones that worked. Home's Done also holds the ones that stopped."))
        }
        if let asked = c.askedFirst, asked > 0 {
            out.append(Row(id: "asked", value: number(asked),
                           label: asked == 1 ? "time I stopped and asked you first"
                                             : "times I stopped and asked you first",
                           caveat: nil))
        }
        if let conversations = c.conversations, conversations > 0 {
            out.append(Row(id: "conversations", value: number(conversations),
                           label: conversations == 1 ? "conversation" : "separate conversations",
                           caveat: nil))
        }
        return out
    }

    /// Where the words came from — this product's answer to "67% from desktop".
    ///
    /// A lane with nothing in it is OMITTED rather than drawn at zero. A pendant
    /// row reading 0% reads as a broken pendant; the pendant has simply never
    /// shipped, and saying nothing is the truthful drawing.
    struct Ear: Equatable, Identifiable {
        let id: String
        let label: String
        let count: Int
        let share: Int
    }

    static func ears(_ c: Counts) -> [Ear] {
        let lanes: [(String, String, Int?)] = [
            ("phone", "This phone's microphone", c.heardByPhone),
            ("typed", "Typed by you", c.typedByYou),
            ("unrecorded", "No record of which", c.earNotRecorded),
        ]
        var present: [(id: String, label: String, count: Int)] = []
        for lane in lanes {
            guard let n = lane.2, n > 0 else { continue }
            present.append((id: lane.0, label: lane.1, count: n))
        }
        let total = present.reduce(0) { $0 + $1.count }
        guard total > 0 else { return [] }
        var out: [Ear] = []
        for lane in present {
            let share = Int((Double(lane.count) / Double(total) * 100).rounded())
            out.append(Ear(id: lane.id, label: lane.label, count: lane.count, share: share))
        }
        return out.sorted { a, b in
            a.count == b.count ? a.id < b.id : a.count > b.count
        }
    }

    // MARK: - What the empty states say

    /// The one sentence a person sees when there is not enough to show. It
    /// never counts down to an unlock: nobody has measured where a real owner's
    /// first finished errand lands, so any number in that sentence would be a
    /// guess dressed as a milestone.
    static func emptyLine(_ stage: Stage) -> String {
        switch stage {
        case .heardNothing:
            return "Nothing yet. Turn on listening, or type something, and this fills in."
        case .heardNothingJudged:
            return "I've heard you, and I haven't reached a verdict on any of it yet. "
                 + "This page fills in once I have."
        case .judgedNothingFinished:
            return "I've picked things up, but nothing has come all the way back to you yet."
        case .steady:
            return ""
        }
    }

    /// Whether the page has anything worth opening at all.
    static func worthOpening(_ c: Counts) -> Bool { !rows(c).isEmpty }

    // MARK: - Numbers, written the way a person reads them

    /// Grouped with separators, and never abbreviated into "1.2k". An
    /// abbreviation is a rounding somebody cannot check, on a screen whose
    /// whole proposition is that its numbers are exact.
    static func number(_ n: Int) -> String {
        let f = NumberFormatter()
        f.numberStyle = .decimal
        f.groupingSeparator = ","
        f.usesGroupingSeparator = true
        return f.string(from: NSNumber(value: n)) ?? String(n)
    }
}
