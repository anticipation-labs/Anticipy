// CONNECTIONS — the pure policy the whole feature stands on.
//
// The load-bearing suite in this file is the FIRST one: rows belonging to
// another owner are dropped, even when the caller hands over a mixed list.
// Everything else here is a screen or a sentence; that one is the spike's
// recorded failure made impossible. On 2026-09-05 one operator's own Gmail and
// Calendar were connected by hand under the `user_id` "omar" — a display name,
// which is one person's tokens serving everybody. It was revoked and deleted
// (research/2026-09-05-composio-connections.md, item 2), and the contract's
// answer is that the user id is the owner ROW id, always, and never a name.
//
// Run: sh app/ios/Tests/run_connections_policy_tests.sh
import Foundation

var failures = 0
func check(_ name: String, _ ok: Bool) {
    print("\(ok ? "PASS" : "FAIL"): \(name)")
    if !ok { failures += 1 }
}

// ---------------------------------------------------------------------------
// THE CONTRACT'S CLOSED SETS, TYPED OUT ONCE.
//
// These five lists are the census the runner compares against
// spike/two-hands/src/connections/contract.ts. Swift enums with associated raw
// values cannot be enumerated from a shell script, so the runner reads the
// CONTRACT and reads THESE, and a member added on the server without a member
// added here is red before anything compiles. Same device as REFUSAL_CAUSES in
// CalendarHandPolicyTests.swift, and for the same reason: a list somebody types
// goes stale in silence unless something outside it counts.
// ---------------------------------------------------------------------------

// `declined_soft` (2026-09-06) is the setup card's Skip: level 0, seven days,
// and NOT a rung on the ladder. It sits where the contract puts it — between
// `asked` and `declined` — because this list is compared to contract.ts IN
// ORDER, and `NudgeState.allCases` has to match it member for member.
let CONTRACT_NUDGE_STATES = ["never_asked", "asked", "declined_soft", "declined",
                             "connected", "needs_reconnect"]
let CONTRACT_STATUSES = ["connected", "needs_reconnect", "disconnected"]
let CONTRACT_ALIASES = ["work", "personal"]
let CONTRACT_TRIGGERS = ["in_task", "repeated_use", "laptop_closed", "user_named_it", "onboarding"]
let CONTRACT_SNOOZE_DAYS = [14, 45, 3650]
let CONTRACT_OWNER_ID_LENGTH = 15

// ----------------------------------------------------------------- fixtures
//
// NO REAL APP NAMES ANYWHERE IN THIS FILE, and that is a decision rather than
// an omission. If the suite proved the policy works "for gmail and notion", the
// next reader would reasonably add a third fixture when a third app ships. The
// whole product claim is that a new app in the catalog is a new app in Anticipy
// with ZERO code — so the fixtures are invented slugs, and the test that a card
// built from an invented slug is indistinguishable from any other is the claim
// itself, checked.

let ME = OwnerId("sxkotd1h02qb6gw")!
let SOMEONE_ELSE = OwnerId("q3zp8bd0h1nv6kw")!
let NOW: Double = 1_757_000_000            // an ordinary afternoon, in seconds
let DAY: Double = 24 * 60 * 60

let SLUG_A = "aurora"                       // invented, and never special-cased
let SLUG_B = "zebracorp"

let META_A = ToolkitMeta(slug: SLUG_A, name: "Aurora",
                         logo: "https://cdn.example.test/aurora.png",
                         description: "Notes.", appURL: "https://aurora.test",
                         scopes: ["notes.read", "notes.write"])
let META_B = ToolkitMeta(slug: SLUG_B, name: "Zebracorp",
                         logo: "https://cdn.example.test/zebra.png",
                         scopes: ["mail.read"])

func connection(owner: OwnerId = ME,
                toolkit: String = SLUG_A,
                account: String = "ca_0001",
                alias: AccountAlias? = .work,
                status: ConnectionStatus = .connected,
                writes: Bool = false,
                lastUsed: Double? = NOW - 3600) -> Connection {
    Connection(userID: owner.raw, toolkit: toolkit, connectedAccountID: account,
               alias: alias, status: status, writesEnabled: writes, lastUsedAt: lastUsed)
}

/// A row whose `user_id` is a NAME. This is the spike's failure as a value.
func rowOwnedByAName(toolkit: String = SLUG_A) -> Connection {
    Connection(userID: "omar", toolkit: toolkit, connectedAccountID: "ca_omar",
               alias: .work, status: .connected, writesEnabled: true, lastUsedAt: NOW)
}

func nudge(owner: OwnerId = ME,
           toolkit: String = SLUG_A,
           state: NudgeState = .asked,
           level: Int = 0,
           snoozeUntil: Double? = nil,
           trigger: NudgeTrigger? = .inTask,
           sentAt: Double? = NOW - 3600,
           actedAt: Double? = nil,
           channel: NudgeChannel? = .sms) -> ConnectNudge {
    ConnectNudge(userID: owner.raw, toolkit: toolkit, state: state, level: level,
                 snoozeUntil: snoozeUntil, trigger: trigger, sentAt: sentAt,
                 actedAt: actedAt, channel: channel)
}

func card(_ n: ConnectNudge, meta: ToolkitMeta? = META_A, owner: OwnerId = ME) -> NudgeCard {
    ConnectionsPolicy.nudgeRender(state: NudgeCardInput(nudge: n, meta: meta, owner: owner))
}

// ===========================================================================
// 1. THE ONE THAT MATTERS: OWNER SCOPING
// ===========================================================================
// "There must be no path where a connection, a nudge, or a toggle is read or
// written for an owner other than the signed-in one." Every public entry point
// that takes rows is checked against a MIXED list below, because a filter that
// is only ever handed clean input is a filter nobody has tested.

print("── owner scoping ──")

let MIXED: [Connection] = [
    connection(owner: ME, account: "ca_mine", writes: false),
    connection(owner: SOMEONE_ELSE, account: "ca_theirs", writes: true),
    rowOwnedByAName(),
    connection(owner: SOMEONE_ELSE, toolkit: SLUG_B, account: "ca_theirs_b"),
]

