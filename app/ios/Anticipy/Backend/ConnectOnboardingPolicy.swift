import Foundation

/// ONBOARDING STEP 2 — "Which apps do you live in?" — and the lockstep that
/// keeps the card and the text ONE ask instead of two.
///
/// Spec: "Connections: how Anticipy asks, learns, and never says Composio",
/// 2026-09-05, page 25 (the step) and pages 22-26 (signals, the state machine,
/// the right-time score). The server-side contract this file agrees with is
/// `spike/two-hands/src/connections/contract.ts`; the tables, the states, the
/// triggers and every constant below are ITS values, and
/// `Tests/run_connect_onboarding_tests.sh` reads them back out of the
/// TypeScript and fails if this file has drifted from them. Nothing here is
/// re-decided; it is mirrored under a gate.
///
/// ── THE FAILURE THIS FILE IS SHAPED AROUND ───────────────────────────────
///
/// During the spike one operator's own mailbox was connected by hand and would
/// have served everybody; it was revoked and deleted
/// (`research/2026-09-05-composio-connections.md`, item 2). So EVERY entry
/// point here takes the signed-in owner's ROW id and refuses — loudly, in a
/// four-state result, never by silently filtering — any signal row, nudge
/// record or link that belongs to somebody else. Refusing costs an empty card.
/// Filtering would cost somebody else's mailbox.
///
/// ── NO APP IS HARDCODED ──────────────────────────────────────────────────
///
/// Not a name, not a slug, not a host, not in a comment — a name in a comment
/// is where the next agent's branch on that name starts (the same rule
/// `src/connections/signals.ts` keeps). Every app this file can reach arrives
/// at run time as a `CatalogEntry`, and the only strings it compares are two
/// hosts the CATALOG supplied. The runner greps this source for a domain
/// literal or a vendor name and is red if it finds one, so "a new app in the
/// catalog is a new app in Anticipy with zero code" is measured rather than
/// promised.
///
/// ── HARNESS-LAWS LAW 1 ───────────────────────────────────────────────────
///
/// Nothing below decides what a human's words MEAN.
///   * `SignalSource`, `NudgeState`, `Trigger` and `Channel` are closed enums
///     the contract declares. Weights attached to them are config keyed on an
///     event type — a rank over things that happened, which law 1 permits and
///     `src/connections/policy.ts` already relies on.
///   * Host comparison is dot-separated label equality over two strings
///     somebody else supplied. It is the same class of check as parsing a port
///     out of a URL, and it cannot express "this app in particular".
///   * Clock arithmetic and decay are senses/plumbing.
///   * WHICH app a person MEANT — "my work email", "office mail" — is the
///     contract's `ToolkitJudge`, a model, on the server. It is not in this
///     file and must never be. The search box hands the typed words over the
///     `OnboardingCatalogSearch` seam UNREAD and shows what comes back in the
///     order it came back; `searchState` is a reducer that never sees the
///     catalog, so it cannot match against it. This was a real violation until
///     2026-09-05 — a `name.lowercased().contains(needle)` deciding which app
///     somebody meant, under four comments citing the judge it never called —
///     and the note on `searchState` records what it cost and how it was
///     replaced. The runner greps this source so it cannot come back.
///   * The connect link is checked against `ConnectHandoff`'s allowlist before
///     it is shown to anyone. Scheme, host and path: transport, not meaning.
enum ConnectOnboardingPolicy {

    // =====================================================================
    // MARK: - The contract, mirrored under a gate
    // =====================================================================

    /// Values copied from `spike/two-hands/src/connections/contract.ts` and
    /// `signals.ts`. Two implementations of "how long is the snooze" is how an
    /// owner gets re-asked on day 7 by one half of the product while the other
    /// believes it is day 14 — so the runner extracts each of these from the
    /// TypeScript and compares. A drift here is a red suite, not a surprise in
    /// somebody's messages.
    enum Contract {
        /// `ownerId()` in contract.ts, verbatim. Fifteen lowercase
        /// alphanumerics — an email or a display name is not an owner.
        static let ownerIdPattern = "^[a-z0-9]{15}$"

        static let onboardingSkipSnoozeDays = 7
        static let globalAskIntervalDays = 7
        static let silenceIsASoftNoHours = 72
        static let linkTTLMilliseconds: Double = 10 * 60 * 1000

        static let hourMilliseconds: Double = 60 * 60 * 1000
        static let dayMilliseconds: Double = 24 * 60 * 60 * 1000

        /// `SOURCE_WEIGHT` (signals.ts). Ordering, not probabilities.
        static let sourceWeight: [SignalSource: Double] = [
            .connected: 1,
            .asked: 1,
            .said: 0.7,
            .observer: 0.7,
            .mx: 0.4,
            .link: 0.4,
        ]

        /// `SOURCE_DECAYS` (signals.ts). The two certainties are facts about
        /// our own records and are as true a year later; letting them decay
        /// would re-open a settled question and ask somebody to connect a thing
        /// they already connected.
        static let sourceDecays: [SignalSource: Bool] = [
            .connected: false,
            .asked: false,
            .said: true,
            .observer: true,
            .mx: true,
            .link: true,
        ]

        /// `DEFAULT_HALF_LIFE_MS` (signals.ts). Thirty days.
        static let defaultHalfLifeMilliseconds: Double = 30 * 24 * 60 * 60 * 1000
    }

    /// How many apps may arrive PRE-SELECTED.
    ///
    /// Config, not law — tune it from what converts. It exists because
    /// "pre-selected" means "I am about to connect these", and a screen of
    /// pre-ticked boxes past the fold is consent nobody gave. Everything past
    /// the cap is still on the card, still one tap away, just not ticked.
    static let maxPreselected = 6

    /// Two weights are the same weight when they differ by less than this,
    /// relatively. Float addition of the same numbers in a different order
    /// lands a few ulps apart and that must not reorder the card.
    /// `TIE_EPSILON` in signals.ts. It decides ORDER, never meaning.
    static let tieEpsilon = 1e-12

    // =====================================================================
    // MARK: - Identity
    // =====================================================================

    /// The owner's row id, as stored in the `owners` table. NOT an email, NOT a
    /// display name. A distinct type, for the same reason contract.ts makes
    /// `OwnerId` a branded string: so a display name cannot be passed where an
    /// id belongs and one person's tokens end up serving everybody.
    struct OwnerID: Hashable, CustomStringConvertible {
        let raw: String

        init?(_ raw: String) {
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            // An id-shape check over a fixed alphabet: structure, not meaning.
            guard trimmed.range(of: Contract.ownerIdPattern,
                                options: .regularExpression) != nil else { return nil }
            self.raw = trimmed
        }

        var description: String { raw }
    }

    // =====================================================================
    // MARK: - The contract's closed enums
    // =====================================================================

    /// `AppUsageSignal["source"]`. Raw values are spelled out on every case so
    /// the runner can compare this list against the TypeScript union member by
    /// member; a spelling the server never writes must read as nothing, never
    /// as the nearest one.
    enum SignalSource: String, CaseIterable {
        case said = "said"
        case observer = "observer"
        case mx = "mx"
        case link = "link"
        case connected = "connected"
        case asked = "asked"
    }

    /// `AccountAlias`. Which of the owner's accounts a row is about. `nil` is
    /// the honest and commonest value and is never turned into a guess.
    enum AccountAlias: String, CaseIterable {
        case work = "work"
        case personal = "personal"
    }

    /// `NudgeState`.
    enum NudgeState: String, CaseIterable {
        case neverAsked = "never_asked"
        case asked = "asked"
        /// The setup card's Skip, level 0, seven days — NOT a rung on the
        /// ladder. `ConnectionsPolicy.NudgeState.declinedSoft` carries the long
        /// version of why; this enum is the same closed set read by the other
        /// half of the same feature, and the runner compares BOTH against
        /// contract.ts member for member.
        case declinedSoft = "declined_soft"
        case declined = "declined"
        case connected = "connected"
        case needsReconnect = "needs_reconnect"
    }

    /// `NudgeTrigger` — real moments, established by the caller from events.
    enum Trigger: String, CaseIterable {
        case inTask = "in_task"
        case repeatedUse = "repeated_use"
        case laptopClosed = "laptop_closed"
        case userNamedIt = "user_named_it"
        case onboarding = "onboarding"
    }

    /// `ConnectNudge.channel`. The two renderings of one ask.
    enum Channel: String, CaseIterable {
        case sms = "sms"
        case ios = "ios"
    }

    // =====================================================================
    // MARK: - Rows
    // =====================================================================

    /// `ToolkitMeta`, plus the one column the catalog owes us and the contract
    /// does not yet declare.
    struct CatalogEntry: Equatable {
        let slug: String
        /// The app's own name, as the catalog gives it. The ONLY place a name
        /// comes from.
        let name: String
        let logo: String?
        let blurb: String?
        /// The product's own site, as the catalog gives it.
        let appURL: String?
        let scopes: [String]
        /// Hosts this vendor's MAIL EXCHANGERS sit under, as the catalog gives
        /// them.
        ///
        /// A CONTRACT GAP, reported rather than papered over: `ToolkitMeta` has
        /// no such field, so the seed below falls back to comparing the
        /// exchanger against `appURL` and comes up empty for any vendor whose
        /// catalog entry points at a product subdomain. The alternative — a
        /// shared-suffix rule — needs a public-suffix list, and a public-suffix
        /// list is a table of domain literals, which is exactly the hardcoding
        /// the spec forbids and which `signals.ts` refused for the same reason.
        /// So: the catalog says, or nothing is seeded.
        let mailHosts: [String]

        init(slug: String, name: String, logo: String? = nil, blurb: String? = nil,
             appURL: String? = nil, scopes: [String] = [], mailHosts: [String] = []) {
            self.slug = slug
            self.name = name
            self.logo = logo
            self.blurb = blurb
            self.appURL = appURL
            self.scopes = scopes
            self.mailHosts = mailHosts
        }
    }

