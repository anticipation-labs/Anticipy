// MeetingLibrary — how one recorded meeting is READ back and SHOWN.
//
// Two authors write into a meeting folder, and this file keeps them apart.
// The recorder (MeetingArchive) writes meeting.json and the audio tracks; it
// is the only thing that ever writes them, and nothing here edits a byte of
// it. The owner writes a title and notes; those live in owner.json beside it,
// and this is the only layer that writes THAT file. A meeting folder is
// therefore always readable by the recorder's own tests, and a library rebuilt
// from disk after a crash loses nothing either author wrote.
//
// LAW 1: nothing in here decides what a meeting MEANS. A title is what the
// owner typed, or the name of the app that held the call plus the word
// "meeting". Labels for bundle identifiers are labels — the same list-as-label
// rule MeetingOfferPolicy already lives under — and there is no rule that
// turns a transcript into a summary. Summaries belong to a model with the
// whole context, and that model is the brain the transcript is sent to.
import Foundation

/// One meeting as the library shows it.
public struct MeetingRecord: Identifiable, Equatable, Sendable {
    public let id: UUID
    public let directoryURL: URL
    public let startedAt: Date
    /// nil while a meeting is being recorded, and nil forever for a session
    /// the app never got to close. `MeetingLibraryPolicy.duration` reads the
    /// transcript's last instant in that case rather than inventing an end.
    public let endedAt: Date?
    public let detectedBundleID: String?
    public let transcript: [MeetingTranscriptLine]
    /// What the owner named it, if anything. Whitespace-only is "nothing".
    public var ownerTitle: String?
    public var notes: String

    public init(id: UUID, directoryURL: URL, startedAt: Date, endedAt: Date?,
                detectedBundleID: String?, transcript: [MeetingTranscriptLine],
                ownerTitle: String? = nil, notes: String = "") {
        self.id = id
        self.directoryURL = directoryURL
        self.startedAt = startedAt
        self.endedAt = endedAt
        self.detectedBundleID = detectedBundleID
        self.transcript = transcript
        self.ownerTitle = ownerTitle
        self.notes = notes
    }
}

/// The owner's half of a meeting folder: owner.json.
public struct MeetingSidecar: Codable, Equatable, Sendable {
    public var title: String?
    public var notes: String

    public init(title: String? = nil, notes: String = "") {
        self.title = title
        self.notes = notes
    }
}

public enum MeetingLibraryPolicy {
    /// The recorder's file. Read here, never written.
    public static let manifestName = "meeting.json"
    /// The owner's file. Written here, never by the recorder.
    public static let sidecarName = "owner.json"

    /// The part of the recorder's manifest the library needs. The track lists
    /// are deliberately not decoded: the library shows words, and a manifest
    /// with an extra key the recorder adds tomorrow still decodes today.
    private struct Manifest: Decodable {
        let id: UUID
        let startedAt: Date
        let endedAt: Date?
        let detectedBundleID: String?
        let transcript: [MeetingTranscriptLine]
    }

    private static var decoder: JSONDecoder {
        let d = JSONDecoder()
        d.dateDecodingStrategy = .iso8601
        return d
    }

    private static var encoder: JSONEncoder {
        let e = JSONEncoder()
        e.outputFormatting = [.prettyPrinted, .sortedKeys]
        return e
    }

    /// Builds a record from the bytes of both files. A missing or unreadable
    /// sidecar is an empty one: the owner's notes cannot make a meeting
    /// unreadable, and a corrupt owner.json loses at most the owner's title.
    public static func record(manifest: Data, sidecar: Data?,
                              directoryURL: URL) throws -> MeetingRecord {
        let m = try decoder.decode(Manifest.self, from: manifest)
        let side = sidecar.flatMap { try? decoder.decode(MeetingSidecar.self, from: $0) }
            ?? MeetingSidecar()
        return MeetingRecord(id: m.id, directoryURL: directoryURL,
                             startedAt: m.startedAt, endedAt: m.endedAt,
                             detectedBundleID: m.detectedBundleID,
                             transcript: m.transcript,
                             ownerTitle: side.title, notes: side.notes)
    }

