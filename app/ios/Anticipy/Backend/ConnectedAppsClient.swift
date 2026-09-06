import Foundation

/// SETTINGS → CONNECTED APPS, TALKING TO THE SERVER.
///
/// `ConnectedAppsModel` decides what the screen does; `ConnectionsPolicy`
/// decides what a connection IS. This is the third piece and the only one that
/// leaves the phone: the real `ConnectedAppsStore`, plus the two calls the
/// connect flow needs (the permission sentences and our own single-use link).
///
/// It replaces `UnreachableConnectedAppsStore`, whose every method threw. That
/// type stays where it is — the model's suite pins it to the `.trouble` side of
/// "empty is not broken", and it is what a preview is handed — but nothing in
/// the shipping app is constructed with it any more.
///
/// ── THE WRONG-PERSON RULE, AS A SHAPE RATHER THAN A PROMISE ──────────────
///
/// During the spike one operator's own mailbox was connected by hand under the
/// `user_id` "omar" — a display name — and one person's tokens served
/// everybody. It was revoked and deleted, and `contract.ts` opens with the rule
/// it produced: the user id is the owner ROW id, always, resolved per request.
///
/// So NO CALL IN THIS FILE PUTS AN OWNER ON THE WIRE. Not in a path, not in a
/// query string, not in a body. Every route is under `me/`, and the server
/// derives the owner from the session token exactly as `me/profile/upsert` and
/// `me/phone/remove` already do. `ConnectedAppsStore` still takes an owner on
/// every method — that is deliberate and stays — but here it is a value to be
/// COMPARED, never a value to be sent: if the owner the caller names is not the
/// owner signed in at this instant, the call throws and no request is made.
/// Both halves are pinned in `ConnectedAppsClientTests`, including the leg that
/// asserts the transport recorded zero requests.
///
/// The credential is read through a closure ON EVERY CALL rather than captured
/// at construction. `SettingsConnectedAppsView` builds its model once, with the
/// store it was handed, and keeps it across a sign-out and a second person
/// signing in on the same phone; a client holding one account's token would go
/// on answering under the next person's name.
///
/// ── THE ROUTES, WHICH DO NOT EXIST YET AND ARE WRITTEN DOWN HERE ─────────
///
/// Checked 2026-09-05: `migration/workers/src/index.ts` serves `/c/` (the
/// connect page) and nothing else in front of `src/connections/`. The store and
/// the provider are built; the data routes are not. This file is the contract
/// they must satisfy, and until they do every call here fails the way an
/// unreachable server fails — `.trouble` on the screen, never "you have nothing
/// connected".
///
///   GET  me/connections                     -> { "items": [connection row, …] }
///   GET  me/connections/catalog?q=…         -> { "items": [toolkit row, …] }
///   GET  me/connections/catalog?slugs=a,b   -> { "items": [toolkit row, …] }
///   POST me/connections/writes              -> 2xx
///        { "rows": [ { "toolkit", "connected_account_id", "writes_enabled" } ] }
///   POST me/connections/disconnect          -> { "revoked", "deleted",
///        { "connected_account_id": … }         "revoke_unavailable", "app_name" }
///   POST me/connections/sentences           -> { "sentences": [ …, …, … ] }
///        { "toolkit": … }
///   POST me/connections/link                -> { "url": "https://…/c/{token}" }
///        { "toolkit": … }
///   GET  me/connections/signals             -> { "state": "ranked"|"none",
///                                                "items": [ranked app row, …] }
///   POST me/connections/skip                -> { "ok": true, "state",
///        { "toolkit", "onboarding" }           "level", "snooze_until" }
///
/// The connection row is `Connection(row:)`'s shape — the same column names
/// `contract.ts` and D1 use — so a row that cannot be read is dropped rather
/// than half-built.
///
/// THE LAST TWO ARE THIS ROUND'S (2026-09-06) and they are the two holes three
/// audits named one at a time. Without `signals` the setup card was constructed
/// with literal empty arrays and pre-selected nothing for every person alive,
/// however well the ranking worked. Without `skip` a person's "not now" lived
/// in this handset's UserDefaults, so a reinstall forgot it and the ask engine
/// — which is the thing that decides whether they are asked again — never heard
/// it at all.
///
/// ONE OF THEM IS CLOSED AND ONE IS BUILT-AND-HELD. `signals` is wired through
/// to the card. `skip` is written, driven by the suite, and gated shut at its
/// call site: the route still records a real decline where the setup card means
/// a seven-day snooze. See `ConnectOnboardingPolicy.serverRecordsTheSoftSnooze`
/// for the measurement and the leg that retires it.
///
/// A RANKED APP ROW IS THE CATALOG ROW PLUS THREE FACTS, and that is the shape
/// `routes/connections_api.ts` actually serves (`signalRow`, read 2026-09-06
/// rather than assumed): `slug`, `name`, `logo`, `description`, `app_url`,
/// `scopes` — byte for byte what `me/connections/catalog` answers with, so one
/// decoder reads both — and then `alias`, `last_seen_at` and `sources`. One
/// line per app, best first, already cut to the server's own ceiling.
///
/// THE ORDER IS THE ANSWER AND THE WEIGHT IS NOT ON THE WIRE. That is the far
/// end's decision and this file keeps it: a decayed weight is a different
/// number this afternoon than it was this morning, and a number on the wire is
/// an invitation to `if weight > 0.5` on a phone — a second policy about who
/// gets asked to connect what, written where nobody reviewing this feature
/// would look. So nothing here re-sorts what came back.
///
/// AND NEITHER IS THE OWNER, WHICH IS THIS ROUTE'S ONE ASYMMETRY AND IS WRITTEN
/// DOWN RATHER THAN GLOSSED. Every other list this client reads carries
/// `user_id` on every row and is scoped twice — once here, once in the model.
/// These rows carry none, so THE PHONE CANNOT CHECK WHOSE EVIDENCE THIS IS; the
/// scoping is wholly the server's (`rankedApps` re-reads the id it was given
/// against every row and raises on a mixed table). What this file can still do,
/// and does, is refuse to ASK on anybody else's behalf — `mine(owner)` — and
/// what the caller can still do, and does, is refuse to ADOPT an answer that
/// landed after the person signed out (`OnboardingView.readConnectSignals`).
/// Neither is the same as scoping the rows, and pretending otherwise by adding
/// a check with nothing to read would be worse than saying so.
///
/// ── LAW 1 ────────────────────────────────────────────────────────────────
///
/// Nothing here decides what anybody MEANT. The letters somebody typed into the
/// search box are handed to the catalog exactly as they arrived: no filter, no
/// ranking, no local list of app names, no "did you mean". What this file reads
/// is structure — a status code, a JSON shape, a URL's scheme and host — and
/// one CEILING over prose that is about to go on our own screen, which is the
/// same clause `ConnectedAppsModel.shownDescription` sits under: the input is
/// text we are about to show, the only outcome is "do not show this", and the
/// failure mode is silence.
@MainActor
final class ConnectedAppsClient: ConnectedAppsStore {

