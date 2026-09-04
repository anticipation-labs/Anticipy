import Foundation

// WHOSE PHONE IS THIS, and what does it still remember about them?
//
// The bug this suite exists over: `signOut()` cleared the credentials and left
// all five device-local owner mirrors on disk, so the second person to open a
// handed-on phone was met at the door by the FIRST person's email address under
// the words "Welcome back.", saw their first name in the tour, and reached the
// number beat with their number already ticked as confirmed. The correct list
// had existed for months in `forgetMeOnThisPhone`, four hundred lines away in
// SettingsView, and nothing in the repo could see that the two disagreed.
//
// So the defect is not a wrong answer a runtime assertion could catch. It is
// the EXISTENCE of a second, silent copy of a list — the same shape
// run_theme_contract_tests.sh scans for, and the same reason it scans source.
// The list is now named once, in `OwnerMirror`, and what follows reads the
// production source and asks whether it still is.
//
// A backstop, not a proof. It can only see a mirror that is spelled `owner…`
// and stored with @AppStorage. A sixth answer-to-who-are-you called
// `preferredName`, or written straight into UserDefaults, walks past every
// check here — which is worth knowing when adding one, and is why the type it
// guards carries the argument in prose as well.

// MARK: - reading the source

enum SourceScan {

    /// Lines with the comments taken off, so prose that DESCRIBES a defect is
    /// never mistaken for the defect. The files in this tree explain
    /// themselves at length; three separate gate rules in this repo have been
    /// caught matching a comment.
    static func code(_ source: String) -> [String] {
        source.split(separator: "\n", omittingEmptySubsequences: false)
            .map(String.init)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
    }

    /// The body of a method declared at one level of nesting — everything
    /// between its `func` line and the `    }` that closes it. Returns nil when
    /// the method is not there at all, which is itself a finding: a renamed
    /// method must not make a rule pass by matching nothing.
    static func body(ofFunc signature: String, in source: String) -> String? {
        let lines = code(source)
        guard let start = lines.firstIndex(where: { $0.contains("func " + signature) })
        else { return nil }
        var out: [String] = []
        for line in lines[(start + 1)...] {
            if line == "    }" { return out.joined(separator: "\n") }
            out.append(line)
        }
        return nil
    }

    /// The body of a top-level `enum X { … }`, closed by a `}` in column zero.
    static func body(ofEnum name: String, in source: String) -> String? {
        let lines = code(source)
        guard let start = lines.firstIndex(where: { $0.hasPrefix("enum " + name + " {") })
        else { return nil }
        var out: [String] = []
        for line in lines[(start + 1)...] {
            if line == "}" { return out.joined(separator: "\n") }
            out.append(line)
        }
        return nil
    }

    /// Every `@AppStorage(<argument>) … var <name>` in the file, as the pair a
    /// reader cares about: what it is called, and which key it writes.
    static func appStorageDeclarations(in source: String) -> [(name: String, key: String)] {
        var out: [(String, String)] = []
        for line in code(source) {
            guard let openIdx = line.range(of: "@AppStorage(") else { continue }
            var depth = 0
            var key = ""
            var rest = Substring("")
            var idx = line.index(before: openIdx.upperBound)
            while idx < line.endIndex {
                let ch = line[idx]
                if ch == "(" { depth += 1; if depth == 1 { idx = line.index(after: idx); continue } }
                if ch == ")" {
                    depth -= 1
                    if depth == 0 { rest = line[line.index(after: idx)...]; break }
                }
                key.append(ch)
                idx = line.index(after: idx)
            }
            guard !rest.isEmpty, let varRange = rest.range(of: " var ") else { continue }
            let name = rest[varRange.upperBound...]
                .prefix { $0.isLetter || $0.isNumber || $0 == "_" }
            guard !name.isEmpty else { continue }
            out.append((String(name), key.trimmingCharacters(in: .whitespaces)))
        }
        return out
    }

    /// `static let <name> = "<value>"` declarations, in order.
    static func stringConstants(in body: String) -> [(name: String, value: String)] {
        var out: [(String, String)] = []
        for line in body.split(separator: "\n").map(String.init) {
            let t = line.trimmingCharacters(in: .whitespaces)
            guard t.hasPrefix("static let ") else { continue }
            let after = t.dropFirst("static let ".count)
            let name = after.prefix { $0.isLetter || $0.isNumber || $0 == "_" }
            guard let eq = after.range(of: "= \""), name.count > 0 else { continue }
            let value = after[eq.upperBound...].prefix { $0 != "\"" }
            out.append((String(name), String(value)))
        }
        return out
    }

    /// The identifiers inside `static let <name> = [a, b, c]`.
    static func arrayLiteral(named name: String, in body: String) -> [String]? {
        for line in body.split(separator: "\n").map(String.init) {
            let t = line.trimmingCharacters(in: .whitespaces)
            guard t.hasPrefix("static let " + name + " ="),
                  let open = t.firstIndex(of: "["),
                  let close = t.lastIndex(of: "]") else { continue }
            return t[t.index(after: open)..<close]
                .split(separator: ",")
                .map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { !$0.isEmpty }
        }
        return nil
    }
}

