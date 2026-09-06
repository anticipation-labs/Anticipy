import Foundation

/// THE CONNECT HANDOFF — the seconds between the owner's tap and the sign-in
/// page the other company serves. Everything compliance-critical about
/// connecting an app happens inside that gap, and all of it is decided here so
/// it can be decided on a laptop with no phone, no network and no browser.
///
/// Spec: "Connections: how Anticipy asks, learns, and never says Composio",
/// 2026-09-05, pages 20–31. Server contract:
/// `spike/two-hands/src/connections/contract.ts` — the tables, the states, the
/// ten-minute link and the OwnerId rule live there and this file agrees with
/// it rather than reinventing it.
///
/// ── THE FOUR THINGS THIS FILE IS ────────────────────────────────────────
///
/// 1. `ConnectPresentation` — HOW a connect link is opened. Two ways, both of
///    them a real browser: a system sign-in session (preferred, because the
///    callback comes back to us instead of through the front door), or the
///    system browser. There is deliberately no third opening mode, and an
///    in-app embedded web view is not a fallback, a degraded mode, or an
///    option on an old OS: Google answers a sign-in inside one with
///    `disallowed_useragent` and the connect simply fails. `ConnectHandoffTests`
///    reads this file's own source and fails if either embedded-view class name
///    appears in it at all, which is the only form of that guarantee a future
///    refactor cannot quietly delete.
///
/// 2. `DisclosureGate` — the in-context disclosure. Google's Workspace policy
///    wants the owner told what will be read, in context, with a REAL TAP,
///    IMMEDIATELY BEFORE the connect flow. A privacy policy does not count and
///    neither does a sentence somebody saw once at install. So this is modelled
///    per ATTEMPT, not per install: a second connect needs a second tap, and an
///    acknowledgement that has been left behind — the app backgrounded, the
///    owner changed, two minutes gone by — is gone.
///
/// 3. `callbackURL` / `parseDone` — our deep link, `anticipy://connected/…`.
///    A custom scheme is reachable by ANYONE: any web page, any other app, a
///    QR code on a poster. So the parse is a floor. It refuses a callback with
///    no attempt in flight, a callback for a toolkit we did not start, a
///    callback for another attempt, a callback for another owner and a
///    callback that arrives after the attempt could still be alive. And even
///    when it says `.connected`, THAT IS A HINT AND NOT A RECORD: it means
///    "stop waiting and go ask the server what this owner has connected". The
///    truth about a connection is a row on the server, keyed by the owner id,
///    and nothing arriving through a URL may write it.
///
/// 4. `connectLinkIsOurs` — the app opens `https://anticipy.ai/c/…` and
///    nothing else. This is an ALLOWLIST, not a list of vendors to block: a
///    blocklist is one new hostname from being wrong, and the spec's first
///    rule is that WE own the ask. A raw provider link reaching this function
///    is a defect upstream — it means a link was minted somewhere it should
///    not have been — so it is refused and reported by code rather than
///    silently opened.
///
/// ── WHAT THE DONE PAGE OWES THIS FILE ───────────────────────────────────
///
/// The connect page redirects to `callbackURL(for:)`, which already carries
/// `state={attempt id}`. Preserve that query when appending `status` and
/// `connected_account_id` and the callback is bound to one attempt exactly; a
/// page that rebuilds the URL and drops it still parses, but then the binding
/// is only "an attempt for this app is in flight, minted less than ten minutes
/// ago, for the owner signed in right now". That is the residual, written down
/// rather than assumed, and it is why `.connected` is a hint that starts a
/// refresh rather than a row anybody writes.
///
/// ── THE WRONG-PERSON RULE, WHICH IS WHAT THE SHAPE IS FOR ───────────────
///
/// During the spike one operator's own mailbox was connected by hand to prove
/// a key worked. It was revoked and deleted, and the contract file next door
/// carries the rule it produced: `THE USER ID IS THE OWNER ROW ID, ALWAYS, AND
/// NEVER A NAME`. Here that becomes three things a caller cannot skip:
///
///   * an attempt cannot be constructed without a well-formed owner row id, so
///     a signed-out device — whose `ownerID` is a device UUID, not an account —
///     cannot begin one at all;
///   * every entry point takes the CURRENTLY signed-in owner as its own
///     argument and refuses when the attempt was minted for somebody else, so
///     an attempt that outlived a sign-out is dead;
///   * the callback URL we hand over carries an opaque attempt id and NEVER
///     the owner id, because that URL is read by another company's server.
///
/// ── LAW 1 ────────────────────────────────────────────────────────────────
///
/// Nothing here decides what a human's words mean. WHICH app the owner meant —
/// "my Outlook", "office mail", "my work email" — is a model's question and it
/// is answered against the catalog by `ToolkitJudge` in the server contract.
/// This file is handed a slug it never chose. What it pattern-matches is
/// structure only: the shape of an identifier, the scheme and host of a URL,
/// and the machine tokens of a status field WE mint on OUR OWN done page.
/// That is HARNESS-LAWS Law 1's "senses and transport" clause, and if a future
/// edit here starts reading prose, it has left this clause.
///
/// NO APP IS NAMED IN THIS FILE, and the suite checks that too: names, logos
/// and permission words come from the catalog at run time, so a new app in the
/// catalog is a new app in Anticipy with zero code.
///
/// ── POLARITY ─────────────────────────────────────────────────────────────
///
/// Every decision here is a FLOOR. Nothing missing, unreadable, stale or
/// unmatched ever opens a browser or marks anything connected. There is no
/// state that means "proceed because nothing objected".
enum ConnectHandoff {