    // ---------------------------------------------------------------- routes

    /// Every path this client can reach, declared once. A route typed at a call
    /// site is a route no census can find, and the runner reads this enum to
    /// check that none of them names an owner.
    enum Route {
        static let connections = "me/connections"
        static let catalog = "me/connections/catalog"
        static let writes = "me/connections/writes"
        static let disconnect = "me/connections/disconnect"
        static let sentences = "me/connections/sentences"
        static let link = "me/connections/link"
        static let signals = "me/connections/signals"
        static let skip = "me/connections/skip"

        static var every: [String] {
            [connections, catalog, writes, disconnect, sentences, link, signals, skip]
        }
    }

    /// The query parameter names. `q` carries the owner's own words untouched;
    /// `slugs` carries catalog keys we already hold.
    enum Field {
        static let query = "q"
        static let slugs = "slugs"
    }

    // ------------------------------------------------------------ the seam

    private let credential: @MainActor () -> ConnectedAppsCredential?
    private let transport: any ConnectedAppsTransport

    /// - Parameter credential: read ON EVERY CALL, never cached. Nil means
    ///   nobody is signed in, and nothing is sent.
    init(credential: @escaping @MainActor () -> ConnectedAppsCredential?,
         transport: (any ConnectedAppsTransport)? = nil) {
        self.credential = credential
        self.transport = transport ?? URLSessionConnectedAppsTransport()
    }

    // ------------------------------------------------------- the owner's list

    /// This owner's connections.
    ///
    /// SCOPED TWICE ON THE WAY IN, and the model scopes them a third time. That
    /// is not superstition: the answer is JSON from a server, and a filter that
    /// forgets its clause, a cache keyed one field too loosely, or a response
    /// that lands after a sign-out all produce a list that looks correct at
    /// every line and holds somebody else's mailbox. A foreign row is DROPPED
    /// rather than throwing, so one bad row cannot blank a person's screen.
    func connections(owner: OwnerId) async throws -> [Connection] {
        let who = try mine(owner)
        let body = try await get(Route.connections, query: [], as: who)
        let rows = try items(body).compactMap { Connection(row: $0) }
        return OwnerScoped.rows(rows, for: owner)
    }

    /// Catalog rows for toolkits this owner already has. A slug we cannot ask
    /// about is simply not asked about; the model falls back to the slug the
    /// connection itself carries.
    func describe(toolkits: [String], owner: OwnerId) async throws -> [ToolkitMeta] {
        let who = try mine(owner)
        let wanted = toolkits
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        guard !wanted.isEmpty else { return [] }
        let body = try await get(Route.catalog,
                                 query: [URLQueryItem(name: Field.slugs,
                                                      value: wanted.joined(separator: ","))],
                                 as: who)
        return try items(body).compactMap(Self.toolkit)
    }

    /// The whole catalog, searched AS TYPED.
    ///
    /// The one thing done to the query is percent-encoding it into the URL,
    /// which is transport. Nothing here reads it, and nothing here re-orders
    /// what comes back: which app a person meant is a model's question asked
    /// against the catalog, and a local list would be the shape the spec
    /// forbids — "a new app in the catalog is a new app in Anticipy with zero
    /// code".
    func catalog(matching query: String, owner: OwnerId) async throws -> [ToolkitMeta] {
        let who = try mine(owner)
        let body = try await get(Route.catalog,
                                 query: [URLQueryItem(name: Field.query, value: query)],
                                 as: who)
        return try items(body).compactMap(Self.toolkit)
    }

    // ------------------------------------------------- what we already know

