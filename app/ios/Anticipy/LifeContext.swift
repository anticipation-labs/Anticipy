import Foundation
#if os(iOS)
import Contacts
import EventKit
#endif

/// Reading the two things about a person that live on their own phone.
///
/// LOCAL-FIRST POSTURE (`design/LOCAL-FIRST.md:41-43` Rule 5 requires this
/// stated explicitly): the store is read on the device and never leaves it.
/// What travels is the smallest conclusion that works — a handful of sentences
/// like "Dinner with Priya, Thursday 7:30pm" — never the calendar, never the
/// address book. `design/briefs/08-day-zero.md:31-33` fixes the limits: "only
/// the names list and event titles+times for the next ~30 days."
///
/// Nothing in here asks iOS for anything until `ContextGrants` says the person
/// has already said yes on our own screen. That ordering is the product: the OS
/// alert is never the first time somebody hears what she wants.
enum LifeContext {

    // MARK: - Calendar

    /// A month is the horizon that answers "what's coming up" without becoming
    /// a data dump: far enough to catch the thing you half-remember, short
    /// enough that thirty facts is the ceiling.
    static let horizonDays = 30
    /// The store punishes bulk — retrieval is keyword + graph walk with no
    /// embeddings (`brain/memory.py:9`), so fifty rows bury the five that
    /// matter. Hard cap, applied after sorting by date.
    static let maxEvents = 15
    static let maxNames = 40

#if os(iOS)
    /// iOS 17 split calendar access into write-only and full, and the new call
    /// does not exist below 17. The deployment target is 16.0, so both paths
    /// ship. A missing Info.plist key here is a CRASH, not a denial — the keys
    /// are `NSCalendarsFullAccessUsageDescription` (17+) and the deprecated
    /// `NSCalendarsUsageDescription`, which is still required while the floor
    /// is 16.
    static func requestCalendar() async -> Bool {
        let store = EKEventStore()
        if #available(iOS 17.0, *) {
            return (try? await store.requestFullAccessToEvents()) ?? false
        }
        return await withCheckedContinuation { cont in
            store.requestAccess(to: .event) { ok, _ in cont.resume(returning: ok) }
        }
    }

    /// True once iOS will actually hand events over. Checked before every read
    /// rather than remembered, because the person can revoke in iOS Settings
    /// while the app is asleep and our own grant would still say yes.
    static var calendarReadable: Bool {
        let status = EKEventStore.authorizationStatus(for: .event)
        if #available(iOS 17.0, *) { return status == .fullAccess }
        return status == .authorized
    }

    /// Titles and times only. Deliberately NOT: notes, attendees, locations,
    /// organiser addresses, or anything already past.
    static func upcomingEvents(now: Date = Date()) -> [String] {
        guard calendarReadable else { return [] }
        let store = EKEventStore()
        guard let end = Calendar.current.date(byAdding: .day, value: horizonDays, to: now)
        else { return [] }
        let predicate = store.predicateForEvents(withStart: now, end: end, calendars: nil)
        let fmt = DateFormatter()
        fmt.dateFormat = "EEEE d MMMM, h:mma"
        return store.events(matching: predicate)
            .filter { !$0.isAllDay }
            .sorted { $0.startDate < $1.startDate }
            .prefix(maxEvents)
            .compactMap { event in
                let title = quoted(event.title ?? "")
                guard !title.isEmpty else { return nil }
                return "\(title), \(fmt.string(from: event.startDate))"
            }
    }

    /// A calendar title is written by WHOEVER SENT THE INVITATION, so it is
    /// hostile input in the strict sense: anyone who can put a meeting on your
    /// Tuesday can choose these characters. It reaches a prompt downstream, so
    /// it is quoted and flattened here, at the only point that can be sure of
    /// what it is looking at.
    ///
    /// The server fences imported facts as untrusted as well
    /// (`brain/anticipy_core.py` memory_notes). This is the other half of that:
    /// a fence made of text cannot hold if the quoted content can forge line
    /// breaks or the fence's own markers.
    static func quoted(_ raw: String) -> String {
        var text = raw
        // Newlines and control characters let a title pretend to be a new
        // section of whatever it lands in.
        text = text.components(separatedBy: .controlCharacters).joined(separator: " ")
        text = text.components(separatedBy: .newlines).joined(separator: " ")
        // The fence markers, and the quote character that would close ours.
        text = text.replacingOccurrences(of: "---", with: "-")
        text = text.replacingOccurrences(of: "\"", with: "'")
        // Collapse the runs that flattening just created.
        while text.contains("  ") { text = text.replacingOccurrences(of: "  ", with: " ") }
        text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        // A title long enough to hold an argument is not a title. Truncated on
        // a word boundary so the result still reads as a name for something.
        let limit = 120
        if text.count > limit {
            let cut = String(text.prefix(limit))
            text = (cut.lastIndex(of: " ").map { String(cut[..<$0]) } ?? cut) + "…"
        }
        guard !text.isEmpty else { return "" }
        // Quoted, so that even unfenced it reads as a name somebody gave a
        // meeting rather than as a sentence addressed to her.
        return "\"\(text)\""
    }

    // MARK: - Contacts

    /// iOS 18 can return *limited* access, where the person picks a subset.
    /// That needs no special handling here: the only thing wanted is names, and
    /// a shorter list of names is still a list of names.
    static func requestContacts() async -> Bool {
        (try? await CNContactStore().requestAccess(for: .contacts)) ?? false
    }

    static var contactsReadable: Bool {
        let status = CNContactStore.authorizationStatus(for: .contacts)
        if #available(iOS 18.0, *) { return status == .authorized || status == .limited }
        return status == .authorized
    }

    /// Names. The keys requested are the narrowest the framework offers, so a
    /// number or an email is not merely unused — it is never fetched.
    static func names() -> [String] {
        guard contactsReadable else { return [] }
        let keys = [CNContactGivenNameKey, CNContactFamilyNameKey] as [CNKeyDescriptor]
        let request = CNContactFetchRequest(keysToFetch: keys)
        request.sortOrder = .givenName
        var out: [String] = []
        try? CNContactStore().enumerateContacts(with: request) { contact, stop in
            let name = "\(contact.givenName) \(contact.familyName)"
                .trimmingCharacters(in: .whitespaces)
            if !name.isEmpty { out.append(name) }
            if out.count >= maxNames { stop.pointee = true }
        }
        return out
    }