// MARK: - the contract

enum OwnerMirrorContract {

    /// `ownerID` is not a mirror of the PERSON. It is this device's
    /// pre-accounts identity — the `legacy_uuid` `claimLegacy` hands the server
    /// so rows made before accounts existed can be adopted rather than
    /// orphaned — and clearing it on sign-out would strand exactly those rows.
    /// It is named here, once, so that adding a sixth `owner…` key is a
    /// decision somebody has to write down rather than one that happens by
    /// itself.
    static let notAMirror: Set<String> = ["ownerID"]

    /// What is wrong with AnticipyApp.swift, in sentences. Empty means the
    /// session, the list and the two lists' users still agree.
    static func problems(inSession source: String) -> [String] {
        var found: [String] = []

        guard let mirror = SourceScan.body(ofEnum: "OwnerMirror", in: source) else {
            return ["OwnerMirror is gone. The five device-local owner keys are named there and nowhere else; without it the list that clears them is free to drift from the list that declares them again."]
        }

        let constants = SourceScan.stringConstants(in: mirror)
        if constants.isEmpty {
            found.append("OwnerMirror declares no keys. An empty list satisfies every rule below by containing nothing.")
        }
        guard let listed = SourceScan.arrayLiteral(named: "keys", in: mirror) else {
            return found + ["OwnerMirror.keys is gone, so nothing says which keys get cleared."]
        }
        for c in constants where !listed.contains(c.name) {
            found.append("OwnerMirror.\(c.name) (\"\(c.value)\") is declared but not in `keys`, so sign-out will leave it on the phone for the next person to be shown as their own.")
        }

        let byName = Dictionary(uniqueKeysWithValues: constants.map { ($0.name, $0.value) })
        for decl in SourceScan.appStorageDeclarations(in: source)
        where decl.name.lowercased().hasPrefix("owner") && !notAMirror.contains(decl.name) {
            let viaMirror = decl.key.hasPrefix("OwnerMirror.")
            let constant = String(decl.key.dropFirst("OwnerMirror.".count))
            if !viaMirror || byName[constant] == nil {
                found.append("`\(decl.name)` is stored under \(decl.key), not under an OwnerMirror key. Sign-out clears OwnerMirror.keys and nothing else, so this one survives the account it belongs to.")
            }
        }

        if let clear = SourceScan.body(ofFunc: "clear(in defaults:", in: source) {
            if !clear.contains("keys") {
                found.append("OwnerMirror.clear no longer walks `keys`. Naming the keys a second time inside the clear is the drift this type was built to remove.")
            }
        } else {
            found.append("OwnerMirror.clear is gone.")
        }

        guard let signOut = SourceScan.body(ofFunc: "signOut()", in: source) else {
            return found + ["signOut() is gone, or is no longer declared where this can read it."]
        }
        let sharedClear = SourceScan.body(ofFunc: "clearSignedInSurface()", in: source)
        let signOutClearsMirrors = signOut.contains("OwnerMirror.clear")
            || (signOut.contains("clearSignedInSurface()")
                && sharedClear?.contains("OwnerMirror.clear") == true)
        if !signOutClearsMirrors {
            found.append("signOut() does not clear the owner mirrors. The next person to open this phone sees the last person's email under \"Welcome back.\", their first name in the tour, and their number ticked as confirmed.")
        }

        guard let refresh = SourceScan.body(ofFunc: "refreshCanonicalOwner()", in: source) else {
            return found + ["refreshCanonicalOwner() is gone. Sign-in and launch need one shared canonical read or their five-field replacement rules can drift."]
        }
        if !refresh.contains("fetchOwner") || !refresh.contains("applyCanonicalOwner") {
            found.append("refreshCanonicalOwner() no longer reads and applies the server owner/profile as one operation.")
        }

        // Swift's external label is followed by an internal parameter name in
        // a declaration (`with canonical:`), not by a colon as it is at the
        // call site (`with:`). Match the declaration prefix and let the body
        // scanner find its brace, so renaming that internal parameter cannot
        // turn a valid implementation red.
        guard let replace = SourceScan.body(
            ofFunc: "replaceOwnerMirror(with ", in: source
        ) else {
            return found + ["replaceOwnerMirror(with:) is gone, so the source gate cannot prove canonical empty values replace all five device mirrors."]
        }
        for field in ["Phone", "FirstName", "LastName", "Email", "Birthday"]
        where !replace.contains("owner\(field) = replacement.") {
            found.append("replaceOwnerMirror(with:) does not unconditionally replace owner\(field); an empty canonical value can leave stale data behind.")
        }

        guard let apply = SourceScan.body(ofFunc: "applyCanonicalOwner(", in: source) else {
            return found + ["applyCanonicalOwner is gone."]
        }
        for field in ["phone", "firstName", "lastName", "email", "birthday"]
        where !apply.contains("owner.\(field)") {
            found.append("applyCanonicalOwner does not carry canonical owner.\(field) into the replacement snapshot.")
        }

        guard let signIn = SourceScan.body(ofFunc: "signIn(email:", in: source) else {
            return found + ["signIn() is gone, or is no longer declared where this can read it."]
        }
        if !signIn.contains("refreshCanonicalOwner") {
            found.append("signIn() no longer rehydrates the complete canonical owner/profile after authentication.")
        }
        if !signIn.contains("prepareLocalPersonStateForSignIn") {
            found.append("signIn() does not pass through the interactive local-person boundary, so an empty legacy stamp can adopt stale device-only data.")
        }

        guard let resume = SourceScan.body(ofFunc: "resumeSignedInAccount()", in: source) else {
            return found + ["resumeSignedInAccount() is gone, or is no longer declared where this can read it."]
        }
        if !resume.contains("refreshCanonicalOwner") {
            found.append("resumeSignedInAccount() does not refresh the complete canonical owner/profile on authenticated launch.")
        }
        if !resume.contains("adoptLocalPersonStateOnAuthenticatedLaunch") {
            found.append("resumeSignedInAccount() no longer uses the one-time authenticated-launch adoption path for a missing local-person stamp.")
        }

        guard let launch = SourceScan.body(
            ofFunc: "adoptLocalPersonStateOnAuthenticatedLaunch(for account:", in: source),
              let arrival = SourceScan.body(
                ofFunc: "prepareLocalPersonStateForSignIn(for account:", in: source)
        else { return found + ["The launch/sign-in local-person ownership paths are no longer separately inspectable."] }
        if !launch.contains("localPersonAccountID.isEmpty")
            || !launch.contains("localPersonAccountID = account")
            || !launch.contains("return") {
            found.append("An already-authenticated legacy launch no longer adopts an empty local-person stamp without purging its own state.")
        }
        let flatArrival = arrival.split(separator: "\n", omittingEmptySubsequences: false)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .joined(separator: " ")
        if !flatArrival.contains("if localPersonAccountID != account {")
            || !arrival.contains("purgeLocalPersonState")
            || !arrival.contains("clearSignedInSurface") {
            found.append("Interactive sign-in no longer purges an empty or different local-person stamp before adoption.")
        }
        if let expiry = SourceScan.body(ofFunc: "expireSession()", in: source),
           expiry.contains("localPersonAccountID") {
            found.append("Token expiry clears the local-person stamp, so same-account re-authentication can no longer preserve device-only state.")
        }
        guard let remove = SourceScan.body(ofFunc: "removeOwnerPhone()", in: source)
        else { return found + ["removeOwnerPhone() is gone; the E.164 save path cannot represent an intentional empty phone."] }
        if !remove.contains("backend.removeOwnerPhone")
            || !remove.contains("refreshCanonicalOwner")
            || !remove.contains("canonicalOwnerPhoneState == .none") {
            found.append("removeOwnerPhone() does not call the atomic unaffiliation endpoint, reread canonical state, and verify `.none` before reporting success.")
        }

        return found
    }

