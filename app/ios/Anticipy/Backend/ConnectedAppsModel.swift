import Foundation
import Combine

/// SETTINGS → CONNECTED APPS: the screen's own decisions, and nothing else's.
///
/// Pure Foundation (plus `Combine`, for `ObservableObject` — no SwiftUI, no
/// UIKit), so every rule below is exercised by
/// `Tests/run_connected_apps_tests.sh` with `swiftc` alone: no simulator, no
/// account, no network.
///
/// WHAT THIS FILE IS NOT. It does not define what a connection IS, what an
/// owner id is, how a status reads, what a disconnect is allowed to claim, or
/// which words are forbidden. All of that is `ConnectionsPolicy` next door —
/// the Swift mirror of `spike/two-hands/src/connections/contract.ts`, whose
/// runner reads the TypeScript at run time and refuses a divergence. A second
/// `OwnerId` or a second disconnect sentence in this file would be a second
/// book to keep in step, which is how the two halves of this product drift
/// apart while both suites stay green.
///
/// So what is left here is exactly the screen's own half:
///
///   * WHOSE LIST IS ON SCREEN, across a sign-in, a sign-out, and a response
///     that arrives after either. Every read and every write is compared
///     against the account signed in at that instant.
///   * THE SWITCH THAT MUST NOT LIE. "Let Anticipy make changes" moves at once
///     and moves BACK when the write does not land, with a sentence, because a
///     switch that silently reads ON over a stored OFF is a person believing
///     they allowed something they did not — and the router believing it may
///     write.
///   * ASK, THEN ACT, THEN SAY WHAT HAPPENED. A disconnect is confirmed first
///     and reported with `ConnectionsPolicy.disconnectConfirmation`, which is
///     the only thing allowed to decide whether the word "revoked" is true.
///   * EMPTY IS NOT BROKEN. Somebody with nothing connected is invited;
///     somebody whose list could not be READ is told that plainly. Folding
///     those together tells a person with four connected apps that they have
///     none.
///
/// NO APP IS NAMED IN THIS FILE, and the runner enforces it. Names, logos and
/// descriptions arrive from the catalog at run time through
/// `ConnectedAppsStore`; a new app in the catalog is a new app on this screen
/// with zero code.
///
/// LAW 1, and it is why `search` looks so thin. Deciding that the letters
/// somebody typed mean a particular app is a MEANING question — "my work
/// email" and "office mail" and a half-typed brand are the same request and no
/// local list holds them all. Nothing here filters, ranks or corrects: the
/// query goes to the catalog as typed and what comes back is what is shown.
/// The only thing this file does to a query is trim the spaces around it.
@MainActor
final class ConnectedAppsModel: ObservableObject {

    // ------------------------------------------------------- what is rendered

    /// One drawn app. `ConnectionCard` is the contract-shaped half — one card
    /// per app even when the owner has two accounts on it, because the write
    /// opt-in is per app. The rest is this screen's wording for it.
    struct Row: Equatable, Identifiable {
        let card: ConnectionCard
        /// WHERE THE SWITCH SITS, ANSWERED BY THE PREDICATE THAT DECIDES THE
        /// WRITE. Stored rather than read off `card.writesEnabled`, and that
        /// is a fix rather than a preference — see `row(for:_:)`.
        let writesEnabled: Bool
        let statusWords: String
        let writesWords: String
        let lastUsedWords: String
        let writesTitle: String
        let writesDetail: String
        let disconnectWords: String

        var id: String { card.toolkit }
        var name: String { card.name }
        var accountLabel: String { card.accountLabel }
        var logoURL: URL? { card.logoURL }
    }

    /// What the whole screen is, in five states.
    enum Screen: Equatable {
        case signedOut(String)
        case loading(String)
        case invitation(String)
        case apps([Row])
        case trouble(String)
    }

    /// The "Add an app" search, in five states for the same reason: "nobody has
    /// typed anything", "nothing matched" and "the catalog could not be
    /// reached" are three different things to say.
    enum SearchState: Equatable {
        case idle(String)
        case searching(String)
        case results([Found])
        case nothingFound(String)
        case trouble(String)
    }

    /// A catalog hit. `alreadyConnected` is an id comparison against this
    /// owner's own rows, not a judgement about the words.
    struct Found: Equatable, Identifiable {
        let meta: ToolkitMeta
        let alreadyConnected: Bool
        /// The catalog's OWN sentence about the app — when it is a sentence
        /// this product is allowed to say. Nil when there is none and nil when
        /// it is in the register we refuse; see `shownDescription`.
        let subtitle: String?

