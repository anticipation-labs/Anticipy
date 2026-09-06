import Foundation

/// HOW AN ERRAND COMING BACK DONE IS ALLOWED TO ARRIVE.
///
/// This is the single most valuable moment the product produces: Anticipy went
/// and did something in the world and came back with proof the SERVER refused
/// to accept without. Until 2026-09-06 it was delivered by one line —
///
///     if !seenDoneJobIDs.isEmpty, !doneIDs.subtracting(seenDoneJobIDs).isEmpty {
///         Haptics.success()
///     }
///
/// — a haptic tap, and a card that silently appeared in a deck. The evidence
/// was already there and was handed over like a bank statement.
///
/// ── CEREMONY IS NOT APPLAUSE, AND THAT DISTINCTION IS THE WHOLE DESIGN ────
///
/// `run_insights_tests.sh` fails this build if anything congratulates, wears a
/// badge, or counts a number up from zero, because "a number rolling up from
/// zero is a small casino". **That rule stays exactly as written and this file
/// is compatible with it by construction**: nothing here produces a word.
/// It produces TIMINGS. The ceremony is a pulse while work is running, a
/// stagger over evidence lines the receipt already contains, and a pause before
/// the card joins the deck. There is no confetti, no modal, no share sheet, and
/// no sentence that was not already going to be shown.
///
/// The thing being ceremonial about is the PROOF. That is the opposite of a
/// casino, which is ceremonial about nothing.
///
/// ── THE FACT OUTRANKS THE THEATRE ────────────────────────────────────────
///
/// A person waiting to learn whether their errand ran may never be made to wait
/// on an animation. `maximumDelay` is a hard budget and the plan COMPRESSES to
/// fit it — a nine-line receipt gets a faster stagger, never a longer ceremony.
/// `run_done_ceremony_tests.sh` walks every receipt size from 0 to the
/// server's hard cap of 12 and fails if any plan overruns.
enum DoneCeremonyPolicy {

    /// Which of `DoneCard`'s three branches this is. The card has three
    /// mutually exclusive arms and only one of them is a completion:
    /// `succeeded` (status `done`), `calledOff` (status `cancelled`), and a
    /// failed arm. A cancellation is not a failure and neither is a success.
    ///
    /// **The ceremony reaches exactly one of these.** A failed errand arriving
    /// with a reveal sequence would be the product performing delight over bad
    /// news, and `job.safetyLine` — "it may already have gone out" — is the
    /// most time-critical sentence in the app.
    enum Outcome: Equatable {
        case succeeded
        case calledOff
        case failed
    }

    /// Why there is no ceremony. A reason, not a bare `false`.
    enum Skip: Equatable {
        /// Reduce Motion, or the owner's own ambient-motion switch.
        case motionIsOff
        /// Not a success. See `Outcome`.
        case notACompletion(Outcome)
        /// This job id has had its moment already. Once, ever.
        case alreadyHadItsMoment
        /// Another ceremony is on screen. Six at once is a hostage situation:
        /// the rest simply appear.
        case oneAtATime
        /// Nothing to reveal — no evidence lines. The card still shows whatever
        /// it was going to show; there is just no sequence to stagger.
        case nothingToReveal
    }

    enum Decision: Equatable {
        case play(Plan)
        case skip(Skip)
    }

    /// The timings, and nothing else. SwiftUI does the drawing.
    struct Plan: Equatable {
        /// How many evidence lines get a beat of their own.
        let revealSteps: Int
        /// The gap between them. Shrinks as `revealSteps` grows.
        let stagger: TimeInterval
        /// The rest before the card joins the deck.
        let afterglow: TimeInterval

        /// Total wall-clock from the card turning over to it settling.
        var total: TimeInterval {
            TimeInterval(max(0, revealSteps - 1)) * stagger + afterglow
        }
    }

    // ── the budget ───────────────────────────────────────────────────────────

