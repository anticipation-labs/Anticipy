import Foundation

/// THE TWO LOOPS THAT ARE ALREADY OPEN, AND WHAT MAY BE DRAWN AROUND THEM.
///
/// Apple's activity rings drove a 49.5% behaviour change in 160,000 people on
/// one principle from Gestalt psychology: the brain treats an incomplete shape
/// as demanding completion. A 90% circle is an open loop, and an open loop
/// wants closing.
///
/// Anticipy already HAS loops like that and renders them as shrinking lists.
/// `InterviewProgress.answeredCount` is a count out of a known script. Connected
/// apps is a count out of the ones that matter. Both are rings nobody drew.
///
/// ── WHY THIS IS NOT A STREAK, AND WHY THAT DISTINCTION IS THE WHOLE FILE ──
///
/// A streak was considered for this product and rejected on evidence, not
/// taste: the ears went deaf for thirty hours and nothing noticed, so a streak
/// would have broken on Anticipy's own outage and billed it to the owner.
/// `run_insights_tests.sh` fails the build if the word appears on that screen.
///
/// Completion drive has none of that shape. Every ring here is MONOTONE — it
/// counts things the owner actually finished, so it cannot fall because a
/// server was down, a phone was off, or somebody had a bad week. There is
/// nothing to protect and nothing to lose, which is the entire difference
/// between a loop worth closing and a loop that has taken you hostage.
///
/// ── AND WHY NEITHER RING COUNTS ATTENTION ─────────────────────────────────
///
/// No ring here may be derived from app opens, session count, days elapsed, or
/// time spent. Those measure whether somebody showed up; these measure whether
/// something got done. A product that scores its owner for opening it has
/// started working on them rather than for them, and `run_rings_tests.sh`
/// refuses the vocabulary outright.
enum RingsPolicy {

    /// Which loop. Two, and adding a third is a decision about what this
    /// product thinks progress IS — so it belongs in this header first.
    enum Ring: String, CaseIterable, Equatable {
        /// How much of the interview she has been told. Closes when the script
        /// is answered.
        case whatSheKnows
        /// How many of the apps that matter are actually reachable. Closes when
        /// the owner has connected the ones their own goals need.
        case whatSheCanReach
    }

    /// A drawn ring. `done` and `total` rather than a fraction, because the
    /// numbers are the honest part and a percentage hides how small the whole
    /// thing is — "2 of 3" and "67%" are the same ratio and not the same fact.
    struct Face: Equatable {
        let ring: Ring
        let done: Int
        let total: Int
        /// The name of the loop, in the product's own voice.
        let title: String
        /// What closing it would get them. Never a reward — a consequence.
        let because: String
        /// 0…1, for the arc. Clamped, so a server that reports 5 of 3 draws a
        /// closed ring rather than one and two-thirds of a circle.
        var fraction: Double {
            guard total > 0 else { return 0 }
            return min(1, max(0, Double(done) / Double(total)))
        }
        var closed: Bool { total > 0 && done >= total }
    }

    /// Why a ring is not drawn. Absent, never empty: a ring at zero out of zero
    /// is a shape that means nothing, and an empty ring on a new owner's screen
    /// is the product opening with a scolding.
    enum Hidden: Equatable {
        /// Nothing is known about this loop yet.
        case nothingToCount
        /// The loop is closed AND has been for a while. A permanently full ring
        /// is decoration; it stops being information the moment it can no
        /// longer change.
        case longSinceClosed
    }

    enum Decision: Equatable {
        case draw(Face)
        case hide(Hidden)
    }

    /// How long a closed ring stays on screen before it stops being news.
    /// Closing it is worth seeing; a full circle three weeks later is furniture.
    static let closedRingLingersForDays = 3

    /// `answered` out of `inScript`; `connected` out of `worthConnecting`.
    ///
    /// Every argument is a COUNT the caller already holds. Nothing here reads a
    /// clock except `daysSinceClosed`, and nothing reads a word at all.
    static func decide(_ ring: Ring,
                       done: Int,
                       total: Int,
                       daysSinceClosed: Int?) -> Decision {
        let done = max(0, done), total = max(0, total)
        guard total > 0 else { return .hide(.nothingToCount) }
        if done >= total, let since = daysSinceClosed, since > closedRingLingersForDays {
            return .hide(.longSinceClosed)
        }
        return .draw(face(ring, done: done, total: total))
    }

    static func face(_ ring: Ring, done: Int, total: Int) -> Face {
        switch ring {
        case .whatSheKnows:
            return Face(ring: ring, done: done, total: total,
                        title: "What she knows about you",
                        // Not "unlock" and not "improve your score". The
                        // consequence is real and specific: the interview is
                        // what lets her act without asking first.
                        because: done >= total
                            ? "She has what she needs to act without asking first."
                            : "Each answer is one thing she stops having to ask.")
        case .whatSheCanReach:
            return Face(ring: ring, done: done, total: total,
                        title: "What she can reach",
                        because: done >= total
                            ? "Everything your goals need is connected."
                            : "An app she cannot reach is an errand she cannot run.")
        }
    }

    /// The rings worth showing, in order. Both hidden means the section is
    /// absent entirely — the caller must not render a heading over nothing.
    /// `reaches` is OPTIONAL, and that is a real state rather than a gap.
    ///
    /// The connected-apps count lives on `ConnectedAppsModel`, which Home does
    /// not hold — and a screen that cannot see a number must not invent a
    /// denominator for it. Passing nil hides that ring exactly the way an
    /// unstarted one is hidden, so the page degrades to the loop it can
    /// actually count instead of drawing a lie next to a truth.
    ///
    /// This is deliberately not solved by guessing a total from the catalog:
    /// "the apps that matter for your goals" is a judgment, and a judgment
    /// belongs to the model that has the goals, never to a ring.
    static func rings(knows: (done: Int, total: Int, closedDays: Int?),
                      reaches: (done: Int, total: Int, closedDays: Int?)?) -> [Face] {
        var out: [Decision] = [decide(.whatSheKnows, done: knows.done, total: knows.total,
                                      daysSinceClosed: knows.closedDays)]
        if let reaches {
            out.append(decide(.whatSheCanReach, done: reaches.done, total: reaches.total,
                              daysSinceClosed: reaches.closedDays))
        }
        return out.compactMap { if case .draw(let f) = $0 { return f } else { return nil } }
    }

    /// What Developer Diagnostics prints.
    static func words(_ decision: Decision) -> String {
        switch decision {
        case .draw(let f):  return "\(f.done) of \(f.total)"
        case .hide(let why):
            switch why {
            case .nothingToCount:  return "nothing to count yet"
            case .longSinceClosed: return "closed a while ago"
            }
        }
    }
}