let mine = OwnerScoped.rows(MIXED, for: ME)
check("a mixed list keeps only the signed-in owner's rows", mine.count == 1)
check("and the row it keeps is the right one",
      mine.first?.connectedAccountID == "ca_mine")
check("another owner's row is dropped even though it is well-formed",
      !mine.contains { $0.userID == SOMEONE_ELSE.raw })

// THE SPIKE'S FAILURE, AS A TEST. A row bound to a display name can never
// belong to anybody, because no valid owner id is a name.
check("a connection bound to a NAME belongs to nobody",
      !OwnerScoped.belongs(rowOwnedByAName(), to: ME))
check("and it is dropped from a mixed list",
      !mine.contains { $0.userID == "omar" })

// The other owner reading the same list gets their own rows and only theirs.
let theirs = OwnerScoped.rows(MIXED, for: SOMEONE_ELSE)
check("the other owner sees exactly their own two rows", theirs.count == 2)
check("and never mine", !theirs.contains { $0.userID == ME.raw })

// An id is lowercase. We do not get to decide that a different string is the
// same person.
let SHOUTED = "SXKOTD1H02QB6GW"
check("an uppercase id is not a valid owner id", OwnerId(SHOUTED) == nil)
let shoutedRow = Connection(userID: SHOUTED, toolkit: SLUG_A, connectedAccountID: "ca_x",
                            alias: nil, status: .connected, writesEnabled: true,
                            lastUsedAt: nil)
check("and a row carrying it does not match the lowercase owner",
      !OwnerScoped.belongs(shoutedRow, to: ME))

// A padded id is a malformed row, and the safe reading of a malformed row is
// "not yours". Over-refusing shows you an empty screen; under-refusing shows
// you somebody else's mail.
let paddedRow = Connection(userID: " \(ME.raw) ", toolkit: SLUG_A,
                           connectedAccountID: "ca_pad", alias: nil,
                           status: .connected, writesEnabled: true, lastUsedAt: nil)
check("a row whose id carries whitespace does not match", !OwnerScoped.belongs(paddedRow, to: ME))

// OwnerId itself: the type that stops a name reaching a place an id belongs.
check("a display name is not an owner id", OwnerId("omar") == nil)
check("an email is not an owner id", OwnerId("jose@anticipy.ai") == nil)
check("an empty string is not an owner id", OwnerId("") == nil)
check("nil is not an owner id", OwnerId(nil) == nil)
check("14 characters is not an owner id", OwnerId("sxkotd1h02qb6w") == nil)
check("16 characters is not an owner id", OwnerId("sxkotd1h02qb6gww") == nil)
check("a hyphen is not an owner id character", OwnerId("sxkotd1h02qb6g-") == nil)
check("a real owner id survives", OwnerId("sxkotd1h02qb6gw")?.raw == "sxkotd1h02qb6gw")
check("the id length agrees with the contract", OwnerId.length == CONTRACT_OWNER_ID_LENGTH)

// A single record read back — a nudge in a push payload, a connection quoted in
// a job row — is the path where a filter is easiest to forget.
check("one record for another owner reads as nothing",
      OwnerScoped.one(connection(owner: SOMEONE_ELSE), for: ME) == nil)
check("one record for this owner reads back",
      OwnerScoped.one(connection(owner: ME), for: ME) != nil)

// ---- and every entry point that takes rows -------------------------------
//
// Not "the filter works" but "the filter is actually called", once per door.

check("settings cards built from a mixed list show only my apps",
      ConnectionsPolicy.settingsCards(rows: MIXED, catalog: [META_A, META_B], for: ME)
          .map(\.toolkit) == [SLUG_A])
check("the other owner's second app never appears on my screen",
      !ConnectionsPolicy.settingsCards(rows: MIXED, catalog: [META_A, META_B], for: ME)
          .contains { $0.toolkit == SLUG_B })

// THE READ. The other owner's row on SLUG_B is `connected`; mine is not there
// at all. A missing filter would answer "yes, you may read it".
check("a read is refused on an app only somebody else has connected",
      !ConnectionsPolicy.mayUse(rows: MIXED, toolkit: SLUG_B, access: .read, for: ME))
check("and a write is too",
      !ConnectionsPolicy.mayUse(rows: MIXED, toolkit: SLUG_B, access: .write, for: ME))

// THE TOGGLE. The other owner's row on SLUG_A has the opt-in ON. If the filter
// were missing, my `writesEnabled` would read from their consent.
check("their opt-in does not turn my toggle on",
      !ConnectionsPolicy.writesEnabled(rows: MIXED, toolkit: SLUG_A, for: ME))

// AND THE WRITE-BACK. This is the one that would actually reach their account.
let flipped = ConnectionsPolicy.writesTransition(rows: MIXED, toolkit: SLUG_A,
                                                 to: true, for: ME)
check("a toggle writes back exactly one row", flipped.rowsToWrite.count == 1)
check("and it is mine", flipped.rowsToWrite.allSatisfy { $0.userID == ME.raw })
check("no row of theirs is ever handed to the writer",
      !flipped.rowsToWrite.contains { $0.userID == SOMEONE_ELSE.raw })

// THE NUDGE. Both directions: render and transition.
check("another owner's nudge renders nothing", !card(nudge(owner: SOMEONE_ELSE)).visible)
check("and it says why, so a log can tell this from 'already connected'",
      card(nudge(owner: SOMEONE_ELSE)).hiddenBecause.contains("another owner"))
check("another owner's nudge cannot be declined from this phone",
      ConnectionsPolicy.recordDecline(nudge(owner: SOMEONE_ELSE), at: NOW,
                                      how: .saidNo, for: ME) == nil)
check("another owner's nudge cannot be tapped through from this phone",
      ConnectionsPolicy.recordTapped(nudge(owner: SOMEONE_ELSE), at: NOW,
                                     on: .ios, for: ME) == nil)
check("and neither can it via the action router",
      ConnectionsPolicy.nudgeAfter(action: .connect, on: nudge(owner: SOMEONE_ELSE),
                                   at: NOW, on: .ios, for: ME) == nil)

