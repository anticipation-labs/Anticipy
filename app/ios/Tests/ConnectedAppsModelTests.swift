// SETTINGS → CONNECTED APPS: the screen's decisions, without a phone.
//
// Compiled against the REAL production sources by the runner
// (`sh app/ios/Tests/run_connected_apps_tests.sh`) — the model AND
// `ConnectionsPolicy`, which owns the contract's own vocabulary. There is no
// copy of either here to drift from what ships.
//
// Six legs, and they are the screen's half of the feature. What a connection
// IS, what an owner id is, and what a disconnect may claim belong to
// `ConnectionsPolicy` and to its own suite; this one asks what the SCREEN does
// with those answers:
//
//   1. THE LIST       one owner's rows and nobody else's — across a sign-in, a
//                     sign-out, and a response that lands after either
//   2. THE SCREENS    five states, and in particular: a list that could not be
//                     read is never rendered as "you have nothing connected"
//   3. THE SWITCH     "let Anticipy make changes" moves at once, moves BACK
//                     when the write does not land, says so, and moves every
//                     account on the app together
//   4. THE DISCONNECT asked first; then whatever the provider actually did,
//                     said in the contract's own words
//   5. THE SEARCH     the catalog answers and this file does not judge it; a
//                     stale answer loses to a newer one
//   6. THE WORDS      every sentence the screen writes, through the same
//                     register gate the nudge card and the text thread pass
//
// The app names here are INVENTED, and that is the point: they exist only in
// this file's fixtures. The runner refuses a real one in the model or the view.
//
// The mutation that turns leg 3 red: keep the optimistic value when the write
// throws. The mutation that turns leg 1 red: answer `rows(for:)` from stored
// state without comparing the owner.
import Foundation

private var failures = 0

@MainActor
private func check(_ name: String, _ ok: Bool, _ detail: String = "") {
    print("\(ok ? "PASS" : "FAIL"): \(name)\(ok || detail.isEmpty ? "" : "  -> \(detail)")")
    if !ok { failures += 1 }
}

private typealias Model = ConnectedAppsModel

// Two real-shaped owner row ids: fifteen lowercase alphanumerics, as
// contract.ts mints them.
private let ownerA = OwnerId("sxkotd1h02qb6gw")!
private let ownerB = OwnerId("qeuy6sv1raof9rw")!

// ---------------------------------------------------------------- the double

@MainActor
private final class FakeStore: ConnectedAppsStore {
    struct Refused: Error {}

    var rows: [Connection] = []
    var meta: [ToolkitMeta] = []
    var hits: [ToolkitMeta] = []
    /// What `disconnect` reports for one account, keyed by account id; the
    /// default answers for anything not named.
    var outcomes: [String: DisconnectResult] = [:]
    var outcome = DisconnectResult(appName: "", attempted: 1, revoked: true,
                                   deleted: true, revokeUnavailable: false)

    var connectionsThrows = false
    var describeThrows = false
    var catalogThrows = false
    var writeThrows = false
    var disconnectThrows = false

    private(set) var seenOwners: [String] = []
    private(set) var connectionsCalls = 0
    private(set) var describeCalls: [[String]] = []
    private(set) var catalogQueries: [String] = []
    private(set) var writeCalls: [(owner: String, rows: [Connection])] = []
    private(set) var disconnectCalls: [(owner: String, account: String)] = []

    /// Runs INSIDE a call, after the model has done whatever it does before
    /// waiting and before the answer comes back. It is how a change of account
    /// mid-flight, and a slow answer overtaken by a fast one, are made to
    /// happen at an exact instant rather than approximately.
    var beforeReturn: (@MainActor () async -> Void)?

    private func enter(_ owner: OwnerId) async {
        seenOwners.append(owner.raw)
        if let hook = beforeReturn { await hook() }
    }

