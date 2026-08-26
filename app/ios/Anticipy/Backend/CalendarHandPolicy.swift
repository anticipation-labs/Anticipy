import Foundation

/// THE PHONE AS A HAND, for one verb: writing and un-writing a calendar event.
///
/// `research/2026-08-26-hands2-better-answer.md` §4 rung 0. The app already
/// holds full calendar access (`LifeContext.requestCalendar`), already polls
/// the job channel every three seconds (`AnticipyApp.startPolling`), and
/// already writes job status back on it. Nothing here is new plumbing. What is
/// new is a DECISION, and it is kept pure on purpose: no `EventKit`, no store,
/// no clock of its own. The `EKEventStore` calls sit behind this type, so what
/// the hand will do is answerable on a laptop with no device and no calendar.
///
/// ── THE CONSTRAINT THAT DECIDES WHETHER ANY OF THIS IS LEGAL ──────────────
///
/// `docs/superpowers/specs/2026-08-24-shelf-2-redesign.md` §4:
///
///     "An act is admissible only when undoing it requires nothing the act
///      produced."
///
/// and §5.2 fixes the representation:
///
///     "The undo plan's inputs are a typed, closed list of provenance-tagged
///      references — minted_by_us / owner_supplied / constant — each resolvable
///      to a stored value at the moment the plan is written."
///
/// `EKEvent.eventIdentifier` IS ASSIGNED BY EVENTKIT ON SAVE. So an undo that
/// says "remove the event whose identifier EventKit gave us" is precisely the
/// shape §6.1 excludes by name — *"a draft created in his Gmail account is not
/// admitted… the undo needs a message id the provider returned — a hole in the
/// recipe, filled by the counterparty, after the act."* Writing that undo would
/// make this whole card inadmissible.
///
/// THE FIX, and it is the reason this type exists at all: **we mint the id
/// before the act and carry it ON the event**, and the undo is a SEARCH for our
/// own id — never a lookup of theirs. The precedent is `brain/workflow.py:
/// new_plan`, which writes `plan_id = plan_id or str(uuid.uuid4())` so the id
/// exists before anything is stored. Spec §10.4 licenses exactly this shape and
/// says why it is not a domain list: *"not 'calendars are safe' but 'an act
/// whose undo addresses an identifier we minted is undoable by us alone.'"*
///
/// So the undo's three inputs are all resolvable before the event exists:
///
///   * `our_ref`      — `minted_by_us`, the uuid stamped onto the event;
///   * `calendar_start`/`calendar_end` — `owner_supplied`, the facts the model
///     already put on the plan, which give the search its window;
///   * the window padding — `constant`.
///
/// Nothing in that list is filled by EventKit, so `admissible()`'s undo side is
/// satisfiable. `decide` re-checks it here rather than trusting it: the plan and
/// the row travelled separately to reach this phone, which is the same argument
/// `JobReceiptPolicy` makes about a receipt.
///
/// ── AND IT IS STILL NOT ADMITTED FOR ACT-AND-TELL. THAT IS NOT A BUG. ─────
///
/// A resolvable undo is necessary and never sufficient (spec §4.1). The
/// admitted set — `brain/workflow.py: ADMITTED_ACT_TYPES` — has exactly ONE
/// member, `local_draft`, and joining it needs all six of §10.1: ten live undos
/// across ten distinct days, a silent-failure probe, a durable announcement,
/// and — condition 6, which §10.4 says fires for *"the first act type whose
/// effect leaves our store"*, which this is — the repair of §2.1's receipt
/// defect first. `extension/agent_loop.js: terminalReceiptEvidence` is
/// unrepaired today.
///
/// So `admittedForActAndTell` below is EMPTY, and a calendar write reaches this
/// hand only after the owner has already tapped. The hand does not carry a
/// second copy of the confirmation gate — the research names duplicating it as
/// the real risk (*"a device execution lane that does not route through the
/// same gate is not a new hand, it is a hole in the gate"*) — it refuses to
/// move without the server's own approval record, bound to this exact plan id,
/// version and scope digest. That is a floor, not a gate: it can only hold.
///
/// ── POLARITY ─────────────────────────────────────────────────────────────
///
/// Everything here is a FLOOR (Law 1's floor/ceiling distinction, spec §5.2).
/// No act declaration, no undo plan, an unrecognised provenance tag, a
/// reference that does not resolve, a fact that will not parse, a row that
/// disagrees with its own plan — every one of those refuses. There is no fifth
/// outcome that means "proceed". A floor that lifts on silence lifts itself.
///
/// ── WHAT THIS NEVER DOES ─────────────────────────────────────────────────
///
/// It never reads prose. "Thursday 7pm" is the MODEL's to resolve (Law 1), and
/// it arrives already resolved in the plan's facts as an instant. A fact that
/// is missing is a REFUSAL naming what is missing; a fact that will not parse
/// is a refusal naming the key. Inventing a time — or a duration for a missing
/// end — is the invention this repo already guards against in three places.
enum CalendarHandPolicy {