// A row off the wire whose owner is a name does not decode at all, so it never
// reaches a filter in the first place.
check("a wire row with a name for an owner does not decode",
      Connection(row: ["user_id": "omar", "toolkit": SLUG_A,
                       "connected_account_id": "ca_1", "status": "connected"]) == nil)
check("a wire row with a real owner id does decode",
      Connection(row: ["user_id": ME.raw, "toolkit": SLUG_A,
                       "connected_account_id": "ca_1", "status": "connected"]) != nil)
check("a nudge row with a name for an owner does not decode",
      ConnectNudge(row: ["user_id": "omar", "toolkit": SLUG_A,
                         "state": "asked", "level": 0]) == nil)

// ===========================================================================
// 2. THE CARD IN SETTINGS
// ===========================================================================

print("── settings cards ──")

let TWO_ACCOUNTS: [Connection] = [
    connection(account: "ca_work", alias: .work, writes: true, lastUsed: NOW - 7200),
    connection(account: "ca_home", alias: .personal, writes: true, lastUsed: NOW - 60),
]
let twoUp = ConnectionsPolicy.settingsCards(rows: TWO_ACCOUNTS, catalog: [META_A], for: ME)

check("two accounts on one app are one card", twoUp.count == 1)
check("and the card counts both", twoUp.first?.accounts == 2)
check("the card names the app from the catalog", twoUp.first?.name == "Aurora")
check("the card carries the catalog's logo", twoUp.first?.logoURL?.absoluteString
          == "https://cdn.example.test/aurora.png")
check("the aliases read as an account label", twoUp.first?.accountLabel == "work and personal")
check("last used is the most recent of the two", twoUp.first?.lastUsedAt == NOW - 60)

// NO APP IS HARDCODED, checked as a behaviour rather than promised in a
// comment. An app nobody has ever heard of renders exactly like any other, and
// the ONLY difference between the two cards is what the catalog said.
let invented = ToolkitMeta(slug: "qwertyapp", name: "Qwerty", logo: nil, scopes: ["x"])
let inventedCards = ConnectionsPolicy.settingsCards(
    rows: [connection(toolkit: "qwertyapp", writes: true)], catalog: [invented], for: ME)
let knownCards = ConnectionsPolicy.settingsCards(
    rows: [connection(toolkit: SLUG_A, writes: true)], catalog: [META_A], for: ME)
check("an app invented five seconds ago gets a full card", inventedCards.count == 1)
check("and it differs from a known app only in what the catalog said",
      inventedCards.first?.accounts == knownCards.first?.accounts
          && inventedCards.first?.status == knownCards.first?.status
          && inventedCards.first?.writesEnabled == knownCards.first?.writesEnabled
          && inventedCards.first?.accountLabel == knownCards.first?.accountLabel)

// A catalog that has nothing to say still has to produce a readable screen.
let noCatalog = ConnectionsPolicy.settingsCards(rows: [connection()], catalog: [], for: ME)
check("with no catalog row the card falls back to the slug",
      noCatalog.first?.name == SLUG_A)
let blankName = ToolkitMeta(slug: SLUG_A, name: "   ", logo: nil)
check("a catalog row with a blank name falls back too",
      ConnectionsPolicy.settingsCards(rows: [connection()], catalog: [blankName],
                                      for: ME).first?.name == SLUG_A)
check("a card built from nothing at all still names something",
      ConnectionsPolicy.appName(nil, fallback: "  ") == "that app")

// A logo is a URL handed to a network image view. A catalog row is a vendor's
// data, and this is a settings screen — nobody would go looking for a scheme
// check here, which is exactly why it has to be here.
check("an http logo is not accepted", ConnectionsPolicy.logoURL("http://x.test/a.png") == nil)
check("a javascript logo is not accepted",
      ConnectionsPolicy.logoURL("javascript:alert(1)") == nil)
check("a file logo is not accepted", ConnectionsPolicy.logoURL("file:///etc/passwd") == nil)
check("a nil logo is nil", ConnectionsPolicy.logoURL(nil) == nil)
check("an https logo survives",
      ConnectionsPolicy.logoURL("https://cdn.example.test/a.png") != nil)

// Status folding: one broken account makes the app broken on this screen,
// because it is broken for the person the moment they try to use it.
let oneStale: [Connection] = [
    connection(account: "ca_ok", alias: .work, status: .connected),
    connection(account: "ca_bad", alias: .personal, status: .needsReconnect),
]
check("one lapsed account makes the app read as needing reconnection",
      ConnectionsPolicy.settingsCards(rows: oneStale, catalog: [META_A], for: ME)
          .first?.status == .needsReconnect)

// History is not a connection.
check("a disconnected row is not on the screen",
      ConnectionsPolicy.settingsCards(rows: [connection(status: .disconnected)],
                                      catalog: [META_A], for: ME).isEmpty)

// Two apps sort by the name the person reads, not by the slug they never see.
let twoApps = ConnectionsPolicy.settingsCards(
    rows: [connection(toolkit: SLUG_B), connection(toolkit: SLUG_A)],
    catalog: [META_A, META_B], for: ME)
check("apps are sorted by the rendered name", twoApps.map(\.name) == ["Aurora", "Zebracorp"])

// A second account with the same alias must not render "work and work". The
// server's own `accountNote` does not de-duplicate today; this is a deliberate
// divergence, recorded here so the next reader knows it was a decision.
let twoWork: [Connection] = [
    connection(account: "ca_1", alias: .work), connection(account: "ca_2", alias: .work),
]
check("two accounts with the same alias read as one word",
      ConnectionsPolicy.settingsCards(rows: twoWork, catalog: [META_A], for: ME)
          .first?.accountLabel == "work")
check("an unnamed account leaves the label empty rather than inventing one",
      ConnectionsPolicy.settingsCards(rows: [connection(alias: nil)], catalog: [META_A],
                                      for: ME).first?.accountLabel == "")

// ===========================================================================
// 3. THE DISCONNECT CONFIRMATION — the sentence that must not lie
// ===========================================================================

print("── disconnect copy ──")

func disconnect(_ appName: String = "Aurora", attempted: Int = 1, revoked: Bool,
                deleted: Bool, unavailable: Bool = false) -> String {
    ConnectionsPolicy.disconnectConfirmation(
        result: DisconnectResult(appName: appName, attempted: attempted, revoked: revoked,
                                 deleted: deleted, revokeUnavailable: unavailable))
}