    /// The hard ceiling. Beyond this a person is waiting on choreography to
    /// learn something about their own life.
    static let maximumDelay: TimeInterval = 1.2
    /// The rest at the end. Short — it is a breath, not a pause for effect.
    static let afterglow: TimeInterval = 0.28
    /// What a stagger wants to be when there is room for it.
    static let preferredStagger: TimeInterval = 0.13
    /// The server caps `evidence` at 12 entries before the row is ever written,
    /// so this is the real upper bound and not a guess.
    static let evidenceHardCap = 12

    /// The anticipation pulse's period, in seconds.
    ///
    /// 2.99 is not a rounded number and is not arbitrary: it is `PendantPulse`'s
    /// own rate, so a card that is working breathes at exactly the speed the
    /// pendant's light does. Four ambient rates already coexist in this app
    /// (1.6 WaveBars, 3.2 BreathingDot, 2.99 PendantPulse); this joins the
    /// pendant's rather than inventing a fifth, because a job running and a
    /// device listening are the same fact wearing two faces.
    static let breathPeriod: TimeInterval = 2.99

    /// The same rate as an angular frequency, because every breathing view in
    /// this app is written as `sin(t * ω)` rather than with a period. Kept
    /// derived rather than as a second literal: two spellings of one rate is
    /// how four different ambient speeds came to coexist here already.
    static var breathOmega: Double { 2 * Double.pi / breathPeriod }

    /// 30fps. Both existing ambient views here cap their timeline and this one
    /// must too: a job can be running for forty minutes, and an uncapped
    /// TimelineView redraws at the display's full rate for all of it.
    static let redrawInterval: Double = 1.0 / 30.0

    // ── the decision ─────────────────────────────────────────────────────────

    /// `evidenceLines` is how many entries the receipt actually holds — a real
    /// browser receipt carries 5 to 9, only ONE is guaranteed non-empty, and a
    /// job with no workflow can legitimately reach `done` with none at all.
    static func decide(outcome: Outcome,
                       evidenceLines: Int,
                       reduceMotion: Bool,
                       ambientMotionOn: Bool,
                       alreadyPlayed: Bool,
                       ceremonyOnScreen: Bool) -> Decision {
        // Motion first: it is the one the owner and the system both control,
        // and the app honours the pair everywhere else as
        // `reduceMotion || !ambientMotion`.
        if reduceMotion || !ambientMotionOn { return .skip(.motionIsOff) }
        guard outcome == .succeeded else { return .skip(.notACompletion(outcome)) }
        if alreadyPlayed { return .skip(.alreadyHadItsMoment) }
        if ceremonyOnScreen { return .skip(.oneAtATime) }

        let steps = min(max(0, evidenceLines), evidenceHardCap)
        guard steps > 0 else { return .skip(.nothingToReveal) }
        return .play(plan(revealSteps: steps))
    }

    /// The plan for N lines, compressed to fit the budget.
    ///
    /// One line gets no stagger at all — there is nothing to stagger against —
    /// so its total is exactly the afterglow.
    static func plan(revealSteps: Int) -> Plan {
        let steps = min(max(0, revealSteps), evidenceHardCap)
        guard steps > 1 else {
            return Plan(revealSteps: steps, stagger: 0, afterglow: afterglow)
        }
        let room = maximumDelay - afterglow
        let stagger = min(preferredStagger, room / TimeInterval(steps - 1))
        return Plan(revealSteps: steps, stagger: stagger, afterglow: afterglow)
    }

    /// Whether the card should be breathing. A job the server is working on
    /// right now, and nothing else — a queued job has not started and a pulse
    /// over it would be the app claiming activity it cannot see.
    static func breathes(status: String) -> Bool { status == "running" }

    /// What Developer Diagnostics prints.
    static func words(_ decision: Decision) -> String {
        switch decision {
        case .play(let p):
            return "\(p.revealSteps) lines over \(String(format: "%.2f", p.total))s"
        case .skip(let why):
            switch why {
            case .motionIsOff:          return "motion is off"
            case .notACompletion(let o): return "not a completion (\(o))"
            case .alreadyHadItsMoment:  return "already had its moment"
            case .oneAtATime:           return "another ceremony is on screen"
            case .nothingToReveal:      return "no evidence to reveal"
            }
        }
    }
}