    /// THE EVIDENCE THIS OWNER'S SETUP CARD RANKS, and the names for it.
    ///
    /// One call answering both halves, because they are one question: a list of
    /// slugs the card cannot put a name to is a screen of blank lines with
    /// buttons on them, and asking for the names afterwards is a second round
    /// trip that can fail on its own and leave the card half-built.
    ///
    /// SCOPED TWICE, like `connections`. The route carries no owner — the
    /// server derives it from the session — and what comes back is compared
    /// against the owner this call was made for. A foreign row is DROPPED here
    /// rather than refused, and the refusal happens one layer up:
    /// `ConnectOnboardingPolicy.rank` reads `user_id` off every row and answers
    /// `foreignRow`/`mixedOwners` for the batch. Dropping here would hide from
    /// that check the exact thing it exists to catch, so this keeps every row
    /// it can read and lets the policy judge the set.
    ///
    /// A ROW NOBODY CAN READ IS DROPPED; AN ANSWER NOBODY CAN READ THROWS. The
    /// asymmetry is the same one `connections` keeps and points the same way: a
    /// single bad row costs one tick-box, and treating a whole unparseable body
    /// as "this person uses nothing" would paint a confident empty card over
    /// somebody's evidence and pre-select nothing forever. So if rows arrived
    /// and NONE of them could be read, that is unreadable rather than empty.
    ///
    /// FOUR ANSWERS, AND THE FAILURES ARE TOLD APART BY A FIELD RATHER THAN BY
    /// PROSE. The route answers `ranked`, `none`, `unreadable` or
    /// `catalog-unreadable` (`SIGNALS_ANSWER`, connections_api.ts), and the
    /// last two arrive as a 503. Both are OUR failure and neither may be shown
    /// as "you use none of these" — but they are still two different sentences
    /// to a person, so `catalog-unreadable` throws its OWN cause instead of the
    /// generic refusal. Nothing branches on `message`: the state is a closed
    /// token the far end declares, and reading the prose beside it to work out
    /// what happened would be this file deciding what somebody's words mean.
    func signals(owner: OwnerId) async throws -> AppSignalsAnswer {
        let who = try mine(owner)
        let answer = try await probe(wire(Route.signals, query: [], as: who))
        guard (200..<300).contains(answer.status) else {
            // A refusal is still allowed to say WHICH refusal it is.
            if ConnectionsPolicy.text(answer.body?["state"]) == State.catalogUnreadable {
                throw ConnectedAppsRefusal(.catalogUnreadable, status: answer.status)
            }
            throw ConnectedAppsRefusal(.serverRefused, status: answer.status)
        }
        let raw = try items(answer.body)
        let rows = raw.compactMap { RankedAppRow(row: $0) }
        guard raw.isEmpty || !rows.isEmpty else {
            throw ConnectedAppsRefusal(.unreadableAnswer)
        }
        // AN EMPTY ANSWER IS A CLAIM ABOUT THE PERSON AND IS READ AS A FLOOR.
        // "You have nothing yet" is the one thing this route says that is about
        // THEM rather than about us, so it is believed only when the server
        // said it in the field it declares — never inferred from `items` being
        // short. A 200 with no readable rows and no such word is an answer this
        // build did not understand, and an answer nobody understood must not be
        // rendered as a confident blank card on the one screen that then asks
        // somebody to connect what they already live in.
        guard !rows.isEmpty else {
            guard ConnectionsPolicy.text(answer.body?["state"]) == State.nothingYet else {
                throw ConnectedAppsRefusal(.unreadableAnswer)
            }
            return .nothingYet
        }
        return .ranked(rows)
    }

    /// The far end's own words for what it answered. Compared, never shown:
    /// these are tokens in a contract (`SIGNALS_ANSWER`), and every sentence a
    /// person reads about them is written on this phone.
    private enum State {
        static let nothingYet = "none"
        static let catalogUnreadable = "catalog-unreadable"
    }

    // ------------------------------------------------------ the write opt-in

    /// Write exactly the rows `ConnectionsPolicy.writesTransition` produced.
    ///
    /// A row belonging to anybody else is a REFUSAL, not a filter. Every other
    /// call here drops a foreign row because dropping one costs the owner a
    /// line on a screen; dropping one HERE would send a smaller batch than the
    /// screen just moved, and the switch would read ON over an account nobody
    /// wrote. A batch that is not wholly this owner's is a bug upstream and
    /// says so.
    func setWrites(_ rows: [Connection], owner: OwnerId) async throws {
        let who = try mine(owner)
        guard !rows.isEmpty else { return }
        for row in rows where !OwnerScoped.belongs(row, to: owner) {
            throw ConnectedAppsRefusal(.foreignRow)
        }
        let payload: [String: Any] = [
            "rows": rows.map {
                [
                    "toolkit": $0.toolkit,
                    "connected_account_id": $0.connectedAccountID,
                    "writes_enabled": $0.writesEnabled,
                ] as [String: Any]
            },
        ]
        _ = try await post(Route.writes, payload: payload, as: who)
    }

    // ------------------------------------------------------------ disconnect

    /// Revoke, THEN delete, at the far end — one account per call.
    ///
    /// Every field is read as a FLOOR: absent, unreadable or the wrong type all
    /// come back false. `revoked` is the only thing that licenses the word
    /// "revoked" (`ConnectionsPolicy.disconnectConfirmation`), so a missing
    /// field must never be read as a yes — telling somebody their access was
    /// revoked when it was not is a lie they cannot detect until it matters.
    func disconnect(owner: OwnerId, connectedAccountID: String) async throws -> DisconnectResult {
        let who = try mine(owner)
        let account = connectedAccountID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !account.isEmpty else { throw ConnectedAppsRefusal(.unreadableAnswer) }
        let body = try await post(Route.disconnect,
                                  payload: ["connected_account_id": account],
                                  as: who)
        guard let row = body else { throw ConnectedAppsRefusal(.unreadableAnswer) }
        return DisconnectResult(
            appName: ConnectionsPolicy.text(row["app_name"]) ?? "",
            attempted: 1,
            revoked: Self.flag(row["revoked"]),
            deleted: Self.flag(row["deleted"]),
            revokeUnavailable: Self.flag(row["revoke_unavailable"]))
    }