    func connections(owner: OwnerId) async throws -> [Connection] {
        connectionsCalls += 1
        // The answer is fixed when the call is MADE, like a real response in
        // flight. Reading it after the hook would make a stale answer and a
        // fresh one identical, and a race test that cannot fail is decoration.
        let answer = rows
        await enter(owner)
        if connectionsThrows { throw Refused() }
        return answer
    }

    func describe(toolkits: [String], owner: OwnerId) async throws -> [ToolkitMeta] {
        describeCalls.append(toolkits)
        let answer = meta.filter { toolkits.contains($0.slug) }
        await enter(owner)
        if describeThrows { throw Refused() }
        return answer
    }

    func catalog(matching query: String, owner: OwnerId) async throws -> [ToolkitMeta] {
        catalogQueries.append(query)
        let answer = hits
        await enter(owner)
        if catalogThrows { throw Refused() }
        return answer
    }

    func setWrites(_ rows: [Connection], owner: OwnerId) async throws {
        writeCalls.append((owner.raw, rows))
        await enter(owner)
        if writeThrows { throw Refused() }
    }

    func disconnect(owner: OwnerId, connectedAccountID: String) async throws -> DisconnectResult {
        disconnectCalls.append((owner.raw, connectedAccountID))
        let answer = outcomes[connectedAccountID] ?? outcome
        await enter(owner)
        if disconnectThrows { throw Refused() }
        return answer
    }
}

// -------------------------------------------------------------- the fixtures
//
// INVENTED APPS. Nothing in the product may know these names; they arrive here
// the way a real catalog's 1,400 arrive at the phone — as data.

private let fernwood = ToolkitMeta(slug: "fernwood", name: "Fernwood Notes",
                                   logo: "https://logos.example/fernwood.png",
                                   description: "Notes and pages")
private let harbour = ToolkitMeta(slug: "harbour", name: "Harbour Mail")
private let quokka = ToolkitMeta(slug: "quokka", name: "Quokka Post")
/// A catalog row that cannot name itself. It is not a row anybody can render.
private let nameless = ToolkitMeta(slug: "nameless", name: "  ")

private func connection(owner: OwnerId,
                        toolkit: String,
                        account: String,
                        alias: AccountAlias? = .work,
                        status: ConnectionStatus = .connected,
                        writes: Bool = false,
                        lastUsed: Double? = nil) -> Connection {
    Connection(userID: owner.raw, toolkit: toolkit, connectedAccountID: account,
               alias: alias, status: status, writesEnabled: writes, lastUsedAt: lastUsed)
}

/// The clock stands still an hour past the epoch's millionth second, so every
/// "last used" sentence in here is arithmetic anybody can check.
private let rightNow = Date(timeIntervalSince1970: 1_000_000)

@MainActor
private func loadedModel(rows: [Connection],
                         meta: [ToolkitMeta] = [fernwood, harbour, quokka])
    async -> (Model, FakeStore) {
    let store = FakeStore()
    store.rows = rows
    store.meta = meta
    let model = Model(store: store, now: { rightNow })
    model.signIn(ownerA)
    await model.load()
    return (model, store)
}

