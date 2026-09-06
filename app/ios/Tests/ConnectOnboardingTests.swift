// ONBOARDING STEP 2 — "Which apps do you live in?" — and the text/app lockstep.
//
// Spec: "Connections: how Anticipy asks, learns, and never says Composio",
// 2026-09-05, page 25. Contract: spike/two-hands/src/connections/contract.ts.
//
// Five legs:
//   1. THE WRONG PERSON   every entry point refuses a row, a record or a link
//                         belonging to anybody but the owner signed into THIS
//                         phone — the spike failure, in miniature, at every door
//   2. DETECTION          pre-selection comes from injected rows and catalog
//                         metadata; rename every app in the catalog and the
//                         behaviour is identical, because no app is named here
//   3. SKIP               a seven-day SOFT SNOOZE that does not touch the
//                         decline ladder, and cannot leave a row the server
//                         reads as unaskable
//   4. LOCKSTEP           one nudge record, one link, two renderings; acting in
//                         either channel flips the other, and a racing double
//                         action settles to ONE connection
//   5. THE CAP            whether the setup ask counts against one-ask-per-week,
//                         pinned in both directions
//
// The mutations that turn these red, named so a reader can try them:
//   * make `skipOutcome` return level + 1 (what `recordDecline` does server-side)
//     -> leg 3's ladder cases fail
//   * make `act` create a connection when the record is already connected
//     -> leg 4's race cases fail with two connections for one app
//   * mint a second token for the second channel -> `firstTextCarriesSameLink`
//   * exempt any trigger spelled "onboarding" regardless of the ledger
//     -> leg 5's loophole case fails
//
// Run: sh app/ios/Tests/run_connect_onboarding_tests.sh
import Foundation

typealias P = ConnectOnboardingPolicy

var failures = 0
func check(_ name: String, _ ok: Bool) {
    print("\(ok ? "PASS" : "FAIL"): \(name)")
    if !ok { failures += 1 }
}

// Fifteen lowercase alphanumerics, invented. Never a real owner id, and never
// a name: contract.ts refuses a name, and so does this.
let me = P.OwnerID("abc123def456ghi")!
let someoneElse = P.OwnerID("zzz999yyy888xxx")!

let day = P.Contract.dayMilliseconds
let now: Double = 1_757_000_000_000

// The catalog is INVENTED, here and everywhere below. Two apps published by one
// vendor whose mail it also hosts, one app from a second vendor. If any real
// product name appears in this suite the runner is red, and so is the policy.
let vendorMail = "mail-in.vendor-one.example"
let appOne = P.CatalogEntry(slug: "alpha-one", name: "Alpha", logo: "alpha.png",
                            appURL: "https://alpha.vendor-one.example",
                            scopes: ["read"], mailHosts: [vendorMail])
let appTwo = P.CatalogEntry(slug: "alpha-two", name: "Beta", logo: "beta.png",
                            appURL: "https://beta.vendor-one.example",
                            scopes: ["read"], mailHosts: [vendorMail])
let appThree = P.CatalogEntry(slug: "gamma-one", name: "Gamma", logo: nil,
                              appURL: "https://gamma-two.example", scopes: ["read"])
let catalog = [appOne, appTwo, appThree]

func row(_ toolkit: String, _ source: P.SignalSource, _ at: Double,
         owner: P.OwnerID = me, weight: Double? = nil,
         alias: P.AccountAlias? = nil) -> P.SignalRow {
    P.SignalRow(owner: owner, toolkit: toolkit, source: source, weight: weight,
                lastSeenAt: at, alias: alias)
}

func keys(_ detection: P.Detection) -> [String] { detection.offered.map { $0.key.toolkit } }
func ticked(_ detection: P.Detection) -> [String] {
    detection.offered.filter { $0.preselected }.map { $0.key.toolkit }
}

// =========================================================================
// LEG 1 — the wrong person
// =========================================================================
// research/2026-09-05-composio-connections.md item 2: during the spike one
// operator's own mailbox was connected by hand and would have served everybody.
// Every door below is that failure's door.

check("an owner id is fifteen lowercase alphanumerics",
      P.OwnerID("abc123def456ghi") != nil)
