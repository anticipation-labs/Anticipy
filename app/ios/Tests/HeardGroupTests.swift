import Foundation

// Checks for HeardGroup — the layer that turns a wall of heard lines into
// conversations. Deliberately NOT an XCTest bundle: HeardGroup.swift is pure
// Foundation, so the REAL source file compiles and runs here in about a second
// with no simulator, no scheme and no signing. There is no second copy of the
// logic to drift. See app/ios/Tests/run_heard_tests.sh.
//
// The app's TranscriptLine lives inside a @MainActor class that drags in
// SwiftUI, Combine, the network layer and the microphone. This is the same
// shape, and the runner diffs it field for field against the real declaration
// before compiling anything.

enum AnticipySession {
    struct TranscriptLine: Identifiable, Equatable {
        let id: String
        let text: String
        let decision: String?
        var goal: String? = nil
        /// Who said it. Mirrored from the real type so the two cannot drift —
        /// the gate compares them field for field.
        var speaker: String? = nil
        var segmentID: String? = nil
        var created: String = ""
        var source: String? = nil
    }
}

// ---------------------------------------------------------------- harness

var checks = 0
var failures: [String] = []

func section(_ name: String) { print("\n\(name)") }

func check(_ name: String, _ ok: Bool) {
    checks += 1
    if ok {
        print("  ok    \(name)")
    } else {
        failures.append(name)
        print("  FAIL  \(name)")
    }
}

func eq<T: Equatable>(_ name: String, _ got: T, _ want: T) {
    checks += 1
    if got == want {
        print("  ok    \(name)")
    } else {
        failures.append(name)
        print("  FAIL  \(name)\n          got:  \(got)\n          want: \(want)")
    }
}

typealias L = AnticipySession.TranscriptLine

func line(_ id: String, _ text: String, decision: String? = nil,
          goal: String? = nil, segment: String? = nil, created: String = "",
          source: String? = nil) -> L {
    L(id: id, text: text, decision: decision, goal: goal,
      segmentID: segment, created: created, source: source)
}

// ---------------------------------------------------------------- cases

enum Cases {

    // MARK: grouping

    /// The whole point: one spoken call is one card.
    static func oneCallOneCard() {
        section("A single stamped conversation")
        let call = (1...12).map { line("e\($0)", "line \($0)", decision: "ignore", segment: "segA") }
        let groups = HeardGroup.build(call)
        eq("twelve lines collapse to one group", groups.count, 1)
        eq("the group keeps every line", groups[0].lines.count, 12)
        eq("group id is derived from the segment", groups[0].id, "seg-segA")
        eq("speech order is preserved (start)", groups[0].lines.first?.id, "e1")
        eq("speech order is preserved (end)", groups[0].lines.last?.id, "e12")
    }

    /// THE DEGRADATION CASE. No segmenter, no segment ids: every line is its
    /// own conversation, i.e. today's feed, line for line, in the same order.
    static func noSegmentsIsToday() {
        section("No segment ids at all — the missing-signal case")
        let raw = (1...12).map { line("e\($0)", "line \($0)", decision: "ignore") }
        let groups = HeardGroup.build(raw)
        eq("one group per line", groups.count, 12)
        eq("order is untouched", groups.map { $0.lines[0].id }, raw.map(\.id))
        check("every group holds exactly one line", groups.allSatisfy { $0.lines.count == 1 })
        check("no group is promoted to a container", groups.allSatisfy { !$0.isCarded })
        check("every stripe is the .noted stripe", groups.allSatisfy { $0.weight == .noted })
    }

    /// An empty-string segment is PocketBase's "unset", not a segment named "".
    static func blankSegmentsNeverMerge() {
        section("Blank segment ids")
        let groups = HeardGroup.build([
            line("a", "one", decision: "ignore", segment: ""),
            line("b", "two", decision: "ignore", segment: "   "),
            line("c", "three", decision: "ignore", segment: nil),
        ])
        eq("empty, whitespace and nil all stay separate", groups.count, 3)
    }