@main
@MainActor
private enum ConnectedAppsModelTests {
    static func main() async {

        // ======================================================== 1. THE LIST
        //
        // THE FAILURE THIS IS SHAPED AROUND: during the week-1 spike one
        // operator's own mailbox was connected by hand and had to be revoked
        // and deleted. Every door here is handed a MIXED list on purpose.
        let (listed, listStore) = await loadedModel(rows: [
            connection(owner: ownerA, toolkit: "fernwood", account: "ca_1",
                       lastUsed: rightNow.timeIntervalSince1970 - 3600),
            connection(owner: ownerA, toolkit: "harbour", account: "ca_3",
                       alias: .personal, status: .needsReconnect),
            connection(owner: ownerA, toolkit: "quokka", account: "ca_9",
                       alias: nil, status: .disconnected),
            connection(owner: ownerB, toolkit: "quokka", account: "ca_2"),
        ])
        let listRows = listed.rows(for: ownerA)
        check("another owner's connection never reaches the list",
              !listRows.contains { $0.card.toolkit == "quokka" },
              listRows.map(\.id).joined(separator: ","))
        check("a disconnected connection is not drawn",
              listRows.map(\.id) == ["fernwood", "harbour"],
              listRows.map(\.id).joined(separator: ","))
        check("the name and the logo come from the catalog",
              listRows[0].name == "Fernwood Notes"
                  && listRows[0].logoURL?.absoluteString == "https://logos.example/fernwood.png")
        check("the account label is the row's own", listRows[1].accountLabel == "personal")
        check("the status is said in the contract's words",
              listRows[0].statusWords == ConnectionsPolicy.statusLine(.connected)
                  && listRows[1].statusWords == ConnectionsPolicy.statusLine(.needsReconnect))
        check("the read/write line is the contract's too",
              listRows[0].writesWords == ConnectionsPolicy.writesLine(false))
        check("last used is said in the app's one wording",
              listRows[0].lastUsedWords == "Last used 1 hr ago", listRows[0].lastUsedWords)
        check("a connection never used says so rather than naming a date",
              listRows[1].lastUsedWords == "Not used yet")
        check("asking for another owner's rows returns nothing at all",
              listed.rows(for: ownerB).isEmpty)
        check("the store was asked for this owner and no other",
              Set(listStore.seenOwners) == [ownerA.raw])

        // The catalog is not the list. Losing it costs the pretty names, not
        // the truth about what is connected.
        let mute = FakeStore()
        mute.rows = [connection(owner: ownerA, toolkit: "fernwood", account: "ca_1")]
        mute.describeThrows = true
        let muteModel = Model(store: mute, now: { rightNow })
        muteModel.signIn(ownerA)
        await muteModel.load()
        check("a catalog that cannot be reached leaves the row under its slug",
              muteModel.rows(for: ownerA).map(\.name) == ["fernwood"])
        if case .apps = muteModel.screen(for: ownerA) {
            check("a silent catalog is still a list of apps", true)
        } else {
            check("a silent catalog is still a list of apps", false)
        }

        // The account on this phone changes.
        let (handed, _) = await loadedModel(rows: [
            connection(owner: ownerA, toolkit: "fernwood", account: "ca_1"),
        ])
        handed.signIn(ownerB)
        check("signing in as somebody else leaves nothing of the last account",
              handed.rows(for: ownerA).isEmpty && handed.rows(for: ownerB).isEmpty)
        check("the new account waits for its own list rather than inheriting one",
              handed.screen(for: ownerB) == .loading(Model.Copy.loading))

        // ... and changes DURING a read.
        let racing = FakeStore()
        racing.rows = [connection(owner: ownerA, toolkit: "fernwood", account: "ca_1")]
        let racedModel = Model(store: racing, now: { rightNow })
        racedModel.signIn(ownerA)
        racing.beforeReturn = { [weak racedModel] in
            racing.beforeReturn = nil
            racedModel?.signIn(ownerB)
        }
        await racedModel.load()
        check("a list that arrives after the account changed reaches nobody",
              racedModel.rows(for: ownerA).isEmpty && racedModel.rows(for: ownerB).isEmpty)
        check("the new account is still waiting for its own list",
              racedModel.screen(for: ownerB) == .loading(Model.Copy.loading))

        // ===================================================== 2. THE SCREENS
        let (empty, _) = await loadedModel(rows: [])
        check("somebody with nothing connected is invited, not shown an error",
              empty.screen(for: ownerA) == .invitation(Model.Copy.invitation))
        check("the invitation reads as an invitation",
              Model.Copy.invitation.contains("Connect an app")
                  && !Model.Copy.invitation.lowercased().contains("error"))
        check("the screen says in one sentence that none of this is required",
              Model.Copy.optional.contains("browser")
                  && Model.Copy.optional.split(separator: ".").count == 1)

        let brokenStore = FakeStore()
        brokenStore.connectionsThrows = true
        let broken = Model(store: brokenStore, now: { rightNow })
        broken.signIn(ownerA)
        await broken.load()
        check("a list that could not be read is trouble, never an empty invitation",
              broken.screen(for: ownerA) == .trouble(Model.Copy.trouble))
        check("the trouble sentence says it is a reach failure, not an empty shelf",
              Model.Copy.trouble.contains("not a sign that nothing is connected"))

        let signedOut = Model(store: FakeStore(), now: { rightNow })
        check("a screen with nobody signed in shows nothing and says so",
              signedOut.screen(for: ownerA) == .signedOut(Model.Copy.signedOut))
        check("a screen asked about nobody shows nothing",
              signedOut.screen(for: nil) == .signedOut(Model.Copy.signedOut))
        check("the wrong owner is shown nothing even on a loaded screen",
              empty.screen(for: ownerB) == .signedOut(Model.Copy.signedOut))

        // ====================================================== 3. THE SWITCH
        // Two accounts on one app: the toggle is per APP, so they move together
        // and the screen's position is the AND of them.
        let (toggling, toggleStore) = await loadedModel(rows: [
            connection(owner: ownerA, toolkit: "fernwood", account: "ca_1", writes: false),
            connection(owner: ownerA, toolkit: "fernwood", account: "ca_2",
                       alias: .personal, writes: false),
            connection(owner: ownerB, toolkit: "fernwood", account: "ca_x", writes: true),
        ])
        check("one card for one app, however many accounts are on it",
              toggling.rows(for: ownerA).count == 1
                  && toggling.rows(for: ownerA)[0].card.accounts == 2)
        check("the write opt-in is off until somebody turns it on",
              toggling.rows(for: ownerA)[0].writesEnabled == false)
        check("the switch says what it does in both positions",
              toggling.rows(for: ownerA)[0].writesDetail.contains("only read")
                  && toggling.rows(for: ownerA)[0].writesDetail.contains("Fernwood Notes"))

        // Optimistic: the row reads ON while the write is still in the air.
        var sawOptimistic = false
        toggleStore.beforeReturn = { [weak toggling] in
            toggleStore.beforeReturn = nil
            sawOptimistic = toggling?.rows(for: ownerA).first?.writesEnabled == true
        }
        var outcome = await toggling.setWrites(true, toolkit: "fernwood", owner: ownerA)
        check("the switch moves before the write lands", sawOptimistic)
        check("a write that lands leaves the switch on and says nothing",
              outcome == .saved && toggling.rows(for: ownerA)[0].writesEnabled
                  && toggling.notice == nil)
        check("every account on the app moved together, and only this owner's",
              toggleStore.writeCalls.count == 1
                  && toggleStore.writeCalls[0].owner == ownerA.raw
                  && toggleStore.writeCalls[0].rows.count == 2
                  && toggleStore.writeCalls[0].rows.allSatisfy { $0.userID == ownerA.raw }
                  && toggleStore.writeCalls[0].rows.allSatisfy(\.writesEnabled))
        check("the other owner's row on the same app was never written",
              toggleStore.writeCalls[0].rows.allSatisfy { $0.connectedAccountID != "ca_x" })

        toggleStore.writeThrows = true
        outcome = await toggling.setWrites(false, toolkit: "fernwood", owner: ownerA)
        check("a write that fails puts the switch back",
              toggling.rows(for: ownerA)[0].writesEnabled == true)
        if case .reverted(let said) = outcome {
            check("a write that fails tells the person, by name",
                  said.contains("Fernwood Notes") && said == toggling.notice)
            check("the sentence says the switch went back and nothing changed",
                  said.contains("gone back") && said.contains("nothing about it changed"))
        } else {
            check("a write that fails tells the person, by name", false, "\(outcome)")
        }

        toggleStore.writeThrows = false
        outcome = await toggling.setWrites(false, toolkit: "fernwood", owner: ownerA)
        check("the switch still works after a failure",
              outcome == .saved && toggling.rows(for: ownerA)[0].writesEnabled == false)

        let callsBefore = toggleStore.writeCalls.count
        check("turning the switch to where it already is sends nothing",
              await toggling.setWrites(false, toolkit: "fernwood", owner: ownerA) == .saved
                  && toggleStore.writeCalls.count == callsBefore)
        check("a switch flipped for another owner sends nothing at all",
              await toggling.setWrites(true, toolkit: "fernwood", owner: ownerB) == .refused
                  && toggleStore.writeCalls.count == callsBefore)
        check("a switch flipped on an app that is not connected sends nothing",
              await toggling.setWrites(true, toolkit: "nothing_here", owner: ownerA) == .refused
                  && toggleStore.writeCalls.count == callsBefore)
        check("nothing was ever written for anybody but this owner",
              toggleStore.writeCalls.allSatisfy { $0.owner == ownerA.raw })

        // A SKEWED app — one account opted in, one not — is not "already
        // there": the card reads OFF, and turning it on has work to do.
        let (skewed, skewStore) = await loadedModel(rows: [
            connection(owner: ownerA, toolkit: "harbour", account: "ca_5", writes: true),
            connection(owner: ownerA, toolkit: "harbour", account: "ca_6",
                       alias: .personal, writes: false),
        ])
        check("one account without the opt-in turns the app's switch off",
              skewed.rows(for: ownerA)[0].writesEnabled == false)
        check("turning a skewed app on writes every account",
              await skewed.setWrites(true, toolkit: "harbour", owner: ownerA) == .saved
                  && skewStore.writeCalls.count == 1
                  && skewStore.writeCalls[0].rows.count == 2)

        // The account changes while the write is in the air.
        let (switching, switchStore) = await loadedModel(rows: [
            connection(owner: ownerA, toolkit: "fernwood", account: "ca_1", writes: false),
        ])
        switchStore.writeThrows = true
        switchStore.beforeReturn = { [weak switching] in
            switchStore.beforeReturn = nil
            switching?.signIn(ownerB)
        }
        outcome = await switching.setWrites(true, toolkit: "fernwood", owner: ownerA)
        check("a failed write for the last account says nothing to the new one",
              outcome == .refused && switching.notice == nil)
        check("and it leaves the new account's screen empty",
              switching.rows(for: ownerB).isEmpty)

        // ================================================== 4. THE DISCONNECT
        let (asking, askStore) = await loadedModel(rows: [
            connection(owner: ownerA, toolkit: "fernwood", account: "ca_1"),
        ])
        check("nothing is disconnected before the question is asked",
              await asking.confirmDisconnect(owner: ownerA) == .refused
                  && askStore.disconnectCalls.isEmpty
                  && asking.rows(for: ownerA).count == 1)

        asking.askToDisconnect("fernwood", owner: ownerA)
        guard let pending = asking.pendingDisconnect else {
            check("the question is posed before anything happens", false)
            exit(1)
        }
        check("the question is posed before anything happens",
              pending.question.contains("Fernwood Notes")
                  && pending.detail.contains("connect it again")
                  && !pending.confirmWords.isEmpty && !pending.cancelWords.isEmpty)
        check("posing the question touches nothing", askStore.disconnectCalls.isEmpty)
        asking.cancelDisconnect()
        check("keeping it cancels the question and touches nothing",
              asking.pendingDisconnect == nil && askStore.disconnectCalls.isEmpty
                  && asking.rows(for: ownerA).count == 1)

        asking.askToDisconnect("fernwood", owner: ownerB)
        check("another owner cannot even pose the question",
              asking.pendingDisconnect == nil)
        check("and confirming without a question does nothing",
              await asking.confirmDisconnect(owner: ownerB) == .refused
                  && askStore.disconnectCalls.isEmpty)

        // Cut off at the far end and forgotten here.
        asking.askToDisconnect("fernwood", owner: ownerA)
        askStore.outcome = DisconnectResult(appName: "", attempted: 1, revoked: true,
                                            deleted: true, revokeUnavailable: false)
        var verdict = await asking.confirmDisconnect(owner: ownerA)
        if case .reported(let result, let said) = verdict {
            check("a full disconnect reports both halves",
                  result.revoked && result.deleted && result.attempted == 1)
            check("and says so in the contract's own sentence",
                  said == ConnectionsPolicy.disconnectConfirmation(result: result)
                      && said == asking.notice)
        } else {
            check("a full disconnect reports both halves", false, "\(verdict)")
        }
        check("the disconnected app leaves the list", asking.rows(for: ownerA).isEmpty)
        check("the disconnect went out for this owner and this account",
              askStore.disconnectCalls.count == 1
                  && askStore.disconnectCalls[0].owner == ownerA.raw
                  && askStore.disconnectCalls[0].account == "ca_1")

        // THE 5% BRANCH: the provider could not cut it off for us.
        let (partial, partialStore) = await loadedModel(rows: [
            connection(owner: ownerA, toolkit: "harbour", account: "ca_3"),
        ])
        partialStore.outcome = DisconnectResult(appName: "", attempted: 1, revoked: false,
                                                deleted: true, revokeUnavailable: true)
        partial.askToDisconnect("harbour", owner: ownerA)
        verdict = await partial.confirmDisconnect(owner: ownerA)
        if case .reported(_, let said) = verdict {
            check("a disconnect the far end would not do never claims it was revoked",
                  !said.lowercased().contains("revoked")
                      && said.contains("may still list"))
        } else {
            check("a disconnect the far end would not do never claims it was revoked",
                  false, "\(verdict)")
        }
        check("it still leaves this side's list", partial.rows(for: ownerA).isEmpty)

        // Two accounts, one app, and only one of them let go.
        let (half, halfStore) = await loadedModel(rows: [
            connection(owner: ownerA, toolkit: "fernwood", account: "ca_1"),
            connection(owner: ownerA, toolkit: "fernwood", account: "ca_2", alias: .personal),
        ])
        halfStore.outcomes = [
            "ca_1": DisconnectResult(appName: "", attempted: 1, revoked: true,
                                     deleted: true, revokeUnavailable: false),
            "ca_2": DisconnectResult(appName: "", attempted: 1, revoked: false,
                                     deleted: false, revokeUnavailable: false),
        ]
        half.askToDisconnect("fernwood", owner: ownerA)
        verdict = await half.confirmDisconnect(owner: ownerA)
        check("every account on the app is disconnected, not just the first",
              halfStore.disconnectCalls.map(\.account) == ["ca_1", "ca_2"])
        if case .reported(let result, let said) = verdict {
            check("one account that would not go means the app did not go",
                  !result.revoked && !result.deleted && result.attempted == 2)
            check("and the person is not told it is done",
                  !said.lowercased().contains("revoked"))
        } else {
            check("one account that would not go means the app did not go", false)
        }
        check("the account that is still live keeps the card on the screen",
              half.rows(for: ownerA).map(\.id) == ["fernwood"]
                  && half.rows(for: ownerA)[0].card.accounts == 1)

        // AN APP THAT NEEDS SIGNING IN AGAIN IS STILL DISCONNECTABLE. It was
        // not: `connectedRows` means `status == .connected`, so the one card a
        // person most wants gone answered "there's nothing to disconnect" about
        // a row they were looking at, and left it on the screen.
        let (broken2, brokenStore2) = await loadedModel(rows: [
            connection(owner: ownerA, toolkit: "harbour", account: "ca_7",
                       status: .needsReconnect),
        ])
        check("a connection that needs signing in again is still on the screen",
              broken2.rows(for: ownerA).map(\.id) == ["harbour"])
        broken2.askToDisconnect("harbour", owner: ownerA)
        verdict = await broken2.confirmDisconnect(owner: ownerA)
        check("and it can be disconnected like any other",
              brokenStore2.disconnectCalls.map(\.account) == ["ca_7"]
                  && broken2.rows(for: ownerA).isEmpty)
        if case .reported(let result, let said) = verdict {
            check("and is not told there was nothing to disconnect",
                  result.attempted == 1 && !said.contains("nothing to disconnect"))
        } else {
            check("and is not told there was nothing to disconnect", false)
        }

        // The notice is news, and news can be put away.
        check("the sentence about what just happened can be dismissed",
              broken2.notice != nil)
        broken2.dismissNotice()
        check("and dismissing it leaves the screen alone",
              broken2.notice == nil && broken2.screen(for: ownerA) == .invitation(Model.Copy.invitation))

        // Nothing reached the provider at all.
        let (stuck, stuckStore) = await loadedModel(rows: [
            connection(owner: ownerA, toolkit: "quokka", account: "ca_4"),
        ])
        stuckStore.disconnectThrows = true
        stuck.askToDisconnect("quokka", owner: ownerA)
        verdict = await stuck.confirmDisconnect(owner: ownerA)
        if case .reported(let result, let said) = verdict {
            check("a disconnect that could not be sent revokes and deletes nothing",
                  !result.revoked && !result.deleted)
            check("and says nothing has changed",
                  said == ConnectionsPolicy.disconnectConfirmation(result: result))
        } else {
            check("a disconnect that could not be sent revokes and deletes nothing", false)
        }
        check("and the app is still on the screen",
              stuck.rows(for: ownerA).map(\.id) == ["quokka"])

        // ====================================================== 5. THE SEARCH
        let (searching, searchStore) = await loadedModel(rows: [
            connection(owner: ownerA, toolkit: "fernwood", account: "ca_1"),
        ])
        check("an empty box asks the catalog nothing",
              searching.searchState == .idle(Model.Copy.searchPrompt)
                  && searchStore.catalogQueries.isEmpty)
        await searching.search("   ", owner: ownerA)
        check("whitespace asks the catalog nothing",
              searchStore.catalogQueries.isEmpty
                  && searching.searchState == .idle(Model.Copy.searchPrompt))

        // WHAT THE CATALOG SAYS IS WHAT THE SCREEN SHOWS. These hits do not
        // contain the letters that were typed, and nothing here re-judges them:
        // deciding which app somebody's letters mean is a meaning question and
        // it does not belong to a phone.
        searchStore.hits = [quokka, fernwood, nameless, harbour]
        await searching.search("notes for work", owner: ownerA)
        check("the catalog was asked exactly what was typed",
              searchStore.catalogQueries == ["notes for work"])
        if case .results(let found) = searching.searchState {
            check("the catalog's answer is shown in the order it came back",
                  found.map(\.meta.slug) == ["quokka", "fernwood", "harbour"],
                  found.map(\.meta.slug).joined(separator: ","))
            check("a catalog row that cannot name itself is not offered",
                  !found.contains { $0.meta.slug == "nameless" })
            check("an app already connected says so instead of offering again",
                  found.first { $0.meta.slug == "fernwood" }?.alreadyConnected == true
                      && found.first { $0.meta.slug == "quokka" }?.alreadyConnected == false)
        } else {
            check("the catalog's answer is shown in the order it came back", false,
                  "\(searching.searchState)")
        }

        searchStore.hits = []
        await searching.search("zzz", owner: ownerA)
        check("nothing found quotes what was asked",
              searching.searchState == .nothingFound(Model.Copy.nothingFound(query: "zzz"))
                  && Model.Copy.nothingFound(query: "zzz").contains("zzz"))

        searchStore.catalogThrows = true
        await searching.search("anything", owner: ownerA)
        check("a catalog that cannot be reached says so, and is not 'nothing found'",
              searching.searchState == .trouble(Model.Copy.searchTrouble))
        searchStore.catalogThrows = false

        let queriesBefore = searchStore.catalogQueries.count
        await searching.search("anything", owner: ownerB)
        check("nobody else's search is run",
              searchStore.catalogQueries.count == queriesBefore
                  && searching.searchState == .idle(Model.Copy.searchPrompt))

        // A slow answer overtaken by a fast one loses.
        let (typing, typeStore) = await loadedModel(rows: [])
        typeStore.hits = [fernwood]
        typeStore.beforeReturn = { [weak typing] in
            typeStore.beforeReturn = nil
            typeStore.hits = [quokka]
            await typing?.search("second", owner: ownerA)
        }
        await typing.search("first", owner: ownerA)
        if case .results(let found) = typing.searchState {
            check("the newest search wins, whatever order the answers arrive in",
                  found.map(\.meta.slug) == ["quokka"],
                  found.map(\.meta.slug).joined(separator: ","))
        } else {
            check("the newest search wins, whatever order the answers arrive in", false,
                  "\(typing.searchState)")
        }

        // A disconnect changes what the search screen says about that app.
        let (both, bothStore) = await loadedModel(rows: [
            connection(owner: ownerA, toolkit: "fernwood", account: "ca_1"),
        ])
        bothStore.hits = [fernwood]
        await both.search("fern", owner: ownerA)
        both.askToDisconnect("fernwood", owner: ownerA)
        _ = await both.confirmDisconnect(owner: ownerA)
        if case .results(let found) = both.searchState {
            check("an app disconnected in one place stops reading as connected in the other",
                  found[0].alreadyConnected == false)
        } else {
            check("an app disconnected in one place stops reading as connected in the other",
                  false)
        }

        both.signOut()
        check("signing out empties the screen, the search and the question",
              both.rows(for: ownerA).isEmpty
                  && both.searchState == .idle(Model.Copy.searchPrompt)
                  && both.pendingDisconnect == nil && both.notice == nil)
        check("and the screen goes back to asking for a sign-in",
              both.screen(for: ownerA) == .signedOut(Model.Copy.signedOut))

        // ======================================================= 6. THE WORDS
        //
        // The same gate the nudge card and the text thread pass, and the same
        // list `words.ts` holds on the server — not a second one written here.
        let sentences = Model.Copy.everySentence(sampleApp: "Quokka Post", sampleQuery: "quok")
        for sentence in sentences {
            let term = ConnectionsPolicy.forbiddenTerm(in: sentence)
            check("no forbidden word in: \(sentence.prefix(44))…", term == nil, term ?? "")
        }
        check("every sentence the screen writes is a real sentence",
              sentences.allSatisfy { !$0.trimmingCharacters(in: .whitespaces).isEmpty })
        check("the whole census goes through the gate in one call",
              ConnectionsPolicy.firstForbidden(in: sentences) == nil)
        check("the switch is worded as the product words it",
              Model.Copy.writesTitle == "Let Anticipy make changes")
        check("the vendor is never named",
              sentences.allSatisfy { !$0.lowercased().contains("composio") })

        // Every call every store ever saw carried the account that was signed
        // in when it was made — the whole session, checked from one end.
        for store in [listStore, toggleStore, askStore, searchStore, partialStore,
                      halfStore, stuckStore, bothStore, typeStore, switchStore,
                      skewStore, brokenStore2] {
            check("every call this store saw was for the signed-in owner",
                  Set(store.seenOwners).isSubset(of: [ownerA.raw]),
                  Set(store.seenOwners).joined(separator: ","))
        }

        if failures > 0 {
            print("ConnectedAppsModelTests: \(failures) failed")
            exit(1)
        }
        print("ConnectedAppsModelTests: all passed")
    }
}
