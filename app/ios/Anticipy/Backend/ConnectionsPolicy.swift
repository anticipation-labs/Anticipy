import Foundation

/// CONNECTIONS — the pure decisions behind "connect your own apps", with no
/// screen attached.
///
/// The server-side contract is `spike/two-hands/src/connections/contract.ts`
/// and this file AGREES WITH IT rather than restating it in Swift's accent. The
/// tables, the five nudge states, the three connection statuses, the two
/// aliases, the snooze ladder and the OwnerId rule are all decided there;
/// `run_connections_policy_tests.sh` reads that file back at run time and goes
/// red the day the two disagree. A constant retyped here without that leg is a
/// second source of truth, and a second source of truth about whose mailbox we
/// are touching is the failure below.
///
/// ── THE WRONG-PERSON FAILURE, WHICH IS WHAT ALL OF THIS IS SHAPED AROUND ──
///
/// During the week-1 spike one operator's own Gmail and Calendar were connected
/// by hand, bound to the `user_id` **"omar"** — a display name. That is one
/// person's tokens serving everybody. It was revoked and deleted
/// (`research/2026-09-05-composio-connections.md`, item 2), and the contract's
/// answer is a sentence in capitals:
///
///     THE USER ID IS THE OWNER ROW ID, ALWAYS, AND NEVER A NAME.
///
/// `OwnerId` below is the Swift half of that. It is a distinct type with a
/// failable initialiser, so a display name, an email or an empty string cannot
/// be passed where an id belongs; and `OwnerScoped` is the rule that a list of
/// rows is FILTERED BY THE SIGNED-IN OWNER rather than trusted. Every public
/// function in this file that reads or writes a connection, a nudge or a toggle
/// takes an `OwnerId` and filters. That is belt and braces on top of a WHERE
/// clause on the server, and it stays: the single worst thing this feature can
/// do is act on somebody else's account, and it has already happened once.
///
/// ── NO APP IS HARDCODED ──────────────────────────────────────────────────
///
/// There is not one app name, slug, logo or permission word in this file, and
/// there must never be one. Names and logos arrive from the catalog at run time
/// (`ToolkitMeta`), so a new app in the catalog is a new app in Anticipy with
/// zero code here. The suite pins it behaviourally — an invented slug renders
/// identically to a real one — and the runner greps this source for app names
/// so the day somebody adds a `switch toolkit` it is red before review.
///
/// ── THE REGISTER ─────────────────────────────────────────────────────────
///
/// The person never hears the vendor's name, and never hears the vocabulary of
/// a consent screen written by a legal team: no "authorize", no "grant access",
/// no "permissions", no "integration", no "API", no "OAuth". It is "connect
/// your <app>", in the app's own name. `forbiddenTerm(in:)` is that rule,
/// executable, and the suite runs every sentence this file can produce through
/// it.
///
/// ── LAW 1 (HARNESS-LAWS), SAID PLAINLY ───────────────────────────────────
///
/// Nothing here decides what a human's words MEAN, and nothing here ever reads
/// a human's words at all.
///
///   * WHICH APP a person meant — "my Outlook", "office mail", "my work email"
///     — is a meaning question and belongs to a model against the catalog
///     (`ToolkitJudge` in the contract). No list in this file is ever compared
///     against anything anybody typed.
///   * WHETHER TO INTERRUPT is a meaning-adjacent question with four states and
///     it belongs to `NudgePolicy` on the server. This file renders the record
///     that policy already decided; it never decides to ask.
///   * `forbiddenTerm(in:)` is a word list, and it is legal for one reason:
///     its input is text WE are about to show, drafted by us or by our own
///     model, and its only possible outcome is "do not show this". It is a
///     CEILING on our own output whose failure mode is silence — the same class
///     of thing as a house style sheet, and the identical argument
///     `connections/words.ts` makes for the list it shares with this one.
///   * The trigger-keyed why-lines are copy attached to a closed enum of things
///     that HAPPENED (a step routed to a browser, a Mac lid closing),
///     established upstream from events. A sentence keyed on an event type is
///     not a pattern deciding meaning.
///
/// ── POLARITY: EVERY GATE HERE IS A FLOOR ─────────────────────────────────
///
/// Showing an ask, claiming a revoke, and letting us change something inside
/// somebody's account are all privileges. A privilege needs a licence, not the
/// absence of an objection — so a malformed row, an unreadable status, a nudge
/// belonging to somebody else, a write opt-in stored as anything we do not
/// recognise, and a disconnect result that contradicts itself all land on the
/// quiet side. Nothing in this file acts on a missing answer.
///
/// Spec: "Connections: how Anticipy asks, learns, and never says Composio",
/// 2026-09-05, pages 20-31.
/// Run: `sh app/ios/Tests/run_connections_policy_tests.sh`

// MARK: - 1. THE OWNER ID, AND THE RULE THAT NOTHING IS READ WITHOUT ONE

/// The owner's row id as stored in D1's `owners` table. NOT an email, NOT a
/// display name.
///
/// The ids this system mints are 15 lowercase alphanumerics
/// (`sxkotd1h02qb6gw`). The initialiser is failable rather than throwing
/// because every caller here is a floor: no id, no read.
struct OwnerId: Hashable, CustomStringConvertible {

    /// The contract's own shape: `/^[a-z0-9]{15}$/`. Declared as a constant so
    /// the runner can compare it against `contract.ts` instead of trusting a
    /// number typed twice.
    static let length = 15

    let raw: String

    init?(_ candidate: String?) {
        guard let candidate else { return nil }
        // Trimmed before validation, exactly as `ownerId()` does next door: an
        // id arriving with a newline off a wire is the same id. Nothing else
        // about it is normalised — see `OwnerScoped.belongs` for why the
        // comparison afterwards is exact.
        let id = candidate.trimmingCharacters(in: .whitespacesAndNewlines)
        let scalars = Array(id.unicodeScalars)
        guard scalars.count == OwnerId.length else { return nil }
        for scalar in scalars where !OwnerId.isIdScalar(scalar) { return nil }
        self.raw = id
    }

