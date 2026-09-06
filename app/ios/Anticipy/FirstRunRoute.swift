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

/// The in-app beats, by absolute index. Moved out of `OnboardingView`'s
/// private `Step`, which is now a typealias onto this — so every `Step.mic`,
/// `.tag()` and `step += 1` in that file still means what it meant.
///
/// THE ORDER BEHIND THE DOOR IS: your name, your computer, then the
/// microphone. The microphone is LAST on purpose — it is the one thing first
/// run asks that iOS then asks again, so it is asked once everything else is
/// settled and the finale can say what it decided. Nothing about that order
/// moves it in front of the door: `.intro` still carries the welcome and the
/// tour and NOTHING ELSE.
///
/// Computer setup used to be omitted because the old browser page was a long
/// task nobody could complete on the phone. It is back as one OPTIONAL handoff
/// beat: the phone opens or shares hosted setup pages, while installation still
/// happens on the computer.
enum FirstRunBeat {
    static let welcome = 0
    static let tour = 1
    static let name = 2
    static let computer = 3
    /// The pendant's offer. AFTER the computer and BEFORE the microphone, and
    /// that ordering is the whole of it: the mic beat must stay last, because
    /// it is the one that asks iOS for the microphone and `heard` pushes live
    /// before it queues. Adding a beat in front of it moves nothing forward.
    ///
    /// Almost nobody continues past the offer — there is no shipping pendant —
    /// so this reads as one extra screen with a plain "Continue without one" on
    /// it. See research/2026-09-06-pendant-onboarding-design.md.
    static let pendant = 4
    /// "Which apps do you live in?" — the Connections spec's STEP 2, page 45.
    /// AFTER the number and the pendant, and BEFORE the microphone, exactly
    /// where the spec puts it and for the same reason the pendant sits there:
    /// the mic beat is the one that asks iOS for the microphone, `heard` pushes
    /// live before it queues, and a beat added after it would run a microphone
    /// while somebody was still being asked questions.
    ///
    /// THE FAILURE THIS INDEX CLOSES. `OnboardingConnectStep.swift` and every
    /// decision it renders (`ConnectOnboardingPolicy`) were written on
    /// 2026-09-05, compiled into the target, and had ZERO CALL SITES — this
    /// enum was welcome/tour/name/computer/pendant/mic and none of them was it.
    /// A screen nothing constructs is a screen no person has: the step existed
    /// in the repository and did not exist in the product.
    ///
    /// It is the one beat that is not always walked; `ConnectBeat` below is the
    /// question of whether it is, and `FirstRunSegment.pages(showingConnect:)`
    /// is where the answer becomes a page list.
    static let connect = 5
    static let mic = 6
    static let count = 7
}

/// WHETHER THE SETUP STEP "which apps do you live in?" IS WALKED AT ALL.
///
/// Foundation only, like everything else in this file, and for the same reason:
/// the states that matter here are the ones nobody reaches by tapping — a
/// second person on a handed-on phone, a list the server would not answer, a
/// tour replayed from Settings three days after the card was shrugged at.
///
/// It decides WHEN, never WHAT. Every sentence on the step, every row on it,
/// what a Skip costs and how long the quiet lasts are `ConnectOnboardingPolicy`
/// and the contract behind it; this type cannot see that file and must not
/// restate one number from it. `snoozeUntil(now:days:)` below is arithmetic
/// over a count of days it is HANDED.
enum ConnectBeat {

    /// What is known about this owner's connections at the moment the beat
    /// falls due.
    ///
    /// FIVE STATES, AND THE TWO THAT LOOK ALIKE ARE THE POINT. "this owner has
    /// nothing connected" and "the list could not be read" are different facts,
    /// and a Bool can carry only one of them. Folding them together is the
    /// failure that deletes this feature silently: one refused request on a bad
    /// connection would read as "already sorted", the step would be skipped,
    /// and the only place in the whole product that ever ASKS would vanish for
    /// that person with nothing on any screen to say so.
    enum Audience: Equatable {
        /// No owner ROW id on this phone. There is nobody to search a catalog
        /// for, nobody to record a snooze against, and nothing a connection
        /// could be bound to.
        case noOwner
        /// This owner already holds at least one live connection. The step's
        /// own question has been answered.
        case alreadyConnected
        /// This owner walked past the card inside the quiet it earned.
        case snoozed
        /// Read, and this owner holds nothing.
        case nothingConnected
        /// The list could not be read at all.
        case unknown
    }