    // MARK: - The vocabulary, declared once

    /// The job row's `lane`. Existing lanes are "" (browser), "research" and
    /// "supervised_read"; this is the device's own.
    static let lane = "device_calendar"

    static let writeActType = "calendar_write"
    static let undoActType = "calendar_undo"

    /// `reach` is act-type-scoped, per spec §9 — `touches`'s compute/read/world
    /// has no honest value for a write into the store on this phone.
    static let reach = "device_calendar_store"

    /// §8.7: a declared reach on a general browser session is a label attached
    /// to a process that can do anything the session can do. This executor is a
    /// single `EKEventStore` call behind a single decision, which is the only
    /// mechanical containment available.
    static let executor = "anticipy_phone"

    /// ACT TYPES THIS HAND MAY RUN WITHOUT A TAP. EMPTY, ON PURPOSE.
    ///
    /// The mirror of `brain/workflow.py: ADMITTED_ACT_TYPES`, and like it, a
    /// list that can only REFUSE. §10.1's six conditions are unmet for
    /// `calendar_write` — see the type comment. Adding a member here is a diff
    /// somebody has to defend, which is the whole reason it is a constant a
    /// reader can check rather than a value a row can carry.
    static let admittedForActAndTell: Set<String> = []

    /// The closed provenance set. §5.2: *"A fourth provenance tag is a schema
    /// change, visible in a diff, not a string a model can invent at runtime."*
    static let provenanceTags: Set<String> = ["minted_by_us", "owner_supplied", "constant"]
    static let mintedByUs = "minted_by_us"

    // The three facts a calendar act needs, read verbatim and never derived.
    static let titleKey = "calendar_title"
    static let startKey = "calendar_start"
    static let endKey = "calendar_end"

    /// How far either side of the event the undo's search reaches.
    ///
    /// `constant` provenance: it is resolvable now because it is a number in
    /// this file. It is a search RADIUS in a mechanical lookup, not a threshold
    /// deciding what anything means. It exists because `EKEventStore`'s
    /// predicate matches events OVERLAPPING a range, and an event that a
    /// calendar's own timezone handling nudged by an hour must still be found
    /// by the undo the owner tapped.
    static let undoWindowPadding: TimeInterval = 24 * 60 * 60

    /// WHERE OUR MINTED ID RIDES, and the reason it is not the notes field.
    ///
    /// `EKEvent` has no public user-data dictionary, so the id has to ride on a
    /// field the store already syncs. Two candidates, and only one is legal:
    ///
    ///   * **notes — REFUSED.** The shipped permission string the owner already
    ///     read says *"She never reads the notes or the invitees"*
    ///     (`NSCalendarsFullAccessUsageDescription`). An undo that searches
    ///     notes reads the notes of every event in its window. Breaking a
    ///     promise the owner has already been shown, to make our own bookkeeping
    ///     easier, is not a trade this hand gets to make.
    ///   * **url — CHOSEN.** `EKEvent.url` is a URL the app owns the meaning of.
    ///     Reading it back reads no note, no attendee, no location.
    ///
    /// **UNVERIFIED, AND IT IS THE ONE THING THAT DECIDES WHETHER THE UNDO
    /// WORKS AT ALL: whether `EKEvent.url` survives a round trip through
    /// Google's CalDAV sync.** If it does not, the undo cannot find what it
    /// minted, the reference stops resolving, and by the floor above the act
    /// stops being admissible — which is the correct outcome, reached honestly,
    /// but it has to be MEASURED on a device rather than assumed here.
    static let stampScheme = "anticipy"