// BRANCH 1: it really was revoked. The word is licensed and it is used.
let clean = disconnect(revoked: true, deleted: true)
check("a real revoke may say access was revoked", clean.lowercased().contains("revoked"))
check("and it says the app is disconnected", clean.contains("Aurora"))

// BRANCH 2: THE 5%. Deleted here, still live at the provider. The word
// "revoked" is a claim about somebody else's system that we did not verify, and
// saying it is a lie they cannot detect until it matters.
let unrevoked = disconnect(revoked: false, deleted: true, unavailable: true)
check("an unrevokable disconnect never says revoke, in any form",
      !unrevoked.lowercased().contains("revoke"))
check("it says the app was disconnected here",
      unrevoked.contains("disconnected here"))
check("and it sends them to the app's own settings to finish the job",
      unrevoked.contains("own settings"))
check("and it names the app both times, so the sentence is actionable",
      unrevoked.components(separatedBy: "Aurora").count - 1 == 2)

// THE CONTRADICTION. A result claiming both a revoke and that revoking was
// impossible is a malformed row, and where a row contradicts itself the honest
// reading is the quiet one. Nothing else in the system can catch this.
let contradiction = disconnect(revoked: true, deleted: true, unavailable: true)
check("a result that claims a revoke AND that revoking was impossible does not claim one",
      !contradiction.lowercased().contains("revoke"))

// BRANCH 3: revoked but our own record survived. Both halves get said.
let halfDone = disconnect(revoked: true, deleted: false)
check("a revoke with our record left behind still says revoked",
      halfDone.lowercased().contains("revoked"))
check("and admits the entry is still on file", halfDone.contains("still on file"))

// BRANCH 4: nothing happened. "Nothing has changed" is the only honest thing
// to say, and it is far better than a "Done." that leaves a live token.
let nothing = disconnect(revoked: false, deleted: false)
check("a failed disconnect claims nothing", !nothing.lowercased().contains("revoke"))
check("and says plainly that nothing changed", nothing.contains("nothing has changed"))
check("and it does not say Done", !nothing.contains("Done"))

// BRANCH 5: there was nothing connected in the first place.
let none = disconnect(attempted: 0, revoked: false, deleted: false)
check("nothing connected is said as nothing to disconnect",
      none.contains("nothing to disconnect"))

// Several accounts folded into one answer: revoked is EVERY, unavailable is
// ANY. Somebody told "access revoked" when only one of two came back has been
// told something false about the one that still works.
let both = ConnectionsPolicy.combine([
    DisconnectResult(appName: "Aurora", attempted: 1, revoked: true, deleted: true,
                     revokeUnavailable: false),
    DisconnectResult(appName: "Aurora", attempted: 1, revoked: false, deleted: true,
                     revokeUnavailable: true),
], appName: "Aurora")
check("one account that could not be revoked makes the whole app unrevoked", !both.revoked)
check("and the app carries the unavailable flag", both.revokeUnavailable)
check("and both attempts are counted", both.attempted == 2)
check("so the copy for two accounts does not claim a revoke",
      !ConnectionsPolicy.disconnectConfirmation(result: both).lowercased().contains("revoke"))

let allRevoked = ConnectionsPolicy.combine([
    DisconnectResult(appName: "Aurora", attempted: 1, revoked: true, deleted: true,
                     revokeUnavailable: false),
    DisconnectResult(appName: "Aurora", attempted: 1, revoked: true, deleted: true,
                     revokeUnavailable: false),
], appName: "Aurora")
check("two clean revokes may say revoked",
      ConnectionsPolicy.disconnectConfirmation(result: allRevoked)
          .lowercased().contains("revoked"))
check("no results at all is not a revoke",
      !ConnectionsPolicy.combine([], appName: "Aurora").revoked)

// ===========================================================================
// 4. THE WRITE OPT-IN — off by default, and reads never wait on it
// ===========================================================================

print("── the write opt-in ──")

check("the write opt-in is OFF by default", ConnectionsPolicy.writesEnabledDefault == false)

// What a stored value reads as. Everything that is not `true` or `1` is off,
// and the asymmetry points the safe way: an unreadable opt-in withholds a
// privilege rather than granting one.
check("an absent column is off", ConnectionsPolicy.writesOptedIn(nil) == false)
check("false is off", ConnectionsPolicy.writesOptedIn(false) == false)
check("0 is off", ConnectionsPolicy.writesOptedIn(0) == false)
check("the string \"1\" is off", ConnectionsPolicy.writesOptedIn("1") == false)
check("the string \"true\" is off", ConnectionsPolicy.writesOptedIn("true") == false)
check("2 is off", ConnectionsPolicy.writesOptedIn(2) == false)
check("0.999 is off", ConnectionsPolicy.writesOptedIn(0.999) == false)
check("true is on", ConnectionsPolicy.writesOptedIn(true) == true)
check("1 is on", ConnectionsPolicy.writesOptedIn(1) == true)

// A row off the wire with the column missing is a read-only connection.
let wireRow = Connection(row: ["user_id": ME.raw, "toolkit": SLUG_A,
                              "connected_account_id": "ca_1", "status": "connected"])
check("a wire row with no opt-in column decodes as read-only",
      wireRow?.writesEnabled == false)

// THE POINT OF THE TOGGLE: A READ NEVER WAITS ON IT.
//
// If a read waited on the write toggle, the toggle would stop being a consent
// control and become an on/off switch for the product — every owner would turn
// it on to make anything work at all, which is the same as never having asked.
let readOnlyRows = [connection(writes: false)]
let writeRows = [connection(writes: true)]
check("a read is allowed with the toggle OFF",
      ConnectionsPolicy.mayUse(rows: readOnlyRows, toolkit: SLUG_A, access: .read, for: ME))
check("a read is allowed with the toggle ON",
      ConnectionsPolicy.mayUse(rows: writeRows, toolkit: SLUG_A, access: .read, for: ME))