    static func mixedAndInterleaved() {
        section("Stamped and unstamped lines side by side")
        let groups = HeardGroup.build([
            line("a", "one", decision: "ignore", segment: "S"),
            line("b", "loose", decision: "ignore"),
            line("c", "two", decision: "ignore", segment: "S"),
        ])
        eq("two groups", groups.count, 2)
        // "S" was last seen at index 2 and the loose line at index 1, so the
        // conversation still being spoken into sorts last (= newest).
        eq("ordered by newest line", groups.map(\.id), ["solo-b", "seg-S"])
        eq("interleaved lines still gather", groups[1].lines.map(\.id), ["a", "c"])
    }

    static func empty() {
        section("Nothing heard")
        eq("empty in, empty out", HeardGroup.build([]).count, 0)
    }

    // MARK: weight

    static func weight() {
        section("Weight, derived only from decisions she already made")
        func w(_ ls: [L]) -> HeardWeight { HeardGroup(id: "x", lines: ls).weight }
        eq("all ignored, no goal => noted",
           w([line("a", "t", decision: "ignore"), line("b", "t", decision: "ignore")]), .noted)
        eq("a goal with no act/ask => looking",
           w([line("a", "t", decision: "ignore", goal: "book a table")]), .looking)
        eq("an empty-string goal is not a goal",
           w([line("a", "t", decision: "ignore", goal: "")]), .noted)
        eq("any act => acting",
           w([line("a", "t", decision: "ignore"), line("b", "t", decision: "act")]), .acting)
        eq("ask outranks act",
           w([line("a", "t", decision: "act"), line("b", "t", decision: "ask")]), .asking)
        eq("undecided lines alone => noted", w([line("a", "t")]), .noted)
        check("only act/ask earn a container",
              HeardGroup(id: "x", lines: [line("a", "t", decision: "act")]).isCarded)
        check("a quiet goal does not earn a container",
              !HeardGroup(id: "x", lines: [line("a", "t", decision: "ignore", goal: "g")]).isCarded)
    }

    // MARK: the title, rung by rung

    static func rung1Goal() {
        section("Rung 1 — her goal")
        let g = HeardGroup(id: "x", lines: [
            line("a", "spoken words", decision: "ignore"),
            line("b", "more words", decision: "ignore", goal: "research dinner spots"),
        ])
        eq("goal wins the title", g.front.title, "Dinner spots")
        check("a goal title is hers, so it takes the serif", g.front.titleIsHers)
        eq("first goal in speech order wins",
           HeardGroup(id: "x", lines: [
            line("a", "t", decision: "ignore", goal: "first thing"),
            line("b", "t", decision: "ignore", goal: "second thing"),
           ]).front.title, "First thing")

        let corrected = HeardGroup(id: "x", lines: [
            line("a", "book downtown", decision: "act", goal: "book dinner downtown"),
            line("b", "actually Burnaby", decision: "act", goal: "book dinner in Burnaby"),
        ])
        eq("recap uses the latest corrected goal",
           corrected.latestGoalTitle, "Book dinner in Burnaby")
        eq("the conversation card title remains stable",
           corrected.goalTitle, "Book dinner downtown")
    }

    static func rung2OpeningLine() {
        section("Rung 2 — no goal anywhere, so your words, verbatim")
        let call = [line("a", "the opening thing that was said", decision: "ignore")]
            + (2...12).map { line("e\($0)", "line \($0)", decision: "ignore") }
        let g = HeardGroup(id: "x", lines: call)
        eq("falls back to the opening line, verbatim",
           g.front.title, "the opening thing that was said")
        check("your words are NOT hers, so they take the voice register", !g.front.titleIsHers)
        eq("she has nothing of her own to add", g.front.verb, nil)
        eq("no live rows on the front", g.front.rows.count, 0)
        check("the other eleven lines are behind the tap", !g.front.isComplete)
        check("she has something of her own on the front", g.front.showsHerOwn)
    }

    static func rung2SkipsBlanks() {
        section("Rung 2 — blank lines are skipped")
        let g = HeardGroup(id: "x", lines: [
            line("a", "", decision: "ignore"),
            line("b", "   ", decision: "ignore"),
            line("c", "the actual words", decision: "ignore"),
        ])
        eq("first line with real text wins", g.front.title, "the actual words")
    }