    // MARK: - The vocabulary, declared once

    /// Our deep link: `anticipy://connected/{toolkit}`. The scheme is already
    /// registered (`CFBundleURLTypes`, shared with the widget's doorbell), and
    /// the host is what separates a connect callback from every other knock.
    static let callbackScheme = "anticipy"
    static let callbackHost = "connected"

    /// THE ONLY HOSTS A CONNECT LINK MAY LIVE ON. One entry, an allowlist, and
    /// widening it is a visible diff that the runner's census leg reads out of
    /// this literal — the spec's first rule ("never the raw provider or Google
    /// URL") is one added hostname away from being false.
    static let connectLinkHosts: Set<String> = ["anticipy.ai"]

    /// `https://anticipy.ai/c/{token}` — single use, ten minutes, bound to one
    /// owner and one toolkit on the server side.
    static let connectLinkPathSegment = "c"

    /// The done page's machine tokens. These are OURS: our page mints them and
    /// this parses them, so they are transport, not language. An unknown token
    /// is unreadable rather than assumed.
    static let statusKey = "status"
    static let accountIdKey = "connected_account_id"
    static let reasonKey = "reason"
    static let stateKey = "state"
    static let statusConnected = "connected"
    static let statusCancelled = "cancelled"
    static let statusFailed = "failed"

    /// What `.failed` carries when the page said nothing about why. It is a
    /// journal token in every case — see `ConnectDone.failed`.
    static let unspecifiedReason = "unspecified"

    /// Ten minutes, matching `LINK_TTL_MS` in the server contract: our token
    /// dies then, and the provider's own link dies in ten minutes too. An
    /// attempt older than that cannot still be in flight, so a callback naming
    /// it is either very late or not from the owner at all.
    static let attemptLifetime: TimeInterval = 10 * 60

    /// The owner row id's shape, mirroring `ownerId()` in the server contract:
    /// fifteen lowercase alphanumerics. An email, a display name or a device
    /// UUID reaching an owner argument means a caller has confused "who is
    /// this" with "what do we call them", and the connection would bind to the
    /// wrong person.
    static let ownerRefLength = 15

    static let maxToolkitLength = 64
    static let maxAccountIdLength = 128
    static let maxReasonLength = 120
    static let maxTokenLength = 256

    // MARK: - Identifier shapes

    /// The signed-in owner's row id, canonicalised, or nil.
    static func ownerRef(_ raw: String) -> String? {
        let id = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard id.count == ownerRefLength else { return nil }
        for scalar in id.unicodeScalars where !isLowerAlphanumeric(scalar) { return nil }
        return id
    }

