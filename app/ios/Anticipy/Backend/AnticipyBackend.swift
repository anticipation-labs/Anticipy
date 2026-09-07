import Foundation

/// Resolve a field shared by the account and its editable profile. `nil`
/// means no profile row exists; `""` means one exists and explicitly holds an
/// empty value. Using `isEmpty` here would resurrect signup-era contact data.
enum OwnerProfileCanonical {
    static func value(profileValue: String?, accountValue: String) -> String {
        profileValue ?? accountValue
    }
}

/// Pure pagination/verdict seams for browser unaffiliation. Twenty-one rows
/// must mean two pages, and one refused PATCH must make the whole operation a
/// failure even if every other browser was released.
enum AgentUnpairPolicy {
    static func pages(totalPages: Int) -> [Int] {
        guard totalPages > 0 else { return [] }
        return Array(1...totalPages)
    }

    static func succeeded(patchResults: [Bool], remainingRows: Int) -> Bool {
        !patchResults.isEmpty
            ? patchResults.allSatisfy { $0 } && remainingRows == 0
            : remainingRows == 0
    }
}

/// A browser-agent job as stored in the backend. The Chrome extension claims
/// queued jobs, runs them, and reports status/result back here.
struct AgentJob: Identifiable, Decodable, Equatable {
    let id: String
    let goal: String
    let params: String
    let status: String // queued | running | awaiting_confirm | done | failed | cancelled
    let result: String?
    let created: String
    /// PocketBase's last-write timestamp. A terminal shelf is about when work
    /// ended, not when it was first requested, so Home uses this when ordering
    /// completed cards and falls back to `created` for legacy rows.
    let updated: String?
    let workflow_id: String?
    let workflow_version: Int?
    let workflow_state: String?
    let consequence: String?
    let approval: String?
    let scope_digest: String?
    let effect_key: String?
    let effect_uncertain: Bool?
    let reconciliation: String?
    /// Which arm is going to run this. "" or absent = the browser lane,
    /// "research" = the worker, "supervised_read" = the browser WITH the person
    /// watching (`design/day-zero.md` §2).
    ///
    /// Decoded because the feed has to tell the last one apart from an errand:
    /// a read somebody is watching happen must never also appear under "Waiting
    /// for your browser" as though it were stalled. The alternative was
    /// sniffing the `params` JSON string, which is how a display bug becomes a
    /// parsing bug.
    let lane: String?

    /// THE EVIDENCE THE SERVER ITSELF CHECKED, as the row holds it.
    ///
    /// `backend/pb_hooks/workflow_guard.pb.js` refuses to mark ANY job done
    /// unless this column parses and carries `verified: true` with a non-empty
    /// `evidence`. The app never decoded it. So the done card led with
    /// `result` — free text the extension composed — while the one thing that
    /// had actually been verified sat unread in the same row, and a stranger
    /// had no way to tell a receipt from a sentence, which is the entire
    /// promise of that card.
    ///
    /// A `String?` because the column is JSON and the phone is not the place to
    /// decide what a malformed receipt means; `JobReceipt.parse` turns it into
    /// something typed, or into nothing.
    let receipt: String?

    init(id: String, goal: String, params: String, status: String,
         result: String?, created: String, updated: String? = nil,
         workflow_id: String? = nil,
         workflow_version: Int? = nil, workflow_state: String? = nil,
         consequence: String? = nil, approval: String? = nil,
         scope_digest: String? = nil, effect_key: String? = nil,
         effect_uncertain: Bool? = nil,
         reconciliation: String? = nil, lane: String? = nil,
         receipt: String? = nil) {
        self.id = id; self.goal = goal; self.params = params; self.status = status
        self.result = result; self.created = created; self.updated = updated
        self.workflow_id = workflow_id
        self.workflow_version = workflow_version; self.workflow_state = workflow_state
        self.consequence = consequence; self.approval = approval
        self.scope_digest = scope_digest; self.effect_key = effect_key
        self.effect_uncertain = effect_uncertain
        self.reconciliation = reconciliation
        self.lane = lane
        self.receipt = receipt
    }

    /// The same job with one field replaced.
    ///
    /// Every property here is `let` on purpose - a job is a value, and nothing
    /// on the phone gets to decide what a job's state is. This exists for the
    /// one legitimate exception: `AnticipySession` holds a status the server has
    /// ALREADY CONFIRMED over the feed until a later fetch agrees with it,
    /// because the read is a separate request and can still return the pre-write
    /// row. A named copy keeps that the only way to do it - a `var status` would
    /// let any view invent a state instead.
    func withStatus(_ status: String) -> AgentJob {
        AgentJob(id: id, goal: goal, params: params, status: status,
                 result: result, created: created, updated: updated,
                 workflow_id: workflow_id,
                 workflow_version: workflow_version, workflow_state: workflow_state,
                 consequence: consequence, approval: approval,
                 scope_digest: scope_digest, effect_key: effect_key,
                 effect_uncertain: effect_uncertain,
                 reconciliation: reconciliation, lane: lane, receipt: receipt)
    }
}

/// A registered browser-agent (Chrome extension install). `lastSeen` is its
/// heartbeat — the app renders it as "last seen Ns ago".
struct BrowserAgent: Decodable, Equatable {
    let id: String
    let agent_id: String
    let owner: String?
    let owner_ref: String?
    let paired: Bool?
    let last_seen: String?
    let browser: String?
}

