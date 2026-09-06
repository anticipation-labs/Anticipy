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


// ===================================================== 7. THE CARD IS ACTUALLY FED
//
// GAP A, and it is the one that made page 45's first sentence a decoration.
// `OnboardingView.connectDetection` was `detected(from: [], catalog: [], …)` —
// two literal empty arrays — so "detected apps pre-selected" pre-selected
// nothing, for every person alive, while section 4 of ConnectOnboardingTests
// proved 154 times over that the ranking would have ordered them beautifully if
// anything had ever handed it a row.
//
// THE ROWS ARE THE SERVER'S AND SO IS THEIR ORDER. `rank` above is the same
// arithmetic mirrored under a gate and still runs over locally held rows; it
// cannot run over these, because the weight is deliberately not on the wire.
// What is still decided here is every product question — which lines are
// dropped, which arrive ticked, how many — and those are what these checks are.
//
// THE APP NAMES AND SLUGS HERE ARE INVENTED. They exist only in this file.
let evidenceSlugs = ["ember", "harbour", "lantern", "meadow", "nimbus",
                     "orchard", "petrel", "quarry"]

func line(_ slug: String, sources: [String] = ["said"], alias: String? = nil,
          seen: Double = nowMillis) -> P.RankedApp {
    P.RankedApp(toolkit: slug, name: slug.uppercased(), logo: nil,
                alias: alias, lastSeenAt: seen, sources: sources)
}

// THE THREE EMPTY ANSWERS ARE THREE DIFFERENT FACTS, and only one of them is a
// claim about the person. A card that folds them together tells somebody they
// use none of the apps in the world every time a request times out — on the one
// screen that then invites them to connect what they already live in.
check("we could not look is a refusal, never an empty card",
      P.detected(from: .unreachable, signedInOwner: me) == .refused(.couldNotLook))
check("and a catalog that could name nothing is its own refusal",
      P.detected(from: .catalogUnreadable, signedInOwner: me)
        == .refused(.catalogUnreadable))
check("we looked and there is nothing is the ONLY empty card",
      P.detected(from: .nothingYet, signedInOwner: me) == .apps([]))
check("CONTROL: and those three are not the same answer",
      Set([P.detected(from: .unreachable, signedInOwner: me),
           P.detected(from: .catalogUnreadable, signedInOwner: me),
           P.detected(from: .nothingYet, signedInOwner: me)]
            .map { "\($0)" }).count == 3)

// SIGNED OUT BEATS EVERYTHING, whatever the network said. It is the more
// fundamental fact and the one ConnectBeat.audience is deciding on at the same
// instant.
for answer in [P.SignalsAnswer.unreachable, .nothingYet, .catalogUnreadable,
               .ranked([line(evidenceSlugs[0])])] {
    check("a signed-out phone refuses that card whatever came back",
          P.detected(from: answer, signedInOwner: nil) == .refused(.notSignedIn))
}

// THE ORDER IS THE SERVER'S AND IS NOT TOUCHED. Two definitions of which app is
// first is a list that reorders itself between the screen and the message
// about it.
let eight = evidenceSlugs.map { line($0) }
guard case .apps(let card) = P.detected(from: .ranked(eight), signedInOwner: me) else {
    print("FAIL: a ranked answer did not produce a card at all, so nothing is offered")
    exit(1)
}
check("every app the server ranked is on the card",
      card.map { $0.key.toolkit } == evidenceSlugs)
// AND THE CAP IS A HARD STOP RATHER THAN A TARGET. Past it the app is still on
// the card and still one tap away; it is not ticked, because a screen of
// pre-ticked boxes past the fold is consent nobody gave.
check("exactly maxPreselected apps arrive ticked",
      card.filter { $0.preselected }.count == P.maxPreselected)
check("and they are the first ones, in the server's order",
      card.prefix(P.maxPreselected).allSatisfy { $0.preselected })
check("CONTROL: the ones past the cap are shown and unticked",
      card.dropFirst(P.maxPreselected).allSatisfy { !$0.preselected })