    /// A catalog slug, canonicalised, or nil. This says whether a string is
    /// SHAPED like a slug — never whether it is an app anyone has heard of.
    static func toolkitSlug(_ raw: String) -> String? {
        let slug = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !slug.isEmpty, slug.count <= maxToolkitLength else { return nil }
        for scalar in slug.unicodeScalars {
            let ok = isLowerAlphanumeric(scalar) || scalar == "_" || scalar == "-"
            if !ok { return nil }
        }
        return slug
    }

    /// An opaque identifier from somewhere else — our own attempt id, our link
    /// token, the provider's account id. We never read one; we only carry it,
    /// so the only questions asked are "is it there", "is it bounded" and "is
    /// it free of the characters that make a string dangerous to log, compare
    /// or put back in a URL".
    static func isOpaqueToken(_ raw: String, max: Int) -> Bool {
        guard !raw.isEmpty, raw.count <= max else { return false }
        for scalar in raw.unicodeScalars {
            let ok = isLowerAlphanumeric(scalar)
                || (scalar.value >= 65 && scalar.value <= 90)
                || scalar == "_" || scalar == "-" || scalar == "." || scalar == "~"
                || scalar == ":" || scalar == "%"
            if !ok { return false }
        }
        return true
    }

    private static func isLowerAlphanumeric(_ scalar: Unicode.Scalar) -> Bool {
        (scalar.value >= 97 && scalar.value <= 122) || (scalar.value >= 48 && scalar.value <= 57)
    }

    // MARK: - Is this link ours?

    static func inspect(link: URL) -> ConnectLinkVerdict {
        guard let parts = URLComponents(url: link, resolvingAgainstBaseURL: false) else {
            return .notOurs(.linkNotOurs)
        }
        // https only. A connect link is a credential in transit; there is no
        // version of this that may travel in the clear.
        guard parts.scheme?.lowercased() == "https" else { return .notOurs(.linkNotOurs) }
        // Exact host, so `anticipy.ai.example.com` and `example.com/anticipy.ai`
        // are both strangers. Nothing about a suffix or a substring is asked.
        guard let host = parts.host?.lowercased(), connectLinkHosts.contains(host) else {
            return .notOurs(.linkNotOurs)
        }
        // Credentials in the authority or a non-default port are shapes our own
        // links never have, and both are classic ways to make a URL read as one
        // host and resolve as another.
        guard parts.user == nil, parts.password == nil, parts.port == nil else {
            return .notOurs(.linkNotOurs)
        }
        let segments = parts.path.split(separator: "/", omittingEmptySubsequences: true)
        guard let first = segments.first, first == connectLinkPathSegment else {
            return .notOurs(.linkNotOurs)
        }
        // Our host and our path with nothing usable on the end is a link built
        // wrong at OUR end. It is reported as ours-and-empty rather than as a
        // stranger, so the two do not read alike in the journal.
        guard segments.count == 2 else {
            return .notOurs(segments.count == 1 ? .linkTokenMissing : .linkNotOurs)
        }
        let token = String(segments[1])
        guard isOpaqueToken(token, max: maxTokenLength) else { return .notOurs(.linkTokenMissing) }
        return .ours(token: token)
    }

    /// The plain question the caller asks before opening anything.
    static func connectLinkIsOurs(url: URL) -> Bool {
        if case .ours = inspect(link: url) { return true }
        return false
    }

    // MARK: - How it opens

