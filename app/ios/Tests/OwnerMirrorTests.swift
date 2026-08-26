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
        if !signOut.contains("OwnerMirror.clear") {
            found.append("signOut() does not clear the owner mirrors. The next person to open this phone sees the last person's email under \"Welcome back.\", their first name in the tour, and their number ticked as confirmed.")
        }

        guard let signIn = SourceScan.body(ofFunc: "signIn(email:", in: source) else {
            return found + ["signIn() is gone, or is no longer declared where this can read it."]
        }
        if !signIn.contains("fetchOwner") {
            found.append("signIn() no longer reads the owner back from the server. ownerPhone is device-local and written only by saveOwnerPhone and signUp, so after a reinstall the phone holds no number while the account holds a real one.")
        }
        if !signIn.contains("ownerPhone = owner.phone") {
            found.append("signIn() reads the owner but does not write the number through, so the read changes nothing.")
        }

        guard let resume = SourceScan.body(ofFunc: "resumeSignedInAccount()", in: source) else {
            return found + ["resumeSignedInAccount() is gone, or is no longer declared where this can read it."]
        }
        if !resume.contains("fetchOwner") {
            found.append("resumeSignedInAccount() never asks for the number again. signIn's read is then the only one there is, and it happens on the worst network moment in the app, so a read that failed there leaves the phone believing this account has no number until the next sign-out and sign-in.")
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
        if !fetch.contains("savedPhone") {
            found.append("fetchOwner no longer consults the profile row. owners.phone is what sign-up wrote and nothing updates again; the number Settings saved lives in owner_profile, which is also the row an inbound text is routed through.")
        }
        guard let saved = SourceScan.body(ofFunc: "savedPhone(ownerRef:", in: source) else {
            return found + ["savedPhone is gone."]
        }
        if !saved.contains("owner_profile") {
            found.append("savedPhone no longer reads owner_profile, so it cannot be reading the number a text would actually reach.")
        }
        if saved.contains("try? await") {
            found.append("savedPhone swallows its read failure. A refused or unreachable profile read then reads as \"this account has no saved number\", and the caller clears one that exists.")
        }
        // Flattened, so a guard written across four lines reads the same as one
        // written across one. The rule is about the EXIT, not the formatting.
        let flat = saved.split(separator: "\n", omittingEmptySubsequences: false)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .joined(separator: " ")
        if flat.contains("else { return \"\" }") {
            found.append("savedPhone answers \"\" from a guard it could not get past. An unparseable 200 — a proxy's error page, a captive portal — then reads as \"Settings never saved a number\", and fetchOwner hands back the one sign-up wrote and calls it current.")
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

// ---- the scanner can find things ----------------------------------------

let goodSession = """
enum OwnerMirror {
    static let phone = "ownerPhone"
    static let email = "ownerEmail"

    static let keys = [phone, email]

    static func clear(in defaults: UserDefaults = .standard) {
        for key in keys { defaults.removeObject(forKey: key) }
    }
}

final class AnticipySession {
    @AppStorage("ownerID") var ownerID = ""
    @AppStorage(OwnerMirror.phone) var ownerPhone = ""
    @AppStorage(OwnerMirror.email) var ownerEmail = ""

    func signIn(email: String, password: String) async -> String? {
        if let owner = try? await backend.fetchOwner(id: id) {
            ownerPhone = owner.phone
        }
        return nil
    }

    func signOut() {
        authToken = ""
        OwnerMirror.clear()
    }

    func resumeSignedInAccount() async {
        if ownerPhone.isEmpty, let owner = try? await backend.fetchOwner(id: accountID) {
            ownerPhone = owner.phone
        }
    }
}
"""

check("the scanner sees the declarations it is meant to read",
      SourceScan.appStorageDeclarations(in: goodSession).count == 3,
      "found \(SourceScan.appStorageDeclarations(in: goodSession))")
check("the scanner reads a method body",
      SourceScan.body(ofFunc: "signOut()", in: goodSession)?.contains("OwnerMirror.clear") == true)
check("a method that is not there reads as nil, not as empty",
      SourceScan.body(ofFunc: "vanished()", in: goodSession) == nil)
check("the scanner reads the key list",
      SourceScan.arrayLiteral(named: "keys", in:
        SourceScan.body(ofEnum: "OwnerMirror", in: goodSession) ?? "") == ["phone", "email"])
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
    of: "    static let keys = [phone, email]",
    with: "    static let keys = [phone]")
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

// The read dropped, or read and thrown away.
let noRead = goodSession.replacingOccurrences(of: "backend.fetchOwner(id: id)", with: "nothing()")
check("a signIn that no longer reads the owner back is caught",
      OwnerMirrorContract.problems(inSession: noRead)
        .contains { $0.contains("reinstall") })
let readIgnored = goodSession.replacingOccurrences(of: "            ownerPhone = owner.phone\n", with: "")
check("a read whose answer is never written through is caught",
      OwnerMirrorContract.problems(inSession: readIgnored)
        .contains { $0.contains("changes nothing") })

// One read, taken on the flakiest connection in the app, and never taken
// again: the shape this had before the re-ask on resume.
let askedOnce = goodSession.replacingOccurrences(
    of: "        if ownerPhone.isEmpty, let owner = try? await backend.fetchOwner(id: accountID) {\n            ownerPhone = owner.phone\n        }\n",
    with: "")
check("a resume that never asks for the number again is caught",
      OwnerMirrorContract.problems(inSession: askedOnce)
        .contains { $0.contains("worst network moment") })

// ---- the same, for the backend half -------------------------------------

let goodBackend = """
final class AnticipyBackend {
    func fetchOwner(id: String) async throws -> Owner {
        let saved = try await savedPhone(ownerRef: id)
        return Owner(id: id, email: "", phone: saved)
    }

    private func savedPhone(ownerRef: String) async throws -> String {
        let listURL = baseURL.appendingPathComponent("api/collections/owner_profile/records")
        return ""
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
        of: "        let saved = try await savedPhone(ownerRef: id)\n", with: ""))
        .contains { $0.contains("owner_profile") })
check("a profile read that swallows its failure is caught",
      OwnerMirrorContract.problems(inBackend: goodBackend.replacingOccurrences(
        of: "        return \"\"\n    }\n}",
        with: "        _ = try? await readData(from: listURL)\n        return \"\"\n    }\n}"))
        .contains { $0.contains("swallows") })
// The same swallow one layer down: the read succeeded, the body was a login
// page, and the guard calls that "no number on file". Written across lines,
// because that is how a guard is actually written.
check("a profile read that reports an absence it could not have learned is caught",
      OwnerMirrorContract.problems(inBackend: goodBackend.replacingOccurrences(
        of: "        return \"\"\n    }\n}",
        with: "        guard let items = root[\"items\"] as? [[String: Any]]\n        else {\n            return \"\"\n        }\n        return \"\"\n    }\n}"))
        .contains { $0.contains("captive portal") })

// ---- and now the real files ---------------------------------------------

let args = CommandLine.arguments
guard args.count >= 3,
      let sessionSource = try? String(contentsOfFile: args[1], encoding: .utf8),
      let backendSource = try? String(contentsOfFile: args[2], encoding: .utf8) else {
    FileHandle.standardError.write(Data("usage: ownermirrortests <AnticipyApp.swift> <AnticipyBackend.swift>\n".utf8))
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

if failures > 0 {
    FileHandle.standardError.write(Data("\(failures) owner-mirror check(s) failed\n".utf8))
    exit(1)
}
print("owner mirrors: one list, cleared on sign-out, read back on sign-in")
