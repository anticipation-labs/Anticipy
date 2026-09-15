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

// Sequence numbers count BLE notifications, not Opus frames or milliseconds.
var asm = OpusFrameAssembler()
for i: UInt16 in 0..<6 { _ = asm.accept(Data([UInt8(i & 0xFF), UInt8(i >> 8), 0, 0xAA])) }
check("continuous stream reports no gap", asm.takeGap() == nil)

// Four absent notifications are known; their duration and frame count are not.
asm = OpusFrameAssembler()
for i: UInt16 in [0, 1, 2, 3] { _ = asm.accept(Data([UInt8(i & 0xFF), UInt8(i >> 8), 0, 0xAA])) }
_ = asm.accept(Data([UInt8(8), 0, 0, 0xAA]))
let drained = asm.takeGap()
check("four absent notifications are counted without inventing duration",
      drained == OpusTransportGap(missingNotifications: 4, discardedFrames: 1))
check("drain clears the transport ledger", asm.takeGap() == nil)

for next: UInt16 in [9, 14, 17] { _ = asm.accept(Data([UInt8(next & 0xFF), UInt8(next >> 8), 0, 0xAA])) }
check("notification and discarded-frame counts accumulate until drained",
      asm.takeGap() == OpusTransportGap(missingNotifications: 6, discardedFrames: 2))

asm = OpusFrameAssembler()
_ = asm.accept(Data([UInt8(65534 & 0xFF), UInt8(65534 >> 8), 0, 0xAA]))
_ = asm.accept(Data([UInt8(65535 & 0xFF), UInt8(65535 >> 8), 0, 0xAA]))
_ = asm.accept(Data([0, 0, 0, 0xAA]))
check("the wrap boundary is continuous", asm.takeGap() == nil)
_ = asm.accept(Data([2, 0, 0, 0xAA]))
check("one missing notification across wrap has unknown duration",
      asm.takeGap() == OpusTransportGap(missingNotifications: 1, discardedFrames: 1))

asm = OpusFrameAssembler()
_ = asm.accept(Data([0, 0, 0, 0xAA]))      // counter 0: frame starts
_ = asm.accept(Data([1, 0, 5, 0xAA]))      // counter 5, expected 1: frame dies
check("bad counter reports discarded frame, not fabricated missing packets",
      asm.takeGap() == OpusTransportGap(missingNotifications: 0, discardedFrames: 1))

// A frame can span multiple notifications at small ATT MTU. Losing two
// fragments says nothing about whether one or several codec frames vanished.
asm = OpusFrameAssembler()
_ = asm.accept(Data([0, 0, 0, 0xAA]))
_ = asm.accept(Data([1, 0, 1, 0xBB]))
_ = asm.accept(Data([4, 0, 4, 0xCC]))
check("fragmented-frame loss reports transport counts only",
      asm.takeGap() == OpusTransportGap(missingNotifications: 2, discardedFrames: 1))
_ = asm.accept(Data([5, 0, 0, 0xDD]))
asm.discardCurrentFrame()
check("disconnect clears diagnostics rather than attributing them to a new session",
      asm.takeGap() == nil)
_ = asm.accept(Data([200, 0, 0, 0xEE]))
check("reconnect has no inferred downtime or missing count", asm.takeGap() == nil)

// ----------------------------------------------------------------- markers

check("the marker prefix is the one the feed reads",
      GapMarker.unknownDuration.hasPrefix(GapMarker.prefix))
check("unknown transport duration is explicit",
      GapMarker.unknownDuration == "[unavailable — audio interrupted; duration unknown]")

// Actual production journal and tally, not a parallel model of those types.
let when = Date(timeIntervalSince1970: 1_756_000_000)
let journalURL = FileManager.default.temporaryDirectory.appendingPathComponent("gap-journal-\(UUID().uuidString).log")
let journal = ListenJournal(limit: 20, fileURL: journalURL)
defer { journal.clear() }
let event = ListenEvent.transportGap(missingNotifications: 4, discardedFrames: 1)
journal.record(event, at: when)
check("transport counts survive the durable journal format",
      journal.entries.first.flatMap(ListenJournal.parse)?.1 == event)
check("journal says duration unknown and never milliseconds",
      journal.entries.first?.contains("duration unknown") == true
          && journal.entries.first?.contains(" ms ") == false)
for bad in ["transportGap  -1 missing notifications, 1 discarded frames, duration unknown",
            "transportGap  1 missing notifications, -1 discarded frames, duration unknown",
            "transportGap  0 missing notifications, 0 discarded frames, duration unknown",
            "transportGap  nope missing notifications, 1 discarded frames, duration unknown",
            "transportGap  1 missing notifications, 1 discarded frames, duration 10ms",
            "transportGap  1 missing notifications, 1 discarded frames, duration unknown extra"] {
    check("malformed transport journal entry refuses: \(bad)",
          ListenJournal.parse("2025-08-24T08:00:00.000Z  " + bad) == nil)
}
let day = ListenTally.of([
    (when, .sessionStarted),
    (when.addingTimeInterval(10), .airtimeLost(milliseconds: 20)),
    (when.addingTimeInterval(20), event),
    (when.addingTimeInterval(30), .transportGap(missingNotifications: 0, discardedFrames: 1)),
], now: when.addingTimeInterval(60))
check("legacy airtime totals remain separate and unchanged",
      day.airtimeLostMilliseconds == 20 && day.airtimeGaps == 1)
check("new gaps count missing notifications and discarded frames separately",
      day.transportGaps == 2 && day.missingNotifications == 4 && day.transportDiscardedFrames == 2)
check("transport gaps cannot imply heard speech, a stop or shorter silence",
      day.wordsFlushed == 0 && day.longestSilenceSeconds == 60 && day.sessions == 1)
let overflowing = ListenTally.of([
    (when, .transportGap(missingNotifications: Int.max, discardedFrames: Int.max)),
    (when.addingTimeInterval(1), .transportGap(missingNotifications: 1, discardedFrames: 1)),
])
check("overflow is an unavailable count, never a crash or wrapped exact total",
      overflowing.missingNotifications == nil && overflowing.transportDiscardedFrames == nil
          && overflowing.transportGaps == 2)
let invalidCounts = ListenTally.of([
    (when, .transportGap(missingNotifications: -1, discardedFrames: -1)),
    (when.addingTimeInterval(1), .transportGap(missingNotifications: 2, discardedFrames: 2)),
])
check("invalid counts cannot subtract loss or recover a fictitious aggregate",
      invalidCounts.missingNotifications == nil && invalidCounts.transportDiscardedFrames == nil)

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