    /// The one door. It answers "may this open, and how" in a single pass, and
    /// on a yes it SPENDS the disclosure acknowledgement on the way out — which
    /// is why `gate` is `inout`. A caller cannot obtain an opening decision
    /// without consuming the tap that licensed it, so "the second connect needs
    /// a second acknowledgement" is enforced here rather than by a view
    /// remembering to call something afterwards.
    ///
    /// - Parameter authSessionAvailable: whether the platform can present the
    ///   system sign-in session right now — a foreground window to anchor on,
    ///   on an OS that has the type. The view knows this; the policy does not
    ///   guess it. False means the system browser, never an embedded one.
    static func presentation(for link: URL,
                             attempt: ConnectAttempt,
                             signedInOwner: String,
                             gate: inout DisclosureGate,
                             now: Date,
                             authSessionAvailable: Bool) -> ConnectPresentation {
        guard let owner = ownerRef(signedInOwner) else { return .refused(.notAnOwnerId) }
        guard attempt.owner == owner else { return .refused(.attemptIsForAnotherOwner) }
        guard attempt.isFresh(at: now) else { return .refused(.attemptExpired) }
        // Reported, not swallowed: a provider's own link arriving here means one
        // was minted somewhere the spec forbids, and the refusal carries the
        // code that says so.
        switch inspect(link: link) {
        case .notOurs(let why): return .refused(why)
        case .ours: break
        }
        if case .refused(let why) = gate.verdict(for: attempt, now: now) {
            return .refused(why)
        }
        // Spent here, before the URL leaves. Whatever happens next — the app
        // backgrounds, the session is dismissed, the owner comes back an hour
        // later — the next connect starts from no acknowledgement at all.
        gate.handedOver(attempt)
        return authSessionAvailable
            ? .authSession(url: link, callbackScheme: callbackScheme)
            : .systemBrowser(url: link)
    }

    // MARK: - Coming back

    /// The callback we hand to the connect page. It carries the attempt id as
    /// opaque state and NOTHING ELSE — no owner id, no email, no alias. Another
    /// company's server reads this URL.
    static func callbackURL(for attempt: ConnectAttempt) -> URL? {
        var parts = URLComponents()
        parts.scheme = callbackScheme
        parts.host = callbackHost
        parts.path = "/" + attempt.toolkit
        parts.queryItems = [URLQueryItem(name: stateKey, value: attempt.id)]
        return parts.url
    }

    /// What a deep link means, in four states and never in three.
    ///
    /// `attempt` is what this phone believes is in flight, and nil is the
    /// normal case for a link nobody asked for. `signedInOwner` is who is on
    /// the phone AT THIS MOMENT, which is not necessarily who the attempt was
    /// minted for.
    static func parseDone(url: URL,
                          attempt: ConnectAttempt?,
                          signedInOwner: String,
                          now: Date) -> ConnectDone {
        // No attempt, no callback. This is the leg that stops a link on a web
        // page from marking an arbitrary app connected on somebody's phone.
        guard let attempt else { return .unreadable(.noAttemptInFlight) }
        guard let owner = ownerRef(signedInOwner) else { return .unreadable(.notAnOwnerId) }
        guard attempt.owner == owner else { return .unreadable(.attemptIsForAnotherOwner) }
        guard attempt.isFresh(at: now) else { return .unreadable(.attemptExpired) }

        guard let parts = URLComponents(url: url, resolvingAgainstBaseURL: false),
              parts.scheme?.lowercased() == callbackScheme,
              parts.host?.lowercased() == callbackHost else {
            return .unreadable(.callbackIsNotOurs)
        }
        let segments = parts.path.split(separator: "/", omittingEmptySubsequences: true)
        guard segments.count == 1, let toolkit = toolkitSlug(String(segments[0])) else {
            return .unreadable(.callbackShapeUnreadable)
        }
        guard toolkit == attempt.toolkit else { return .unreadable(.callbackToolkitMismatch) }

        // A repeated key is not a typo. `status=cancelled&status=connected`
        // reads whichever way the reader happens to look, so neither.
        let items = parts.queryItems ?? []
        func single(_ key: String) -> QueryRead {
            let hits = items.filter { $0.name == key }
            if hits.count > 1 { return .repeated }
            guard let value = hits.first?.value else { return .absent }
            return .one(value)
        }
        for key in [statusKey, accountIdKey, reasonKey, stateKey] {
            if case .repeated = single(key) { return .unreadable(.callbackShapeUnreadable) }
        }
        // The state rides on the callback URL we handed over, so a page that
        // redirects to it gets it back for free. When it comes back it must be
        // ours; when it does not come back the three checks above still stand.
        if case .one(let state) = single(stateKey), state != attempt.id {
            return .unreadable(.callbackIsForAnotherAttempt)
        }

        guard case .one(let rawStatus) = single(statusKey) else {
            return .unreadable(.callbackStatusUnknown)
        }
        switch rawStatus.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case statusConnected:
            guard case .one(let rawId) = single(accountIdKey) else {
                return .unreadable(.callbackAccountIdMissing)
            }
            let accountId = rawId.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !accountId.isEmpty else { return .unreadable(.callbackAccountIdMissing) }
            guard isOpaqueToken(accountId, max: maxAccountIdLength) else {
                return .unreadable(.callbackAccountIdUnusable)
            }
            // The toolkit reported is OUR canonical slug, not the one off the
            // URL: they are equal by the check above, and returning ours means
            // no caller ever writes a row keyed by a string a stranger chose.
            return .connected(toolkit: attempt.toolkit, accountId: accountId)
        case statusCancelled:
            return .cancelled
        case statusFailed:
            guard case .one(let rawReason) = single(reasonKey) else {
                return .failed(reason: unspecifiedReason)
            }
            return .failed(reason: journalReason(rawReason))
        default:
            return .unreadable(.callbackStatusUnknown)
        }
    }

    private enum QueryRead {
        case absent
        case one(String)
        case repeated
    }

    /// Bounded, control-character-free, and for the journal. See
    /// `ConnectDone.failed`.
    private static func journalReason(_ raw: String) -> String {
        let cleaned = raw.unicodeScalars
            .filter { !CharacterSet.controlCharacters.contains($0) }
            .map(String.init)
            .joined()
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if cleaned.isEmpty { return unspecifiedReason }
        return String(cleaned.prefix(maxReasonLength))
    }
}