    static func stampValue(for ourRef: String) -> String {
        "\(stampScheme)://act/\(ourRef)"
    }

    // MARK: - What the hand is told

    /// Exactly the columns the phone already decodes on `AgentJob`, plus the
    /// raw `params` string. Nothing here is read from the device.
    struct Row: Equatable {
        let id: String
        let status: String
        let lane: String?
        let workflowID: String?
        let workflowVersion: Int?
        let scopeDigest: String?
        let consequence: String?
        let params: String

        init(id: String, status: String, lane: String?, workflowID: String?,
             workflowVersion: Int?, scopeDigest: String?, consequence: String?,
             params: String) {
            self.id = id; self.status = status; self.lane = lane
            self.workflowID = workflowID; self.workflowVersion = workflowVersion
            self.scopeDigest = scopeDigest; self.consequence = consequence
            self.params = params
        }
    }

    /// The calendar the write would land in, as the device reports it.
    ///
    /// `landsOnlyOnThisDevice` is the stranger case named in the research §4:
    /// *"EventKit writes into whichever account the device holds. A cold
    /// stranger whose Google Calendar is not configured in iOS Settings gets a
    /// write that never reaches calendar.google.com."* It is NOT a refusal —
    /// a local calendar is a real calendar and the owner asked for the event —
    /// but it must reach the sentence she says afterwards, or "it's on your
    /// calendar" means something she cannot back up.
    struct Target: Equatable {
        let identifier: String
        let title: String
        let landsOnlyOnThisDevice: Bool
    }

    // MARK: - What the hand decides

    /// A half-open span the undo searches. Not a Foundation `DateInterval`, so
    /// this type stays comparable in a test without a calendar or a timezone.
    struct Window: Equatable {
        let from: Date
        let to: Date
    }

    enum Stamp: Equatable {
        /// `EKEvent.url`, set to `anticipy://act/<ourRef>`.
        case url(String)
    }

    struct Write: Equatable {
        let jobID: String
        let planID: String
        let planVersion: Int
        /// OUR id, minted before the act, on the plan before this hand saw it.
        let ourRef: String
        let stamp: Stamp
        let title: String
        let start: Date
        let end: Date
        let target: Target
        /// Where the undo will look for `ourRef`. Computed now, from values
        /// that are all resolvable now.
        ///
        /// AND IT IS ALSO WHAT MAKES A SECOND EXECUTION SAFE, which is an
        /// obligation on the executor that this type cannot discharge for it:
        /// **before saving, search this window for `ourRef` and treat a hit as
        /// already done.** The poll runs every three seconds and a row sits at
        /// `queued` until something claims it, so "write it twice" is the
        /// ordinary accident here, not the exotic one — and a duplicate booking
        /// is the cardinal sin this product names (moment 50). Minting the id
        /// first is what buys that check; an EventKit-assigned identifier could
        /// not answer "have I already done this" at all.
        let undoWindow: Window
    }

    struct Undo: Equatable {
        let jobID: String
        let planID: String
        let planVersion: Int
        let ourRef: String
        let stamp: Stamp
        let searchWindow: Window
        let target: Target
    }

    /// Not this hand's business, and nothing is wrong. Distinct from a refusal
    /// so that a journal can count the two apart — §10.5(a) is emphatic that
    /// "there was nothing to do" and "I would not do it" must never read alike.
    enum Idle: String, Equatable {
        case notThisHand
        case alreadyClaimed
        case alreadyTerminal
        case stillWaiting
    }

    /// The enumerated causes. §11: *"Reasons are the enumerated refusal causes
    /// of §5.2 and §8.5's a-f, not free text. A shelf that refuses in prose
    /// cannot be widened on evidence, because nobody can count what it
    /// refused."*
    enum Refusal: Equatable {
        case malformedParams
        case actTypeNotAdmitted(String)
        case reachDisagrees(String)
        case executorDisagrees(String)
        /// The plan claimed Shelf 2 for an act type this hand does not admit
        /// for act-and-tell. The §5.4 attack, arriving from the device side.
        case actAndTellNotAdmitted(String)
        case rowDisagreesWithPlan
        case noApproval
        case approvalUnbound
        case actTargetUnbound
        case noUndoPlan
        case undoAddressesAnotherAct
        case unknownProvenance(String)
        case unresolvedReference(String)
        case undoBindsNothing
        case undoMissesTheTarget
        case factsIncomplete([String])
        case unreadableFact(String)
        case endsBeforeItStarts
        case startAlreadyPast
        case noWritableCalendar

