import Foundation
#if os(iOS)
import EventKit

/// The native hand runs independently of feed refreshes. It never asks for OS
/// permission from a background poll: the existing calendar consent screen owns
/// that interaction. A revoked grant stops execution before EventKit is read.
@MainActor
final class NativeCalendarHand {
    private var busy = false
    private let actorID: String

    init(defaults: UserDefaults = .standard) {
        let key = "anticipy.nativeCalendar.actor"
        let identity = defaults.string(forKey: key) ?? UUID().uuidString
        defaults.set(identity, forKey: key)
        actorID = "iphone-calendar-" + identity
    }

    /// The server deliberately separates an owner's approval record from an
    /// executor's release/claim. Recording both in one write is refused on the
    /// device lane. Each step addresses the exact ETag it just observed.
    func approveAndRelease(jobID: String, expectedVersion: Int, expectedScope: String,
                           fields: [String: Any], baseURL: URL, token: String,
                           owner: String, stillCurrent: @escaping @MainActor () -> Bool) async throws {
        let client = NativeCalendarClient(baseURL: baseURL, token: token)
        let (row, etag) = try await client.read(jobID)
        guard stillCurrent(), row["owner_ref"] as? String == owner,
              row["workflow_version"] as? Int == expectedVersion,
              row["scope_digest"] as? String == expectedScope,
              ["awaiting_confirm", "needs_user"].contains(row["status"] as? String ?? "")
        else { throw NativeCalendarWorkflow.Failure.malformed }
        let held = try NativeCalendarWorkflow.approvalRecord(fields, row: row, owner: owner)
        try await client.patch(jobID, fields: held, etag: etag, lease: "")
        let (approved, nextETag) = try await client.read(jobID)
        guard stillCurrent(), approved["owner_ref"] as? String == owner,
              approved["status"] as? String == row["status"] as? String,
              approved["approval"] as? String == fields["approval"] as? String,
              approved["workflow_version"] as? Int == fields["workflow_version"] as? Int,
              approved["scope_digest"] as? String == fields["scope_digest"] as? String
        else { throw NativeCalendarWorkflow.Failure.malformed }
        try await client.patch(jobID, fields: fields, etag: nextETag, lease: "")
    }

    func run(baseURL: URL, token: String, owner: String,
             stillCurrent: @escaping @MainActor () -> Bool) async {
        guard !busy, !owner.isEmpty, !token.isEmpty else { return }
        busy = true
        defer { busy = false }
        let client = NativeCalendarClient(baseURL: baseURL, token: token)
        let jobIDs: [String]
        do { jobIDs = try await client.pendingJobIDs(owner: owner) }
        catch { return }
        for id in jobIDs {
            guard stillCurrent() else { return }
            do {
                let (row, etag) = try await client.read(id)
                guard stillCurrent() else { return }
                _ = try NativeCalendarWorkflow.parts(row, owner: owner)
                guard CalendarHandPolicy.normalizedLane(row["lane"] as? String)
                        == CalendarHandPolicy.lane else { continue }
                let status = row["status"] as? String ?? ""
                let recovering = status == "running"
                guard status == "queued" || (recovering && row["claimed_by"] as? String == actorID)
                else { continue }

                let access = ContextGrants().granted(.calendar) && LifeContext.calendarReadable
                let store = access ? EventKitCalendarStore() : nil
                var policyRow = row
                // Recovery may only inspect an existing effect; the execution
                // function is separately barred from saving/removing in this mode.
                if recovering { policyRow["status"] = "queued" }
                let decision = CalendarHandPolicy.decide(
                    row: NativeCalendarWorkflow.policyRow(policyRow), now: Date(),
                    writableCalendar: store?.target(for: policyRow))
                let lease = row["lease_token"] as? String ?? ""
                if recovering {
                    let until = CalendarHandPolicy.instant(row["lease_until"] as? String ?? "")
                    guard !lease.isEmpty else { continue }
                    if until == nil || until! <= Date() {
                        try await client.patch(id, fields: NativeCalendarWorkflow.finish(row,
                            owner: owner, outcome: nil,
                            reason: "Calendar work stopped before its receipt was saved. I need to check the event before trying again.",
                            uncertain: true, now: Date()), etag: etag, lease: lease)
                        continue
                    }
                }
                switch decision {
                case .nothing: continue
                case .refuse(let why):
                    print("native calendar policy held \(id): \(why.code)")
                    let reason = access
                        ? "This calendar task is incomplete or has changed. Please tell me what you want on your calendar before I continue. Nothing new was written."
                        : "Calendar access is off. Open Settings in Anticipy and allow calendar access, then answer this task to continue."
                    try await client.patch(id, fields: NativeCalendarWorkflow.finish(row,
                        owner: owner, outcome: nil, reason: reason,
                        uncertain: recovering, now: Date()), etag: etag, lease: lease)
                    continue
                default: break
                }
                guard let store else { continue }
                var heldRow = row
                var heldETag = etag
                var heldToken = lease
                if !recovering {
                    heldToken = UUID().uuidString
                    let fields = try NativeCalendarWorkflow.claim(row, owner: owner,
                        actor: actorID, token: heldToken, now: Date())
                    try await client.patch(id, fields: fields, etag: etag, lease: "")
                    // Read after the atomic claim. A lost PATCH response never
                    // authorizes a write; recovery on the next poll only verifies.
                    let current = try await client.read(id)
                    heldRow = current.0; heldETag = current.1
                }
                guard stillCurrent(),
                      heldRow["status"] as? String == "running",
                      heldRow["lease_token"] as? String == heldToken,
                      heldRow["claimed_by"] as? String == actorID,
                      heldRow["workflow_version"] as? Int == row["workflow_version"] as? Int,
                      heldRow["scope_digest"] as? String == row["scope_digest"] as? String,
                      let until = CalendarHandPolicy.instant(heldRow["lease_until"] as? String ?? ""),
                      until > Date(), ContextGrants().granted(.calendar), LifeContext.calendarReadable
                else { continue }

                // No suspension between the final account/lease check and the
                // bounded EventKit operation. Other accounts cannot repaint or
                // lend permission while the asynchronous claim is in flight.
                let fields: [String: Any]
                do {
                    let outcome = try NativeCalendarExecution.execute(decision,
                        store: store, verifyOnly: recovering)
                    fields = try NativeCalendarWorkflow.finish(heldRow, owner: owner,
                        outcome: outcome, reason: "Calendar readback verified.",
                        uncertain: false, now: Date())
                } catch {
                    fields = try NativeCalendarWorkflow.finish(heldRow, owner: owner,
                        outcome: nil,
                        reason: "I couldn't verify the calendar change. Please check the event before trying again; I won't create another copy.",
                        uncertain: true, now: Date())
                }
                try await client.patch(id, fields: fields, etag: heldETag, lease: heldToken)
            } catch {
                // Keep the authoritative row intact on network/CAS failure. The
                // next poll reconciles an owned running row without replaying it.
                print("native calendar task \(id) paused: \(String(describing: error))")
            }
        }
    }
}