    private static func isIdScalar(_ scalar: Unicode.Scalar) -> Bool {
        (scalar.value >= 97 && scalar.value <= 122) || (scalar.value >= 48 && scalar.value <= 57)
    }

    var description: String { raw }
}

/// Anything carrying an owner's id: a connection, a nudge, a toggle's row. The
/// protocol exists so the filter below is written ONCE and cannot be forgotten
/// on the third table somebody adds.
protocol OwnerStamped {
    var userID: String { get }
}

/// THE OWNER RULE, EXECUTABLE.
///
/// A function that takes a list of rows FILTERS IT rather than trusting the
/// caller. That sounds redundant next to a `WHERE user_id = ?`, and it is
/// exactly the redundancy that would have caught the spike's failure: a
/// `forOwner` that forgets its clause, a cache keyed one field too loosely, or
/// a poll response that arrives after a sign-out all produce a list that looks
/// correct at every line and contains somebody else's mailbox.
/// `RefreshAccountRacePolicy` in this same tree exists because that last one
/// happened on this phone already.
enum OwnerScoped {

    /// Does this row belong to the signed-in owner?
    ///
    /// EXACT string comparison against a VALIDATED id, deliberately. Not
    /// case-insensitive (an id is lowercase; `SXKOTD1H02QB6GW` is a different
    /// string and we do not get to decide it is the same person), not trimmed
    /// (a stored id with whitespace welded on is a malformed row, and the safe
    /// reading of a malformed row is "not yours"). Both directions of being
    /// wrong here are unequal: dropping a row of your own shows you an empty
    /// screen, keeping a row of somebody else's shows you their mail.
    static func belongs<Row: OwnerStamped>(_ row: Row, to owner: OwnerId) -> Bool {
        row.userID == owner.raw
    }

    /// The filter. Rows belonging to anybody else are DROPPED, including when
    /// the caller passed a mixed list — which is the whole point of the type.
    static func rows<Row: OwnerStamped>(_ rows: [Row], for owner: OwnerId) -> [Row] {
        rows.filter { belongs($0, to: owner) }
    }

    /// One row, or nothing. Used where a single record is read back — a nudge
    /// arriving in a push payload, a connection quoted in a job row — because
    /// the single-record path is the one where a filter is easiest to forget.
    static func one<Row: OwnerStamped>(_ row: Row?, for owner: OwnerId) -> Row? {
        guard let row, belongs(row, to: owner) else { return nil }
        return row
    }
}

// MARK: - 2. THE CONTRACT'S CLOSED SETS

/// Which of the owner's accounts this connection is. Closed at two values by
/// the contract; the normal case is two Google accounts.
enum AccountAlias: String, CaseIterable, Hashable {
    case work
    case personal
}

/// A connection's status. A fourth value is a connection we cannot honestly
/// describe, so a row carrying one is dropped from the screen rather than
/// guessed at.
enum ConnectionStatus: String, CaseIterable, Hashable {
    case connected
    case needsReconnect = "needs_reconnect"
    case disconnected
}

/// The nudge state machine, verbatim from the contract:
/// `never_asked -> asked -> declined -> connected -> needs_reconnect`.
enum NudgeState: String, CaseIterable, Hashable {
    case neverAsked = "never_asked"
    case asked
    case declined
    case connected
    case needsReconnect = "needs_reconnect"
}

/// Which real moment produced the ask. Never "out of nowhere": every member is
/// a thing that actually happened, established upstream from events.
enum NudgeTrigger: String, CaseIterable, Hashable {
    case inTask = "in_task"
    case repeatedUse = "repeated_use"
    case laptopClosed = "laptop_closed"
    case userNamedIt = "user_named_it"
    case onboarding
}

/// Where the ask went out. The card and the text thread are two skins on one
/// record, so which skin was used is a fact about the row, not a second row.
enum NudgeChannel: String, CaseIterable, Hashable {
    case sms
    case ios
}

/// Name, logo, description and scopes, from the catalog at RUN TIME. This is
/// the only place an app name may come from.
struct ToolkitMeta: Equatable {
    let slug: String
    let name: String
    let logo: String?
    let description: String?
    let appURL: String?
    let scopes: [String]

    init(slug: String, name: String, logo: String? = nil,
         description: String? = nil, appURL: String? = nil, scopes: [String] = []) {
        self.slug = slug
        self.name = name
        self.logo = logo
        self.description = description
        self.appURL = appURL
        self.scopes = scopes
    }

    /// A catalog row is usable when it can name the app on a screen. A page
    /// headed "Connect your " is, to the person reading it, indistinguishable
    /// from a broken one.
    var isUsable: Bool {
        !slug.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}

/// The `connections` table's row.
struct Connection: OwnerStamped, Equatable {
    let userID: String
    let toolkit: String
    let connectedAccountID: String
    let alias: AccountAlias?
    let status: ConnectionStatus
    /// THE WRITE OPT-IN, off by default. Reads never require it.
    let writesEnabled: Bool
    let lastUsedAt: Double?

    init(userID: String, toolkit: String, connectedAccountID: String,
         alias: AccountAlias?, status: ConnectionStatus,
         writesEnabled: Bool, lastUsedAt: Double?) {
        self.userID = userID
        self.toolkit = toolkit
        self.connectedAccountID = connectedAccountID
        self.alias = alias
        self.status = status
        self.writesEnabled = writesEnabled
        self.lastUsedAt = lastUsedAt
    }