    /// What is wrong with AnticipyBackend.swift.
    static func problems(inBackend source: String) -> [String] {
        var found: [String] = []

        guard let fetch = SourceScan.body(ofFunc: "fetchOwner(id:", in: source) else {
            return ["fetchOwner is gone. Nothing else on the phone asks the server who this account is."]
        }
        let signature = SourceScan.code(source)
            .first { $0.contains("func fetchOwner(id:") } ?? ""
        if !signature.contains("async throws") {
            found.append("fetchOwner no longer throws. A read that failed and an account with no number then arrive as the same answer, and the caller wipes a good number every time the train goes into a tunnel.")
        }
        if !fetch.contains("savedProfile") {
            found.append("fetchOwner no longer consults the complete profile row. Settings' name, contact details, and birthday would disappear after sign-out.")
        }
        guard let saved = SourceScan.body(ofFunc: "savedProfile(ownerRef:", in: source) else {
            return found + ["savedProfile is gone."]
        }
        if !saved.contains("owner_profile") {
            found.append("savedProfile no longer reads owner_profile.")
        }
        if saved.contains("try? await") {
            found.append("savedProfile swallows its read failure. A refused profile read can then erase valid local mirrors.")
        }
        // Flattened, so a guard written across four lines reads the same as one
        // written across one. The rule is about the EXIT, not the formatting.
        let flat = saved.split(separator: "\n", omittingEmptySubsequences: false)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .joined(separator: " ")
        if flat.contains("else { return \"\" }") {
            found.append("savedProfile reports an empty answer from a guard it could not get past; malformed data must throw rather than erase mirrors.")
        }
        for key in ["phone", "first_name", "last_name", "email", "birthday"]
        where !saved.contains("[\"\(key)\"]") {
            found.append("savedProfile does not decode \(key), so that canonical field cannot survive re-authentication.")
        }
        if fetch.contains("profilePhone.isEmpty")
            || fetch.contains("profile?.phone.isEmpty") {
            found.append("fetchOwner falls back by phone value. An existing profile's explicit empty would resurrect owners.phone.")
        }
        guard let upsert = SourceScan.body(ofFunc: "upsertOwner(ownerID:", in: source)
        else { return found + ["upsertOwner is gone."] }
        if !upsert.contains("me/profile/upsert") || !upsert.contains("method: \"POST\"") {
            found.append("upsertOwner bypasses the authenticated atomic profile endpoint, so independent first saves can still create or reject partial rows.")
        }
        if upsert.contains("api/collections/owner_profile/records") {
            found.append("upsertOwner still performs the racy client-side owner_profile list/write flow.")
        }
        if upsert.contains("body[\"owner_id\"]")
            || upsert.contains("body[\"owner_ref\"]")
            || upsert.contains("[\"owner_id\": ownerID]") {
            found.append("upsertOwner lets the device choose profile ownership instead of deriving it from the authenticated account.")
        }
        if upsert.contains("where !v.isEmpty") {
            found.append("upsertOwner drops explicit empty values, so the remove-number action can report success without clearing the server field.")
        }
        for evidence in ["send(request)", "result[\"ok\"]", "result[\"profile\"]",
                         "profile[\"owner_ref\"]", "fields.allSatisfy"]
        where !upsert.contains(evidence) {
            found.append("upsertOwner does not verify \(evidence) in the canonical endpoint response.")
        }
        guard let removePhone = SourceScan.body(ofFunc: "removeOwnerPhone()", in: source)
        else { return found + ["The backend client has no atomic remove-owner-phone endpoint."] }
        for evidence in ["me/phone/remove", "result[\"ok\"]", "result[\"phone\"]",
                         "result[\"clearedProfiles\"]"]
        where !removePhone.contains(evidence) {
            found.append("Backend removeOwnerPhone does not verify \(evidence) from the atomic endpoint response.")
        }

        return found
    }