    /// The audience, from the three facts the caller can actually establish.
    ///
    /// - Parameters:
    ///   - ownerIsReal: the signed-in account carries an owner ROW id. Not a
    ///     name, not an email, not this app's pre-accounts device UUID.
    ///   - liveConnections: how many connections the server says this owner
    ///     holds, or `nil` when the list could not be read. `nil` is NOT zero.
    ///   - skipSnoozeUntil: the instant a previous skip's quiet runs out, in
    ///     the same units as `now`, already scoped to this owner by
    ///     `snoozeStanding` below.
    ///
    /// ORDER, STATED: a connection that exists outranks a snooze, because it
    /// answers the question rather than postponing it; a snooze outranks an
    /// unreadable list, because it is a durable fact this phone wrote itself
    /// and a failed request is not evidence against it.
    static func audience(ownerIsReal: Bool,
                         liveConnections: Int?,
                         skipSnoozeUntil: Double,
                         now: Double) -> Audience {
        guard ownerIsReal else { return .noOwner }
        guard now.isFinite else { return .unknown }
        if let held = liveConnections, held > 0 { return .alreadyConnected }
        if skipSnoozeUntil.isFinite, now < skipSnoozeUntil { return .snoozed }
        guard liveConnections != nil else { return .unknown }
        return .nothingConnected
    }

    /// Is the beat one of the pages this launch walks?
    ///
    /// A CEILING, AND THE POLARITY IS THE DECISION. The question this asks is
    /// "is showing the step positively unnecessary?" — so a missing verdict may
    /// not fence, or the fence becomes a wall. `.unknown` therefore SHOWS the
    /// step. The cost of getting that wrong in this direction is one optional
    /// screen, with Skip on it, offered to somebody who did not need it. The
    /// cost of the other direction is the spec's step 2 disappearing again,
    /// which is the defect that was already shipped once.
    static func isShown(to audience: Audience) -> Bool {
        switch audience {
        case .noOwner, .alreadyConnected, .snoozed:
            return false
        case .nothingConnected, .unknown:
            return true
        }
    }

    /// MAY A LATE ANSWER STILL CHANGE THE PAGE LIST?
    ///
    /// Only while the person is still in front of the beat. The connections
    /// list is read over the network, so the answer can land at any moment; if
    /// it landed while somebody was STANDING on the connect beat and said
    /// "already connected", the page would be removed from under them and the
    /// `ForEach` would render nothing — a blank screen, mid-setup, with no way
    /// forward. That is the same dead end `segment.lastStep` was written for,
    /// arriving from the other side, so the list is frozen the moment it is
    /// reached.
    static func mayAdoptAudience(standingOn step: Int) -> Bool {
        step < FirstRunBeat.connect
    }

    /// The snooze this device is entitled to honour, or zero.
    ///
    /// A SNOOZE BELONGS TO A PERSON, NOT TO A HANDSET, and the durable store is
    /// per device — the same shape as `hasSeenIntro`, with the same trap.
    /// Without this, a second person signing in on a handed-on phone inherits
    /// the first one's quiet and is never shown the step at all. So the owner
    /// is stored beside the instant and compared exactly; anything else scores
    /// zero, which SHOWS the step.
    static func snoozeStanding(storedOwner: String,
                               storedUntil: Double,
                               owner: String) -> Double {
        guard !owner.isEmpty, storedOwner == owner, storedUntil.isFinite else { return 0 }
        return storedUntil
    }