// THE TWO EXCLUSIONS, WHICH ARE NOT THE SAME EXCLUSION.
let mixed = P.detected(from: .ranked([
    line("ember", sources: ["connected"]),
    line("harbour", sources: ["asked", "said"]),
    line("lantern", sources: ["said", "mx"]),
]), signedInOwner: me)
check("an app already connected is not offered again",
      mixed.offered.map { $0.key.toolkit } == ["harbour", "lantern"])
check("an app already asked about is shown and never pre-ticked",
      mixed.offered.first { $0.key.toolkit == "harbour" }?.preselected == false)
check("CONTROL: and the one nobody has been asked about is ticked",
      mixed.offered.first { $0.key.toolkit == "lantern" }?.preselected == true)
check("an asked line does not spend a tick either",
      mixed.offered.filter { $0.preselected }.count == 1)

// NEVER INVENT A TICK OUT OF OUR OWN IGNORANCE. A source spelling or an alias
// this build has never heard of reads as NOTHING — the enums are closed for
// that reason — and "nothing" is not "there was nothing there". The exclusions
// are written in terms of sources, so a spelling we cannot read is a rule we
// cannot apply, and the safe side of a rule nobody could apply is unticked.
let strange = P.detected(from: .ranked([
    line("meadow", sources: ["said", "telepathy"]),
    line("nimbus", sources: ["said"], alias: "shared"),
    line("orchard", sources: ["said"], alias: "work"),
]), signedInOwner: me)
check("a line carrying a source this build cannot read is shown",
      strange.offered.map { $0.key.toolkit } == ["meadow", "nimbus", "orchard"])
check("and it is not pre-ticked",
      strange.offered.first { $0.key.toolkit == "meadow" }?.preselected == false)
check("nor is one carrying an alias this build cannot read",
      strange.offered.first { $0.key.toolkit == "nimbus" }?.preselected == false)
check("CONTROL: an alias this build DOES know ticks and keys the row",
      strange.offered.first { $0.key.toolkit == "orchard" }?.preselected == true)
check("CONTROL: and that alias reached the key, so two accounts stay two rows",
      strange.offered.first { $0.key.toolkit == "orchard" }?.key.alias == .personal
        ? false : strange.offered.first { $0.key.toolkit == "orchard" }?.key.alias == .work)

// THE TRANSLATION ITSELF, which is where a closed enum earns its keep.
let read = P.RankedApp(toolkit: "petrel", name: "PETREL", logo: nil,
                       alias: "personal", lastSeenAt: nowMillis,
                       sources: ["said", "said", "observer", "telepathy"])
check("a repeated source is one source", read.sources == [.said, .observer])
check("a spelling this build never heard of is kept, not guessed at",
      read.unreadable == ["telepathy"])
check("CONTROL: and a spelling it knows is not in that list",
      !read.unreadable.contains("said"))
check("the alias reaches the key", read.key == P.AppKey(toolkit: "petrel", alias: .personal))

// ===================================================== 8. AND IT CAME OFF THE WIRE
//
// The half a source scan cannot see. `ConnectedAppsClient` is compiled into
// this binary and driven over a fake transport, so the request that WOULD have
// gone out is inspected rather than imagined, and the answers the Worker
// actually serves are decoded rather than described.
//
// The shapes below are `routes/connections_api.ts` as it stands on 2026-09-06:
// `signalRow` is `catalogRow` plus `alias`, `last_seen_at` and `sources`, and
// the four states are `SIGNALS_ANSWER`.

@MainActor
final class Wire: ConnectedAppsTransport {
    struct NoAnswer: Error {}
    var status = 200
    var body: [String: Any] = [:]
    private(set) var sent: [URLRequest] = []
    var urls: [String] { sent.compactMap { $0.url?.absoluteString } }

    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        sent.append(request)
        let data = (try? JSONSerialization.data(withJSONObject: body)) ?? Data()
        return (data, HTTPURLResponse(url: request.url!, statusCode: status,
                                      httpVersion: nil, headerFields: nil)!)
    }

    func bodyOut() -> [String: Any]? {
        guard let data = sent.last?.httpBody else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }
}