check("an email is not an owner id", P.OwnerID("someone@example.test") == nil)
check("a display name is not an owner id", P.OwnerID("omar") == nil)
check("an uppercase id is not an owner id", P.OwnerID("ABC123DEF456GHI") == nil)
check("fourteen characters is not an owner id", P.OwnerID("abc123def456gh") == nil)
check("sixteen characters is not an owner id", P.OwnerID("abc123def456ghij") == nil)
check("an empty string is not an owner id", P.OwnerID("") == nil)
check("surrounding whitespace is trimmed, not rejected",
      P.OwnerID("  abc123def456ghi  ")?.raw == "abc123def456ghi")

let signals = [row("alpha-one", .mx, now - day)]

check("detection refuses when nobody is signed in",
      P.detected(from: signals, catalog: catalog, signedInOwner: nil, at: now)
          == .refused(.notSignedIn))
check("detection refuses another owner's signal rows",
      P.detected(from: [row("alpha-one", .mx, now, owner: someoneElse)],
                 catalog: catalog, signedInOwner: me, at: now) == .refused(.foreignRow))
check("detection refuses two owners' rows arriving together",
      P.detected(from: [row("alpha-one", .mx, now),
                        row("alpha-two", .mx, now, owner: someoneElse)],
                 catalog: catalog, signedInOwner: me, at: now) == .refused(.mixedOwners))
check("a refused detection offers no apps at all",
      P.detected(from: [row("alpha-one", .mx, now, owner: someoneElse)],
                 catalog: catalog, signedInOwner: me, at: now).offered.isEmpty)

let mine = P.NudgeRecord(owner: me, toolkit: "alpha-one", state: .neverAsked,
                         trigger: .onboarding, sentAt: now)
let theirs = P.NudgeRecord(owner: someoneElse, toolkit: "alpha-one", state: .neverAsked)

check("skip refuses another owner's nudge record",
      P.skipOutcome(offered: [theirs], signedInOwner: me, at: now) == .refused(.foreignRow))
check("skip refuses when nobody is signed in",
      P.skipOutcome(offered: [mine], signedInOwner: nil, at: now) == .refused(.notSignedIn))

let myLink = P.LinkRow(token: "tok-aaaaaaaaaaaaaaaaaaaa", owner: me, toolkit: "alpha-one",
                       expiresAt: now + P.Contract.linkTTLMilliseconds)
let theirLink = P.LinkRow(token: "tok-bbbbbbbbbbbbbbbbbbbb", owner: someoneElse,
                          toolkit: "alpha-one", expiresAt: now + P.Contract.linkTTLMilliseconds)
let otherAppLink = P.LinkRow(token: "tok-cccccccccccccccccccc", owner: me,
                             toolkit: "gamma-one", expiresAt: now + P.Contract.linkTTLMilliseconds)
let base = "https://connect.example/c"

check("a link minted for another owner is refused, not rendered",
      P.rendering(of: P.Ask(record: mine, link: theirLink), in: .ios, catalog: catalog,
                  base: base, signedInOwner: me, at: now) == .refused(.foreignLink))
check("a link for another app is refused",
      P.rendering(of: P.Ask(record: mine, link: otherAppLink), in: .ios, catalog: catalog,
                  base: base, signedInOwner: me, at: now) == .refused(.wrongToolkit))
check("acting on another owner's record is refused",
      P.act(.connected(accountID: "acct-1"), in: .ios,
            on: P.Ask(record: theirs, link: nil), signedInOwner: me, at: now)
          == .refused(.foreignRow))
check("acting with another owner's link is refused",
      P.act(.connected(accountID: "acct-1"), in: .sms,
            on: P.Ask(record: mine, link: theirLink), signedInOwner: me, at: now)
          == .refused(.foreignLink))
check("a link decision refuses another owner's link",
      P.linkDecision(for: mine, existing: theirLink, signedInOwner: me, at: now)
          == .refused(.foreignLink))
check("every refusal has its own code and a sentence",
      Set(P.Refusal.allCases.map { $0.rawValue }).count == P.Refusal.allCases.count
          && P.Refusal.allCases.allSatisfy { !$0.sentence.isEmpty })