    static func problems(inSettingsProfile source: String) -> [String] {
        var found: [String] = []
        if !source.contains("Remove number") || !source.contains("Use in-app updates only") {
            found.append("Profile has no explicit consumer-facing route to remove SMS and use in-app updates only.")
        }
        guard let remove = SourceScan.body(ofFunc: "removeNumber()", in: source) else {
            return found + ["SettingsProfileView.removeNumber() is gone."]
        }
        if !remove.contains("session.removeOwnerPhone()") || !remove.contains("phoneField = \"\"") {
            found.append("The remove-number control does not call the verified session action and clear the visible field after success.")
        }
        return found
    }
}

// MARK: - checks

var failures = 0

func check(_ name: String, _ ok: Bool, _ why: @autoclosure () -> String = "") {
    if ok { return }
    failures += 1
    let tail = why()
    FileHandle.standardError.write(Data(("FAIL: " + name + (tail.isEmpty ? "" : " — " + tail) + "\n").utf8))
}

// ---- the production replacement policy, exercised as account lifecycles ---

let canonicalA = OwnerMirror.Values(
    phone: "+16045550101", firstName: "Alpha", lastName: "Able",
    email: "alpha@example.com", birthday: "1990-01-02")
let restoredA = OwnerMirror.Values.empty.replacing(with: canonicalA)
check("A sign-out then A sign-in restores every canonical profile field",
      restoredA == canonicalA)

let canonicalB = OwnerMirror.Values(
    phone: "", firstName: "Bravo", lastName: "",
    email: "bravo@example.com", birthday: "")
let switchedToB = canonicalA.replacing(with: canonicalB)
check("A to B replaces the whole profile rather than merging non-empty fields",
      switchedToB == canonicalB)
check("B's explicit empty values erase A's phone, last name, and birthday",
      switchedToB.phone.isEmpty && switchedToB.lastName.isEmpty
        && switchedToB.birthday.isEmpty)

let removedPhone = OwnerProfileCanonical.value(
    profileValue: "", accountValue: canonicalA.phone)
check("an existing profile's explicit empty phone beats a stale signup number",
      removedPhone.isEmpty)
check("the signup phone seeds only an absent profile row",
      OwnerProfileCanonical.value(profileValue: nil, accountValue: canonicalA.phone)
        == canonicalA.phone)
check("an explicit empty canonical phone is the none state",
      OwnerMirror.phoneState(forCanonicalPhone: removedPhone, isValid: false) == .none)
check("a non-empty malformed canonical phone is invalid, not absent",
      OwnerMirror.phoneState(forCanonicalPhone: "not-a-number", isValid: false) == .invalid)
check("a validated canonical phone is valid",
      OwnerMirror.phoneState(forCanonicalPhone: canonicalA.phone, isValid: true) == .valid)

check("21 browser rows at perPage 20 require both server pages",
      AgentUnpairPolicy.pages(totalPages: 2) == [1, 2])
