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
///     file and must never be: `visibleMatches` below filters a list the owner
///     is looking at, and the owner's TAP is the decision.
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
        /// A weight, a timestamp or a level this build cannot read. Fails
        /// closed: an unreadable row must not be ranked, and must not be asked.
        case unreadableRow = "unreadable_row"

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
            case .unreadableRow:
                return "a row carried a value this build cannot read"
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
        var refusal: Refusal?
        if case .refused(let why) = detection { refusal = why }
        return Step(title: Copy.title,
                    subtitle: Copy.subtitle,
                    apps: detection.offered,
                    searchPlaceholder: Copy.searchPlaceholder,
                    connectLabel: Copy.connect,
                    connectEnabled: !chosen.isEmpty,
                    skipLabel: Copy.skip,
                    footnote: Copy.footnote,
                    refusal: refusal)
    }

    /// The tick-boxes as the card opens: whatever detection pre-selected.
    static func initialSelection(_ detection: Detection) -> Set<AppKey> {
        Set(detection.offered.filter { $0.preselected }.map { $0.key })
    }

    /// The search box, over the catalog.
    ///
    /// LAW 1: this decides nothing. It narrows a list the owner is looking at,
    /// and the owner's TAP is the decision — which is why it may be a plain
    /// case-insensitive containment over the name the CATALOG supplied. What it
    /// must never become is the answer to "which app did they mean": a query
    /// that matches nothing is a question for the contract's `ToolkitJudge`, a
    /// model with the catalog in front of it, not for a wider rule here.
    static func visibleMatches(for query: String, in catalog: [CatalogEntry],
                               excluding shown: Set<String> = []) -> [CatalogEntry] {
        let needle = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if needle.isEmpty { return [] }
        return catalog
            .filter { !shown.contains($0.slug) && $0.name.lowercased().contains(needle) }
            .sorted { $0.name.lowercased() < $1.name.lowercased() }
    }

    // =====================================================================
    // MARK: - 2. Skip
    // =====================================================================

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
    /// number, and it is where this file DIVERGES from `recordDecline` in
    /// `src/connections/policy.ts`, which stamps `state: "declined"` and
    /// `level: 1` with a seven-day snooze. Read the consequences of that on the
    /// server's own thresholds: level 1 raises the bar from 0.5 to 0.8, and the
    /// score must beat it STRICTLY — so a shrug at the setup card silences
    /// `repeated_use` (0.6) and `onboarding` (0.7) outright and leaves
    /// `in_task` (0.8) permanently one hair short. A person who tapped Skip
    /// during setup would then never be asked again by the two triggers that
    /// carry actual evidence. That is not a seven-day snooze; it is a life
    /// sentence with a seven-day label.
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
            case .neverAsked, .asked:
                // The ladder has not advanced and does not advance now.
                next.state = .neverAsked
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
    static func connectURL(token: String, base: String) -> String {
        let trimmed = base.hasSuffix("/") ? String(base.dropLast()) : base
        return trimmed + "/" + token
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
            url = connectURL(token: link.token, base: base)
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
