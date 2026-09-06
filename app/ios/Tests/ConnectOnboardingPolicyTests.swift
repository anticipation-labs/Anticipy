// THE SETUP STEP AS FIRST RUN ACTUALLY WALKS IT.
//
//   sh app/ios/Tests/run_connect_onboarding_step_tests.sh
//
// ConnectOnboardingTests.swift next door runs the DECISION — what the card
// holds, what a skip costs, what the two channels render. It passed 154 checks
// on 2026-09-05 over a screen that had ZERO CALL SITES: `FirstRunBeat` was
// welcome/tour/name/computer/pendant/mic and none of them was "which apps do
// you live in?", so every one of those checks was true of something no person
// could reach. This file is the seam between the two halves — the flow's own
// use of the policy — and every check in it fails against that tree.
//
// Two real sources are compiled together and that IS the measurement:
// `ConnectOnboardingPolicy`, which owns what a skip MEANS, and `FirstRunRoute`,
// which owns when the beat is walked and does the snooze arithmetic. They
// cannot import each other — the route is compiled on its own by
// run_first_run_route_tests.sh — so the only thing stopping them drifting is a
// suite that holds both at once. The unit gap is deliberate and is part of what
// is measured: the policy keeps milliseconds, the phone's store keeps seconds,
// and `agreesWithSkip` spans it by comparing FACTS rather than rows.
import Foundation

typealias P = ConnectOnboardingPolicy

var failures = 0
func check(_ name: String, _ ok: Bool) {
    print("\(ok ? "PASS" : "FAIL"): \(name)")
    if !ok { failures += 1 }
}

let day = 24.0 * 60 * 60
/// Seconds, as `Date.timeIntervalSince1970` and `@AppStorage` carry them.
let nowSeconds = 1_757_000_000.0
/// The same instant in the policy's units.
let nowMillis = nowSeconds * 1000

guard let me = P.OwnerID("aaaaaaaaaaaaaaa") else {
    print("FAIL: the suite could not build an owner id at all")
    exit(1)
}

// ===================================================== 1. THE SKIP THE FLOW MAKES
//
// `OnboardingView.recordConnectSkip()` makes exactly this call: no nudge rows,
// because no route on this phone serves them, and the clock in milliseconds
// because that is the policy's unit. What comes back is the seven days and the
// promise that nothing else moved.
//
// A SKIP IS A SEVEN-DAY SOFT SNOOZE, NOT A DECLINE — page 41. The other
// implementation of this same event, `ConnectionsPolicy.recordDecline`, stamps
// `declined` at level 1, and level 1 raises the server's own threshold to 0.8
// against a STRICT comparison: a shrug at the setup card would silence
// `repeated_use` (0.6), `onboarding` (0.7) and `in_task` (0.8) for good. That
// is not a snooze with a label on it; it is the end of the conversation.
guard case .snoozed(let flowSkip) = P.skipOutcome(offered: [], signedInOwner: me, at: nowMillis) else {
    print("FAIL: the call OnboardingView makes on Skip does not snooze at all.")
    print("      Skip is the only way off the setup card for somebody who does")
    print("      not want it, and a Skip that records nothing is a card that")
    print("      comes back tomorrow.")
    exit(1)
}
check("the flow's own Skip call snoozes rather than refusing", flowSkip.snoozeDays > 0)
check("it moves no decline level", !flowSkip.declineLevelChanged)
check("and it writes no rows, because this phone holds none", flowSkip.records.isEmpty)

// THE NUMBER IS THE CONTRACT'S, and it is not written down twice. `ConnectBeat`
// takes the count of days and does arithmetic; the count comes from here.
let until = ConnectBeat.snoozeUntil(now: nowSeconds, days: flowSkip.snoozeDays)
check("the stored instant is the policy's own number of days ahead",
      until == nowSeconds + Double(P.Contract.onboardingSkipSnoozeDays) * day)
check("which is the seven days skipMeans describes",
      flowSkip.snoozeDays == P.skipMeans.snoozeDays)

// THE UNIT GAP, SPANNED THE WAY THE POLICY SAYS TO SPAN IT. The store keeps
// seconds and the policy keeps milliseconds, so what is compared is the FACT —
// how many days of quiet did this transition buy — and not a row.
let daysStored = (until - nowSeconds) / day
check("what the phone stores means what the policy meant",
      P.agreesWithSkip(levelBefore: 0, levelAfter: 0,
                       declinedAfter: false, snoozeDaysAfter: daysStored))
// AND THE MUTANTS. Each of these is a real, tempting way to write this line;
// each is caught.
check("storing the ladder's fourteen days would not agree",
      !P.agreesWithSkip(levelBefore: 0, levelAfter: 0, declinedAfter: false,
                        snoozeDaysAfter: (ConnectBeat.snoozeUntil(now: nowSeconds, days: 14)
                                          - nowSeconds) / day))
check("recording a decline would not agree",
      !P.agreesWithSkip(levelBefore: 0, levelAfter: 1,
                        declinedAfter: true, snoozeDaysAfter: daysStored))