        var id: String { meta.slug }
    }

    /// The confirmation the screen must show before anything is disconnected.
    ///
    /// IT CARRIES THE OWNER IT WAS POSED FOR, and that is the fix for a real
    /// defect rather than a tidiness: the screen keeps its OWN copy of this
    /// question (see `SettingsConnectedAppsView.confirming`, and the comment
    /// there for why it has to), and a copy is a place a previous account's app
    /// name can live through a sign-out. Without this field nothing could tell
    /// A's question from B's — the toolkit and the app name are the same string
    /// for both — so "Disconnect Fernwood Notes?" could still be on the screen
    /// of a phone that had just been handed to somebody else, and answering it
    /// would be the new account answering the old one's question.
    struct PendingDisconnect: Equatable {
        let owner: OwnerId
        let toolkit: String
        let appName: String
        let question: String
        let detail: String
        let confirmWords: String
        let cancelWords: String
    }

    /// What happened to a toggle. `reverted` carries the sentence the person is
    /// shown; `refused` means nothing was touched and nothing was sent.
    enum WriteOutcome: Equatable {
        case saved
        case reverted(String)
        case refused
    }

    /// What happened to a disconnect: the combined result the provider gave,
    /// and the sentence `ConnectionsPolicy` turned it into.
    enum DisconnectVerdict: Equatable {
        case reported(DisconnectResult, String)
        case refused
    }

    // ------------------------------------------------------------- the state

    private let store: ConnectedAppsStore
    private let now: () -> Date

    /// Who this screen is for. Set from the signed-in account's row id, and
    /// cleared on sign-out. Every read and every write is compared against it.
    @Published private(set) var owner: OwnerId?
    @Published private(set) var searchState: SearchState
    @Published private(set) var pendingDisconnect: PendingDisconnect?
    /// The one sentence the screen is currently saying about something that
    /// just happened — a switch that went back, a disconnect that landed.
    @Published private(set) var notice: String?

    private enum Phase: Equatable { case notLoaded, loading, ready, trouble }
    @Published private var phase: Phase = .notLoaded

    /// The owner's connections and the catalog rows that name them.
    /// `listingOwner` is whose they are: a list loaded for somebody else is
    /// never shown to anybody, and never quietly reused after a sign-in.
    @Published private var loaded: [Connection] = []
    private var catalog: [ToolkitMeta] = []
    private var listingOwner: OwnerId?

    /// Late answers lose. A response for load N-1 arriving after load N started
    /// — or after the account changed — is dropped, the same rule
    /// `RefreshAccountPolicy` holds for the session's own polling, and for the
    /// same measured reason: it already happened on this phone.
    private var loadGeneration = 0
    private var searchGeneration = 0

    init(store: ConnectedAppsStore, now: @escaping () -> Date = Date.init) {
        self.store = store
        self.now = now
        self.searchState = .idle(Copy.searchPrompt)
    }

    // ------------------------------------------------------- who is signed in

    /// The account signed in on this phone became this one. Everything held for
    /// anybody else goes, before a single row can be drawn under the new name.
    func signIn(_ newOwner: OwnerId) {
        guard owner != newOwner else { return }
        forgetEverything()
        owner = newOwner
    }

    func signOut() {
        forgetEverything()
        owner = nil
    }

    private func forgetEverything() {
        loadGeneration += 1
        searchGeneration += 1
        loaded = []
        catalog = []
        listingOwner = nil
        phase = .notLoaded
        pendingDisconnect = nil
        notice = nil
        searchState = .idle(Copy.searchPrompt)
    }

    func dismissNotice() { notice = nil }

    // -------------------------------------------------------------- the list

