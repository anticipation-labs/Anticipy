// Which screen a launch opens on, walked through every state a person can
// actually be in.
//
// The two beats that ask for nothing — the introduction, and how she works —
// now happen in FRONT of the sign-in door, because a stranger used to type an
// email, a password AND a phone number before the product had produced one
// single thing of its own. Splitting a four-page TabView across an auth
// boundary makes three states real that nobody can reach by tapping through
// the app: force-quitting between the second beat and the door, signing out
// and handing the phone to somebody else, and reinstalling onto an account
// that already exists. Those are the ones this file is for.
//
// Run: sh app/ios/Tests/run_first_run_route_tests.sh
import Foundation

var failures = 0
func check(_ name: String, _ ok: Bool) {
    print("\(ok ? "PASS" : "FAIL"): \(name)")
    if !ok { failures += 1 }
}

// ===================================================== THE HARD LINE
//
// The microphone stays behind the door. `heard` attempts a LIVE PUSH before it
// ever queues and only `flushUnsent` is gated on an account, so a primer in
// `.intro` would post a stranger's room to the server — stopped only by the
// backend's own guard hook, which is a safety property nobody wrote down on
// the client. This is the first check in the file on purpose.
check("the pre-auth segment carries no microphone beat",
      !FirstRunSegment.intro.pages.contains(FirstRunBeat.mic))
check("and no number beat either — nothing pre-auth saves to an account",
      !FirstRunSegment.intro.pages.contains(FirstRunBeat.phone))
check("it carries exactly the introduction and how-it-works",
      FirstRunSegment.intro.pages == [FirstRunBeat.welcome, FirstRunBeat.howItWorks])
// And no route the app can compute puts them there.
for seen in [true, false] {
    for signedIn in [true, false] {
        for onboarded in [true, false] {
            let route = FirstRunRoute.decide(hasSeenIntro: seen,
                                             isSignedIn: signedIn,
                                             hasOnboarded: onboarded)
            if let segment = route.segment, !signedIn {
                check("no signed-out route reaches the microphone (\(seen), \(onboarded))",
                      !segment.pages.contains(FirstRunBeat.mic))
            }
        }
    }
}

// ===================================================== A PHONE
//
// The three durable facts the routing reads, and the account lifecycle that
// writes them. It exists because the defect this file caught did not live
// inside either policy — it lived BETWEEN them: `FirstRunOwnership.arriving`
// answers `.replay` for a brand-new sign-up as well as for a second person on
// a handed-on phone, so a rule phrased as "clear the intro flag wherever the
// tour flag is cleared" walks every new customer through the welcome
// typewriter twice. Nothing that tests the two policies separately can see
// that. These walk them together.
struct Phone {
    var hasSeenIntro = false
    var hasOnboarded = false
    var onboardedAccount = ""
    var account = ""

    var route: FirstRunRoute {
        FirstRunRoute.decide(hasSeenIntro: hasSeenIntro,
                             isSignedIn: !account.isEmpty,
                             hasOnboarded: hasOnboarded)
    }

    /// Continue, on the second pre-auth beat. OnboardingView.advance() writes
    /// the durable fact in its terminal branch, before anything decorative.
    mutating func clearsTheIntroduction() { hasSeenIntro = true }

    /// Continue, on the last beat of a tour. AnticipyApp's onFinished writes
    /// both flags — the tour AND the introduction, because a person who walked
    /// all four beats has had both.
    mutating func finishesTheTour() {
        hasSeenIntro = true
        hasOnboarded = true
    }

    /// AnticipyApp.signIn, all three arms, in the order the real one writes
    /// them. Reached by sign-UP too: signUp ends in signIn.
    mutating func signsIn(_ id: String) {
        switch FirstRunOwnership.arriving(account: id,
                                          onboardedAccount: onboardedAccount,
                                          hasOnboarded: hasOnboarded) {
        case .keep:
            break
        case .adopt:
            onboardedAccount = id
        case .replay:
            if !FirstRunRoute.introSurvivesReplay(onboardedAccount: onboardedAccount,
                                                  hasOnboarded: hasOnboarded) {
                hasSeenIntro = false
            }
            hasOnboarded = false
            onboardedAccount = id
        }
        account = id
    }

    /// signOut clears the credentials and the five owner mirrors and touches
    /// NEITHER flag: sign-out is not where the person changes, sign-in is.
    mutating func signsOut() { account = "" }
}

