import Foundation

// A text is the ONLY channel this product has outside the app. `e164` decides
// what number that text goes to, and it used to decide it by guessing:
// `if digits.count == 10 { return "+1" + digits }`. A stranger in London typing
// the ten digits of their own number — 2079460958 — had +12079460958 written to
// their account at minute two of sign-up. Nothing validated it, nothing tested
// deliverability, and Twilio's rejection reaches a print() on worker stdout and
// nowhere else, so they would have finished a whole week with no messages and
// no error on any screen.
//
// The two lines under it were the same bug in national dress: most of the world
// writes its own numbers with a leading trunk 0 — "020 7946 0958" — and
// `"+" + digits` made that +02079460958. No country code in E.164 begins with
// 0, so that number cannot be dialled from anywhere on earth.
//
// e164 is compiled here FROM AnticipyApp.swift, not copied into it. The suite
// beside this one (ReachableNumberTests) keeps its own copy of looksReachable,
// which is exactly how a test stays green over a source that changed under it.

var failures = 0
func check(_ name: String, _ ok: Bool) {
    print("\(ok ? "PASS" : "FAIL"): \(name)")
    if !ok { failures += 1 }
}

func eq(_ name: String, _ got: String?, _ want: String?) {
    let ok = got == want
    print("\(ok ? "PASS" : "FAIL"): \(name)"
          + (ok ? "" : "  got \(got ?? "nil"), wanted \(want ?? "nil")"))
    if !ok { failures += 1 }
}

// ---------------------------------------------------------------- the bug
// Every one of these is a real number a real person would type, and every one
// of them used to come back as a number belonging to somebody else.
eq("a London number typed bare is not moved to the United States",
   e164("2079460958"), nil)
eq("a London number in national form is not given a +0 country",
   e164("020 7946 0958"), nil)
eq("a UK mobile in national form is not given a +0 country",
   e164("07700900123"), nil)
eq("a Delhi number in national form is refused, not mangled",
   e164("011 2345 6789"), nil)
eq("a Paris number in national form is refused, not mangled",
   e164("01 42 68 53 00"), nil)

// Refusing to guess has to be even-handed: a NANP local is refused too. If it
// were still accepted, the rule would be "guess the United States" wearing a
// guard, and the London stranger would be the only person the app is honest to.
eq("a Vancouver number typed bare is refused as well",
   e164("6045550142"), nil)

// NOTHING may come back wearing +1 that did not have +1 typed into it. This is
// the wrong-fire check: the original bug is a value, not a code path.
for typed in ["2079460958", "020 7946 0958", "07700900123", "6045550142",
              "0044 20 7946 0958", "+44 20 7946 0958", "+91 98765 43210",
              "01 42 68 53 00", "", "call me"] {
    let got = e164(typed) ?? ""
    check("\(typed.isEmpty ? "(empty)" : typed) is not turned into a US number",
          !got.hasPrefix("+1") || typed.contains("+1"))
}

// -------------------------------------------------------- what must survive
eq("a fully typed +44 survives", e164("+44 20 7946 0958"), "+442079460958")
eq("a fully typed +1 survives", e164("+1 604 555 0142"), "+16045550142")
eq("a fully typed +91 survives", e164("+91 98765 43210"), "+919876543210")
eq("punctuation is stripped", e164("+1 (604) 555-0142"), "+16045550142")
eq("00 is how the world writes +", e164("0044 20 7946 0958"), "+442079460958")
eq("00 with punctuation", e164("00 44 20 7946 0958"), "+442079460958")

// ------------------------------------------------------------- the refusals
eq("an empty field", e164(""), nil)
eq("a lone plus", e164("+"), nil)
eq("letters", e164("call me"), nil)
eq("a half-typed number", e164("+44 207"), nil)
eq("a country code that starts with 0", e164("+0 44 20 7946 0958"), nil)
eq("00 followed by another 0", e164("000 44 20 7946"), nil)
eq("longer than E.164 allows", e164("+1234567890123456"), nil)
eq("exactly 15 digits is still a number", e164("+441234567890123"),
   "+441234567890123")

// ------------------------------------------------------------ the prefill
// e164's refusal is only honest if the field the stranger meets already carries
// their country. If this table is wrong, the old bug is back with a new table.
eq("GB", DiallingCode.forRegion("GB"), "+44")
eq("US", DiallingCode.forRegion("US"), "+1")
eq("CA", DiallingCode.forRegion("CA"), "+1")
eq("IN", DiallingCode.forRegion("IN"), "+91")
eq("DE", DiallingCode.forRegion("DE"), "+49")
eq("BR", DiallingCode.forRegion("BR"), "+55")
eq("NG", DiallingCode.forRegion("NG"), "+234")
eq("SG", DiallingCode.forRegion("SG"), "+65")
eq("AU", DiallingCode.forRegion("AU"), "+61")
eq("JP", DiallingCode.forRegion("JP"), "+81")
eq("a lowercase region is the same region", DiallingCode.forRegion("gb"), "+44")
eq("a region nobody has heard of", DiallingCode.forRegion("ZZ"), nil)
eq("an empty region", DiallingCode.forRegion(""), nil)
eq("a three-letter code is not a region", DiallingCode.forRegion("USA"), nil)

// An unlisted region gets a bare "+" — an honest empty prompt — never a
// plausible wrong country, which is the bug this whole file is about.
eq("an unlisted phone is asked, not guessed at",
   DiallingCode.forThisPhone(region: "ZZ"), "+")
eq("a UK phone arrives with +44", DiallingCode.forThisPhone(region: "GB"), "+44")

// A table that half-parsed would answer nil for most regions and "+" for the
// rest — every check above it would still pass. Size is what notices that.
check("the table carries the world, not four countries",
      DiallingCode.regions.count >= 200)

// EVERY entry, not the ten somebody thought to name.
var badShape: [String] = []
var unusable: [String] = []
for region in DiallingCode.regions {
    guard let code = DiallingCode.forRegion(region) else {
        badShape.append("\(region): no code")
        continue
    }
    let digits = code.dropFirst()
    if !code.hasPrefix("+") || digits.isEmpty || digits.count > 3
        || digits.hasPrefix("0") || !digits.allSatisfy({ $0.isNumber }) {
        badShape.append("\(region): \(code)")
    }
    // The end of the stranger's minute two: the code this puts in the field,
    // followed by the digits they type, has to be a number the app accepts.
    let typed = code + " 7946 095 812"
    guard let normalised = e164(typed), normalised.hasPrefix(code) else {
        unusable.append("\(region): \(code) -> \(e164(typed) ?? "nil")")
        continue
    }
}
check("every dialling code is one to three digits with no leading zero",
      badShape.isEmpty)
if !badShape.isEmpty { print("      \(badShape.prefix(8))") }
check("every prefilled code plus a typed number is accepted by e164",
      unusable.isEmpty)
if !unusable.isEmpty { print("      \(unusable.prefix(8))") }

if failures > 0 { print("PhoneNumberTests: \(failures) failed"); exit(1) }
print("PhoneNumberTests: all passed")