let base = URL(string: "https://api.invalid")!
let token = "sess_2f7c1d9e"
guard let wireOwner = OwnerId(me.raw) else {
    print("FAIL: the suite could not build the client's owner id")
    exit(1)
}

@MainActor
func clientOver(_ wire: Wire, owner: OwnerId? = nil) -> ConnectedAppsClient {
    ConnectedAppsClient(credential: {
        guard let who = owner else { return nil }
        return ConnectedAppsCredential(baseURL: base, owner: who, authToken: token)
    }, transport: wire)
}

func wireRow(_ slug: String, alias: String? = nil,
             sources: [String] = ["said"], name: String? = nil) -> [String: Any] {
    var row: [String: Any] = [
        "slug": slug,
        "name": name ?? slug.uppercased(),
        "logo": "https://logos.invalid/\(slug).png",
        "description": NSNull(),
        "app_url": "https://\(slug).invalid",
        "scopes": ["read"],
        "last_seen_at": nowMillis,
        "sources": sources,
    ]
    if let alias { row["alias"] = alias }
    return row
}

func cause(_ error: Error) -> ConnectedAppsRefusal.Cause? {
    (error as? ConnectedAppsRefusal)?.cause
}

// THE OWNER IS NEVER ON THE WIRE. The route is under `me/` and the server
// derives the owner from the session — this is the rule the spike broke when
// one operator's mailbox served everybody.
let ranked = Wire()
ranked.body = ["state": "ranked",
               "items": [wireRow("ember"), wireRow("harbour", alias: "work")]]
let answered = try? await clientOver(ranked, owner: wireOwner).signals(owner: wireOwner)
check("the evidence route is asked on the path the Worker serves",
      ranked.sent.first?.url?.path == "/me/connections/signals")
check("it is a GET, because reading evidence may never write any",
      ranked.sent.first?.httpMethod == "GET")
check("no owner id appears anywhere in the request",
      !ranked.urls.joined().contains(me.raw))
check("the session token rides in the header, never on the URL",
      ranked.sent.first?.value(forHTTPHeaderField: "Authorization") == token
        && !ranked.urls.joined().contains(token))
guard case .ranked(let wireLines)? = answered else {
    print("FAIL: a ranked answer off the wire did not decode as ranked at all.")
    print("      That is gap A with a route in front of it: the card would")
    print("      still pre-select nothing, for everybody, forever.")
    exit(1)
}
check("both lines came back, in the order the server sent them",
      wireLines.map { $0.toolkit } == ["ember", "harbour"])
check("the catalog's own name is on the line, so no slug is shown raw",
      wireLines.first?.name == "EMBER")
check("the alias crosses as the server wrote it", wireLines.last?.alias == "work")
check("and so do the sources", wireLines.first?.sources == ["said"])

// AN EMPTY ANSWER IS BELIEVED ONLY WHEN THE SERVER SAID IT. "You have nothing
// yet" is the one claim on this route that is about the PERSON, so it is a
// floor: read from the field the far end declares, never inferred from a short
// list.
let empty = Wire()
empty.body = ["state": "none", "items": []]
check("the server's own word for an empty table is what makes the card empty",
      (try? await clientOver(empty, owner: wireOwner).signals(owner: wireOwner))
        == .nothingYet)
let silent = Wire()
silent.body = ["items": []]
var silentCause: ConnectedAppsRefusal.Cause?
do { _ = try await clientOver(silent, owner: wireOwner).signals(owner: wireOwner) }
catch { silentCause = cause(error) }
check("a 200 with nothing in it and no such word is unreadable, not empty",
      silentCause == .unreadableAnswer)
let unnameable = Wire()
unnameable.body = ["state": "ranked", "items": [["slug": "ember"]]]
var unnameableCause: ConnectedAppsRefusal.Cause?
do { _ = try await clientOver(unnameable, owner: wireOwner).signals(owner: wireOwner) }
catch { unnameableCause = cause(error) }
check("rows arrived and none could be read: unreadable, not empty",
      unnameableCause == .unreadableAnswer)