let personA = "acc_a_first"
let personB = "acc_b_second"

// ===================================================== THE SIX STATES

// 1. THE COMMONEST PATH IN THE PRODUCT, and the one the first draft of this
//    change broke. Fresh install, walk the introduction, make an account.
var one = Phone()
check("1. a fresh install opens on the introduction", one.route == .intro)
one.clearsTheIntroduction()
check("1. clearing the introduction opens the door", one.route == .door)
one.signsIn(personA)
check("1. and the account they make resumes at the microphone",
      one.route == .tour(.rest))
// Said twice because it is the whole point: `arriving` returns .replay here,
// on an empty owner id, exactly as it does for a stranger on a handed-on
// phone. If the intro flag is cleared on that arm unconditionally, this reads
// .tour(.whole) and the person watches the welcome typewriter and the three
// how-it-works cards a second time, forty seconds after the first.
check("1. the introduction is NOT replayed straight after the sign-up",
      one.hasSeenIntro && one.route.segment?.pages.contains(FirstRunBeat.welcome) == false)
one.finishesTheTour()
check("1. and finishing lands them on Home", one.route == .home)

// 2. THE STATE THE FLAG EXISTS FOR. Saw the introduction, force-quit before
//    making an account. Nothing about a relaunch changes a durable flag.
var two = Phone()
two.clearsTheIntroduction()
check("2. a force-quit between the introduction and the door does not replay it",
      two.route == .door)
// Sub-case: quit ON the welcome beat, before how-it-works was cleared. Chosen
// granularity — somebody who force-quits on the logo screen has been told
// nothing, so replaying two beats costs them nothing and skipping them robs.
let two2 = Phone()
check("2. but a force-quit on the logo screen still gets the introduction",
      two2.route == .intro)

// 3. Saw the introduction, made an account, quit before the microphone.
//    authToken and accountID are @AppStorage, so isSignedIn survives the quit.
var three = Phone()
three.clearsTheIntroduction()
three.signsIn(personA)
check("3. an interrupted first run resumes at the microphone",
      three.route == .tour(.rest))
check("3. and resumes AT it, not before it",
      three.route.segment?.firstStep == FirstRunBeat.mic)
check("3. with no second trip through the door and no replayed introduction",
      three.route.segment?.pages == [FirstRunBeat.mic, FirstRunBeat.phone])

// 4. Signed out, then reopened by the SAME person.
var four = Phone()
four.clearsTheIntroduction()
four.signsIn(personA)
four.finishesTheTour()
four.signsOut()
check("4. a signed-out phone opens on the door, not on the introduction",
      four.route == .door)
check("4. because before somebody authenticates the app cannot know who is holding it",
      four.hasSeenIntro)
four.signsIn(personA)
check("4. and signing back in lands straight on Home", four.route == .home)
check("4. with no tour and no introduction", four.hasOnboarded && four.hasSeenIntro)

// 5. THE STATE THAT HAS BITTEN THIS REPO. Signed out, and a DIFFERENT person
//    signs in on the same handset.
var five = Phone()
five.clearsTheIntroduction()
five.signsIn(personA)
five.finishesTheTour()
five.signsOut()
five.signsIn(personB)
check("5. a second person on a handed-on phone gets the whole tour",
      five.route == .tour(.whole))
check("5. all four beats, in their true order",
      five.route.segment?.pages == [FirstRunBeat.welcome, FirstRunBeat.howItWorks,
                                    FirstRunBeat.mic, FirstRunBeat.phone])
check("5. and both flags were cleared together, so neither can drift",
      !five.hasSeenIntro == !five.hasOnboarded)

// 5b. The same shape where the first person ABANDONED their tour part-way.
//     hasOnboarded is false, but an owner id is recorded, and that is the fact
//     that says somebody else's first run is already on this phone.
var fiveB = Phone()
fiveB.clearsTheIntroduction()
fiveB.signsIn(personA)
fiveB.signsOut()
fiveB.signsIn(personB)
check("5b. a phone abandoned mid-tour still introduces itself to the next person",
      fiveB.route == .tour(.whole))

// 6. Reinstalled, signing into an account that already exists. Defaults are
//    fresh, so the introduction plays once, then the door — and the mirrors
//    went with the reinstall, so `arriving` sees "" and replays the tour.
var six = Phone()
check("6. a reinstall opens on the introduction", six.route == .intro)
six.clearsTheIntroduction()
check("6. then the door", six.route == .door)
six.signsIn(personA)
check("6. and the tour resumes at the microphone, the introduction already spent",
      six.route == .tour(.rest))