    public static func sidecarData(_ sidecar: MeetingSidecar) throws -> Data {
        try encoder.encode(sidecar)
    }

    public static func sidecar(of record: MeetingRecord) -> MeetingSidecar {
        MeetingSidecar(title: cleanTitle(record.ownerTitle), notes: record.notes)
    }

    // ------------------------------------------------------------- naming

    /// A LABEL for the app that held the call, for the title and nothing
    /// else. Unknown apps get no label rather than a mangled identifier:
    /// "xos meeting" is worse than "Meeting".
    public static func appLabel(bundleID: String?) -> String? {
        guard let bundleID else { return nil }
        let labels: [String: String] = [
            "us.zoom.xos": "Zoom",
            "com.google.Chrome": "Chrome",
            "com.google.Chrome.canary": "Chrome",
            "com.apple.Safari": "Safari",
            "org.mozilla.firefox": "Firefox",
            "com.brave.Browser": "Brave",
            "company.thebrowser.Browser": "Arc",
            "com.microsoft.edgemac": "Edge",
            "com.microsoft.teams2": "Teams",
            "com.microsoft.teams": "Teams",
            "com.apple.FaceTime": "FaceTime",
            "com.tinyspeck.slackmacgap": "Slack",
            "com.hnc.Discord": "Discord",
            "com.cisco.webexmeetingsapp": "Webex",
            "com.webex.meetingmanager": "Webex",
            "com.skype.skype": "Skype",
            "com.apple.MobileSMS": "Messages",
            "com.loom.desktop": "Loom",
        ]
        return labels[bundleID]
    }

    static func cleanTitle(_ raw: String?) -> String? {
        guard let raw else { return nil }
        let t = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return t.isEmpty ? nil : t
    }

    /// The owner's title if there is one, else the app's label and the word
    /// "meeting", else "Meeting". A title is never guessed from the words.
    public static func title(for record: MeetingRecord) -> String {
        if let own = cleanTitle(record.ownerTitle) { return own }
        if let app = appLabel(bundleID: record.detectedBundleID) { return "\(app) meeting" }
        return "Meeting"
    }

    public static func speakerLabel(_ channel: MeetingCaptureChannel) -> String {
        switch channel {
        case .owner: return "You"
        case .system: return "Others"
        }
    }

    // ------------------------------------------------------------- time

    /// How long the meeting ran. An unfinished session's length is the last
    /// instant anybody was heard, which is the last fact on disk; nil when
    /// there is no such fact.
    public static func duration(of record: MeetingRecord) -> TimeInterval? {
        if let end = record.endedAt { return max(0, end.timeIntervalSince(record.startedAt)) }
        guard let last = record.transcript.map(\.endedAt).max() else { return nil }
        return max(0, last.timeIntervalSince(record.startedAt))
    }

    public static func durationWords(_ seconds: TimeInterval) -> String {
        let whole = Int(seconds.rounded(.down))
        if whole < 60 { return "under a minute" }
        let minutes = whole / 60
        if minutes < 60 { return "\(minutes) min" }
        let hours = minutes / 60
        let rest = minutes % 60
        return rest == 0 ? "\(hours) hr" : "\(hours) hr \(rest) min"
    }

    /// "12:05" from the meeting's start; "1:02:05" past an hour. Elapsed, not
    /// wall clock, so a transcript reads the same in any time zone.
    public static func clock(_ instant: Date, from start: Date) -> String {
        let total = max(0, Int(instant.timeIntervalSince(start).rounded(.down)))
        let h = total / 3600, m = (total % 3600) / 60, s = total % 60
        if h > 0 { return String(format: "%d:%02d:%02d", h, m, s) }
        return String(format: "%02d:%02d", m, s)
    }

