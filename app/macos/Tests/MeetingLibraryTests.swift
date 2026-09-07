import AVFoundation
import Foundation

var failures = 0
func check(_ name: String, _ condition: @autoclosure () -> Bool) {
    let passed = condition()
    print("\(passed ? "PASS" : "FAIL"): \(name)")
    if !passed { failures += 1 }
}

guard CommandLine.arguments.count == 2 else {
    print("expected a temporary output directory")
    exit(2)
}
let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)

var utc = Calendar(identifier: .gregorian)
utc.timeZone = TimeZone(secondsFromGMT: 0)!
let posix = Locale(identifier: "en_US_POSIX")
let policy = MeetingLibraryPolicy.self

/// ICU sets "8:00 AM" with a NARROW NO-BREAK SPACE (U+202F) before the
/// meridiem. That is correct typography on screen and invisible in a source
/// file, so the checks below compare with it folded to a plain space.
func plain(_ s: String) -> String { s.replacingOccurrences(of: "\u{202F}", with: " ") }

// ---------------------------------------------------------------------------
// 1. The recorder's own manifest is what the library reads. No hand-written
//    JSON here: MeetingArchive writes the file, the library decodes it, and the
//    two can only agree on shape by actually meeting.
let archive = try MeetingArchive(detectedBundleID: "us.zoom.xos", rootURL: root)
let start = Date(timeIntervalSince1970: 1_800_000_000)
archive.append(MeetingTranscriptLine(text: "Shall we start?", channel: .owner,
                                     startedAt: start.addingTimeInterval(12),
                                     endedAt: start.addingTimeInterval(14)))
archive.append(MeetingTranscriptLine(text: "Yes, go ahead.", channel: .system,
                                     startedAt: start.addingTimeInterval(15),
                                     endedAt: start.addingTimeInterval(16)))
let finished = DispatchSemaphore(value: 0)
archive.finish { _ in finished.signal() }
_ = finished.wait(timeout: .now() + 5)

let manifestData = try Data(contentsOf: archive.directoryURL.appendingPathComponent(policy.manifestName))
let fromDisk = try policy.record(manifest: manifestData, sidecar: nil,
                                 directoryURL: archive.directoryURL)
check("the recorder's manifest decodes into a record",
      fromDisk.transcript.count == 2 && fromDisk.detectedBundleID == "us.zoom.xos")
check("provenance survives the round trip",
      fromDisk.transcript.map(\.channel) == [.owner, .system])
check("a finished archive has an end", fromDisk.endedAt != nil)
check("no sidecar means no title and empty notes",
      fromDisk.ownerTitle == nil && fromDisk.notes.isEmpty)

// A manifest with a key the recorder adds tomorrow still decodes today.
var loosened = try JSONSerialization.jsonObject(with: manifestData) as! [String: Any]
loosened["somethingNew"] = ["a": 1]
let loosenedData = try JSONSerialization.data(withJSONObject: loosened)
check("an unknown manifest key is ignored",
      (try? policy.record(manifest: loosenedData, sidecar: nil,
                          directoryURL: archive.directoryURL)) != nil)

// ---------------------------------------------------------------------------
// 2. The owner's half: owner.json round-trips, and a corrupt one costs only
//    the owner's words, never the meeting.
let sidecar = MeetingSidecar(title: "Pricing call", notes: "Follow up on tiers.")
let sidecarData = try policy.sidecarData(sidecar)
let withSidecar = try policy.record(manifest: manifestData, sidecar: sidecarData,
                                    directoryURL: archive.directoryURL)
check("the sidecar's title and notes land on the record",
      withSidecar.ownerTitle == "Pricing call" && withSidecar.notes == "Follow up on tiers.")
check("sidecar(of:) reproduces what was written",
      policy.sidecar(of: withSidecar) == sidecar)
let corrupt = try policy.record(manifest: manifestData, sidecar: Data("{not json".utf8),
                                directoryURL: archive.directoryURL)
check("a corrupt sidecar leaves the meeting readable",
      corrupt.transcript.count == 2 && corrupt.notes.isEmpty)
check("a whitespace title is no title",
      policy.sidecar(of: MeetingRecord(id: UUID(), directoryURL: root, startedAt: start,
                                       endedAt: nil, detectedBundleID: nil, transcript: [],
                                       ownerTitle: "   \n", notes: "")).title == nil)

// ---------------------------------------------------------------------------
// 3. Naming: the owner's word, then the app's label, then "Meeting". Never
//    a guess from the transcript.
func record(app: String?, title: String? = nil, notes: String = "",
            startedAt: Date = start, endedAt: Date? = start.addingTimeInterval(2_520),
            lines: [MeetingTranscriptLine] = []) -> MeetingRecord {
    MeetingRecord(id: UUID(), directoryURL: root, startedAt: startedAt, endedAt: endedAt,
                  detectedBundleID: app, transcript: lines, ownerTitle: title, notes: notes)
}
check("a known app labels the meeting", policy.title(for: record(app: "us.zoom.xos")) == "Zoom meeting")
check("Teams' two identifiers both label", policy.appLabel(bundleID: "com.microsoft.teams2") == "Teams")
check("an unknown app is just a meeting", policy.title(for: record(app: "com.example.thing")) == "Meeting")
check("no app is just a meeting", policy.title(for: record(app: nil)) == "Meeting")
check("the owner's title wins", policy.title(for: record(app: "us.zoom.xos", title: "Board prep")) == "Board prep")
check("a blank owner title does not win", policy.title(for: record(app: "us.zoom.xos", title: "  ")) == "Zoom meeting")
check("the sides are You and Others",
      policy.speakerLabel(.owner) == "You" && policy.speakerLabel(.system) == "Others")