private struct NativeCalendarClient {
    let baseURL: URL
    let token: String

    func pendingJobIDs(owner: String) async throws -> [String] {
        // The home feed is capped at thirty cards. Execution must not depend on
        // a pending event still being among the newest thirty things displayed.
        let escaped = owner.replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
        let filter = "owner_ref=\"\(escaped)\" && lane!=\"\" && lane!=\"research\""
            + " && lane!=\"api\" && lane!=\"supervised_read\""
            + " && status!=\"done\" && status!=\"failed\" && status!=\"cancelled\""
        var page = 1
        var ids = Set<String>()
        while true {
            var components = URLComponents(url: baseURL.appendingPathComponent(
                "api/collections/jobs/records"), resolvingAgainstBaseURL: false)!
            components.queryItems = [URLQueryItem(name: "filter", value: filter),
                URLQueryItem(name: "page", value: String(page)),
                URLQueryItem(name: "perPage", value: "100"),
                URLQueryItem(name: "sort", value: "created,id")]
            var request = URLRequest(url: components.url!)
            request.setValue(token, forHTTPHeaderField: "Authorization")
            request.timeoutInterval = 20
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200,
                  let body = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let rows = body["items"] as? [[String: Any]],
                  let totalPages = body["totalPages"] as? Int,
                  rows.allSatisfy({ $0["owner_ref"] as? String == owner })
            else { throw NativeCalendarWorkflow.Failure.malformed }
            for row in rows where CalendarHandPolicy.normalizedLane(row["lane"] as? String)
                == CalendarHandPolicy.lane {
                if let id = row["id"] as? String { ids.insert(id) }
            }
            if page >= totalPages { return ids.sorted() }
            page += 1
        }
    }

    func request(_ id: String) -> URLRequest {
        var r = URLRequest(url: baseURL.appendingPathComponent("api/collections/jobs/records")
            .appendingPathComponent(id))
        r.setValue(token, forHTTPHeaderField: "Authorization")
        r.timeoutInterval = 20
        return r
    }