    /// The row as it arrives off the wire. Returns nil rather than a
    /// half-populated value: a connection whose owner, app or status cannot be
    /// read is not a connection this phone may show or act on.
    init?(row: [String: Any]) {
        guard let userID = ConnectionsPolicy.text(row["user_id"]),
              OwnerId(userID) != nil,
              let toolkit = ConnectionsPolicy.text(row["toolkit"]),
              let account = ConnectionsPolicy.text(row["connected_account_id"]),
              let statusText = ConnectionsPolicy.text(row["status"]),
              let status = ConnectionStatus(rawValue: statusText)
        else { return nil }
        self.userID = userID
        self.toolkit = toolkit
        self.connectedAccountID = account
        self.alias = AccountAlias(rawValue: ConnectionsPolicy.text(row["alias"]) ?? "")
        self.status = status
        // The opt-in is read through the one predicate, so a column that is
        // absent, null, `0`, or the string "true" all come back OFF.
        self.writesEnabled = ConnectionsPolicy.writesOptedIn(row["writes_enabled"])
        self.lastUsedAt = ConnectionsPolicy.instant(row["last_used_at"])
    }
}

/// The `connect_nudges` table's row: ONE record, rendered by both the card and
/// the text thread, so acting in either flips the other.
struct ConnectNudge: OwnerStamped, Equatable {
    let userID: String
    let toolkit: String
    let state: NudgeState
    /// 0 while never declined; 1, 2, 3 as declines accumulate. Level 3 stops.
    let level: Int
    let snoozeUntil: Double?
    let trigger: NudgeTrigger?
    let sentAt: Double?
    let actedAt: Double?
    let channel: NudgeChannel?

    init(userID: String, toolkit: String, state: NudgeState, level: Int,
         snoozeUntil: Double? = nil, trigger: NudgeTrigger? = nil,
         sentAt: Double? = nil, actedAt: Double? = nil, channel: NudgeChannel? = nil) {
        self.userID = userID
        self.toolkit = toolkit
        self.state = state
        self.level = level
        self.snoozeUntil = snoozeUntil
        self.trigger = trigger
        self.sentAt = sentAt
        self.actedAt = actedAt
        self.channel = channel
    }

    init?(row: [String: Any]) {
        guard let userID = ConnectionsPolicy.text(row["user_id"]),
              OwnerId(userID) != nil,
              let toolkit = ConnectionsPolicy.text(row["toolkit"]),
              let stateText = ConnectionsPolicy.text(row["state"]),
              let state = NudgeState(rawValue: stateText)
        else { return nil }
        // A level outside 0...3 is a ladder we cannot read, and reading it as 0
        // re-asks somebody who has already said no three times.
        guard let level = ConnectionsPolicy.wholeNumber(row["level"]),
              (0...3).contains(level)
        else { return nil }
        self.userID = userID
        self.toolkit = toolkit
        self.state = state
        self.level = level
        self.snoozeUntil = ConnectionsPolicy.instant(row["snooze_until"])
        self.trigger = NudgeTrigger(rawValue: ConnectionsPolicy.text(row["trigger"]) ?? "")
        self.sentAt = ConnectionsPolicy.instant(row["sent_at"])
        self.actedAt = ConnectionsPolicy.instant(row["acted_at"])
        self.channel = NudgeChannel(rawValue: ConnectionsPolicy.text(row["channel"]) ?? "")
    }

    /// The ladder's terminal state. Only the owner reopening this counts, and
    /// that arrives as an owner request, never as a trigger.
    var isStopped: Bool { state == .declined && level >= ConnectionsPolicy.maxDeclineLevel }
}

/// What the provider's disconnect actually did, plus the app's own name so the
/// confirmation reads like a sentence about an app rather than about a slug.
///
/// `revoked` is the ONLY thing that licenses the word "revoked". Not `deleted`,
/// not the absence of `revokeUnavailable`, not "it usually works".
struct DisconnectResult: Equatable {
    /// From the catalog. Empty is tolerated and falls back — see `appName`.
    let appName: String
    /// How many of the owner's accounts on this app we tried. Zero means there
    /// was nothing connected.
    let attempted: Int
    let revoked: Bool
    let deleted: Bool
    /// True when the provider could not revoke programmatically at all. About
    /// 5% of connections cannot be.
    let revokeUnavailable: Bool

    init(appName: String, attempted: Int, revoked: Bool, deleted: Bool,
         revokeUnavailable: Bool) {
        self.appName = appName
        self.attempted = attempted
        self.revoked = revoked
        self.deleted = deleted
        self.revokeUnavailable = revokeUnavailable
    }
}

// MARK: - 3. WHAT A ROW IN SETTINGS SHOWS

/// One app's row on the "Connected apps" screen, built from CATALOG METADATA
/// plus the owner's own connection records.
///
/// ONE CARD PER APP even when the owner has two accounts on it, because the
/// write opt-in is per app: a screen showing two toggles for one app would be
/// promising a per-account control that neither this policy nor the server
/// implements.
struct ConnectionCard: Equatable {
    let toolkit: String
    /// From the catalog, falling back to the slug, falling back to a neutral
    /// phrase. A blank where a name belongs renders as "  disconnected" and
    /// reads to the person as a bug.
    let name: String
    /// Parsed and scheme-checked, so a catalog row cannot hand a screen a
    /// `file:` or `javascript:` "logo".
    let logoURL: URL?
    /// The named accounts, in the order the rows arrived, de-duplicated.
    let aliases: [AccountAlias]
    /// How many connections stand behind this one card, named or not.
    let accounts: Int
    let status: ConnectionStatus
    /// The floor: ON only when EVERY connected account on this app is opted in.
    let writesEnabled: Bool
    /// Raw instant. Wording a date is the view's job and PlainDuration's; a
    /// policy that wrote "2 days ago" would be a second opinion about time.
    let lastUsedAt: Double?

    /// "work", "work and personal", or empty when no account is named.
    var accountLabel: String {
        aliases.map(\.rawValue).joined(separator: " and ")
    }

    /// Everything this card puts in front of a person that WE wrote. The app's
    /// own name is excluded on purpose: it is quoted from the catalog and is
    /// not ours to censor (see `forbiddenTerm(in:)`).
    var houseLines: [String] {
        [accountLabel, ConnectionsPolicy.writesLine(writesEnabled),
         ConnectionsPolicy.statusLine(status)]
    }
}

// MARK: - 4. THE NUDGE, RENDERED

/// What the card offers. The same members the text thread's reply handler acts
/// on, so tapping and typing produce the same record.
enum NudgeAction: String, CaseIterable, Hashable {
    case connect
    case reconnect
    case notNow = "not_now"
}

/// Everything the card renders from: ONE nudge row, the catalog row that names
/// the app, and the owner who is signed into THIS phone.
///
/// Bundled into a single value so the call is `nudgeRender(state:)` — there is
/// exactly one input and it is a record. Two inputs is how a screen ends up
/// rendering one owner's nudge next to another owner's app name.
struct NudgeCardInput {
    let nudge: ConnectNudge
    let meta: ToolkitMeta?
    let owner: OwnerId