// ---------------------------------------------------------------------------
// 4. Time. Durations in words, clocks as elapsed time, and the day headings.
check("a finished meeting's length is end minus start",
      policy.duration(of: record(app: nil)) == 2_520)
let unfinished = record(app: nil, endedAt: nil, lines: [
    MeetingTranscriptLine(text: "a", channel: .owner, startedAt: start.addingTimeInterval(5),
                          endedAt: start.addingTimeInterval(9)),
    MeetingTranscriptLine(text: "b", channel: .system, startedAt: start.addingTimeInterval(1),
                          endedAt: start.addingTimeInterval(30)),
])
check("an unfinished meeting's length is the last instant heard",
      policy.duration(of: unfinished) == 30)
check("an unfinished, silent meeting has no length",
      policy.duration(of: record(app: nil, endedAt: nil)) == nil)
check("seconds read as under a minute", policy.durationWords(42) == "under a minute")
check("minutes read as min", policy.durationWords(2_520) == "42 min")
check("a whole hour reads as hr", policy.durationWords(3_600) == "1 hr")
check("an hour and change reads both", policy.durationWords(3_900) == "1 hr 5 min")
check("the clock is elapsed mm:ss", policy.clock(start.addingTimeInterval(725), from: start) == "12:05")
check("the clock grows an hour field", policy.clock(start.addingTimeInterval(3_725), from: start) == "1:02:05")
check("a line before the start clocks at zero", policy.clock(start.addingTimeInterval(-3), from: start) == "00:00")

// 1_800_000_000 is 2027-01-15 08:00:00 UTC, a Friday.
let now = start.addingTimeInterval(6 * 3_600)
func day(_ hoursAgo: Double) -> String {
    policy.dayLabel(for: now.addingTimeInterval(-hoursAgo * 3_600), now: now,
                    calendar: utc, locale: posix)
}
check("this morning is Today", day(6) == "Today")
check("last night is Yesterday", day(20) == "Yesterday")
check("three days ago is a weekday", day(72) == "Tuesday")
check("six days ago is still a weekday", day(6 * 24) == "Saturday")
check("seven days ago is a date", day(7 * 24) == "January 8")
check("last year carries its year", day(200 * 24) == "June 29, 2026")
check("time of day in the reader's clock",
      plain(policy.timeOfDay(start, calendar: utc, locale: posix)) == "8:00 AM")

// ---------------------------------------------------------------------------
// 5. Order and grouping: newest first, sectioned by day, ties broken stably.
let a = record(app: nil, startedAt: now.addingTimeInterval(-3_600))
let b = record(app: nil, startedAt: now.addingTimeInterval(-30 * 3_600))
let c = record(app: nil, startedAt: now.addingTimeInterval(-2 * 3_600))
let groups = policy.grouped([b, a, c], now: now, calendar: utc, locale: posix)
check("groups are newest first", groups.map(\.label) == ["Today", "Yesterday"])
check("today's meetings are newest first inside the day",
      groups[0].records.map(\.id) == [a.id, c.id])
let tie1 = record(app: nil, startedAt: start), tie2 = record(app: nil, startedAt: start)
let tied = policy.sortedNewestFirst([tie2, tie1])
check("a tie in start time is broken the same way every time",
      tied == policy.sortedNewestFirst([tie1, tie2]))

// ---------------------------------------------------------------------------
// 6. Export. Notes first when there are any; every line with its side.
let exported = policy.markdown(for: record(app: "us.zoom.xos", title: "Pricing call",
                                           notes: "Follow up on tiers.",
                                           lines: fromDisk.transcript),
                               calendar: utc, locale: posix)
check("export leads with the title", exported.hasPrefix("# Pricing call\n"))
check("export carries the date, length and app",
      plain(exported).contains("Friday, January 15, 2027 at 8:00 AM · 42 min · on Zoom"))
check("export carries the notes under their own heading",
      exported.contains("## Notes\n\nFollow up on tiers.\n"))
check("export lists both sides with clocks",
      exported.contains("**You** 00:12  Shall we start?") &&
      exported.contains("**Others** 00:15  Yes, go ahead."))
let bare = policy.markdown(for: record(app: nil), calendar: utc, locale: posix)
check("no notes means no Notes heading", !bare.contains("## Notes"))
check("no lines is said plainly", bare.contains("_Nothing was transcribed._"))

print(failures == 0 ? "all meeting-library checks passed" : "\(failures) meeting-library check(s) failed")
exit(failures == 0 ? 0 : 1)
