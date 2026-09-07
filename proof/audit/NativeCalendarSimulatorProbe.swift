import SwiftUI
import EventKit

/// Built only by the isolated proof script, never linked into Anticipy.
@main
struct CalendarProbe: App {
    var body: some Scene {
        WindowGroup { Text("Isolated calendar proof").task { await prove() } }
    }

    @MainActor
    func prove() async {
        var result: [String: Any] = ["passed": false, "personal_data_used": false]
        let store = EKEventStore()
        do {
            let granted = try await store.requestFullAccessToEvents()
            guard granted else { throw NativeCalendarWorkflow.Failure.malformed }
            guard let source = store.sources.first(where: { $0.sourceType == .local })
                ?? store.defaultCalendarForNewEvents?.source else {
                throw NSError(domain: "CalendarProbe", code: 1,
                              userInfo: [NSLocalizedDescriptionKey: "No writable simulator calendar source"])
            }
            let calendar = EKCalendar(for: .event, eventStore: store)
            calendar.source = source
            calendar.title = "Anticipy isolated execution proof"
            try store.saveCalendar(calendar, commit: true)
            defer { try? store.removeCalendar(calendar, commit: true) }
            let target = CalendarHandPolicy.Target(identifier: calendar.calendarIdentifier,
                title: calendar.title, landsOnlyOnThisDevice: source.sourceType == .local)
            let start = Date(timeIntervalSince1970: floor(Date().timeIntervalSince1970) + 86400)
            let end = start.addingTimeInterval(3600)
            let marker = UUID().uuidString
            let window = CalendarHandPolicy.Window(from: start.addingTimeInterval(-86400),
                                                    to: end.addingTimeInterval(86400))
            let write = CalendarHandPolicy.Write(jobID: "isolated", planID: "isolated",
                planVersion: 1, ourRef: marker,
                stamp: .url(CalendarHandPolicy.stampValue(for: marker)),
                title: "Anticipy isolated native calendar fixture", start: start, end: end,
                target: target, undoWindow: window)
            let adapter = EventKitCalendarStore()
            let outcome = try NativeCalendarExecution.execute(.write(write), store: adapter)
            _ = try NativeCalendarExecution.execute(.write(write), store: adapter)
            let newStore = EventKitCalendarStore()
            _ = try NativeCalendarExecution.execute(.write(write), store: newStore, verifyOnly: true)
            let undo = CalendarHandPolicy.Undo(jobID: "isolated-undo", planID: "isolated-undo",
                planVersion: 1, ourRef: marker, stamp: write.stamp,
                searchWindow: window, target: target)
            let removed = try NativeCalendarExecution.execute(.undo(undo), store: newStore)
            guard try EventKitCalendarStore().matching(
                stamp: CalendarHandPolicy.stampValue(for: marker), window: window,
                target: target).isEmpty else { throw NativeCalendarExecution.Failure.readbackFailed }
            result = ["passed": true, "personal_data_used": false,
                      "checks": ["EventKit save and title/time/URL readback",
                                 "repeat write yields exactly one event",
                                 "new EventKit instance reads persistent marker",
                                 "marker-based undo and independent absence readback"],
                      "write_evidence": outcome.evidence, "undo_evidence": removed.evidence]
        } catch { result["error"] = String(describing: error) }
        let url = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("calendar-proof.json")
        try? JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys])
            .write(to: url, options: .atomic)
    }
}
