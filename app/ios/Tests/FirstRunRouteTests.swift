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
check("and no name beat either — nothing pre-auth saves to an account",
      !FirstRunSegment.intro.pages.contains(FirstRunBeat.name))
check("it carries exactly the welcome and the tour",
      FirstRunSegment.intro.pages == [FirstRunBeat.welcome, FirstRunBeat.tour])
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
// AND TOTALITY OVER THAT HALF OF THE TABLE, because the loop above can only
// speak about routes that carry a segment: once `.door` is the answer for more
// of the signed-out combinations, it falls silent on exactly the rows that
// changed. Signed out, the only two screens that ask nothing of an account are
// the introduction and the door, and every row must land on one of them.
check("every signed-out route is the introduction or the door",
      [true, false].allSatisfy { seen in
          [true, false].allSatisfy { onboarded in
              let route = FirstRunRoute.decide(hasSeenIntro: seen, isSignedIn: false,
                                               hasOnboarded: onboarded)
              return route == .intro || route == .door
          }
      })

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

    /// AnticipyApp.resumeSignedInAccount's flag reconciliation — the switch at
    /// the top of it, which runs synchronously before the first `await`.
    ///
    /// MODELLED BECAUSE THE UPGRADE IS ONLY REACHABLE THROUGH IT. Nothing a
    /// person can tap produces a handset carrying `hasOnboarded` and no
    /// `hasSeenIntro`; an app update produces it on every phone already using
    /// the product, and this is the only code that then runs.
    mutating func resumes() {
        guard !account.isEmpty else { return }
        switch FirstRunOwnership.resuming(account: account,
                                          onboardedAccount: onboardedAccount,
                                          hasOnboarded: hasOnboarded) {
        case .keep:
            break
        case .adopt:
            onboardedAccount = account
        case .replay:
            if !FirstRunRoute.introSurvivesReplay(onboardedAccount: onboardedAccount,
                                                  hasOnboarded: hasOnboarded) {
                hasSeenIntro = false
            }
            hasOnboarded = false
            onboardedAccount = account
        }
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
check("3. an interrupted first run resumes behind the door",
      three.route == .tour(.rest))
check("3. and resumes AT the name beat, not before it",
      three.route.segment?.firstStep == FirstRunBeat.name)
check("3. with no second trip through the door and no replayed introduction",
      three.route.segment?.pages == [FirstRunBeat.name, FirstRunBeat.computer,
                                     FirstRunBeat.pendant, FirstRunBeat.connect,
                                     FirstRunBeat.mic])

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
check("5. all seven in-app beats, in their true order",
      five.route.segment?.pages == [FirstRunBeat.welcome, FirstRunBeat.tour,
                                    FirstRunBeat.name, FirstRunBeat.computer,
                                    FirstRunBeat.pendant, FirstRunBeat.connect,
                                    FirstRunBeat.mic])
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

// 7. THE UPGRADE — the one state nobody can be walked INTO, because every
//    existing owner is already standing in it. `hasSeenIntro` is a new key, so
//    it is false on a handset that earned `hasOnboarded` on the build before
//    this one, and nothing writes it retroactively: the only two lines that
//    write it are walked by somebody doing THIS build's first run. The tour on
//    that build CONTAINED the introduction — all four beats sat behind the
//    door — so a false flag there is a hole in the record, not a fact about
//    the person.
var seven = Phone()
seven.hasOnboarded = true       // earned on an earlier build
seven.onboardedAccount = ""     // whose, was not recorded: the key did not exist
seven.account = personA
check("7. the update itself changes nothing — the owner opens on Home",
      seven.route == .home)
seven.resumes()
check("7. and the resuming launch adopts the tour flag without inventing an introduction",
      seven.onboardedAccount == personA && !seven.hasSeenIntro)
// THE REGRESSION THIS PINS. Read on `hasSeenIntro` alone, the signed-out
// branch sent this phone into the new-user introduction the moment its owner
// signed out: the logo animation, the "I'm Anticipy…" typewriter and the three
// how-it-works cards, with `skipLabel` returning nil on both pre-auth beats, in
// front of somebody who has used the product for weeks. It also contradicted
// the rule written three lines above it — signed out, the app cannot know who
// is holding the phone, so it shows the door.
seven.signsOut()
check("7. signing out shows an existing owner the door, not a first-run introduction",
      seven.route == .door)
seven.signsIn(personA)
check("7. and signing back in lands straight on Home", seven.route == .home)
check("7. with the introduction still never claimed on their behalf",
      !seven.hasSeenIntro)

// 7b. AND IT DOES NOT RE-OPEN THE HOLE FirstRunOwnership CLOSED. The same
//     upgraded handset, handed to somebody else: the arriving account is not
//     the recorded owner, so both flags clear together and person B is
//     introduced to a product they have never seen.
var sevenB = Phone()
sevenB.hasOnboarded = true
sevenB.account = personA
sevenB.resumes()
sevenB.signsOut()
sevenB.signsIn(personB)
check("7b. a second person on an upgraded phone still gets the whole tour",
      sevenB.route == .tour(.whole))
check("7b. the introduction included, because they have never had it",
      sevenB.route.segment?.pages.contains(FirstRunBeat.welcome) == true)

// THE SIGNED-OUT BRANCH, DIRECTLY, over the pair of flags that names it.
// A completed tour on this handset is proof the introduction was given on it:
// until the door moved, all four beats sat behind it and `hasOnboarded` could
// not be earned without walking them. That is the same adoption argument
// FirstRunOwnership makes about the pre-upgrade flag, not a second guess about
// who is holding the phone — and it is the only shape that can carry a tour
// without an introduction, because both `onFinished` sites write the two
// together and every clear clears them together.
check("a handset carrying a completed tour opens on the door once signed out",
      FirstRunRoute.decide(hasSeenIntro: false, isSignedIn: false,
                           hasOnboarded: true) == .door)
check("a handset carrying neither still opens on the introduction",
      FirstRunRoute.decide(hasSeenIntro: false, isSignedIn: false,
                           hasOnboarded: false) == .intro)
check("and no signed-out phone that already carries somebody's first run is introduced again",
      [true, false].allSatisfy { seen in
          FirstRunRoute.decide(hasSeenIntro: seen, isSignedIn: false,
                               hasOnboarded: true) == .door
      })

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
check("the pre-auth segment ends at the tour",
      FirstRunSegment.intro.lastStep == FirstRunBeat.tour)
check("which is NOT where the old predicate ended",
      FirstRunSegment.intro.lastStep != FirstRunBeat.count - 1)
check("the two post-door segments end at the microphone, asked last",
      FirstRunSegment.rest.lastStep == FirstRunBeat.mic
      && FirstRunSegment.whole.lastStep == FirstRunBeat.mic)
// Every segment's first and last page really are its own first and last, so
// `step` and `lastStep` seed to a page the person can be standing on.
for segment in [FirstRunSegment.intro, .rest, .whole] {
    check("\(segment) seeds from a page it carries",
          segment.pages.first == segment.firstStep
          && segment.pages.last == segment.lastStep)
}
check("and .rest seeds at 2 rather than 0, so `previous` is never a page nobody was on",
      FirstRunSegment.rest.firstStep == FirstRunBeat.name)

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
// copied, so these read the shipped arithmetic. Eight names, with the account
// counted first and the microphone last, is what the UI renders.
//
// A BEAT ADDED WITHOUT A NAME IS THE FAILURE THIS PINS. `offset` is
// `beatNames.count - pageCount`, so growing FirstRunBeat.count by one while
// this list stands still shifts every name back one place: the name beat would
// wear "How I work", and the setup step would wear "Your pendant". No crash,
// no compile error, just the whole track lying.
check("the track names eight beats, account first, microphone last",
      FirstRunTrack.beatNames == ["Your account", "Hello", "How I work",
                                  "Your name", "Your computer", "Your pendant",
                                  "Which apps?", "May I listen?"])
check("and counts eight", FirstRunTrack.count == 8)
check("one name for the door and one for every in-app beat",
      FirstRunTrack.count == FirstRunBeat.count + 1)

// THE INVARIANT. `step` is the absolute beat index in every segment and
// `pageCount` is always FirstRunBeat.count, so the name beat reads "4 of 6"
// whichever way the person arrived at it. That is true of both of them rather
// than a rounding error: the ordinal counts the beats BEHIND you. A fresh
// stranger has done Hello, How I work, Your account. A person whose tour
// replayed has done Your account, Hello, How I work. Three each.
let nameOrdinal = FirstRunTrack.ordinal(step: FirstRunBeat.name,
                                        pageCount: FirstRunBeat.count)
check("the name beat is the fourth of eight", nameOrdinal == 4)
check("and it is named for what it asks",
      FirstRunTrack.name(step: FirstRunBeat.name,
                         pageCount: FirstRunBeat.count) == "Your name")
check("the computer handoff is fifth",
      FirstRunTrack.ordinal(step: FirstRunBeat.computer,
                            pageCount: FirstRunBeat.count) == 5)
check("the setup step is seventh",
      FirstRunTrack.ordinal(step: FirstRunBeat.connect,
                            pageCount: FirstRunBeat.count) == 7)
check("and it is named for what it asks",
      FirstRunTrack.name(step: FirstRunBeat.connect,
                         pageCount: FirstRunBeat.count) == "Which apps?")
check("the microphone closes the count at eight",
      FirstRunTrack.ordinal(step: FirstRunBeat.mic,
                            pageCount: FirstRunBeat.count) == 8)
// THE TRAP THIS ARITHMETIC SETS, named so nobody walks into it. `pageCount` is
// how many pages the TRACK is counting over, not how many the current segment
// happens to carry. Handing it `segment.pages.count` looks like the obvious
// tidy-up and silently renames every beat: in `.rest` the name beat would
// wear the name of the last beat, with a number to match. Checked, because
// the failure is a wrong word on a screen rather than a crash.
check("a segment page count would misname the name beat",
      FirstRunTrack.name(step: FirstRunBeat.name,
                         pageCount: FirstRunSegment.rest.pages.count) == "Your pendant")
check("while the absolute count names it correctly",
      FirstRunTrack.name(step: FirstRunBeat.name,
                         pageCount: FirstRunBeat.count) == "Your name")

// WHY THE PRE-AUTH SEGMENT SHOWS NO NUMBER, derived rather than preferred.
// On the tour the person has ONE beat behind them, so the only honest
// ordinal is 1 — and the track's rule is that it never opens at 1. The other
// available number is the absolute one, which counts an account nobody has
// made. Both permitted numbers are forbidden, so no number is shown.
check("the absolute ordinal on the tour counts an account nobody has made",
      FirstRunTrack.ordinal(step: FirstRunBeat.tour,
                            pageCount: FirstRunBeat.count) == 3)
check("and the honest pre-auth ordinal would open the track at 1",
      FirstRunSegment.intro.pages.count == 2
      && FirstRunSegment.intro.pages.firstIndex(of: FirstRunBeat.tour) == 1)
check("so the pre-auth segment shows neither", !FirstRunSegment.intro.showsTrack)

// THE MICROPHONE STAYS LAST, and this is the leg that says so. `heard` pushes
// live before it queues, so the beat that asks iOS for the microphone may never
// be moved in front of anything — a beat added after it would run the mic while
// somebody was still being asked questions. The pendant beat (build 137) went
// in FRONT of it for exactly this reason.
for segment in [FirstRunSegment.rest, FirstRunSegment.whole] {
    check("the microphone is the last beat of \(segment)",
          segment.pages.last == FirstRunBeat.mic)
}
check("and the setup step sits directly in front of it",
      FirstRunSegment.rest.pages.dropLast().last == FirstRunBeat.connect)
check("with the pendant in front of that",
      FirstRunSegment.rest.pages.dropLast(2).last == FirstRunBeat.pendant)

// A beat added to the indices and not to OnboardingView's page builder
// would render a blank page on somebody's first run. There is no way to see a
// SwiftUI switch from here, so the tripwire is the count the switch was
// written against.
check("there are seven in-app beats behind the eight names", FirstRunBeat.count == 7)
check("and every page in every segment is one of them",
      [FirstRunSegment.intro, .rest, .whole].allSatisfy { segment in
          segment.pages.allSatisfy { (0 ..< FirstRunBeat.count).contains($0) }
      })

check("browser handoff follows the configured backend",
      ComputerSetupLinks.browser(baseURL: "http://127.0.0.1:8090")?.absoluteString
        == "http://127.0.0.1:8090/setup.html")
check("Mac handoff follows the configured backend without a double slash",
      ComputerSetupLinks.mac(baseURL: "https://example.test/")?.absoluteString
        == "https://example.test/mac.html")


// ============================================ THE STEP THAT WAS NEVER SHOWN
//
// "Which apps do you live in?" — the Connections spec's STEP 2, page 45.
//
// THE DEFECT THESE CHECKS EXIST FOR, stated plainly: `OnboardingConnectStep`
// and `ConnectOnboardingPolicy` were written on 2026-09-05, compiled into the
// target, tested with 154 checks — and had ZERO CALL SITES. `FirstRunBeat` was
// welcome/tour/name/computer/pendant/mic and none of them was it, so the step
// existed in the repository and did not exist for a single person. Every check
// below fails against that tree, which is the only reason to write them: a
// suite that passes before the change measures nothing.

// WHERE IT SITS. After the number and the pendant, before the microphone. The
// microphone stays last for the reason the header of this file gives, so the
// step goes in FRONT of it, exactly as the pendant beat did in build 137.
check("the setup step is a beat at all", FirstRunBeat.connect < FirstRunBeat.count)
check("it comes after the pendant", FirstRunBeat.connect > FirstRunBeat.pendant)
check("and before the microphone", FirstRunBeat.connect < FirstRunBeat.mic)

// EXACTLY ONCE, in every segment that carries it. A beat listed twice is a
// screen somebody meets, answers, and then meets again — and `nextPage` walks
// to the FIRST match, so the second copy is also a page with no way off it.
for segment in [FirstRunSegment.rest, FirstRunSegment.whole] {
    check("\(segment) carries the setup step exactly once",
          segment.pages.filter { $0 == FirstRunBeat.connect }.count == 1)
    check("\(segment) walks it directly after the pendant",
          segment.pages.firstIndex(of: FirstRunBeat.connect)
            == segment.pages.firstIndex(of: FirstRunBeat.pendant).map { $0 + 1 })
    check("\(segment) walks the microphone directly after it",
          segment.pages.firstIndex(of: FirstRunBeat.mic)
            == segment.pages.firstIndex(of: FirstRunBeat.connect).map { $0 + 1 })
}
// AND NEVER IN FRONT OF THE DOOR. The step reaches the catalog with an owner
// row id on every call; pre-auth there is no owner, and the whole feature is
// per-owner. It is also one more thing asked of somebody who has not yet been
// given anything, which is the failure the segment split exists to close.
check("the pre-auth segment carries no setup step",
      !FirstRunSegment.intro.pages.contains(FirstRunBeat.connect))
for seen in [true, false] {
    for onboarded in [true, false] {
        let route = FirstRunRoute.decide(hasSeenIntro: seen, isSignedIn: false,
                                         hasOnboarded: onboarded)
        check("no signed-out route reaches the setup step (\(seen), \(onboarded))",
              route.segment.map { !$0.pages.contains(FirstRunBeat.connect) } ?? true)
    }
}

// IT IS NEVER A SEGMENT'S FIRST OR LAST PAGE, in either mode. This is what
// lets `firstStep` and `lastStep` stay a plain function of `pages` while the
// beat is dropped underneath them. If it ever became the last page, `advance()`
// would compare `step < segment.lastStep` against a page that is not there and
// finish the walkthrough in the middle of it.
for segment in [FirstRunSegment.intro, .rest, .whole] {
    for showing in [true, false] {
        let walked = segment.pages(showingConnect: showing)
        check("\(segment) does not open on the setup step (showing: \(showing))",
              walked.first != FirstRunBeat.connect)
        check("\(segment) does not end on the setup step (showing: \(showing))",
              walked.last != FirstRunBeat.connect)
        check("\(segment)'s first page is unmoved by dropping it (showing: \(showing))",
              walked.first == segment.firstStep)
        check("\(segment)'s last page is unmoved by dropping it (showing: \(showing))",
              walked.last == segment.lastStep)
    }
}

// DERIVED, NOT WRITTEN TWICE. Dropping the beat removes that one page and
// nothing else, and leaves the order alone — the failure a second hand-written
// list produces is a `ForEach` and a `nextPage` that disagree about which page
// follows the pendant, which is a blank screen for whoever is standing there.
for segment in [FirstRunSegment.intro, .rest, .whole] {
    check("\(segment) shown is the whole list",
          segment.pages(showingConnect: true) == segment.pages)
    check("\(segment) hidden drops exactly the setup step",
          segment.pages(showingConnect: false)
            == segment.pages.filter { $0 != FirstRunBeat.connect })
    check("\(segment) hidden loses at most one page",
          segment.pages.count - segment.pages(showingConnect: false).count <= 1)
}

// ===================================================== WHO IS SHOWN IT
//
// The audience, over every combination of the three facts that decide it. The
// pair this is really about is `nil` versus `0`: a refused request that read as
// "already connected" would delete the spec's step 2 for that person with
// nothing on any screen to say so.
let day = 24.0 * 60 * 60
let noon = 1_757_000_000.0

check("nobody signed in: no owner to ask, and nothing to ask about",
      ConnectBeat.audience(ownerIsReal: false, liveConnections: 0,
                           skipSnoozeUntil: 0, now: noon) == .noOwner)
check("an owner with one connection has answered the question",
      ConnectBeat.audience(ownerIsReal: true, liveConnections: 1,
                           skipSnoozeUntil: 0, now: noon) == .alreadyConnected)
check("an owner with none has not",
      ConnectBeat.audience(ownerIsReal: true, liveConnections: 0,
                           skipSnoozeUntil: 0, now: noon) == .nothingConnected)
// THE ONE THAT MATTERS. A list that could not be read is NOT an empty list.
check("a list that could not be read is unknown, not empty",
      ConnectBeat.audience(ownerIsReal: true, liveConnections: nil,
                           skipSnoozeUntil: 0, now: noon) == .unknown)
check("and unknown is not the same answer as nothing connected",
      ConnectBeat.audience(ownerIsReal: true, liveConnections: nil,
                           skipSnoozeUntil: 0, now: noon)
        != ConnectBeat.audience(ownerIsReal: true, liveConnections: 0,
                                skipSnoozeUntil: 0, now: noon))
check("a live snooze is honoured",
      ConnectBeat.audience(ownerIsReal: true, liveConnections: 0,
                           skipSnoozeUntil: noon + day, now: noon) == .snoozed)
check("a snooze that has run out is not",
      ConnectBeat.audience(ownerIsReal: true, liveConnections: 0,
                           skipSnoozeUntil: noon - day, now: noon) == .nothingConnected)
// ORDER, STATED AS A TEST. A connection outranks a snooze; a snooze outranks an
// unreadable list, because it is a fact this phone wrote itself and a failed
// request is not evidence against it.
check("a connection outranks a live snooze",
      ConnectBeat.audience(ownerIsReal: true, liveConnections: 2,
                           skipSnoozeUntil: noon + day, now: noon) == .alreadyConnected)
check("a live snooze outranks an unreadable list",
      ConnectBeat.audience(ownerIsReal: true, liveConnections: nil,
                           skipSnoozeUntil: noon + day, now: noon) == .snoozed)
check("no owner outranks everything",
      ConnectBeat.audience(ownerIsReal: false, liveConnections: 3,
                           skipSnoozeUntil: noon + day, now: noon) == .noOwner)
check("an unreadable clock is unknown rather than a guess",
      ConnectBeat.audience(ownerIsReal: true, liveConnections: 0,
                           skipSnoozeUntil: 0, now: .nan) == .unknown)
check("a stored snooze that is not a number is ignored, and the step shows",
      ConnectBeat.audience(ownerIsReal: true, liveConnections: 0,
                           skipSnoozeUntil: .nan, now: noon) == .nothingConnected)

// THE STEP IS NOT SHOWN TO SOMEBODY WHO ALREADY CONNECTED SOMETHING.
check("somebody who already connected something is not asked",
      !ConnectBeat.isShown(to: .alreadyConnected))
check("nor is somebody inside the quiet they earned", !ConnectBeat.isShown(to: .snoozed))
check("nor is a phone with no owner on it", !ConnectBeat.isShown(to: .noOwner))
// THE CONTROL, and the polarity. This is a CEILING — "is showing it positively
// unnecessary?" — so a missing verdict may not fence, or the fence becomes a
// wall and the step disappears again the first time a request fails.
check("CONTROL: somebody with nothing connected IS asked",
      ConnectBeat.isShown(to: .nothingConnected))
check("CONTROL: and so is somebody whose list could not be read",
      ConnectBeat.isShown(to: .unknown))
// TOTALITY. Every audience lands on one side, so a sixth state added later
// cannot arrive with no answer.
for audience in [ConnectBeat.Audience.noOwner, .alreadyConnected, .snoozed,
                 .nothingConnected, .unknown] {
    let shown = ConnectBeat.isShown(to: audience)
    check("\(audience) is decided one way or the other", shown || !shown)
}

// AND THE PAGE LIST FOLLOWS IT. The two halves joined up: an audience that is
// not shown the step is an audience whose walk does not contain it, and the
// walk is otherwise identical.
for audience in [ConnectBeat.Audience.noOwner, .alreadyConnected, .snoozed,
                 .nothingConnected, .unknown] {
    let walked = FirstRunSegment.rest.pages(showingConnect: ConnectBeat.isShown(to: audience))
    check("\(audience) sees the step exactly when it is shown to them",
          walked.contains(FirstRunBeat.connect) == ConnectBeat.isShown(to: audience))
    check("\(audience) still reaches the microphone", walked.last == FirstRunBeat.mic)
    check("\(audience) still starts on the name beat", walked.first == FirstRunBeat.name)
}

// ===================================================== THE PAGE UNDER A THUMB
//
// The connections list is read over the network, so its answer can land at any
// moment. Adopting one while somebody is STANDING on the beat removes the page
// from under them: the `ForEach` renders nothing and there is no way forward.
check("a late answer is adopted while the person is still ahead of the beat",
      ConnectBeat.mayAdoptAudience(standingOn: FirstRunBeat.name)
        && ConnectBeat.mayAdoptAudience(standingOn: FirstRunBeat.pendant))
check("and refused the moment they are standing on it",
      !ConnectBeat.mayAdoptAudience(standingOn: FirstRunBeat.connect))
check("and refused after it",
      !ConnectBeat.mayAdoptAudience(standingOn: FirstRunBeat.mic))
check("every beat in front of it may still adopt one",
      (0 ..< FirstRunBeat.connect).allSatisfy { ConnectBeat.mayAdoptAudience(standingOn: $0) })
check("and no beat from it onward may",
      (FirstRunBeat.connect ..< FirstRunBeat.count)
        .allSatisfy { !ConnectBeat.mayAdoptAudience(standingOn: $0) })

// ===================================================== WHOSE QUIET IT IS
//
// A snooze belongs to a PERSON and this store is per DEVICE — the same shape as
// `hasSeenIntro`, with the same trap. Without the owner beside it, the second
// person on a handed-on phone inherits the first one's quiet and is never shown
// the step at all.
let alice = "aaaaaaaaaaaaaaa"
let bob = "bbbbbbbbbbbbbbb"
check("this owner's own snooze stands",
      ConnectBeat.snoozeStanding(storedOwner: alice, storedUntil: noon + day,
                                 owner: alice) == noon + day)
check("somebody else's does not",
      ConnectBeat.snoozeStanding(storedOwner: alice, storedUntil: noon + day,
                                 owner: bob) == 0)
check("and a phone with nobody signed in honours none of it",
      ConnectBeat.snoozeStanding(storedOwner: alice, storedUntil: noon + day,
                                 owner: "") == 0)
check("a stored instant that is not a number is not a snooze",
      ConnectBeat.snoozeStanding(storedOwner: alice, storedUntil: .nan,
                                 owner: alice) == 0)
check("an untouched store is no snooze at all",
      ConnectBeat.snoozeStanding(storedOwner: "", storedUntil: 0, owner: alice) == 0)
// END TO END: the second person is shown the step the first one skipped.
check("the second person on a handed-on phone is still asked",
      ConnectBeat.isShown(to: ConnectBeat.audience(
        ownerIsReal: true,
        liveConnections: 0,
        skipSnoozeUntil: ConnectBeat.snoozeStanding(storedOwner: alice,
                                                    storedUntil: noon + day,
                                                    owner: bob),
        now: noon)))
check("CONTROL: and the person who skipped it is not",
      !ConnectBeat.isShown(to: ConnectBeat.audience(
        ownerIsReal: true,
        liveConnections: 0,
        skipSnoozeUntil: ConnectBeat.snoozeStanding(storedOwner: alice,
                                                    storedUntil: noon + day,
                                                    owner: alice),
        now: noon)))

// THE ARITHMETIC, over a count of days it is HANDED. The number itself is the
// contract's, mirrored in ConnectOnboardingPolicy.skipMeans and pinned against
// it by ConnectOnboardingPolicyTests — this file cannot see that type and must
// not restate its number.
check("a snooze is that many days ahead of now",
      ConnectBeat.snoozeUntil(now: noon, days: 7) == noon + 7 * day)
check("zero days is no quiet at all",
      ConnectBeat.snoozeUntil(now: noon, days: 0) == noon)
check("and a fresh snooze always outlives the instant it was written",
      ConnectBeat.snoozeUntil(now: noon, days: 1) > noon)

print(failures == 0 ? "all first-run route checks passed" : "\(failures) FAILED")
exit(failures == 0 ? 0 : 1)