// THE TWO FAILURES ARE TOLD APART BY A FIELD, NEVER BY THE PROSE BESIDE IT.
let noCatalog = Wire()
noCatalog.status = 503
noCatalog.body = ["ok": false, "state": "catalog-unreadable", "message": "…"]
var noCatalogCause: ConnectedAppsRefusal.Cause?
do { _ = try await clientOver(noCatalog, owner: wireOwner).signals(owner: wireOwner) }
catch { noCatalogCause = cause(error) }
check("a catalog that could name nothing has its own cause",
      noCatalogCause == .catalogUnreadable)
let outage = Wire()
outage.status = 503
outage.body = ["ok": false, "state": "unreadable", "message": "…"]
var outageCause: ConnectedAppsRefusal.Cause?
do { _ = try await clientOver(outage, owner: wireOwner).signals(owner: wireOwner) }
catch { outageCause = cause(error) }
check("CONTROL: and an ordinary outage does not borrow it",
      outageCause == .serverRefused)

// SIGNED OUT SENDS NOTHING, and the assertion is on the recorder: a client that
// threw AFTER building the request would pass a test that only read the throw,
// and the request would already be at the server.
let signedOut = Wire()
var signedOutCause: ConnectedAppsRefusal.Cause?
do { _ = try await clientOver(signedOut, owner: nil).signals(owner: wireOwner) }
catch { signedOutCause = cause(error) }
check("a signed-out phone does not ask for anybody's evidence",
      signedOutCause == .notSignedIn && signedOut.sent.isEmpty)
guard let neighbour = OwnerId("bbbbbbbbbbbbbbb") else {
    print("FAIL: the suite could not build a second owner id")
    exit(1)
}
let wrongPerson = Wire()
var wrongPersonCause: ConnectedAppsRefusal.Cause?
do { _ = try await clientOver(wrongPerson, owner: neighbour).signals(owner: wireOwner) }
catch { wrongPersonCause = cause(error) }
check("and a call naming somebody who is not signed in reaches the wire zero times",
      wrongPersonCause == .anotherOwner && wrongPerson.sent.isEmpty)

// THE SKIP'S BODY IS TWO FIELDS AND NEITHER OF THEM IS A LEVEL. What a refusal
// COSTS is the ladder's answer; a client that could name the snooze could name
// it as zero.
let said = Wire()
said.body = ["ok": true, "state": "recorded", "level": 1,
             "snooze_until": nowMillis + 7 * day * 1000]
let ack = try? await clientOver(said, owner: wireOwner)
    .skip(toolkit: "ember", onboarding: true, owner: wireOwner)
check("the skip goes to the route the Worker serves",
      said.sent.first?.url?.path == "/me/connections/skip")
check("its body is the toolkit and the surface, and nothing else",
      (said.bodyOut()?["toolkit"] as? String) == "ember"
        && (said.bodyOut()?["onboarding"] as? Bool) == true
        && said.bodyOut()?.keys.sorted() == ["onboarding", "toolkit"])
check("no owner id is on the body either", !(said.bodyOut()?.keys.contains("user_id") ?? true))
check("what the server did comes back rather than being swallowed",
      ack?.level == 1 && ack?.state == "recorded")

// AND WHAT COMES BACK IS JUDGED BY THE PREDICATE THIS FILE ALREADY HAS.
//
// THE MEASUREMENT THAT KEEPS THE SKIP ON THIS PHONE. The Worker's `recordSkip`
// reaches `recordDecline`, which stamps `declined` and `level + 1` on the very
// event this card calls a shrug — a seven-day snooze, yes, but a real decline
// under it, and level 1 raises the ask threshold to 0.8 against a strict
// comparison. `serverAgreedWithSkip` reads exactly that and says no.
check("the server's answer today is NOT what the setup card means by a skip",
      !P.serverAgreedWithSkip(levelAfter: ack?.level, snoozeUntil: ack?.snoozeUntil,
                              at: nowMillis))
check("which is the fact the flow's gate is holding",
      P.serverRecordsTheSoftSnooze == false)