/// One brain event: a transcript line, the brain's decision on it, or
/// something Anticipy said/texted.
struct BrainEvent: Decodable, Identifiable, Equatable {
    let id: String
    let kind: String // transcript | decision | anticipy_says | anticipy_text
    let text: String?
    let decision: String?
    let goal: String?
    let created: String
    /// The conversation this turn belongs to, stamped by the brain's segmenter
    /// when it places the turn. Absent (nil) on rows written before the
    /// segmenter existed, and empty ("") on any turn it failed to place or when
    /// segmenting is switched off — in which case the feed groups nothing and
    /// renders exactly as it does today.
    let segment: String?
    /// WHO SAID IT: "owner", "other", or absent when the phone could not say.
    ///
    /// `SpeakerTagger` has stamped this on every pushed line since the field
    /// existed, and the column is in the wire map — but nothing ever DECODED it,
    /// so every line in the app arrived anonymous and the feed drew one
    /// continuous bubble as though a single person had said all of it. In a
    /// room with two people that is not a transcript, it is a fabrication.
    ///
    /// "unknown" never travels: the tagger sends nothing rather than claim
    /// somebody, and a missing field means the same thing here.
    let speaker: String?
    /// WHICH EARS heard this line: "phone_mic", "pendant" or "typed".
    ///
    /// The phone has stamped this on every event it pushes since the field was
    /// added (`pushEvent(source:)`), and until now nothing ever read it back —
    /// so the one comparison the field exists for, the pendant run of an errand
    /// against the phone-mic run of the same errand, was invisible in the app
    /// that produced both. Optional, and empty on the thousands of rows written
    /// before anything wrote it: absent means "no verdict", never "typed".
    let source: String?
    /// Stable link back to the outside record that caused this event. Worker
    /// job receipts use `job-result:<job id>` so Home can avoid presenting the
    /// same completed work once as a Done card and again as a recap.
    let external_event_id: String?
}

/// One PocketBase page of events, including the server's own pagination
/// boundary. History reads this instead of guessing that a short page was the
/// end or pretending the Home poll window is an archive.
struct BrainEventPage: Decodable, Equatable {
    let page: Int
    let perPage: Int
    let totalItems: Int
    let totalPages: Int
    let items: [BrainEvent]
}

/// Thin client for the Anticipy PocketBase backend (pairing, events, jobs).
/// Endpoints proven live in proof/test_backend.py and proof/test_extension.py.
final class AnticipyBackend {
    var baseURL: URL
    let deviceID: String
    /// The signed-in person's session token, when there is one.
    var authToken: String

    init(baseURL: URL, deviceID: String, authToken: String = "",
         accountID: String = "") {
        self.baseURL = baseURL
        self.deviceID = deviceID
        self.authToken = authToken
        self.accountID = accountID
    }

    /// Customer devices authenticate only as the signed-in owner. The
    /// server-wide worker credential is never present in the app.
    private func authorize(_ r: inout URLRequest) {
        if !authToken.isEmpty {
            r.setValue(authToken, forHTTPHeaderField: "Authorization")
        }
    }

