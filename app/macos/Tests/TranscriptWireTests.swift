// Checks for the row a Mac transcript line becomes on the wire — the same row
// the phone posts, so the brain cannot tell the two ears apart except by the
// `source` column that says which one it was.
//
// Run: sh app/macos/Tests/run_transcript_wire_tests.sh
import Foundation

var failures = 0
func check(_ name: String, _ ok: Bool) {
    print("\(ok ? "PASS" : "FAIL"): \(name)")
    if !ok { failures += 1 }
}

let started = Date(timeIntervalSince1970: 1_800_000_000.25)
let ended = started.addingTimeInterval(3.5)
let row = TranscriptWire.body(text: "We should ship Tuesday.", speaker: "owner",
                              startedAt: started, endedAt: ended,
                              ownerRef: "owner123", deviceID: "mac-b151")

// ===================================================================
// The ear
// ===================================================================
check("the Mac names itself as one ear, \"mac\"", TranscriptWire.source == "mac")
check("the row carries that ear", row["source"] == "mac")
check("the side of the call is not the ear",
      TranscriptWire.source != "mac_mic" && TranscriptWire.source != "mac_system")
check("the microphone side is the owner",
      TranscriptWire.speaker(for: .owner) == "owner")
check("the system-audio side is other people",
      TranscriptWire.speaker(for: .system) == "other")
check("the speaker travels on the row", row["speaker"] == "owner")

// ===================================================================
// The device names the build, as the phone's does
// ===================================================================
check("the device id names the build", TranscriptWire.deviceID(build: "151") == "mac-b151")
check("a bundle with no number does not invent one",
      TranscriptWire.deviceID(build: nil) == "mac-b?"
        && TranscriptWire.deviceID(build: "  ") == "mac-b?")
check("the prefix is not the probe's and not the phone's",
      !TranscriptWire.devicePrefix.hasPrefix("e2e-")
        && !TranscriptWire.devicePrefix.hasPrefix("iphone-")
        && TranscriptWire.devicePrefix != "anticipy-brain")

// ===================================================================
// The columns are the phone's, and only the phone's
// ===================================================================
let phoneColumns: Set<String> = [
    "device_id", "kind", "text", "decision", "goal", "owner_ref", "source",
    "speaker", "capture_started_at", "spoken_at", "capture_ended_at",
]
check("the row has exactly the columns the phone sends — the Worker 400s any other",
      Set(row.keys) == phoneColumns)
check("the row is a transcript", row["kind"] == "transcript")
check("the words travel untouched", row["text"] == "We should ship Tuesday.")
check("the owner is stamped", row["owner_ref"] == "owner123")
check("the device is stamped", row["device_id"] == "mac-b151")
check("decision and goal are empty, never absent",
      row["decision"] == "" && row["goal"] == "")

// ===================================================================
// The envelope: two instants, three columns
// ===================================================================
check("capture_started_at is the start", row["capture_started_at"] == "2027-01-15T08:00:00.250Z")
check("spoken_at is the SAME instant as the start",
      row["spoken_at"] == row["capture_started_at"])
check("capture_ended_at is the end", row["capture_ended_at"] == "2027-01-15T08:00:03.750Z")
check("the clock keeps fractional seconds",
      row["capture_started_at"]?.contains(".250Z") == true)
check("the clock is UTC", row["capture_started_at"]?.hasSuffix("Z") == true)

let backwards = TranscriptWire.body(text: "x", speaker: "other",
                                    startedAt: ended, endedAt: started,
                                    ownerRef: "o", deviceID: "d")
check("instants that came back out of order collapse onto the end",
      backwards["capture_started_at"] == backwards["capture_ended_at"]
        && backwards["capture_ended_at"] == "2027-01-15T08:00:00.250Z")
let instant = TranscriptWire.body(text: "x", speaker: "other",
                                  startedAt: started, endedAt: started,
                                  ownerRef: "o", deviceID: "d")
check("one instant named twice is a zero-length span, not an error",
      instant["capture_started_at"] == instant["capture_ended_at"])

// The line policy's own envelope survives the trip: what MeetingLinePolicy
// measured is what leaves.
var policy = MeetingLinePolicy(silenceSeconds: 2.5, ceilingSeconds: 15)
policy.absorbFinal("The other side", at: started)
policy.absorbFinal("is present.", at: started.addingTimeInterval(1))
if let line = policy.take(channel: .system, at: started.addingTimeInterval(4)) {
    let sent = TranscriptWire.body(text: line.text,
                                   speaker: TranscriptWire.speaker(for: line.channel),
                                   startedAt: line.startedAt, endedAt: line.endedAt,
                                   ownerRef: "o", deviceID: "d")
    check("a far-side line leaves as overheard, bracketed by its own finals",
          sent["speaker"] == "other"
            && sent["capture_started_at"] == "2027-01-15T08:00:00.250Z"
            && sent["capture_ended_at"] == "2027-01-15T08:00:01.250Z"
            && sent["text"] == "The other side is present.")
} else {
    check("the line policy hands over a line", false)
}

if failures > 0 {
    print("\(failures) transcript-wire check(s) failed")
    exit(1)
}
print("all transcript-wire checks passed")
