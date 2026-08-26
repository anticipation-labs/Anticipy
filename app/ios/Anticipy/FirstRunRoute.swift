import Foundation

/// WHERE FIRST RUN IS UP TO — decided once, in a type that can be read without
/// a simulator.
///
/// The order used to be: door, then four beats. A stranger typed an email, a
/// password AND a phone number before the product had produced one single
/// thing of its own, and the mobile-UX audit's diagnosis is that Anticipy's
/// problem is ORDERING, not tone. So the two beats that ask for nothing and
/// start nothing — the introduction, and how she works — happen BEFORE the
/// door now, and the two that need an account stay behind it.
///
/// -- WHY THE MICROPHONE STAYS BEHIND THE DOOR ---------------------------
///
/// Not a preference. `AnticipySession.heard` attempts a LIVE PUSH before it
/// ever queues, and only `flushUnsent` is gated on having an account, so a
/// microphone running before an account exists would post a stranger's room to
/// the server — stopped only by the backend's own `guard.pb.js` hook, which is
/// a safety property nobody ever wrote down on the client. `.intro` therefore
/// carries the welcome and how-it-works beats and NOTHING ELSE, and
/// `run_first_run_route_tests.sh` asserts that rather than trusting it. Moving
/// the primer forward is not a smaller version of this change; it is a
/// different change, and it is not safe.
///
/// -- WHY THIS IS A TYPE AND NOT AN `if` IN A SwiftUI BODY ---------------
///
/// Because the states that matter are the ones nobody reaches by tapping:
/// force-quitting between the second beat and the door, signing out and
/// handing the phone to somebody else, reinstalling onto an account that
/// already exists. Foundation only — no SwiftUI — so a standalone swiftc
/// runner can walk every one of them, exactly as `FirstRunOwnership` is
/// walked by `run_first_run_tests.sh`.

/// The four beats, by absolute index. Moved verbatim out of `OnboardingView`'s
/// private `Step`, which is now a typealias onto this — so every `Step.mic`,
/// `.tag()` and `step += 1` in that file still means what it meant.
///
/// The browser was a fifth until `design/day-zero.md` took it out of first run
/// for exceeding the ~70-second budget; nothing may be added here.
enum FirstRunBeat {
    static let welcome = 0
    static let howItWorks = 1
    static let mic = 2
    static let phone = 3
    static let count = 4
}

/// Which beats one instance of `OnboardingView` is carrying.
///
/// THE INDEX STAYS ABSOLUTE IN EVERY SEGMENT — `.rest` simply starts at
/// `FirstRunBeat.mic` rather than at zero. That is what keeps the progress
/// track honest without the track knowing segments exist: `FirstRunTrack`
/// offsets by `beatNames.count - pageCount`, `pageCount` is always
/// `FirstRunBeat.count`, and so the microphone beat reads "4 of 5" whichever
/// way the person arrived at it.
enum FirstRunSegment: Equatable {
    /// Before the door. Asks for nothing, saves nothing, starts nothing.
    case intro
    /// After the door, for somebody who already had the introduction.
    case rest
    /// After the door, all four beats — a different person has arrived on a
    /// phone whose introduction was spent on somebody else.
    case whole

    var pages: [Int] {
        switch self {
        case .intro:
            return [FirstRunBeat.welcome, FirstRunBeat.howItWorks]
        case .rest:
            return [FirstRunBeat.mic, FirstRunBeat.phone]
        case .whole:
            return [FirstRunBeat.welcome, FirstRunBeat.howItWorks,
                    FirstRunBeat.mic, FirstRunBeat.phone]
        }
    }

    /// DERIVED FROM `pages`, never written down twice. `OnboardingView` seeds
    /// both `step` and `lastStep` from `firstStep`: seeding only the first
    /// leaves the first page turn recording a `previous` of 0 that nobody was
    /// ever on, which is a wrong value one edit away from mattering to
    /// `savePhoneOnLeaving`.
    var firstStep: Int { pages.first ?? FirstRunBeat.welcome }

    /// The terminal page of THIS segment. `advance()` compares against this
    /// rather than `FirstRunBeat.count - 1`, which is the dead end that the
    /// "routing only, ~10 lines" version of this change produces: in `.intro`,
    /// howItWorks is 1 < 3, so Continue steps to a page tagged 2 that this
    /// segment does not carry — a blank screen, pre-auth, with no way forward.
    var lastStep: Int { pages.last ?? FirstRunBeat.welcome }

    /// DERIVED, NOT PREFERRED. On howItWorks pre-auth the person has exactly
    /// one beat behind them, so the only honest ordinal is "1 of 5" — and the
    /// track's rule is that it never opens at 1. The other available number,
    /// the absolute "3 of 5", counts an account nobody has made yet. Both
    /// permitted numbers are forbidden, so no number is shown. The same
    /// argument bans a counting line in the prose under either pre-auth beat.
    var showsTrack: Bool { self != .intro }

    /// Whether clearing this segment's last page ends first run. It does not
    /// in `.intro`: the last page there is cleared by walking through the
    /// door, and a voice-enrolment offer must not be raised over somebody who
    /// has no account to attach a voice to.
    var endsTheTour: Bool { self != .intro }
}

/// What the app shows on this launch.
///
/// Three durable facts decide it, and `decide` is total over all eight of
/// their combinations. Two of those eight are the ones this type was written
/// for: `hasSeenIntro` true with no account (somebody force-quit between the
/// introduction and the door, and must NOT be shown the introduction again),
/// and `hasSeenIntro` false with an account and no tour (a different person
/// signed in, and must be shown the introduction they have never seen).
enum FirstRunRoute: Equatable {
    /// The two pre-auth beats.
    case intro
    /// `AuthView`.
    case door
    /// The beats behind the door.
    case tour(FirstRunSegment)
    /// `HomeView`.
    case home