check("leaving the row saying declined would not agree",
      !P.agreesWithSkip(levelBefore: 0, levelAfter: 0,
                        declinedAfter: true, snoozeDaysAfter: daysStored))
check("and neither would writing no snooze at all",
      !P.agreesWithSkip(levelBefore: 0, levelAfter: 0, declinedAfter: false,
                        snoozeDaysAfter: (ConnectBeat.snoozeUntil(now: nowSeconds, days: 0)
                                          - nowSeconds) / day))

// THE MISTAKE THE ARITHMETIC ITSELF COULD MAKE, and it is the tempting one:
// `skipOutcome` is handed a millisecond clock, so the obvious thing is to pass
// that same clock to `snoozeUntil` and store what comes back. The store and the
// audience read SECONDS, and the two are a factor of a thousand apart — the
// snooze would then run out in the year 57,000 and the setup step would never be
// offered to that person again. It is checked twice, once as a disagreement
// about the fact and once as the consequence on a real phone.
let wrongUnits = ConnectBeat.snoozeUntil(now: nowMillis, days: flowSkip.snoozeDays)
check("a snooze written from the policy's clock into the phone's store is caught",
      !P.agreesWithSkip(levelBefore: 0, levelAfter: 0, declinedAfter: false,
                        snoozeDaysAfter: (wrongUnits - nowSeconds) / day))
check("and it would silence the step for the rest of this owner's life",
      ConnectBeat.audience(ownerIsReal: true, liveConnections: 0,
                           skipSnoozeUntil: wrongUnits,
                           now: nowSeconds + 3650 * day) == .snoozed)
check("CONTROL: the units the flow actually stores run out on time",
      ConnectBeat.audience(ownerIsReal: true, liveConnections: 0,
                           skipSnoozeUntil: until,
                           now: nowSeconds + 3650 * day) == .nothingConnected)

// ===================================================== 2. SKIP IS REACHABLE
//
// Page 41: Skip is ALWAYS VISIBLE, in every state this step can be in. The
// runner reads the view's source for a branch in front of the control; this
// reads the DECISION, over every state the card can be handed, because a
// `skipLabel` the policy declines to fill is a button with no words on it.
let states: [(String, P.Detection)] = [
    ("nothing detected", P.detected(from: [], catalog: [], signedInOwner: me, at: nowMillis)),
    ("detection refused", P.detected(from: [], catalog: [], signedInOwner: nil, at: nowMillis)),
    ("an unreadable row", .refused(.unreadableRow)),
    ("somebody else's row", .refused(.foreignRow)),
]
for (what, detection) in states {
    let card = P.step(for: detection, chosen: [])
    check("Skip is on the card when \(what)", !card.skipLabel.isEmpty)
    check("and the card still says what it is when \(what)", !card.title.isEmpty)
    check("and Connect is dark with nothing ticked when \(what)", !card.connectEnabled)
}
// EVERY refusal the policy can produce, so a case added later cannot arrive
// with a card that has no way off it.
for why in P.Refusal.allCases {
    check("Skip survives a \(why.rawValue) refusal",
          !P.step(for: .refused(why), chosen: []).skipLabel.isEmpty)
}

// ===================================================== 3. THE CARD THE FLOW DRAWS
//
// `OnboardingView.connectDetection` ranks over NOTHING, and says so honestly:
// `app_usage_signals` has zero rows on production and `ConnectedAppsClient`
// serves no route that could read one. That is "we looked and found none",
// which is true, and it is deliberately not `.refused` — which would print "I
// could not work out which apps you use" to every person forever over a table
// that is simply empty.
let flowDetection = P.detected(from: [], catalog: [], signedInOwner: me, at: nowMillis)
check("with no signals the card is empty rather than broken",
      flowDetection == .apps([]))
check("so nothing arrives pre-ticked over no evidence",
      P.initialSelection(flowDetection).isEmpty)
let flowCard = P.step(for: flowDetection, chosen: [])
check("and the empty card is not a failure state", flowCard.refusal == nil)
check("it carries the search box that is the whole of it",
      !flowCard.searchPlaceholder.isEmpty)
check("and the footnote that says this is optional", !flowCard.footnote.isEmpty)

// THE CONTROL. The empty card is a fact about today's data, not a rule baked
// into the flow: hand the same call a signal and a catalog entry and the app
// arrives on the card, ticked. If this ever stops passing, the step has been
// wired to something that cannot pre-select at all, and page 45's first
// sentence is unreachable rather than merely unfed.
let evidence = P.SignalRow(owner: me, toolkit: "fictional-desk",
                           source: .said, lastSeenAt: nowMillis - day * 1000)
let catalogue = [P.CatalogEntry(slug: "fictional-desk", name: "Fictional Desk")]
let fedDetection = P.detected(from: [evidence], catalog: catalogue,
                              signedInOwner: me, at: nowMillis)
check("CONTROL: an app with evidence behind it reaches the card",
      fedDetection.offered.map { $0.key.toolkit } == ["fictional-desk"])