    /// An `app_usage_signals` row, plus `alias` — the same extra column
    /// `signals.ts` carries and reports as a contract gap, for the same reason:
    /// the table as declared cannot say WHICH of two accounts a row was about.
    struct SignalRow: Equatable {
        let owner: OwnerID
        let toolkit: String
        let source: SignalSource
        /// `nil` means "use the source's band". A caller passing one is
        /// overriding the band on purpose.
        let weight: Double?
        let lastSeenAt: Double
        let alias: AccountAlias?

        init(owner: OwnerID, toolkit: String, source: SignalSource,
             weight: Double? = nil, lastSeenAt: Double, alias: AccountAlias? = nil) {
            self.owner = owner
            self.toolkit = toolkit
            self.source = source
            self.weight = weight
            self.lastSeenAt = lastSeenAt
            self.alias = alias
        }
    }

    /// The identity of a ranked line and of a row on the card. Keyed by
    /// (toolkit, alias) exactly as `rankRows` keys it, so the same app held
    /// twice — work and personal — ranks twice and can be asked about
    /// separately.
    struct AppKey: Hashable {
        let toolkit: String
        let alias: AccountAlias?
    }

    /// One line of the ranked table.
    struct RankedLine: Equatable {
        let key: AppKey
        /// Summed decayed weight at the `now` that was passed in.
        let weight: Double
        let lastSeenAt: Double
        /// Which sources fed this line, sorted.
        let sources: [SignalSource]
    }

    /// A `connect_nudges` row.
    struct NudgeRecord: Equatable {
        let owner: OwnerID
        let toolkit: String
        var alias: AccountAlias?
        var state: NudgeState
        /// 0 while never declined; 1, 2, 3 as declines accumulate.
        var level: Int
        var snoozeUntil: Double?
        var trigger: Trigger?
        var sentAt: Double?
        var actedAt: Double?
        var channel: Channel?

        init(owner: OwnerID, toolkit: String, alias: AccountAlias? = nil,
             state: NudgeState = .neverAsked, level: Int = 0,
             snoozeUntil: Double? = nil, trigger: Trigger? = nil,
             sentAt: Double? = nil, actedAt: Double? = nil, channel: Channel? = nil) {
            self.owner = owner
            self.toolkit = toolkit
            self.alias = alias
            self.state = state
            self.level = level
            self.snoozeUntil = snoozeUntil
            self.trigger = trigger
            self.sentAt = sentAt
            self.actedAt = actedAt
            self.channel = channel
        }

        var key: AppKey { AppKey(toolkit: toolkit, alias: alias) }
    }

    /// A `connect_links` row as the phone sees it: the raw token it was handed,
    /// bound to one owner and one toolkit, dead at `expiresAt`.
    struct LinkRow: Equatable {
        let token: String
        let owner: OwnerID
        let toolkit: String
        let alias: AccountAlias?
        let expiresAt: Double
        var usedAt: Double?

        init(token: String, owner: OwnerID, toolkit: String, alias: AccountAlias? = nil,
             expiresAt: Double, usedAt: Double? = nil) {
            self.token = token
            self.owner = owner
            self.toolkit = toolkit
            self.alias = alias
            self.expiresAt = expiresAt
            self.usedAt = usedAt
        }

        func isLive(at now: Double) -> Bool { usedAt == nil && now < expiresAt }
    }

    // =====================================================================
    // MARK: - Refusals
    // =====================================================================

    /// Enumerated causes, never free text: a card that refuses in prose cannot
    /// be counted, and a cause nobody can count is a cause nobody can fix.
    /// `CaseIterable` so the suite's census cannot go stale.
    enum Refusal: String, CaseIterable {
        /// No signed-in owner. Nothing about connections may be read or written
        /// without one — the whole feature is per-owner.
        case notSignedIn = "not_signed_in"
        /// A row belongs to somebody other than the person holding this phone.
        /// The read that produced it was not scoped, and the honest answer is
        /// to refuse the batch rather than to quietly drop the row and let an
        /// unscoped query ship looking healthy.
        case foreignRow = "foreign_row"
        /// Rows for more than one owner arrived together — the same failure
        /// reached by arithmetic instead of by a constant.
        case mixedOwners = "mixed_owners"
        /// A link minted for a different owner. Redeeming it would bind
        /// somebody else's account.
        case foreignLink = "foreign_link"
        /// A link minted for a different app than the record it is rendered
        /// with.
        case wrongToolkit = "wrong_toolkit"
        /// The address this card would have opened is not one of ours.
        ///
        /// Reported rather than swallowed. A blank where the link should be
        /// reads as "the ask is still loading" and gets retried forever; a
        /// refusal names the defect — a base handed to this file that is not
        /// the connect page, which is one configuration mistake away from a
        /// text carrying the OTHER company's address, the exact thing the spec
        /// forbids and the exact thing the spike did four times.
        case linkNotOurs = "link_not_ours"
        /// A weight, a timestamp or a level this build cannot read. Fails
        /// closed: an unreadable row must not be ranked, and must not be asked.
        case unreadableRow = "unreadable_row"
        /// WE HAVE NOT LOOKED. The evidence could not be read — the request
        /// failed, or the card was reached before the answer landed.
        ///
        /// It is its own cause and not folded into an empty card, because the
        /// two are claims about different things. "You use none of these" is a
        /// claim about the PERSON; this is a claim about US, and telling
        /// somebody the first when the truth is the second is how a working
        /// product gets abandoned at setup by a person whose network blinked.
        case couldNotLook = "could_not_look"
        /// There IS evidence for this owner and the catalog could name none of
        /// it. Also not an empty card: every row was dropped for want of a
        /// name, which is our defect, and rendering it as "nothing detected"
        /// bills it to the person.
        case catalogUnreadable = "catalog_unreadable"

        /// WHAT THE PERSON READS when this refusal reaches the setup card.
        ///
        /// DECIDED HERE AND NOT IN THE VIEW. `OnboardingConnectStep` drew
        /// `Copy.detectionTrouble` for EVERY refusal until 2026-09-06 — two
        /// renderings for three answers — and the reason it could is that the
        /// choice lived in a `some View` where no suite can run it. A caller
        /// that must pick a string cannot be checked; a caller that renders one
        /// can.
        ///
        /// EVERY REFUSAL ANSWERS, including the ones that cannot reach this
        /// screen, because a `default:` here is how the next cause added to the
        /// enum silently inherits somebody else's sentence. The scoping causes
        /// share `detectionTrouble`: to the person they are all "we could not
        /// work out your apps", and the half that names which is for the
        /// journal, where somebody can act on it.
        var cardSentence: String {
            switch self {
            case .catalogUnreadable:
                return Copy.catalogTrouble
            case .notSignedIn, .foreignRow, .mixedOwners, .foreignLink,
                 .wrongToolkit, .linkNotOurs, .unreadableRow, .couldNotLook:
                return Copy.detectionTrouble
            }
        }

        var sentence: String {
            switch self {
            case .notSignedIn:
                return "nobody is signed in on this phone; connections belong to one owner"
            case .foreignRow:
                return "a row for another owner reached this phone; the read was not scoped"
            case .mixedOwners:
                return "two owners' rows arrived together; signals rank per owner"
            case .foreignLink:
                return "this link was minted for another owner"
            case .wrongToolkit:
                return "this link was minted for another app"
            case .linkNotOurs:
                return "the address this card would open is not our connect page"
            case .unreadableRow:
                return "a row carried a value this build cannot read"
            case .couldNotLook:
                return "this owner's evidence could not be read, so nothing was ranked"
            case .catalogUnreadable:
                return "there is evidence for this owner and the catalog could name none of it"
            }
        }
    }

    // =====================================================================
    // MARK: - 1. Detection — which apps arrive pre-selected
    // =====================================================================

    /// One row on the card.
    struct DetectedApp: Equatable {
        let key: AppKey
        /// From the catalog. Never a slug shown raw: a vendor's internal
        /// spelling is not a name, and an app the catalog cannot name is an app
        /// this card cannot honestly offer.
        let name: String
        let logo: String?
        let preselected: Bool
        /// What we are going on, for the one-line "why am I seeing this".
        let evidence: [SignalSource]
    }

    enum Detection: Equatable {
        case apps([DetectedApp])
        case refused(Refusal)

        /// The rows the card shows. A refusal offers none — and still shows
        /// Skip and the search box, because nobody may be trapped in setup.
        var offered: [DetectedApp] {
            if case .apps(let list) = self { return list }
            return []
        }
    }

    enum RankResult: Equatable {
        case lines([RankedLine])
        case refused(Refusal)
    }

    /// A stored weight as it stands at `now`: `weight * 2^(-age / halfLife)`.
    /// `decayedWeight` in signals.ts, including its two refusals to amplify: a
    /// signal stamped in the FUTURE decays by zero rather than out-weighing
    /// every honest row, and a broken half-life loses the freshness ordering
    /// rather than zeroing the whole table.
    static func decayedWeight(_ weight: Double, lastSeenAt: Double, now: Double,
                              halfLifeMilliseconds: Double = Contract.defaultHalfLifeMilliseconds) -> Double {
        guard weight.isFinite else { return 0 }
        let age = now - lastSeenAt
        guard age.isFinite, age > 0 else { return weight }
        guard halfLifeMilliseconds.isFinite, halfLifeMilliseconds > 0 else { return weight }
        return weight * pow(2, -age / halfLifeMilliseconds)
    }

