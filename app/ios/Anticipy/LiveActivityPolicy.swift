import Foundation

/// WHAT THE LOCK SCREEN IS ALLOWED TO SAY.
///
/// A Live Activity is the most privileged surface this product has: it sits on
/// a locked phone, in front of anybody who picks it up, without the owner
/// choosing to look. Two rules follow from that and they are the reason this
/// file is pure and tested rather than inlined into a view.
///
/// ── ONE: IT NEVER QUOTES ANYBODY ──────────────────────────────────────────
///
/// Nothing spoken, heard or transcribed may appear here. Not a line, not a
/// fragment, not a goal's wording. The lock screen is readable over somebody's
/// shoulder on a train, and an always-on microphone that prints what it heard
/// onto a locked screen is the single worst thing this product could do. The
/// runner greps the widget's source for any path from a transcript to a label.
///
/// What may appear: counts, durations, and the app's own fixed words.
///
/// ── TWO: IT NEVER APPROVES ────────────────────────────────────────────────
///
/// "Nothing sends without your OK" means an OK given with the consequence in
/// front of you. A lock-screen button is a one-tap yes on a surface too small
/// to carry the consequence, given by whoever is holding the phone. So the
/// activity may SAY something is waiting and may open the app at it; it may
/// never approve, send, or confirm. `Action` has no case for it, which is the
/// enforceable version of that sentence.
enum LiveActivityPolicy {

    /// Why the activity is on screen at all. It exists only while there is a
    /// live reason; the moment there is not, it ends rather than lingering.
    enum Reason: Equatable {
        /// The microphone is on and hearing.
        case listening
        /// The owner pressed hold. Still on screen, because a paused capture
        /// that vanished would read as a crash.
        case paused
        /// Listening is on but the phone cannot reach the server, so what is
        /// heard is being kept locally.
        case offline
        /// Work is running that the owner asked for.
        case working
        /// Something needs the owner and cannot proceed without them.
        case waiting
    }

    /// The one control the lock screen may offer.
    ///
    /// There is deliberately no `approve`. See the file header: an OK given
    /// from a lock screen is an OK given without the consequence, by whoever
    /// is holding the phone.
    enum Action: Equatable {
        /// Stop listening. Safe, reversible, and the only thing somebody
        /// actually wants from a locked phone.
        case stopListening
        /// Open the app at the thing that needs them. Opens; does not decide.
        case openApp
    }

    /// Everything the surface draws, decided here.
    struct Face: Equatable {
        /// Always the product's name — the lock screen has to say whose
        /// activity this is before it says anything else.
        let title: String
        /// The one line under it. Counts and durations only.
        let detail: String
        /// Whether the mark should breathe. False whenever the microphone is
        /// not actually hearing, because a moving indicator over a stopped
        /// engine is the same lie on a lock screen as it is in the app.
        let alive: Bool
        let action: Action
    }

    /// `heard` is the number of lines this listening session has produced —
    /// a count, never their content. `elapsed` is seconds since it started.
    /// `pending` is how many jobs are in the state `reason` names, so the one
    /// capsule can say how much is going on instead of "something".
    static func face(_ reason: Reason, heard: Int, elapsed: TimeInterval,
                     pending: Int = 0) -> Face {
        switch reason {
        case .listening:
            return Face(title: "Anticipy",
                        detail: heardLine(heard, elapsed: elapsed),
                        alive: true, action: .stopListening)
        case .offline:
            // Says the true thing rather than the reassuring one. Somebody
            // whose phone has no signal should learn it here, not later.
            return Face(title: "Anticipy",
                        detail: [heardLine(heard, elapsed: elapsed), qualifier(.offline)]
                            .compactMap { $0 }.joined(separator: " · "),
                        alive: true, action: .stopListening)
        case .paused:
            return Face(title: "Anticipy",
                        detail: "Paused",
                        alive: false, action: .stopListening)
        case .working:
            // A COUNT, never a name. "Working on the deck" would put somebody's
            // sentence on a locked screen; "Working on 2 things" says the same
            // useful part of it and nothing that identifies anybody.
            return Face(title: "Anticipy",
                        detail: pending > 1 ? "Working on \(pending) things"
                                            : "Working on something",
                        alive: false, action: .openApp)
        case .waiting:
            // NOT the goal's wording. A goal is somebody's sentence and this
            // is a lock screen.
            return Face(title: "Anticipy",
                        detail: pending > 1 ? "\(pending) waiting on you"
                                            : "Waiting on you",
                        alive: false, action: .openApp)
        }
    }