    /// Read this owner's connections. Safe to call again; the last call wins.
    func load() async {
        guard let signedIn = owner else {
            forgetEverything()
            return
        }
        loadGeneration += 1
        let generation = loadGeneration
        if listingOwner != signedIn {
            loaded = []
            catalog = []
            listingOwner = nil
        }
        phase = .loading

        do {
            let rows = try await store.connections(owner: signedIn)
            guard stillCurrent(generation, signedIn) else { return }
            // The store scopes its own query, and the answer is scoped again
            // here. That is the redundancy `OwnerScoped` exists for: a filter
            // that forgets its clause, a cache keyed one field too loosely, or
            // a response that lands after a sign-out all produce a list that
            // looks correct at every line and holds somebody else's mailbox.
            let mine = OwnerScoped.rows(rows, for: signedIn)
            let slugs = Array(Set(mine.map(\.toolkit))).sorted()
            var described: [ToolkitMeta] = []
            if !slugs.isEmpty {
                // A catalog that cannot be reached costs the logos and the
                // pretty names, and nothing else — `settingsCards` falls back
                // to the slug the connection itself carries.
                described = (try? await store.describe(toolkits: slugs, owner: signedIn)) ?? []
                guard stillCurrent(generation, signedIn) else { return }
            }
            loaded = mine
            catalog = described
            listingOwner = signedIn
            phase = .ready
        } catch {
            guard stillCurrent(generation, signedIn) else { return }
            loaded = []
            catalog = []
            listingOwner = signedIn
            phase = .trouble
        }
    }

    private func stillCurrent(_ generation: Int, _ expected: OwnerId) -> Bool {
        generation == loadGeneration && owner == expected
    }

    /// The rows for one owner, and no rows for anybody else. Asked WITH the
    /// owner rather than answered from stored state alone, so the caller's idea
    /// of who is signed in has to agree with this one.
    func rows(for viewer: OwnerId) -> [Row] {
        guard let signedIn = owner, viewer == signedIn, listingOwner == signedIn else { return [] }
        return ConnectionsPolicy.settingsCards(rows: loaded, catalog: catalog, for: signedIn)
            .map { row(for: $0, signedIn) }
    }

    func screen(for viewer: OwnerId?) -> Screen {
        guard let viewer, let signedIn = owner, viewer == signedIn else {
            return .signedOut(Copy.signedOut)
        }
        guard listingOwner == signedIn else { return .loading(Copy.loading) }
        switch phase {
        case .notLoaded, .loading:
            return .loading(Copy.loading)
        case .trouble:
            return .trouble(Copy.trouble)
        case .ready:
            let drawn = rows(for: viewer)
            return drawn.isEmpty ? .invitation(Copy.invitation) : .apps(drawn)
        }
    }

    /// ONE PREDICATE FOR THE WRITE LICENCE, ASKED THE WAY THE ROUTER ASKS IT.
    ///
    /// `ConnectionsPolicy.writesEnabled` IS `mayUse(..., .write, ...)` — the
    /// call anything about to send, create or change something in the owner's
    /// app has to pass. This row's switch, and the sentence beside it, are that
    /// same call and nothing else.
    ///
    /// WHY NOT `card.writesEnabled`, WHICH LOOKS LIKE THE SAME THING AND SAYS
    /// SO IN ITS OWN COMMENT. It is not the same thing, and the comment
    /// claiming it is is false — it is the "Same floor as `mayUse`" line on
    /// the two-account fold in `ConnectionsPolicy.settingsCards`, and it is
    /// still there because that file is the contract mirror and is not this
    /// one's to edit. `settingsCards` folds the opt-in over every
    /// row whose status is not `disconnected`; `mayUse` folds it over
    /// `connected` rows only. The two disagree in BOTH directions, and an
    /// adversary drove both on 2026-09-05:
    ///
    ///   PERMISSIVE, and this is the one that hurts. An app whose only account
    ///   NEEDS SIGNING IN AGAIN, carrying `writes_enabled = 1` from before it
    ///   broke, drew a switch reading ON and the sentence "On, I can also send,
    ///   create and change things in it" — while every write to it would have
    ///   been refused. A person reads that and believes they granted something
    ///   the product does not have; the next thing they believe is that we
    ///   silently did not do what they asked.
    ///
    ///   RESTRICTIVE. One healthy opted-in account plus one broken account that
    ///   was never opted in drew OFF over a write that WOULD have gone through.
    ///
    /// Fixing this in `settingsCards` would be the tidier place for it and is
    /// not this file's to make — `ConnectionsPolicy` is the contract mirror and
    /// its own runner compares it against `contract.ts`. So the screen asks the
    /// write question of the thing that answers the write question, and the
    /// suite compares the two answers across every shape two accounts can be
    /// in. If the card's own field is ever made to agree, this call keeps
    /// agreeing with it and nothing here needs to change.
    private func row(for card: ConnectionCard, _ signedIn: OwnerId) -> Row {
        let mayWrite = ConnectionsPolicy.writesEnabled(rows: loaded, toolkit: card.toolkit,
                                                       for: signedIn)
        return Row(card: card,
                   writesEnabled: mayWrite,
                   statusWords: ConnectionsPolicy.statusLine(card.status),
                   writesWords: ConnectionsPolicy.writesLine(mayWrite),
                   lastUsedWords: Copy.lastUsed(card.lastUsedAt, now: now()),
                   writesTitle: Copy.writesTitle,
                   writesDetail: Copy.writesDetail(app: card.name),
                   disconnectWords: Copy.disconnectAction(app: card.name))
    }