// =========================================================================
// LEG 2 — detection
// =========================================================================

// The spec's own case: the sign-up address' mail is hosted by a vendor that
// also publishes other apps, and the step pre-selects THAT VENDOR'S apps —
// plural. Nothing here knows the vendor; the catalog entries claim the
// exchanger themselves.
let seeded = P.seeds(fromMailExchanger: vendorMail, catalog: catalog,
                     for: me, seenAt: now - day)
check("a mail exchanger the catalog claims seeds every app that claims it",
      seeded.map { $0.toolkit }.sorted() == ["alpha-one", "alpha-two"])
check("seeded rows are the contract's medium `mx` band",
      seeded.allSatisfy { $0.source == .mx && $0.weight == nil })
check("seeded rows belong to the signed-in owner", seeded.allSatisfy { $0.owner == me })
check("a subdomain of a claimed exchanger is still that vendor's",
      P.seeds(fromMailExchanger: "alt.\(vendorMail)", catalog: catalog, for: me, seenAt: now)
          .map { $0.toolkit }.sorted() == ["alpha-one", "alpha-two"])
check("an exchanger nobody claims seeds nothing",
      P.seeds(fromMailExchanger: "mx.unknown-vendor.example", catalog: catalog,
              for: me, seenAt: now).isEmpty)
check("no signed-in owner seeds nothing",
      P.seeds(fromMailExchanger: vendorMail, catalog: catalog, for: nil, seenAt: now).isEmpty)
check("a single-label host cannot swallow the catalog",
      P.seeds(fromMailExchanger: "example", catalog: catalog, for: me, seenAt: now).isEmpty)
check("a numeric address only matches itself",
      P.seeds(fromMailExchanger: "10.0.0.1", catalog: catalog, for: me, seenAt: now).isEmpty)

// Tier two: no declared mail host, but the exchanger sits under the app's own
// site. One vendor, one app, no declaration needed.
let undeclared = [P.CatalogEntry(slug: "delta-one", name: "Delta",
                                 appURL: "https://delta-vendor.example")]
check("an exchanger under the app's own site is that app",
      P.seeds(fromMailExchanger: "mx.delta-vendor.example", catalog: undeclared,
              for: me, seenAt: now).map { $0.toolkit } == ["delta-one"])

let detected = P.detected(from: seeded, catalog: catalog, signedInOwner: me, at: now)
check("the seeded apps arrive on the card, pre-selected",
      ticked(detected).sorted() == ["alpha-one", "alpha-two"])
check("the card names apps from the catalog, never from a slug",
      detected.offered.map { $0.name }.sorted() == ["Alpha", "Beta"])

// Ranking.
let ranked = P.detected(from: [row("gamma-one", .said, now),
                               row("alpha-one", .mx, now)],
                        catalog: catalog, signedInOwner: me, at: now)
check("stronger evidence ranks first", keys(ranked) == ["gamma-one", "alpha-one"])
check("arrival order does not change the order",
      keys(P.detected(from: [row("alpha-one", .mx, now), row("gamma-one", .said, now)],
                      catalog: catalog, signedInOwner: me, at: now))
          == ["gamma-one", "alpha-one"])
check("equal weights are broken by slug, not by arrival",
      keys(P.detected(from: [row("gamma-one", .mx, now), row("alpha-one", .mx, now)],
                      catalog: catalog, signedInOwner: me, at: now))
          == ["alpha-one", "gamma-one"])
check("one fresh medium signal outranks a high one from three months ago",
      keys(P.detected(from: [row("gamma-one", .said, now - 90 * day),
                             row("alpha-one", .mx, now)],
                      catalog: catalog, signedInOwner: me, at: now))
          == ["alpha-one", "gamma-one"])
check("a signal stamped in the future is not amplified",
      P.decayedWeight(0.4, lastSeenAt: now + 30 * day, now: now) == 0.4)
check("a certain source does not decay",
      keys(P.detected(from: [row("gamma-one", .asked, now - 365 * day),
                             row("alpha-one", .mx, now)],
                      catalog: catalog, signedInOwner: me, at: now))
          == ["gamma-one", "alpha-one"])