    init(nudge: ConnectNudge, meta: ToolkitMeta?, owner: OwnerId) {
        self.nudge = nudge
        self.meta = meta
        self.owner = owner
    }
}

/// The card. `visible == false` is a real answer with a reason attached, not an
/// empty struct: "she already connected it" and "this row belongs to somebody
/// else" are different facts and the log needs to tell them apart.
struct NudgeCard: Equatable {
    let visible: Bool
    let headline: String
    /// Why this ask exists, keyed on the moment that produced it. Empty when
    /// the card is hidden.
    let why: String
    /// THE SENTENCE THAT IS NEVER OPTIONAL. Connecting is always optional and
    /// every ask says so in one sentence, because the browser does the same
    /// work either way. A visible card without this line is a card that
    /// corners somebody, and somebody who feels cornered does not say so —
    /// they go quiet, and a quiet owner is a product that hears nothing.
    let optionalLine: String
    let primary: NudgeAction?
    let secondary: NudgeAction?
    /// For the log. Nothing branches on these words.
    let hiddenBecause: String

    static let hidden = NudgeCard(visible: false, headline: "", why: "",
                                  optionalLine: "", primary: nil, secondary: nil,
                                  hiddenBecause: "")

    static func hidden(_ because: String) -> NudgeCard {
        NudgeCard(visible: false, headline: "", why: "", optionalLine: "",
                  primary: nil, secondary: nil, hiddenBecause: because)
    }

    /// Every sentence the card shows. Used by the vocabulary gate and by the
    /// suite, so a fourth line added later cannot escape either.
    var lines: [String] { [headline, why, optionalLine].filter { !$0.isEmpty } }
}

// MARK: - 5. THE POLICY

enum ConnectionsPolicy {

    // ---------------------------------------------------------------------
    // 5.1 The contract's numbers. Config, not code — and the runner compares
    //     every one of them against contract.ts.
    // ---------------------------------------------------------------------

    /// Snooze after each decline, in days, indexed 1/2/3. Level 3 never
    /// re-asks; 3650 days is the contract's way of writing "stop" as a number
    /// the same arithmetic can carry.
    static let snoozeDays: [Int] = [14, 45, 3650]

    /// Somebody skipping a card during setup has refused a form, not the app.
    /// The first decline of an ONBOARDING ask snoozes 7 days, not 14 — once, at
    /// level 1: a second decline is a second decline whatever the first was.
    static let onboardingSkipSnoozeDays = 7

    /// The top of the ladder. Three noes is an answer.
    static let maxDeclineLevel = 3

    /// One ask per owner per 7 days, ACROSS ALL APPS.
    static let globalAskIntervalDays = 7

    /// 72 hours of silence is a decline, just a quieter one.
    static let silenceIsASoftNoHours = 72

    /// Our link's life. The vendor's own expires in ten minutes from the moment
    /// it is minted, which is why one is generated at tap time and never sent.
    static let linkTTLSeconds: Double = 10 * 60

    /// OUR link, never the vendor's. Single use, bound to one owner.
    static let connectLinkPrefix = "https://anticipy.ai/c/"

    private static let dayInSeconds: Double = 24 * 60 * 60

    // ---------------------------------------------------------------------
    // 5.2 THE WRITE OPT-IN
    // ---------------------------------------------------------------------

    /// OFF BY DEFAULT. This is the Settings toggle "let Anticipy make changes",
    /// and it is the write opt-in the Two Hands ladder needs for rung 3.
    static let writesEnabledDefault = false

    /// What a stored opt-in reads as.
    ///
    /// The column arrives from storage where booleans are integers, so `true`
    /// and `1` count and EVERYTHING ELSE DOES NOT — absent, null, `0`, `"1"`,
    /// `"true"`, a number nobody expected. The asymmetry points the safe way:
    /// an unreadable opt-in withholds a privilege rather than granting one.
    static func writesOptedIn(_ stored: Any?) -> Bool {
        if let flag = stored as? Bool { return flag }
        if let number = stored as? Int { return number == 1 }
        // NSNumber from JSONSerialization bridges to Bool and Int above; a
        // Double reaches here and is compared without a tolerance on purpose —
        // an opt-in stored as 0.999 is not an opt-in.
        if let number = stored as? Double { return number == 1 }
        return writesEnabledDefault
    }

    /// What we may do with this app right now.
    enum Access {
        case read
        case write
    }

    /// MAY WE? Owner-scoped, and the read path never consults the toggle.
    ///
    /// READS NEVER REQUIRE IT. Reading somebody's mail is what they connected
    /// the app for. If a read waited on the write toggle, the toggle would stop
    /// being a consent control and become an on/off switch for the product —
    /// every owner would turn it on to make anything work at all, which is the
    /// same as never having asked.
    ///
    /// WRITES REQUIRE EVERY connected account on the app, not any. The toggle
    /// is per app, so in the normal case the two readings are one sentence;
    /// they diverge only when the rows have skewed — a second account connected
    /// after the toggle was set — and there the floor is honest. Under "any",
    /// opting in for a personal account would license a write to a work one
    /// that was never offered the choice.
    static func mayUse(rows: [Connection], toolkit: String, access: Access,
                       for owner: OwnerId) -> Bool {
        let live = connectedRows(rows, toolkit: toolkit, for: owner)
        guard !live.isEmpty else { return false }
        if access == .read { return true }
        return live.allSatisfy { $0.writesEnabled }
    }

    /// The toggle's position as Settings renders it. The SAME predicate as
    /// `mayUse(..., .write, ...)`, so the screen cannot show ON while a write
    /// is refused.
    static func writesEnabled(rows: [Connection], toolkit: String,
                              for owner: OwnerId) -> Bool {
        mayUse(rows: rows, toolkit: toolkit, access: .write, for: owner)
    }

