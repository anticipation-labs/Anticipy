import Foundation

/// Does first run offer to learn your voice?
///
/// -- The measured problem -------------------------------------------------
///
/// `VoiceEnrollView` is complete, its embedding model ships in every build, and
/// the whole app presented it from exactly ONE place: a sheet inside Settings,
/// under "Your voice", below Listening / Pendant / You. To reach it a stranger
/// had to tap the slider glyph in the Home toolbar and scroll past three
/// sections, with nobody ever suggesting they should. Nobody does.
///
/// The consequence is measured, not guessed. `research/2026-08-24-engine-
/// options.md:254` records `speaker` at 0% across 221 production events, cause
/// "enrollment unreachable", confidence "Certain" — and with no owner profile
/// the tagger returns nil for every line, which is the named cause of four of
/// the six bad acts on the only call ever scored.
///
/// -- Why this is a policy and not an `if` in the view ---------------------
///
/// Because the interesting answer is the THIRD one, and a bool cannot carry it.
/// "Offer it" and "don't offer it" are not the whole space: there is also
/// CANNOT, and the difference between "she already knows your voice" and "this
/// build cannot learn anyone's voice" is the difference between a tour that
/// respects someone's time and a tour that lies to them.
///
/// -- What CANNOT means today, said out loud -------------------------------
///
/// `SpeakerTagger.available` is FALSE in the shipping build. `project.yml`
/// unlinked sherpa-onnx for the second time in commit d3ccb133, because builds
/// 76-80 delivered ZERO rows to production and build 75 delivered 313. So
/// `VoiceEmbedderFactory.make()` returns nil, every embedding is nil, and
/// enrollment cannot enrol anybody however many screens lead to it.
///
/// THEREFORE FIRST RUN OFFERS NOTHING TODAY, deliberately. Twelve seconds of
/// reading that can never produce a profile is worse than not asking: it spends
/// the one budget first run has (the ~70-second walkthrough of
/// CONSUMER-FEEL-DIRECTION §5) to teach a stranger that the product is broken.
/// The honest move is to ask only when the answer can be yes, and that is what
/// `.cannot` is for.
///
/// This is also why closing the gate leg is NOT the same as fixing the
/// measurement: `speaker` stays at 0% until somebody re-links the engine, and
/// no amount of onboarding moves it. What changes here is that the day the
/// engine comes back, the invite is already standing in front of every new
/// person instead of three scrolls deep in Settings.
enum EnrollmentOfferPolicy {

    /// Four-state in spirit, three in fact: the fourth — "we do not know
    /// whether this phone can enrol" — cannot occur, because
    /// `SpeakerTagger.available` is a synchronous read of whether the embedder
    /// loaded, never a pending answer. If that ever becomes async, this enum
    /// gains a case rather than defaulting one of these two ways.
    enum Offer: Equatable {
        /// Ask. The engine works and there is no profile yet.
        case offer
        /// Say nothing: she already knows this voice. Re-teaching is still
        /// reachable from Settings, where somebody who wants it will look.
        case alreadyKnown
        /// This build cannot learn a voice. Offering a tour beat that
        /// dead-ends is worse than not offering it.
        case cannot
    }

    /// - Parameters:
    ///   - engineAvailable: `SpeakerTagger.available` — did the embedder load?
    ///   - hasOwnerProfile: `SpeakerTagger.hasOwnerProfile` — is there already
    ///     a voiceprint for the person signing in?
    static func firstRun(engineAvailable: Bool, hasOwnerProfile: Bool) -> Offer {
        // ORDER MATTERS, and it is the honest way round. Asked the other way,
        // a phone that cannot embed anything would report `alreadyKnown` for
        // any profile left behind by an older build that COULD — telling
        // somebody she knows their voice while every tag comes back nil.
        guard engineAvailable else { return .cannot }
        return hasOwnerProfile ? .alreadyKnown : .offer
    }

    /// Does first run put the invite on screen at all? The single question the
    /// walkthrough asks, so a view never re-derives the answer from parts.
    static func presents(engineAvailable: Bool, hasOwnerProfile: Bool) -> Bool {
        firstRun(engineAvailable: engineAvailable,
                 hasOwnerProfile: hasOwnerProfile) == .offer
    }
}