        /// The stable string a journal counts. Distinct per case — a shared
        /// code is a refusal nobody can tell from another one.
        var code: String {
            switch self {
            case .malformedParams:         return "calhand.malformed_params"
            case .actTypeNotAdmitted:      return "calhand.act_type_not_admitted"
            case .reachDisagrees:          return "calhand.reach_disagrees"
            case .executorDisagrees:       return "calhand.executor_disagrees"
            case .actAndTellNotAdmitted:   return "calhand.act_and_tell_not_admitted"
            case .rowDisagreesWithPlan:    return "calhand.row_disagrees_with_plan"
            case .noApproval:              return "calhand.no_approval"
            case .approvalUnbound:         return "calhand.approval_unbound"
            case .actTargetUnbound:        return "calhand.act_target_unbound"
            case .noUndoPlan:              return "calhand.no_undo_plan"
            case .undoAddressesAnotherAct: return "calhand.undo_addresses_another_act"
            case .unknownProvenance:       return "calhand.unknown_provenance"
            case .unresolvedReference:     return "calhand.unresolved_reference"
            case .undoBindsNothing:        return "calhand.undo_binds_nothing"
            case .undoMissesTheTarget:     return "calhand.undo_misses_the_target"
            case .factsIncomplete:         return "calhand.facts_incomplete"
            case .unreadableFact:          return "calhand.unreadable_fact"
            case .endsBeforeItStarts:      return "calhand.ends_before_it_starts"
            case .startAlreadyPast:        return "calhand.start_already_past"
            case .noWritableCalendar:      return "calhand.no_writable_calendar"
            }
        }
    }

    enum Decision: Equatable {
        case write(Write)
        case undo(Undo)
        case nothing(Idle)
        case refuse(Refusal)
    }

    // MARK: - The decision

