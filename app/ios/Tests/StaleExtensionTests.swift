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

// Mirrors AnticipySession.staleExtension. The pin is hand-maintained and this
// is its second copy, so tests/test_extension_version_pin.py holds all three
// numbers -- extension/manifest.json, AnticipyApp.swift, this file -- to the
// same value and goes red the moment one of them lags.
let expected = "0.14.0"
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

// The exact situation he was in: Chrome on 0.7.9, source ahead of it.
check("the version he was actually stuck on is caught",
      staleExtension("Chrome/128.0.0.0 ext/0.7.9") == "0.7.9",
      String(describing: staleExtension("Chrome/128.0.0.0 ext/0.7.9")))
check("the shipping-gap version is caught",
      staleExtension("Chrome/128.0.0.0 ext/0.3.3") == "0.3.3")
check("being up to date says nothing at all",
      staleExtension("Chrome/128.0.0.0 ext/\(expected)") == nil)
check("being AHEAD says nothing — no nagging a dev build",
      staleExtension("Chrome/128.0.0.0 ext/99.0.0") == nil)
check("a minor-version gap is caught", staleExtension("Chrome/1 ext/0.8.1") == "0.8.1")
// SAME NUMBER, DIFFERENT CODE was the real incident: the served zip said
// 0.8.2 and so did the source, while containing none of that day's work, so
// this check sat silent. The lesson is not testable here -- it is that the
// version MUST be bumped whenever the bytes change -- but the immediately
// previous version being caught is.
check("the previous version is caught once source moves on",
      staleExtension("Chrome/1 ext/0.8.2") == "0.8.2")
// This line used to assert 0.10.0 says nothing, because 0.10 really was ahead
// of the pin -- the pin had sat at 0.8.3 since the extension shipped 0.11.0.
// That is what three minor versions of silent drift looked like from inside
// the test that was supposed to catch it. Being ahead is still covered above.
check("the version the rotted pin was blind to is caught",
      staleExtension("Chrome/1 ext/0.10.0") == "0.10.0")
// The pin now carries a two-digit minor for the first time, which makes a
// whole class of install invisible to anything that compares these as text:
// "0.9.0" sorts ABOVE "0.11.0" lexically, so a string compare would tell a
// two-release-old browser it was current. parts() is what stops that, and
// this is the case that proves parts() is still doing it.
check("a single-digit minor behind a two-digit one is caught",
      staleExtension("Chrome/1 ext/0.9.0") == "0.9.0")

// Never invent a warning out of missing or malformed data.
check("no version reported means no claim", staleExtension("Chrome/128.0.0.0") == nil)
check("nil is safe", staleExtension(nil) == nil)
check("empty is safe", staleExtension("") == nil)
check("garbage after ext/ is safe", staleExtension("Chrome/1 ext/") == nil)
check("non-numeric is safe", staleExtension("Chrome/1 ext/dev") == nil)

if failures > 0 { print("StaleExtensionTests: \(failures) failed"); exit(1) }
print("StaleExtensionTests: all passed")