#else
    // The test host is macOS, where neither framework's authorization model
    // exists. The stubs keep the POLICY — the caps, the fact shaping, the
    // gate — compilable and testable off-device, and make it structurally
    // impossible for a host build to invent context it cannot have read.
    static func requestCalendar() async -> Bool { false }
    static var calendarReadable: Bool { false }
    static func upcomingEvents(now: Date = Date()) -> [String] { [] }
    static func requestContacts() async -> Bool { false }
    static var contactsReadable: Bool { false }
    static func names() -> [String] { [] }
#endif

    // MARK: - Facts

    /// The sentences that travel, and nothing else does.
    ///
    /// One fact per event, because a commitment is the unit she acts on. Names
    /// arrive as ONE fact rather than forty, because forty name-facts would
    /// drown keyword recall in exactly the way the store is worst at.
    static func facts(for source: ContextSource, now: Date = Date()) -> [String] {
        // Only the sources that live on this phone have a reader in this file.
        // Mail is not one of them: it is read in the BROWSER, in the
        // foreground, while the person watches (`design/day-zero.md` §2), and
        // its facts arrive by a different path entirely — the worker distils
        // them and they land through `remember_fact()`, never through here. A
        // number here for an off-device source would be this file inventing
        // context it never read, which is the one thing it exists to prevent.
        guard source.isOnDevice else { return [] }
        switch source {
        case .calendar:
            return upcomingEvents(now: now).map { "On their calendar: \($0)." }
        case .contacts:
            let list = names()
            guard !list.isEmpty else { return [] }
            return ["People in their contacts: \(list.joined(separator: ", "))."]
        case .mail:
            // Unreachable — the guard above already returned. Written out
            // rather than folded into a `default`, so that adding a source
            // fails to compile here until somebody decides what it reads
            // instead of silently producing nothing.
            return []
        }
    }
}