    /// What flipping the toggle produces.
    ///
    /// `rowsToWrite` carries ONLY the signed-in owner's connected rows on this
    /// app, already updated. The caller writes back exactly what it is handed
    /// and never the list it passed in — which is what makes it impossible for
    /// a mixed list to travel through a toggle and land on somebody else's
    /// connection.
    struct WritesTransition: Equatable {
        let toolkit: String
        /// The position AFTER the call.
        let enabled: Bool
        /// False when there was nothing to toggle because the app is not
        /// connected for this owner.
        let applied: Bool
        let accounts: Int
        let rowsToWrite: [Connection]
    }

    static func writesTransition(rows: [Connection], toolkit: String, to on: Bool,
                                 for owner: OwnerId) -> WritesTransition {
        let live = connectedRows(rows, toolkit: toolkit, for: owner)
        guard !live.isEmpty else {
            return WritesTransition(toolkit: toolkit, enabled: false, applied: false,
                                    accounts: 0, rowsToWrite: [])
        }
        // Every account on the app moves together. Leaving one behind is the
        // exact skew `mayUse` refuses, and a toggle reading ON while a write is
        // refused is worse than a toggle that never moved.
        let updated = live.map {
            Connection(userID: $0.userID, toolkit: $0.toolkit,
                       connectedAccountID: $0.connectedAccountID, alias: $0.alias,
                       status: $0.status, writesEnabled: on, lastUsedAt: $0.lastUsedAt)
        }
        return WritesTransition(toolkit: toolkit, enabled: on, applied: true,
                                accounts: updated.count, rowsToWrite: updated)
    }

    /// What a DELETED connection becomes.
    ///
    /// It leaves as `disconnected` rather than vanishing, and its opt-in is
    /// cleared, so the write permission it carried cannot be inherited by a
    /// fresh connection to the same app months later. Consent is to a
    /// connection, not to an app name.
    static func afterDisconnect(_ row: Connection) -> Connection {
        Connection(userID: row.userID, toolkit: row.toolkit,
                   connectedAccountID: row.connectedAccountID, alias: row.alias,
                   status: .disconnected, writesEnabled: writesEnabledDefault,
                   lastUsedAt: row.lastUsedAt)
    }

    // ---------------------------------------------------------------------
    // 5.3 THE SETTINGS CARDS
    // ---------------------------------------------------------------------

    /// The "Connected apps" screen, built from the owner's rows and the
    /// catalog. Owner-scoped at the door.
    static func settingsCards(rows: [Connection], catalog: [ToolkitMeta],
                              for owner: OwnerId) -> [ConnectionCard] {
        var metas: [String: ToolkitMeta] = [:]
        for meta in catalog where meta.isUsable { metas[meta.slug] = meta }

        var order: [String] = []
        var bySlug: [String: ConnectionCard] = [:]

        for row in OwnerScoped.rows(rows, for: owner) {
            let slug = row.toolkit.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !slug.isEmpty else { continue }
            // A row the owner already disconnected is history, and history on
            // this screen reads as "you are still connected".
            guard row.status != .disconnected else { continue }

            let meta = metas[slug]
            guard let seen = bySlug[slug] else {
                order.append(slug)
                bySlug[slug] = ConnectionCard(
                    toolkit: slug,
                    name: appName(meta, fallback: slug),
                    logoURL: logoURL(meta?.logo),
                    aliases: row.alias.map { [$0] } ?? [],
                    accounts: 1,
                    status: row.status,
                    writesEnabled: row.writesEnabled,
                    lastUsedAt: row.lastUsedAt)
                continue
            }

            var aliases = seen.aliases
            // De-duplicated, unlike the server's `accountNote` today: two work
            // accounts on one app would otherwise render "work and work", which
            // is a screen describing a control the owner does not have. Noted
            // as a divergence to close on the server side.
            if let alias = row.alias, !aliases.contains(alias) { aliases.append(alias) }

            bySlug[slug] = ConnectionCard(
                toolkit: slug,
                name: seen.name,
                logoURL: seen.logoURL,
                aliases: aliases,
                accounts: seen.accounts + 1,
                // A broken account makes the whole app broken on this screen.
                status: row.status == .needsReconnect ? .needsReconnect : seen.status,
                // Same floor as `mayUse`: one account without the opt-in turns
                // the app's toggle off, so the screen never claims a licence a
                // write would refuse.
                writesEnabled: seen.writesEnabled && row.writesEnabled,
                lastUsedAt: laterOf(seen.lastUsedAt, row.lastUsedAt))
        }

        // Sorted by the rendered NAME so this screen and its text twin list the
        // same apps in the same order; the slug breaks ties so the order is
        // stable across reloads rather than dependent on how D1 felt.
        return order.compactMap { bySlug[$0] }.sorted {
            $0.name == $1.name ? $0.toolkit < $1.toolkit : $0.name < $1.name
        }
    }

    /// The later of two instants, where "nothing recorded" loses to any real
    /// one. Two accounts on one app share a card, and the card reports the last
    /// time the APP was used — the older account going quiet is not the app
    /// going quiet.
    static func laterOf(_ a: Double?, _ b: Double?) -> Double? {
        switch (a, b) {
        case let (x?, y?): return Swift.max(x, y)
        case let (x?, nil): return x
        case let (nil, y?): return y
        case (nil, nil): return nil
        }
    }

    /// The name, from the catalog, falling back to the slug and then to a
    /// neutral phrase. NOT a table: `meta` arrived from the catalog at run
    /// time, and the fallback is the row's own slug.
    static func appName(_ meta: ToolkitMeta?, fallback: String) -> String {
        let given = meta?.name.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !given.isEmpty { return given }
        let slug = fallback.trimmingCharacters(in: .whitespacesAndNewlines)
        return slug.isEmpty ? "that app" : slug
    }