check("CONTROL: pre-selected, as page 45 asks",
      P.initialSelection(fedDetection) == [P.AppKey(toolkit: "fictional-desk", alias: nil)])
check("CONTROL: named by the catalog and never by a slug",
      fedDetection.offered.first?.name == "Fictional Desk")
check("CONTROL: and the Connect button lights up once it is ticked",
      P.step(for: fedDetection, chosen: P.initialSelection(fedDetection)).connectEnabled)

// ===================================================== 4. THE TWO HALVES AGREE
//
// The flow builds the step's owner out of `session.accountID` and hands the
// same id to `ConnectBeat`. The two must not disagree about whether there is
// anybody there: a beat walked over an id the policy will refuse is a card that
// can only ever say "I could not", and a beat SKIPPED over an id the policy
// would have accepted is the spec's step 2 disappearing again.
let ids = ["aaaaaaaaaaaaaaa", "", "not an owner", "AAAAAAAAAAAAAAA",
           "aaaaaaaaaaaaaa", "aaaaaaaaaaaaaaaa", " aaaaaaaaaaaaaaa "]
for id in ids {
    let real = P.OwnerID(id) != nil
    let audience = ConnectBeat.audience(ownerIsReal: real, liveConnections: 0,
                                        skipSnoozeUntil: 0, now: nowSeconds)
    check("\"\(id)\" is an owner to both halves or to neither",
          (audience != .noOwner) == real)
    if !real {
        check("\"\(id)\" is not walked to the step at all", !ConnectBeat.isShown(to: audience))
        check("and the policy would refuse its card anyway",
              P.detected(from: [], catalog: [], signedInOwner: P.OwnerID(id),
                         at: nowMillis) == .refused(.notSignedIn))
    }
}
// AND THE SKIP REFUSES FOR THE SAME REASON, rather than quietly writing a
// snooze for nobody.
check("a skip with no owner is refused, not recorded",
      P.skipOutcome(offered: [], signedInOwner: nil, at: nowMillis) == .refused(.notSignedIn))

// ===================================================== 5. THE ONE-WEEK LEDGER
//
// Onboarding's ask is exempt from the global cap as a GATE — a person who has
// been asked nothing has not been nagged — and it CHARGES it. So a skipped
// setup card and a shown one both cost the same quiet week, which is why the
// snooze the flow writes lands on the same number as the cap's interval.
check("the setup step is never blocked by the cap on a new owner",
      P.onboardingAskIsExemptFromGlobalCap(trigger: .onboarding, lastAskAnyAppAt: nil,
                                           thisAskSentAt: nil, at: nowMillis).isExempt)
check("and the quiet a skip buys is the same week the cap counts",
      P.Contract.onboardingSkipSnoozeDays == P.Contract.globalAskIntervalDays)

// ===================================================== 6. AND THE BEAT MOVES ON
//
// THE CONTROL FOR THE WHOLE FILE. Everything above is about not asking twice;
// this is about not trapping anybody. Whichever way the step ends — skipped,
// or every ticked app connected — the walk continues to the microphone beat and
// first run finishes. A step that records a perfect snooze and leaves somebody
// standing on it is worse than no step.
for showing in [true, false] {
    let walked = FirstRunSegment.rest.pages(showingConnect: showing)
    check("CONTROL: the walk still ends on the microphone (showing: \(showing))",
          walked.last == FirstRunBeat.mic)
    check("CONTROL: and the microphone is still the segment's last step (showing: \(showing))",
          walked.last == FirstRunSegment.rest.lastStep)
}
let afterSkip = FirstRunSegment.rest.pages(showingConnect: true)
guard let atStep = afterSkip.firstIndex(of: FirstRunBeat.connect) else {
    print("FAIL: the setup step is not in the walk at all, so nothing can move off it")
    exit(1)
}
check("CONTROL: there is a page after the setup step to move to",
      atStep + 1 < afterSkip.count)
check("CONTROL: and it is the microphone", afterSkip[atStep + 1] == FirstRunBeat.mic)
// AND THE SECOND TIME ROUND. A person who skipped is inside their quiet, the
// beat is not walked, and the walk is otherwise the same one — the same first
// page, the same last page, one page shorter.
let replay = ConnectBeat.audience(ownerIsReal: true, liveConnections: 0,
                                  skipSnoozeUntil: until, now: nowSeconds + day)
check("a replayed first run inside the quiet does not ask again", replay == .snoozed)
let replayWalk = FirstRunSegment.rest.pages(showingConnect: ConnectBeat.isShown(to: replay))
check("and that walk is the same walk without the step",
      replayWalk == afterSkip.filter { $0 != FirstRunBeat.connect })
check("CONTROL: eight days later it asks again",
      ConnectBeat.audience(ownerIsReal: true, liveConnections: 0,
                           skipSnoozeUntil: until,
                           now: nowSeconds + Double(flowSkip.snoozeDays + 1) * day)
        == .nothingConnected)

print(failures == 0 ? "all connect-onboarding step checks passed" : "\(failures) FAILED")
exit(failures == 0 ? 0 : 1)