// MARK: - The attempt

/// ONE connect, from the tap that started it to the callback that ends it.
///
/// It cannot be constructed for a name, an email or a signed-out device: the
/// owner must be a row id, which is the whole of the wrong-person rule stated
/// as a type. `id` is minted BEFORE anything happens — the same argument
/// `CalendarHandPolicy` makes about an id that exists before the act — so the
/// callback can be bound to it without asking the other side for anything.
struct ConnectAttempt: Equatable {
    let id: String
    let owner: String
    let toolkit: String
    let startedAt: Date

    init?(id: String, owner: String, toolkit: String, startedAt: Date) {
        guard let owner = ConnectHandoff.ownerRef(owner),
              let toolkit = ConnectHandoff.toolkitSlug(toolkit),
              ConnectHandoff.isOpaqueToken(id, max: ConnectHandoff.maxTokenLength) else {
            return nil
        }
        self.id = id
        self.owner = owner
        self.toolkit = toolkit
        self.startedAt = startedAt
    }

    /// The normal entry point. `id` is injectable so a suite can be exact
    /// about it; nothing else may pass one in.
    static func begin(owner: String,
                      toolkit: String,
                      now: Date,
                      id: String = UUID().uuidString) -> ConnectAttempt? {
        ConnectAttempt(id: id, owner: owner, toolkit: toolkit, startedAt: now)
    }

    /// A clock that ran backwards is as suspicious as one that ran too far.
    func isFresh(at now: Date) -> Bool {
        let age = now.timeIntervalSince(startedAt)
        return age >= 0 && age <= ConnectHandoff.attemptLifetime
    }
}

// MARK: - The disclosure

/// THE IN-CONTEXT DISCLOSURE, per attempt.
///
/// Google's Workspace policy asks for the owner to be told what will be read,
/// in context, and to take a real affirmative action, immediately before the
/// sign-in flow. Three things follow that a per-install flag cannot do:
///
///   * the sheet must have been SHOWN before it can be acknowledged, so a tap
///     cannot be recorded for something never put on screen;
///   * the acknowledgement is spent when the link is handed over, so the next
///     connect starts from nothing;
///   * it does not survive the app leaving the screen, the owner changing, or
///     `freshness` elapsing — because "immediately before" is the whole
///     requirement, and an acknowledgement found lying around afterwards would
///     let a connect start that nobody watched begin.
///
/// The COPY on that sheet is the view's, and it is rendered from the catalog's
/// own metadata — the permission sentences come from the toolkit's scopes, not
/// from anything typed in Swift. Nothing about an app is named here.
struct DisclosureGate: Equatable {

