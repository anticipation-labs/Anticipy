import Foundation

/// THE PENDANT'S ONBOARDING, decided in one pure place.
///
/// Spec: `research/2026-09-06-pendant-onboarding-design.md`, written off 28
/// screens of Oura's ring onboarding and 11 photographs of the Anticipy
/// prototype.
///
/// ── THE DECISION THAT SHAPES EVERYTHING ───────────────────────────────────
///
/// **Most people do not have a pendant, and the flow is built for them.** There
/// is no shipping hardware yet, and even once there is, the phone is the
/// primary ear. So the offer screen's PRIMARY action is *Continue without one*
/// and owning a pendant is the quiet secondary.
///
/// This is deliberately the opposite of Oura, whose first screen makes "Start"
/// mean owning a ring and "No Oura Ring yet?" the outlined alternative. Oura
/// sells rings. Anticipy works completely without the pendant, so continuing
/// without one is not a lesser path and must never be dressed as one — no
/// "skip", no "maybe later", no greyed-out anything. `offer.primary` is the
/// ordinary road.
///
/// ── WHAT THIS FILE MAY NOT DO ─────────────────────────────────────────────
///
/// It may not talk to a radio, and it may not invent a fact about hardware. A
/// battery percentage, a firmware version or a signal strength that nobody
/// measured is a sentence that will be wrong in front of the first real device.
/// Everything here is either given to it or is copy.
enum PendantOnboardingPolicy {

    // MARK: - The beats

    enum Beat: Int, CaseIterable, Equatable {
        /// Everyone sees this one. Almost everyone leaves from it.
        case offer
        /// Owners only, from here down.
        case wake
        case looking
        case pairing
        case wearing
        case done
    }

    /// What the person chose on the offer screen.
    enum Answer: Equatable {
        case hasOne
        case notYet
    }

    static func next(after beat: Beat, answer: Answer? = nil) -> Beat? {
        switch beat {
        case .offer:   return answer == .hasOne ? .wake : nil   // nil = first run carries on
        case .wake:    return .looking
        case .looking: return .pairing
        case .pairing: return .wearing
        case .wearing: return .done
        case .done:    return nil
        }
    }

    // MARK: - What the radio is doing

    /// The states the screens must draw. Mirrors what `PendantManager` can
    /// report, plus the two refusals that come from iOS rather than the radio.
    enum Radio: Equatable {
        case warmingUp
        case scanning
        case foundSomething(count: Int)
        case connecting(name: String)
        case connected(name: String)
        /// The person has not been asked for Bluetooth yet, or said no.
        case needsPermission
        /// Bluetooth is switched off at the system level.
        case switchedOff
        /// Long enough with nothing, that saying nothing would read as broken.
        case nothingFound
    }

    struct Face: Equatable {
        let title: String
        let body: String
        /// Whether the screen should show live motion. A still screen under
        /// "Looking…" is the one combination that lies.
        let searching: Bool
        /// Whether a person can get out of here without hardware. It is true on
        /// every screen, because somebody who tapped "I have a pendant" by
        /// mistake must never be trapped behind a device they do not own.
        let offersWayOut: Bool = true
    }

    static func face(_ radio: Radio) -> Face {
        switch radio {
        case .warmingUp:
            return Face(title: "One moment",
                        body: "Waiting for this phone's Bluetooth to come up.",
                        searching: true)
        case .scanning:
            return Face(title: "Looking for your pendant",
                        body: "Hold it close to the phone. It shows a soft light when it is awake.",
                        searching: true)
        case .foundSomething(let count):
            return Face(title: count == 1 ? "Found one" : "Found \(count)",
                        body: "Tap the one that is yours.",
                        searching: true)
        case .connecting(let name):
            return Face(title: "Connecting to \(name)",
                        body: "This takes a few seconds.",
                        searching: true)
        case .connected(let name):
            return Face(title: "\(name) is connected",
                        body: "It will find this phone on its own from now on.",
                        searching: false)
        case .needsPermission:
            return Face(title: "I need Bluetooth to find it",
                        body: "iOS will ask once. Bluetooth is only used to reach your pendant.",
                        searching: false)
        case .switchedOff:
            return Face(title: "Bluetooth is switched off",
                        body: "Turn it on in Settings or Control Centre and I'll look again.",
                        searching: false)
        case .nothingFound:
            return Face(title: "Nothing yet",
                        body: "Hold the pendant until its light breathes, and keep it near the phone.",
                        searching: true)
        }
    }