check("an app the catalog cannot name is not offered",
      keys(P.detected(from: [row("nobody-knows-this", .said, now)],
                      catalog: catalog, signedInOwner: me, at: now)).isEmpty)
check("an app already connected is not offered again",
      keys(P.detected(from: [row("alpha-one", .connected, now), row("alpha-one", .mx, now)],
                      catalog: catalog, signedInOwner: me, at: now)).isEmpty)
let asked = P.detected(from: [row("alpha-one", .asked, now), row("alpha-one", .mx, now)],
                       catalog: catalog, signedInOwner: me, at: now)
check("an app the state machine already asked about is shown, unticked",
      keys(asked) == ["alpha-one"] && ticked(asked).isEmpty)
check("an unreadable weight refuses the whole table rather than ranking it",
      P.detected(from: [row("alpha-one", .mx, now, weight: -1)],
                 catalog: catalog, signedInOwner: me, at: now) == .refused(.unreadableRow))
check("a weight of zero is unreadable too",
      P.detected(from: [row("alpha-one", .mx, now, weight: 0)],
                 catalog: catalog, signedInOwner: me, at: now) == .refused(.unreadableRow))
check("work and personal rank as two lines",
      P.detected(from: [row("alpha-one", .mx, now, alias: .work),
                        row("alpha-one", .mx, now, alias: .personal)],
                 catalog: catalog, signedInOwner: me, at: now).offered.count == 2)

// The pre-selection cap: everything is offered, six arrive ticked.
let many = (1...8).map { P.CatalogEntry(slug: "slug-\($0)", name: "App \($0)") }
let manyRows = (1...8).map { row("slug-\($0)", .said, now - Double($0) * 1000) }
let capped = P.detected(from: manyRows, catalog: many, signedInOwner: me, at: now)
check("every detected app is offered", capped.offered.count == 8)
check("only the first six arrive ticked",
      ticked(capped).count == P.maxPreselected
          && ticked(capped) == ["slug-1", "slug-2", "slug-3", "slug-4", "slug-5", "slug-6"])
check("the ones past the cap are still on the card, unticked",
      Array(keys(capped).suffix(2)) == ["slug-7", "slug-8"])

// NO APP IS HARDCODED, measured: run the whole flow twice on different invented
// slugs and names, and the shape of the answer is identical.
func flow(_ one: String, _ two: String, _ mail: String) -> [String] {
    let cat = [P.CatalogEntry(slug: one, name: one.uppercased(), appURL: nil, mailHosts: [mail]),
               P.CatalogEntry(slug: two, name: two.uppercased(), appURL: nil, mailHosts: [mail])]
    let rows = P.seeds(fromMailExchanger: mail, catalog: cat, for: me, seenAt: now)
    return ticked(P.detected(from: rows, catalog: cat, signedInOwner: me, at: now))
}
check("any two slugs behave identically — nothing here knows an app",
      flow("aaa", "bbb", "mx.one.example") == ["aaa", "bbb"]
          && flow("qqq", "rrr", "mx.two.example") == ["qqq", "rrr"])

// =========================================================================
// LEG 2b — the card
// =========================================================================

let fullStep = P.step(for: detected, chosen: P.initialSelection(detected))
let emptyStep = P.step(for: .apps([]), chosen: [])
let refusedStep = P.step(for: .refused(.foreignRow), chosen: [])

check("skip is on the card when apps were detected", !fullStep.skipLabel.isEmpty)
check("skip is on the card when nothing was detected", !emptyStep.skipLabel.isEmpty)
check("skip is on the card even when a row was refused", !refusedStep.skipLabel.isEmpty)
check("a refused card still offers the search box",
      !refusedStep.searchPlaceholder.isEmpty && refusedStep.refusal == .foreignRow)
check("the connect button is dead until something is ticked",
      !emptyStep.connectEnabled && fullStep.connectEnabled)
check("the ticked boxes are what detection pre-selected",
      P.initialSelection(detected).count == 2)