    private func card(for toolkit: String, _ signedIn: OwnerId) -> ConnectionCard? {
        ConnectionsPolicy.settingsCards(rows: loaded, catalog: catalog, for: signedIn)
            .first { $0.toolkit == toolkit }
    }

    // ---------------------------------------------------- the write opt-in

    /// Flip "let Anticipy make changes" for one app.
    ///
    /// OPTIMISTIC, AND IT REVERTS. The switch moves at once because a switch
    /// that waits on a network feels broken — and if the write does not land it
    /// moves back and the person is told, because the only thing worse than a
    /// switch that lags is a switch that lies.
    ///
    /// Per APP, not per account: `ConnectionsPolicy.writesTransition` moves
    /// every one of this owner's connected accounts on the app together, and
    /// the rows it hands back are exactly what is written. That is what makes
    /// it impossible for a mixed list to travel through a toggle and land on
    /// somebody else's connection.
    @discardableResult
    func setWrites(_ on: Bool, toolkit: String, owner viewer: OwnerId) async -> WriteOutcome {
        guard let signedIn = owner, viewer == signedIn, listingOwner == signedIn else {
            return .refused
        }
        let originals = ConnectionsPolicy.connectedRows(loaded, toolkit: toolkit, for: signedIn)
        let transition = ConnectionsPolicy.writesTransition(rows: loaded, toolkit: toolkit,
                                                            to: on, for: signedIn)
        guard transition.applied else { return .refused }
        // Already where it is being put, on every account: nothing to send.
        // A SKEWED app — one account opted in, one not — is not this case, and
        // does send, because the screen's toggle is the AND of them.
        guard !originals.allSatisfy({ $0.writesEnabled == on }) else { return .saved }

        let app = card(for: toolkit, signedIn)?.name
            ?? ConnectionsPolicy.appName(nil, fallback: toolkit)
        notice = nil
        apply(transition.rowsToWrite, for: signedIn)

        do {
            try await store.setWrites(transition.rowsToWrite, owner: signedIn)
            guard owner == signedIn else { return .refused }
            return .saved
        } catch {
            // The account may have changed while the write was in flight. If it
            // did, this owner's list is already gone: there is nothing to put
            // back, and nothing may be said to whoever is signed in now.
            guard owner == signedIn, listingOwner == signedIn else { return .refused }
            apply(originals, for: signedIn)
            let said = Copy.writeNotSaved(app: app)
            notice = said
            return .reverted(said)
        }
    }

    /// Put updated rows back into the list, matched by account id and owner.
    private func apply(_ rows: [Connection], for signedIn: OwnerId) {
        guard !rows.isEmpty else { return }
        var byAccount: [String: Connection] = [:]
        for row in rows where OwnerScoped.belongs(row, to: signedIn) {
            byAccount[row.connectedAccountID] = row
        }
        loaded = loaded.map { existing in
            guard OwnerScoped.belongs(existing, to: signedIn),
                  let replacement = byAccount[existing.connectedAccountID] else { return existing }
            return replacement
        }
    }

    // ------------------------------------------------------------ disconnect

    /// Nothing is disconnected without being asked about first. This only poses
    /// the question; `confirmDisconnect` is the only thing that acts.
    func askToDisconnect(_ toolkit: String, owner viewer: OwnerId) {
        guard let signedIn = owner, viewer == signedIn, listingOwner == signedIn,
              let card = card(for: toolkit, signedIn) else {
            pendingDisconnect = nil
            return
        }
        pendingDisconnect = PendingDisconnect(
            owner: signedIn,
            toolkit: card.toolkit,
            appName: card.name,
            question: Copy.disconnectQuestion(app: card.name),
            detail: Copy.disconnectDetail(app: card.name),
            confirmWords: Copy.disconnectConfirm,
            cancelWords: Copy.disconnectCancel)
    }

    func cancelDisconnect() { pendingDisconnect = nil }

