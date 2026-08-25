// MeetingOfferPolicy — decides whether the Mac OFFERS to record. It never
// decides to record; that click belongs to the owner (spec §6.1, and the card's
// "detection may be automatic, recording starts explicitly").
//
// LAW 1: this file is senses-layer plumbing. Its only inputs are which PROCESS
// holds which STREAM — `kAudioProcessPropertyIsRunningInput` / `…IsRunningOutput`
// over `kAudioHardwarePropertyProcessObjectList`. It never sees a sample and it
// never sees a word. Bundle identifiers appear here to LABEL the offer and to
// hold the owner's never-offer list; they are forbidden from deciding what
// anything MEANS, and there is no bundle list that decides what a meeting is.
//
// The signal is grounded in measurement, not belief. Measured on macOS 15.6.1
// (24G90) on 2026-08-25, recorded in research/2026-08-25-macos-concurrent-capture.md:
//
//   a Voice-Processing-IO process (what Zoom/Meet/Teams use)  -> in=1 out=1
//   a pure playback process (afplay)                          -> in=0 out=1
//   macOS dictation (com.apple.CoreSpeech)                     -> in=1 out=0
//
// Only the first is a two-way conversation. That is the whole rule.
import Foundation

/// One reading of one process's Core Audio IO state. Plumbing, not content.
public struct ProcessAudioObservation: Equatable, Sendable {
    public let pid: Int32
    /// Labels the offer ("Zoom" reads better than "us.zoom.xos") and keys the
    /// never-offer list. Never a predicate over meaning.
    public let bundleID: String?
    public let isRunningInput: Bool
    public let isRunningOutput: Bool

    public init(pid: Int32, bundleID: String?, isRunningInput: Bool, isRunningOutput: Bool) {
        self.pid = pid
        self.bundleID = bundleID
        self.isRunningInput = isRunningInput
        self.isRunningOutput = isRunningOutput
    }

    /// A two-way conversation on this machine, stated in the only terms the OS
    /// offers. Neither half alone is one.
    public var isTwoWay: Bool { isRunningInput && isRunningOutput }
}

public enum MeetingOffer: Equatable, Sendable {
    /// Nothing to offer. The menu-bar item stays grey.
    case none
    /// The menu-bar item goes amber and says so. A click, and only a click,
    /// starts capture.
    case offer(pid: Int32, bundleID: String?)

    public var isOffer: Bool { if case .offer = self { return true }; return false }
}

public struct MeetingOfferPolicy: Sendable {
    /// How many consecutive readings must agree before the offer appears. One
    /// reading fires on anything that momentarily touches both streams; the
    /// owner should not see the banner flicker. This is a threshold over how
    /// long a PROCESS HELD A STREAM — plumbing — and never over content.
    public let sustainedReadings: Int

    public init(sustainedReadings: Int = 3) {
        self.sustainedReadings = max(1, sustainedReadings)
    }

    /// `history` is oldest-first; each element is one full sweep of the process
    /// object list. Returns an offer only when one process that is not us has
    /// been two-way across the last `sustainedReadings` sweeps.
    public func offer(history: [[ProcessAudioObservation]],
                      selfPID: Int32,
                      neverOffer: Set<String> = []) -> MeetingOffer {
        guard history.count >= sustainedReadings else { return .none }
        let window = history.suffix(sustainedReadings)

        // Candidates from the most recent sweep, in a stable order so the same
        // input always produces the same offer.
        guard let newest = window.last else { return .none }
        let candidates = newest
            .filter { $0.pid != selfPID && $0.isTwoWay }
            .filter { obs in
                guard let b = obs.bundleID else { return true }
                return !neverOffer.contains(b)
            }
            .sorted { $0.pid < $1.pid }

        for c in candidates {
            let heldThroughout = window.allSatisfy { sweep in
                sweep.contains { $0.pid == c.pid && $0.isTwoWay }
            }
            if heldThroughout { return .offer(pid: c.pid, bundleID: c.bundleID) }
        }
        return .none
    }
}