    // ------------------------------------------------ starting a connect

    /// THE THREE PLAIN SENTENCES, written from the toolkit's own scopes by the
    /// server's words module, and put through the register gate again here.
    ///
    /// WHY AGAIN. `words.ts` audits the register at the far end, and this
    /// checks it at the near end, because the two failures are different: that
    /// one is a model writing a bad sentence, this one is a bad sentence
    /// arriving on this phone from anywhere at all. The disclosure sheet is the
    /// one screen in the product where somebody agrees to something, and it is
    /// the last screen that may say "authorize", "permissions" or the vendor's
    /// name. A sentence that fails REFUSES THE WHOLE SET rather than being
    /// dropped: showing two of three claims is asking somebody to agree to less
    /// than they are agreeing to, which is the same defect with better manners.
    ///
    /// This is the CEILING polarity — the outcome is "do not show this" and the
    /// failure mode is silence — and it reads OUR prose, never a person's.
    func permissionSentences(toolkit: String, owner: OwnerId) async throws -> [String] {
        let who = try mine(owner)
        let slug = try Self.slug(toolkit)
        let body = try await post(Route.sentences, payload: ["toolkit": slug], as: who)
        let raw = (body?["sentences"] as? [Any]) ?? []
        let lines = raw.compactMap { ConnectionsPolicy.text($0) }
        // A blank disclosure is not a disclosure, and neither is a partial one.
        guard !lines.isEmpty, lines.count == raw.count else {
            throw ConnectedAppsRefusal(.noSentences)
        }
        if ConnectionsPolicy.firstForbidden(in: lines) != nil {
            throw ConnectedAppsRefusal(.forbiddenSentence)
        }
        return lines
    }

    /// OUR single-use link, minted now and stamped with this attempt's state.
    ///
    /// TWO THINGS HAPPEN HERE AND BOTH ARE LOAD-BEARING.
    ///
    /// The link is checked against `ConnectHandoff.inspect` before anything
    /// else, through `ConnectHandoff.outboundLink`. A raw vendor link reaching
    /// a person is not hypothetical — four of them went into messages on
    /// 2026-09-05 — and a server that answered with one would otherwise be
    /// obeyed by this phone. It is refused by code, never opened.
    ///
    /// And the attempt's STATE is put on it. That is what makes the callback
    /// bindable: it rides out on our page's hidden field, out again on the URL
    /// we hand the other company, and back on `anticipy://connected/{toolkit}`,
    /// where `ConnectHandoff.parseDone` refuses any callback whose state is not
    /// the attempt's. Without it the deep link — which any web page, any other
    /// app or a QR code on a poster can open — satisfies every other check for
    /// free while a connect is genuinely in flight.
    ///
    /// The state itself is not written here. `ConnectHandoff` reads it out of
    /// the callback it will accept, so the value sent and the value demanded
    /// have exactly one producer.
    func connectLink(toolkit: String, owner: OwnerId, attemptID: String) async throws -> URL {
        try await connectLink(toolkits: [toolkit], owner: owner, attemptID: attemptID)
    }

    /// ONE LINK FOR THE WHOLE TICKED SET — spec page 25, "One Connect button
    /// opens a multi-app connect page".
    ///
    /// WHAT THIS REPLACES, and it is worth naming because it was the shipped
    /// behaviour. The setup card asked for a link PER app and walked the person
    /// through the browser once for each: tick four, and the phone minted four
    /// tokens, opened four pages and came back four times, for one decision they
    /// made once. The Worker has been able to draw, walk, tap, call back and
    /// skip a page of apps since 2026-09-06; the minter that could MAKE one
    /// landed the same day, and this is the caller.
    ///
    /// A PAGE OF ONE IS THE LINK THIS APP HAS ALWAYS MINTED. The server writes
    /// app 0 at the plain token handle, so `connectLink(toolkit:)` above is one
    /// line and every link in the wild resolves unchanged.
    ///
    /// THE ATTEMPT IS STILL ONE ATTEMPT, and it is named by the FIRST app. That
    /// is the honest limit of the current handoff and it is written here rather
    /// than hidden: `ConnectAttempt` carries a single toolkit, because it exists
    /// to bind ONE `anticipy://connected/{toolkit}` callback, and the vendor
    /// sends one of those per app connected. The `state` is what the callback is
    /// actually matched on (`ConnectHandoff.parseDone`), and it is the same for
    /// every app on the page — so the binding holds for all of them. What does
    /// not hold is the NAME: a page-level cancel deep-links back naming app one.
    /// Whoever gives `ConnectAttempt` a page-level identity should delete this
    /// paragraph in the same change.
    func connectLink(toolkits: [String], owner: OwnerId, attemptID: String) async throws -> URL {
        let who = try mine(owner)
        let slugs = try toolkits.map { try Self.slug($0) }
        // AN EMPTY PAGE IS NOT A REQUEST. The server refuses it with a 400; this
        // refuses it without spending a round trip, and with the cause that says
        // which of the two things went wrong.
        guard let first = slugs.first else { throw ConnectedAppsRefusal(.toolkitNotNamed) }
        // The attempt is rebuilt from the three fields the handoff itself uses
        // to say two attempts are one (`sameAttempt(as:)`: id, owner, toolkit).
        // It licenses nothing — `ConnectSession` holds the real one privately
        // and `presentation` compares against THAT — it only names the state.
        guard let attempt = ConnectAttempt(id: attemptID, owner: owner.raw,
                                           toolkit: first, startedAt: Date()) else {
            throw ConnectedAppsRefusal(.unreadableAnswer)
        }
        // `toolkits` ALWAYS, including for one app. The route takes either shape
        // and a page of one is byte-identical either way, so sending one shape
        // means there is a single path to keep working rather than two that
        // diverge the first time one of them is edited.
        let body = try await post(Route.link, payload: ["toolkits": slugs], as: who)
        guard let text = ConnectionsPolicy.text(body?["url"]),
              let minted = URL(string: text) else {
            throw ConnectedAppsRefusal(.unreadableAnswer)
        }
        // WHAT THE SERVER SAYS IT MINTED, CHECKED AGAINST WHAT WE ASKED FOR.
        // The route echoes the set back precisely so this comparison can exist:
        // a link carrying fewer apps than the person ticked is a page that opens
        // and quietly does not offer one of them, and the person has no way to
        // tell. Absent is tolerated — an older Worker sends no such field, and
        // refusing then would break the phone against the deployment it is
        // shipping alongside — but a PRESENT-and-different set is refused.
        if let echoed = body?["toolkits"] as? [Any] {
            let named = echoed.compactMap { ConnectionsPolicy.text($0) }
            guard named == slugs else { throw ConnectedAppsRefusal(.unreadableAnswer) }
        }
        guard let outbound = ConnectHandoff.outboundLink(minted, for: attempt) else {
            throw ConnectedAppsRefusal(.linkNotOurs)
        }
        return outbound
    }