    /// A logo is a URL we are about to hand a network image view. Only `https`
    /// survives: a catalog row is data from a vendor's API, and `file:` or
    /// `javascript:` reaching a web view through a "logo" field is a hole
    /// nobody would look for on a settings screen.
    static func logoURL(_ raw: String?) -> URL? {
        guard let raw else { return nil }
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, let url = URL(string: trimmed),
              url.scheme?.lowercased() == "https", url.host?.isEmpty == false
        else { return nil }
        return url
    }

    // ---------------------------------------------------------------------
    // 5.4 THE DISCONNECT CONFIRMATION — the sentence this file exists to get
    //     right.
    // ---------------------------------------------------------------------

    /// What we tell somebody after a disconnect.
    ///
    /// `revoked == true` is the ONLY licence for the word "revoked", and a
    /// result that also reports `revokeUnavailable` does not get it however
    /// `revoked` was set: those two cannot both be true of one account, and
    /// where a row contradicts itself the honest reading is the quiet one.
    ///
    /// Deleting our record while the token stays live at the provider is
    /// precisely the state a person would describe as "I disconnected it", so
    /// the honest copy has to tell them the second half themselves. Telling
    /// somebody their access was revoked when it was not is a lie they cannot
    /// detect until it matters, and this repo treats it as a defect.
    static func disconnectConfirmation(result: DisconnectResult) -> String {
        let app = appName(nil, fallback: result.appName)
        guard result.attempted > 0 else {
            return "\(app) isn't connected, so there's nothing to disconnect."
        }
        let revoked = result.revoked && !result.revokeUnavailable
        let deleted = result.deleted

        if revoked && deleted {
            return "Done. \(app) disconnected and access revoked."
        }
        if revoked {
            // Access is genuinely gone; our own record is not. "Done" here
            // would be true about the half they care about and false about the
            // half that makes the app leave this screen, so it says both.
            return "\(app) access is revoked — nothing can use it from here. "
                + "Its entry is still on file on my side and I'm clearing it."
        }
        if deleted {
            // THE 5% BRANCH. We removed it here and we could not remove it
            // there, and the person is the only one who can finish the job.
            return "Done. \(app) is disconnected here. \(app) may still list Anticipy in its "
                + "own settings, so clear it there if you want it gone at both ends."
        }
        return "I couldn't disconnect \(app) just now, so nothing has changed. "
            + "Want me to try again?"
    }

    /// Several accounts on one app, folded into one answer.
    ///
    /// `revoked` is EVERY and `revokeUnavailable` is ANY. Somebody with a work
    /// and a personal account who is told "access revoked" when only one came
    /// back has been told something false about the account that still works —
    /// and it is the more dangerous half of the sentence that would be wrong.
    static func combine(_ results: [DisconnectResult], appName: String) -> DisconnectResult {
        guard !results.isEmpty else {
            return DisconnectResult(appName: appName, attempted: 0, revoked: false,
                                    deleted: false, revokeUnavailable: false)
        }
        return DisconnectResult(
            appName: appName,
            attempted: results.reduce(0) { $0 + $1.attempted },
            revoked: results.allSatisfy(\.revoked),
            deleted: results.allSatisfy(\.deleted),
            revokeUnavailable: results.contains(where: \.revokeUnavailable))
    }

    // ---------------------------------------------------------------------
    // 5.5 THE NUDGE, RENDERED — one record, two skins
    // ---------------------------------------------------------------------

    /// ONE nudge record to what the CARD shows.
    ///
    /// The text thread and this card are two skins on the same row, so acting
    /// in either flips the other: the card's actions are the same members the
    /// text handler produces, and `recordDecline`/`recordTapped` below are the
    /// one arithmetic both use. Two implementations of "how long is the snooze"
    /// is how an owner gets re-asked on day 14 by one path while the other
    /// believes it is day 45.
    ///
    /// What is shared is the RECORD and the TRANSITION, not the prose: the SMS
    /// is written by a model against `words.ts`, and this card is house copy.
    /// They must never disagree about state, and they are not required to use
    /// the same adjectives.
    ///
    /// Every branch that hides says why. Hidden is a real answer.
    static func nudgeRender(state: NudgeCardInput) -> NudgeCard {
        let nudge = state.nudge

        // THE OWNER, FIRST AND BEFORE ANYTHING ELSE. A nudge for another owner
        // is not "a card with the wrong name on it" — it is this phone showing
        // its user what somebody else has been asked about, which is the whole
        // class of failure this file is shaped around.
        guard OwnerScoped.belongs(nudge, to: state.owner) else {
            return .hidden("this nudge belongs to another owner")
        }

        let app = appName(state.meta, fallback: nudge.toolkit)

        switch nudge.state {
        case .neverAsked:
            // Nothing has been asked, so there is nothing to answer. A card
            // raised here would be the app asking out of nowhere, which is the
            // one thing every ask in this product is forbidden to be. Connecting
            // an app ON PURPOSE lives on the catalog screen, not on this card.
            return .hidden("nothing has been asked about this app yet")

        case .connected:
            // No ask to show. The app appears in the Connected apps list, which
            // is `settingsCards`' job; duplicating it here would give one app
            // two rows that can disagree.
            return .hidden("this app is already connected")

        case .declined:
            if nudge.isStopped {
                return .hidden("this owner has said no three times; only they reopen it")
            }
            return .hidden("this owner said no and the snooze is running")

        case .asked:
            // An ask with no moment behind it is an ask out of nowhere, and a
            // row that says `asked` with no `sent_at` cannot tell "asked ten
            // minutes ago" from "asked in March". Both are unreadable rows, and
            // an unreadable row does not get to interrupt anybody.
            guard let trigger = nudge.trigger else {
                return .hidden("this ask names no moment; an ask is never out of nowhere")
            }
            guard nudge.sentAt != nil else {
                return .hidden("this ask has no sent time, so its age is unknown")
            }
            return NudgeCard(
                visible: true,
                headline: "Connect your \(app)?",
                why: whyLine(trigger, app: app),
                optionalLine: optionalLine(app: app),
                primary: .connect,
                secondary: .notNow,
                hiddenBecause: "")

        case .needsReconnect:
            // The ladder deliberately does not apply here: it governs "will you
            // connect an app you have not connected", and a reconnect is the
            // repair of a thing this owner already chose. It is still optional,
            // because the browser still does the same work.
            return NudgeCard(
                visible: true,
                headline: "\(app) has stopped working.",
                why: "The connection lapsed, so I've been doing \(app) in your browser instead.",
                optionalLine: optionalLine(app: app),
                primary: .reconnect,
                secondary: .notNow,
                hiddenBecause: "")
        }
    }