    func read(_ id: String) async throws -> ([String: Any], String) {
        let (data, response) = try await URLSession.shared.data(for: request(id))
        guard let http = response as? HTTPURLResponse, http.statusCode == 200,
              let etag = http.value(forHTTPHeaderField: "ETag"), !etag.isEmpty,
              let row = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              row["id"] as? String == id else { throw NativeCalendarWorkflow.Failure.malformed }
        return (row, etag)
    }

    func patch(_ id: String, fields: [String: Any], etag: String, lease: String) async throws {
        var r = request(id)
        r.httpMethod = "PATCH"
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.setValue(etag, forHTTPHeaderField: "If-Match")
        if !lease.isEmpty { r.setValue(lease, forHTTPHeaderField: "X-Anticipy-Lease") }
        r.httpBody = try JSONSerialization.data(withJSONObject: fields)
        let (_, response) = try await URLSession.shared.data(for: r)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode)
        else { throw NativeCalendarWorkflow.Failure.missingLease }
    }
}

/// Store reads are limited to titles, times and our URL marker. Notes,
/// attendees, contact addresses and locations are never touched.
final class EventKitCalendarStore: NativeCalendarStore {
    private let store = EKEventStore()

    func target(for row: [String: Any]) -> CalendarHandPolicy.Target? {
        // Recover a previously written event in its original calendar even if
        // the owner's default calendar has changed since the write.
        if let raw = row["params"] as? String,
           let top = try? JSONSerialization.jsonObject(with: Data(raw.utf8)) as? [String: Any],
           let plan = top["_workflow"] as? [String: Any],
           let act = plan["act"] as? [String: Any],
           let target = act["target"] as? [String: String],
           let ref = target["ref"], let undo = plan["undo"] as? [String: Any],
           let held = undo["held"] as? [String: [String: Any]],
           let marker = held[CalendarHandPolicy.mintedByUs]?[ref] as? String,
           let facts = plan["facts"] as? [String: Any],
           let start = CalendarHandPolicy.instant(facts[CalendarHandPolicy.startKey] as? String ?? ""),
           let end = CalendarHandPolicy.instant(facts[CalendarHandPolicy.endKey] as? String ?? ""), end > start {
            let predicate = store.predicateForEvents(
                withStart: start.addingTimeInterval(-CalendarHandPolicy.undoWindowPadding),
                end: end.addingTimeInterval(CalendarHandPolicy.undoWindowPadding), calendars: nil)
            let events = store.events(matching: predicate).filter {
                $0.url?.absoluteString == CalendarHandPolicy.stampValue(for: marker)
            }
            if events.count == 1, let calendar = events.first?.calendar,
               calendar.allowsContentModifications { return describe(calendar) }
            if events.count > 1 { return nil }
        }
        guard let calendar = store.defaultCalendarForNewEvents,
              calendar.allowsContentModifications else { return nil }
        return describe(calendar)
    }

    private func describe(_ calendar: EKCalendar) -> CalendarHandPolicy.Target {
        .init(identifier: calendar.calendarIdentifier, title: calendar.title,
              landsOnlyOnThisDevice: calendar.source.sourceType == .local)
    }

    func matching(stamp: String, window: CalendarHandPolicy.Window,
                  target: CalendarHandPolicy.Target) throws -> [NativeCalendarEvent] {
        guard let calendar = store.calendar(withIdentifier: target.identifier),
              calendar.allowsContentModifications
        else { throw NativeCalendarExecution.Failure.readbackFailed }
        let predicate = store.predicateForEvents(withStart: window.from, end: window.to,
                                                 calendars: [calendar])
        return store.events(matching: predicate).filter { $0.url?.absoluteString == stamp }.map {
            NativeCalendarEvent(identifier: $0.eventIdentifier, stamp: stamp,
                title: $0.title ?? "", start: $0.startDate, end: $0.endDate,
                calendarIdentifier: $0.calendar.calendarIdentifier)
        }
    }

    func save(_ write: CalendarHandPolicy.Write) throws {
        guard let calendar = store.calendar(withIdentifier: write.target.identifier),
              calendar.allowsContentModifications else { throw NativeCalendarExecution.Failure.readbackFailed }
        let event = EKEvent(eventStore: store)
        event.calendar = calendar
        event.title = write.title
        event.startDate = write.start
        event.endDate = write.end
        event.url = URL(string: CalendarHandPolicy.stampValue(for: write.ourRef))
        try store.save(event, span: .thisEvent, commit: true)
    }

    func remove(_ event: NativeCalendarEvent) throws {
        guard let found = store.event(withIdentifier: event.identifier),
              found.url?.absoluteString == event.stamp,
              found.calendar.calendarIdentifier == event.calendarIdentifier
        else { throw NativeCalendarExecution.Failure.readbackFailed }
        try store.remove(found, span: .thisEvent, commit: true)
    }
}
#endif