    // --------------------------------------------------------------- no

    /// A PERSON'S NO, WHERE THE ASK ENGINE CAN READ IT.
    ///
    /// The body is `{ "toolkit", "onboarding" }` and that is the whole of it.
    /// There is no level, no snooze and no state on it, deliberately: what a
    /// refusal COSTS is the ladder's answer, and a client that could name the
    /// snooze could name it as zero. `onboarding` says which SURFACE the person
    /// was looking at — the setup card, or anything else — and it is a real
    /// boolean rather than a string, because a string is truthy at the far end
    /// and this field shortens how long somebody is left alone.
    ///
    /// WHAT COMES BACK IS HANDED TO THE CALLER RATHER THAN SWALLOWED, and that
    /// is the load-bearing half. `ConnectOnboardingPolicy.agreesWithSkip` is
    /// the predicate this feature already has for holding two implementations
    /// of one event to one meaning, and it takes exactly these three numbers.
    /// A method that returned `Void` would make the answer unreadable and the
    /// disagreement unmeasurable — which is how the phone and the server came
    /// to mean two different things by "skip" in the first place.
    ///
    /// AS OF 2026-09-06 ONBOARDING'S CALL SITE EXISTS AND IS SHUT.
    /// `OnboardingView.sendConnectSkip` reads
    /// `ConnectOnboardingPolicy.serverRecordsTheSoftSnooze` and returns before
    /// this method is reached, because the route still records a real decline
    /// where the setup card means a seven-day snooze — and a level-1 decline is
    /// not something the phone can walk back afterwards. Settings has no such
    /// gate to want: a person disconnecting there IS declining.
    func skip(toolkit: String, onboarding: Bool, owner: OwnerId) async throws -> SkipAcknowledgement {
        let who = try mine(owner)
        let slug = try Self.slug(toolkit)
        let body = try await post(Route.skip,
                                  payload: ["toolkit": slug, "onboarding": onboarding],
                                  as: who)
        // A 2xx with a body nobody can read is not a recorded no. The whole
        // point of this call is that the phone stops asking because the SERVER
        // is now the one remembering, and it may only stop on an answer it
        // understood.
        guard let row = body, let state = ConnectionsPolicy.text(row["state"]) else {
            throw ConnectedAppsRefusal(.unreadableAnswer)
        }
        return SkipAcknowledgement(state: state,
                                   level: ConnectionsPolicy.wholeNumber(row["level"]),
                                   snoozeUntil: ConnectionsPolicy.instant(row["snooze_until"]))
    }

    // ------------------------------------------------------------- the wire

    /// Who is signed in RIGHT NOW, and is it who the caller thinks it is?
    ///
    /// Both halves in one place, so no call in this file can be written that
    /// skips one. The comparison is against the credential's own owner rather
    /// than against anything on the request, and a mismatch throws BEFORE a
    /// URLRequest exists — the suite asserts the transport recorded nothing.
    private func mine(_ viewer: OwnerId) throws -> ConnectedAppsCredential {
        guard let now = credential() else { throw ConnectedAppsRefusal(.notSignedIn) }
        guard now.owner == viewer else { throw ConnectedAppsRefusal(.anotherOwner) }
        return now
    }

    private func get(_ path: String, query: [URLQueryItem],
                     as who: ConnectedAppsCredential) async throws -> [String: Any]? {
        try await send(wire(path, query: query, as: who))
    }

    /// The GET this client would make, BUILT AND NOT YET SENT.
    ///
    /// Split out for exactly one caller: `signals` has to see the status code
    /// beside the body, because the far end tells its two failures apart in a
    /// field and a thrown `serverRefused` cannot carry one. Every other call
    /// goes through `send`, which throws on a non-2xx and never lets a refusal
    /// out as data.
    private func wire(_ path: String, query: [URLQueryItem],
                      as who: ConnectedAppsCredential) throws -> URLRequest {
        var parts = URLComponents(
            url: who.baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)
        parts?.queryItems = query.isEmpty ? nil : query
        guard let url = parts?.url else { throw ConnectedAppsRefusal(.unreadableAnswer) }
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        authorize(&request, who)
        return request
    }