    /// THE PART OF THE LINE A RUNNING CLOCK MUST NOT SWALLOW.
    ///
    /// The lock-screen view does not print `detail` while the microphone is
    /// live — it draws the count beside a timer it ticks itself, so that the
    /// app is not woken once a second to push a number. That optimisation once
    /// silently ate the offline qualifier: the capsule said "3 things heard ·
    /// 2:12" with no signal and no hint that the words were going nowhere,
    /// which is precisely the reassuring lie `.offline` exists to refuse.
    ///
    /// So the qualifier is separable, and the view appends it to the live line.
    /// `face` composes the same two pieces, so there is one definition of what
    /// offline says.
    static func qualifier(_ reason: Reason) -> String? {
        reason == .offline ? "keeping it on this phone" : nil
    }

    /// What the count line reads. A duration alone is what a recorder shows; a
    /// count alone hides how long it has been on. Both, and neither is ever a
    /// word somebody said.
    static func heardLine(_ heard: Int, elapsed: TimeInterval) -> String {
        let time = clock(elapsed)
        guard heard > 0 else { return time.isEmpty ? "Listening" : "Listening · \(time)" }
        let things = heard == 1 ? "1 thing heard" : "\(heard) things heard"
        return time.isEmpty ? things : "\(things) · \(time)"
    }

    /// mm:ss under an hour, h:mm:ss over it. Empty below a second, so a freshly
    /// started activity does not flash "0:00".
    static func clock(_ seconds: TimeInterval) -> String {
        guard seconds.isFinite, seconds >= 1 else { return "" }
        let total = Int(seconds)
        let s = total % 60, m = (total / 60) % 60, h = total / 3600
        if h > 0 { return String(format: "%d:%02d:%02d", h, m, s) }
        return String(format: "%d:%02d", m, s)
    }

    /// Which reason wins when several are true at once.
    ///
    /// Listening outranks everything, because it is the state with a microphone
    /// open and the one the owner most needs to be able to see and stop. An
    /// activity that showed "Waiting on you" while the microphone was live
    /// would be hiding the more important fact behind the more interesting one.
    static func reason(listening: Bool,
                       paused: Bool,
                       reachable: Bool,
                       working: Bool,
                       waiting: Bool) -> Reason? {
        if listening && paused { return .paused }
        if listening { return reachable ? .listening : .offline }
        if waiting { return .waiting }
        if working { return .working }
        return nil          // nil ends the activity
    }

    /// The Dynamic Island's compact form has room for a handful of characters.
    /// A count is the only thing that survives being that small and still means
    /// something.
    static func compact(_ reason: Reason, heard: Int, pending: Int = 0) -> String {
        switch reason {
        case .listening, .offline: return heard > 0 ? "\(heard)" : ""
        case .paused:              return "❙❙"
        case .working:             return pending > 1 ? "\(pending)" : "···"
        case .waiting:             return pending > 1 ? "\(pending)!" : "!"
        }
    }

    /// How long an activity may sit on a lock screen once nothing is happening.
    /// iOS will end it eventually on its own; this is the app being polite
    /// first.
    static let lingerAfterEnding: TimeInterval = 8
}

/// The reason, back out of the wire form. An unknown value is treated as
/// listening rather than crashing or drawing nothing: a widget that fails
/// closed on a locked phone leaves somebody with a microphone they cannot see.
enum ActivityReason {
    static func from(_ raw: String) -> LiveActivityPolicy.Reason {
        switch raw {
        case "paused":  return .paused
        case "offline": return .offline
        case "working": return .working
        case "waiting": return .waiting
        default:        return .listening
        }
    }

    static func wire(_ reason: LiveActivityPolicy.Reason) -> String {
        switch reason {
        case .listening: return "listening"
        case .paused:    return "paused"
        case .offline:   return "offline"
        case .working:   return "working"
        case .waiting:   return "waiting"
        }
    }
}