    /// When a skip's quiet runs out.
    ///
    /// THE NUMBER OF DAYS IS NOT DECIDED HERE. It is the contract's
    /// `ONBOARDING_SKIP_SNOOZE_DAYS`, mirrored in
    /// `ConnectOnboardingPolicy.skipMeans.snoozeDays` and read back out of the
    /// TypeScript by `run_connect_onboarding_tests.sh`. This file cannot see
    /// that file — it is compiled on its own — so it takes the count and does
    /// the arithmetic. Writing `7` here would be a second book, and the two
    /// books would disagree the week somebody edited one.
    ///
    /// Seconds, because that is what `Date.timeIntervalSince1970` and
    /// `@AppStorage` carry on this side. The policy keeps milliseconds. The
    /// unit gap is exactly the one `ConnectOnboardingPolicy.agreesWithSkip` was
    /// written to span, and it is spanned in the suite rather than papered over
    /// by making one side lie about its clock.
    static func snoozeUntil(now: Double, days: Int) -> Double {
        now + Double(days) * 24 * 60 * 60
    }

    /// The two durable facts a skip writes, spelled ONCE. A second copy of
    /// either string is how a rename leaves behind a write nothing reads —
    /// the accident `FirstRunOwnership.introKey` exists to prevent, and the one
    /// `run_first_run_route_tests.sh` greps for on the introduction flag.
    static let snoozeKey = "connectStepSnoozeUntil"
    static let snoozeOwnerKey = "connectStepSnoozeOwner"
}

/// The two public handoff pages, derived from the backend the app is actually
/// using. Keeping the paths here gives onboarding and Settings one source of
/// truth and keeps local walkthrough builds on their local server.
enum ComputerSetupLinks {
    static func browser(baseURL: String) -> URL? {
        URL(string: baseURL)?.appendingPathComponent("setup.html")
    }

    static func mac(baseURL: String) -> URL? {
        URL(string: baseURL)?.appendingPathComponent("mac.html")
    }
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
    /// After the door, all five beats — a different person has arrived on a
    /// phone whose introduction was spent on somebody else.
    case whole

    /// Every beat this segment CAN carry, in order. What one launch actually
    /// walks is `pages(showingConnect:)` below — the connect beat is the one
    /// page of first run that is not always due.
    var pages: [Int] {
        switch self {
        case .intro:
            return [FirstRunBeat.welcome, FirstRunBeat.tour]
        case .rest:
            return [FirstRunBeat.name, FirstRunBeat.computer,
                    FirstRunBeat.pendant, FirstRunBeat.connect, FirstRunBeat.mic]
        case .whole:
            return [FirstRunBeat.welcome, FirstRunBeat.tour,
                    FirstRunBeat.name, FirstRunBeat.computer,
                    FirstRunBeat.pendant, FirstRunBeat.connect, FirstRunBeat.mic]
        }
    }

    /// The pages this launch walks.
    ///
    /// DERIVED FROM `pages`, never written down twice — a second list is how
    /// the `ForEach` and `nextPage` end up disagreeing about which page comes
    /// after the pendant, which is a blank screen for whoever is standing
    /// there. `ConnectBeat.isShown(to:)` is the decision; this only removes.
    ///
    /// The connect beat is never a segment's first or last page, in either
    /// mode, so `firstStep` and `lastStep` do not move when it is dropped and
    /// do not need a second spelling. That is checked rather than assumed
    /// (`FirstRunRouteTests`), because if it ever stopped being true, `advance()`
    /// would finish the walkthrough on a page in the middle of it.
    func pages(showingConnect: Bool) -> [Int] {
        showingConnect ? pages : pages.filter { $0 != FirstRunBeat.connect }
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

    /// DERIVED, NOT PREFERRED. On the tour pre-auth the person has exactly
    /// one beat behind them, so the only honest ordinal is "1 of 5" — and the
    /// track's rule is that it never opens at 1. The other available number,
    /// the absolute "3 of 5", counts an account nobody has made yet. Both
    /// permitted numbers are forbidden, so no progress is shown in front of
    /// the door: the welcome and the tour carry no bar at all.
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
            // given on it, because until the door moved every in-app beat sat
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