check("all 21 verified PATCHes plus zero remaining rows succeeds",
      AgentUnpairPolicy.succeeded(
        patchResults: Array(repeating: true, count: 21), remainingRows: 0))
var onePatchFailed = Array(repeating: true, count: 21)
onePatchFailed[20] = false
check("one failed PATCH makes 21-row unaffiliation fail",
      !AgentUnpairPolicy.succeeded(
        patchResults: onePatchFailed, remainingRows: 0))
check("a remaining browser row defeats otherwise successful PATCHes",
      !AgentUnpairPolicy.succeeded(
        patchResults: Array(repeating: true, count: 21), remainingRows: 1))

let speechAcrossDevice: [String?] = [nil, "prior-account", "current-account"]
check("device Forget removes nil, prior-account, and current-account queued speech",
      PendingSpeechRetention.afterDeviceForget(speechAcrossDevice).isEmpty)

// The unsent queue had NO bound at all until this existed: one JSON array in
// one UserDefaults string, re-encoded whole on every append, growing for as
// long as an outage lasted. These pin the two halves that make bounding it
// safe rather than merely smaller.
let underLimit = Array(0..<10)
let under = PendingSpeechRetention.bounded(underLimit, limit: 100)
check("a queue inside the limit is returned untouched and reports no loss",
      under.kept == underLimit && under.dropped == 0)

// THE DIRECTION. The newest line is the one still worth acting on; the oldest
// is already past the six hours after which the brain may remember a line but
// never act on it. Keeping the tail is what makes the loss cost memory rather
// than action, and reversing it would be silently worse.
let over = PendingSpeechRetention.bounded(Array(0..<10), limit: 4)
check("an overflowing queue keeps the NEWEST rows, not the oldest",
      over.kept == [6, 7, 8, 9])
check("and it reports exactly how many rows it lost",
      over.dropped == 6)

// A queue at exactly the limit is not an overflow. Off by one here would
// report a drop on every append once the queue reached its bound, and the
// journal would fill with losses that never happened.
let exact = PendingSpeechRetention.bounded(Array(0..<4), limit: 4)
check("a queue exactly at the limit drops nothing",
      exact.kept.count == 4 && exact.dropped == 0)

// A nonsense limit must not silently keep everything. Failing closed here
// means the count is still honest about what was thrown away.
let none = PendingSpeechRetention.bounded(Array(0..<3), limit: 0)
check("a zero limit keeps nothing and still reports the loss",
      none.kept.isEmpty && none.dropped == 3)

let partialDeleteBody = #"{"ok":false,"message":"Some rows remain.","deleted":{"events":4,"jobs":1},"failed":["owner_profile"]}"#
let partialDelete = AccountDeletionPolicy.outcome(status: 500, body: partialDeleteBody)
check("a partial 500 is not reported as complete", !partialDelete.ok)
check("a partial 500 surfaces the server message",
      partialDelete.message.contains("Some rows remain."))
check("a partial 500 names records already removed",
      partialDelete.message.contains("events (4)")
        && partialDelete.message.contains("jobs (1)"))
check("a partial 500 names the table still needing deletion",
      partialDelete.message.contains("owner_profile"))
let scheduledDeleteBody = #"{"ok":true,"deleted":{"events":4},"account_deleted":true,"memory_purge":"scheduled"}"#
let scheduledDelete = AccountDeletionPolicy.outcome(status: 200, body: scheduledDeleteBody)
check("a scheduled private-memory purge can close the deleted account",
      scheduledDelete.ok)
check("a scheduled purge is named as pending rather than already gone",
      scheduledDelete.message.contains("purge is scheduled")
        && !scheduledDelete.message.contains("private memory are gone")
        && !scheduledDelete.message.contains("Already removed"))
let purgedDeleteBody = #"{"ok":true,"account_deleted":true,"memory_purge":"purged"}"#
let purgedDelete = AccountDeletionPolicy.outcome(status: 200, body: purgedDeleteBody)
check("a verified completed private-memory purge may be called gone",
      purgedDelete.ok && purgedDelete.message.contains("private memory are gone"))