    private func post(_ path: String, payload: [String: Any],
                      as who: ConnectedAppsCredential) async throws -> [String: Any]? {
        var request = URLRequest(url: who.baseURL.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        authorize(&request, who)
        request.httpBody = try? JSONSerialization.data(withJSONObject: payload)
        return try await send(request)
    }

    /// The session token, in the header the data API already uses. It is never
    /// put on a query string: a credential in a URL is a credential in browser
    /// history, in our own request logs and in every screenshot of the bar.
    private func authorize(_ request: inout URLRequest, _ who: ConnectedAppsCredential) {
        request.setValue(who.authToken, forHTTPHeaderField: "Authorization")
    }

    /// A NON-2XX THROWS. This is the whole reason the screen can tell "I could
    /// not read your connected apps" from "you have nothing connected": a
    /// refusal handed back as data is a refusal every caller swallows, and the
    /// app then paints a confident empty state over somebody's four connected
    /// apps and invites them to connect what they already have.
    private func send(_ request: URLRequest) async throws -> [String: Any]? {
        let answer = try await probe(request)
        guard (200..<300).contains(answer.status) else {
            throw ConnectedAppsRefusal(.serverRefused, status: answer.status)
        }
        return answer.body
    }

    /// The one place this file touches the transport. `send` is this plus the
    /// throw, so there is no second reading of a status code and no call that
    /// can quietly skip it: a caller reaching for `probe` is choosing to look
    /// at a refusal, in the open, and there is exactly one of those.
    private func probe(_ request: URLRequest) async throws
        -> (status: Int, body: [String: Any]?) {
        let (data, response) = try await transport.send(request)
        guard !data.isEmpty else { return (response.statusCode, nil) }
        return (response.statusCode,
                (try? JSONSerialization.jsonObject(with: data)) as? [String: Any])
    }

    /// The list out of an answer. A body that is not `{ "items": [ … ] }` is
    /// unreadable rather than empty: an answer nobody can parse is not evidence
    /// that somebody has nothing.
    private func items(_ body: [String: Any]?) throws -> [[String: Any]] {
        guard let rows = body?["items"] as? [Any] else {
            throw ConnectedAppsRefusal(.unreadableAnswer)
        }
        return rows.compactMap { $0 as? [String: Any] }
    }

    /// A catalog row. Nil when it cannot name the app: `ToolkitMeta.isUsable`
    /// is the difference between a row and a blank line with a button on it.
    ///
    /// `fileprivate` for one reader, `RankedAppRow(row:)`: a ranked line IS a
    /// catalog row with three facts stapled on, and decoding those six fields a
    /// second time next door is how a `logo` comes back on one screen and not
    /// on the other.
    ///
    /// `nonisolated` because it is arithmetic over a dictionary and touches
    /// nothing this class holds — a row decoder that needed the main actor
    /// could not be called from a value type's initialiser, which is exactly
    /// where the other reader lives.
    nonisolated fileprivate static func toolkit(_ row: [String: Any]) -> ToolkitMeta? {
        guard let slug = ConnectionsPolicy.text(row["slug"]),
              let name = ConnectionsPolicy.text(row["name"]) else { return nil }
        let scopes = (row["scopes"] as? [Any])?.compactMap { ConnectionsPolicy.text($0) } ?? []
        // `mail_hosts`, snake_case beside `app_url`, present on EVERY catalog row
        // from ?slugs= and ?q= AND on every /signals row — the Worker builds both
        // through one `catalogRow()` so the phone's two doors answer one shape.
        //
        // THE LINE THAT JOINS THE SEAM, and until 2026-09-06 it was the missing
        // one: the server had carried this column since that morning and this
        // decoder read six fields, so `CatalogEntry.mailHosts` was fed `[]` by
        // the phone rather than by the catalog and the MX seed could never fire
        // for a reason nobody could see from either end.
        //
        // It reads back EMPTY on every app today, and that is a measurement of
        // the vendor rather than of this line: the catalog publishes no mail
        // host anywhere. `ConnectionsPolicy.text` drops a blank or a non-string
        // at the boundary, because a blank reaching `hostLabels()` is a line that
        // can never match and would sit in the list looking like evidence.
        let mailHosts = (row["mail_hosts"] as? [Any])?
            .compactMap { ConnectionsPolicy.text($0) } ?? []
        return ToolkitMeta(slug: slug, name: name,
                           logo: ConnectionsPolicy.text(row["logo"]),
                           description: ConnectionsPolicy.text(row["description"]),
                           appURL: ConnectionsPolicy.text(row["app_url"]),
                           scopes: scopes,
                           mailHosts: mailHosts)
    }

    /// A slug SHAPED like a slug, through the handoff's own canonicaliser, so
    /// the string this file sends and the string the phone compares a callback
    /// against are produced by one function.
    private static func slug(_ raw: String) throws -> String {
        guard let slug = ConnectHandoff.toolkitSlug(raw) else {
            throw ConnectedAppsRefusal(.toolkitNotNamed)
        }
        return slug
    }

    /// A boolean off a JSON row, THROUGH THE PREDICATE THIS FEATURE ALREADY HAS.
    ///
    /// `ConnectionsPolicy.writesOptedIn` is named for its first caller and is
    /// really the answer to "what does a stored boolean read as": `true` and `1`
    /// count, because the column arrives from storage where booleans are
    /// integers, and EVERYTHING else — absent, null, `0`, `"true"`, `"yes"`, a
    /// number nobody expected — does not. The asymmetry points the safe way.
    ///
    /// That is exactly the floor a disconnect needs, and reusing it is the point:
    /// `revoked` is the only thing that licenses the word "revoked"
    /// (`ConnectionsPolicy.disconnectConfirmation`), so a second reading of a
    /// boolean written here is a second chance to read one generously and tell
    /// somebody their access was removed when it was not.
    private static func flag(_ value: Any?) -> Bool {
        ConnectionsPolicy.writesOptedIn(value)
    }
}

// -------------------------------------------------------- what we already know

/// ONE LINE OF `me/connections/signals`: AN APP THIS OWNER LIVES IN, NAMED.
///
/// Not an `app_usage_signals` row. The table is the server's — six columns, a
/// row per piece of evidence, several rows per app — and what crosses the wire
/// is `signalRow` (connections_api.ts): the RANKED result, one line per app,
/// carrying the catalog's own row so the card needs no second round trip to
/// learn a name.
///
/// SO THE SIX CATALOG FIELDS ARE READ BY THE SAME DECODER `me/connections/
/// catalog` uses, deliberately — `Self.toolkit` — because they are the same six
/// fields and a second reading of them is a second place a `logo` can go
/// missing. Three facts are added on top, and none of them is a verdict:
///
///   * `alias`, which of this owner's accounts the strongest evidence was
///     about, or nothing when the row did not say;
///   * `lastSeenAt`, so a screen can say when;
///   * `sources`, which KINDS of evidence fed the line.
///
/// `sources` AND `alias` STAY STRINGS HERE. The closed enums belong to
/// `ConnectOnboardingPolicy`, which is where the contract is mirrored under a
/// gate, and a second spelling of them in this file would be a second book. A
/// spelling this build has never heard of must read as NOTHING rather than as
/// the nearest one, and it can only do that where the enum is.
///
/// THERE IS NO WEIGHT AND NO OWNER, and both absences are the far end's
/// decision rather than an omission here. The order IS the weight's answer; the
/// scoping is the server's, and the header says what this file can and cannot
/// still do about it.
struct RankedAppRow: Equatable {
    /// The app's own slug, as the catalog spells it. `ToolkitMeta.slug`.
    let toolkit: String
    /// The catalog's name for it. The ONLY place a name comes from.
    let name: String
    let logo: String?
    let alias: String?
    let lastSeenAt: Double
    let sources: [String]