    /// THE SENTENCE EVERY ASK CARRIES. One sentence, saying it is optional,
    /// and saying WHY it is optional — the browser does the same work either
    /// way, which is the fact that makes the sentence true rather than polite.
    static func optionalLine(app: String) -> String {
        "Entirely up to you — I can do \(app) in your browser either way."
    }

    /// Why this ask exists, keyed on the MOMENT that produced it.
    ///
    /// A closed enum of things that happened, established upstream from events,
    /// mapped to a sentence. Nothing here reads anything anybody said: swap
    /// every case for a number and the behaviour is identical, which is the
    /// test of whether a list is doing meaning's job.
    static func whyLine(_ trigger: NudgeTrigger, app: String) -> String {
        switch trigger {
        case .inTask:
            return "The thing you just asked for would have gone quicker through \(app)."
        case .repeatedUse:
            return "You've had me do this in your browser a few times lately."
        case .laptopClosed:
            return "Your Mac is shut, so this one is waiting for it."
        case .userNamedIt:
            return "You mentioned \(app) just now."
        case .onboarding:
            return "Worth having from the start, if you use \(app)."
        }
    }

    /// What the status says on a card.
    static func statusLine(_ status: ConnectionStatus) -> String {
        switch status {
        case .connected: return "Connected"
        case .needsReconnect: return "Needs connecting again"
        case .disconnected: return "Not connected"
        }
    }

    /// What the write opt-in says on a card. Read-only is stated positively:
    /// "reading only" is what the person chose, not a limitation to apologise
    /// for.
    static func writesLine(_ enabled: Bool) -> String {
        enabled ? "I can make changes" : "Reading only"
    }

    // ---------------------------------------------------------------------
    // 5.6 ACT IN EITHER, THE OTHER FLIPS
    // ---------------------------------------------------------------------

    /// The record after a decline — a "Not now" tapped on the card or typed
    /// into the thread, or 72 hours of silence.
    ///
    /// `how` is not decoration. "They tapped Not now" and "they never answered"
    /// are different facts about a person, they are the difference between
    /// `actedAt` set and `actedAt` nil, and the log is what the spec's timers
    /// get tuned from. A silent decline that stamps `actedAt` claims an action
    /// nobody took.
    ///
    /// Owner-scoped: a record that is not this owner's does not transition at
    /// all, it returns nil.
    enum DeclineKind {
        case saidNo
        case silence
    }

    static func recordDecline(_ nudge: ConnectNudge, at now: Double, how: DeclineKind,
                              for owner: OwnerId) -> ConnectNudge? {
        guard OwnerScoped.belongs(nudge, to: owner) else { return nil }
        // THE SETUP CARD'S SKIP IS NOT A DECLINE, and this branch is the whole
        // of that. It used to fix the NUMBER and leave the sentence: seven days
        // instead of fourteen, but state `.declined` and the ladder advanced to
        // level 1 — so walking past a card during setup was written down as a
        // refusal of the app, and the server's own thresholds turn a level-1
        // decline into permanent silence for the two triggers that carry
        // evidence. A shrug ended the conversation for good.
        //
        // `ConnectOnboardingPolicy.skipOutcome` has always said what a skip
        // means, and its three rules are mirrored exactly here: never advance
        // and never reset the ladder, never shorten a snooze somebody already
        // earned, and leave a connected row alone. Two files, one meaning —
        // `agreesWithSkip` is the leg that holds them together.
        if nudge.trigger == .onboarding,
           nudge.state == .neverAsked || nudge.state == .asked {
            let until = now + Double(onboardingSkipSnoozeDays) * dayInSeconds
            return ConnectNudge(
                userID: nudge.userID, toolkit: nudge.toolkit, state: .neverAsked,
                level: nudge.level,
                snoozeUntil: max(nudge.snoozeUntil ?? -Double.greatestFiniteMagnitude, until),
                trigger: nudge.trigger,
                sentAt: nudge.sentAt,
                actedAt: now,
                channel: nudge.channel)
        }
        let level = min(nudge.level + 1, maxDeclineLevel)
        guard level >= 1, level <= snoozeDays.count else { return nil }
        return ConnectNudge(
            userID: nudge.userID, toolkit: nudge.toolkit, state: .declined,
            level: level,
            snoozeUntil: now + Double(snoozeDays[level - 1]) * dayInSeconds,
            trigger: nudge.trigger,
            sentAt: nudge.sentAt,
            actedAt: how == .saidNo ? now : nil,
            channel: nudge.channel)
    }

    /// The record after the owner tapped through to connect.
    ///
    /// The state does NOT become `connected` here, and that is the point: the
    /// connection lands when the provider says it landed. Stamping `connected`
    /// on a tap would put an app on the Settings screen that nothing can
    /// actually use, and the person would find out at the moment they relied on
    /// it. What the tap records is that they acted, and on which skin.
    static func recordTapped(_ nudge: ConnectNudge, at now: Double, on channel: NudgeChannel,
                             for owner: OwnerId) -> ConnectNudge? {
        guard OwnerScoped.belongs(nudge, to: owner) else { return nil }
        return ConnectNudge(
            userID: nudge.userID, toolkit: nudge.toolkit, state: nudge.state,
            level: nudge.level, snoozeUntil: nudge.snoozeUntil, trigger: nudge.trigger,
            sentAt: nudge.sentAt, actedAt: now, channel: channel)
    }