    static func rung3LastResort() {
        section("Rung 3 — every line is empty text")
        let g = HeardGroup(id: "x", lines: [
            line("a", "", decision: "ignore"),
            line("b", "  ", decision: "ignore"),
        ])
        eq("last resort title", g.front.title, HeardGroup.lastResortTitle)
        check("the last resort is hers, so it takes the serif", g.front.titleIsHers)
        check("a title always exists", (g.front.title ?? "").isEmpty == false)

        let withGoal = HeardGroup(id: "x", lines: [
            line("a", "", decision: "ignore", goal: "chase the invoice"),
        ])
        eq("a goal still beats the last resort", withGoal.front.title, "Chase the invoice")
    }

    // MARK: never lose speech / degrade to today

    /// THE HONESTY WALL. A single just-spoken line she has said nothing about
    /// yet renders as the raw row and nothing else — no synthesized title above
    /// it, no affordance, no flip. Exactly today's app.
    static func freshSpeechIsUntouched() {
        section("A line she has not come back on yet")
        let g = HeardGroup(id: "x", lines: [line("a", "I'll send that tonight")])
        eq("no title is synthesized over a live row", g.front.title, nil)
        eq("the words render as the live row", g.front.rows.map(\.id), ["a"])
        eq("no verb row", g.front.verb, nil)
        check("nothing of her own on the front, so no affordance", !g.front.showsHerOwn)
        check("nothing hidden => not flippable", g.front.isComplete)

        let two = HeardGroup(id: "x", lines: [
            line("a", "one", segment: "S"), line("b", "two", segment: "S"),
        ])
        eq("two pending lines both show", two.front.rows.map(\.id), ["a", "b"])
        eq("still no invented title", two.front.title, nil)
        check("still exactly today", two.front.isComplete)
    }

    /// The cap engages, and the moment anything is hidden the card admits it.
    static func burstIsCappedButNotDiscarded() {
        section("A burst of un-triaged speech")
        let g = HeardGroup(id: "x", lines: [
            line("a", "one", segment: "S"), line("b", "two", segment: "S"),
            line("c", "three", segment: "S"),
        ])
        eq("front is capped at the two newest live rows", g.front.rows.map(\.id), ["b", "c"])
        check("the hidden one is admitted to and reachable", !g.front.isComplete)
        eq("no line was dropped from the record", g.lines.count, 3)
    }

    /// Nothing is ever printed twice, and no pending line ever loses the status
    /// row that says she is still thinking about it.
    static func noDuplicationEitherWay() {
        section("A decided line and a pending line together")
        let decidedFirst = HeardGroup(id: "x", lines: [
            line("a", "settled words", decision: "ignore", segment: "S"),
            line("b", "brand new words", segment: "S"),
        ])
        eq("title is the opening line", decidedFirst.front.title, "settled words")
        eq("the pending line keeps its live row", decidedFirst.front.rows.map(\.id), ["b"])
        check("the title is not also a row",
              !decidedFirst.front.rows.contains { $0.text == decidedFirst.front.title })

        // Reverse order: the pending line would have been the title. It stays a
        // live row instead — the title is dropped rather than duplicating the
        // words or silencing their status.
        let pendingFirst = HeardGroup(id: "x", lines: [
            line("a", "brand new words", segment: "S"),
            line("b", "settled words", decision: "ignore", segment: "S"),
        ])
        eq("no duplicate title", pendingFirst.front.title, nil)
        eq("the live row survives", pendingFirst.front.rows.map(\.id), ["a"])
        check("a verdict is hidden, so it flips", !pendingFirst.front.isComplete)
    }

    /// Whatever a group is made of, it keeps every line, and it is never blank.
    static func nothingIsEverLost() {
        section("Nothing is lost and nothing is blank")
        let all: [L] = [
            line("a", "x", decision: "act", segment: "S"),
            line("b", "", decision: "ignore", segment: "S"),
            line("c", "y", goal: "g", segment: "S"),
            line("d", "z", decision: "ask"),
            line("e", "", decision: nil),
        ]
        let groups = HeardGroup.build(all)
        eq("no line is lost by grouping",
           groups.flatMap { $0.lines }.map(\.id).sorted(), all.map(\.id).sorted())
        check("no group is ever empty", groups.allSatisfy { !$0.lines.isEmpty })
        check("no card is ever blank",
              groups.allSatisfy { g in
                  g.front.title == nil
                      ? !g.front.rows.isEmpty
                      : !(g.front.title ?? "").isEmpty
              })
    }

    // MARK: Humanize

