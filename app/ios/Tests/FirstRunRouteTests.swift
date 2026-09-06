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
                                     FirstRunBeat.pendant, FirstRunBeat.mic])

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
check("5. all six in-app beats, in their true order",
      five.route.segment?.pages == [FirstRunBeat.welcome, FirstRunBeat.tour,
                                    FirstRunBeat.name, FirstRunBeat.computer,
                                    FirstRunBeat.pendant, FirstRunBeat.mic])
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
// copied, so these read the shipped arithmetic. Six names, with the account
// counted first and the optional handoff last, is what the UI renders.
check("the track names seven beats, account first, microphone last",
      FirstRunTrack.beatNames == ["Your account", "Hello", "How I work",
                                  "Your name", "Your computer", "Your pendant",
                                  "May I listen?"])
check("and counts seven", FirstRunTrack.count == 7)

// THE INVARIANT. `step` is the absolute beat index in every segment and
// `pageCount` is always FirstRunBeat.count, so the name beat reads "4 of 6"
// whichever way the person arrived at it. That is true of both of them rather
// than a rounding error: the ordinal counts the beats BEHIND you. A fresh
// stranger has done Hello, How I work, Your account. A person whose tour
// replayed has done Your account, Hello, How I work. Three each.
let nameOrdinal = FirstRunTrack.ordinal(step: FirstRunBeat.name,
                                        pageCount: FirstRunBeat.count)
check("the name beat is the fourth of six", nameOrdinal == 4)
check("and it is named for what it asks",
      FirstRunTrack.name(step: FirstRunBeat.name,
                         pageCount: FirstRunBeat.count) == "Your name")
check("the computer handoff is fifth",
      FirstRunTrack.ordinal(step: FirstRunBeat.computer,
                            pageCount: FirstRunBeat.count) == 5)
check("the microphone closes the count at seven",
      FirstRunTrack.ordinal(step: FirstRunBeat.mic,
                            pageCount: FirstRunBeat.count) == 7)
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
check("and the pendant sits directly in front of it",
      FirstRunSegment.rest.pages.dropLast().last == FirstRunBeat.pendant)

// A beat added to the indices and not to OnboardingView's page builder
// would render a blank page on somebody's first run. There is no way to see a
// SwiftUI switch from here, so the tripwire is the count the switch was
// written against.
check("there are six in-app beats behind the seven names", FirstRunBeat.count == 6)
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

print(failures == 0 ? "all first-run route checks passed" : "\(failures) FAILED")
exit(failures == 0 ? 0 : 1)