// THE GAP, WRITTEN DOWN RATHER THAN LEFT TO BE DISCOVERED. An installer who
// taps through the two pre-auth beats and never signs in is indistinguishable,
// with every durable fact this device has, from state 1 — so the owner who
// signs up next is not shown those two beats. What that costs is bounded and
// it is checked here: they still reach the microphone primer, because the tour
// flag is cleared on the same decision either way, so "she hears nothing all
// week" cannot come back through this door.
var installed = Phone()
installed.clearsTheIntroduction()
installed.signsIn(personB)
check("the installer gap costs the owner the two explanatory beats",
      installed.route == .tour(.rest))
check("but never the microphone primer, which is the failure that matters",
      installed.route.segment?.pages.contains(FirstRunBeat.mic) == true)

// AND THE PREDICATE THAT DRAWS THAT LINE, directly.
check("an introduction survives a replay on a phone carrying nobody's first run",
      FirstRunRoute.introSurvivesReplay(onboardedAccount: "", hasOnboarded: false))
check("it does not survive one where somebody's tour is recorded",
      !FirstRunRoute.introSurvivesReplay(onboardedAccount: personA, hasOnboarded: true))
check("nor one where somebody signed in and abandoned the tour",
      !FirstRunRoute.introSurvivesReplay(onboardedAccount: personA, hasOnboarded: false))
check("nor one carrying a tour flag with no owner recorded — the pre-accounts phone",
      !FirstRunRoute.introSurvivesReplay(onboardedAccount: "", hasOnboarded: true))

// The decision is total, and Home wins once the tour is done — including over
// an intro flag that a reinstall or a replay left false.
check("an onboarded account reaches Home whatever the intro flag says",
      FirstRunRoute.decide(hasSeenIntro: false, isSignedIn: true,
                           hasOnboarded: true) == .home
      && FirstRunRoute.decide(hasSeenIntro: true, isSignedIn: true,
                              hasOnboarded: true) == .home)

// ===================================================== THE DEAD END
//
// advance() used to end `if step < Step.count - 1 { step += 1 } else { finish() }`.
// Step.count - 1 is 3, and how-it-works is 1, so in the pre-auth segment
// Continue walked to a page tagged 2 that the segment does not carry: a blank
// screen, in front of the door, with no way forward. That is precisely what a
// "routing only, ~10 lines" version of this change produces, so the number
// advance() now compares against is checked rather than trusted.
check("the pre-auth segment ends at how-it-works",
      FirstRunSegment.intro.lastStep == FirstRunBeat.howItWorks)
check("which is NOT where the old predicate ended",
      FirstRunSegment.intro.lastStep != FirstRunBeat.count - 1)
check("the two post-door segments still end at the number beat",
      FirstRunSegment.rest.lastStep == FirstRunBeat.phone
      && FirstRunSegment.whole.lastStep == FirstRunBeat.phone)
// Every segment's first and last page really are its own first and last, so
// `step` and `lastStep` seed to a page the person can be standing on.
for segment in [FirstRunSegment.intro, .rest, .whole] {
    check("\(segment) seeds from a page it carries",
          segment.pages.first == segment.firstStep
          && segment.pages.last == segment.lastStep)
}
check("and .rest seeds at 2 rather than 0, so `previous` is never a page nobody was on",
      FirstRunSegment.rest.firstStep == FirstRunBeat.mic)

// ===================================================== ENDINGS AND TRACKS
//
// Clearing the last pre-auth page means the DOOR is next, not that first run
// is over. finish() guards on this before it may raise the voice-enrolment
// offer — a stranger cannot record a voice for an account that does not exist.
check("the pre-auth segment does not end the tour", !FirstRunSegment.intro.endsTheTour)
check("both post-door segments do",
      FirstRunSegment.rest.endsTheTour && FirstRunSegment.whole.endsTheTour)
check("and the pre-auth segment shows no progress track",
      !FirstRunSegment.intro.showsTrack)
check("while both post-door segments do",
      FirstRunSegment.rest.showsTrack && FirstRunSegment.whole.showsTrack)

