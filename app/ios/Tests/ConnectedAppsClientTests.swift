// SETTINGS → CONNECTED APPS, ON THE WIRE — the client, without a network.
//
// Compiled against the REAL production sources by the runner
// (`sh app/ios/Tests/run_connected_apps_client_tests.sh`): the client, the
// model whose protocol it satisfies, `ConnectionsPolicy` (the contract mirror)
// and `ConnectHandoff` (the link allowlist and the state). Nothing here is a
// copy of anything that ships.
//
// Six legs, and every one of them is a way this client can be wrong in a way
// nothing else in the app would notice:
//
//   1. WHOSE CALL IS IT    the owner is COMPARED, never sent. A call naming
//                          somebody else, or made signed out, reaches the
//                          transport ZERO times — the assertion is on the
//                          recorder, not on the throw.
//   2. WHAT WENT OUT       the token is in the header and never on a URL; no
//                          owner id appears in any request this suite makes;
//                          the search query crosses unread.
//   3. WHAT CAME BACK      a non-2xx THROWS, so the screen can tell "I could
//                          not read this" from "you have nothing". A foreign
//                          row is dropped; a foreign row in a WRITE refuses.
//   4. THE SENTENCES       no sentences, a blank one, or one using a word the
//                          register forbids: none of them is shown.
//   5. THE LINK            ours or nothing — and it comes back stamped with
//                          the attempt's own state, which is the value
//                          `parseDone` will demand back.
//   6. THROUGH THE SCREEN  the model over this client: a server that refuses
//                          renders `.trouble`, and a server that answers with
//                          an empty list renders `.invitation`.
//
// THE APP NAMES HERE ARE INVENTED. They exist only in this file's fixtures.
//
// The mutations that turn these red are listed on each leg.
import Foundation

private var failures = 0

@MainActor
private func check(_ name: String, _ ok: Bool, _ detail: String = "") {
    print("\(ok ? "PASS" : "FAIL"): \(name)\(ok || detail.isEmpty ? "" : "  -> \(detail)")")
    if !ok { failures += 1 }
}

// Two real-shaped owner row ids: fifteen lowercase alphanumerics, as
// contract.ts mints them.
private let ownerA = OwnerId("sxkotd1h02qb6gw")!
private let ownerB = OwnerId("qeuy6sv1raof9rw")!

private let BASE = URL(string: "https://stub.invalid")!
private let TOKEN = "eyJhbGciOiJIUzI1NiJ9.stub.signature"

/// A slug and an app nobody has written code for. The whole feature's claim is
/// that this works exactly like any other app.
private let TOOLKIT = "fernwood"
private let OTHER_TOOLKIT = "quokkapost"

/// The attempt id shape `ConnectSession` mints: a UUID string.
private let ATTEMPT_ID = "8f14e45f-ceea-467a-9a4d-3b2c1d0e5a67"

// ---------------------------------------------------------------- the double

/// One canned answer.
private struct Canned {
    var status: Int = 200
    var body: [String: Any] = [:]
    /// Sent verbatim when set, so a body that is not JSON at all can be tested.
    var raw: Data?
}

@MainActor
private final class Recorder: ConnectedAppsTransport {
    struct NoAnswer: Error {}

    /// Keyed by the path the request landed on, so one recorder can serve a
    /// whole session.
    var answers: [String: Canned] = [:]
    var fallback: Canned?

    private(set) var sent: [URLRequest] = []

    var paths: [String] { sent.compactMap { $0.url?.path } }
    var urls: [String] { sent.compactMap { $0.url?.absoluteString } }

    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        sent.append(request)
        let path = request.url?.path ?? ""
        guard let canned = answers[path] ?? fallback else { throw NoAnswer() }
        let data = canned.raw
            ?? ((try? JSONSerialization.data(withJSONObject: canned.body)) ?? Data())
        let response = HTTPURLResponse(url: request.url!, statusCode: canned.status,
                                       httpVersion: nil, headerFields: nil)!
        return (data, response)
    }

    func bodyOf(_ path: String) -> [String: Any]? {
        guard let request = sent.last(where: { $0.url?.path == path }),
              let data = request.httpBody else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }
}