    /// Rank this owner's rows into the table the card reads from. Pure, total,
    /// and independent of arrival order: weight descending, ties broken by
    /// toolkit then alias, both ascending, and rows summed in a sorted order so
    /// the same evidence in a different order produces the same float.
    static func rank(_ rows: [SignalRow], for signedInOwner: OwnerID?, at now: Double,
                     halfLifeMilliseconds: Double = Contract.defaultHalfLifeMilliseconds) -> RankResult {
        guard let owner = signedInOwner else { return .refused(.notSignedIn) }
        guard now.isFinite else { return .refused(.unreadableRow) }

        let owners = Set(rows.map { $0.owner })
        if owners.count > 1 { return .refused(.mixedOwners) }
        if let only = owners.first, only != owner { return .refused(.foreignRow) }

        for row in rows {
            guard row.lastSeenAt.isFinite else { return .refused(.unreadableRow) }
            if let w = row.weight {
                // Strictly positive, as signals.ts insists: a negative weight
                // would let one piece of evidence SUBTRACT another and push an
                // app below apps with no evidence at all — a "never ask about
                // this" reached through arithmetic, invisible to the state
                // machine that is supposed to own that decision.
                guard w.isFinite, w > 0 else { return .refused(.unreadableRow) }
            }
        }

        let sorted = rows.sorted { a, b in
            sortKey(a) < sortKey(b)
        }

        var weights: [AppKey: Double] = [:]
        var lastSeen: [AppKey: Double] = [:]
        var sources: [AppKey: [SignalSource]] = [:]
        for row in sorted {
            let key = AppKey(toolkit: row.toolkit, alias: row.alias)
            let band = row.weight ?? (Contract.sourceWeight[row.source] ?? 0)
            let decays = Contract.sourceDecays[row.source] ?? true
            let value = decays
                ? decayedWeight(band, lastSeenAt: row.lastSeenAt, now: now,
                                halfLifeMilliseconds: halfLifeMilliseconds)
                : band
            weights[key] = (weights[key] ?? 0) + value
            lastSeen[key] = max(lastSeen[key] ?? -Double.greatestFiniteMagnitude, row.lastSeenAt)
            var seen = sources[key] ?? []
            if !seen.contains(row.source) { seen.append(row.source) }
            sources[key] = seen
        }

        var lines = weights.keys.map { key in
            RankedLine(key: key,
                       weight: weights[key] ?? 0,
                       lastSeenAt: lastSeen[key] ?? 0,
                       sources: (sources[key] ?? []).sorted { $0.rawValue < $1.rawValue })
        }
        lines.sort { a, b in
            let d = b.weight - a.weight
            let scale = max(1, abs(a.weight), abs(b.weight))
            if abs(d) > tieEpsilon * scale { return d < 0 }
            if a.key.toolkit != b.key.toolkit { return a.key.toolkit < b.key.toolkit }
            return (a.key.alias?.rawValue ?? "") < (b.key.alias?.rawValue ?? "")
        }
        return .lines(lines)
    }

    /// A NUL joiner, because a slug containing the separator would otherwise
    /// merge two apps into one row.
    private static func sortKey(_ row: SignalRow) -> String {
        [row.owner.raw, row.toolkit, row.alias?.rawValue ?? "", row.source.rawValue]
            .joined(separator: "\u{0}")
    }

    /// WHICH APPS ARRIVE PRE-SELECTED, ORDERED.
    ///
    /// From injected rows and catalog metadata only. There is no table of
    /// domains, no table of names and no branch on any app in this function —
    /// swap the catalog and the card changes with no diff here.
    ///
    /// Three exclusions, each with a different reason:
    ///   * a slug the catalog does not claim is DROPPED — there is no name to
    ///     show, and a raw vendor slug on an onboarding card is the vendor's
    ///     word leaking into the product's voice;
    ///   * a line carrying `connected` is DROPPED — it is already connected,
    ///     and offering it reads as "Anticipy forgot";
    ///   * a line carrying `asked` is SHOWN UNTICKED — the nudge state machine
    ///     already owns that conversation, and a pre-ticked box would re-put a
    ///     question this owner has already been put.
    static func detected(from signals: [SignalRow],
                         catalog: [CatalogEntry],
                         signedInOwner: OwnerID?,
                         at now: Double,
                         halfLifeMilliseconds: Double = Contract.defaultHalfLifeMilliseconds,
                         maxPreselected: Int = ConnectOnboardingPolicy.maxPreselected) -> Detection {
        switch rank(signals, for: signedInOwner, at: now, halfLifeMilliseconds: halfLifeMilliseconds) {
        case .refused(let why):
            return .refused(why)
        case .lines(let lines):
            var byslug: [String: CatalogEntry] = [:]
            for entry in catalog where byslug[entry.slug] == nil { byslug[entry.slug] = entry }

            var out: [DetectedApp] = []
            var ticked = 0
            for line in lines {
                guard let entry = byslug[line.key.toolkit] else { continue }
                if line.sources.contains(.connected) { continue }
                let alreadyAsked = line.sources.contains(.asked)
                let preselect = !alreadyAsked && ticked < maxPreselected
                if preselect { ticked += 1 }
                out.append(DetectedApp(key: line.key,
                                       name: entry.name,
                                       logo: entry.logo,
                                       preselected: preselect,
                                       evidence: line.sources))
            }
            return .apps(out)
        }
    }

    // =====================================================================
    // MARK: - 1B. The card, from what the server actually said
    // =====================================================================

    /// ONE LINE OF `me/connections/signals`: AN APP THIS OWNER LIVES IN,
    /// ALREADY RANKED, ALREADY NAMED.
    ///
    /// THE RANKING IS THE SERVER'S AND IS NOT REDONE HERE. `rank` above is the
    /// same arithmetic in this language, mirrored under a gate, and it still
    /// runs — over rows a caller holds locally. It cannot run over THIS,
    /// because the weight is deliberately not on the wire: it is an ordering
    /// with no unit that decays between two calls, and a number on the wire is
    /// an invitation to `if weight > 0.5` on a phone — a second policy about
    /// who gets asked to connect what, in the one place nobody reviewing this
    /// feature would look. Two definitions of which app is first is a list that
    /// reorders itself between the screen and the message about it.
    ///
    /// WHAT IS STILL DECIDED HERE IS EVERY PRODUCT QUESTION: which lines are
    /// dropped, which arrive ticked, and how many. That is what the card is,
    /// and it belongs where a laptop can run it.
    ///
    /// `unreadable` IS THE HONEST FOURTH FIELD. A source spelling or an account
    /// alias this build has never heard of reads as NOTHING rather than as the
    /// nearest thing — the enums are closed for that reason — but "nothing" is
    /// not the same as "there was nothing there", and the difference decides a
    /// tick. A line carrying one is SHOWN and never PRE-SELECTED: the exclusion
    /// rules are written in terms of sources (`connected` drops a line, `asked`
    /// unticks it), so a spelling we cannot read is a rule we cannot apply, and
    /// the safe side of a rule nobody could apply is the unticked one. Ticking
    /// it would be inventing a tick out of our own ignorance.
    struct RankedApp: Equatable {
        let key: AppKey
        /// From the catalog, through the server. Never a slug shown raw.
        let name: String
        let logo: String?
        let lastSeenAt: Double
        /// The kinds of evidence this build knows, as they arrived.
        let sources: [SignalSource]
        /// Every value on this line this build could not read — a source, an
        /// alias — kept rather than dropped in silence.
        let unreadable: [String]

        /// The line as the wire carried it: strings in, closed enums out.
        ///
        /// The client cannot build this type (the two files are compiled apart,
        /// on purpose — see the runners), so the translation is done from
        /// primitives HERE, where the enums are and where a suite can run it.
        init(toolkit: String, name: String, logo: String? = nil,
             alias: String? = nil, lastSeenAt: Double, sources: [String] = []) {
            var known: [SignalSource] = []
            var lost: [String] = []
            for raw in sources {
                if let source = SignalSource(rawValue: raw) {
                    if !known.contains(source) { known.append(source) }
                } else {
                    lost.append(raw)
                }
            }
            var account: AccountAlias?
            if let alias, !alias.isEmpty {
                account = AccountAlias(rawValue: alias)
                if account == nil { lost.append(alias) }
            }
            self.key = AppKey(toolkit: toolkit, alias: account)
            self.name = name
            self.logo = logo
            self.lastSeenAt = lastSeenAt
            self.sources = known
            self.unreadable = lost
        }
    }

    /// WHAT THE EVIDENCE ROUTE ANSWERED, in the four states the route declares
    /// (`SIGNALS_ANSWER`, routes/connections_api.ts).
    ///
    /// Four rather than one, because three of them come back EMPTY and they are
    /// three different things to say to a person. A card that folds them
    /// together tells somebody they use none of the apps in the world every
    /// time a request fails — on the one screen that then invites them to
    /// connect what they already live in.
    enum SignalsAnswer: Equatable {
        /// This owner's apps, best first, as the server ordered them.
        case ranked([RankedApp])
        /// We looked, and this owner has no evidence yet. THE ONLY ONE OF THE
        /// four that is a claim about the person.
        case nothingYet
        /// We could not look — the request failed, or the card was reached
        /// before the answer landed. A claim about us.
        case unreachable
        /// We looked, there IS evidence, and the catalog could name none of it.
        /// Also a claim about us, and a different one.
        case catalogUnreadable
    }