check("the read decision is IDENTICAL in both toggle positions",
      ConnectionsPolicy.mayUse(rows: readOnlyRows, toolkit: SLUG_A, access: .read, for: ME)
          == ConnectionsPolicy.mayUse(rows: writeRows, toolkit: SLUG_A, access: .read, for: ME))
check("a write is refused with the toggle OFF",
      !ConnectionsPolicy.mayUse(rows: readOnlyRows, toolkit: SLUG_A, access: .write, for: ME))
check("a write is allowed with the toggle ON",
      ConnectionsPolicy.mayUse(rows: writeRows, toolkit: SLUG_A, access: .write, for: ME))
check("so the toggle changes the write answer and only the write answer",
      ConnectionsPolicy.mayUse(rows: readOnlyRows, toolkit: SLUG_A, access: .write, for: ME)
          != ConnectionsPolicy.mayUse(rows: writeRows, toolkit: SLUG_A, access: .write, for: ME))

// Nothing connected is not a licence for anything.
check("a read on an unconnected app is refused",
      !ConnectionsPolicy.mayUse(rows: [], toolkit: SLUG_A, access: .read, for: ME))
check("a read on a lapsed connection is refused",
      !ConnectionsPolicy.mayUse(rows: [connection(status: .needsReconnect, writes: true)],
                                toolkit: SLUG_A, access: .read, for: ME))

// SKEW. Writes need EVERY connected account opted in, not any: under "any",
// opting in for a personal account would license a write to a work one that was
// never offered the choice.
let skewed = [connection(account: "ca_1", alias: .work, writes: true),
              connection(account: "ca_2", alias: .personal, writes: false)]
check("one account without the opt-in refuses the write",
      !ConnectionsPolicy.mayUse(rows: skewed, toolkit: SLUG_A, access: .write, for: ME))
check("but reads still work, because reads never needed it",
      ConnectionsPolicy.mayUse(rows: skewed, toolkit: SLUG_A, access: .read, for: ME))
check("and the screen shows the toggle OFF, so it cannot claim a licence a write refuses",
      ConnectionsPolicy.writesEnabled(rows: skewed, toolkit: SLUG_A, for: ME) == false)
check("the screen's toggle and the write decision are the same predicate",
      ConnectionsPolicy.writesEnabled(rows: skewed, toolkit: SLUG_A, for: ME)
          == ConnectionsPolicy.mayUse(rows: skewed, toolkit: SLUG_A, access: .write, for: ME))
check("and the card agrees with both",
      ConnectionsPolicy.settingsCards(rows: skewed, catalog: [META_A], for: ME)
          .first?.writesEnabled == false)

// The transition itself.
let turnedOn = ConnectionsPolicy.writesTransition(rows: skewed, toolkit: SLUG_A,
                                                  to: true, for: ME)
check("turning it on moves every account on the app", turnedOn.accounts == 2)
check("and every row handed to the writer is opted in",
      turnedOn.rowsToWrite.allSatisfy(\.writesEnabled))
check("and it reports itself applied", turnedOn.applied && turnedOn.enabled)
let turnedOff = ConnectionsPolicy.writesTransition(rows: writeRows, toolkit: SLUG_A,
                                                   to: false, for: ME)
check("turning it off clears every row", turnedOff.rowsToWrite.allSatisfy { !$0.writesEnabled })
check("nothing connected means nothing to toggle",
      ConnectionsPolicy.writesTransition(rows: [], toolkit: SLUG_A, to: true, for: ME).applied
          == false)
check("and a toggle that did not apply does not report itself on",
      ConnectionsPolicy.writesTransition(rows: [], toolkit: SLUG_A, to: true,
                                         for: ME).enabled == false)
check("a lapsed connection is not toggled",
      ConnectionsPolicy.writesTransition(rows: [connection(status: .needsReconnect)],
                                         toolkit: SLUG_A, to: true, for: ME).applied == false)

// CONSENT IS TO A CONNECTION, NOT TO AN APP NAME. A disconnected row keeps its
// place as history and loses its opt-in, so a fresh connection months later
// cannot inherit a permission nobody granted it.
let gone = ConnectionsPolicy.afterDisconnect(connection(writes: true))
check("a disconnected row keeps its place as history", gone.status == .disconnected)
check("and loses the write opt-in it carried", gone.writesEnabled == false)
check("and stays with the same owner", gone.userID == ME.raw)

// ===========================================================================
// 5. ONE NUDGE RECORD, TWO SKINS
// ===========================================================================

print("── the nudge card ──")

// EVERY STATE IN THE CONTRACT IS COVERED, and the census below proves the list
// is complete rather than merely long.
var rendered: [NudgeState: NudgeCard] = [:]
rendered[.neverAsked] = card(nudge(state: .neverAsked, trigger: nil, sentAt: nil))
rendered[.asked] = card(nudge(state: .asked))
rendered[.declined] = card(nudge(state: .declined, level: 1, snoozeUntil: NOW + 14 * DAY))
// LEVEL 0 AND A SEVEN-DAY SNOOZE, which is the whole shape of the state: a
// setup-card skip does not climb the ladder, so a fixture at level 1 here would
// be a row the server can no longer write.
rendered[.declinedSoft] = card(nudge(state: .declinedSoft, level: 0,
                                     snoozeUntil: NOW + 7 * DAY, trigger: .onboarding))
rendered[.connected] = card(nudge(state: .connected, trigger: nil))
rendered[.needsReconnect] = card(nudge(state: .needsReconnect))

check("every state in the contract has a rendering",
      NudgeState.allCases.allSatisfy { rendered[$0] != nil })
check("the states are exactly the contract's, in order",
      NudgeState.allCases.map(\.rawValue) == CONTRACT_NUDGE_STATES)
check("the statuses are exactly the contract's",
      ConnectionStatus.allCases.map(\.rawValue) == CONTRACT_STATUSES)
check("the aliases are exactly the contract's",
      AccountAlias.allCases.map(\.rawValue) == CONTRACT_ALIASES)
check("the triggers are exactly the contract's",
      NudgeTrigger.allCases.map(\.rawValue) == CONTRACT_TRIGGERS)
check("the snooze ladder is exactly the contract's",
      ConnectionsPolicy.snoozeDays == CONTRACT_SNOOZE_DAYS)