    init(toolkit: String, name: String, logo: String? = nil, alias: String? = nil,
         lastSeenAt: Double, sources: [String] = []) {
        self.toolkit = toolkit
        self.name = name
        self.logo = logo
        self.alias = alias
        self.lastSeenAt = lastSeenAt
        self.sources = sources
    }

    /// The line off the wire, or nil.
    ///
    /// Three things are load-bearing and a line missing any of them is dropped
    /// rather than half-built, exactly as `Connection(row:)` is. A SLUG WITH NO
    /// NAME IS THE ONE THAT MATTERS: it renders as a blank line with a
    /// checkbox on it, which is a person being asked to agree to something the
    /// product cannot name. And an instant nobody can read cannot be shown, so
    /// the "seen last Tuesday" line would be about the epoch.
    init?(row: [String: Any]) {
        guard let meta = ConnectedAppsClient.toolkit(row),
              let seen = ConnectionsPolicy.instant(row["last_seen_at"])
        else { return nil }
        self.toolkit = meta.slug
        self.name = meta.name
        self.logo = meta.logo
        self.alias = ConnectionsPolicy.text(row["alias"])
        self.lastSeenAt = seen
        self.sources = (row["sources"] as? [Any])?
            .compactMap { ConnectionsPolicy.text($0) } ?? []
    }
}

/// WHAT `me/connections/signals` ANSWERED, in the two shapes that are answers.
///
/// The route has four states and the other two — `unreadable` and
/// `catalog-unreadable` — arrive as refusals and leave this file as THROWN
/// refusals, because a refusal handed back as data is a refusal every caller
/// swallows. They are still told apart: `.catalogUnreadable` is its own cause.
///
/// `nothingYet` IS SPELLED THAT WAY ON PURPOSE. The server's word is "none",
/// and a case literally named `none` on a Swift enum is one shadowed
/// `Optional.none` away from a card that reads "you use nothing" because
/// somebody wrote `answer == .none` against an optional.
enum AppSignalsAnswer: Equatable {
    /// This owner's apps, best first, as the server ordered them. Never empty:
    /// an empty list is the other case, and only when the server said so.
    case ranked([RankedAppRow])
    /// We looked, and this owner has no evidence yet. A claim about the person,
    /// and the only one on this route.
    case nothingYet
}

/// WHAT THE SERVER DID WITH A NO.
///
/// Returned rather than swallowed so a caller can hold it to
/// `ConnectOnboardingPolicy.agreesWithSkip` — the three numbers that decide
/// whether the far end meant what this end meant. `state` is the server's own
/// word for the outcome and nothing here branches on it: it is carried for the
/// journal, and a client that read prose to decide what happened would be
/// making the same mistake in a new place.
struct SkipAcknowledgement: Equatable {
    let state: String
    /// The rung of the decline ladder AFTER the write. `nil` when the server
    /// did not say — which is not zero: "the ladder did not move" and "nobody
    /// told us where it is" are different facts and only one of them is safe to
    /// stop asking on.
    let level: Int?
    /// When the quiet runs out, on the server's clock in the server's units.
    let snoozeUntil: Double?
}

// ------------------------------------------------------------ the credential

/// WHO THIS PHONE IS, AT ONE INSTANT.
///
/// A value rather than a reference on purpose: it is read at the top of a call
/// and every later comparison in that call is against the same three fields,
/// so a sign-out landing mid-flight cannot make a request half belong to two
/// people.
struct ConnectedAppsCredential: Equatable {
    /// The server this build talks to. Injected, never a literal here — the app
    /// already knows its own base from configuration, and a host written into
    /// this file is a host nobody can point at a preview.
    let baseURL: URL
    /// The owner ROW id. `OwnerId` cannot be built from a name or an email.
    let owner: OwnerId
    /// The signed-in session token, in `Authorization`, exactly as
    /// `AnticipyBackend` sends it.
    let authToken: String