    /// What this hand should do with this row, at this instant, on this device.
    ///
    /// - Parameters:
    ///   - row: the job as the poll already delivered it.
    ///   - now: the reading moment, handed in rather than taken — a policy that
    ///     reads its own clock cannot be tested at the instant that matters.
    ///   - writableCalendar: the calendar `EKEventStore` would write into, or
    ///     nil when the device has none.
    static func decide(row: Row, now: Date, writableCalendar: Target?) -> Decision {

        // ---------------------------------------------------------- not ours
        guard (row.lane ?? "") == lane else { return .nothing(.notThisHand) }

        switch row.status {
        case "done", "failed", "cancelled":  return .nothing(.alreadyTerminal)
        case "running":                      return .nothing(.alreadyClaimed)
        case "queued":                       break
        default:                             return .nothing(.stillWaiting)
        }

        // -------------------------------------------------- the plan, parsed
        guard let params = try? JSONSerialization.jsonObject(with: Data(row.params.utf8)),
              let top = params as? [String: Any],
              let plan = top["_workflow"] as? [String: Any]
        else { return .refuse(.malformedParams) }

        guard let act = plan["act"] as? [String: Any],
              let actType = act["act_type"] as? String, !actType.isEmpty
        else { return .refuse(.actTypeNotAdmitted("")) }

        guard actType == writeActType || actType == undoActType
        else { return .refuse(.actTypeNotAdmitted(actType)) }

        let declaredReach = act["reach"] as? String ?? ""
        guard declaredReach == reach else { return .refuse(.reachDisagrees(declaredReach)) }

        let declaredExecutor = act["executor"] as? String ?? ""
        guard declaredExecutor == executor
        else { return .refuse(.executorDisagrees(declaredExecutor)) }

        // ------------------------------------------------------- the shelf
        // A plan that claims act-and-tell for an act type this hand does not
        // admit is the §5.4 attack from the device side: the label is a member
        // of a set somewhere, and the effect is not the effect it named. The
        // set here is empty, so this always holds.
        // EITHER SOURCE, not the blob with the row as a fallback. The blob and
        // the column travelled separately, and a plan that says
        // "consequential" in the blob while the row says "reversible_local" is
        // the more interesting of the two disagreements, not the less. A floor
        // that reads only its preferred witness is a floor with a side door.
        let claimsActAndTell = (plan["consequence"] as? String) == "reversible_local"
            || (row.consequence ?? "") == "reversible_local"
        if claimsActAndTell, !admittedForActAndTell.contains(actType) {
            return .refuse(.actAndTellNotAdmitted(actType))
        }

        // ---------------------------------------- the row and the plan agree
        // They travelled separately to get to this phone. `approvalFields` in
        // AnticipyApp makes the same three-way check before it writes an
        // approval; this makes it before it acts on one.
        let planID = plan["plan_id"] as? String ?? ""
        let planVersion = plan["version"] as? Int
        let planDigest = plan["scope_digest"] as? String ?? ""
        guard !planID.isEmpty, let planVersion,
              !planDigest.isEmpty,
              planID == (row.workflowID ?? ""),
              planVersion == row.workflowVersion,
              planDigest == (row.scopeDigest ?? "")
        else { return .refuse(.rowDisagreesWithPlan) }

        // ------------------------------------------------------- the gate
        // THE HAND DOES NOT CARRY A SECOND COPY OF THE CONFIRMATION GATE. It
        // refuses to move without the server's own approval record, bound to
        // this exact immutable version. A hand that decided for itself would
        // be the hole the research names.
        guard let approval = plan["approval"] as? [String: Any]
        else { return .refuse(.noApproval) }
        guard (approval["plan_id"] as? String) == planID,
              (approval["plan_version"] as? Int) == planVersion,
              (approval["scope_digest"] as? String) == planDigest
        else { return .refuse(.approvalUnbound) }

        // ------------------------------------------------- our own minted id
        // §5.4's ACT_TARGET_UNBOUND: without this the act declares nothing it
        // will address, and any well-formed undo satisfies the structural test
        // while addressing something the act never creates.
        guard let rawTarget = act["target"] as? [String: Any],
              let targetProvenance = rawTarget["provenance"] as? String,
              let targetRef = rawTarget["ref"] as? String,
              !targetRef.isEmpty,
              targetProvenance == mintedByUs
        else { return .refuse(.actTargetUnbound) }

        // ------------------------------------------------------ the undo plan
        guard let undo = plan["undo"] as? [String: Any],
              let steps = undo["steps"] as? [Any], !steps.isEmpty
        else { return .refuse(.noUndoPlan) }

        guard (undo["act_type"] as? String) == actType
        else { return .refuse(.undoAddressesAnotherAct) }

        let held = undo["held"] as? [String: [String: Any]] ?? [:]
        let inputs = undo["inputs"] as? [[String: Any]] ?? []

        // Resolve EVERY reference. Read `provenance` and `ref`. NEVER `name`,
        // never the steps: §5.2's *"It never inspects a field name and never
        // parses prose"* is the clause that keeps this inside Law 1's seatbelt
        // exemption. A reference that resolves only after the act is discovered
        // by TRYING TO RESOLVE IT AND FAILING — which is exactly what an
        // `EKEvent.eventIdentifier` input does here.
        for input in inputs {
            let provenance = input["provenance"] as? String ?? ""
            guard provenanceTags.contains(provenance)
            else { return .refuse(.unknownProvenance(provenance)) }
            let ref = input["ref"] as? String ?? ""
            guard resolves(held, provenance, ref)
            else { return .refuse(.unresolvedReference(ref)) }
        }

        // Presence is not correspondence, and these two are the difference.
        guard inputs.contains(where: { ($0["provenance"] as? String) == mintedByUs })
        else { return .refuse(.undoBindsNothing) }

        guard inputs.contains(where: {
            ($0["provenance"] as? String) == targetProvenance
                && ($0["ref"] as? String) == targetRef
        }) else { return .refuse(.undoMissesTheTarget) }

        // The act's own target is held to the same "known-good BEFORE acting",
        // and it must resolve to a STRING, because that string is what gets
        // stamped onto the event and searched for again. `ref` is a KEY into
        // `held` — `brain/workflow.py: _resolves_one` does `bucket[item.ref]` —
        // so the id we mint is the resolved VALUE, never the reference name.
        // Strictly stronger than `resolves` on its own, which is why that call
        // is NOT also made here: a value that is nil, `NSNull`, a number, or
        // whitespace all fail this, and a redundant check no test can kill is
        // a line that reads as a guard and guards nothing.
        guard let ourRef = held[targetProvenance]?[targetRef] as? String,
              !ourRef.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else { return .refuse(.unresolvedReference(targetRef)) }

        // ---------------------------------------------------------- the facts
        // The model decided these. This reads them; it never derives one.
        let facts = plan["facts"] as? [String: Any] ?? [:]
        var present: [String: String] = [:]
        var missing: [String] = []
        // Stable order, so a refusal reads the same way twice and a test can
        // assert on it. Not sorted: this is the order a person would say them.
        for key in [titleKey, startKey, endKey] {
            let text = (facts[key] as? String)?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if text.isEmpty { missing.append(key) } else { present[key] = text }
        }
        guard missing.isEmpty, let title = present[titleKey],
              let rawStart = present[startKey], let rawEnd = present[endKey]
        else { return .refuse(.factsIncomplete(missing)) }

        guard let start = instant(rawStart) else { return .refuse(.unreadableFact(startKey)) }
        guard let end = instant(rawEnd) else { return .refuse(.unreadableFact(endKey)) }
        guard end > start else { return .refuse(.endsBeforeItStarts) }

        // A queue that sat still is not a licence to write last Thursday's
        // dinner into next week. Checked for a WRITE only: removing an event
        // whose time has passed is still what the owner asked for.
        if actType == writeActType, start <= now { return .refuse(.startAlreadyPast) }

        guard let target = writableCalendar else { return .refuse(.noWritableCalendar) }

        let window = Window(from: start.addingTimeInterval(-undoWindowPadding),
                            to: end.addingTimeInterval(undoWindowPadding))
        let stamp = Stamp.url(stampValue(for: ourRef))

        if actType == undoActType {
            return .undo(Undo(jobID: row.id, planID: planID, planVersion: planVersion,
                              ourRef: ourRef, stamp: stamp,
                              searchWindow: window, target: target))
        }
        return .write(Write(jobID: row.id, planID: planID, planVersion: planVersion,
                            ourRef: ourRef, stamp: stamp, title: title,
                            start: start, end: end, target: target,
                            undoWindow: window))
    }