// never_asked: nothing has been asked, so a card here would be the app asking
// out of nowhere — which every ask in this product is forbidden to be.
check("never_asked shows nothing", !rendered[.neverAsked]!.visible)
check("and says so", !rendered[.neverAsked]!.hiddenBecause.isEmpty)

// declined_soft: they walked past a setup card. Quiet, exactly like a decline —
// the difference between the two is not what this screen shows, it is what the
// ASK ENGINE may do afterwards, and that lives on the server.
let shrugged = rendered[.declinedSoft]!
check("a skipped setup card shows nothing", !shrugged.visible)
check("and it does not read as a refusal",
      shrugged.hiddenBecause != rendered[.declined]!.hiddenBecause)
// THE POINT OF THE STATE, said in the one place this app can say it: a shrug is
// not a no. Two states that hid for the same recorded reason would be one state
// with two names, and the next reader would collapse them again.
check("the two quiet states hide for reasons a person could tell apart",
      shrugged.hiddenBecause.contains("skipped")
          && rendered[.declined]!.hiddenBecause.contains("said no"))

// asked: the card IS the text, in the other skin.
let asked = rendered[.asked]!
check("asked shows a card", asked.visible)
check("it offers connect", asked.primary == .connect)
check("and a way out that is not a dismissal", asked.secondary == .notNow)
check("it names the app from the catalog", asked.headline.contains("Aurora"))
check("it says WHY, so the ask is never out of nowhere", !asked.why.isEmpty)
check("and it says, in one sentence, that this is optional",
      asked.optionalLine.contains("Entirely up to you"))
check("and the sentence says why it is optional: the browser does it either way",
      asked.optionalLine.contains("browser"))

// An ask with no moment behind it is an ask out of nowhere. An `asked` row with
// no sent time cannot tell ten minutes ago from March. Both are unreadable, and
// an unreadable row does not get to interrupt anybody.
check("an ask with no moment is not shown",
      !card(nudge(state: .asked, trigger: nil)).visible)
check("an ask with no sent time is not shown",
      !card(nudge(state: .asked, sentAt: nil)).visible)
check("and the two hide for different recorded reasons",
      card(nudge(state: .asked, trigger: nil)).hiddenBecause
          != card(nudge(state: .asked, sentAt: nil)).hiddenBecause)

// Every trigger produces its own why-line, and no two are the same sentence —
// otherwise the enum is decoration.
let whys = NudgeTrigger.allCases.map { ConnectionsPolicy.whyLine($0, app: "Aurora") }
check("every moment has a why-line", whys.allSatisfy { !$0.isEmpty })
check("and no two moments say the same thing", Set(whys).count == NudgeTrigger.allCases.count)
check("every trigger renders a visible card",
      NudgeTrigger.allCases.allSatisfy { card(nudge(state: .asked, trigger: $0)).visible })

// declined: hidden, and the two reasons for hiding are different facts. Level 3
// is the end of the ladder; a running snooze is not.
check("a declined ask is not on screen", !rendered[.declined]!.visible)
check("a third decline stops it for good",
      card(nudge(state: .declined, level: 3)).hiddenBecause.contains("three times"))
check("and that is a different reason from a running snooze",
      card(nudge(state: .declined, level: 3)).hiddenBecause
          != card(nudge(state: .declined, level: 1)).hiddenBecause)
check("the record itself knows it is stopped",
      nudge(state: .declined, level: 3).isStopped)
check("and one decline is not stopped", !nudge(state: .declined, level: 1).isStopped)

// connected: no ask to show. The app is on the Settings list instead, and one
// app with two rows is two rows that can disagree.
check("a connected app has no ask card", !rendered[.connected]!.visible)
check("and it says so, not 'belongs to another owner'",
      rendered[.connected]!.hiddenBecause.contains("already connected"))

// needs_reconnect: the ladder does not apply, and it is still optional.
let stale = rendered[.needsReconnect]!
check("a lapsed connection raises a card", stale.visible)
check("it offers reconnect, not connect", stale.primary == .reconnect)
check("it names the app", stale.headline.contains("Aurora"))
check("and it is STILL optional, because the browser still does the same work",
      stale.optionalLine.contains("Entirely up to you"))

// THE RULE WITH NO EXCEPTIONS: every visible card carries the optional line.
let everyRender: [NudgeCard] = NudgeState.allCases.flatMap { state -> [NudgeCard] in
    NudgeTrigger.allCases.map { card(nudge(state: state, trigger: $0)) }
}
check("every visible card, in every state and every moment, says it is optional",
      everyRender.filter(\.visible).allSatisfy { !$0.optionalLine.isEmpty })
check("every visible card has a headline and a why",
      everyRender.filter(\.visible).allSatisfy { !$0.headline.isEmpty && !$0.why.isEmpty })
check("every visible card offers a way to say not now",
      everyRender.filter(\.visible).allSatisfy { $0.secondary == .notNow })
check("every hidden card records a reason",
      everyRender.filter { !$0.visible }.allSatisfy { !$0.hiddenBecause.isEmpty })
check("and no hidden card leaks a sentence onto the screen",
      everyRender.filter { !$0.visible }.allSatisfy { $0.lines.isEmpty })

// A card renders from the record and nothing else: the same record with no
// catalog row still renders, using the slug.
check("with no catalog row the card still asks, by slug",
      card(nudge(state: .asked), meta: nil).headline.contains(SLUG_A))

// ---- ACT IN EITHER, THE OTHER FLIPS -------------------------------------

print("── the flip ──")

let openAsk = nudge(state: .asked, level: 0, trigger: .inTask)
let declined = ConnectionsPolicy.recordDecline(openAsk, at: NOW, how: .saidNo, for: ME)!
check("not now moves the record to declined", declined.state == .declined)
check("and advances the ladder one rung", declined.level == 1)
check("and snoozes for the contract's first interval",
      declined.snoozeUntil == NOW + Double(CONTRACT_SNOOZE_DAYS[0]) * DAY)
check("and stamps that they actually acted", declined.actedAt == NOW)
check("and the card for the new record is gone", !card(declined).visible)

