import Foundation

// Gap-law and engine-policy checks. Pure Foundation, run by
// run_gap_engine_tests.sh. Exit non-zero on the first wrong case.

var failures = 0
func check(_ name: String, _ condition: Bool, _ why: String = "") {
    if condition {
        print("  ok   \(name)")
    } else {
        failures += 1
        print("  FAIL \(name) — \(why)")
    }
}

// ---------------------------------------------------------------- assembler

// Continuous packets are airtime, not gaps.
var asm = OpusFrameAssembler()
for i: UInt16 in 0..<6 { _ = asm.accept(Data([UInt8(i & 0xFF), UInt8(i >> 8), 0, 0xAA])) }
check("continuous stream measures no gap", asm.gapSeconds == 0,
      "a clean stream invented \(asm.gapSeconds)s of gap")

// A packet-index jump is measured airtime: indices 3 -> 8 means packets
// 4,5,6,7 never arrived — four packets, 40 ms.
asm = OpusFrameAssembler()
for i: UInt16 in [0, 1, 2, 3] { _ = asm.accept(Data([UInt8(i & 0xFF), UInt8(i >> 8), 0, 0xAA])) }
_ = asm.accept(Data([UInt8(8), 0, 0, 0xAA]))
check("a 4-packet jump measures 0.040s", abs(asm.gapSeconds - 0.040) < 0.0001,
      "measured \(asm.gapSeconds)")

// Draining clears; a gap reported twice is a lie told once and repeated.
let drained = asm.takeGapSeconds()
check("drain hands the gap over", abs(drained - 0.040) < 0.0001)
check("drain clears the ledger", asm.gapSeconds == 0)

// Gaps accumulate until someone drains them. From index 8: 8->9 is
// continuous, 9->14 skips 10,11,12,13 — four packets, another 40 ms.
for next: UInt16 in [9, 14] { _ = asm.accept(Data([UInt8(next & 0xFF), UInt8(next >> 8), 0, 0xAA])) }
check("gaps accumulate across events", abs(asm.gapSeconds - 0.040) < 0.0001,
      "measured \(asm.gapSeconds), wanted the four packets the 9-to-14 jump skipped")

// The 16-bit counter wraps, and the distance ACROSS the wrap is the truth:
// 65534 -> 65535 is continuous; 65535 -> 1 skips packet 0 and 65535... no —
// it skips 0 only if 65535 arrived. delta = 1 - 65535 + 65536 = 2: one
// missing packet, 10 ms.
asm = OpusFrameAssembler()
_ = asm.accept(Data([UInt8(65534 & 0xFF), UInt8(65534 >> 8), 0, 0xAA]))
_ = asm.accept(Data([UInt8(65535 & 0xFF), UInt8(65535 >> 8), 0, 0xAA]))
_ = asm.accept(Data([0, 0, 0, 0xAA]))
check("the wrap boundary is continuous", asm.gapSeconds == 0,
      "a wrap counted as a gap is a gap that did not happen")
_ = asm.accept(Data([2, 0, 0, 0xAA]))
check("one missing packet across the wrap is 0.010s", abs(asm.gapSeconds - 0.010) < 0.0001,
      "measured \(asm.gapSeconds)")

// A frame killed by a bad counter is a dropped FRAME, not measured airtime —
// the packet index did not jump, so no seconds are claimed.
asm = OpusFrameAssembler()
_ = asm.accept(Data([0, 0, 0, 0xAA]))      // counter 0: frame starts
_ = asm.accept(Data([1, 0, 5, 0xAA]))      // counter 5, expected 1: frame dies
check("a bad counter drops the frame, invents no gap",
      asm.droppedFrames == 1 && asm.gapSeconds == 0,
      "dropped \(asm.droppedFrames), gap \(asm.gapSeconds)")

// ----------------------------------------------------------------- markers

check("sub-second says so", GapMarker.text(0.4) == "[unavailable under 1s]")
check("seconds", GapMarker.text(45) == "[unavailable 45s]")
check("minutes and seconds", GapMarker.text(272) == "[unavailable 4m 32s]")
check("hours", GapMarker.text(3661) == "[unavailable 1h 1m 1s]")
check("nothing negative is ever a time", GapMarker.text(-3) == "[unavailable under 1s]")

// ------------------------------------------------------------------ policy

// The flag wins over the OS check — a hatch that loses is decoration.
UserDefaults.standard.set(true, forKey: ListenEnginePolicy.legacyFlagKey)
check("the operator's flag forces legacy on a 26 phone",
      ListenEnginePolicy.usesAnalyzer(on: (26, 0, 0)) == false)
check("and on a 15 phone, which never had the choice",
      ListenEnginePolicy.usesAnalyzer(on: (15, 4, 0)) == false)

// Flag unset: the OS version decides. The runner here is a Mac, so inject.
UserDefaults.standard.removeObject(forKey: ListenEnginePolicy.legacyFlagKey)
check("iOS 26 runs the analyzer", ListenEnginePolicy.usesAnalyzer(on: (26, 0, 0)) == true)
check("iOS 26.1 runs the analyzer", ListenEnginePolicy.usesAnalyzer(on: (26, 1, 2)) == true)
check("iOS 25 never runs it", ListenEnginePolicy.usesAnalyzer(on: (25, 9, 9)) == false)

if failures > 0 {
    print("\(failures) case(s) came back wrong.")
    exit(1)
}
print("the gap law holds: measured, drained, marked, never spoken through")