    /// DOES THE QUESTION THE SCREEN IS HOLDING STILL STAND?
    ///
    /// The view cannot answer this and must not try. It holds its own copy of
    /// the pending question because iOS dismisses an alert AS its button fires:
    /// an `isPresented` bound to `pendingDisconnect` cleared the model's copy
    /// before the confirm action ran, the action found nothing pending, and the
    /// destructive button disconnected nothing at all. The copy is the fix for
    /// that — and it is also a previous account's app name sitting in a `@State`
    /// that a sign-out does not touch.
    ///
    /// So the copy comes BACK through here before it is drawn or acted on, with
    /// the account signed in at that instant, exactly like every other call on
    /// this screen. Four things have to agree, and each one is a way the held
    /// copy goes stale:
    ///
    ///   * somebody is signed in, and the viewer is that somebody
    ///     (a sign-out mid-alert);
    ///   * the question was posed FOR that same owner
    ///     (the phone changed hands and the new account has the same app);
    ///   * the app is still on that list
    ///     (it was disconnected in the meantime, or from the search screen,
    ///     which is fed by the same rows).
    ///
    /// The fourth clause, `listingOwner == signedIn`, is a REDUNDANCY and is
    /// declared as one: `loaded` is only ever non-empty alongside a matching
    /// `listingOwner` (`load` sets both with no `await` between them, and
    /// `forgetEverything` clears both), so today no held question can pass the
    /// card lookup and fail this. The suite cannot drive it apart, and a
    /// predicate nothing can drive is normally a defect — this one is kept
    /// because it makes all four methods on this screen ask the same four
    /// questions in the same order, and because the day that invariant is
    /// broken by an `await` landing between those two lines, the failure it
    /// prevents is precisely the dead destructive button this copy exists to
    /// fix: `confirmDisconnect` checks `listingOwner` and would refuse, while
    /// the alert went on being drawn.
    ///
    /// Nil is the answer that closes the alert, and `confirmDisconnect` makes
    /// the same comparisons again before it acts — this decides what is DRAWN,
    /// never what is permitted.
    func questionStillStands(_ held: PendingDisconnect?,
                             for viewer: OwnerId?) -> PendingDisconnect? {
        guard let held, let viewer, let signedIn = owner,
              viewer == signedIn, held.owner == signedIn,
              listingOwner == signedIn,
              card(for: held.toolkit, signedIn) != nil else { return nil }
        return held
    }

    /// Act on the pending question, and say what actually happened.
    ///
    /// Every one of this owner's connected accounts on the app is disconnected,
    /// because the card was one app. The per-account results are folded by
    /// `ConnectionsPolicy.combine` — `revoked` is EVERY, `revokeUnavailable` is
    /// ANY — and only `disconnectConfirmation` decides what the person is told.
    /// A call that throws is a result that revoked nothing and deleted nothing,
    /// which is the honest reading of "I could not reach it".
    @discardableResult
    func confirmDisconnect(owner viewer: OwnerId) async -> DisconnectVerdict {
        guard let signedIn = owner, viewer == signedIn, listingOwner == signedIn,
              let pending = pendingDisconnect else {
            pendingDisconnect = nil
            return .refused
        }
        pendingDisconnect = nil
        notice = nil

        // EVERY row this owner still has on the app, not only the healthy
        // ones. `connectedRows` means `status == .connected`, and a connection
        // that NEEDS SIGNING IN AGAIN is still a connection at the provider —
        // filtering to connected here left the one card a person most wants to
        // remove unremovable, and told them "there's nothing to disconnect"
        // about a row they were looking at.
        let live = OwnerScoped.rows(loaded, for: signedIn)
            .filter { $0.toolkit == pending.toolkit && $0.status != .disconnected }
        var results: [DisconnectResult] = []
        var gone: Set<String> = []
        for row in live {
            do {
                let result = try await store.disconnect(owner: signedIn,
                                                        connectedAccountID: row.connectedAccountID)
                results.append(result)
                if result.deleted { gone.insert(row.connectedAccountID) }
            } catch {
                results.append(DisconnectResult(appName: pending.appName, attempted: 1,
                                                revoked: false, deleted: false,
                                                revokeUnavailable: false))
            }
            guard owner == signedIn, listingOwner == signedIn else { return .refused }
        }

        let combined = ConnectionsPolicy.combine(results, appName: pending.appName)
        // Only the accounts the provider actually let go leave the screen. A
        // half-done disconnect that cleared the whole card would tell somebody
        // an account is gone while its token is live.
        if !gone.isEmpty {
            loaded = loaded.map { row in
                guard OwnerScoped.belongs(row, to: signedIn),
                      gone.contains(row.connectedAccountID) else { return row }
                return ConnectionsPolicy.afterDisconnect(row)
            }
            refreshFoundFlags()
        }
        let said = ConnectionsPolicy.disconnectConfirmation(result: combined)
        notice = said
        return .reported(combined, said)
    }