    /// Reads carry the token too — the guard hook protects the whole data
    /// API, not just writes.
    ///
    /// A non-2xx read THROWS. It used to hand the body of a 403 back as if it
    /// were data; every caller then swallowed the decode failure with `try?`,
    /// so a refused read was indistinguishable from "you have nothing yet" and
    /// the app confidently painted an empty screen.
    private func readData(from url: URL) async throws -> Data {
        var r = URLRequest(url: url)
        authorize(&r)
        let (data, resp) = try await URLSession.shared.data(for: r)
        if let http = resp as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw BackendError(status: http.statusCode)
        }
        return data
    }

    /// Every write goes through here, so none of them can report success for a
    /// request the server refused. Four call sites used to do
    /// `_ = try await URLSession.shared.data(for:)` and then `return true`.
    @discardableResult
    private func send(_ request: URLRequest) async throws -> Data {
        let (data, resp) = try await URLSession.shared.data(for: request)
        if let http = resp as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw BackendError(status: http.statusCode,
                               message: Self.serverMessage(data))
        }
        return data
    }

    /// The server's own sentence, when it wrote one. The hooks answer refusals
    /// in real English — "Pick a password with at least 8 characters.",
    /// "Something went wrong on my end." — and that body was being dropped on
    /// the floor here, which is why one screen could only ever recite a single
    /// canned reason for three different failures. Anything that isn't JSON
    /// with a `message` (an HTML 502 page from the proxy, an empty body) has
    /// nothing worth showing a person, so it stays nil.
    private static func serverMessage(_ data: Data) -> String? {
        guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let message = (root["message"] as? String)?
                  .trimmingCharacters(in: .whitespacesAndNewlines),
              !message.isEmpty else { return nil }
        return message
    }

    private func writeRequest(_ url: URL, method: String) -> URLRequest {
        var r = URLRequest(url: url)
        r.httpMethod = method
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        authorize(&r)
        return r
    }

    // NO transcriptionToken(). It exchanged the owner's session for a
    // short-lived speech-vendor JWT so the phone could open a websocket and
    // stream the pendant's raw Opus frames to a third party — design/
    // LOCAL-FIRST.md rule 1 broken by the one function that made it possible.
    //
    // The route still exists server-side and answers 410 GONE with its reason
    // (backend/pb_hooks/transcription_token.pb.js), because a deleted route
    // answers 404 and a 404 reads as "wrong URL" — something a client retries.
    // Nothing in this app calls it any more, so the refusal is a backstop
    // rather than a thing this file has to interpret.

    /// Who the server says this account is.
    ///
    /// Added because the phone had no way to ASK. Every owner field on the
    /// device is a write-only mirror: the app puts them there at sign-up and
    /// in Settings and never reads one back, so the same account on a second
    /// handset — or on the same handset after a reinstall — knew nothing about
    /// itself, and the screens that ask "can I reach you?" answered from the
    /// device rather than from the account.
    ///
    /// THE NUMBER LIVES IN TWO COLUMNS, and this is the whole reason this is
    /// not a one-line record fetch. `owners.phone` is what sign-up wrote and
    /// nothing updates again — Settings saves through `upsertOwnerPhone`,
    /// which writes `owner_profile`. And `owner_profile.phone` is the one that
    /// carries: it is the row an inbound text is routed through
    /// (backend/pb_hooks/sms.pb.js:167) and the row a live run refuses to
    /// start without (proof/live_day.py:105). So the profile answers when it
    /// has a number, and the account record answers for the accounts that have
    /// never been through Settings. Reading only the account record would hand
    /// back the number somebody replaced months ago and call it current.
    ///
    /// THROWS rather than returning an empty owner when it could not ask. The
    /// caller's decision turns on the difference: "" means the account has no
    /// number and the phone should stop claiming one, and a thrown error means
    /// nothing has been learned and nothing should change.
    func fetchOwner(id: String) async throws -> Owner {
        let data = try await readData(
            from: baseURL.appendingPathComponent("api/collections/owners/records/\(id)"))
        // A 200 carrying something this cannot parse is "I could not ask",
        // never "you have no number". Defaulting to [:] here would have made a
        // proxy's HTML error page read as an account with no phone on file and
        // wiped a good one — the same swallow, one layer down, that the rest of
        // this call is built to avoid.
        guard let root = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else {
            throw BackendError(status: -1)
        }
        let profile = try await savedProfile(ownerRef: id)
        let accountEmail = (root["email"] as? String) ?? ""
        let accountPhone = (root["phone"] as? String) ?? ""
        // Profile EXISTENCE is authoritative. In particular, an existing row
        // with phone "" means the number was removed; falling back by value
        // would resurrect the immutable signup-era owners.phone. The account
        // record seeds only accounts that have no profile row at all.
        return Owner(id: (root["id"] as? String) ?? id,
                     email: OwnerProfileCanonical.value(
                        profileValue: profile.map(\.email), accountValue: accountEmail),
                     phone: OwnerProfileCanonical.value(
                        profileValue: profile.map(\.phone), accountValue: accountPhone),
                     firstName: profile?.firstName ?? "",
                     lastName: profile?.lastName ?? "",
                     birthday: profile?.birthday ?? "")
    }

    private struct StoredOwnerProfile {
        let phone: String
        let firstName: String
        let lastName: String
        let email: String
        let birthday: String
    }

    /// The complete profile Settings last saved for this account. A missing row
    /// is a successful 200 with empty `items`; malformed or refused reads throw
    /// so the caller cannot erase good device mirrors because a proxy answered.
    private func savedProfile(ownerRef: String) async throws -> StoredOwnerProfile? {
        let listURL = baseURL.appendingPathComponent("api/collections/owner_profile/records")
        var comps = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
        let filter = "owner_ref=\"\(ownerRef)\""
        let encodedFilter = filter.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)!
        comps.percentEncodedQuery = "filter=\(encodedFilter)&sort=-updated&perPage=1"
        // Not `return ""`: an unbuildable URL is a failure to ask, and the one
        // thing this function may never do is report a number's absence for
        // any reason other than the server saying so.
        guard let url = comps.url else { throw BackendError(status: -1) }
        let data = try await readData(from: url)
        // A body with no `items` is not a profile row saying "no number" — it is
        // not a list answer at all, so nothing was learned. An EMPTY `items` is
        // the answer, and the difference matters: the second means this account
        // has never been through Settings, the first means a proxy or a captive
        // portal answered instead of the server, and `return ""` there would
        // have handed back the number sign-up wrote and called it current.
        guard let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let items = root["items"] as? [[String: Any]] else { throw BackendError(status: -1) }
        guard let item = items.first else { return nil }
        return StoredOwnerProfile(
            phone: (item["phone"] as? String) ?? "",
            firstName: (item["first_name"] as? String) ?? "",
            lastName: (item["last_name"] as? String) ?? "",
            email: (item["email"] as? String) ?? "",
            birthday: (item["birthday"] as? String) ?? "")
    }

    /// What the server holds about the person, as opposed to what this handset
    /// remembers about them.
    struct Owner {
        let id: String
        let email: String
        /// E.164, or "" when this account has no number anywhere on the server.
        /// Empty is an answer here, never a failure — `fetchOwner` throws for
        /// that.
        let phone: String
        let firstName: String
        let lastName: String
        let birthday: String
    }

    /// Store the owner's number where the brain reads it. Updates the
    /// existing row for this owner rather than piling up duplicates.
    func upsertOwnerPhone(ownerID: String, phone: String) async -> Bool {
        await upsertOwner(ownerID: ownerID, fields: ["phone": phone])
    }

    /// Atomically unaffiliate the signed-in person's number everywhere it can
    /// route: the immutable account seed and every owner_profile row. The hook
    /// performs and verifies that transaction; the session then rereads the
    /// canonical owner before presenting `.none`.
    func removeOwnerPhone() async -> Bool {
        guard !accountID.isEmpty else { return false }
        var request = writeRequest(
            baseURL.appendingPathComponent("me/phone/remove"), method: "POST")
        request.httpBody = Data("{}".utf8)
        guard let data = try? await send(request),
              let result = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              (result["ok"] as? Bool) == true,
              ((result["phone"] as? String) ?? "x").isEmpty,
              let cleared = result["clearedProfiles"] as? Int,
              cleared >= 0 else { return false }
        return true
    }

    /// Name and email too: every booking and signup form asks for the same
    /// four things, and without them a run reaches the form and stops.
    ///
    /// The server owns profile identity and performs the read/merge/write in a
    /// single transaction. A client-side list followed by POST/PATCH lets the
    /// independent phone and details saves both observe "no row" and race to
    /// create partial profiles. It also lets a device choose `owner_ref` or the
    /// legacy `owner_id`. This route derives ownership from the session token,
    /// preserves omitted fields, and treats an explicit empty string as clear.
    func upsertOwner(ownerID: String, fields: [String: String]) async -> Bool {
        guard !accountID.isEmpty else { return false }
        let editable = Set([
            "phone", "name", "first_name", "last_name", "email", "birthday",
            "facts", "timezone",
        ])
        guard fields.keys.allSatisfy(editable.contains) else { return false }

        var request = writeRequest(
            baseURL.appendingPathComponent("me/profile/upsert"), method: "POST")
        request.httpBody = try? JSONSerialization.data(withJSONObject: fields)
        guard request.httpBody != nil,
              let data = try? await send(request),
              let result = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              (result["ok"] as? Bool) == true,
              let profile = result["profile"] as? [String: Any],
              let profileID = profile["id"] as? String,
              !profileID.isEmpty,
              (profile["owner_ref"] as? String) == accountID else { return false }

        // A 2xx is not enough: the endpoint promises to echo the complete
        // canonical row, so verify that every value this request supplied made
        // it into that row. This also keeps a malformed proxy response from
        // painting "Saved" in Settings.
        return fields.allSatisfy { key, value in
            (profile[key] as? String) == value
        }
    }

    /// An error that carries the server's own sentence, so the screen can show
    /// what actually went wrong instead of a generic apology.
    struct MessageError: Error { let message: String }

    /// Why an account couldn't be created, by field, so the screen can say
    /// what is actually wrong instead of blaming the email for everything.
    struct CreateAccountError: Error {
        let status: Int
        let emailTaken: Bool
        let phoneTaken: Bool
        let deviceTaken: Bool
    }

    /// Create an account. `legacyUUID` is this device's pre-accounts identity,
    /// carried up so the person's existing rows can be claimed rather than
    /// orphaned.
    func createAccount(email: String, password: String,
                       phone: String?, legacyUUID: String) async throws {
        var req = writeRequest(
            baseURL.appendingPathComponent("api/collections/owners/records"), method: "POST")
        var body: [String: Any] = [
            "email": email.trimmingCharacters(in: .whitespaces).lowercased(),
            "password": password,
            "passwordConfirm": password,
            "legacy_uuid": legacyUUID,
        ]
        if let phone, !phone.isEmpty { body["phone"] = phone }
        req.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw BackendError(status: -1) }
        if (200..<300).contains(http.statusCode) { return }
        let root = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        let fields = (root?["data"] as? [String: Any]) ?? [:]
        throw CreateAccountError(status: http.statusCode,
                                 emailTaken: fields["email"] != nil,
                                 phoneTaken: fields["phone"] != nil,
                                 deviceTaken: fields["legacy_uuid"] != nil)
    }

    /// Sign in. Returns the session token and the account id.
    func authWithPassword(email: String, password: String) async throws -> (token: String, id: String) {
        var req = writeRequest(
            baseURL.appendingPathComponent("api/collections/owners/auth-with-password"),
            method: "POST")
        req.httpBody = try JSONSerialization.data(withJSONObject: [
            "identity": email.trimmingCharacters(in: .whitespaces).lowercased(),
            "password": password,
        ])
        let data = try await send(req)
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let token = root["token"] as? String,
              let record = root["record"] as? [String: Any],
              let id = record["id"] as? String
        else { throw BackendError(status: -1) }
        return (token, id)
    }

    /// Ask the server to delete everything it holds, and close the account.
    ///
    /// The STATUS is returned rather than swallowed, because this is the one
    /// call where "not quite" must not read as "done": 409 means the rows went
    /// but the account survived, 500 means something was left behind. The
    /// endpoint requires an explicit confirm so a replayed request from a stolen
    /// token cannot wipe an account on its own.
    func deleteAccount() async throws -> (status: Int, body: String) {
        var req = writeRequest(baseURL.appendingPathComponent("me/delete"), method: "POST")
        req.httpBody = try JSONSerialization.data(withJSONObject: ["confirm": "delete"])
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw BackendError(status: -1) }
        return (http.statusCode, String(data: data, encoding: .utf8) ?? "")
    }

    /// Adopt everything this device made before accounts existed onto the
    /// account that just signed in, so signing up never looks like losing your
    /// history.
    func claimLegacy(legacyUUID: String) async {
        var req = writeRequest(baseURL.appendingPathComponent("auth/claim"), method: "POST")
        req.httpBody = try? JSONSerialization.data(withJSONObject: ["legacy_uuid": legacyUUID])
        _ = try? await send(req)
    }

    /// "I forgot my password" — the code arrives by text, because this backend
    /// has no way to send mail.
    func requestPasswordReset(email: String) async throws {
        var req = writeRequest(baseURL.appendingPathComponent("auth/reset/request"), method: "POST")
        req.httpBody = try JSONSerialization.data(withJSONObject: [
            "email": email.trimmingCharacters(in: .whitespaces).lowercased()])
        try await send(req)
    }

    func confirmPasswordReset(email: String, code: String, password: String) async throws {
        var req = writeRequest(baseURL.appendingPathComponent("auth/reset/confirm"), method: "POST")
        req.httpBody = try JSONSerialization.data(withJSONObject: [
            "email": email.trimmingCharacters(in: .whitespaces).lowercased(),
            "code": code.trimmingCharacters(in: .whitespaces),
            "password": password,
        ])
        do {
            try await send(req)
        } catch let e as BackendError {
            // The reset route answers three different refusals with three
            // different sentences: the genuine bad code, "Pick a password with
            // at least 8 characters." (400), and "Something went wrong on my
            // end." (500, when the owners record fails to save). This line used
            // to recite the bad-code one for all three — so someone holding a
            // code that arrived seconds ago was told the code was wrong, went
            // back and asked for another, and after five requests in an hour
            // the throttle silently stopped texting anything at all. Locked
            // out, with every screen naming the wrong reason.
            throw MessageError(message: e.message
                ?? "That code isn't right, or it has expired. Ask for a new one.")
        }
    }

    /// Pair this app to a pendant using the short code the pendant registered.
    func pair(code: String, owner: String) async throws -> Bool {
        let filter = "pair_code=\"\(code)\"".addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)!
        let listURL = baseURL.appendingPathComponent("api/collections/pendants/records")
        var comps = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
        comps.percentEncodedQuery = "filter=\(filter)"
        let data = try await readData(from: comps.url!)
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let items = root["items"] as? [[String: Any]],
              let id = items.first?["id"] as? String else { return false }

        var patch = writeRequest(listURL.appendingPathComponent(id), method: "PATCH")
        guard !accountID.isEmpty else { throw BackendError(status: 401) }
        patch.httpBody = try JSONSerialization.data(withJSONObject: [
            "owner": owner, "owner_ref": accountID, "paired": true,
        ])
        try await send(patch)
        return true
    }

    /// Pair this phone to a browser agent using the 6-digit code the
    /// extension displays. Binds the agent to this owner; from then on it
    /// only claims this owner's jobs.
    ///
    /// Returns false ONLY when the code genuinely matched nothing. Anything
    /// else — no network, a refused write — throws, so the UI can tell "that
    /// code is wrong" apart from "I can't reach Anticipy right now". Telling
    /// someone their correct code is wrong is how they give up.
    func pairAgent(code: String, owner: String) async throws -> Bool {
        // A claim that names no owner would "succeed" into a record the
        // extension can never match a job against — the phone celebrates, the
        // browser stays an orphan. The backend now refuses blank owners too;
        // throwing here keeps the failure loud on this side as well.
        guard !owner.isEmpty else { throw BackendError(status: 400) }
        let listURL = baseURL.appendingPathComponent("api/collections/agents/records")
        let filter = "pair_code=\"\(code)\"".addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)!
        var comps = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
        comps.percentEncodedQuery = "filter=\(filter)"
        let data = try await readData(from: comps.url!)
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let items = root["items"] as? [[String: Any]],
              let id = items.first?["id"] as? String else { return false }

        var patch = writeRequest(listURL.appendingPathComponent(id), method: "PATCH")
        guard !accountID.isEmpty else { throw BackendError(status: 401) }
        patch.httpBody = try JSONSerialization.data(withJSONObject: [
            "owner": owner, "owner_ref": accountID, "paired": true,
        ])
        try await send(patch)

        // Trust the record, not the status code. On 2026-08-14 a claim was
        // answered politely while nothing persisted, the UI said nothing, and
        // the first real stranger sat un-paired with no error anywhere. Same
        // law as jobs: paired is illegal without evidence. Read it back.
        let verify = try await readData(from: listURL.appendingPathComponent(id))
        guard let saved = try JSONSerialization.jsonObject(with: verify) as? [String: Any],
              saved["owner"] as? String == owner,
              saved["paired"] as? Bool == true else {
            throw BackendError(status: 502)
        }
        return true
    }

    /// Release the browser this owner had paired, so the extension stops
    /// claiming a link the phone has let go of.
    ///
    /// The two sides answer "are we linked?" from different places — the
    /// extension from its own row, the phone from a lookup by owner id — and
    /// nothing kept them honest with each other. When the phone's identity
    /// rotated, the row kept the old id and both sides were correct and
    /// contradictory at once. Unpairing here is what makes disagreement
    /// impossible: the extension falls back to showing a pair code, which is
    /// the state a person can actually act on.
    @discardableResult
    func unpairAgent(owner: String) async -> Bool {
        guard !owner.isEmpty else { return true }
        let listURL = baseURL.appendingPathComponent("api/collections/agents/records")
        let rawFilter = accountID.isEmpty
            ? "owner=\"\(owner)\""
            : "owner_ref=\"\(accountID)\""
        let filter = rawFilter.addingPercentEncoding(
            withAllowedCharacters: .urlQueryAllowed)!
        // Snapshot every page BEFORE mutating any row. Paging a filtered list
        // while clearing the field in that filter shifts later rows toward page
        // one and can skip them. perPage=20 keeps the 21-row regression honest.
        var ids: [String] = []
        var page = 1
        var totalPages = 1
        repeat {
            var comps = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
            comps.percentEncodedQuery = "filter=\(filter)&perPage=20&page=\(page)"
            guard let url = comps.url,
                  let data = try? await readData(from: url),
                  let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let items = root["items"] as? [[String: Any]],
                  let pages = root["totalPages"] as? Int,
                  pages >= 0 else { return false }
            totalPages = pages
            for item in items {
                guard let id = item["id"] as? String, !id.isEmpty else { return false }
                ids.append(id)
            }
            page += 1
        } while AgentUnpairPolicy.pages(totalPages: totalPages).contains(page)
        guard Set(ids).count == ids.count else { return false }

        var patchResults: [Bool] = []
        for id in ids {
            var patch = writeRequest(listURL.appendingPathComponent(id), method: "PATCH")
            var body: [String: Any] = ["owner": "", "paired": false]
            if !accountID.isEmpty { body["owner_ref"] = "" }
            guard let payload = try? JSONSerialization.data(withJSONObject: body) else {
                return false
            }
            patch.httpBody = payload
            // The successful PATCH response is the saved record. Reading the
            // row back after clearing owner_ref can correctly become forbidden
            // to the account that just released it, so a second GET would turn
            // a verified unpair into a false failure.
            let patched: Bool
            if let savedData = try? await send(patch),
               let saved = try? JSONSerialization.jsonObject(with: savedData) as? [String: Any] {
                patched = (saved["paired"] as? Bool) == false
                    && ((saved["owner"] as? String) ?? "").isEmpty
                    && (accountID.isEmpty
                        || ((saved["owner_ref"] as? String) ?? "").isEmpty)
            } else {
                patched = false
            }
            patchResults.append(patched)
            guard patched else { return false }
        }

        // Verify the filtered set itself is empty. Individual PATCH responses
        // prove only the rows we saw; this final read catches a missed page or a
        // row that appeared during unaffiliation.
        var verify = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
        verify.percentEncodedQuery = "filter=\(filter)&perPage=1&page=1"
        guard let verifyURL = verify.url,
              let data = try? await readData(from: verifyURL),
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let remaining = root["totalItems"] as? Int else { return false }
        return AgentUnpairPolicy.succeeded(
            patchResults: patchResults, remainingRows: remaining)
    }

    /// The agent paired to this owner (if any), with its latest heartbeat.
    func fetchAgent(owner: String) async throws -> BrowserAgent? {
        let listURL = baseURL.appendingPathComponent("api/collections/agents/records")
        let rawFilter = accountID.isEmpty
            ? "owner=\"\(owner)\""
            : "owner_ref=\"\(accountID)\""
        let filter = rawFilter.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed)!
        var comps = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
        comps.percentEncodedQuery = "filter=\(filter)&sort=-updated&perPage=1"
        let data = try await readData(from: comps.url!)
        struct Page: Decodable { let items: [BrowserAgent] }
        return try JSONDecoder().decode(Page.self, from: data).items.first
    }

    /// The signed-in account these writes belong to, when there is one.
    var accountID: String = ""

    /// Push one event, and say which row it became.
    ///
    /// The returned id is what a LATER line names as its parent when the clock
    /// cut a sentence in half. It is empty when the row was created but the
    /// response could not be read: the write DID happen, so that case must
    /// never be treated as a failure or the same words are posted twice.
    @discardableResult
    func pushEvent(kind: String, text: String, decision: String? = nil,
                   importance: Int? = nil,
                   goal: String? = nil, speaker: String? = nil,
                   explicit: Bool = false, source: String? = nil,
                   capture: CaptureEnvelope? = nil,
                   parentLine: String? = nil,
                   externalEventID: String? = nil) async throws -> String {
        var body: [String: Any] = [
            "device_id": deviceID, "kind": kind, "text": text,
            "decision": decision ?? "", "goal": goal ?? "",
        ]
        // WHEN IT WAS SAID, not when it arrived. The phone buffers: offline,
        // backgrounded, bad signal, a call holding the mic — and then flushes
        // a lump. Everything downstream that reasons about order was reading
        // PocketBase's `created`, which is the moment the network delivered
        // the row, so a flushed backlog looked like a burst of unrelated
        // fragments seconds apart. Omi ships this exact bug (their #6551).
        //
        // This used to call `Date()` right here, which is PUSH time, so the
        // offline retry queue re-stamped every buffered line at the moment the
        // signal came back and reintroduced the exact reordering the paragraph
        // above claims to fix. Only the caller that produced the line knows
        // when the words were finished, so it passes that instant in and this
        // method transmits what it is given.
        //
        // AND HOW LONG IT TOOK TO SAY. This block used to read "the phone
        // honestly knows ONE moment, the one the flush happened at" and write
        // that one instant into all three columns. It was wrong on its own
        // terms: `PhoneListener.deliver` has always had `wordsAppearedAt` in
        // scope beside `now` and simply had no way to hand both over.
        //
        // Aliasing them is not a harmless approximation. Ordering is a
        // COMPARISON, which a constant offset preserves; a boundary is a
        // SUBTRACTION, and subtracting a number from itself is zero — so
        // `brain/segmenter.py` fell back to `end = start` and every silence
        // between two turns was measured flush-to-flush, swallowing the whole
        // speaking duration of the later turn plus the 2.6 s debounce.
        //
        // Which column gets which instant is `CaptureEnvelope`'s decision and
        // not this method's, so there is one rule, in one testable place, for
        // the live push and the offline flush alike. This method transmits
        // what it is given.
        //
        // The server treats an implausible stamp as absent, so a device with a
        // wrong clock degrades to yesterday's behaviour rather than reordering
        // someone's day. Omitted entirely when the caller does not know, since
        // an event posted at the moment it happens is already described by
        // `created` and a guessed stamp is worse than an absent one.
        if let capture {
            let clock = ISO8601DateFormatter.anticipyUTC
            for (column, value) in capture.wireFields(stamp: clock.string(from:)) {
                body[column] = value
            }
        }
        // THIS LINE CARRIES ON FROM THAT ONE. Set only when the 8s ceiling cut
        // a sentence in half, which is mechanism the phone knows for certain:
        // it says which timer fired, never what the words mean. The column
        // already exists (migration 1700000020) and nothing reads it yet, so
        // this is additive on the wire — `LINKS_ON` is untouched and no brain
        // behaviour changes today.
        if let parentLine, !parentLine.isEmpty { body["parent_line"] = parentLine }
        // The ONLY thing the voice check ever sends: one short word about
        // who spoke ("owner", "other:v2", "other:Sarah"). The voiceprint it
        // came from never leaves the phone, and neither does the audio.
        if let speaker, !speaker.isEmpty { body["speaker"] = speaker }
        if explicit { body["explicit"] = true }
        // WHICH EARS HEARD IT. `device_id` names the build, not the
        // microphone, so a phone-mic line and a pendant line were byte
        // identical on the wire — 1338 transcripts in production and not one
        // of them says which mic spoke. That makes "is the pendant as good as
        // the phone" a stopwatch-and-eyeball question about the exact two
        // paths this product is a comparison between. The column already
        // exists on `events` and no build ever wrote it.
        //
        // Omitted rather than sent empty when unknown, so an old row and a
        // genuinely unattributable one read the same downstream.
        if let source, !source.isEmpty { body["source"] = source }
        // Stable client identity for writes whose HTTP response can be lost.
        // The events collection has a unique index on non-empty values, so a
        // retry of the same logical app reply cannot create a second turn.
        if let externalEventID, !externalEventID.isEmpty {
            body["external_event_id"] = externalEventID
        }
        // How much a seeded fact matters. Only the day-zero paths set it; a
        // transcript has no business claiming an importance, and a missing
        // value reads as 4 on the worker side.
        if let importance { body["importance"] = importance }
        // Say whose words these are. Until today `events` had no owner column
        // at all, which is why a brand-new account opened the app to a stranger's
        // transcripts — seen for real in the simulator against production.
        if !accountID.isEmpty { body["owner_ref"] = accountID }
        let data = try await post("api/collections/events/records", body: body)
        // Best effort, and deliberately NOT a throw. The row exists by the
        // time this runs, so failing here would send the caller down its retry
        // path and post the same speech a second time. A line whose id cannot
        // be read simply cannot be named as a parent.
        guard let row = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let id = row["id"] as? String else { return "" }
        return id
    }

    /// Queue an errand, and say which row it became.
    ///
    /// `lane`, `consequence` and `watchingUntil` are omitted for ordinary
    /// browser work, which is why they are optional: an errand from triage is
    /// byte-identical on the wire to what it was before.
    ///
    /// A SUPERVISED READ IS BORN WITH ITS LEASE ALREADY SET. The extension
    /// re-reads `watching_until` before it may claim the row
    /// (`research_lane.pb.js`), so a job created without one is unclaimable
    /// until the first heartbeat lands ten seconds later — which reads as a
    /// dead screen. Set it here and the heartbeat only ever extends it.
    ///
    /// Returns the created row's id. Nothing else can name a supervised read
    /// afterwards: the lease is PATCHed onto that id, and the narration comes
    /// back stamped with it.
    @discardableResult
    func queueJob(goal: String, params: [String: String],
                  lane: String? = nil, consequence: String? = nil,
                  watchingUntil: Date? = nil) async throws -> String {
        let paramsJSON = String(data: try JSONSerialization.data(withJSONObject: params), encoding: .utf8) ?? "{}"
        var body: [String: Any] = [
            "goal": goal, "params": paramsJSON, "status": "queued", "device_id": deviceID,
        ]
        if let lane, !lane.isEmpty { body["lane"] = lane }
        if let consequence, !consequence.isEmpty { body["consequence"] = consequence }
        if let watchingUntil {
            body["watching_until"] = ISO8601DateFormatter.anticipyUTC.string(from: watchingUntil)
        }
        if !accountID.isEmpty { body["owner_ref"] = accountID }
        let data = try await post("api/collections/jobs/records", body: body)
        // Trust the record, not the status code — the same law pairing learned
        // the hard way (`pairAgent` above). A read whose job id we only think
        // we know would heartbeat into the void and narrate nothing.
        guard let row = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let id = row["id"] as? String, !id.isEmpty else {
            throw BackendError(status: 502)
        }
        return id
    }

    /// Latest brain events, newest first — heard lines + what Anticipy said.
    ///
    /// `matching` narrows to one thing's events (a supervised read's narration,
    /// say) and is ANDed onto the owner clause. IT MUST NOT CONTAIN `||`:
    /// guard.pb.js:38-43 refuses any list whose filter carries an `or`, because
    /// `&&` can only narrow the owner set while `||` can widen it back out.
    /// Filter on one column and split the kinds on this side.
    ///
    /// `oldestFirst` exists for a narration log, which is only readable in the
    /// order she said it.
    func fetchEvents(limit: Int = 40, matching extra: String? = nil,
                     oldestFirst: Bool = false) async throws -> [BrainEvent] {
        let listURL = baseURL.appendingPathComponent("api/collections/events/records")
        var comps = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
        var items = [URLQueryItem(name: "perPage", value: String(limit)),
                     URLQueryItem(name: "sort", value: oldestFirst ? "created" : "-created")]
        // Scoped, always. Unowned legacy rows are deliberately NOT included:
        // showing them to whoever happens to be signed in is the exact bug this
        // fixes. They are claimed onto an account by /auth/claim instead.
        var clauses: [String] = []
        if !accountID.isEmpty { clauses.append("owner_ref=\"\(accountID)\"") }
        if let extra, !extra.isEmpty { clauses.append("(\(extra))") }
        if !clauses.isEmpty {
            items.append(URLQueryItem(name: "filter", value: clauses.joined(separator: " && ")))
        }
        comps.queryItems = items
        let data = try await readData(from: comps.url!)
        struct Page: Decodable { let items: [BrainEvent] }
        return try JSONDecoder().decode(Page.self, from: data).items
    }

    /// Exact read-after-write for an idempotent app reply. Both the server
    /// filter and the decoded result are account checked: a proxy that ignores
    /// one query clause cannot turn another owner's matching durable id into a
    /// false success on this phone.
    func hasEvent(kind: String, externalEventID: String) async throws -> Bool {
        guard !accountID.isEmpty, !kind.isEmpty,
              !externalEventID.isEmpty else { throw BackendError(status: 400) }
        func escaped(_ value: String) -> String {
            value.replacingOccurrences(of: "\\", with: "\\\\")
                .replacingOccurrences(of: "\"", with: "\\\"")
        }
        let filter = "owner_ref=\"\(escaped(accountID))\""
            + " && external_event_id=\"\(escaped(externalEventID))\""
            + " && kind=\"\(escaped(kind))\""
        let listURL = baseURL.appendingPathComponent("api/collections/events/records")
        var comps = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
        comps.queryItems = [
            URLQueryItem(name: "filter", value: filter),
            URLQueryItem(name: "perPage", value: "2"),
            URLQueryItem(name: "page", value: "1"),
        ]
        let data = try await readData(from: comps.url!)
        struct Identity: Decodable {
            let kind: String
            let owner_ref: String?
            let external_event_id: String?
        }
        struct Page: Decodable { let items: [Identity] }
        let rows = try JSONDecoder().decode(Page.self, from: data).items
        guard rows.allSatisfy({
            $0.kind == kind && $0.owner_ref == accountID
                && $0.external_event_id == externalEventID
        }) else { throw BackendError(status: 502) }
        return !rows.isEmpty
    }

    /// A real page of the event archive with the server's page and total-page
    /// answers intact. `fetchEvents` remains the small live poll; screens that
    /// promise history use this and explicitly advance until `totalPages`.
    func fetchEventPage(page: Int, perPage: Int = 100,
                        matching extra: String? = nil,
                        oldestFirst: Bool = false) async throws -> BrainEventPage {
        let listURL = baseURL.appendingPathComponent("api/collections/events/records")
        var comps = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
        var items = [
            URLQueryItem(name: "page", value: String(max(1, page))),
            URLQueryItem(name: "perPage", value: String(min(max(1, perPage), 500))),
            URLQueryItem(name: "sort", value: oldestFirst ? "created" : "-created"),
        ]
        var clauses: [String] = []
        if !accountID.isEmpty { clauses.append("owner_ref=\"\(accountID)\"") }
        if let extra, !extra.isEmpty { clauses.append("(\(extra))") }
        if !clauses.isEmpty {
            items.append(URLQueryItem(name: "filter",
                                      value: clauses.joined(separator: " && ")))
        }
        comps.queryItems = items
        let data = try await readData(from: comps.url!)
        return try JSONDecoder().decode(BrainEventPage.self, from: data)
    }

    /// Transcript-only archive page. Keeping the filter here means History
    /// does not page through replies, status narration, and other event kinds
    /// merely to discard them on the phone.
    func fetchTranscriptPage(page: Int, perPage: Int = 100,
                             createdAtOrBefore snapshot: String? = nil) async throws -> BrainEventPage {
        var clauses = ["kind=\"transcript\""]
        if let snapshot, !snapshot.isEmpty {
            // The value came from PocketBase's own `created` field. Escape it
            // anyway so the archive boundary remains data inside the filter,
            // never syntax, if that wire format changes later.
            let safe = snapshot
                .replacingOccurrences(of: "\\", with: "\\\\")
                .replacingOccurrences(of: "\"", with: "\\\"")
            clauses.append("created<=\"\(safe)\"")
        }
        return try await fetchEventPage(page: page, perPage: perPage,
                                        matching: clauses.joined(separator: " && "))
    }

    /// Latest jobs for THIS owner, newest first — powers the proactive feed.
    ///
    /// The owner filter is not cosmetic: unscoped, the second person to install
    /// Anticipy opened it to the first person's errands, with "Send it" next to
    /// them. `jobs` already carries `owner` (the brain stamps it), so this is a
    /// client-side change only. Note it is a courtesy, not a security boundary —
    /// the backend still gates every read on one shared token.
    func fetchJobs(owner: String, limit: Int = 30) async throws -> [AgentJob] {
        let listURL = baseURL.appendingPathComponent("api/collections/jobs/records")
        var comps = URLComponents(url: listURL, resolvingAgainstBaseURL: false)!
        var items = [URLQueryItem(name: "perPage", value: String(limit)),
                     URLQueryItem(name: "sort", value: "-created")]
        if !accountID.isEmpty {
            items.append(URLQueryItem(name: "filter", value: "owner_ref=\"\(accountID)\""))
        }
        comps.queryItems = items
        let data = try await readData(from: comps.url!)
        struct Page: Decodable { let items: [AgentJob] }
        return try JSONDecoder().decode(Page.self, from: data).items
    }

    /// Canonical read-after-uncertain-write for one action card. A collection
    /// refresh is not enough here: it is capped and can omit the exact row whose
    /// PATCH response was lost.
    func fetchJob(id: String) async throws -> AgentJob {
        let url = baseURL
            .appendingPathComponent("api/collections/jobs/records")
            .appendingPathComponent(id)
        let data = try await readData(from: url)
        return try JSONDecoder().decode(AgentJob.self, from: data)
    }

    /// Release a held job (in-app "Send it") or cancel it ("Not now").
    func setJobFields(id: String, fields: [String: Any]) async throws {
        let url = baseURL
            .appendingPathComponent("api/collections/jobs/records")
            .appendingPathComponent(id)
        var patch = writeRequest(url, method: "PATCH")
        patch.httpBody = try JSONSerialization.data(withJSONObject: fields)
        // "Send it" and "Not now" land here. This used to discard the response,
        // so a 403 buzzed success and left the card sitting there — which reads
        // as a UI glitch, so people tap it again.
        try await send(patch)
    }

    /// Quick reachability probe for the connection health UI.
    func isReachable() async -> Bool {
        var req = URLRequest(url: baseURL.appendingPathComponent("api/health"))
        req.timeoutInterval = 4
        guard let (_, resp) = try? await URLSession.shared.data(for: req),
              let http = resp as? HTTPURLResponse else { return false }
        return http.statusCode == 200
    }

    /// A refusal from the backend. `message` carries the server's own sentence
    /// when it sent one, so a screen can say what actually went wrong instead
    /// of picking the likeliest-sounding reason. Defaulted to nil so the call
    /// sites that only ever knew a status code are unchanged.
    struct BackendError: Error {
        let status: Int
        var message: String? = nil
    }

    @discardableResult
    private func post(_ path: String, body: [String: Any]) async throws -> Data {
        var request = writeRequest(baseURL.appendingPathComponent(path), method: "POST")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, resp) = try await URLSession.shared.data(for: request)
        // A rejected write is a FAILED write: without this the caller's
        // do/catch never fires and a line the backend refused looks sent.
        if let http = resp as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw BackendError(status: http.statusCode)
        }
        // The created row comes back in the body; `queueJob` needs its id and
        // everything else still ignores it (@discardableResult).
        return data
    }
}

extension ISO8601DateFormatter {
    /// One shared, explicitly-UTC formatter for the capture stamp.
    ///
    /// Explicit about the timezone because the failure it prevents is not
    /// hypothetical: a build that stamps naive local time hands the server a
    /// timestamp hours away from the truth, and anything that gates on
    /// "how old is this line" then either drops today's speech as stale or
    /// treats yesterday's as fresh. Built once — ISO8601DateFormatter is
    /// expensive to construct and this runs on every finished line.
    static let anticipyUTC: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.timeZone = TimeZone(secondsFromGMT: 0)
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
}