    /// The record the OTHER skin should now be rendering, given an action taken
    /// on this one. One switch, so the card and the thread cannot answer the
    /// same tap differently.
    static func nudgeAfter(action: NudgeAction, on nudge: ConnectNudge, at now: Double,
                           on channel: NudgeChannel, for owner: OwnerId) -> ConnectNudge? {
        switch action {
        case .connect, .reconnect:
            return recordTapped(nudge, at: now, on: channel, for: owner)
        case .notNow:
            return recordDecline(nudge, at: now, how: .saidNo, for: owner)
        }
    }

    // ---------------------------------------------------------------------
    // 5.7 THE FORBIDDEN-VOCABULARY GATE
    // ---------------------------------------------------------------------

    /// The register the spec fixes for every word Anticipy says about
    /// connecting. Shared, term for term, with `connections/words.ts`; the
    /// runner compares the two lists and goes red if they drift, because the
    /// app's copy is bound by the same rules as the SMS copy and two lists is
    /// two rules.
    ///
    /// These are not concepts we may not express — they are the vocabulary of a
    /// consent screen written by a legal team, and the point of this surface is
    /// that it sounds like a person offering to help. "Connect your Notion",
    /// never "authorize the Notion integration".
    ///
    /// Inflections are listed rather than stemmed, because a stemmer is a guess
    /// and this list has to be readable by whoever argues with it.
    static let forbiddenTerms: [String] = [
        "authorize",
        "authorise",
        "authorization",
        "authorisation",
        "grant access",
        "grants access",
        "granting access",
        "granted access",
        "permission",
        "permissions",
        "integration",
        "integrations",
        "api",
        "apis",
        "oauth",
        // The vendor's name is the one entry here that is not a register
        // problem but a promise: the product never says it, so copy that does
        // is not shown. Bare `connect.<vendor>.dev/...` links with no scheme
        // are caught by this entry too, which is why it earns its place twice.
        "composio",
    ]

    /// The first forbidden term in a piece of OUR copy, or nil.
    ///
    /// WHAT THIS IS FOR, AND WHAT IT IS NOT FOR. The input is text we are about
    /// to put in front of a person, written by us or by our own model. It never
    /// reads a human's words and its only possible outcome is "do not show
    /// this". An app's own NAME, quoted from the catalog, is not ours to censor
    /// — a vendor that calls itself something on this list gets called that,
    /// and the check belongs on the sentences around the name.
    ///
    /// Whole-word, case-insensitive, with the boundary defined as "not a
    /// lowercase letter and not a digit" — the same boundary `words.ts` uses.
    /// So "API-key" trips `api` (a hyphen is a boundary) and "capital" and
    /// "therapist" do not (a letter is not).
    static func forbiddenTerm(in text: String) -> String? {
        let hay = forScan(text)
        for term in forbiddenTerms where containsWholeTerm(hay, forScan(term)) {
            return term
        }
        return nil
    }

    /// The gate, as a caller states it.
    static func saysNothingForbidden(_ text: String) -> Bool {
        forbiddenTerm(in: text) == nil
    }

    /// Every line of a set of them, so a caller cannot check one string and
    /// believe it checked a screen.
    static func firstForbidden(in lines: [String]) -> (line: String, term: String)? {
        for line in lines {
            if let term = forbiddenTerm(in: line) { return (line, term) }
        }
        return nil
    }

    // ---------------------------------------------------------------------
    // 5.8 PLUMBING. Nothing below decides anything a person can feel.
    // ---------------------------------------------------------------------

    /// The owner's connected rows on one app. Owner filter first, always.
    static func connectedRows(_ rows: [Connection], toolkit: String,
                              for owner: OwnerId) -> [Connection] {
        OwnerScoped.rows(rows, for: owner)
            .filter { $0.toolkit == toolkit && $0.status == .connected }
    }

    /// A non-empty string off a JSON row, or nil. `NSNull` and numbers are not
    /// text, and a blank string is not an answer.
    static func text(_ value: Any?) -> String? {
        guard let string = value as? String else { return nil }
        let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    /// A whole number off a JSON row.
    static func wholeNumber(_ value: Any?) -> Int? {
        if let int = value as? Int { return int }
        if let double = value as? Double, double.rounded() == double, double.isFinite {
            return Int(double)
        }
        return nil
    }

    /// A timestamp off a JSON row. `nil` covers both "looked, nothing there"
    /// and "did not look"; the callers that need to tell those apart do it on
    /// the row's own shape, not here.
    static func instant(_ value: Any?) -> Double? {
        if let double = value as? Double { return double.isFinite ? double : nil }
        if let int = value as? Int { return Double(int) }
        return nil
    }

    /// Lowercased, curly apostrophes folded, whitespace collapsed. Display
    /// plumbing on a string we are about to scan; it changes no verdict.
    private static func forScan(_ text: String) -> String {
        let folded = text
            .replacingOccurrences(of: "\u{2018}", with: "'")
            .replacingOccurrences(of: "\u{2019}", with: "'")
            .replacingOccurrences(of: "\u{02BC}", with: "'")
            .lowercased()
        return folded.split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
    }

    /// Whole-word / whole-phrase containment, written as a scan rather than a
    /// regular expression. There is no pattern here to get subtly wrong and
    /// nothing for a future reader to mistake for text understanding.
    private static func containsWholeTerm(_ hay: String, _ term: String) -> Bool {
        let haystack = Array(hay)
        let needle = Array(term)
        guard !needle.isEmpty, haystack.count >= needle.count else { return false }
        var start = 0
        while start + needle.count <= haystack.count {
            if Array(haystack[start..<(start + needle.count)]) == needle {
                let beforeOK = start == 0 || !isWordCharacter(haystack[start - 1])
                let after = start + needle.count
                let afterOK = after == haystack.count || !isWordCharacter(haystack[after])
                if beforeOK && afterOK { return true }
            }
            start += 1
        }
        return false
    }

    /// The boundary, defined exactly as the server's `(?<![a-z0-9])` is.
    private static func isWordCharacter(_ character: Character) -> Bool {
        let scalars = Array(character.unicodeScalars)
        guard scalars.count == 1, let scalar = scalars.first else { return false }
        return (scalar.value >= 97 && scalar.value <= 122)
            || (scalar.value >= 48 && scalar.value <= 57)
    }
}
