import Foundation

/// Whose first run is this?
///
/// `@AppStorage("hasOnboarded")` is one boolean for the whole PHONE, and the
/// account lifecycle never touched it. Cable install is the only way this app
/// gets onto a device today, so the phone having passed through somebody else's
/// hands is the normal case: the installer opens it once to check it, and the
/// stranger's sign-up lands them **straight on the feed**. They never see the
/// microphone primer, so listening is never started, so she hears nothing all
/// week — and the four-beat tour survives only as "Replay the welcome tour"
/// buried in Settings, which nobody knows to look for.
///
/// So the flag gets an owner. `hasOnboarded` still says WHETHER, and
/// `onboardedAccount` says WHOSE; a flag whose owner is not the account signing
/// in belongs to somebody else and is cleared.
///
/// -- Why this is not simply "clear it on sign out" ------------------------
///
/// Because sign-out is not where the account changes — sign-IN is. The
/// installer may never sign out at all (the stranger taps sign out themselves,
/// or the installer left the app on the feed), and on a phone that has been
/// wiped and re-signed-in by its own owner there is nothing to clear. Reading
/// the arriving account id answers both without guessing which of them
/// happened.
///
/// -- Why the pre-upgrade flag is adopted rather than cleared -------------
///
/// A phone updating to this build has `hasOnboarded = true` and no owner
/// recorded, because the owner column did not exist when it was written. That
/// state is unambiguous: the tour can only be completed from behind the
/// sign-in door (`AnticipyApp` routes to `AuthView` first), so the only account
/// that could have earned it is the one currently signed in. Stamping it is
/// therefore a fact, not a guess, and it costs the existing owner nothing.
/// Clearing it instead would make everybody already using the product redo
/// first run for a bug that was never theirs.
///
/// It cannot re-open the hole it closes: adoption only ever runs for the
/// account that is signed in AT THAT MOMENT, and the moment a different account
/// signs in, `arriving` has already cleared the flag.
enum FirstRunOwnership {

    /// THE TWO KEYS, DECLARED ONCE.
    ///
    /// `AnticipyApp` binds `@AppStorage` to these and the account lifecycle
    /// writes them. A second copy of the string is precisely how a rename
    /// leaves behind a clear that silently clears nothing — the accident
    /// `overnight/stranger_gate.py`'s `swift_string_behind` was written to
    /// catch, after moving this key into an `OnboardingKeys` constant turned
    /// leg 4 green while the value stayed one string for the whole phone.
    ///
    /// `flagKey` keeps its historical name deliberately: every phone already
    /// running the product has its tour recorded under it, and renaming the key
    /// would show first run again to every existing owner.
    static let flagKey = "hasOnboarded"
    static let ownerKey = "onboardedAccount"

    /// AND THE THIRD, for the two beats that now happen in front of the door.
    ///
    /// STORED PER DEVICE, GOVERNED PER ACCOUNT. It has to be stored on the
    /// handset because at the moment it is written there is no account to key
    /// it to — a person walking the introduction has not made one yet, which
    /// is the entire point of moving those beats. But an introduction is said
    /// to a PERSON, not to a handset, and a purely per-device flag would
    /// re-open the exact hole this file was written to close, on the two beats
    /// it just moved: the installer opens the app, walks welcome and
    /// how-it-works, sets the flag, and the real owner who signs up next is
    /// never introduced to the product at all.
    ///
    /// So it is cleared beside `flagKey`, on the same `.replay` decision, at
    /// all three sites — but NOT unconditionally, and that difference is the
    /// design rather than a slip. `arriving` answers `.replay` for a brand-new
    /// sign-up too (an empty owner id is not the id just minted), so an
    /// unconditional clear walks every new customer through the welcome
    /// typewriter and the how-it-works cards a second time, forty seconds after
    /// the first. `FirstRunRoute.introSurvivesReplay` draws the line, and where
    /// it answers true the two flags DO part company: the installer above keeps
    /// the introduction they spent, and the owner who signs up next does not
    /// get it. That gap is real and it is chosen; `FirstRunRoute` argues the
    /// trade in full beside the predicate, and `FirstRunRouteTests.swift` walks
    /// the case rather than leaving it as prose. What the tour flag still
    /// guarantees is the part that matters most: it is cleared either way, so
    /// the microphone primer is asked for, and "she hears nothing all week"
    /// cannot come back through here. `run_first_run_route_tests.sh` reads all
    /// three sites for the clear AND for the predicate rather than trusting
    /// the pairing.
    ///
    /// Declared here for the reason above: a second copy of the string is how
    /// a rename leaves behind a clear that silently clears nothing.
    static let introKey = "hasSeenIntro"

    /// What to do with the tour flag. `replay` means clear it — the person
    /// about to use this phone has not been shown first run.
    enum Decision: Equatable {
        /// Leave both values alone.
        case keep
        /// Clear `hasOnboarded` and the recorded owner: a different person.
        case replay
        /// Keep `hasOnboarded` and record this account as its owner.
        case adopt
    }

    /// An account has just authenticated. This is the ONE moment the person
    /// holding the phone can change, and it is reached by sign-up too —
    /// `signUp` ends in `signIn`.
    ///
    /// - Parameters:
    ///   - account: the id the auth boundary just returned. Never trusted to
    ///     be non-empty: a failed sign-in must not clear anybody's flag.
    ///   - onboardedAccount: whose tour flag is currently on this phone.
    ///   - hasOnboarded: whether there is a flag at all.
    static func arriving(account: String,
                         onboardedAccount: String,
                         hasOnboarded: Bool) -> Decision {
        guard !account.isEmpty else { return .keep }
        // Not "if hasOnboarded" — a stale owner id left behind a cleared flag
        // would then survive to be matched against later.
        if onboardedAccount == account { return .keep }
        return .replay
    }

    /// A signed-in launch, for the flag that was written before it had an
    /// owner. Never clears on its own — see the note above; the arriving path
    /// is what protects the stranger, and this one only stops the fix from
    /// charging the existing owner for it.
    static func resuming(account: String,
                         onboardedAccount: String,
                         hasOnboarded: Bool) -> Decision {
        guard !account.isEmpty, hasOnboarded else { return .keep }
        if onboardedAccount.isEmpty { return .adopt }
        if onboardedAccount == account { return .keep }
        // Belt and braces. Reaching here means a flag owned by somebody else
        // survived a sign-in, which is the bug this file exists for; the safe
        // reading of "I cannot tell whose this is" is to show the tour.
        return .replay
    }
}