// `decide` never returns `.tour(.intro)`: the pre-auth beats are reached
// through `.intro`, which is the case that does not end the tour. If it ever
// did, a stranger would be handed a segment whose finish() writes hasOnboarded.
for seen in [true, false] {
    for signedIn in [true, false] {
        for onboarded in [true, false] {
            let route = FirstRunRoute.decide(hasSeenIntro: seen, isSignedIn: signedIn,
                                             hasOnboarded: onboarded)
            if case .tour(let segment) = route {
                check("no tour route carries the pre-auth segment (\(seen), \(signedIn), \(onboarded))",
                      segment != .intro)
            }
        }
    }
}
check("the route that renders the introduction reports the segment that carries it",
      FirstRunRoute.intro.segment == .intro)
check("and the two that render no walkthrough report none",
      FirstRunRoute.door.segment == nil && FirstRunRoute.home.segment == nil)

// ===================================================== WHAT THE TRACK COUNTS
//
// FirstRunTrack is LIFTED out of OnboardingView.swift by the runner, never
// copied, so these read the shipped arithmetic. Five names, with the account
// counted first, is what the previous fix shipped and this one must not undo.
check("the track still names five beats, account first",
      FirstRunTrack.beatNames == ["Your account", "Hello", "How I work",
                                  "May I listen?", "Where to reach you"])
check("and still counts five", FirstRunTrack.count == 5)

// THE INVARIANT. `step` is the absolute beat index in every segment and
// `pageCount` is always FirstRunBeat.count, so the microphone beat reads
// "4 of 5" whichever way the person arrived at it. That is true of both of
// them rather than a rounding error: the ordinal counts the beats BEHIND you.
// A fresh stranger has done Hello, How I work, Your account. A person whose
// tour replayed has done Your account, Hello, How I work. Three each.
let micOrdinal = FirstRunTrack.ordinal(step: FirstRunBeat.mic,
                                       pageCount: FirstRunBeat.count)
check("the microphone beat is the fourth of five", micOrdinal == 4)
check("and it is named for what it asks",
      FirstRunTrack.name(step: FirstRunBeat.mic,
                         pageCount: FirstRunBeat.count) == "May I listen?")
check("the number beat closes the count at five",
      FirstRunTrack.ordinal(step: FirstRunBeat.phone,
                            pageCount: FirstRunBeat.count) == 5)
// THE TRAP THIS ARITHMETIC SETS, named so nobody walks into it. `pageCount` is
// how many pages the TRACK is counting over, not how many the current segment
// happens to carry. Handing it `segment.pages.count` looks like the obvious
// tidy-up and silently renames every beat: in `.rest` the microphone would
// wear the name of the beat after it, with a number to match. Checked, because
// the failure is a wrong word on a screen rather than a crash.
check("a segment page count would misname the microphone beat",
      FirstRunTrack.name(step: FirstRunBeat.mic,
                         pageCount: FirstRunSegment.rest.pages.count) == "Where to reach you")
check("while the absolute count names it correctly",
      FirstRunTrack.name(step: FirstRunBeat.mic,
                         pageCount: FirstRunBeat.count) == "May I listen?")

// WHY THE PRE-AUTH SEGMENT SHOWS NO NUMBER, derived rather than preferred.
// On how-it-works the person has ONE beat behind them, so the only honest
// ordinal is 1 — and the track's rule is that it never opens at 1. The other
// available number is the absolute one, which counts an account nobody has
// made. Both permitted numbers are forbidden, so no number is shown.
check("the absolute ordinal on how-it-works counts an account nobody has made",
      FirstRunTrack.ordinal(step: FirstRunBeat.howItWorks,
                            pageCount: FirstRunBeat.count) == 3)
check("and the honest pre-auth ordinal would open the track at 1",
      FirstRunSegment.intro.pages.count == 2
      && FirstRunSegment.intro.pages.firstIndex(of: FirstRunBeat.howItWorks) == 1)
check("so the pre-auth segment shows neither", !FirstRunSegment.intro.showsTrack)

// A fifth beat added to the indices and not to OnboardingView's page builder
// would render a blank page on somebody's first run. There is no way to see a
// SwiftUI switch from here, so the tripwire is the count the switch was
// written against.
check("there are still four beats behind the five names", FirstRunBeat.count == 4)
check("and every page in every segment is one of them",
      [FirstRunSegment.intro, .rest, .whole].allSatisfy { segment in
          segment.pages.allSatisfy { (0 ..< FirstRunBeat.count).contains($0) }
      })

print(failures == 0 ? "all first-run route checks passed" : "\(failures) FAILED")
exit(failures == 0 ? 0 : 1)