check("the step asks the spec's question", fullStep.title == "Which apps do you live in?")
check("the copy under the button says it is optional",
      fullStep.footnote.lowercased().contains("optional"))
check("the copy says the browser can do it too",
      fullStep.footnote.lowercased().contains("browser"))
check("the copy says connecting makes it instant",
      fullStep.footnote.lowercased().contains("instant"))
check("the copy says it works with the laptop shut",
      fullStep.footnote.lowercased().contains("laptop shut"))

let forbidden = ["composio", "oauth", "authorize", "authorise", "grant access",
                 "permission", "integration", "api"]
let everyWord = [P.Copy.title, P.Copy.subtitle, P.Copy.searchPlaceholder, P.Copy.connect,
                 P.Copy.skip, P.Copy.footnote].joined(separator: " ").lowercased()
check("the owner never hears the vendor, or a permission word",
      forbidden.allSatisfy { !everyWord.contains($0) })

check("the search box finds an app by the name the catalog gave it",
      P.visibleMatches(for: "gam", in: catalog).map { $0.slug } == ["gamma-one"])
check("the search box is case-insensitive",
      P.visibleMatches(for: "GAM", in: catalog).map { $0.slug } == ["gamma-one"])
check("the search box does not re-offer what is already on the card",
      P.visibleMatches(for: "a", in: catalog, excluding: ["alpha-one", "alpha-two"])
          .map { $0.slug } == ["gamma-one"])
check("an empty query lists nothing", P.visibleMatches(for: "  ", in: catalog).isEmpty)

// =========================================================================
// LEG 3 — skip is a soft snooze, not a decline
// =========================================================================

guard case .snoozed(let skipped) = P.skipOutcome(offered: [mine], signedInOwner: me, at: now)
else { fatalError("skip refused a record that belongs to the signed-in owner") }
let afterSkip = skipped.records[0]

check("skip snoozes for the contract's onboarding number, not the ladder's",
      skipped.snoozeDays == P.Contract.onboardingSkipSnoozeDays && skipped.snoozeDays == 7)
check("the snooze lands seven days out",
      afterSkip.snoozeUntil == now + 7 * day)
check("the snooze is NOT the ladder's fourteen days",
      afterSkip.snoozeUntil != now + 14 * day)
check("skip does not advance the decline level",
      afterSkip.level == mine.level && afterSkip.level == 0)
check("skip says so, in a field a test can read", !skipped.declineLevelChanged)
check("skip does not leave the row saying `declined`",
      afterSkip.state != .declined)
check("skip leaves the ladder where it was, so the server can still read the row",
      afterSkip.state == .neverAsked && !(afterSkip.state == .asked && afterSkip.actedAt != nil))
check("a shrug is recorded as an action, not as silence", afterSkip.actedAt == now)
check("the trigger records which moment produced it", afterSkip.trigger == .onboarding)

// Skip after connecting on the same card must not undo the connection.
let connectedRecord = P.NudgeRecord(owner: me, toolkit: "alpha-one", state: .connected,
                                    trigger: .onboarding, sentAt: now, actedAt: now,
                                    channel: .ios)
guard case .snoozed(let afterConnectedSkip) =
        P.skipOutcome(offered: [connectedRecord], signedInOwner: me, at: now + 1000)
else { fatalError("skip refused a connected record") }
check("skip never un-connects an app connected on the same card",
      afterConnectedSkip.records[0] == connectedRecord)

// A level-3 stop outlives a shrug.
let stopped = P.NudgeRecord(owner: me, toolkit: "alpha-one", state: .declined, level: 3,
                            snoozeUntil: now + 3650 * day, trigger: .inTask, sentAt: now - day)
guard case .snoozed(let afterStoppedSkip) =
        P.skipOutcome(offered: [stopped], signedInOwner: me, at: now)
else { fatalError("skip refused a declined record") }
check("skip never shortens a snooze somebody already earned",
      afterStoppedSkip.records[0].snoozeUntil == now + 3650 * day)
check("skip does not reopen a ladder that reached its end",
      afterStoppedSkip.records[0].state == .declined && afterStoppedSkip.records[0].level == 3)