    /// THE CARD, FROM WHAT THE SERVER ACTUALLY SAID.
    ///
    /// The overload the flow calls. It exists because the flow used to call the
    /// one above with two literal empty arrays — `detected(from: [], catalog:
    /// [], …)` — so "detected apps pre-selected" pre-selected nothing, for
    /// every person, forever, while this file's own suite proved it would have
    /// ranked them correctly if anything had ever handed it a row.
    ///
    /// THREE EMPTY ANSWERS, THREE DIFFERENT THINGS TO SAY, and this is the
    /// function that keeps them apart:
    ///   * `.apps([])` — we looked, and there is nothing. A claim about the
    ///     person, and only made when the server made it.
    ///   * `.refused(.couldNotLook)` — we could not look.
    ///   * `.refused(.catalogUnreadable)` — we looked, there IS evidence, and
    ///     the catalog could name none of it.
    ///
    /// NEVER INVENT A TICK, and there are three ways this function could and
    /// does not: a refusal returns no rows at all; a line whose evidence this
    /// build cannot fully read is shown unticked; and the cap is a hard stop
    /// rather than a target, so a short list stays short.
    ///
    /// NO CLOCK. Nothing here decays, because nothing here re-ranks — the two
    /// went together, and a `now` on this signature would be a parameter that
    /// changes no answer and reads as though it might.
    static func detected(from answer: SignalsAnswer,
                         signedInOwner: OwnerID?,
                         maxPreselected: Int = ConnectOnboardingPolicy.maxPreselected) -> Detection {
        // Asked first, so a signed-out phone reads as signed out whatever the
        // network did. `notSignedIn` is the more fundamental fact and it is the
        // one the flow's other half (`ConnectBeat.audience`) is deciding on at
        // the same moment.
        guard signedInOwner != nil else { return .refused(.notSignedIn) }
        switch answer {
        case .unreachable:
            return .refused(.couldNotLook)
        case .catalogUnreadable:
            return .refused(.catalogUnreadable)
        case .nothingYet:
            return .apps([])
        case .ranked(let lines):
            var out: [DetectedApp] = []
            var ticked = 0
            for line in lines {
                // Already connected: offering it reads as "Anticipy forgot".
                if line.sources.contains(.connected) { continue }
                // Already asked: the nudge state machine owns that
                // conversation, and a pre-ticked box would re-put a question
                // this owner has already been put.
                let alreadyAsked = line.sources.contains(.asked)
                let readable = line.unreadable.isEmpty
                let preselect = !alreadyAsked && readable && ticked < maxPreselected
                if preselect { ticked += 1 }
                out.append(DetectedApp(key: line.key,
                                       name: line.name,
                                       logo: line.logo,
                                       preselected: preselect,
                                       evidence: line.sources))
            }
            return .apps(out)
        }
    }

    // =====================================================================
    // MARK: - The sign-up address' mail exchanger
    // =====================================================================

    /// How the observed host sits against a catalog host, strongest first.
    enum HostRelation: String {
        case exact
        case observedUnderCatalog
        case catalogUnderObserved
    }