    static func humanize() {
        section("Humanize.goal")
        eq("prefix stripped and sentence-cased", Humanize.goal("research dinner spots"), "Dinner spots")
        eq("capitalised prefix too", Humanize.goal("Look up the ferry times"), "The ferry times")
        eq("colon form", Humanize.goal("Research: the ferry times"), "The ferry times")
        eq("no match is returned in full",
           Humanize.goal("call the plumber back"), "Call the plumber back")
        eq("only the first prefix is stripped",
           Humanize.goal("find find the thing"), "Find the thing")
        eq("empty stays empty", Humanize.goal(""), "")
        eq("whitespace only stays empty", Humanize.goal("   "), "")
        // The trim runs BEFORE the match, and every prefix carries its own
        // trailing space — so a goal that is nothing but a prefix word can
        // never match, and survives whole instead of leaving a blank card.
        eq("a goal that is only a prefix word survives", Humanize.goal("research "), "Research")
        check("no input makes a non-empty goal come back empty",
              ["research ", "find", "Look up", "  Research:  ", "x"]
                  .allSatisfy { !Humanize.goal($0).isEmpty })
        eq("unicode is not mangled", Humanize.goal("émigré paperwork"), "Émigré paperwork")
    }

    // MARK: which ear

    /// Comparing a pendant run of an errand against a phone-mic run of the same
    /// errand is the reason `events.source` exists. The card front is where that
    /// comparison actually happens — a glance down the feed.
    static func whichEar() {
        section("HeardGroup.ear")

        func ear(_ sources: [String?]) -> String? {
            HeardGroup(id: "g", lines: sources.enumerated().map {
                line("e\($0.offset)", "said something", segment: "segA", source: $0.element)
            }).ear
        }

        eq("a whole conversation off the phone reads phone_mic",
           ear(["phone_mic", "phone_mic", "phone_mic"]), "phone_mic")
        eq("a whole conversation off the pendant reads pendant",
           ear(["pendant", "pendant"]), "pendant")

        // THE ONE THAT MATTERS. Half off each ear must claim NEITHER: a card
        // labelled "Pendant" whose speech was half phone-mic corrupts the exact
        // comparison this field exists for, silently, in the direction of
        // whichever line happened to come first.
        check("a MIXED conversation claims no ear at all",
              ear(["pendant", "phone_mic"]) == nil && ear(["phone_mic", "pendant"]) == nil)

        check("an unstamped conversation claims no ear", ear([nil, nil]) == nil)
        check("an empty group claims no ear", HeardGroup(id: "g", lines: []).ear == nil)
        check("typed alone claims no ear", ear(["typed", "typed"]) == nil)
        check("blank and whitespace sources claim no ear", ear(["", "   "]) == nil)

        // Sources that earn no badge must not be able to make a real ear
        // ambiguous — otherwise typing one reply into a pendant conversation
        // would erase its provenance.
        eq("typed lines do not make a pendant conversation mixed",
           ear(["pendant", "typed", "pendant"]), "pendant")
        eq("unstamped lines do not make a phone conversation mixed",
           ear([nil, "phone_mic", nil]), "phone_mic")
        eq("padding is tolerated", ear([" pendant ", "pendant"]), "pendant")

        // And the front must actually carry it, or none of the above is visible.
        let front = HeardGroup(id: "g", lines: [
            line("e1", "check the happy hour times", decision: "act",
                 goal: "Check happy hour times", segment: "segA", source: "pendant"),
        ]).front
        eq("the card front carries the ear", front.ear, "pendant")
    }
}

@main
enum Main {
    static func main() {
        Cases.oneCallOneCard()
        Cases.noSegmentsIsToday()
        Cases.blankSegmentsNeverMerge()
        Cases.mixedAndInterleaved()
        Cases.empty()
        Cases.weight()
        Cases.rung1Goal()
        Cases.rung2OpeningLine()
        Cases.rung2SkipsBlanks()
        Cases.rung3LastResort()
        Cases.freshSpeechIsUntouched()
        Cases.burstIsCappedButNotDiscarded()
        Cases.noDuplicationEitherWay()
        Cases.nothingIsEverLost()
        Cases.humanize()
        Cases.whichEar()

        print("\n\(checks - failures.count)/\(checks) checks passed")
        if !failures.isEmpty {
            print("\(failures.count) FAILED")
            exit(1)
        }
        print("HeardGroup: all green")
        exit(0)
    }
}