    // ------------------------------------------------------------ add an app

    /// Search the whole catalog — which is how somebody connects an app nobody
    /// ever asked them about.
    ///
    /// The query is not read here. It is handed to the catalog as typed, and
    /// what comes back is shown in the order it came back: no local list to
    /// match against, no ranking, no "did you mean". The one thing dropped is a
    /// row that cannot name itself, because `ToolkitMeta.isUsable` is the
    /// difference between a row and a blank line with a button on it.
    func search(_ query: String, owner viewer: OwnerId) async {
        guard let signedIn = owner, viewer == signedIn else {
            searchState = .idle(Copy.searchPrompt)
            return
        }
        let asked = query.trimmingCharacters(in: .whitespacesAndNewlines)
        searchGeneration += 1
        let generation = searchGeneration
        guard !asked.isEmpty else {
            searchState = .idle(Copy.searchPrompt)
            return
        }
        searchState = .searching(Copy.searching)
        do {
            let hits = try await store.catalog(matching: asked, owner: signedIn)
            guard generation == searchGeneration, owner == signedIn else { return }
            let usable = hits.filter(\.isUsable)
            guard !usable.isEmpty else {
                searchState = .nothingFound(Copy.nothingFound(query: asked))
                return
            }
            searchState = .results(usable.map {
                Found(meta: $0, alreadyConnected: isConnected($0.slug, for: signedIn),
                      subtitle: Self.shownDescription($0.description))
            })
        } catch {
            guard generation == searchGeneration, owner == signedIn else { return }
            searchState = .trouble(Copy.searchTrouble)
        }
    }

    func clearSearch() {
        searchGeneration += 1
        searchState = .idle(Copy.searchPrompt)
    }

    private func isConnected(_ slug: String, for signedIn: OwnerId) -> Bool {
        !ConnectionsPolicy.connectedRows(loaded, toolkit: slug, for: signedIn).isEmpty
    }

    /// An app disconnected on the list must stop reading as connected on the
    /// search screen; the flag there is derived from the same rows.
    private func refreshFoundFlags() {
        guard case .results(let found) = searchState, let signedIn = owner else { return }
        searchState = .results(found.map {
            Found(meta: $0.meta, alreadyConnected: isConnected($0.meta.slug, for: signedIn),
                  subtitle: $0.subtitle)
        })
    }

    /// THE CATALOG'S OWN WORDS, THROUGH THE SAME GATE AS OURS.
    ///
    /// `ToolkitMeta.description` is written by a vendor, arrives at run time
    /// from 1,400 catalog rows nobody here has read, and until 2026-09-05 was
    /// rendered verbatim as the subtitle of every "Add an app" result — which
    /// is also the VoiceOver hint on the button that starts a connect. It is
    /// not in `Copy.everySentence`, so the suite's register leg never saw one:
    /// a blurb reading "authorize our API" or naming the provider went onto the
    /// screen of a product whose first rule is that the person never hears any
    /// of that. The gate the rest of this screen passes is worth exactly
    /// nothing while the one string nobody wrote goes around it.
    ///
    /// WITHHELD, NOT REWRITTEN. There is no cleaning pass here and there must
    /// not be one: editing a sentence into a vendor's mouth is a worse failure
    /// than an app with no subtitle, and the row still carries the app's name,
    /// its logo and the button. Silence is a state this screen already has.
    ///
    /// THE NAME IS NOT SCREENED, on purpose, and that is `forbiddenTerm`'s own
    /// rule: an app that calls itself something on the list gets called that,
    /// because quoting a name is not us using the word. The check belongs to
    /// the prose around it.
    ///
    /// LAW 1, SINCE THIS WIDENS A WORD LIST'S INPUT. `forbiddenTerm` justifies
    /// itself as a CEILING on text WE are about to show, drafted by us or by
    /// our own model, whose only outcome is "do not show this" and whose
    /// failure mode is silence. A vendor's sentence we are about to put on our
    /// own screen is text we are about to show; the polarity, the outcome and
    /// the failure mode are all unchanged. Nothing here reads a human's words
    /// and nothing here decides what anybody meant — the one meaning question
    /// on this screen, WHICH APP a person typed at, is still asked of the
    /// catalog and never of a list in this file.
    static func shownDescription(_ raw: String?) -> String? {
        guard let said = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
              !said.isEmpty,
              ConnectionsPolicy.saysNothingForbidden(said) else { return nil }
        return said
    }