check("CONTROL: a far end that left the ladder alone WOULD agree",
      P.serverAgreedWithSkip(levelAfter: 0, snoozeUntil: nowMillis + 7 * day * 1000,
                             at: nowMillis))
// A FLOOR, POINTED THE WAY A FLOOR MUST POINT: nobody answering is not a yes.
check("a missing level is nobody answering, not a level of zero",
      !P.serverAgreedWithSkip(levelAfter: nil, snoozeUntil: nowMillis + 7 * day * 1000,
                              at: nowMillis))
check("and a missing instant is nobody answering either",
      !P.serverAgreedWithSkip(levelAfter: 0, snoozeUntil: nil, at: nowMillis))
let mute = Wire()
mute.body = ["ok": true, "level": 1]
var muteCause: ConnectedAppsRefusal.Cause?
do {
    _ = try await clientOver(mute, owner: wireOwner)
        .skip(toolkit: "ember", onboarding: true, owner: wireOwner)
} catch { muteCause = cause(error) }
check("a 2xx nobody can read is not a recorded no", muteCause == .unreadableAnswer)

// ===================================================== 8B. END TO END, ON ONE CARD
//
// THE WHOLE OF GAP A IN ONE CHECK. A body in the shape the Worker serves, read
// by the real client, translated the way OnboardingView.readConnectSignals
// translates it, and handed to the policy — and what comes out has ticks on it.
// Against the tree this closes, every one of these was false: the flow passed
// two literal empty arrays and the card came back blank for everybody.
//
// The six lines below are the view's own mapping. The view cannot be compiled
// on a laptop, so the runner greps it for exactly this shape; if these two ever
// disagree, that leg is the one that says so.
@MainActor
func asPolicyAnswer(_ answer: AppSignalsAnswer) -> P.SignalsAnswer {
    switch answer {
    case .nothingYet:
        return .nothingYet
    case .ranked(let rows):
        return .ranked(rows.map {
            ConnectOnboardingPolicy.RankedApp(toolkit: $0.toolkit, name: $0.name,
                                              logo: $0.logo, alias: $0.alias,
                                              lastSeenAt: $0.lastSeenAt,
                                              sources: $0.sources)
        })
    }
}

let live = Wire()
live.body = [
    "state": "ranked",
    "items": [
        wireRow("ember"),
        wireRow("harbour", sources: ["connected"]),
        wireRow("lantern", sources: ["asked", "said"]),
        wireRow("meadow", alias: "work", sources: ["mx", "said"]),
    ],
]
guard let offWire = try? await clientOver(live, owner: wireOwner).signals(owner: wireOwner) else {
    print("FAIL: the card's own evidence route did not answer at all")
    exit(1)
}
let endToEnd = P.detected(from: asPolicyAnswer(offWire), signedInOwner: me)
check("the card is built from what the server said",
      endToEnd.offered.map { $0.key.toolkit } == ["ember", "lantern", "meadow"])
check("THE DEFECT THIS CLOSES: something is actually pre-selected",
      endToEnd.offered.contains { $0.preselected })
check("the app already connected is not offered", !endToEnd.offered.contains { $0.key.toolkit == "harbour" })
check("the app already asked about is offered unticked",
      endToEnd.offered.first { $0.key.toolkit == "lantern" }?.preselected == false)
check("the two nobody has been asked about arrive ticked",
      endToEnd.offered.filter { $0.preselected }.map { $0.key.toolkit } == ["ember", "meadow"])
check("and the name on the card is the catalog's, never the slug",
      endToEnd.offered.first?.name == "EMBER")
// AND THE CONTROL FOR THE WHOLE SECTION: the same journey with the answer the
// old flow forced on every person. It has to come out empty, or these checks
// prove nothing about the wire.
check("CONTROL: with no evidence the same card is honestly empty",
      P.detected(from: .nothingYet, signedInOwner: me).offered.isEmpty)

print(failures == 0 ? "all connect-onboarding step checks passed" : "\(failures) FAILED")
exit(failures == 0 ? 0 : 1)