    /// The labels of a host, or nil if there is not one. Accepts a bare host or
    /// an absolute http(s) url, because the observed side arrives as a host and
    /// the catalog side arrives as a url. Plumbing, mirroring `hostLabels` in
    /// signals.ts.
    static func hostLabels(_ raw: String?) -> [String]? {
        let s = (raw ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if s.isEmpty { return nil }

        var host = s
        if s.contains("://") {
            guard let comps = URLComponents(string: s),
                  let scheme = comps.scheme,
                  scheme == "http" || scheme == "https",
                  let parsed = comps.host, !parsed.isEmpty else { return nil }
            host = parsed.lowercased()
        } else {
            // A bare host has no path, no credentials and no whitespace.
            // Refusing those outright beats letting a url parser find a "host"
            // inside them: a string with an "@" would otherwise parse with
            // everything before it as credentials and an unrelated tail as the
            // host.
            if s.rangeOfCharacter(from: CharacterSet(charactersIn: " \t\n\r/@?#")) != nil { return nil }
        }

        while host.hasSuffix(".") { host.removeLast() }
        if host.isEmpty { return nil }
        // A literal address is one opaque label: it has no registrar inside it,
        // so only exact equality can ever mean anything.
        if host.hasPrefix("[") || host.contains(":") { return [host] }

        let labels = host.split(separator: ".", omittingEmptySubsequences: false).map(String.init)
        if labels.contains(where: { $0.isEmpty }) { return nil }
        return labels
    }

    /// A dotted quad is an address, not a name with an owner inside it.
    /// Trimming labels off one produces another valid address belonging to
    /// somebody else entirely, so containment must never apply to it.
    static func isNumericHost(_ labels: [String]) -> Bool {
        if labels.count == 1 { return labels[0].hasPrefix("[") || labels[0].contains(":") }
        return labels.allSatisfy { !$0.isEmpty && $0.allSatisfy { $0.isNumber } }
    }

    /// True when `inner`'s trailing labels are exactly `outer` — i.e. `inner` is
    /// a strict subdomain of `outer`.
    static func isUnder(_ inner: [String], _ outer: [String]) -> Bool {
        guard inner.count > outer.count else { return false }
        return Array(inner.suffix(outer.count)) == outer
    }

    static func relate(observed: [String], catalog: [String]) -> HostRelation? {
        if observed == catalog { return .exact }
        if isNumericHost(observed) || isNumericHost(catalog) { return nil }
        // Two labels minimum on both sides before containment is allowed. It is
        // the only brake available without a public-suffix list, and it stops
        // the shortest and most dangerous reading — a single-label host
        // swallowing every entry in the catalog.
        if observed.count < 2 || catalog.count < 2 { return nil }
        if isUnder(observed, catalog) { return .observedUnderCatalog }
        if isUnder(catalog, observed) { return .catalogUnderObserved }
        return nil
    }

    /// SEEDS FROM THE SIGN-UP ADDRESS' MAIL EXCHANGER.
    ///
    /// The spec's page-25 example is an owner whose mail is hosted by a vendor
    /// that also publishes several other apps, and the step pre-selects THAT
    /// VENDOR'S apps — plural. So unlike `hostToToolkit` in signals.ts, which
    /// refuses to pick when two entries claim a host, this returns ALL of them.
    ///
    /// The asymmetry is deliberate and it is about what a wrong answer costs.
    /// There, an ambiguous host would become HIGH weight and license a text
    /// about an app the owner may not use — spending one of their seven-day ask
    /// budget on a coin flip. Here the result is a tick-box the owner is
    /// looking at, on a card whose Skip is always visible: over-inclusion costs
    /// one tap, under-inclusion costs the whole point of the step. So the
    /// weight it carries is the contract's MEDIUM `mx` band, and the human is
    /// in the loop by construction.
    ///
    /// Two tiers, strongest only:
    ///   1. entries whose catalog-declared mail hosts claim the exchanger;
    ///   2. entries whose own site relates to the exchanger by exact match or
    ///      containment.
    /// No tier three. A shared-suffix rule would need a public-suffix list, and
    /// that is a table of domain literals — the hardcoding the spec forbids.
    static func seeds(fromMailExchanger host: String,
                      catalog: [CatalogEntry],
                      for signedInOwner: OwnerID?,
                      seenAt: Double) -> [SignalRow] {
        guard let owner = signedInOwner else { return [] }
        guard let observed = hostLabels(host) else { return [] }

        var declared: [String] = []
        var bySite: [String: HostRelation] = [:]

        for entry in catalog {
            let slug = entry.slug.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if slug.isEmpty { continue }

            var claimed = false
            for mail in entry.mailHosts {
                guard let theirs = hostLabels(mail) else { continue }
                if observed == theirs || isUnder(observed, theirs) { claimed = true; break }
            }
            if claimed {
                if !declared.contains(slug) { declared.append(slug) }
                continue
            }

            if let theirs = hostLabels(entry.appURL),
               let relation = relate(observed: observed, catalog: theirs) {
                if bySite[slug] == nil { bySite[slug] = relation }
            }
        }

        let chosen: [String]
        if !declared.isEmpty {
            chosen = declared.sorted()
        } else {
            // Strongest tier that matched, and only that tier.
            for relation: HostRelation in [.exact, .observedUnderCatalog, .catalogUnderObserved] {
                let slugs = bySite.filter { $0.value == relation }.keys.sorted()
                if !slugs.isEmpty {
                    return slugs.map {
                        SignalRow(owner: owner, toolkit: $0, source: .mx, lastSeenAt: seenAt)
                    }
                }
            }
            chosen = []
        }
        return chosen.map { SignalRow(owner: owner, toolkit: $0, source: .mx, lastSeenAt: seenAt) }
    }

    // =====================================================================
    // MARK: - The card
    // =====================================================================

    /// Every word this step says, in one place, so a test can read them.
    ///
    /// THE REGISTER IS FIXED BY THE SPEC. The owner never hears the vendor's
    /// name, and never hears "authorize", "grant access", "permissions",
    /// "integration", "API" or "OAuth". It is "connect your <name the catalog
    /// gave us>". The runner greps every string literal in this file and is red
    /// on any of those words.
    enum Copy {
        static let title = "Which apps do you live in?"
        static let subtitle = "Tick the ones you use. You can change this later."
        static let searchPlaceholder = "Search for another app"
        static let connect = "Connect"
        /// ALWAYS VISIBLE, never buried, in every state this step can be in —
        /// including the states where something upstream went wrong.
        static let skip = "Skip"
        /// Under the button, one sentence, per the spec: optional, the browser
        /// can do these too, connecting makes them instant and works with the
        /// laptop shut.
        static let footnote = "Optional — the browser can do all of this too. "
            + "Connecting just makes it instant, and it works with your laptop shut."

        // The four things the search area can be saying. Here rather than in
        // the view because copy is a decision, and this is where the register
        // gate can read all of it at once.
        static let searchPrompt = "Type the name of an app you use. "
            + "Anything I can reach is in here, including the ones I have never mentioned."
        static let searching = "Looking…"
        /// The catalog could not be reached. NOT "nothing matched": telling
        /// somebody their app does not exist when the truth is that a request
        /// failed is how a working product gets abandoned at setup.
        static let searchTrouble = "I could not look just now. Try again in a moment."
        static func nothingFound(query: String) -> String {
            "Nothing came back for \u{201C}\(query)\u{201D}. Try another name, or skip this — "
                + "you can add anything later."
        }

        /// What the PERSON is told when detection refused.
        ///
        /// Not `Refusal.sentence`, which says "the read was not scoped" and is
        /// for the journal: a diagnostic on a setup screen tells somebody their
        /// product is broken in a language they cannot act on. This says the
        /// true and useful half — nothing was worked out, nothing is required,
        /// here are the two things you can still do — and the card keeps both
        /// of them, because a refusal must never be a dead end during setup.
        static let detectionTrouble = "I could not work out which apps you use just now. "
            + "Search for one, or skip this — none of it is required."

        /// THE OTHER REFUSAL, WHICH IS A DIFFERENT THING TO HAVE HAPPENED.
        ///
        /// `detectionTrouble` is "we could not look". This one is "we looked,
        /// there IS evidence for you, and we could not put a NAME to any of it"
        /// — the catalog answered nothing usable. Both are claims about US and
        /// neither tells the person a falsehood about themselves, which is why
        /// one sentence over both was defensible; it was still two renderings
        /// for three answers, and the two failures need different work from us,
        /// so a support thread that can tell them apart is worth one string.
        ///
        /// It says LESS about the cause than the diagnostic does, on purpose:
        /// "the catalog is unreadable" is our vocabulary. What the person needs
        /// is that the list is missing, that it is not their fault, and that
        /// both ways out are still open.
        static let catalogTrouble = "I know you use a few apps, but I could not load their "
            + "names just now. Search for one, or skip this — none of it is required."

        /// EVERY SENTENCE THIS STEP CAN SAY, in one list, so a suite cannot
        /// check six of them and believe it checked the screen. The query
        /// inside `nothingFound` is the OWNER'S OWN WORDS quoted back, so the
        /// placeholder here stands for it: what the register gate judges is our
        /// prose, never theirs.
        static var everySentence: [String] {
            [title, subtitle, searchPlaceholder, connect, skip, footnote,
             searchPrompt, searching, searchTrouble, detectionTrouble, catalogTrouble,
             nothingFound(query: "…")]
        }
    }

    /// The whole card, decided. A view renders this and adds nothing.
    struct Step: Equatable {
        let title: String
        let subtitle: String
        let apps: [DetectedApp]
        let searchPlaceholder: String
        let connectLabel: String
        /// One Connect button, live only when something is ticked. Skip is what
        /// the empty card offers, and it is not a failure state.
        let connectEnabled: Bool
        let skipLabel: String
        let footnote: String
        /// Set when detection refused. The card still stands — search still
        /// works, Skip still works — because a person cannot be trapped in
        /// onboarding by a bad row.
        let refusal: Refusal?
    }

    static func step(for detection: Detection, chosen: Set<AppKey>) -> Step {
        step(for: detection, found: [], chosen: chosen)
    }

    /// The card, including the apps the owner went and found for themselves.
    static func step(for detection: Detection, found: [CatalogEntry],
                     chosen: Set<AppKey>) -> Step {
        var refusal: Refusal?
        if case .refused(let why) = detection { refusal = why }
        return Step(title: Copy.title,
                    subtitle: Copy.subtitle,
                    apps: offered(detection, plus: found),
                    searchPlaceholder: Copy.searchPlaceholder,
                    connectLabel: Copy.connect,
                    connectEnabled: !chosen.isEmpty,
                    skipLabel: Copy.skip,
                    footnote: Copy.footnote,
                    refusal: refusal)
    }

    /// An app the owner went and FOUND is an app they have just named, so it
    /// arrives ticked — unlike a detected one past the pre-selection cap, which
    /// nobody has said anything about. Its evidence list is empty because there
    /// honestly is none: the search box judged nothing, and their tap is the
    /// decision.
    static func chosenFromSearch(_ entry: CatalogEntry) -> DetectedApp {
        DetectedApp(key: AppKey(toolkit: entry.slug, alias: nil),
                    name: entry.name, logo: entry.logo,
                    preselected: true, evidence: [])
    }

    /// The card's rows: what was detected, then what the owner found, with
    /// nothing shown twice.
    ///
    /// The de-duplication is by `AppKey`, which is (toolkit, alias) — so an
    /// owner who has this app under two aliases keeps both rows, and a search
    /// hit for an app already on the card does not become a second tick-box
    /// that can disagree with the first about whether it is ticked.
    static func offered(_ detection: Detection, plus found: [CatalogEntry]) -> [DetectedApp] {
        var out = detection.offered
        var seen = Set(out.map { $0.key })
        for entry in found {
            let row = chosenFromSearch(entry)
            if seen.contains(row.key) { continue }
            seen.insert(row.key)
            out.append(row)
        }
        return out
    }

    /// The slugs the card is already showing, which is what the search area
    /// excludes. An id comparison, never a judgement about the words.
    static func slugsOnCard(_ apps: [DetectedApp]) -> Set<String> {
        Set(apps.map { $0.key.toolkit })
    }

    /// The tick-boxes as the card opens: whatever detection pre-selected.
    static func initialSelection(_ detection: Detection) -> Set<AppKey> {
        Set(detection.offered.filter { $0.preselected }.map { $0.key })
    }

    // =====================================================================
    // MARK: - The search box, which judges nothing
    // =====================================================================

    /// HARNESS-LAWS LAW 1, AND THE VIOLATION THIS REPLACED.
    ///
    /// Until 2026-09-05 this file answered the search box with
    /// `$0.name.lowercased().contains(needle)` — a case-insensitive substring
    /// test over the owner's own typed words, sorted by name, with no model
    /// anywhere behind it. That is a pattern deciding MEANING: "which app did
    /// they mean". It is wrong in both directions and both directions are
    /// measurable. It shows nothing for the half of the ways a person names an
    /// app that are not a prefix of the vendor's own spelling — a work mailbox
    /// asked for by the job it does, a product asked for by the name it had
    /// before it was bought, a name typed with one letter out of place. And it
    /// shows the wrong thing whenever three letters of one app's name sit
    /// inside another's. `ToolkitJudge` in `contract.ts` exists for exactly
    /// this question and was cited in four comments in this file with zero
    /// call sites, which is a law obeyed in prose and broken in code.
    ///
    /// THE SIBLING ALREADY HAD IT RIGHT. `ConnectedAppsModel.search` refuses to
    /// read the query at all: it hands it to the injected catalog as typed and
    /// shows what comes back, in the order it came back. Two search boxes in
    /// one feature must not run two rules, so this is now that rule, in the
    /// pure-function shape this layer keeps.
    ///
    /// What is left here is a REDUCER over an answer somebody else produced. It
    /// never sees the catalog, so it cannot match against it. The only two rows
    /// it drops are dropped on facts, not on words: one the card above is
    /// already showing (an id comparison against slugs this screen chose), and
    /// one the catalog could not put a name to — a nameless row is a blank line
    /// with a button on it, and a raw vendor slug is the vendor's own spelling
    /// leaking into our voice.

    /// What the catalog said when it was asked. Two states, because "it
    /// answered with nothing" and "it could not be reached" are different
    /// facts, and folding them together tells somebody their app does not
    /// exist when the truth is that the network is down.
    enum CatalogAnswer: Equatable {
        case hits([CatalogEntry])
        case unreachable
    }

    /// What the search area is, in five states, for the same reason the sibling
    /// has five: "nobody has typed anything", "we are asking", "nothing came
    /// back" and "we could not ask" are four different things to say, and a
    /// person told the wrong one gives up on a working product.
    enum SearchState: Equatable {
        case idle(String)
        case searching(String)
        case results([CatalogEntry])
        case nothingFound(String)
        case trouble(String)
    }

    /// The query as it leaves for the catalog: the spaces around it removed and
    /// NOTHING ELSE. No lowercasing, no folding, no splitting into words — the
    /// far end is the thing entitled to interpret it, and every transform
    /// applied here is a small decision about meaning taken by the wrong layer.
    /// `nil` means nobody has asked anything yet.
    static func searchQuery(_ typed: String) -> String? {
        let asked = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        return asked.isEmpty ? nil : asked
    }

    /// The search area, given what the owner typed and what the catalog
    /// answered. `answer` is nil while the answer is still in flight.
    static func searchState(typed: String, answer: CatalogAnswer?,
                            excluding shown: Set<String> = []) -> SearchState {
        guard let asked = searchQuery(typed) else { return .idle(Copy.searchPrompt) }
        guard let answer else { return .searching(Copy.searching) }
        switch answer {
        case .unreachable:
            return .trouble(Copy.searchTrouble)
        case .hits(let rows):
            let usable = rows.filter { row in
                !shown.contains(row.slug)
                    && !row.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            }
            return usable.isEmpty ? .nothingFound(Copy.nothingFound(query: asked))
                                  : .results(usable)
        }
    }

    // =====================================================================
    // MARK: - 2. Skip
    // =====================================================================

    /// WHAT A SKIP MEANS, in three facts, so one app cannot hold two answers.
    ///
    /// This exists because it did hold two. `ConnectOnboardingPolicy.skipOutcome`
    /// and `ConnectionsPolicy.recordDecline` are both reachable for the SAME
    /// event — the owner refusing an ask whose trigger is `onboarding`, on the
    /// card or in the text thread — and they disagreed about whether it costs a
    /// rung of the decline ladder. Each file's comment argued the other was
    /// wrong and neither moved, for as long as the disagreement was only ever
    /// printed as a note. A note is not a decision, so this is one, and
    /// `agreesWithSkip` makes it a thing a suite can hold BOTH implementations
    /// to instead of a paragraph each of them has its own copy of.
    ///
    /// The reasoning is on `skipOutcome` below.
    struct SkipMeaning: Equatable {
        /// False. A form refused is not an app refused.
        let advancesTheDeclineLevel: Bool
        /// False. `declined` at level 0 is a row the server refuses to read at
        /// all ("the ladder was not advanced, so the decline cannot be
        /// honoured"), which means nobody is ever asked about that app again —
        /// the opposite of a soft snooze, reached by trying to record one.
        let leavesTheRowDeclined: Bool
        /// Seven, the contract's own `ONBOARDING_SKIP_SNOOZE_DAYS`, not the
        /// ladder's fourteen.
        let snoozeDays: Int
    }

    static let skipMeans = SkipMeaning(advancesTheDeclineLevel: false,
                                       leavesTheRowDeclined: false,
                                       snoozeDays: Contract.onboardingSkipSnoozeDays)

    /// DOES THE SERVER RECORD WHAT THIS CARD MEANS BY A SKIP? MEASURED, NO.
    ///
    /// A skip has to reach the server or it does not exist: the local write is
    /// this handset's memory, a reinstall forgets it, a second phone never had
    /// it, and the ask engine — the thing that actually decides whether this
    /// person is asked again — reads neither. So the phone wants to send one.
    ///
    /// THE SERVER HALF LANDED ON 2026-09-06 AND THE DATABASE HALF DID NOT, and
    /// this constant is now tracking the second one. What changed and what did
    /// not, measured rather than assumed:
    ///
    ///   FIXED. `recordDecline` (connections/nudge.ts) no longer advances the
    ///   ladder for a setup-card skip. It writes `state: "declined_soft"`,
    ///   `level: 0` and a seven-day snooze, so when the snooze runs out the
    ///   person is back at threshold 0.50 and every trigger can reach them
    ///   again. `POST /me/connections/skip` answers `{level: 0, soft: true}`,
    ///   which is exactly what `serverAgreedWithSkip` below demands. Deployed
    ///   the same day: `/me/connections/skip` answers 401 rather than 404 on
    ///   the live backend. (The host is deliberately not written out — the
    ///   law-1 scan over this file refuses any domain literal, and it is right
    ///   to: a file that may carry one of ours is a file somebody will put an
    ///   app's in.)
    ///
    ///   NOT FIXED. Live D1's `connect_nudges` still carries the CHECK
    ///   constraint it shipped with — five states, no `declined_soft` — and
    ///   SQLite cannot widen a CHECK, so the table has to be rebuilt. Until it
    ///   is, that write is refused by the DATABASE: `recordSkip` answers
    ///   `not-recorded` and the route answers 503. A phone sending skips into
    ///   that would have every onboarding skip fail, which is worse than not
    ///   sending: the local snooze still happens either way, and a 503 per
    ///   ticked app is a burst of failures at the most fragile minute this
    ///   product has.
    ///
    ///   The repair is one file, run once, and it is somebody's yes rather than
    ///   an agent's: `migration/d1/2026-09-06-connect-nudges-declined-soft.sql`.
    ///   `overnight/is_connect_live.py` leg 13 is RED until it lands and names
    ///   that file in its own failure text, so nobody has to remember.
    ///
    /// That is exactly `skipMeans` inverted on two of its three facts, and
    /// `agreesWithSkip(levelBefore: 0, levelAfter: 1, declinedAfter: true, …)`
    /// returns false over it — the predicate this file already had for holding
    /// two implementations to one meaning, pointed at the server for the first
    /// time.
    ///
    /// The spec says the same thing in its own words twice: page 21, "Skip
    /// records `declined_soft` with a 7-day snooze, not a real decline", and
    /// page 25, "Skipping in onboarding is a 7-day snooze, not a decline".
    /// `NudgeState.declinedSoft` now exists on BOTH sides — contract.ts, this
    /// app's own enum, and the Worker's ladder. What is missing is a column
    /// constraint on one table.
    ///
    /// SO THE WIRE IS BUILT AND NOT USED, WHICH IS A THIRD STATE AND NOT A
    /// SHRUG. `ConnectedAppsClient.skip` exists, is driven by the suite, and
    /// has a call site in the flow that reads this constant. Flipping it to
    /// true is the whole change, and it is ONE line the day the migration runs.
    /// The step runner reads the Worker's `recordDecline` and demands this
    /// constant match it, so it goes RED in BOTH directions until the two
    /// agree. Nobody has to remember.
    ///
    /// Writing a wrong `declined` is not the safe direction here and that is
    /// the whole argument: an unsent skip costs one person one repeated ask,
    /// which the next skip can correct, and a recorded level-1 decline cannot
    /// be walked back by anything the phone can do.
    /// TRUE SINCE 2026-09-06 19:40Z. The migration that lets live D1 hold
    /// `declined_soft` (migration/d1/2026-09-06-connect-nudges-declined-soft.sql)
    /// was applied to production that evening with 0 rows to carry, and
    /// overnight/is_connect_live.py leg 13 reads PASS against the live CHECK.
    /// nudge.ts treats declined_soft as the legitimate level-0 refusal. Build
    /// 148 was stamped while this still read false and the gate refused it --
    /// correctly, since a false here with a live table that CAN hold the state
    /// was tape with no tracker. Both halves agree now; so does this line.
    static let serverRecordsTheSoftSnooze = true

    /// Does another implementation of "the owner refused the setup card" mean
    /// the same thing this one does?
    ///
    /// Written over the FACTS rather than over a row type on purpose: the other
    /// implementation of this transition keeps its clock in seconds while this
    /// one keeps milliseconds, and a comparison that could not span that would
    /// have to be written twice — which is how the two halves drifted in the
    /// first place. So the caller reads its own row, in its own units, and
    /// hands over the three numbers this decision is actually about.
    ///
    /// The snooze is compared to within half a day, because the two sides round
    /// their clocks differently and a disagreement worth failing over is a
    /// disagreement about WEEKS.
    static func agreesWithSkip(levelBefore: Int, levelAfter: Int,
                               declinedAfter: Bool, snoozeDaysAfter: Double) -> Bool {
        guard (levelAfter != levelBefore) == skipMeans.advancesTheDeclineLevel else { return false }
        guard declinedAfter == skipMeans.leavesTheRowDeclined else { return false }
        guard snoozeDaysAfter.isFinite else { return false }
        return abs(snoozeDaysAfter - Double(skipMeans.snoozeDays)) < 0.5
    }

    /// DID THE FAR END MEAN WHAT THIS CARD MEANT?
    ///
    /// `agreesWithSkip` pointed at an acknowledgement off the wire instead of
    /// at a row, so the phone can check the server's answer with the same
    /// predicate it checks its neighbour's transition with. One meaning, one
    /// judge, whichever implementation is being judged.
    ///
    /// A FLOOR, AND POINTED THE WAY A FLOOR MUST POINT. The question is "does
    /// anything license believing the server recorded what this card means",
    /// and a missing level or a missing instant is nobody answering — so it
    /// returns false rather than waving through. A no-verdict that waved
    /// through would be a phone that stopped asking on an answer it never read.
    ///
    /// `declinedAfter` IS THE LEVEL, and that is a fact about the far end
    /// rather than a convenience: the ask engine's `recordDecline` stamps
    /// `declined` in the same statement that advances the ladder, so a level
    /// above zero and a row left saying declined are the same event. The
    /// acknowledgement carries no field for the row's state, and inventing one
    /// here would be reading a word to decide what happened.
    ///
    /// Milliseconds on both sides, which is the contract's clock. The phone's
    /// own store keeps seconds and that gap is spanned by `agreesWithSkip`
    /// taking a count of DAYS rather than two instants.
    static func serverAgreedWithSkip(levelAfter: Int?, snoozeUntil: Double?,
                                     at now: Double) -> Bool {
        guard let level = levelAfter, let until = snoozeUntil else { return false }
        guard now.isFinite, until.isFinite else { return false }
        return agreesWithSkip(levelBefore: 0, levelAfter: level,
                              declinedAfter: level >= 1,
                              snoozeDaysAfter: (until - now) / Contract.dayMilliseconds)
    }

    /// What Skip did, so a caller logs what it actually wrote.
    struct SkipOutcome: Equatable {
        let records: [NudgeRecord]
        let snoozeDays: Int
        /// Always false. Named, and returned, so the claim is pinned by a test
        /// rather than by a comment.
        let declineLevelChanged: Bool
    }

    enum SkipResult: Equatable {
        case snoozed(SkipOutcome)
        case refused(Refusal)
    }

    /// SKIP IS A SEVEN-DAY SOFT SNOOZE, NOT A DECLINE.
    ///
    /// Somebody skipping a card during setup has not refused the app; they have
    /// refused a form. The contract prices that at
    /// `ONBOARDING_SKIP_SNOOZE_DAYS` — seven days, not the ladder's fourteen.
    ///
    /// AND THE LEVEL DOES NOT MOVE. This is the half that matters more than the
    /// number, and it is the half `recordDecline` gets wrong — in
    /// `ConnectionsPolicy` next door and in `src/connections/policy.ts` on the
    /// server, both of which stamp `state: declined` and `level: 1` on the same
    /// event this function is given. `skipMeans` below is the decision between
    /// them, made rather than noted, with the reasoning here.
    ///
    /// Read the consequences of level 1 on the server's own thresholds: it
    /// raises the bar from 0.5 to 0.8, and `shouldAsk` compares STRICTLY
    /// (`!(score > threshold)`) — so a shrug at the setup card silences
    /// `repeated_use` (0.6) and `onboarding` (0.7) outright and leaves
    /// `in_task` (0.8) permanently one hair short. The only two moments that
    /// could ever ask again are the owner naming the app themselves and a
    /// closed laptop. A person who tapped Skip during setup would never again
    /// be asked by either trigger that carries EVIDENCE — the two that can name
    /// a task which already cost them real time, which is the only argument
    /// this product has. That is not a seven-day snooze; it is a life sentence
    /// with a seven-day label.
    ///
    /// THE CONTRACT SAYS THE SAME THING IN ITS VOCABULARY, and that is what
    /// settles it rather than this file's preference. `SNOOZE_DAYS` is
    /// documented "Snooze after each DECLINE"; `level` is "0 while never
    /// declined; 1, 2, 3 as DECLINES accumulate"; and the seven-day number is
    /// a separate constant that does not live in that table and is named
    /// `ONBOARDING_SKIP_SNOOZE_DAYS` — a SKIP, deliberately not a decline.
    /// Two vocabularies, two things. `recordDecline`'s own comment already
    /// agrees in words — "a card skipped during setup is a form refused, not an
    /// app refused" — and then advances the ladder anyway, which fixes the
    /// number and leaves the sentence. Where a comment and an assignment
    /// disagree, the assignment is what ships.
    ///
    /// WHICH STATE A SHRUG LEAVES BEHIND, and why it is not "declined": the
    /// server refuses to read a row that says `declined` at level 0
    /// ("the ladder was not advanced, so the decline cannot be honoured") and
    /// returns `no-verdict`, which means NOBODY IS EVER ASKED about that app
    /// again. `asked` with `acted_at` set is refused for the same reason. So
    /// the ladder position stays where it was, the fact that a card was shown
    /// lives in `sentAt`/`trigger`/`channel`, the shrug itself lives in
    /// `actedAt`, and the only thing that moves is the snooze.
    ///
    /// Three things Skip must not do, each pinned by a test:
    ///   * never un-connect an app connected earlier on the same card;
    ///   * never shorten an existing snooze (a level-3 stop outlives a shrug);
    ///   * never advance, and never reset, the decline level.
    static func skipOutcome(offered records: [NudgeRecord],
                            signedInOwner: OwnerID?,
                            at now: Double) -> SkipResult {
        guard let owner = signedInOwner else { return .refused(.notSignedIn) }
        guard now.isFinite else { return .refused(.unreadableRow) }
        if records.contains(where: { $0.owner != owner }) { return .refused(.foreignRow) }
        if records.contains(where: { $0.level < 0 || $0.level > 3 }) { return .refused(.unreadableRow) }

        let until = now + Double(Contract.onboardingSkipSnoozeDays) * Contract.dayMilliseconds
        var out: [NudgeRecord] = []
        for record in records {
            var next = record
            switch record.state {
            case .connected, .needsReconnect:
                // Nothing to snooze. Skip is about the ASK; the connection is
                // not an ask and is not undone by walking past a card.
                out.append(next)
                continue
            case .declined:
                // The ladder already has an answer from this person, and the
                // row is the only record of HOW it was reached. Extend the
                // snooze if ours is longer and touch nothing else — in
                // particular not `trigger`, because the server infers "the
                // level-1 laptop-closed override has been spent" from the
                // trigger of the ask that WAS declined. Rewriting it to
                // `onboarding` would hand that override back and let a
                // laptop-closed moment ask inside a snooze the owner earned by
                // saying no. And not `actedAt`, which is the moment they
                // actually said it.
                next.snoozeUntil = max(record.snoozeUntil ?? -Double.greatestFiniteMagnitude, until)
                out.append(next)
                continue
            case .declinedSoft:
                // ALREADY A SHRUG. Walking past the card a second time is the
                // same answer, not a new one: extend the quiet if ours is
                // longer and touch nothing else. Without this branch the row
                // would fall through and re-stamp `actedAt`, which would move
                // the moment they answered to the moment they scrolled past.
                next.snoozeUntil = max(record.snoozeUntil ?? -Double.greatestFiniteMagnitude,
                                       until)
                out.append(next)
                continue
            case .neverAsked, .asked:
                // The ladder has not advanced and does not advance now — and
                // since 2026-09-06 the row can SAY that rather than imply it.
                // It used to become `neverAsked`, which had the right effect
                // (askable again when the snooze ends) and told a small lie:
                // they WERE asked, the card was on the glass, and `actedAt` two
                // lines down says so. `declinedSoft` is the state the server's
                // own ladder writes for this exact event, so the offline
                // fallback and the server row now mean one thing.
                next.state = .declinedSoft
            }
            // Never shorten a snooze somebody already earned.
            next.snoozeUntil = max(record.snoozeUntil ?? -Double.greatestFiniteMagnitude, until)
            next.trigger = .onboarding
            next.actedAt = now
            out.append(next)
        }
        return .snoozed(SkipOutcome(records: out,
                                    snoozeDays: Contract.onboardingSkipSnoozeDays,
                                    declineLevelChanged: false))
    }

    // =====================================================================
    // MARK: - 3. The text and the app are one ask
    // =====================================================================

    /// One nudge record and the link minted for it — the single thing BOTH
    /// channels render.
    struct Ask: Equatable {
        let record: NudgeRecord
        let link: LinkRow?
    }

    /// What one channel shows. Two of these, built from one `Ask`, must agree.
    struct Rendering: Equatable {
        let channel: Channel
        let key: AppKey
        let appName: String
        /// The connect link. IDENTICAL across channels, byte for byte, because
        /// our token is single-use: two tokens would be two redeems, two vendor
        /// round trips and two connection rows for one app.
        let url: String?
        let state: NudgeState
        let showsConnect: Bool
        /// Always true. Skip is never buried, in either channel.
        let showsSkip: Bool
    }

    enum RenderResult: Equatable {
        case shown(Rendering)
        case refused(Refusal)
    }

    /// OUR `/c/{token}` page — never the vendor's URL, and never a vendor URL
    /// in a text. The base is INJECTED rather than written here: a host literal
    /// in this file is the domain hardcoding the runner refuses, and the app
    /// already knows its own base from configuration.
    ///
    /// AND INJECTED IS NOT THE SAME AS TRUSTED. Until 2026-09-05 this function
    /// trimmed one slash off whatever it was handed and glued the token on:
    /// no scheme check, no host check, no path check, under a doc comment
    /// promising "never the vendor's URL, and never a vendor URL in a text".
    /// A base read from a stale configuration, a debug build's local server, or
    /// a provider link pasted into a settings field would all have been
    /// rendered into the card AND into the text as if they were ours — and
    /// during the spike a raw provider link WAS used as the ask four times
    /// (`research/2026-09-05-composio-connections.md`, item 4). A promise in a
    /// comment is not a check.
    ///
    /// THE CHECK LIVES NEXT DOOR ON PURPOSE. `ConnectHandoff` already owns the
    /// allowlist — one host, exact match, https only, no credentials, no port,
    /// our path segment, and a token shaped like a token — and it is the same
    /// function the app calls before it opens anything. A second copy here
    /// would be a second allowlist to widen, and it could not live in this file
    /// anyway: the runner refuses a domain literal in this source, which is
    /// precisely why the host belongs where the check is.
    ///
    /// `nil` means "this is not our connect page". Callers refuse; none of them
    /// fall back to showing it.
    static func connectURL(token: String, base: String) -> String? {
        let trimmed = base.hasSuffix("/") ? String(base.dropLast()) : base
        let candidate = trimmed + "/" + token
        guard let url = URL(string: candidate),
              ConnectHandoff.connectLinkIsOurs(url: url) else { return nil }
        return candidate
    }

    static func rendering(of ask: Ask, in channel: Channel, catalog: [CatalogEntry],
                          base: String, signedInOwner: OwnerID?, at now: Double) -> RenderResult {
        guard let owner = signedInOwner else { return .refused(.notSignedIn) }
        guard ask.record.owner == owner else { return .refused(.foreignRow) }
        if let link = ask.link {
            guard link.owner == owner else { return .refused(.foreignLink) }
            guard link.toolkit == ask.record.toolkit else { return .refused(.wrongToolkit) }
        }

        let name = catalog.first { $0.slug == ask.record.toolkit }?.name ?? ask.record.toolkit
        let settled = ask.record.state == .connected
        var url: String?
        if let link = ask.link, link.isLive(at: now), !settled {
            // REFUSED, not blanked. A card with an empty link where a live one
            // belongs looks like an ask still loading and gets retried; a
            // refusal names the defect and stops the same bad base reaching the
            // TEXT, where a wrong address is permanent and unrecallable.
            guard let ours = connectURL(token: link.token, base: base) else {
                return .refused(.linkNotOurs)
            }
            url = ours
        }
        return .shown(Rendering(channel: channel,
                                key: ask.record.key,
                                appName: name,
                                url: url,
                                state: ask.record.state,
                                showsConnect: !settled,
                                showsSkip: true))
    }

    /// THE FIRST TEXT CARRIES THE SAME LINK.
    ///
    /// The card and the text go out the same minute and are one ask: the
    /// contract's `ConnectLink` is single-use and bound to (owner, toolkit), so
    /// minting a second token for the second channel would produce two live
    /// bindings for one app, and whichever the owner did not tap would sit in
    /// their messages as a working link to a connection they never asked for.
    ///
    /// True only when both renderings succeed AND carry byte-identical urls.
    static func firstTextCarriesSameLink(_ ask: Ask, catalog: [CatalogEntry], base: String,
                                         signedInOwner: OwnerID?, at now: Double) -> Bool {
        guard case .shown(let app) = rendering(of: ask, in: .ios, catalog: catalog, base: base,
                                               signedInOwner: signedInOwner, at: now),
              case .shown(let text) = rendering(of: ask, in: .sms, catalog: catalog, base: base,
                                                signedInOwner: signedInOwner, at: now)
        else { return false }
        guard let a = app.url, let t = text.url else { return false }
        return a == t && app.key == text.key && app.state == text.state
            && app.showsConnect == text.showsConnect
    }

    /// Do the two renderings of this record agree about everything except which
    /// channel they are? The lockstep property, executable, so a test can assert
    /// it after every action rather than eyeballing two structs.
    static func renderingsAgree(_ ask: Ask, catalog: [CatalogEntry], base: String,
                                signedInOwner: OwnerID?, at now: Double) -> Bool {
        guard case .shown(let app) = rendering(of: ask, in: .ios, catalog: catalog, base: base,
                                               signedInOwner: signedInOwner, at: now),
              case .shown(let text) = rendering(of: ask, in: .sms, catalog: catalog, base: base,
                                                signedInOwner: signedInOwner, at: now)
        else { return false }
        return app.url == text.url && app.state == text.state && app.key == text.key
            && app.appName == text.appName && app.showsConnect == text.showsConnect
            && app.showsSkip == text.showsSkip
    }

    /// Whether a second token may be minted for an ask that already has one.
    enum LinkDecision: Equatable {
        /// A live token exists: BOTH channels carry this one.
        case reuse(String)
        /// Nothing live — the record has never had a link, or the ten minutes
        /// ran out while the text sat unread. One token is minted, and it is
        /// still ONE ask: the record is not re-sent and the cap is not charged
        /// again.
        case mint
        case refused(Refusal)
    }

    static func linkDecision(for record: NudgeRecord, existing: LinkRow?,
                             signedInOwner: OwnerID?, at now: Double) -> LinkDecision {
        guard let owner = signedInOwner else { return .refused(.notSignedIn) }
        guard record.owner == owner else { return .refused(.foreignRow) }
        guard let link = existing else { return .mint }
        guard link.owner == owner else { return .refused(.foreignLink) }
        guard link.toolkit == record.toolkit else { return .refused(.wrongToolkit) }
        return link.isLive(at: now) ? .reuse(link.token) : .mint
    }

    /// What the owner did, in whichever channel they did it.
    enum Act: Equatable {
        case connected(accountID: String)
        case skipped
    }

    /// What the caller must write. Effects are returned rather than performed
    /// so that "how many connections did this produce" is answerable in a test
    /// with no store — which is the only way to prove a racing double action
    /// settles to ONE.
    enum Effect: Equatable {
        case createConnection(toolkit: String, alias: AccountAlias?, accountID: String,
                              writesEnabled: Bool)
        case spendLink(token: String)
        case snooze(until: Double)
    }

    struct Settlement: Equatable {
        let record: NudgeRecord
        let effects: [Effect]
        /// Log line. Nothing branches on these words.
        let note: String
    }

    enum ActResult: Equatable {
        case settled(Settlement)
        case refused(Refusal)
    }

    /// ACT IN EITHER CHANNEL; THE OTHER FLIPS.
    ///
    /// The record is the single source of truth, so "acting in the app" and
    /// "acting in the text" are the same function with a different `channel`
    /// stamped on the row — and a second action arriving from the other channel
    /// lands on a record that is already settled and produces NO second effect.
    /// That is what makes a racing double tap one connection instead of two:
    /// the loser of the race is not an error and is not a duplicate, it is a
    /// no-op that reports what already happened.
    ///
    /// `writesEnabled` is FALSE on every connection this creates. "Let Anticipy
    /// make changes" is the write opt-in the Two Hands ladder needs for rung 3,
    /// it is off by default, and reads never require it — so it can only ever be
    /// turned on by the owner, on purpose, in Settings.
    static func act(_ what: Act, in channel: Channel, on ask: Ask,
                    signedInOwner: OwnerID?, at now: Double) -> ActResult {
        guard let owner = signedInOwner else { return .refused(.notSignedIn) }
        guard ask.record.owner == owner else { return .refused(.foreignRow) }
        guard now.isFinite else { return .refused(.unreadableRow) }
        if let link = ask.link {
            guard link.owner == owner else { return .refused(.foreignLink) }
            guard link.toolkit == ask.record.toolkit else { return .refused(.wrongToolkit) }
        }

        var record = ask.record

        switch what {
        case .connected(let accountID):
            if record.state == .connected {
                return .settled(Settlement(record: record, effects: [],
                                           note: "already connected in the other channel; "
                                               + "one ask, one connection"))
            }
            record.state = .connected
            record.actedAt = now
            record.channel = channel
            // A connected app has nothing left to snooze, and leaving a date on
            // the row would quietly gag the reconnect ask if the token expires.
            record.snoozeUntil = nil
            var effects: [Effect] = [
                .createConnection(toolkit: record.toolkit, alias: record.alias,
                                  accountID: accountID, writesEnabled: false)
            ]
            if let link = ask.link, link.isLive(at: now) { effects.append(.spendLink(token: link.token)) }
            return .settled(Settlement(record: record, effects: effects,
                                       note: "connected from \(channel.rawValue)"))

        case .skipped:
            if record.state == .connected {
                return .settled(Settlement(record: record, effects: [],
                                           note: "already connected in the other channel; "
                                               + "a skip does not undo a connection"))
            }
            switch skipOutcome(offered: [record], signedInOwner: owner, at: now) {
            case .refused(let why):
                return .refused(why)
            case .snoozed(let outcome):
                let next = outcome.records[0]
                var effects: [Effect] = []
                if let until = next.snoozeUntil { effects.append(.snooze(until: until)) }
                var stamped = next
                stamped.channel = channel
                return .settled(Settlement(record: stamped, effects: effects,
                                           note: "skipped from \(channel.rawValue); "
                                               + "\(outcome.snoozeDays)-day soft snooze, level unchanged"))
            }
        }
    }

    // =====================================================================
    // MARK: - 4. The onboarding ask and the one-ask-per-week cap
    // =====================================================================

    /// Whether the global cap is consulted at all for this ask. `applies` does
    /// NOT mean "refuse" — it means "hand this to the ordinary cap check",
    /// which passes whenever the last ask is older than the interval.
    enum CapVerdict: Equatable {
        case exempt(String)
        case applies(String)

        var isExempt: Bool {
            if case .exempt = self { return true }
            return false
        }
    }

    /// THE READING, STATED AND PINNED.
    ///
    /// The spec says two things that look like they collide: onboarding ALWAYS
    /// asks, and no owner is asked about connections more than once in seven
    /// days across all apps. They do not collide, because the cap exists to
    /// stop NAGGING, and a person who has been asked nothing has not been
    /// nagged. The setup card is also not an interruption in the sense the cap
    /// prices: it is a step of a flow the owner is walking through right now,
    /// with Skip on the screen.
    ///
    /// So the onboarding ask is EXEMPT FROM THE CAP AS A GATE — it is never
    /// blocked by the ask ledger, and the step never has to read it. Two
    /// narrowings, because "onboarding" must not become a word that buys an
    /// extra ask:
    ///
    ///   * the exemption is spent on an EMPTY LEDGER only. If this owner was
    ///     genuinely asked about some other app inside the interval, the cap
    ///     applies however the trigger is spelled. A caller that mislabels a
    ///     mid-week nudge as `onboarding` gains nothing.
    ///   * the same ask rendered in the second channel is not a second ask. The
    ///     text going out the same minute carries the SAME nudge record and the
    ///     SAME link, so a ledger entry whose instant IS this record's `sentAt`
    ///     is this ask, and it does not bar its own other half.
    ///
    /// AND IT CHARGES. The onboarding card DOES stamp the ledger
    /// (`onboardingAskChargesTheCap`), exactly once per record, at the instant
    /// the first channel sent it. The exemption is about there being nothing to
    /// nag about YET; the moment the card is on screen there is, and the next
    /// ask waits the full seven days. It also lands on the same number as Skip's
    /// snooze, so a skipped setup means one quiet week either way.
    static func onboardingAskIsExemptFromGlobalCap(trigger: Trigger,
                                                   lastAskAnyAppAt: Double?,
                                                   thisAskSentAt: Double?,
                                                   at now: Double) -> CapVerdict {
        guard trigger == .onboarding else {
            return .applies("the cap applies to every ask that is not the setup step")
        }
        guard let last = lastAskAnyAppAt else {
            return .exempt("nothing has ever been asked of this owner; a new owner is not being nagged")
        }
        if let sent = thisAskSentAt, sent == last {
            return .exempt("the ledger's newest entry is this same ask in its other channel; "
                           + "one record, one ask")
        }
        let since = now - last
        if since >= Double(Contract.globalAskIntervalDays) * Contract.dayMilliseconds {
            return .applies("the cap applies and passes: the last ask is older than "
                            + "\(Contract.globalAskIntervalDays) days")
        }
        return .applies("this owner was asked about some app inside the interval; "
                        + "the setup step does not buy a second ask")
    }

    /// Yes. See the reasoning above.
    static let onboardingAskChargesTheCap = true

    /// The instant the ask ledger records, or nil when nothing is charged.
    /// Once per RECORD, never once per channel: the second rendering finds
    /// `sentAt` already set and does not move it, which is what keeps the
    /// same-minute text from spending a second week of the owner's budget.
    static func capLedgerStamp(for record: NudgeRecord, at now: Double) -> Double? {
        guard onboardingAskChargesTheCap else { return nil }
        return record.sentAt ?? now
    }
}

/// THE SEAM. Everything this step knows about the world outside itself.
///
/// One call, and it carries the owner even though a catalog lookup does not
/// strictly need one — the same rule `ConnectedAppsStore` keeps next door, for
/// the same reason: a call that does not take an owner is a call somebody can
/// make while signed out, and there is no such call in this feature.
///
/// THE QUERY GOES OVER THIS SEAM UNREAD. Whoever implements it is the one
/// entitled to decide which apps the owner's words point at — the contract's
/// `ToolkitJudge`, a model with the catalog in front of it. What comes back is
/// shown in the order it came back. Nothing on this side of the seam matches,
/// ranks, corrects or second-guesses it; see the Law-1 note on
/// `ConnectOnboardingPolicy.searchState`.
///
/// `@MainActor` because the step is: one actor, one card, no chance of a late
/// answer landing on a copy of the state somebody else is also holding.
/// Implementations do their waiting inside `await`.
@MainActor
protocol OnboardingCatalogSearch: AnyObject {
    func catalog(matching query: String,
                 owner: ConnectOnboardingPolicy.OwnerID)
        async throws -> [ConnectOnboardingPolicy.CatalogEntry]
}