    /// How long a step of the sequence may sit. Two minutes is long enough to
    /// read a short sheet and short enough that nothing found on a phone
    /// picked up later is still valid. It bounds a gesture, not a meaning.
    static let freshness: TimeInterval = 120

    enum Stage: Equatable {
        case nothingShown
        case shown(attempt: ConnectAttempt, at: Date)
        case acknowledged(attempt: ConnectAttempt, at: Date)
    }

    enum Verdict: Equatable {
        case mayPresent
        case refused(ConnectRefusal)
    }

    private(set) var stage: Stage = .nothingShown

    init() {}

    /// The view put the disclosure on screen for this attempt. A new attempt
    /// replaces whatever was there: only one connect is ever in front of the
    /// owner.
    mutating func disclosureShown(for attempt: ConnectAttempt, now: Date) {
        stage = .shown(attempt: attempt, at: now)
    }

    /// The owner tapped. True when that tap counted.
    @discardableResult
    mutating func acknowledge(_ attempt: ConnectAttempt, now: Date) -> Bool {
        guard case .shown(let shownFor, let shownAt) = stage,
              shownFor == attempt,
              fresh(shownAt, now) else {
            return false
        }
        stage = .acknowledged(attempt: attempt, at: now)
        return true
    }

    func verdict(for attempt: ConnectAttempt, now: Date) -> Verdict {
        switch stage {
        case .nothingShown:
            return .refused(.disclosureNotShown)
        case .shown:
            return .refused(.disclosureNotAcknowledged)
        case .acknowledged(let acknowledgedFor, let at):
            guard acknowledgedFor == attempt else {
                return .refused(.disclosureIsForAnotherAttempt)
            }
            guard fresh(at, now) else { return .refused(.disclosureIsStale) }
            return .mayPresent
        }
    }

    /// The plain question, for a caller that only wants the yes or no.
    func canPresentConnect(_ attempt: ConnectAttempt, now: Date) -> Bool {
        verdict(for: attempt, now: now) == .mayPresent
    }

    /// Spent. Called by `ConnectHandoff.presentation` as the link goes out.
    mutating func handedOver(_ attempt: ConnectAttempt) {
        if case .acknowledged(let acknowledgedFor, _) = stage, acknowledgedFor == attempt {
            stage = .nothingShown
        }
    }

    /// The app left the screen with a disclosure still unspent. Whatever the
    /// owner was looking at, they are not looking at it now.
    mutating func appMovedToBackground() {
        stage = .nothingShown
    }

    /// A different person is signed in, or nobody is. Nothing this gate holds
    /// belongs to them.
    mutating func ownerChanged() {
        stage = .nothingShown
    }

    private func fresh(_ at: Date, _ now: Date) -> Bool {
        let age = now.timeIntervalSince(at)
        return age >= 0 && age <= DisclosureGate.freshness
    }
}

// MARK: - The three answers

/// HOW A CONNECT LINK OPENS. Two of these open something, and both of them are
/// a real browser the person can see the address bar of. The third opens
/// nothing.
///
/// There is no case here for an embedded web view, and adding one would not be
/// a feature flag or a fallback — it is how the connect stops working, because
/// Google refuses a sign-in inside one. The runner counts these cases and the
/// suite reads this file's source for the class names, so the absence is
/// checked twice and by two different means.
enum ConnectPresentation: Equatable {
    /// The system sign-in session — `ASWebAuthenticationSession`, holding our
    /// callback scheme. Preferred: the result comes back to the caller
    /// directly, so a connect that finishes while the app is on screen never
    /// has to travel back through the deep link at all.
    case authSession(url: URL, callbackScheme: String)
    /// The system browser. The callback returns as a deep link, which
    /// `parseDone` treats as what it is: attacker-reachable.
    case systemBrowser(url: URL)
    /// Nothing opens, and the code says why.
    case refused(ConnectRefusal)
}