    /// The sidebar's section headings. Relative words for the last week, a
    /// date after that.
    public static func dayLabel(for date: Date, now: Date,
                                calendar: Calendar, locale: Locale) -> String {
        if calendar.isDate(date, inSameDayAs: now) { return "Today" }
        if let yesterday = calendar.date(byAdding: .day, value: -1, to: now),
           calendar.isDate(date, inSameDayAs: yesterday) { return "Yesterday" }
        let f = DateFormatter()
        f.calendar = calendar
        f.timeZone = calendar.timeZone
        f.locale = locale
        // Counted in calendar days, not hours: a meeting six days ago at any
        // hour is "Saturday", and the seventh day back is a date. Hours would
        // move the boundary with the time of day the window happens to open.
        let daysBack = calendar.dateComponents([.day], from: calendar.startOfDay(for: date),
                                               to: calendar.startOfDay(for: now)).day ?? 0
        if daysBack > 0, daysBack < 7 {
            f.setLocalizedDateFormatFromTemplate("EEEE")
            return f.string(from: date)
        }
        let sameYear = calendar.component(.year, from: date) == calendar.component(.year, from: now)
        f.setLocalizedDateFormatFromTemplate(sameYear ? "d MMMM" : "d MMMM yyyy")
        return f.string(from: date)
    }

    /// "2:30 PM", in the reader's own clock.
    public static func timeOfDay(_ date: Date, calendar: Calendar, locale: Locale) -> String {
        let f = DateFormatter()
        f.calendar = calendar
        f.timeZone = calendar.timeZone
        f.locale = locale
        f.setLocalizedDateFormatFromTemplate("jmm")
        return f.string(from: date)
    }

    /// "Tuesday, 8 September 2026 at 2:30 PM".
    public static func longDate(_ date: Date, calendar: Calendar, locale: Locale) -> String {
        let f = DateFormatter()
        f.calendar = calendar
        f.timeZone = calendar.timeZone
        f.locale = locale
        f.setLocalizedDateFormatFromTemplate("EEEEdMMMMyyyyjmm")
        return f.string(from: date)
    }

    // ------------------------------------------------------------- order

    public static func sortedNewestFirst(_ records: [MeetingRecord]) -> [MeetingRecord] {
        records.sorted { a, b in
            if a.startedAt != b.startedAt { return a.startedAt > b.startedAt }
            return a.id.uuidString < b.id.uuidString
        }
    }

    public struct DayGroup: Equatable, Sendable {
        public let label: String
        public let records: [MeetingRecord]
    }

    /// Newest first, sectioned by day, with each section keeping its order.
    public static func grouped(_ records: [MeetingRecord], now: Date,
                               calendar: Calendar, locale: Locale) -> [DayGroup] {
        var groups: [DayGroup] = []
        for record in sortedNewestFirst(records) {
            let label = dayLabel(for: record.startedAt, now: now,
                                 calendar: calendar, locale: locale)
            if let last = groups.last, last.label == label {
                groups[groups.count - 1] = DayGroup(label: label,
                                                    records: last.records + [record])
            } else {
                groups.append(DayGroup(label: label, records: [record]))
            }
        }
        return groups
    }

    // ------------------------------------------------------------- export

    /// The meeting as a Markdown document the owner can paste anywhere. Notes
    /// first when there are any, because they are the owner's own words;
    /// then every line with its side and its clock.
    public static func markdown(for record: MeetingRecord, calendar: Calendar,
                                locale: Locale) -> String {
        var out: [String] = []
        out.append("# \(title(for: record))")
        var meta = [longDate(record.startedAt, calendar: calendar, locale: locale)]
        if let seconds = duration(of: record) { meta.append(durationWords(seconds)) }
        if let app = appLabel(bundleID: record.detectedBundleID) { meta.append("on \(app)") }
        out.append(meta.joined(separator: " · "))
        out.append("")
        let notes = record.notes.trimmingCharacters(in: .whitespacesAndNewlines)
        if !notes.isEmpty {
            out.append("## Notes")
            out.append("")
            out.append(notes)
            out.append("")
        }
        out.append("## Transcript")
        out.append("")
        if record.transcript.isEmpty {
            out.append("_Nothing was transcribed._")
        }
        for line in record.transcript {
            let who = speakerLabel(line.channel)
            let at = clock(line.startedAt, from: record.startedAt)
            out.append("**\(who)** \(at)  \(line.text)")
        }
        out.append("")
        return out.joined(separator: "\n")
    }
}