    init(baseURL: URL, owner: OwnerId, authToken: String) {
        self.baseURL = baseURL
        self.owner = owner
        self.authToken = authToken
    }

    /// The credential a signed-in `AnticipyBackend` is holding, or nil.
    ///
    /// The three fields are exactly what that class carries, because it is the
    /// app's one place for "which server, whose session" and a second answer
    /// here would be a second answer everywhere.
    ///
    /// NIL FOR AN ID THAT IS NOT AN OWNER ROW ID, which is the leg that matters:
    /// this app also holds `session.ownerID`, a UUID it minted for its
    /// pre-accounts identity, and a connection bound to that is a connection
    /// bound to a handset rather than to a person. `OwnerId` refuses it.
    /// Nil for a blank token too — a request with no credential on it is a
    /// request the server answers as somebody else, or as nobody.
    init?(baseURL: URL, accountID: String, authToken: String) {
        guard let owner = OwnerId(accountID) else { return nil }
        guard !authToken.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return nil
        }
        self.init(baseURL: baseURL, owner: owner, authToken: authToken)
    }
}

// ---------------------------------------------------------------- refusals

/// EVERY WAY THIS CLIENT SAYS NO, each with a code for the journal.
///
/// A code and never a sentence, for the same reason `ConnectRefusal` is: a
/// refusal token may name the other company or the vocabulary of a consent
/// screen, and the spec forbids the owner ever seeing those words. The screen
/// writes its own sentence.
struct ConnectedAppsRefusal: Error, Equatable {
    enum Cause: String, CaseIterable, Equatable {
        /// Nobody is signed in on this phone.
        case notSignedIn = "not_signed_in"
        /// The caller named an owner who is not the one signed in. Nothing was
        /// sent.
        case anotherOwner = "another_owner"
        /// A write batch carried a row belonging to somebody else.
        case foreignRow = "foreign_row"
        /// The server answered, and said no. `status` carries which.
        case serverRefused = "server_refused"
        /// The answer was not a shape this client can read.
        case unreadableAnswer = "unreadable_answer"
        /// The catalog named the app in a shape we cannot carry.
        case toolkitNotNamed = "toolkit_not_named"
        /// No permission sentences, or a blank one among them.
        case noSentences = "no_sentences"
        /// A sentence used a word the register forbids. It is not shown.
        case forbiddenSentence = "forbidden_sentence"
        /// The link the server minted is not our own connect page.
        case linkNotOurs = "link_not_ours"
        /// There IS evidence for this owner and the catalog could name none of
        /// it. OUR failure, kept apart from `serverRefused` because the card
        /// says it differently: "I know what you use and cannot describe it
        /// right now" is not "ask me again in a moment", and neither of them is
        /// "you use none of these".
        case catalogUnreadable = "catalog_unreadable"
        /// The answer did not come back over HTTP at all.
        case notHTTP = "not_http"
    }

    let cause: Cause
    let status: Int?

    init(_ cause: Cause, status: Int? = nil) {
        self.cause = cause
        self.status = status
    }

    var code: String { "connected_apps.\(cause.rawValue)" }
}

// ---------------------------------------------------------------- transport

/// THE ONE THING THIS FILE CANNOT DO ON A LAPTOP.
///
/// Everything above — whose call this is, what shape an answer must have, which
/// links may be opened, which sentences may be shown — runs under `swiftc` with
/// no simulator and no network, because the only piece that touches the world
/// is behind this protocol.
@MainActor
protocol ConnectedAppsTransport: AnyObject {
    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse)
}

@MainActor
final class URLSessionConnectedAppsTransport: ConnectedAppsTransport {
    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw ConnectedAppsRefusal(.notHTTP)
        }
        return (data, http)
    }
}

// --------------------------------------------------------------- the copy

/// THE TWO SENTENCES THE CONNECT FLOW ITSELF SAYS.
///
/// Here rather than in `SettingsHomeView` for the reason every other sentence
/// in this feature is in a Backend file: copy is a decision, and this is where
/// a suite can read all of it at once and put it through
/// `ConnectionsPolicy.forbiddenTerm`. `ConnectedAppsModel.Copy` is the screen's
/// own census and owns everything the LIST says; these two belong to the moment
/// between the tap and the browser, which that screen knows nothing about.
///
/// Everything else the disclosure sheet says is borrowed rather than written:
/// the heading and the button are `ConnectedAppsModel.Copy.connectAction(app:)`,
/// the claims are the catalog's own sentences, and the line saying this is
/// optional is `ConnectedAppsModel.Copy.optional`. A second wording of any of
/// them would be a second book.
enum ConnectStartCopy {
    /// While the sentences and the link are being fetched. It promises nothing
    /// and names nothing.
    static let settingUp = "One moment — I'm getting this ready."

    /// The connect could not be started. It says the true and useful half:
    /// nothing happened, and it is worth another go. It never says why, because
    /// every reason is a word this product does not say out loud.
    static let couldNotStart =
        "I could not set that up just now. Nothing has changed on your account — "
        + "try again in a moment."

    /// The census, so a third sentence added later cannot escape the gate.
    static var everySentence: [String] { [settingUp, couldNotStart] }
}