// The server infers "the level-1 laptop-closed override is spent" from the
// trigger of the ask that WAS declined. A skip that rewrote it to `onboarding`
// would hand that override back and let a closed laptop ask inside a snooze
// this person earned by saying no.
check("skip does not overwrite how a decline was reached",
      afterStoppedSkip.records[0].trigger == .inTask
          && afterStoppedSkip.records[0].actedAt == stopped.actedAt)
// An old decline whose snooze has already run out still costs a week.
let coldDecline = P.NudgeRecord(owner: me, toolkit: "alpha-one", state: .declined, level: 1,
                                snoozeUntil: now - 6 * day, trigger: .inTask, sentAt: now - 20 * day)
guard case .snoozed(let afterColdSkip) =
        P.skipOutcome(offered: [coldDecline], signedInOwner: me, at: now)
else { fatalError("skip refused an expired decline") }
check("a skip over an expired decline snoozes seven days without touching the level",
      afterColdSkip.records[0].snoozeUntil == now + 7 * day
          && afterColdSkip.records[0].level == 1
          && afterColdSkip.records[0].state == .declined)

// One card, several apps, one Skip.
let offeredThree = [mine,
                    P.NudgeRecord(owner: me, toolkit: "alpha-two", trigger: .onboarding, sentAt: now),
                    P.NudgeRecord(owner: me, toolkit: "gamma-one", trigger: .onboarding, sentAt: now)]
guard case .snoozed(let allThree) = P.skipOutcome(offered: offeredThree, signedInOwner: me, at: now)
else { fatalError("skip refused the card's own records") }
check("skip snoozes every app the card offered",
      allThree.records.count == 3
          && allThree.records.allSatisfy { $0.snoozeUntil == now + 7 * day && $0.level == 0 })

// =========================================================================
// LEG 4 — one nudge record, two renderings
// =========================================================================

let ask = P.Ask(record: mine, link: myLink)

check("the first text carries the same link as the card",
      P.firstTextCarriesSameLink(ask, catalog: catalog, base: base, signedInOwner: me, at: now))
check("both channels agree before anybody acts",
      P.renderingsAgree(ask, catalog: catalog, base: base, signedInOwner: me, at: now))

guard case .shown(let cardView) = P.rendering(of: ask, in: .ios, catalog: catalog, base: base,
                                              signedInOwner: me, at: now),
      case .shown(let textView) = P.rendering(of: ask, in: .sms, catalog: catalog, base: base,
                                              signedInOwner: me, at: now)
else { fatalError("a rendering of the owner's own ask was refused") }
check("the link is ours, and it is the same bytes in both channels",
      cardView.url == textView.url && cardView.url == base + "/" + myLink.token)
check("the app is named from the catalog in both channels",
      cardView.appName == "Alpha" && textView.appName == "Alpha")
check("skip is never buried, in either channel", cardView.showsSkip && textView.showsSkip)

// A second channel never mints a second token: one ask, one binding.
check("a live token is reused, never re-minted",
      P.linkDecision(for: mine, existing: myLink, signedInOwner: me, at: now)
          == .reuse(myLink.token))
check("an expired token is re-minted, because ten minutes is short for a text",
      P.linkDecision(for: mine, existing: myLink, signedInOwner: me,
                     at: now + P.Contract.linkTTLMilliseconds + 1) == .mint)
check("a spent token is not offered again",
      P.linkDecision(for: mine,
                     existing: P.LinkRow(token: myLink.token, owner: me, toolkit: "alpha-one",
                                         expiresAt: now + 1000, usedAt: now),
                     signedInOwner: me, at: now) == .mint)
check("a record with no link mints one",
      P.linkDecision(for: mine, existing: nil, signedInOwner: me, at: now) == .mint)

// Acting in the app.
guard case .settled(let fromApp) = P.act(.connected(accountID: "acct-1"), in: .ios, on: ask,
                                         signedInOwner: me, at: now + 60_000)
else { fatalError("connecting from the app was refused") }
check("acting in the app connects the one record",
      fromApp.record.state == .connected && fromApp.record.channel == .ios)