// The same decline typed into the thread produces the same record. That is the
// twin claim, and it holds because there is one arithmetic, not two.
check("a decline from the app and a decline from the thread are one record",
      ConnectionsPolicy.nudgeAfter(action: .notNow, on: openAsk, at: NOW,
                                   on: .ios, for: ME) == declined)

// 72 hours of silence is a decline too, just a quieter one — and it must not
// claim an action nobody took.
let silent = ConnectionsPolicy.recordDecline(openAsk, at: NOW, how: .silence, for: ME)!
check("silence declines without claiming they acted", silent.actedAt == nil)
check("but it still advances the ladder", silent.level == 1)

let second = ConnectionsPolicy.recordDecline(declined, at: NOW, how: .saidNo, for: ME)!
check("a second decline snoozes for the second interval",
      second.snoozeUntil == NOW + Double(CONTRACT_SNOOZE_DAYS[1]) * DAY)
let third = ConnectionsPolicy.recordDecline(second, at: NOW, how: .saidNo, for: ME)!
check("a third decline is the end of the ladder", third.level == 3 && third.isStopped)
let fourth = ConnectionsPolicy.recordDecline(third, at: NOW, how: .saidNo, for: ME)!
check("a fourth decline cannot climb past three", fourth.level == 3)

// The onboarding exception: a card skipped during setup is a form refused, not
// an app refused — a SKIP, and the ladder does not move.
//
// THIS BLOCK USED TO ASSERT THE DEFECT. It fixed the NUMBER and left the
// sentence: seven days rather than fourteen, but state `.declined` and the
// ladder advanced to level 1 — and the server turns a level-1 decline into
// permanent silence for the two triggers that carry evidence. So walking past
// a card during setup ended the conversation about that app for good, which is
// the opposite of what a skip means. `ConnectOnboardingPolicy.skipOutcome` has
// always said so, and `agreesWithSkip` is the leg that caught the two files
// disagreeing (CI red on 2026-09-06). The expectation below is the contract's,
// not the old behaviour's.
let skipped = ConnectionsPolicy.recordDecline(nudge(state: .asked, trigger: .onboarding),
                                              at: NOW, how: .saidNo, for: ME)!
check("skipping a setup card snoozes 7 days, not 14",
      skipped.snoozeUntil == NOW + Double(ConnectionsPolicy.onboardingSkipSnoozeDays) * DAY)
check("and does not advance the ladder", skipped.level == 0)
check("and does not write the row down as a refusal of the app",
      skipped.state != .declined)
check("but it does record that they acted", skipped.actedAt == NOW)
let skippedTwice = ConnectionsPolicy.recordDecline(skipped, at: NOW, how: .saidNo, for: ME)!
check("skipping the same setup card again is still a skip, not a climb",
      skippedTwice.level == 0
        && skippedTwice.snoozeUntil == NOW + Double(ConnectionsPolicy.onboardingSkipSnoozeDays) * DAY)
// A refusal that is NOT the setup card still climbs, and that is the whole
// point of keeping the two apart.
let realNo = ConnectionsPolicy.recordDecline(nudge(state: .asked, trigger: .inTask),
                                             at: NOW, how: .saidNo, for: ME)!
check("a refusal outside setup is a decline and does climb",
      realNo.level == 1 && realNo.state == .declined)
let realNoTwice = ConnectionsPolicy.recordDecline(realNo, at: NOW, how: .saidNo, for: ME)!
check("and a second decline is a second decline",
      realNoTwice.snoozeUntil == NOW + Double(CONTRACT_SNOOZE_DAYS[1]) * DAY)

// Tapping through is NOT a connection. The connection lands when the provider
// says it landed; stamping `connected` on a tap puts an app on the Settings
// screen that nothing can use, and the person finds out when they rely on it.
let tapped = ConnectionsPolicy.recordTapped(openAsk, at: NOW, on: .ios, for: ME)!
check("tapping connect does not claim the app is connected", tapped.state == .asked)
check("it records that they acted", tapped.actedAt == NOW)
check("and on which skin", tapped.channel == .ios)
check("connect and reconnect route to the same transition",
      ConnectionsPolicy.nudgeAfter(action: .connect, on: openAsk, at: NOW, on: .ios, for: ME)
          == ConnectionsPolicy.nudgeAfter(action: .reconnect, on: openAsk, at: NOW,
                                          on: .ios, for: ME))
check("every action the card can offer has a transition",
      NudgeAction.allCases.allSatisfy {
          ConnectionsPolicy.nudgeAfter(action: $0, on: openAsk, at: NOW,
                                       on: .ios, for: ME) != nil
      })

// ===========================================================================
// 6. THE FORBIDDEN-VOCABULARY GATE
// ===========================================================================
// The app's copy is bound by the same rules as the SMS copy, so the check is
// the same check. It is a CEILING on our own output: its input is text WE are
// about to show and its only outcome is "do not show this". It never reads a
// human's words.

print("── the register ──")

check("authorize is refused", ConnectionsPolicy.forbiddenTerm(in: "Authorize it") == "authorize")
check("the British spelling too",
      ConnectionsPolicy.forbiddenTerm(in: "Please authorise") == "authorise")
check("grant access is refused",
      ConnectionsPolicy.forbiddenTerm(in: "You grant access to it") == "grant access")
check("permissions is refused",
      ConnectionsPolicy.forbiddenTerm(in: "Review the permissions") != nil)
check("integration is refused",
      ConnectionsPolicy.forbiddenTerm(in: "Set up the integration") != nil)
check("OAuth is refused", ConnectionsPolicy.forbiddenTerm(in: "Finish OAuth") == "oauth")
check("the vendor's name is refused",
      ConnectionsPolicy.forbiddenTerm(in: "Opening Composio now") == "composio")
check("and a bare vendor link is caught by the same entry",
      ConnectionsPolicy.forbiddenTerm(in: "tap connect.composio.dev/link/x") == "composio")