/// WHAT A DEEP LINK MEANT. Four states, because "it did not connect", "they
/// backed out", "we cannot read this" and "it connected" are four different
/// things and no smaller answer keeps them apart.
enum ConnectDone: Equatable {
    /// The other side says this owner's account is attached. It is a HINT: the
    /// caller refreshes the owner's connections from the server and believes
    /// THAT. Nothing arriving through a URL writes a connection row.
    case connected(toolkit: String, accountId: String)
    /// They backed out. Not a failure, not a decline — the nudge state machine
    /// is the only thing that decides what a back-out costs.
    case cancelled
    /// It went wrong. `reason` is a token FOR THE JOURNAL and must never be put
    /// on screen: it is written by another company's server and may name that
    /// company, or its sign-in protocol, in words the spec forbids the owner
    /// from ever seeing. The screen gets a sentence the view writes.
    case failed(reason: String)
    /// Nothing here can be acted on — including a perfectly well-formed URL
    /// that belongs to another attempt, another owner, another app, or to no
    /// attempt at all.
    case unreadable(ConnectRefusal)
}

/// Is a link ours to open, and if not, what do we report?
enum ConnectLinkVerdict: Equatable {
    case ours(token: String)
    case notOurs(ConnectRefusal)
}

/// EVERY WAY THE HANDOFF SAYS NO, each with its own code for the journal.
///
/// No case carries an associated value, on purpose: that makes the enum
/// `CaseIterable`, so the census the suite runs is the compiler's rather than
/// a list somebody types and forgets — which is exactly how two refusal causes
/// in `CalendarHandPolicy` came to share one code.
enum ConnectRefusal: String, CaseIterable, Equatable {
    /// The identity on this phone is not an owner row id — a signed-out
    /// device, a display name, an email, a legacy device UUID.
    case notAnOwnerId = "connect.not_an_owner_id"
    /// The attempt was minted for a different owner than the one signed in now.
    case attemptIsForAnotherOwner = "connect.attempt_is_for_another_owner"
    /// Older than the link could possibly still be alive for.
    case attemptExpired = "connect.attempt_expired"
    /// The URL to open is not one of ours. A provider's own link reaching this
    /// point is a defect upstream, and this code is how it gets reported.
    case linkNotOurs = "connect.link_not_ours"
    /// Our host and our path, and no token we can carry — absent, over-long,
    /// or holding characters our own tokens never have.
    case linkTokenMissing = "connect.link_token_missing"
    /// The disclosure was never put on screen for this attempt.
    case disclosureNotShown = "connect.disclosure_not_shown"
    /// It was shown and nobody tapped.
    case disclosureNotAcknowledged = "connect.disclosure_not_acknowledged"
    /// It was acknowledged, for something else.
    case disclosureIsForAnotherAttempt = "connect.disclosure_is_for_another_attempt"
    /// It was acknowledged too long ago to still be "immediately before".
    case disclosureIsStale = "connect.disclosure_is_stale"
    /// A callback arrived with nothing in flight.
    case noAttemptInFlight = "connect.no_attempt_in_flight"
    /// Not our scheme, or not our host.
    case callbackIsNotOurs = "connect.callback_is_not_ours"
    /// Our scheme and host, a shape we do not mint.
    case callbackShapeUnreadable = "connect.callback_shape_unreadable"
    /// A callback for an app we did not start.
    case callbackToolkitMismatch = "connect.callback_toolkit_mismatch"
    /// A callback whose state is not the attempt's.
    case callbackIsForAnotherAttempt = "connect.callback_is_for_another_attempt"
    /// A status token our own page does not mint.
    case callbackStatusUnknown = "connect.callback_status_unknown"
    /// Said connected, named no account.
    case callbackAccountIdMissing = "connect.callback_account_id_missing"
    /// Named an account we will not carry.
    case callbackAccountIdUnusable = "connect.callback_account_id_unusable"

    /// The journal code. Identical to the raw value, named so call sites read
    /// as what they are.
    var code: String { rawValue }
}
