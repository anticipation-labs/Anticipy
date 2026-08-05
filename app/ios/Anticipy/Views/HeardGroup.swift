import Foundation

// Pure Foundation on purpose. Every decision a conversation card makes about
// WHAT to say lives here, with no SwiftUI in sight, so it can be compiled and
// exercised without a simulator: sh app/ios/Tests/run_heard_tests.sh

// MARK: - Shared humanizing

/// Free-form model strings, softened into something a person would read.
enum Humanize {
    /// Goals arrive as machine shorthand ("research dinner spots in
    /// Vancouver"). Soften them into the thing itself.
    ///
    /// This is `FoundCard.headline`'s body promoted to one shared
    /// implementation so the goal on a conversation card and the goal on a
    /// found card cannot drift apart.
    ///
    /// Said plainly: the prefix list below IS a small fixed list. It already
    /// shipped, nothing has been added to it, it names no person, place or
    /// number from anyone's life, and it is cosmetic only — a goal that
    /// matches no prefix is returned in full.
    static func goal(_ raw: String) -> String {
        var s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !s.isEmpty else { return s }
        for prefix in ["research ", "Research ", "research: ", "Research: ",
                       "look up ", "Look up ", "find ", "Find "] {
            if s.hasPrefix(prefix) { s = String(s.dropFirst(prefix.count)); break }
        }
        return s.prefix(1).uppercased() + s.dropFirst()
    }
}

// MARK: - Weight

/// How much a conversation is asking of you. Never displayed as a number,
/// never summed, never shown as a badge — it only selects a register, and
/// every input to it is a decision the brain already made and this app already
/// renders line by line.
enum HeardWeight: Int, Comparable {
    case noted = 0      // every line was left alone, and no goal anywhere
    case looking = 1    // no act/ask, but she stamped a goal — quiet work
    case acting = 2     // some line decided "act"
    case asking = 3     // some line decided "ask" — she needs you
    static func < (a: Self, b: Self) -> Bool { a.rawValue < b.rawValue }
}

// MARK: - The group

/// One conversation, assembled on the phone out of lines the server already
/// sent. No new fetch and no new collection: the key is `events.segment`,
/// which the brain's segmenter stamps on every turn it places.
///
/// A line with no segment id is its own conversation of one — which renders as
/// the row this app already renders. A missing signal changes nothing.
struct HeardGroup: Identifiable, Equatable {
    let id: String                                  // "seg-<id>" or "solo-<line id>"
    let lines: [AnticipySession.TranscriptLine]     // speech order, oldest first

    /// Groups come back ordered by their NEWEST line, oldest conversation
    /// first — so the caller can reverse for a strict reverse-chronological
    /// feed, and a conversation still being spoken into floats to the top.
    static func build(_ lines: [AnticipySession.TranscriptLine]) -> [HeardGroup] {
        var byKey: [String: [AnticipySession.TranscriptLine]] = [:]
        var lastIndex: [String: Int] = [:]
        for (i, line) in lines.enumerated() {
            let seg = (line.segmentID ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            // An unstamped line keys off its own id, so it can never be merged
            // with another line by accident.
            let key = seg.isEmpty ? "solo-\(line.id)" : "seg-\(seg)"
            byKey[key, default: []].append(line)
            lastIndex[key] = i
        }
        return lastIndex.keys
            .sorted { (lastIndex[$0] ?? 0) < (lastIndex[$1] ?? 0) }
            .compactMap { key in
                guard let ls = byKey[key], !ls.isEmpty else { return nil }
                return HeardGroup(id: key, lines: ls)
            }
    }

    var weight: HeardWeight {
        if lines.contains(where: { $0.decision == "ask" }) { return .asking }
        if lines.contains(where: { $0.decision == "act" }) { return .acting }
        if lines.contains(where: { ($0.goal ?? "").isEmpty == false }) { return .looking }
        return .noted
    }

    /// Weight decides the register: a conversation that asked something of you
    /// is an object; a quiet one is a line on the ink.
    var isCarded: Bool { weight >= .acting }

    /// Lines she has not come back on yet. Independent of weight — a group can
    /// be `.acting` and still have a line in flight.
    var pending: [AnticipySession.TranscriptLine] { lines.filter { $0.decision == nil } }

    /// Rung 1 — what she understood this to be about. The first goal in speech
    /// order: the earliest thing she committed to is what the conversation was
    /// for. Nil when she never stamped one.
    var goalTitle: String? {
        for line in lines {
            let g = (line.goal ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if !g.isEmpty { return Humanize.goal(g) }
        }
        return nil
    }

    /// Rung 2 — she stamped no goal anywhere, so the card shows the words
    /// themselves, verbatim. She does not get to invent a summary she never
    /// made. Nil when every line in the group has empty text.
    var openingTextLine: AnticipySession.TranscriptLine? {
        lines.first { !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    }

    /// Rung 3 — the group has lines but every one of them has empty text
    /// (`BrainEvent.text` is Optional and maps to ""). Never blank, never a
    /// crash.
    static let lastResortTitle = "Something I heard"

    /// Everything the front of the card shows, decided in one place from the
    /// lines alone.
    var front: HeardFront {
        // Un-triaged speech renders on the FRONT exactly as this app renders
        // it today — "Thinking…"/"Sending…", the 90-second recovery, the act
        // celebration. Capped at two so a burst cannot rebuild the wall;
        // nothing is discarded, the rest is one tap away.
        let rows = Array(pending.suffix(2))
        let verb: HeardWeight? = (weight == .noted) ? nil : weight
        var title: String?
        var titleIsHers = true
        if let g = goalTitle {
            title = g
        } else if let opening = openingTextLine {
            if rows.contains(where: { $0.id == opening.id }) {
                // The words are already below as a LIVE row, with their status
                // and their recovery button. Printing them again above would
                // be a wall of two, and dropping the row instead would cost
                // this line the only signal that says she is still thinking.
                title = nil
            } else {
                title = opening.text
                titleIsHers = false
            }
        } else {
            title = Self.lastResortTitle
        }
        let showsHerOwn = (title != nil) || (verb != nil)
        return HeardFront(
            title: title,
            titleIsHers: titleIsHers,
            verb: verb,
            rows: rows,
            showsHerOwn: showsHerOwn,
            // Nothing is behind the tap, so there is nothing to tap: this card
            // is the raw row the app already draws, and stays as inert as one.
            isComplete: !showsHerOwn && rows.count == lines.count
        )
    }
}

/// What the front face renders. `title == nil` is not an error state — it means
/// the words are already on the front as a live row.
struct HeardFront: Equatable {
    let title: String?
    /// A goal title is HER interpretation and takes the serif; a rung-2 title
    /// is YOUR words and takes the voice register, so the two can never be
    /// mistaken for each other.
    let titleIsHers: Bool
    let verb: HeardWeight?
    let rows: [AnticipySession.TranscriptLine]
    /// Does this card show anything of her own — an understanding, a verdict?
    /// When it does not, it gets no stripe, no gutter and no affordance.
    let showsHerOwn: Bool
    let isComplete: Bool
}