    // MARK: - The copy that must not drift

    enum Copy {
        /// The offer. One sentence about what the hardware is FOR, never about
        /// what the app lacks without it.
        static let offerTitle = "Better ears, when you want them"
        static let offerBody =
            "The pendant hears the room the way this phone does, without the phone "
            + "being out. Most people start without one, and nothing is missing if you do."
        /// PRIMARY, and it is the one without hardware.
        static let offerPrimary = "Continue without one"
        /// Quiet, secondary, and never styled as the main road.
        static let offerSecondary = "I have a pendant"
        /// Said under both, so nobody feels they are closing a door.
        static let offerFootnote = "You can pair one any time in Settings."

        static let wakeTitle = "Wake it up"
        static let wakeBody =
            "Hold the button until the light breathes. Keep it within arm's reach of this phone."

        static let wearTitle = "Wear it where it can hear"
        static let wearBody =
            "Anywhere on the chain is fine. Against a collar or a scarf is not — cloth over "
            + "the microphone is the one thing it cannot hear through."

        static let doneTitle = "That's the pendant sorted"

        /// Oura puts a "Why we ask" beside the personal details it collects, and
        /// this product already opens the microphone's promises before iOS
        /// asks. Bluetooth gets the same courtesy: the sentence explaining it
        /// is reachable BEFORE the system dialog, not after somebody has
        /// refused one they did not understand.
        static let whyBluetooth = "Why Bluetooth?"
        static let whyBluetoothTitle = "What Bluetooth is for"
        static let whyBluetoothPoints = [
            "It is only ever used to reach your pendant. Nothing else is looked for and nothing is broadcast.",
            "Your location is not read. iOS mentions location on this prompt because a Bluetooth scan can in principle infer it; this app asks for none and stores none.",
            "The pendant sends audio to this phone and nowhere else. What leaves the phone is the same text the phone's own microphone would produce.",
            "Turning Bluetooth off later stops the pendant and changes nothing else.",
        ]

        /// The way out, offered on every screen behind the offer. Oura says
        /// "No Oura Ring yet?" twice, quietly, and never as an error; this is
        /// the same idea in this product's voice.
        static let wayOut = "I don't have it with me"
    }

    /// The closing line, which names what actually changed rather than
    /// congratulating somebody.
    static func doneLine(deviceName: String?) -> String {
        guard let name = deviceName, !name.isEmpty else {
            return "It will listen when you ask it to, and stay quiet otherwise."
        }
        return "\(name) will listen when you ask it to, and stay quiet otherwise."
    }

    // MARK: - What may be said about a device

    /// A row in the found-devices list.
    struct Candidate: Equatable, Identifiable {
        let id: String
        let name: String
        /// Signal, if it was measured. Nil is drawn as nothing at all.
        let rssi: Int?

        /// The last block of the identifier, which is what tells two pendants
        /// in one room apart. Nil when the id is not shaped like one, because a
        /// truncated something-else is worse than nothing.
        var shortID: String? {
            let tail = id.split(separator: "-").last.map(String.init) ?? id
            guard tail.count >= 4, tail.allSatisfy({ $0.isHexDigit }) else { return nil }
            return String(tail.suffix(6)).uppercased()
        }

        /// Four bars' worth of nearness, or nil when nothing was measured.
        /// NEVER a percentage: RSSI is not a percentage and dressing it as one
        /// is a number somebody will believe.
        var nearness: Int? {
            guard let rssi else { return nil }
            switch rssi {
            case (-55)...:      return 3
            case (-70)..<(-55): return 2
            case (-85)..<(-70): return 1
            default:            return 0
            }
        }
    }

    /// Strongest first, because the pendant in somebody's hand is the one they
    /// mean. Ties break by id so the list does not reshuffle under a thumb.
    static func ordered(_ found: [Candidate]) -> [Candidate] {
        found.sorted {
            ($0.rssi ?? Int.min, $1.id) > ($1.rssi ?? Int.min, $0.id)
        }
    }

    /// How long to look before saying "nothing yet". Long enough not to give up
    /// in front of somebody still fetching the pendant from another room.
    static let patience: TimeInterval = 12
}
