// Which ear heard a line, and — more importantly — when we must say nothing.
//
// events.source was write-only for its whole life: the phone stamped it on
// every event and nothing ever read it back, so the comparison it exists for
// (the pendant run of an errand against the phone-mic run of the same errand)
// was invisible in the app that produced both halves.
//
// Run: swift app/ios/Tests/CaptureSourcePolicyTests.swift
import Foundation

// Compiled by run_capture_source_tests.sh against the REAL production source
// (CaptureSourcePolicy.swift is pure Foundation), never a copy of it.
var failures = 0
func check(_ name: String, _ ok: Bool) {
    print("\(ok ? "PASS" : "FAIL"): \(name)")
    if !ok { failures += 1 }
}

// ---------------------------------------------------------- the two ears
if let phone = CaptureSourcePolicy.badge(for: "phone_mic") {
    check("the phone mic is labelled Phone", phone.label == "Phone")
    check("the phone badge has a glyph", !phone.glyph.isEmpty)
} else {
    check("phone_mic produces a badge", false)
}

if let pendant = CaptureSourcePolicy.badge(for: "pendant") {
    check("the pendant is labelled Pendant", pendant.label == "Pendant")
    check("the pendant badge has a glyph", !pendant.glyph.isEmpty)
} else {
    check("pendant produces a badge", false)
}

check("the two ears are visually distinguishable",
      CaptureSourcePolicy.badge(for: "phone_mic")
        != CaptureSourcePolicy.badge(for: "pendant"))

// ------------------------------------------------------- deliberate silence
check("a typed line draws nothing — it was never in question",
      CaptureSourcePolicy.badge(for: "typed") == nil)

// PocketBase sends "" for an unset column, and thousands of rows predate
// anything writing this field. Defaulting to a microphone would be a lie about
// a measurement, and it would pollute the comparison this badge exists for.
check("nil draws nothing", CaptureSourcePolicy.badge(for: nil) == nil)
check("empty draws nothing", CaptureSourcePolicy.badge(for: "") == nil)
check("whitespace draws nothing", CaptureSourcePolicy.badge(for: "   ") == nil)

// A future third microphone must be silent, never mislabelled as one we know.
check("an unrecognised source draws nothing",
      CaptureSourcePolicy.badge(for: "watch_mic") == nil)
check("a near-miss is not fuzzy-matched",
      CaptureSourcePolicy.badge(for: "phone") == nil
        && CaptureSourcePolicy.badge(for: "phone_mic_v2") == nil)

// Real rows arrive with surrounding whitespace often enough to matter.
check("a padded value still matches",
      CaptureSourcePolicy.badge(for: " pendant ")?.label == "Pendant")

// ------------------------------------------- the constants match the wire
// If these ever drift from AnticipySession.LineSource.wireName, the badge
// silently stops appearing and the comparison silently stops working.
check("the wire constants are the ones the phone stamps",
      CaptureSourcePolicy.phone == "phone_mic"
        && CaptureSourcePolicy.pendant == "pendant"
        && CaptureSourcePolicy.typed == "typed")
check("the constants agree with the lookup",
      CaptureSourcePolicy.badge(for: CaptureSourcePolicy.phone) != nil
        && CaptureSourcePolicy.badge(for: CaptureSourcePolicy.pendant) != nil
        && CaptureSourcePolicy.badge(for: CaptureSourcePolicy.typed) == nil)

// ------------------------------------------------------------ VoiceOver
if let pendant = CaptureSourcePolicy.badge(for: "pendant") {
    let spoken = CaptureSourcePolicy.accessibilityLabel(for: pendant)
    check("VoiceOver says what the badge means, not just its word",
          spoken == "Heard by Pendant")
    check("the spoken label is not the bare label", spoken != pendant.label)
}

if failures > 0 {
    print("CaptureSourcePolicyTests: \(failures) failed")
    exit(1)
}
print("CaptureSourcePolicyTests: all passed")