check("the connection is created with writes OFF",
      fromApp.effects.contains(.createConnection(toolkit: "alpha-one", alias: nil,
                                                 accountID: "acct-1", writesEnabled: false)))
check("the single-use link is spent exactly once",
      fromApp.effects.filter { e -> Bool in
          if case .spendLink = e { return true }
          return false
      }.count == 1)
check("the text flips with it — both renderings now say connected",
      P.renderingsAgree(P.Ask(record: fromApp.record, link: myLink), catalog: catalog,
                        base: base, signedInOwner: me, at: now + 60_000))
guard case .shown(let textAfter) = P.rendering(of: P.Ask(record: fromApp.record, link: myLink),
                                               in: .sms, catalog: catalog, base: base,
                                               signedInOwner: me, at: now + 60_000)
else { fatalError("the text rendering was refused after connecting") }
check("a settled ask offers no link and no connect button in either channel",
      textAfter.url == nil && !textAfter.showsConnect)

// Acting in the text.
guard case .settled(let fromText) = P.act(.connected(accountID: "acct-1"), in: .sms, on: ask,
                                          signedInOwner: me, at: now + 60_000)
else { fatalError("connecting from the text was refused") }
check("acting in the text connects the same one record",
      fromText.record.state == .connected && fromText.record.channel == .sms)
check("either channel produces exactly one connection",
      fromText.effects.filter { e -> Bool in
          if case .createConnection = e { return true }
          return false
      }.count == 1)

// THE RACE. Both channels acted on, one after the other, in both orders.
guard case .settled(let raceSecond) =
        P.act(.connected(accountID: "acct-2"), in: .sms,
              on: P.Ask(record: fromApp.record, link: myLink),
              signedInOwner: me, at: now + 61_000)
else { fatalError("the losing half of the race was refused") }
check("a racing second action produces no second connection", raceSecond.effects.isEmpty)
check("the record is unchanged by the loser of the race",
      raceSecond.record == fromApp.record)
check("the account that won is the one that was written",
      fromApp.effects.contains(.createConnection(toolkit: "alpha-one", alias: nil,
                                                 accountID: "acct-1", writesEnabled: false)))

guard case .settled(let reverseSecond) =
        P.act(.connected(accountID: "acct-1"), in: .ios,
              on: P.Ask(record: fromText.record, link: myLink),
              signedInOwner: me, at: now + 61_000)
else { fatalError("the losing half of the reversed race was refused") }
check("the same holds with the channels reversed",
      reverseSecond.effects.isEmpty && reverseSecond.record == fromText.record)
check("one ask, one connected state, never two",
      fromApp.effects.count + raceSecond.effects.count
          == fromText.effects.count + reverseSecond.effects.count)

// Skip in one channel, connect in the other.
guard case .settled(let skipInText) = P.act(.skipped, in: .sms, on: ask, signedInOwner: me,
                                            at: now + 30_000)
else { fatalError("skipping from the text was refused") }
check("skipping in the text snoozes the one record, seven days, level unchanged",
      skipInText.record.snoozeUntil == now + 30_000 + 7 * day && skipInText.record.level == 0)
check("a skip creates no connection",
      skipInText.effects.allSatisfy { e -> Bool in
          if case .createConnection = e { return false }
          return true
      })
guard case .settled(let connectAfterSkip) =
        P.act(.connected(accountID: "acct-9"), in: .ios,
              on: P.Ask(record: skipInText.record, link: myLink),
              signedInOwner: me, at: now + 40_000)
else { fatalError("connecting after a skip was refused") }
check("connecting after a skip wins, and clears the snooze",
      connectAfterSkip.record.state == .connected && connectAfterSkip.record.snoozeUntil == nil)
guard case .settled(let skipAfterConnect) =
        P.act(.skipped, in: .sms, on: P.Ask(record: connectAfterSkip.record, link: myLink),
              signedInOwner: me, at: now + 50_000)
else { fatalError("skipping after a connect was refused") }
check("skipping after a connect changes nothing",
      skipAfterConnect.record == connectAfterSkip.record && skipAfterConnect.effects.isEmpty)

