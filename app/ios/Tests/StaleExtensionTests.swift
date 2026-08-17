import Foundation

// He asked "am I on the right version of the extension?" twice, and a whole
// retest cycle once ran against a stale extension while everyone believed the
// fixes were live. Chrome reports its version on every heartbeat, so the
// product can answer that itself instead of making him ask a person.

func check(_ name: String, _ ok: Bool, _ detail: String = "") {
    print("\(ok ? "PASS" : "FAIL"): \(name)\(ok || detail.isEmpty ? "" : "  -> \(detail)")")
    if !ok { failures += 1 }
}
var failures = 0

// Mirrors AnticipySession.staleExtension.
let expected = "0.8.2"
func staleExtension(_ browser: String?) -> String? {
    guard let browser, let range = browser.range(of: "ext/") else { return nil }
    let running = String(browser[range.upperBound...]).prefix(while: { $0.isNumber || $0 == "." })
    guard !running.isEmpty else { return nil }
    func parts(_ v: some StringProtocol) -> [Int] { v.split(separator: ".").map { Int($0) ?? 0 } }
    let have = parts(running), want = parts(expected)
    for i in 0..<max(have.count, want.count) {
        let a = i < have.count ? have[i] : 0
        let b = i < want.count ? want[i] : 0
        if a != b { return a < b ? String(running) : nil }
    }
    return nil
}

// The exact situation he was in: Chrome on 0.7.9, source on 0.8.2.
check("the version he was actually stuck on is caught",
      staleExtension("Chrome/128.0.0.0 ext/0.7.9") == "0.7.9",
      String(describing: staleExtension("Chrome/128.0.0.0 ext/0.7.9")))
check("the shipping-gap version is caught",
      staleExtension("Chrome/128.0.0.0 ext/0.3.3") == "0.3.3")
check("being up to date says nothing at all",
      staleExtension("Chrome/128.0.0.0 ext/0.8.2") == nil)
check("being AHEAD says nothing — no nagging a dev build",
      staleExtension("Chrome/128.0.0.0 ext/0.9.0") == nil)
check("a minor-version gap is caught", staleExtension("Chrome/1 ext/0.8.1") == "0.8.1")
check("a major-version gap is caught", staleExtension("Chrome/1 ext/0.10.0") == nil)  // 0.10 > 0.8

// Never invent a warning out of missing or malformed data.
check("no version reported means no claim", staleExtension("Chrome/128.0.0.0") == nil)
check("nil is safe", staleExtension(nil) == nil)
check("empty is safe", staleExtension("") == nil)
check("garbage after ext/ is safe", staleExtension("Chrome/1 ext/") == nil)
check("non-numeric is safe", staleExtension("Chrome/1 ext/dev") == nil)

if failures > 0 { print("StaleExtensionTests: \(failures) failed"); exit(1) }
print("StaleExtensionTests: all passed")