let unprovenDelete = AccountDeletionPolicy.outcome(
    status: 200, body: #"{"ok":true,"account_deleted":true}"#)
check("a 200 without memory-purge proof is not called complete",
      !unprovenDelete.ok && !unprovenDelete.message.contains("gone"))
check("a lost response makes no no-deletion claim",
      AccountDeletionPolicy.unverified.message.contains("couldn't verify how far"))
check("a lost response tells the owner to re-authenticate and recheck",
      AccountDeletionPolicy.unverified.message.contains("Sign in again")
        && AccountDeletionPolicy.unverified.message.contains("check what's left"))

check("a response-lost approval already claimed by the worker is accepted, not retried",
      ActionWritePolicy.reconcile(
        originalStatus: "awaiting_confirm",
        expectedStatus: "queued",
        observedStatus: "running") == .accepted)
check("a response-lost approval whose exact row is unchanged becomes safe to retry",
      ActionWritePolicy.reconcile(
        originalStatus: "awaiting_confirm",
        expectedStatus: "queued",
        observedStatus: "awaiting_confirm") == .safeToRetry)
check("an unchanged needs_user row is not mistaken for post-approval progress",
      ActionWritePolicy.reconcile(
        originalStatus: "needs_user",
        expectedStatus: "queued",
        observedStatus: "needs_user") == .safeToRetry)
check("a response-lost approval with no canonical read remains unverified",
      ActionWritePolicy.reconcile(
        originalStatus: "awaiting_confirm",
        expectedStatus: "queued",
        observedStatus: nil) == .unverified)
check("a server 422 is a verified refusal",
      ActionWritePolicy.isVerifiedRefusal(status: 422))
check("a server timeout is not called a verified refusal",
      !ActionWritePolicy.isVerifiedRefusal(status: 408))

// ---- the scanner can find things ----------------------------------------

let goodSession = """
enum OwnerMirror {
    static let phone = "ownerPhone"
    static let firstName = "ownerFirstName"
    static let lastName = "ownerLastName"
    static let email = "ownerEmail"
    static let birthday = "ownerBirthday"

    static let keys = [phone, firstName, lastName, email, birthday]

    static func clear(in defaults: UserDefaults = .standard) {
        for key in keys { defaults.removeObject(forKey: key) }
    }
}

final class AnticipySession {
    @AppStorage("ownerID") var ownerID = ""
    @AppStorage(OwnerMirror.phone) var ownerPhone = ""
    @AppStorage(OwnerMirror.firstName) var ownerFirstName = ""
    @AppStorage(OwnerMirror.lastName) var ownerLastName = ""
    @AppStorage(OwnerMirror.email) var ownerEmail = ""
    @AppStorage(OwnerMirror.birthday) var ownerBirthday = ""

    private func replaceOwnerMirror(with canonical: OwnerMirror.Values) {
        let replacement = currentOwnerMirror.replacing(with: canonical)
        ownerPhone = replacement.phone
        ownerFirstName = replacement.firstName
        ownerLastName = replacement.lastName
        ownerEmail = replacement.email
        ownerBirthday = replacement.birthday
    }

    private func applyCanonicalOwner(_ owner: Owner) {
        replaceOwnerMirror(with: .init(phone: owner.phone,
                                       firstName: owner.firstName,
                                       lastName: owner.lastName,
                                       email: owner.email,
                                       birthday: owner.birthday))
    }

    func refreshCanonicalOwner() async -> Bool {
        if let owner = try? await backend.fetchOwner(id: accountID) {
            applyCanonicalOwner(owner)
        }
        return true
    }

    func signIn(email: String, password: String) async -> String? {
        prepareLocalPersonStateForSignIn(for: id)
        await refreshCanonicalOwner()
        return nil
    }

    func signOut() {
        authToken = ""
        OwnerMirror.clear()
    }

    func resumeSignedInAccount() async {
        adoptLocalPersonStateOnAuthenticatedLaunch(for: accountID)
        await refreshCanonicalOwner()
    }

    func removeOwnerPhone() async -> Bool {
        guard await backend.removeOwnerPhone(),
              await refreshCanonicalOwner() else { return false }
        return canonicalOwnerPhoneState == .none
    }

    private func clearSignedInSurface() {
        OwnerMirror.clear()
    }

    private func purgeLocalPersonState() {
        forgetEverything()
    }

    private func adoptLocalPersonStateOnAuthenticatedLaunch(for account: String) {
        if localPersonAccountID.isEmpty {
            localPersonAccountID = account
            return
        }
        if localPersonAccountID != account { purgeLocalPersonState() }
        localPersonAccountID = account
    }

    private func prepareLocalPersonStateForSignIn(for account: String) {
        if localPersonAccountID != account {
            clearSignedInSurface()
            purgeLocalPersonState()
        }
        localPersonAccountID = account
    }

    private func expireSession() {
        clearSignedInSurface()
    }
}
"""

check("the scanner sees the declarations it is meant to read",
      SourceScan.appStorageDeclarations(in: goodSession).count == 6,
      "found \(SourceScan.appStorageDeclarations(in: goodSession))")
check("the scanner reads a method body",
      SourceScan.body(ofFunc: "signOut()", in: goodSession)?.contains("OwnerMirror.clear") == true)
check("a method that is not there reads as nil, not as empty",
      SourceScan.body(ofFunc: "vanished()", in: goodSession) == nil)
check("the scanner reads the key list",
      SourceScan.arrayLiteral(named: "keys", in:
        SourceScan.body(ofEnum: "OwnerMirror", in: goodSession) ?? "")
        == ["phone", "firstName", "lastName", "email", "birthday"])
check("a source that keeps the contract has nothing to say",
      OwnerMirrorContract.problems(inSession: goodSession).isEmpty,
      "\(OwnerMirrorContract.problems(inSession: goodSession))")

// ---- and the drift it exists for turns it red ----------------------------
// Each of these is a real edit somebody could make on a Tuesday.

// THE ONE THIS SUITE IS FOR: a sixth owner field on the session, stored under
// its own string, exactly as the five originals were.
let sixthField = goodSession.replacingOccurrences(
    of: "    @AppStorage(OwnerMirror.email) var ownerEmail = \"\"",
    with: "    @AppStorage(OwnerMirror.email) var ownerEmail = \"\"\n    @AppStorage(\"ownerNickname\") var ownerNickname = \"\"")
check("a sixth owner field stored outside OwnerMirror is caught",
      OwnerMirrorContract.problems(inSession: sixthField)
        .contains { $0.contains("ownerNickname") })

// A key added to the type but not to the list it is cleared from.
let unlisted = goodSession.replacingOccurrences(
    of: "    static let keys = [phone, firstName, lastName, email, birthday]",
    with: "    static let keys = [phone, firstName, lastName, email]")
check("a key missing from OwnerMirror.keys is caught",
      OwnerMirrorContract.problems(inSession: unlisted)
        .contains { $0.contains("not in `keys`") })

// The original bug, put back.
let noClear = goodSession.replacingOccurrences(of: "        OwnerMirror.clear()\n", with: "")
check("a signOut that does not clear the mirrors is caught",
      OwnerMirrorContract.problems(inSession: noClear)
        .contains { $0.contains("Welcome back.") })

// The clear rewritten to name the keys a second time.
let handRolled = goodSession.replacingOccurrences(
    of: "        for key in keys { defaults.removeObject(forKey: key) }",
    with: "        defaults.removeObject(forKey: phone)")
check("a clear that stops walking the list is caught",
      OwnerMirrorContract.problems(inSession: handRolled)
        .contains { $0.contains("walks `keys`") })

// The canonical read dropped, or one field is no longer replaced.
let noRead = goodSession.replacingOccurrences(
    of: "backend.fetchOwner(id: accountID)", with: "nothing()")
check("a refresh that no longer reads the owner back is caught",
      OwnerMirrorContract.problems(inSession: noRead)
        .contains { $0.contains("reads and applies") })
let readIgnored = goodSession.replacingOccurrences(
    of: "        ownerBirthday = replacement.birthday\n", with: "")
check("a canonical empty birthday that is never written through is caught",
      OwnerMirrorContract.problems(inSession: readIgnored)
        .contains { $0.contains("ownerBirthday") })

// One read after sign-in, and never again on an authenticated launch.
let askedOnce = goodSession.replacingOccurrences(
    of: "        adoptLocalPersonStateOnAuthenticatedLaunch(for: accountID)\n        await refreshCanonicalOwner()\n",
    with: "        adoptLocalPersonStateOnAuthenticatedLaunch(for: accountID)\n")
check("a resume that never asks for the profile again is caught",
      OwnerMirrorContract.problems(inSession: askedOnce)
        .contains { $0.contains("authenticated launch") })

let emptyStampAdoptedAtSignIn = goodSession.replacingOccurrences(
    of: "        if localPersonAccountID != account {\n            clearSignedInSurface()",
    with: "        if !localPersonAccountID.isEmpty && localPersonAccountID != account {\n            clearSignedInSurface()")
check("interactive sign-in treating an empty stamp as safe is caught",
      OwnerMirrorContract.problems(inSession: emptyStampAdoptedAtSignIn)
        .contains { $0.contains("empty or different") })

// ---- the same, for the backend half -------------------------------------

let goodBackend = """
final class AnticipyBackend {
    func fetchOwner(id: String) async throws -> Owner {
        let profile = try await savedProfile(ownerRef: id)
        return Owner(id: id,
                     email: OwnerProfileCanonical.value(profileValue: profile?.email, accountValue: ""),
                     phone: OwnerProfileCanonical.value(profileValue: profile?.phone, accountValue: ""),
                     firstName: profile?.firstName ?? "",
                     lastName: profile?.lastName ?? "",
                     birthday: profile?.birthday ?? "")
    }

    private func savedProfile(ownerRef: String) async throws -> StoredOwnerProfile? {
        let listURL = baseURL.appendingPathComponent("api/collections/owner_profile/records")
        let item = ["phone": "", "first_name": "", "last_name": "",
                    "email": "", "birthday": ""]
        return StoredOwnerProfile(phone: item["phone"] ?? "",
                                  firstName: item["first_name"] ?? "",
                                  lastName: item["last_name"] ?? "",
                                  email: item["email"] ?? "",
                                  birthday: item["birthday"] ?? "")
    }

    func upsertOwner(ownerID: String, fields: [String: String]) async -> Bool {
        var request = writeRequest(
            baseURL.appendingPathComponent("me/profile/upsert"), method: "POST")
        request.httpBody = try? JSONSerialization.data(withJSONObject: fields)
        let data = try! await send(request)
        let result = try! JSONSerialization.jsonObject(with: data) as! [String: Any]
        let profile = result["profile"] as! [String: Any]
        return result["ok"] as? Bool == true
            && profile["owner_ref"] as? String == accountID
            && fields.allSatisfy { profile[$0.key] as? String == $0.value }
    }

    func removeOwnerPhone() async -> Bool {
        let path = "me/phone/remove"
        let result: [String: Any] = ["ok": true, "phone": "", "clearedProfiles": 1]
        return result["ok"] as? Bool == true
            && (result["phone"] as? String) == ""
            && result["clearedProfiles"] as? Int == 1
    }
}
"""
check("a backend that keeps the contract has nothing to say",
      OwnerMirrorContract.problems(inBackend: goodBackend).isEmpty,
      "\(OwnerMirrorContract.problems(inBackend: goodBackend))")
check("a fetchOwner that stops throwing is caught",
      OwnerMirrorContract.problems(inBackend: goodBackend.replacingOccurrences(
        of: "func fetchOwner(id: String) async throws -> Owner",
        with: "func fetchOwner(id: String) async -> Owner"))
        .contains { $0.contains("tunnel") })
check("a fetchOwner that reads only the account record is caught",
      OwnerMirrorContract.problems(inBackend: goodBackend.replacingOccurrences(
        of: "        let profile = try await savedProfile(ownerRef: id)\n", with: ""))
        .contains { $0.contains("complete profile row") })
check("a profile read that swallows its failure is caught",
      OwnerMirrorContract.problems(inBackend: goodBackend.replacingOccurrences(
        of: "        let item = [\"phone\": \"\", \"first_name\": \"\", \"last_name\": \"\",\n",
        with: "        _ = try? await readData(from: listURL)\n        let item = [\"phone\": \"\", \"first_name\": \"\", \"last_name\": \"\",\n"))
        .contains { $0.contains("swallows") })
check("an upsert that drops explicit empty fields is caught",
      OwnerMirrorContract.problems(inBackend: goodBackend.replacingOccurrences(
        of: "request.httpBody = try? JSONSerialization.data(withJSONObject: fields)",
        with: "request.httpBody = try? JSONSerialization.data(withJSONObject: fields.filter { !$0.value.isEmpty })\n        for (k, v) in fields where !v.isEmpty { _ = (k, v) }"))
        .contains { $0.contains("explicit empty") })
check("a client-side owner_profile list/write path is caught",
      OwnerMirrorContract.problems(inBackend: goodBackend.replacingOccurrences(
        of: "baseURL.appendingPathComponent(\"me/profile/upsert\")",
        with: "baseURL.appendingPathComponent(\"api/collections/owner_profile/records\")"))
        .contains { $0.contains("racy client-side") })
check("a client-selected owner ref is caught",
      OwnerMirrorContract.problems(inBackend: goodBackend.replacingOccurrences(
        of: "request.httpBody = try? JSONSerialization.data(withJSONObject: fields)",
        with: "var body = fields\n        body[\"owner_ref\"] = accountID\n        request.httpBody = try? JSONSerialization.data(withJSONObject: body)"))
        .contains { $0.contains("device choose profile ownership") })
check("an upsert that trusts a 2xx without its canonical profile is caught",
      OwnerMirrorContract.problems(inBackend: goodBackend.replacingOccurrences(
        of: "let profile = result[\"profile\"] as! [String: Any]",
        with: "let profile: [String: Any] = [:]"))
        .contains { $0.contains("result[\"profile\"]") })

// ---- and now the real files ---------------------------------------------

let args = CommandLine.arguments
guard args.count >= 4,
      let sessionSource = try? String(contentsOfFile: args[1], encoding: .utf8),
      let backendSource = try? String(contentsOfFile: args[2], encoding: .utf8),
      let settingsSource = try? String(contentsOfFile: args[3], encoding: .utf8) else {
    FileHandle.standardError.write(Data("usage: ownermirrortests <AnticipyApp.swift> <AnticipyBackend.swift> <SettingsProfileView.swift>\n".utf8))
    exit(2)
}

for problem in OwnerMirrorContract.problems(inSession: sessionSource) {
    failures += 1
    FileHandle.standardError.write(Data(("FAIL (AnticipyApp.swift): " + problem + "\n").utf8))
}
for problem in OwnerMirrorContract.problems(inBackend: backendSource) {
    failures += 1
    FileHandle.standardError.write(Data(("FAIL (AnticipyBackend.swift): " + problem + "\n").utf8))
}
for problem in OwnerMirrorContract.problems(inSettingsProfile: settingsSource) {
    failures += 1
    FileHandle.standardError.write(Data(("FAIL (SettingsProfileView.swift): " + problem + "\n").utf8))
}

if failures > 0 {
    FileHandle.standardError.write(Data("\(failures) owner-mirror check(s) failed\n".utf8))
    exit(1)
}
print("owner mirrors: full canonical replacement, isolated account lifecycle, explicit phone removal")