/// The credential this phone is holding at this instant.
@MainActor
private final class Wallet {
    var owner: OwnerId?
    init(_ owner: OwnerId?) { self.owner = owner }
    func credential() -> ConnectedAppsCredential? {
        guard let owner else { return nil }
        return ConnectedAppsCredential(baseURL: BASE, owner: owner, authToken: TOKEN)
    }
}

// ---------------------------------------------------------------- fixtures

private func connectionRow(owner: OwnerId, toolkit: String = TOOLKIT,
                           account: String = "ca_9f2CQ4bX",
                           status: String = "connected",
                           writes: Bool = false) -> [String: Any] {
    [
        "user_id": owner.raw,
        "toolkit": toolkit,
        "connected_account_id": account,
        "status": status,
        "writes_enabled": writes,
        "last_used_at": 1_757_000_000.0,
    ]
}

private func toolkitRow(_ slug: String, _ name: String,
                        description: String? = nil) -> [String: Any] {
    var row: [String: Any] = [
        "slug": slug,
        "name": name,
        "logo": "https://logos.invalid/\(slug).png",
        "app_url": "https://\(slug).invalid",
        "scopes": ["read", "write"],
    ]
    if let description { row["description"] = description }
    return row
}

private func connection(owner: OwnerId, toolkit: String = TOOLKIT,
                        account: String = "ca_9f2CQ4bX",
                        writes: Bool = false) -> Connection {
    Connection(userID: owner.raw, toolkit: toolkit, connectedAccountID: account,
               alias: nil, status: .connected, writesEnabled: writes,
               lastUsedAt: nil)
}

private func refusal(_ error: Error) -> ConnectedAppsRefusal.Cause? {
    (error as? ConnectedAppsRefusal)?.cause
}