    // --------------------------------------------------------------- the copy

    /// EVERY SENTENCE THIS SCREEN WRITES, in one place.
    ///
    /// Here rather than in the view because copy is a decision, and this is
    /// where decisions are testable: the suite reads all of it at once through
    /// `everySentence` and puts it through `ConnectionsPolicy.forbiddenTerm` —
    /// the same register gate the nudge card and the text thread pass, and the
    /// same list `words.ts` holds on the server.
    ///
    /// The sentences that are NOT here are the ones the contract already owns:
    /// the status line, the read/write line, and every ending of a disconnect.
    /// Those come from `ConnectionsPolicy`, because a second wording of "was it
    /// actually revoked" is exactly the kind of second book that drifts.
    enum Copy {
        static let title = "Connected apps"
        static let sectionHeader = "Your apps"
        static let signedOut = "Sign in on this iPhone to see the apps you have connected."
        static let loading = "Checking what you have connected…"
        static let trouble = "I could not read your connected apps just now. That is me failing to reach Anticipy, not a sign that nothing is connected."
        static let tryAgain = "Try again"
        /// The notice says what just happened; this puts it away. Without it
        /// the last sentence sits on the screen until the next action, which
        /// reads as a state rather than as news.
        static let dismissNotice = "OK"
        static let invitation = "Nothing is connected yet. Connect an app and I can work in it for you directly, and you can undo it here whenever you like."
        /// The screen's version of `ConnectionsPolicy.optionalLine(app:)`, which
        /// needs an app's name and is for one ask. Same sentence, same reason:
        /// the browser does the same work either way, which is what makes it
        /// true rather than polite.
        static let optional = "Entirely up to you — I can do any of this in your browser either way."

        static let addAnApp = "Add an app"
        static let searchLabel = "App"
        static let searchPlaceholder = "Type a name"
        static let searchPrompt = "Type the name of an app you use. Anything I can reach is in here, including the ones I have never asked you about."
        static let searching = "Looking…"
        static let searchTrouble = "I could not search just now. Try again in a moment."
        static let alreadyConnected = "Already connected"

        static func nothingFound(query: String) -> String {
            "Nothing came back for “\(query)”. Try the name the app calls itself."
        }

        static func connectAction(app: String) -> String { "Connect \(app)" }

        /// Reuses `PlainDuration` for the reason every other screen does: one
        /// stretch of time reads the same way everywhere, or the reader is
        /// comparing three different claims about one measurement.
        ///
        /// The instant is epoch SECONDS, which is what `ConnectionsPolicy`
        /// counts in throughout (`linkTTLSeconds`, the snooze arithmetic).
        static func lastUsed(_ at: Double?, now: Date) -> String {
            guard let at, at > 0 else { return "Not used yet" }
            let seconds = Int(now.timeIntervalSince1970 - at)
            guard seconds > 0 else { return "Last used just now" }
            return "Last used \(PlainDuration.words(seconds)) ago"
        }

        static let writesTitle = "Let Anticipy make changes"

        static func writesDetail(app: String) -> String {
            "Off, I only read \(app). On, I can also send, create and change things in it."
        }

        static func writeNotSaved(app: String) -> String {
            "That switch has gone back: I could not save the change for \(app), so nothing about it changed. Try again in a moment."
        }

        static func disconnectAction(app: String) -> String { "Disconnect \(app)" }
        static func disconnectQuestion(app: String) -> String { "Disconnect \(app)?" }

        static func disconnectDetail(app: String) -> String {
            "I will stop using \(app) and forget the connection. You can connect it again whenever you want."
        }

        static let disconnectConfirm = "Disconnect"
        static let disconnectCancel = "Keep it"

        /// The census. Every sentence, with one sample name filled in by the
        /// caller — the sample lives in the SUITE, not here, because a real app
        /// name in this file is the thing the runner refuses.
        static func everySentence(sampleApp app: String, sampleQuery query: String) -> [String] {
            [
                title, sectionHeader, signedOut, loading, trouble, tryAgain,
                dismissNotice,
                invitation, optional, addAnApp, searchLabel, searchPlaceholder,
                searchPrompt, searching, searchTrouble, alreadyConnected,
                nothingFound(query: query), connectAction(app: app),
                lastUsed(nil, now: Date()),
                lastUsed(0.0, now: Date(timeIntervalSince1970: 3600)),
                lastUsed(1.0, now: Date(timeIntervalSince1970: 3601)),
                writesTitle, writesDetail(app: app), writeNotSaved(app: app),
                disconnectAction(app: app), disconnectQuestion(app: app),
                disconnectDetail(app: app), disconnectConfirm, disconnectCancel,
            ]
        }
    }
}