// An expired token is still one ask: the text tapped an hour later re-mints,
// and both renderings still agree about the state of the record.
let staleAsk = P.Ask(record: mine, link: myLink)
check("an expired link is not rendered as a live one",
      !P.firstTextCarriesSameLink(staleAsk, catalog: catalog, base: base, signedInOwner: me,
                                  at: now + 2 * P.Contract.linkTTLMilliseconds))
check("but the two channels still agree about the record",
      P.renderingsAgree(staleAsk, catalog: catalog, base: base, signedInOwner: me,
                        at: now + 2 * P.Contract.linkTTLMilliseconds))

// =========================================================================
// LEG 5 — the onboarding ask and the one-ask-per-week cap
// =========================================================================

check("a new owner with an empty ask ledger is exempt: nothing has nagged them",
      P.onboardingAskIsExemptFromGlobalCap(trigger: .onboarding, lastAskAnyAppAt: nil,
                                           thisAskSentAt: now, at: now).isExempt)
check("the same-minute text is the same ask, not a second one",
      P.onboardingAskIsExemptFromGlobalCap(trigger: .onboarding, lastAskAnyAppAt: now,
                                           thisAskSentAt: now, at: now + 60_000).isExempt)
check("a genuine ask about another app two days ago is NOT jumped by the word onboarding",
      !P.onboardingAskIsExemptFromGlobalCap(trigger: .onboarding, lastAskAnyAppAt: now - 2 * day,
                                            thisAskSentAt: now, at: now).isExempt)
check("an ask older than the interval leaves the cap to pass on its own",
      !P.onboardingAskIsExemptFromGlobalCap(trigger: .onboarding, lastAskAnyAppAt: now - 8 * day,
                                            thisAskSentAt: now, at: now).isExempt)
for trigger in P.Trigger.allCases where trigger != .onboarding {
    check("a \(trigger.rawValue) ask is never exempt from the cap",
          !P.onboardingAskIsExemptFromGlobalCap(trigger: trigger, lastAskAnyAppAt: nil,
                                                thisAskSentAt: now, at: now).isExempt)
}
check("the setup ask does charge the cap once it has happened",
      P.onboardingAskChargesTheCap)
check("the ledger is stamped at the moment the first channel sent it",
      P.capLedgerStamp(for: mine, at: now + 60_000) == now)
check("a record nobody has sent yet stamps now",
      P.capLedgerStamp(for: P.NudgeRecord(owner: me, toolkit: "alpha-one"), at: now) == now)
check("the second channel does not move the ledger",
      P.capLedgerStamp(for: mine, at: now + 60_000)
          == P.capLedgerStamp(for: mine, at: now + 120_000))

// =========================================================================
// The contract's own numbers and spellings
// =========================================================================

check("the onboarding skip snooze is the contract's seven days",
      P.Contract.onboardingSkipSnoozeDays == 7)
check("the global cap is seven days", P.Contract.globalAskIntervalDays == 7)
check("silence becomes a soft no at seventy-two hours",
      P.Contract.silenceIsASoftNoHours == 72)
check("our link lives ten minutes", P.Contract.linkTTLMilliseconds == 10 * 60 * 1000)
check("the nudge states are the contract's five",
      P.NudgeState.allCases.map { $0.rawValue }.sorted()
          == ["asked", "connected", "declined", "needs_reconnect", "never_asked"])
check("the triggers are the contract's five",
      P.Trigger.allCases.map { $0.rawValue }.sorted()
          == ["in_task", "laptop_closed", "onboarding", "repeated_use", "user_named_it"])
check("the signal sources are the contract's six",
      P.SignalSource.allCases.map { $0.rawValue }.sorted()
          == ["asked", "connected", "link", "mx", "observer", "said"])
check("the account aliases are the contract's two",
      P.AccountAlias.allCases.map { $0.rawValue }.sorted() == ["personal", "work"])
check("the channels are the contract's two",
      P.Channel.allCases.map { $0.rawValue }.sorted() == ["ios", "sms"])

if failures > 0 {
    print("\nConnectOnboardingTests: \(failures) case(s) came back wrong")
    exit(1)
}
print("\nConnectOnboardingTests: all passed")