@main
@MainActor
private enum ConnectedAppsClientTests {
    static func main() async {

        // ============================================== 1. WHOSE CALL IS IT
        //
        // contract.ts opens with this: during the spike one operator's own
        // mailbox was connected by hand under a display name, and one person's
        // tokens served everybody. The rule it produced is that the user id is
        // the owner ROW id, resolved per request — so this client compares the
        // owner it is handed against the one signed in NOW, and sends nothing
        // when they differ.
        //
        // THE ASSERTION IS ON THE RECORDER. A client that threw AFTER building
        // and sending the request would pass a test that only checked the
        // throw, and the request would already be at the server.
        //
        // Mutation: delete the `now.owner == viewer` guard in `mine`. Four
        // cases go red, including the two that count requests.
        do {
            let wire = Recorder()
            let wallet = Wallet(ownerA)
            let client = ConnectedAppsClient(credential: wallet.credential,
                                             transport: wire)
            wire.fallback = Canned(body: ["items": []])

            var caught: ConnectedAppsRefusal.Cause?
            do { _ = try await client.connections(owner: ownerB) }
            catch { caught = refusal(error) }
            check("a call naming another owner is refused",
                  caught == .anotherOwner, String(describing: caught))
            check("and nothing was sent on their behalf", wire.sent.isEmpty,
                  wire.urls.joined(separator: " "))

            caught = nil
            do { try await client.setWrites([connection(owner: ownerB)], owner: ownerB) }
            catch { caught = refusal(error) }
            check("a write for another owner is refused too", caught == .anotherOwner)
            check("and no write was sent", wire.sent.isEmpty)

            // THE ROW, NOT ONLY THE ARGUMENT. A batch addressed to the signed-in
            // owner but carrying somebody else's row is the same failure wearing
            // the right label, and it REFUSES rather than filtering: a smaller
            // batch than the screen just moved leaves a switch reading ON over
            // an account nobody wrote.
            caught = nil
            do { try await client.setWrites([connection(owner: ownerA),
                                             connection(owner: ownerB, account: "ca_other")],
                                            owner: ownerA) }
            catch { caught = refusal(error) }
            check("a foreign row inside an owner's own batch is refused",
                  caught == .foreignRow, String(describing: caught))
            check("and the whole batch stayed on the phone", wire.sent.isEmpty)

            // Signed out is not "empty", and it is not a request either.
            wallet.owner = nil
            caught = nil
            do { _ = try await client.connections(owner: ownerA) }
            catch { caught = refusal(error) }
            check("a signed-out call is refused", caught == .notSignedIn)
            check("and reaches the network zero times", wire.sent.isEmpty)

            // THE CREDENTIAL IS READ EVERY TIME, not captured. The same client
            // object, after the phone changes hands, answers for the new owner
            // and refuses the old one.
            wallet.owner = ownerB
            let mine = try? await client.connections(owner: ownerB)
            check("the same client serves whoever is signed in now", mine != nil)
            caught = nil
            do { _ = try await client.connections(owner: ownerA) }
            catch { caught = refusal(error) }
            check("and refuses the account that just left", caught == .anotherOwner)
        }

        // ================================================= 2. WHAT WENT OUT
        //
        // No owner on the wire, ever: not in a path, not in a query string, not
        // in a body. The server derives it from the token, exactly as
        // `me/profile/upsert` already does.
        //
        // Mutation: put the owner on the connections URL as a query item. Two
        // cases go red.
        do {
            let wire = Recorder()
            let client = ConnectedAppsClient(credential: Wallet(ownerA).credential,
                                             transport: wire)
            wire.fallback = Canned(body: ["items": []])

            _ = try? await client.connections(owner: ownerA)
            _ = try? await client.catalog(matching: "  work mail  ", owner: ownerA)
            _ = try? await client.describe(toolkits: [TOOLKIT, OTHER_TOOLKIT],
                                           owner: ownerA)
            try? await client.setWrites([connection(owner: ownerA, writes: true)],
                                        owner: ownerA)

            check("the token travels in the header",
                  wire.sent.allSatisfy {
                      $0.value(forHTTPHeaderField: "Authorization") == TOKEN
                  })
            check("and never on a URL",
                  wire.urls.allSatisfy { !$0.contains("signature") },
                  wire.urls.joined(separator: " "))
            check("no owner id appears in any request URL",
                  wire.urls.allSatisfy {
                      !$0.contains(ownerA.raw) && !$0.contains(ownerB.raw)
                  },
                  wire.urls.joined(separator: " "))
            let writeBody = wire.bodyOf("/" + ConnectedAppsClient.Route.writes)
            check("nor in the write's body",
                  !String(describing: writeBody ?? [:]).contains(ownerA.raw),
                  String(describing: writeBody ?? [:]))
            check("every route this client can reach is under me/",
                  ConnectedAppsClient.Route.every.allSatisfy { $0.hasPrefix("me/") },
                  ConnectedAppsClient.Route.every.joined(separator: " "))

            // LAW 1. The letters somebody typed are handed to the catalog as
            // they arrived. Nothing here trims, ranks, corrects or matches
            // against a local list — "my work email" and a half-typed brand are
            // the same request and no list in this app holds them.
            //
            // Mutation: trim or lowercase the query before it is sent. Red.
            let searched = wire.urls.first { $0.contains(ConnectedAppsClient.Route.catalog) }
            check("the query crosses unread, spaces and all",
                  searched?.contains("%20%20work%20mail%20%20") == true,
                  searched ?? "no catalog request")
        }

        // ================================================ 3. WHAT CAME BACK
        //
        // THE LOAD-BEARING ONE. A refusal handed back as data is a refusal
        // every caller swallows, and the app then paints a confident empty
        // state over somebody's four connected apps.
        //
        // Mutation: return `[]` instead of throwing on a non-2xx. Three cases
        // go red, including the `.trouble` screen in leg 6.
        do {
            let wire = Recorder()
            let client = ConnectedAppsClient(credential: Wallet(ownerA).credential,
                                             transport: wire)

            wire.fallback = Canned(status: 403, body: ["message": "no"])
            var caught: ConnectedAppsRefusal?
            do { _ = try await client.connections(owner: ownerA) }
            catch { caught = error as? ConnectedAppsRefusal }
            check("a refused read throws rather than reading as empty",
                  caught?.cause == .serverRefused)
            check("and carries the status it was refused with", caught?.status == 403)

            wire.fallback = Canned(status: 200, raw: Data("<html>502</html>".utf8))
            var cause: ConnectedAppsRefusal.Cause?
            do { _ = try await client.connections(owner: ownerA) }
            catch { cause = refusal(error) }
            check("an answer nobody can parse is unreadable, not empty",
                  cause == .unreadableAnswer, String(describing: cause))

            // A MIXED LIST. The server scopes the query and this scopes the
            // answer: a filter that forgets its clause, or a cache keyed one
            // field too loosely, produces a list that looks right at every line
            // and holds somebody else's mailbox. Dropped rather than thrown —
            // one bad row must not blank a person's screen.
            //
            // Mutation: return the decoded rows without `OwnerScoped.rows`. Red.
            wire.fallback = Canned(body: ["items": [
                connectionRow(owner: ownerA),
                connectionRow(owner: ownerB, toolkit: OTHER_TOOLKIT, account: "ca_theirs"),
                ["toolkit": TOOLKIT],
            ]])
            let rows = (try? await client.connections(owner: ownerA)) ?? []
            check("only this owner's rows come back", rows.count == 1,
                  rows.map(\.userID).joined(separator: ","))
            check("and it is the owner's own row",
                  rows.first?.connectedAccountID == "ca_9f2CQ4bX")

            // THE OPT-IN IS READ THROUGH THE ONE PREDICATE, so a column that is
            // absent, null or the string "true" all come back OFF. That is
            // `Connection(row:)`'s rule and this asks it the way a screen does.
            check("the write opt-in defaults off", rows.first?.writesEnabled == false)

            // THE DISCONNECT, AS A FLOOR. `revoked` is the only thing that
            // licenses the word "revoked"; a missing field must never be a yes.
            // Read through `ConnectionsPolicy.writesOptedIn`, this feature's one
            // answer to "what does a stored boolean read as" — `1` counts,
            // because the column comes from storage where booleans are
            // integers, and a WORD never does.
            //
            // Mutation: read the flags with `!= false`, or with
            // `(value as? Bool) != nil`. Red.
            wire.fallback = Canned(body: ["deleted": true])
            let quiet = try? await client.disconnect(owner: ownerA,
                                                     connectedAccountID: "ca_9f2CQ4bX")
            check("a disconnect that says nothing about revoking has not revoked",
                  quiet?.revoked == false && quiet?.deleted == true)
            wire.fallback = Canned(body: ["revoked": 1, "deleted": "yes",
                                          "revoke_unavailable": 0])
            let sloppy = try? await client.disconnect(owner: ownerA,
                                                      connectedAccountID: "ca_9f2CQ4bX")
            check("a stored integer is a yes and a word is not",
                  sloppy?.revoked == true && sloppy?.deleted == false
                  && sloppy?.revokeUnavailable == false)
            check("the account it was asked about is the one on the wire",
                  ConnectionsPolicy.text(
                      wire.bodyOf("/" + ConnectedAppsClient.Route.disconnect)?[
                          "connected_account_id"]) == "ca_9f2CQ4bX")
        }

        // ================================================== 4. THE SENTENCES
        //
        // The disclosure sheet is the one screen where somebody agrees to
        // something, and it is the last screen that may say "authorize",
        // "permissions" or the vendor's name. The server's words module audits
        // the register at the far end; this audits it at the near end, because
        // the two failures are different — that one is a model writing a bad
        // sentence, this one is a bad sentence arriving from anywhere at all.
        //
        // Mutation: return the lines without `firstForbidden`. Red.
        do {
            let wire = Recorder()
            let client = ConnectedAppsClient(credential: Wallet(ownerA).credential,
                                             transport: wire)
            let good = ["Read the notes you already have.",
                        "Add a note when you ask me to.",
                        "Nothing else, and nothing without you asking."]
            wire.fallback = Canned(body: ["sentences": good])
            let said = try? await client.permissionSentences(toolkit: TOOLKIT,
                                                             owner: ownerA)
            check("three plain sentences come through untouched", said == good)
            check("the toolkit asked about is the canonical slug",
                  ConnectionsPolicy.text(
                      wire.bodyOf("/" + ConnectedAppsClient.Route.sentences)?["toolkit"])
                  == TOOLKIT)

            // THE CONTROL for every refusal below: a clean set is shown. A gate
            // that refused everything would pass every negative case and be
            // worth nothing.
            for (name, payload, want) in [
                ("nothing at all", [String](), ConnectedAppsRefusal.Cause.noSentences),
                ("a blank among good ones", ["Read the notes you have.", "  "],
                 ConnectedAppsRefusal.Cause.noSentences),
            ] {
                wire.fallback = Canned(body: ["sentences": payload])
                var cause: ConnectedAppsRefusal.Cause?
                do { _ = try await client.permissionSentences(toolkit: TOOLKIT,
                                                              owner: ownerA) }
                catch { cause = refusal(error) }
                check("a disclosure with \(name) is not shown", cause == want,
                      String(describing: cause))
            }

            // Every word on the register list, one at a time, so a list that
            // shrank is a red suite rather than a quiet one.
            for term in ConnectionsPolicy.forbiddenTerms {
                wire.fallback = Canned(body: ["sentences": [
                    "Read the notes you already have.",
                    "Anticipy would \(term) the things you keep there.",
                ]])
                var cause: ConnectedAppsRefusal.Cause?
                do { _ = try await client.permissionSentences(toolkit: TOOLKIT,
                                                              owner: ownerA) }
                catch { cause = refusal(error) }
                check("a sentence using \"\(term)\" is refused, not trimmed",
                      cause == .forbiddenSentence, String(describing: cause))
            }

            // And this file's own two sentences go through the same gate.
            check("the connect flow's own copy passes the register",
                  ConnectionsPolicy.firstForbidden(in: ConnectStartCopy.everySentence) == nil,
                  String(describing:
                          ConnectionsPolicy.firstForbidden(in: ConnectStartCopy.everySentence)))
            check("and every one of them is a real sentence",
                  ConnectStartCopy.everySentence.allSatisfy {
                      !$0.trimmingCharacters(in: .whitespaces).isEmpty
                  })
            check("the vendor is never named",
                  ConnectStartCopy.everySentence.allSatisfy {
                      !$0.lowercased().contains("composio")
                  })
        }

        // ======================================================= 5. THE LINK
        //
        // Two things at once, and both are load-bearing.
        //
        // OURS OR NOTHING. A raw vendor link reaching a person is not
        // hypothetical: four went into messages on 2026-09-05. A server that
        // answered with one would otherwise be obeyed by this phone.
        //
        // AND STAMPED WITH THE ATTEMPT'S STATE. `anticipy://connected/{toolkit}`
        // is openable by any web page, any other app or a QR code on a poster,
        // and every other check on it is satisfied for free by a stranger's URL
        // while a connect is in flight. The attempt id is the one thing in that
        // callback only our own page can know — and it can only know it because
        // it went out on this link.
        //
        // Mutation: return `minted` instead of `outbound`. Five cases go red.
        do {
            let wire = Recorder()
            let client = ConnectedAppsClient(credential: Wallet(ownerA).credential,
                                             transport: wire)
            let host = ConnectHandoff.connectLinkHosts.sorted().first!
            let ours = "https://\(host)/\(ConnectHandoff.connectLinkPathSegment)/tok_9f2CQ4bX"

            wire.fallback = Canned(body: ["url": ours])
            let opened = try? await client.connectLink(toolkit: TOOLKIT, owner: ownerA,
                                                       attemptID: ATTEMPT_ID)
            check("the link that comes back is ours",
                  opened.map { ConnectHandoff.connectLinkIsOurs(url: $0) } == true,
                  opened?.absoluteString ?? "nothing")
            check("and it carries this attempt's state",
                  opened?.absoluteString == ours + "?state=\(ATTEMPT_ID)",
                  opened?.absoluteString ?? "nothing")

            // ONE PRODUCER. The value on the way out is the value the callback
            // will be measured against, read out of the callback itself.
            let attempt = ConnectAttempt(id: ATTEMPT_ID, owner: ownerA.raw,
                                         toolkit: TOOLKIT, startedAt: Date())!
            let callback = ConnectHandoff.callbackURL(for: attempt)!
            check("the state sent is the state the callback will be judged by",
                  opened?.absoluteString.hasSuffix(
                      "state=" + ConnectHandoff.stateToken(for: attempt)!) == true)
            check("and that is exactly what the callback carries",
                  callback.absoluteString.hasSuffix(
                      "state=" + ConnectHandoff.stateToken(for: attempt)!))

            // The round trip this suite can actually run: the link goes out
            // with the state, the done page echoes it, and the phone believes
            // the callback. Change one character of the state and it does not.
            check("a callback carrying that state reads as a connection",
                  ConnectHandoff.parseDone(
                      url: URL(string: callback.absoluteString
                               + "&status=connected&connected_account_id=ca_9f2CQ4bX")!,
                      attempt: attempt, signedInOwner: ownerA.raw, now: Date())
                  == .connected(toolkit: TOOLKIT, accountId: "ca_9f2CQ4bX"))
            check("and a callback carrying somebody else's does not",
                  ConnectHandoff.parseDone(
                      url: URL(string: "anticipy://connected/\(TOOLKIT)"
                               + "?state=not-this-attempt"
                               + "&status=connected&connected_account_id=ca_9f2CQ4bX")!,
                      attempt: attempt, signedInOwner: ownerA.raw, now: Date())
                  == .unreadable(.callbackIsForAnotherAttempt))

            // Every shape of link this client must refuse. The vendor's own
            // link is the one that has already happened.
            let refused: [(String, String)] = [
                ("the vendor's own link",
                 "https://connect.composio.dev/link/abc123"),
                // WHAT THIS ENTRY USED TO BE, AND WHY IT MOVED. It pinned
                // `api.<host>` as REFUSED, and it was right to: the Worker mints
                // there and the phone's allowlist named only the apex, so every
                // real link was refused by the app that had just asked for one.
                // The two agree now — api.anticipy.ai is in the allowlist, with
                // the measurement beside it — so the honest test of "a
                // neighbouring host" needs a neighbour we do NOT own.
                //
                // This is the shape that was actually doing the work: a
                // subdomain somebody else can obtain (a stale CNAME, a
                // marketing host, a takeover) must never carry a link that
                // binds an account.
                ("a link on a neighbouring host of ours",
                 "https://cdn.\(host)/\(ConnectHandoff.connectLinkPathSegment)/tok_9f2CQ4bX"),
                ("a link nested under the one host we do allow",
                 "https://x.api.\(host)/\(ConnectHandoff.connectLinkPathSegment)/tok_9f2CQ4bX"),
                ("a link in the clear",
                 "http://\(host)/\(ConnectHandoff.connectLinkPathSegment)/tok_9f2CQ4bX"),
                ("a link that already carries somebody's state",
                 ours + "?state=someone-elses-attempt"),
            ]
            for (name, candidate) in refused {
                wire.fallback = Canned(body: ["url": candidate])
                var cause: ConnectedAppsRefusal.Cause?
                do { _ = try await client.connectLink(toolkit: TOOLKIT, owner: ownerA,
                                                      attemptID: ATTEMPT_ID) }
                catch { cause = refusal(error) }
                check("\(name) is refused rather than opened",
                      cause == .linkNotOurs, String(describing: cause))
            }

            // And a link with somebody else's state, if one ever reached the
            // presenter another way, does not open under this attempt either.
            // This is the tightening in `presentation`: the token says which
            // LINK this is, the state says which ATTEMPT it was fetched for, and
            // the two are not the same fact.
            //
            // The CONTROL is the whole of `ConnectHandoffTests`' presentation
            // section, which opens a link with NO state on it — absent stays
            // allowed, or every link that has not been through `outboundLink`
            // would stop opening.
            let started = Date(timeIntervalSince1970: 1_757_000_000)
            let tapped = started.addingTimeInterval(2)
            let fixed = ConnectAttempt(id: ATTEMPT_ID, owner: ownerA.raw,
                                       toolkit: TOOLKIT, startedAt: started)!
            let foreign = URL(string: ours + "?state=another-attempt")!
            guard case .bound(let stamped) = fixed.binding(to: foreign) else {
                check("the presenter leg could not be set up", false)
                return exitIfFailed()
            }
            var gate = DisclosureGate()
            gate.disclosureShown(for: stamped, sentences: ["Read the notes you have."],
                                 now: started)
            gate.acknowledge(stamped, now: tapped)
            check("a link stamped for another attempt does not open",
                  ConnectHandoff.presentation(for: foreign, attempt: stamped,
                                              signedInOwner: ownerA.raw, gate: &gate,
                                              now: tapped, authSessionAvailable: true)
                  == .refused(.linkIsForAnotherAttempt))

            // The same attempt, with ITS OWN state on the link, opens.
            let mineNow = ConnectHandoff.outboundLink(URL(string: ours)!, for: fixed)!
            guard case .bound(let ownStamp) = fixed.binding(to: mineNow) else {
                check("the matching-state leg could not be set up", false)
                return exitIfFailed()
            }
            var openGate = DisclosureGate()
            openGate.disclosureShown(for: ownStamp, sentences: ["Read the notes you have."],
                                     now: started)
            openGate.acknowledge(ownStamp, now: tapped)
            check("and the link this attempt was actually handed does",
                  ConnectHandoff.presentation(for: mineNow, attempt: ownStamp,
                                              signedInOwner: ownerA.raw, gate: &openGate,
                                              now: tapped, authSessionAvailable: true)
                  == .authSession(url: mineNow,
                                  callbackScheme: ConnectHandoff.callbackScheme))
        }

        // ============================================== 6. THROUGH THE SCREEN
        //
        // The client under the model it is written for. This is the leg that
        // says the screen is LIVE rather than that a class compiles: the same
        // five states, driven by a server instead of by a stub that throws.
        //
        // Mutation: swap the client back for `UnreachableConnectedAppsStore`.
        // The `.apps` and `.invitation` cases go red.
        do {
            let wire = Recorder()
            let client = ConnectedAppsClient(credential: Wallet(ownerA).credential,
                                             transport: wire)
            let model = ConnectedAppsModel(store: client)
            model.signIn(ownerA)

            wire.answers["/" + ConnectedAppsClient.Route.connections] =
                Canned(body: ["items": [connectionRow(owner: ownerA)]])
            wire.answers["/" + ConnectedAppsClient.Route.catalog] =
                Canned(body: ["items": [toolkitRow(TOOLKIT, "Fernwood Notes")]])
            await model.load()
            guard case .apps(let drawn) = model.screen(for: ownerA) else {
                check("a live server draws the owner's apps", false,
                      String(describing: model.screen(for: ownerA)))
                return exitIfFailed()
            }
            check("a live server draws the owner's apps", drawn.count == 1)
            check("named by the catalog rather than by this app",
                  drawn.first?.name == "Fernwood Notes")

            // EMPTY IS NOT BROKEN.
            wire.answers["/" + ConnectedAppsClient.Route.connections] =
                Canned(body: ["items": []])
            await model.load()
            check("a server that answers with nothing invites",
                  model.screen(for: ownerA) == .invitation(ConnectedAppsModel.Copy.invitation))

            // AND BROKEN IS NOT EMPTY. This is the sentence the whole client
            // exists to make true: "I could not read your connected apps just
            // now", never "nothing is connected yet".
            wire.answers["/" + ConnectedAppsClient.Route.connections] =
                Canned(status: 500, body: [:])
            await model.load()
            check("a server that refuses says so",
                  model.screen(for: ownerA) == .trouble(ConnectedAppsModel.Copy.trouble))

            // The search reaches the catalog and the model shows what came
            // back, in the order it came back — including an app nobody wrote
            // code for.
            wire.answers["/" + ConnectedAppsClient.Route.catalog] =
                Canned(body: ["items": [toolkitRow(OTHER_TOOLKIT, "Quokka Post"),
                                        toolkitRow(TOOLKIT, "Fernwood Notes")]])
            await model.search("post", owner: ownerA)
            guard case .results(let found) = model.searchState else {
                check("the catalog answers the search", false,
                      String(describing: model.searchState))
                return exitIfFailed()
            }
            check("the catalog answers the search", found.count == 2)
            check("in the order it came back",
                  found.map(\.meta.slug) == [OTHER_TOOLKIT, TOOLKIT])

            // THE CATALOG'S OWN WORDS, THROUGH THE SAME GATE AS OURS. A vendor
            // blurb is the subtitle of a result AND the VoiceOver hint on the
            // button that starts a connect.
            wire.answers["/" + ConnectedAppsClient.Route.catalog] =
                Canned(body: ["items": [
                    toolkitRow(TOOLKIT, "Fernwood Notes",
                               description: "The fastest integration for your notes."),
                    toolkitRow(OTHER_TOOLKIT, "Quokka Post",
                               description: "Keep every letter in one place."),
                ]])
            await model.search("notes", owner: ownerA)
            guard case .results(let blurbed) = model.searchState else {
                check("the blurbed results were drawn", false)
                return exitIfFailed()
            }
            check("a vendor blurb in the register we refuse is withheld",
                  blurbed.first(where: { $0.meta.slug == TOOLKIT })?.subtitle == nil)
            check("and a plain one is shown",
                  blurbed.first(where: { $0.meta.slug == OTHER_TOOLKIT })?.subtitle
                  == "Keep every letter in one place.")
        }

        exitIfFailed()
    }

    static func exitIfFailed() {
        if failures > 0 {
            print("ConnectedAppsClientTests: \(failures) failed")
            exit(1)
        }
        print("ConnectedAppsClientTests: all passed")
    }
}