/// THE SEAM. Everything this screen knows about the outside world.
///
/// Every call carries the owner, without exception — including the catalog
/// search, which does not strictly need one. That is deliberate: a call that
/// does not take an owner is a call somebody can make while signed out, and the
/// whole point of the model above is that there is no such call.
///
/// `@MainActor` because the screen is: one actor, one list, no chance of a
/// response landing on a copy of the state somebody else is also holding.
/// Implementations do their waiting inside `await`.
@MainActor
protocol ConnectedAppsStore: AnyObject {
    /// This owner's connections. The server scopes the query; the model scopes
    /// the answer again.
    func connections(owner: OwnerId) async throws -> [Connection]

    /// Catalog rows for the toolkits given — the reason no app is named in the
    /// app.
    func describe(toolkits: [String], owner: OwnerId) async throws -> [ToolkitMeta]

    /// The whole catalog, searched as typed. Nothing local filters or ranks
    /// what comes back.
    func catalog(matching query: String, owner: OwnerId) async throws -> [ToolkitMeta]

    /// The write opt-in. The rows handed over are exactly the ones
    /// `ConnectionsPolicy.writesTransition` produced — write those, never the
    /// list they came from. Throwing means the switch goes back on the screen.
    func setWrites(_ rows: [Connection], owner: OwnerId) async throws

    /// Revoke, THEN delete, at the far end — one connected account per call.
    /// What comes back is what the person is told, including the case where the
    /// revoke could not be done for us.
    func disconnect(owner: OwnerId, connectedAccountID: String) async throws -> DisconnectResult
}

// ------------------------------------- the store a build without a client has

/// WHAT THE SCREEN IS HANDED ON A BUILD THAT CANNOT REACH THE SERVER YET.
///
/// Settings now has a row that opens this screen — before 2026-09-05 nothing in
/// the app navigated to it at all, so the screen, its model and its whole suite
/// were a feature no person could get to. The row is the reachable half. The
/// CLIENT that reads an owner's connections off the server is the other half,
/// and it is not written, because there is nothing yet to write it against:
/// `migration/workers/src/connections/` holds the D1 store and the provider,
/// and `migration/workers/src/index.ts` serves no route in front of them
/// (checked 2026-09-05). A client invented against routes nobody serves is a
/// contract this repo would then have to keep — see LAW 3: repo-green is not
/// done, and a guess about a URL is not even repo-green.
///
/// So this build answers every call with a refusal, and the screen says the one
/// true thing it can say: `Copy.trouble` — "I could not read your connected
/// apps just now. That is me failing to reach Anticipy, not a sign that nothing
/// is connected."
///
/// THAT SENTENCE IS THE WHOLE REASON THIS TYPE EXISTS RATHER THAN AN EMPTY
/// ANSWER. A store that returned `[]` would render `Copy.invitation` —
/// "Nothing is connected yet" — to somebody who connected two apps by text,
/// and would invite them to connect what they already have. Empty is not
/// broken, and broken is not empty; the model already keeps those apart, and
/// `ConnectedAppsModelTests` pins this type to the `.trouble` side of that line
/// so no later "harmless" default can quietly move it.
///
/// The day a client exists it is constructed here instead, and nothing else on
/// the screen changes: the states, the copy and the suite are already written
/// for a store that sometimes answers.
@MainActor
final class UnreachableConnectedAppsStore: ConnectedAppsStore {

    /// Named for what it is, so a log line reads as a missing client rather
    /// than as a server that said no.
    struct NoConnectionsClient: Error {}

    func connections(owner: OwnerId) async throws -> [Connection] {
        throw NoConnectionsClient()
    }

    func describe(toolkits: [String], owner: OwnerId) async throws -> [ToolkitMeta] {
        throw NoConnectionsClient()
    }

    func catalog(matching query: String, owner: OwnerId) async throws -> [ToolkitMeta] {
        throw NoConnectionsClient()
    }

    func setWrites(_ rows: [Connection], owner: OwnerId) async throws {
        throw NoConnectionsClient()
    }

    func disconnect(owner: OwnerId, connectedAccountID: String) async throws -> DisconnectResult {
        throw NoConnectionsClient()
    }
}