// The boundary is "not a lowercase letter and not a digit", exactly as the
// server's is — so a hyphen splits and a letter does not. Without this the list
// refuses ordinary English and every ask it eats is an interruption spent for
// nothing.
check("capital does not trip api", ConnectionsPolicy.saysNothingForbidden("Capital idea"))
check("therapist does not trip api", ConnectionsPolicy.saysNothingForbidden("her therapist"))
check("rapid does not trip api", ConnectionsPolicy.saysNothingForbidden("a rapid reply"))
check("API-key does trip api", ConnectionsPolicy.forbiddenTerm(in: "your API-key") == "api")
check("a bare API trips", ConnectionsPolicy.forbiddenTerm(in: "the API") == "api")
check("case does not matter", ConnectionsPolicy.forbiddenTerm(in: "AUTHORIZE") == "authorize")
check("a curly apostrophe does not hide a term",
      ConnectionsPolicy.forbiddenTerm(in: "the app\u{2019}s permissions") != nil)
check("ordinary copy passes",
      ConnectionsPolicy.saysNothingForbidden("Connect your Aurora? Entirely up to you."))

// AND NOW THE PRODUCT'S OWN COPY, EXHAUSTIVELY. Every sentence this file can
// put in front of a person, in every state and every branch, goes through the
// gate. This is the part that would catch a well-meaning rewrite six months
// from now.
var everyLine: [String] = []
for state in NudgeState.allCases {
    for trigger in NudgeTrigger.allCases {
        everyLine += card(nudge(state: state, trigger: trigger), meta: META_A).lines
        everyLine += card(nudge(state: state, trigger: trigger), meta: nil).lines
    }
}
for revoked in [true, false] {
    for deleted in [true, false] {
        for unavailable in [true, false] {
            for attempted in [0, 1, 2] {
                everyLine.append(disconnect(attempted: attempted, revoked: revoked,
                                            deleted: deleted, unavailable: unavailable))
            }
        }
    }
}
for status in ConnectionStatus.allCases { everyLine.append(ConnectionsPolicy.statusLine(status)) }
for on in [true, false] { everyLine.append(ConnectionsPolicy.writesLine(on)) }
everyLine.append(ConnectionsPolicy.optionalLine(app: "Aurora"))

check("the product's own copy is not empty (the sweep would pass on nothing)",
      everyLine.count > 60)
if let bad = ConnectionsPolicy.firstForbidden(in: everyLine) {
    check("every sentence this policy can show passes the register — found \"\(bad.term)\" in \"\(bad.line)\"",
          false)
} else {
    check("every sentence this policy can show passes the register", true)
}
check("and none of them raises its voice",
      everyLine.allSatisfy { !$0.contains("!") })

// ---------------------------------------------------------------------------
// THE TWO LINES THAT SAY WHAT IS TRUE OF SOMEBODY'S ACCOUNT
// ---------------------------------------------------------------------------
//
// Every other assertion about these two compares the model's output against
// ConnectionsPolicy.statusLine(...) and ConnectionsPolicy.writesLine(...) —
// the implementation as its own oracle. An audit on 2026-09-06 SWAPPED the two
// writesLine strings, so a read-only connection rendered as "I can make
// changes", and ran all four connect-related iOS suites: every one exited 0.
// It did the same to statusLine(.needsReconnect), making a dead credential
// render as "Connected", with the same result.
//
// A person reading "I can make changes" over a connection that cannot, or
// "Connected" over one that has stopped working, has been told something false
// about their own account by a screen whose entire job is to be true about it.
// So these are pinned to the WORDS, which is the only thing a copied oracle
// cannot follow.

check("a live connection says Connected",
      ConnectionsPolicy.statusLine(.connected) == "Connected")
check("a dead credential does NOT say Connected",
      ConnectionsPolicy.statusLine(.needsReconnect) == "Needs connecting again")
check("and one that was never connected says so",
      ConnectionsPolicy.statusLine(.disconnected) == "Not connected")
check("no two statuses share a line, so the card cannot show one state as another",
      Set(ConnectionStatus.allCases.map { ConnectionsPolicy.statusLine($0) }).count
        == ConnectionStatus.allCases.count)

check("the write opt-in ON says Anticipy can act",
      ConnectionsPolicy.writesLine(true) == "I can make changes")
check("the write opt-in OFF says it only reads",
      ConnectionsPolicy.writesLine(false) == "Reading only")
check("the two write lines are not the same sentence",
      ConnectionsPolicy.writesLine(true) != ConnectionsPolicy.writesLine(false))
// The direction, stated once more in the form a swap actually breaks: only the
// ON line may promise a change, and the OFF line must not.
check("only the ON line mentions changing anything",
      ConnectionsPolicy.writesLine(true).lowercased().contains("change")
        && !ConnectionsPolicy.writesLine(false).lowercased().contains("change"))
check("and only the OFF line says reading",
      ConnectionsPolicy.writesLine(false).lowercased().contains("read")
        && !ConnectionsPolicy.writesLine(true).lowercased().contains("read"))

// The one thing the gate deliberately does NOT do: censor an app's own name.
// A vendor calling itself something on the list gets called that; the check is
// on the sentences around the name, and pretending otherwise would render a
// card that cannot name the app the person is looking at.
let awkward = ToolkitMeta(slug: "apitools", name: "API Tools", logo: nil, scopes: ["x"])
let awkwardCard = card(nudge(state: .asked), meta: awkward)
check("an app whose own name is on the list is still named",
      awkwardCard.visible && awkwardCard.headline.contains("API Tools"))
check("and our own sentence around it is still clean",
      ConnectionsPolicy.saysNothingForbidden(
          ConnectionsPolicy.optionalLine(app: "<app>")))

// ===========================================================================
// 7. THE CONTRACT'S OTHER CONSTANTS
// ===========================================================================

check("the ask cap is the contract's 7 days", ConnectionsPolicy.globalAskIntervalDays == 7)
check("silence matures at the contract's 72 hours",
      ConnectionsPolicy.silenceIsASoftNoHours == 72)
check("our link lives ten minutes", ConnectionsPolicy.linkTTLSeconds == 600)
check("and it is OUR link, never the vendor's",
      ConnectionsPolicy.connectLinkPrefix == "https://anticipy.ai/c/")
check("the link prefix names no vendor",
      ConnectionsPolicy.saysNothingForbidden(ConnectionsPolicy.connectLinkPrefix))

print(failures == 0 ? "all connections policy checks passed" : "\(failures) FAILED")
exit(failures == 0 ? 0 : 1)