    /// The one segment this route renders, if it renders `OnboardingView` at
    /// all — so the call site has one shape rather than two.
    ///
    /// `decide` never returns `.tour(.intro)`: the pre-auth beats are reached
    /// through `.intro`, which is the case that does not end the tour.
    var segment: FirstRunSegment? {
        switch self {
        case .intro: return .intro
        case .tour(let segment): return segment
        case .door, .home: return nil
        }
    }

    /// WHETHER AN INTRODUCTION ALREADY GIVEN ON THIS DEVICE COULD HAVE BEEN
    /// GIVEN TO THE PERSON NOW SIGNING IN.
    ///
    /// Asked at the `.replay` moment, and it has to be asked, because
    /// `FirstRunOwnership.arriving` returns `.replay` for the COMMONEST path
    /// in the product as well as for the rare one it was written about: a
    /// brand-new sign-up has `onboardedAccount == ""`, which is not the id it
    /// just minted, so the fresh stranger and the second person on a handed-on
    /// phone arrive at the same arm. Clearing `hasSeenIntro` on both — which
    /// is what "clear it wherever `hasOnboarded` is cleared" literally says —
    /// walks every new customer through the welcome typewriter and the
    /// how-it-works cards A SECOND TIME, forty seconds after the first, with a
    /// progress track calling it "Hello, 2 of 5" over a screen they have
    /// already read. That is the product repeating itself, which is the exact
    /// complaint this whole reordering exists to answer.
    ///
    /// So the two flags are cleared together only when the phone already
    /// carries somebody's first run. `hasOnboarded` on its own is the flag
    /// FirstRunOwnership argues about; `onboardedAccount` non-empty catches
    /// the other shape, where a previous person signed in and abandoned the
    /// tour part-way.
    ///
    /// -- WHAT THIS DELIBERATELY DOES NOT CATCH ------------------------------
    ///
    /// An installer who taps through the two pre-auth beats and never signs
    /// in leaves `hasSeenIntro` true with no owner recorded, which is exactly
    /// what the stranger who walked those beats themselves a moment ago leaves.
    ///
    /// "There is no third fact to separate them" would be too strong, and it
    /// is worth being exact about which pair is really trapped. A NON-durable
    /// fact does separate the stranger cleanly — whether the introduction was
    /// walked in THIS process — and it could be read here. What survives no
    /// fact at all is the installer versus the person who walked the
    /// introduction, force-quit before the door, and came back: on the launch
    /// after a force-quit no in-process marker exists either, so those two are
    /// the pair one of which has to be got wrong. This gets the rarer one
    /// wrong. Taking the other side is a real option, and its price is that
    /// the force-quitter is walked through both beats a second time; it is
    /// written down here rather than done, because it is a trade and not a fix.
    ///
    /// What that costs is bounded, and it is worth writing down: the owner of
    /// such a phone misses the two EXPLANATORY beats. They do not miss the
    /// microphone primer, because `hasOnboarded` is still cleared on the very
    /// same decision — so listening is still asked for, and the failure
    /// FirstRunOwnership exists to prevent ("she hears nothing all week")
    /// cannot come back through this door.
    static func introSurvivesReplay(onboardedAccount: String,
                                    hasOnboarded: Bool) -> Bool {
        !hasOnboarded && onboardedAccount.isEmpty
    }

    /// - Parameters:
    ///   - hasSeenIntro: whether the two pre-auth beats have been cleared on
    ///     this device by the person the app currently believes is holding it.
    ///     Stored per DEVICE because at the moment it is written there is no
    ///     account to key it to — that is the whole point of the fix — and
    ///     cleared per ACCOUNT on the same `FirstRunOwnership.Decision` that
    ///     clears `hasOnboarded`, because an introduction is said to a person
    ///     and not to a handset.
    ///   - isSignedIn: an account exists on this device.
    ///   - hasOnboarded: the tour flag, owned by `FirstRunOwnership`.
    static func decide(hasSeenIntro: Bool,
                       isSignedIn: Bool,
                       hasOnboarded: Bool) -> FirstRunRoute {
        guard isSignedIn else {
            // Signed out is NOT the same question as "is this a new person".
            // Before somebody authenticates the app cannot know who is holding
            // the phone, so it must not guess by showing or hiding an
            // introduction — it shows the door and lets the sign-in answer it.
            //
            // TWO FLAGS, BECAUSE ONE OF THEM DID NOT EXIST YET. `hasSeenIntro`
            // is new with this change, so it is false on every handset that
            // earned `hasOnboarded` on an earlier build, and nothing writes it
            // retroactively: the only lines that write it are walked by
            // somebody doing THIS build's first run. Read on its own, this
            // branch therefore sent every existing owner who signed out into
            // the new-user introduction — the logo animation, the typewriter
            // and the three how-it-works cards, neither beat carrying a skip —
            // and contradicted the paragraph above it while doing so.
            //
            // A completed tour on this handset is proof the introduction was
            // given on it, because until the door moved all four beats sat
            // BEHIND it and `hasOnboarded` could not be earned without walking
            // them. That is the adoption argument `FirstRunOwnership` already
            // makes about the pre-upgrade flag, not a second guess about who is
            // holding the phone — and the pair (tour, no introduction) can only
            // be the pre-upgrade handset, because both `onFinished` sites write
            // the two flags together and every clear clears them together.
            return (hasSeenIntro || hasOnboarded) ? .door : .intro
        }
        guard !hasOnboarded else { return .home }
        return .tour(hasSeenIntro ? .rest : .whole)
    }
}