    /// §5.2's checker, one reference at a time. Reads `provenance` and `ref`.
    /// NEVER `name`, never `steps`.
    ///
    /// The empty and null legs are `brain/workflow.py: _resolves_one`'s
    /// `bucket[item.ref] in (None, "")`, and they are not decoration: JSON
    /// `null` arrives as `NSNull`, which is a perfectly non-nil Swift value, so
    /// a bare presence check would let `{"our_ref": null}` resolve.
    static func resolves(_ held: [String: [String: Any]],
                         _ provenance: String, _ ref: String) -> Bool {
        guard !ref.isEmpty, let bucket = held[provenance],
              let value = bucket[ref], !(value is NSNull) else { return false }
        if let text = value as? String {
            return !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
        return true
    }

    // MARK: - Senses

    /// An instant off the wire. Transport, not meaning: this reads a stamp the
    /// model already resolved, and it reads NOTHING ELSE. There is no path in
    /// this file from "Thursday 7pm" to a Date.
    ///
    /// Both widths are tried because the two writers disagree:
    /// `ISO8601DateFormatter.anticipyUTC` in this app emits fractional seconds,
    /// and Python's `datetime.isoformat()` omits them when the microsecond is
    /// zero. A parser that knew only one of those would refuse real stamps.
    static func instant(_ raw: String) -> Date? {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return nil }
        for options in [ISO8601DateFormatter.Options([.withInternetDateTime,
                                                      .withFractionalSeconds]),
                        ISO8601DateFormatter.Options([.withInternetDateTime])] {
            let formatter = ISO8601DateFormatter()
            formatter.timeZone = TimeZone(secondsFromGMT: 0)
            formatter.formatOptions = options
            if let date = formatter.date(from: text) { return date }
        }
        return nil
    }
}
