// THE PHONE AS A HAND — what it will and will not do to a calendar.
//
// research/2026-08-26-hands2-better-answer.md §4 rung 0, checked against the
// one constraint that decides whether the card is legal at all:
// docs/superpowers/specs/2026-08-24-shelf-2-redesign.md §4 —
//
//     "An act is admissible only when undoing it requires nothing the act
//      produced."
//
// EKEvent.eventIdentifier is assigned BY EVENTKIT ON SAVE, so an undo that
// looks up the identifier EventKit returned is the exact shape §6.1 excludes.
// The suite below pins the alternative: an id WE minted, resolvable before the
// act, stamped onto the event, and searched for afterwards.
//
// Run: sh app/ios/Tests/run_calendar_hand_tests.sh
import Foundation

var failures = 0
func check(_ name: String, _ ok: Bool) {
    print("\(ok ? "PASS" : "FAIL"): \(name)")
    if !ok { failures += 1 }
}

// ----------------------------------------------------------------- fixtures

let PLAN = "pln_7f3a91"
let VERSION = 3
let DIGEST = "sha256:0f19ab4c"
/// The id we mint. It exists on the plan BEFORE this hand ever sees the row,
/// which is the whole argument: brain/workflow.py new_plan writes
/// `plan_id = plan_id or str(uuid.uuid4())` for the same reason.
let OUR_REF = "8f4c1a20-6b44-4a1e-9d31-2c7e5f0a9b11"

let NOW = CalendarHandPolicy.instant("2026-08-25T12:00:00Z")!
let START = "2026-08-27T19:00:00Z"
let END = "2026-08-27T21:00:00Z"

let googleCalendar = CalendarHandPolicy.Target(
    identifier: "cal-google-primary", title: "omar@gmail.com",
    landsOnlyOnThisDevice: false)
let onDeviceOnly = CalendarHandPolicy.Target(
    identifier: "cal-local", title: "Calendar", landsOnlyOnThisDevice: true)

func json(_ any: Any) -> String {
    let data = try! JSONSerialization.data(withJSONObject: any)
    return String(decoding: data, as: UTF8.self)
}

/// An undo plan of exactly the shape §5.2 demands: typed, provenance-tagged
/// references, each resolvable against `held` at the moment the plan is
/// written. NOTHING in it is filled by EventKit.
func undoPlan(actType: String = CalendarHandPolicy.writeActType,
              steps: [String] = ["Search the device calendar across the stored window.",
                                 "Remove the event whose url carries our minted id."],
              inputs: [[String: Any]]? = nil,
              held: [String: Any]? = nil) -> [String: Any] {
    [
        "act_type": actType,
        "steps": steps,
        "inputs": inputs ?? [
            ["name": "our id", "provenance": "minted_by_us", "ref": "our_ref"],
            ["name": "when it starts", "provenance": "owner_supplied", "ref": "calendar_start"],
            ["name": "search padding", "provenance": "constant", "ref": "undo_window_padding"],
        ],
        "held": held ?? [
            "minted_by_us": ["our_ref": OUR_REF],
            "owner_supplied": ["calendar_start": START],
            "constant": ["undo_window_padding": 86400],
        ],
    ]
}

func approvalBlob(planID: String = PLAN, version: Int = VERSION,
                  digest: String = DIGEST) -> [String: Any] {
    ["plan_id": planID, "plan_version": version, "scope_digest": digest,
     "owner_words": "Tapped “Send it”.", "approved_at": "2026-08-25T11:59:02Z"]
}

func params(actType: String = CalendarHandPolicy.writeActType,
            reach: String = CalendarHandPolicy.reach,
            executor: String = CalendarHandPolicy.executor,
            target: Any? = ["name": "our id", "provenance": "minted_by_us",
                            "ref": "our_ref"],
            undo: [String: Any]? = nil,
            facts: [String: Any]? = nil,
            approval: Any? = nil,
            consequence: String = "consequential",
            planID: String = PLAN, version: Int = VERSION,
            digest: String = DIGEST,
            dropAct: Bool = false) -> String {
    var act: [String: Any] = ["act_type": actType, "reach": reach, "executor": executor]
    if let target { act["target"] = target }
    var plan: [String: Any] = [
        "plan_id": planID, "version": version, "scope_digest": digest,
        "consequence": consequence,
        "facts": facts ?? [CalendarHandPolicy.titleKey: "Dinner with Priya",
                           CalendarHandPolicy.startKey: START,
                           CalendarHandPolicy.endKey: END],
        "undo": undo ?? undoPlan(actType: actType),
        "approval": approval ?? approvalBlob(),
    ]
    if !dropAct { plan["act"] = act }
    return json(["source": "put dinner with Priya Thursday 7", "_workflow": plan])
}

func row(status: String = "queued", lane: String? = CalendarHandPolicy.lane,
         workflowID: String? = PLAN, workflowVersion: Int? = VERSION,
         scopeDigest: String? = DIGEST, consequence: String? = "consequential",
         params p: String? = nil) -> CalendarHandPolicy.Row {
    CalendarHandPolicy.Row(id: "job_991", status: status, lane: lane,
                           workflowID: workflowID, workflowVersion: workflowVersion,
                           scopeDigest: scopeDigest, consequence: consequence,
                           params: p ?? params())
}

func decide(_ r: CalendarHandPolicy.Row, now: Date = NOW,
            calendar: CalendarHandPolicy.Target? = googleCalendar)
-> CalendarHandPolicy.Decision {
    CalendarHandPolicy.decide(row: r, now: now, writableCalendar: calendar)
}

func refusal(_ d: CalendarHandPolicy.Decision) -> CalendarHandPolicy.Refusal? {
    if case .refuse(let why) = d { return why }
    return nil
}
func idle(_ d: CalendarHandPolicy.Decision) -> CalendarHandPolicy.Idle? {
    if case .nothing(let why) = d { return why }
    return nil
}
func written(_ d: CalendarHandPolicy.Decision) -> CalendarHandPolicy.Write? {
    if case .write(let w) = d { return w }
    return nil
}
func undone(_ d: CalendarHandPolicy.Decision) -> CalendarHandPolicy.Undo? {
    if case .undo(let u) = d { return u }
    return nil
}

// =================================================== 1. not this hand's row
// "Nothing to do" and "I will not do this" must never read alike (§10.5(a)).

check("a browser-lane job is not this hand's business",
      idle(decide(row(lane: ""))) == .notThisHand)
check("a job with no lane at all is not this hand's business",
      idle(decide(row(lane: nil))) == .notThisHand)
check("the research lane is not this hand's business",
      idle(decide(row(lane: "research"))) == .notThisHand)
for terminal in ["done", "failed", "cancelled"] {
    check("a \(terminal) job is already over",
          idle(decide(row(status: terminal))) == .alreadyTerminal)
}
check("a running job is somebody else's claim",
      idle(decide(row(status: "running"))) == .alreadyClaimed)
check("a job still at the gate is waiting, not refused",
      idle(decide(row(status: "awaiting_confirm"))) == .stillWaiting)
check("a job asking the owner a question is waiting, not refused",
      idle(decide(row(status: "needs_user"))) == .stillWaiting)

// ============================================ 2. the gate did not move here
// The research names duplicating the confirmation gate as the real risk: "a
// device execution lane that does not route through the same gate is not a new
// hand, it is a hole in the gate." So this hand carries no gate. It refuses to
// move without the SERVER's approval record, bound to this exact version.

check("no approval record on the plan and the hand will not move",
      refusal(decide(row(params: params(approval: NSNull())))) == .noApproval)
check("an approval for a different plan does not release this one",
      refusal(decide(row(params: params(
          approval: approvalBlob(planID: "pln_other"))))) == .approvalUnbound)
check("an approval for an earlier version does not release this one",
      refusal(decide(row(params: params(
          approval: approvalBlob(version: VERSION - 1))))) == .approvalUnbound)
check("an approval carrying a different scope digest does not release this one",
      refusal(decide(row(params: params(
          approval: approvalBlob(digest: "sha256:tampered"))))) == .approvalUnbound)

// The row and the plan travelled separately to reach this phone.
check("a row whose plan id disagrees with its own blob is refused",
      refusal(decide(row(workflowID: "pln_other"))) == .rowDisagreesWithPlan)
check("a row whose version disagrees with its own blob is refused",
      refusal(decide(row(workflowVersion: 9))) == .rowDisagreesWithPlan)
check("a row whose scope digest disagrees with its own blob is refused",
      refusal(decide(row(scopeDigest: "sha256:other"))) == .rowDisagreesWithPlan)
check("a row with no scope digest at all is refused",
      refusal(decide(row(scopeDigest: ""))) == .rowDisagreesWithPlan)

// THE §5.4 ATTACK, ARRIVING FROM THE DEVICE SIDE. A plan that labels itself
// Shelf 2 gets no exemption from a label: the admitted set here is EMPTY.
check("the device admits NOTHING for act-and-tell today",
      CalendarHandPolicy.admittedForActAndTell.isEmpty)
check("a plan claiming act-and-tell for a calendar write is refused, not run",
      refusal(decide(row(consequence: "reversible_local",
                         params: params(consequence: "reversible_local"))))
        == .actAndTellNotAdmitted(CalendarHandPolicy.writeActType))
check("...and the refusal names the act type it refused",
      refusal(decide(row(consequence: "reversible_local",
                         params: params(consequence: "reversible_local"))))?
        .code == "calhand.act_and_tell_not_admitted")
// The blob and the column travelled separately. A plan that claims the shelf in
// ONE of them is claiming it; reading only the preferred witness is a side door.
check("the shelf claim is caught when only the plan blob makes it",
      refusal(decide(row(consequence: "consequential",
                         params: params(consequence: "reversible_local"))))
        == .actAndTellNotAdmitted(CalendarHandPolicy.writeActType))
check("the shelf claim is caught when only the row column makes it",
      refusal(decide(row(consequence: "reversible_local",
                         params: params(consequence: "consequential"))))
        == .actAndTellNotAdmitted(CalendarHandPolicy.writeActType))

// A version written by the server's JavaScript arrives as a JSON float. If it
// stopped binding, EVERY calendar errand would strand at `rowDisagreesWithPlan`
// and the cause would read as tampering.
//
// THE HONEST LIMIT OF THIS CHECK, measured rather than assumed: NO MUTATION OF
// THE POLICY CAN MAKE IT RED TODAY. After JSONSerialization both widths are one
// `NSNumber`, and Swift's bridging casts either to `Int` — `"\(NSNumber(3.0))"`
// is even "3". So this pins a CONTRACT, not a branch: it is a tripwire for the
// refactor that swaps `as? Int` for a JSONDecoder or a strict numeric type,
// which is one edit away at all times. Said out loud because a check whose
// reach is implied gets read as proving more than it does.
check("a plan version delivered as a JSON float still binds",
      written(decide(CalendarHandPolicy.Row(
          id: "job_991", status: "queued", lane: CalendarHandPolicy.lane,
          workflowID: PLAN, workflowVersion: VERSION, scopeDigest: DIGEST,
          consequence: "consequential",
          params: json(["_workflow": [
              "plan_id": PLAN, "version": Double(VERSION),
              "scope_digest": DIGEST, "consequence": "consequential",
              "facts": [CalendarHandPolicy.titleKey: "Dinner with Priya",
                        CalendarHandPolicy.startKey: START,
                        CalendarHandPolicy.endKey: END],
              "undo": undoPlan(),
              "approval": ["plan_id": PLAN, "plan_version": Double(VERSION),
                           "scope_digest": DIGEST],
              "act": ["act_type": CalendarHandPolicy.writeActType,
                      "reach": CalendarHandPolicy.reach,
                      "executor": CalendarHandPolicy.executor,
                      "target": ["name": "our id", "provenance": "minted_by_us",
                                 "ref": "our_ref"]],
          ]])))) != nil)

// ================================================= 3. what the act declares

check("a plan with no act declaration at all is refused",
      refusal(decide(row(params: params(dropAct: true)))) == .actTypeNotAdmitted(""))
check("an act type this hand does not run is refused by name",
      refusal(decide(row(params: params(actType: "gmail_draft"))))
        == .actTypeNotAdmitted("gmail_draft"))
check("a reach this hand does not have is refused",
      refusal(decide(row(params: params(reach: "world"))))
        == .reachDisagrees("world"))
check("an executor that is a browser session is refused",
      refusal(decide(row(params: params(executor: "browser_agent"))))
        == .executorDisagrees("browser_agent"))

// ============================== 4. THE MINTED ID — the heart of the card

check("an act that never says what it will address is refused",
      refusal(decide(row(params: params(target: NSNull())))) == .actTargetUnbound)
check("a target with an empty reference is refused",
      refusal(decide(row(params: params(
          target: ["name": "x", "provenance": "minted_by_us", "ref": ""]))))
        == .actTargetUnbound)
// THE EXCLUDED SHAPE, NAMED. A target the counterparty supplies is exactly the
// Gmail-message-id case §6.1 refuses.
check("a target the owner supplied is not an id we minted",
      refusal(decide(row(params: params(
          target: ["name": "x", "provenance": "owner_supplied", "ref": "our_ref"]))))
        == .actTargetUnbound)
check("a target wearing an invented provenance tag is refused",
      refusal(decide(row(params: params(
          target: ["name": "x", "provenance": "returned_by_provider", "ref": "our_ref"]))))
        == .actTargetUnbound)

// ============================================ 5. the undo plan, structurally

check("no undo plan at all and the act is refused",
      refusal(decide(row(params: params(undo: [:])))) == .noUndoPlan)
check("an undo plan with no steps is not an executable undo",
      refusal(decide(row(params: params(undo: undoPlan(steps: []))))) == .noUndoPlan)
check("an undo written for a different act is refused",
      refusal(decide(row(params: params(undo: undoPlan(actType: "local_draft")))))
        == .undoAddressesAnotherAct)

check("an undo input wearing a tag outside the closed set is refused",
      refusal(decide(row(params: params(undo: undoPlan(inputs: [
          ["name": "our id", "provenance": "minted_by_us", "ref": "our_ref"],
          ["name": "id", "provenance": "returned_by_eventkit", "ref": "our_ref"],
      ]))))) == .unknownProvenance("returned_by_eventkit"))

// ★ THE ONE THIS WHOLE TYPE EXISTS FOR ★
//
// An undo that says "remove the event whose identifier EventKit gave us" can
// tag that input `minted_by_us` and name it anything it likes. It still cannot
// RESOLVE, because the value does not exist until after the act — and the
// checker discovers that by trying to resolve it and failing, never by reading
// what it is called (§5.2).
check("an undo needing the identifier EventKit will return does not resolve",
      refusal(decide(row(params: params(undo: undoPlan(inputs: [
          ["name": "our id", "provenance": "minted_by_us", "ref": "our_ref"],
          ["name": "event id", "provenance": "minted_by_us",
           "ref": "ek_event_identifier"],
      ]))))) == .unresolvedReference("ek_event_identifier"))
check("...and naming that field owner_supplied does not save it either",
      refusal(decide(row(params: params(undo: undoPlan(inputs: [
          ["name": "our id", "provenance": "minted_by_us", "ref": "our_ref"],
          ["name": "owner_supplied_reference", "provenance": "owner_supplied",
           "ref": "ek_event_identifier"],
      ]))))) == .unresolvedReference("ek_event_identifier"))
check("a reference held as JSON null does not resolve",
      refusal(decide(row(params: params(undo: undoPlan(
          held: ["minted_by_us": ["our_ref": NSNull()],
                 "owner_supplied": ["calendar_start": START],
                 "constant": ["undo_window_padding": 86400]])))))
        == .unresolvedReference("our_ref"))
check("a reference held as the empty string does not resolve",
      refusal(decide(row(params: params(undo: undoPlan(
          held: ["minted_by_us": ["our_ref": "  "],
                 "owner_supplied": ["calendar_start": START],
                 "constant": ["undo_window_padding": 86400]])))))
        == .unresolvedReference("our_ref"))
// The two above are ALSO caught by the target's own guard, so on their own
// they cannot tell whether the input loop resolves anything. Found by mutation:
// making `resolves` accept null and accept "" left both of them green. These
// two use a NON-target reference, where the input loop is the only thing
// standing there.
check("a NON-target reference held as JSON null does not resolve either",
      refusal(decide(row(params: params(undo: undoPlan(
          held: ["minted_by_us": ["our_ref": OUR_REF],
                 "owner_supplied": ["calendar_start": NSNull()],
                 "constant": ["undo_window_padding": 86400]])))))
        == .unresolvedReference("calendar_start"))
check("a NON-target reference held as whitespace does not resolve either",
      refusal(decide(row(params: params(undo: undoPlan(
          held: ["minted_by_us": ["our_ref": OUR_REF],
                 "owner_supplied": ["calendar_start": "   "],
                 "constant": ["undo_window_padding": 86400]])))))
        == .unresolvedReference("calendar_start"))
check("a reference into a bucket that does not exist does not resolve",
      refusal(decide(row(params: params(undo: undoPlan(
          held: ["minted_by_us": ["our_ref": OUR_REF],
                 "owner_supplied": ["calendar_start": START]])))))
        == .unresolvedReference("undo_window_padding"))
// And a held value that is not text still resolves: the padding is a number,
// and "resolvable" means "we already have it", not "it is a string".
check("a numeric constant is a value we already hold",
      written(decide(row())) != nil)

check("an undo binding only owner-supplied and constant values binds nothing of ours",
      refusal(decide(row(params: params(undo: undoPlan(inputs: [
          ["name": "when", "provenance": "owner_supplied", "ref": "calendar_start"],
          ["name": "pad", "provenance": "constant", "ref": "undo_window_padding"],
      ]))))) == .undoBindsNothing)

// PRESENCE IS NOT CORRESPONDENCE. A well-formed undo that addresses a
// different minted id is an undo that cannot undo.
check("an undo addressing a DIFFERENT minted id misses the target",
      refusal(decide(row(params: params(undo: undoPlan(
          inputs: [["name": "some id", "provenance": "minted_by_us",
                    "ref": "other_ref"]],
          held: ["minted_by_us": ["our_ref": OUR_REF,
                                  "other_ref": "0000-not-the-one"],
                 "owner_supplied": ["calendar_start": START],
                 "constant": ["undo_window_padding": 86400]])))))
        == .undoMissesTheTarget)

// The act's own target is held to the same standard as any other reference.
check("a target that resolves to nothing is refused",
      refusal(decide(row(params: params(
          target: ["name": "x", "provenance": "minted_by_us", "ref": "our_ref"],
          undo: undoPlan(
              inputs: [["name": "our id", "provenance": "minted_by_us",
                        "ref": "our_ref"]],
              held: ["minted_by_us": ["our_ref": 12345],
                     "owner_supplied": ["calendar_start": START],
                     "constant": ["undo_window_padding": 86400]])))))
        == .unresolvedReference("our_ref"))

// ================================================= 6. the facts, never prose

check("a missing title is named, not guessed",
      refusal(decide(row(params: params(facts: [
          CalendarHandPolicy.startKey: START,
          CalendarHandPolicy.endKey: END]))))
        == .factsIncomplete([CalendarHandPolicy.titleKey]))
check("a missing end time is named, not defaulted to an hour",
      refusal(decide(row(params: params(facts: [
          CalendarHandPolicy.titleKey: "Dinner with Priya",
          CalendarHandPolicy.startKey: START]))))
        == .factsIncomplete([CalendarHandPolicy.endKey]))
check("everything missing is listed at once, in a stable order",
      refusal(decide(row(params: params(facts: [:]))))
        == .factsIncomplete([CalendarHandPolicy.titleKey,
                             CalendarHandPolicy.startKey,
                             CalendarHandPolicy.endKey]))
check("a whitespace title is a missing title",
      refusal(decide(row(params: params(facts: [
          CalendarHandPolicy.titleKey: "   ",
          CalendarHandPolicy.startKey: START,
          CalendarHandPolicy.endKey: END]))))
        == .factsIncomplete([CalendarHandPolicy.titleKey]))

// LAW 1. Resolving "Thursday 7pm" is the MODEL's job and it arrives already
// resolved. Prose reaching this hand is a refusal naming the key, never a
// parse — there is no path in the policy from a weekday word to a Date.
check("prose where an instant should be is refused by key name",
      refusal(decide(row(params: params(facts: [
          CalendarHandPolicy.titleKey: "Dinner with Priya",
          CalendarHandPolicy.startKey: "Thursday 7pm",
          CalendarHandPolicy.endKey: END]))))
        == .unreadableFact(CalendarHandPolicy.startKey))
check("an unreadable end is refused by its own key name",
      refusal(decide(row(params: params(facts: [
          CalendarHandPolicy.titleKey: "Dinner with Priya",
          CalendarHandPolicy.startKey: START,
          CalendarHandPolicy.endKey: "later that evening"]))))
        == .unreadableFact(CalendarHandPolicy.endKey))
check("a local time with no zone is not an instant",
      refusal(decide(row(params: params(facts: [
          CalendarHandPolicy.titleKey: "Dinner with Priya",
          CalendarHandPolicy.startKey: "2026-08-27T19:00:00",
          CalendarHandPolicy.endKey: END]))))
        == .unreadableFact(CalendarHandPolicy.startKey))
// Both stamp widths are read: this app writes fractional seconds, Python's
// isoformat() omits them at a whole second.
check("a stamp carrying fractional seconds is read",
      written(decide(row(params: params(facts: [
          CalendarHandPolicy.titleKey: "Dinner with Priya",
          CalendarHandPolicy.startKey: "2026-08-27T19:00:00.000Z",
          CalendarHandPolicy.endKey: END])))) != nil)

check("an event that ends before it starts is refused",
      refusal(decide(row(params: params(facts: [
          CalendarHandPolicy.titleKey: "Dinner with Priya",
          CalendarHandPolicy.startKey: END,
          CalendarHandPolicy.endKey: START]))))
        == .endsBeforeItStarts)
check("a zero-length event is refused",
      refusal(decide(row(params: params(facts: [
          CalendarHandPolicy.titleKey: "Dinner with Priya",
          CalendarHandPolicy.startKey: START,
          CalendarHandPolicy.endKey: START]))))
        == .endsBeforeItStarts)

// A queue that sat still is not a licence to write last week's dinner.
let afterTheDinner = CalendarHandPolicy.instant("2026-08-28T09:00:00Z")!
check("a write whose start has already passed is refused",
      refusal(decide(row(), now: afterTheDinner)) == .startAlreadyPast)
check("a write starting exactly now is refused",
      refusal(decide(row(), now: CalendarHandPolicy.instant(START)!))
        == .startAlreadyPast)
// But removing an event whose time has passed is still what the owner asked
// for, so the undo is not fenced by the clock.
check("an undo of an event already in the past still runs",
      undone(decide(row(params: params(actType: CalendarHandPolicy.undoActType)),
                    now: afterTheDinner)) != nil)

// ============================================== 7. the device, and stranger

check("no writable calendar on this phone and the hand refuses loudly",
      refusal(decide(row(), calendar: nil)) == .noWritableCalendar)
// research §4 trade 2: EventKit writes into whichever account the device holds,
// so a stranger with no Google account configured gets a write that never
// reaches calendar.google.com. Not a refusal — a local calendar is a real
// calendar — but the sentence she says afterwards has to be able to say so.
check("a write that lands only on this device says so",
      written(decide(row(), calendar: onDeviceOnly))?
        .target.landsOnlyOnThisDevice == true)
check("a write into a synced account says that too",
      written(decide(row()))?.target.landsOnlyOnThisDevice == false)

// ==================================================== 8. what actually runs

guard let w = written(decide(row())) else {
    check("an approved, provenance-clean calendar write runs", false)
    print("\(failures) FAILED"); exit(1)
}
check("an approved, provenance-clean calendar write runs", true)
check("it carries the job it came from", w.jobID == "job_991")
check("it is bound to the exact plan version that was approved",
      w.planID == PLAN && w.planVersion == VERSION)
check("the title is the model's, verbatim", w.title == "Dinner with Priya")
check("the start is the instant the plan carried",
      w.start == CalendarHandPolicy.instant(START))
check("the end is the instant the plan carried",
      w.end == CalendarHandPolicy.instant(END))

// THE ID IS THE RESOLVED VALUE, NOT THE REFERENCE NAME. `ref` is a key into
// `held` — brain/workflow.py _resolves_one does `bucket[item.ref]` — so a hand
// that stamped "our_ref" onto the event would stamp the same string onto every
// event it ever wrote, and one undo would sweep all of them.
check("the id stamped on the event is the uuid we minted, not the reference name",
      w.ourRef == OUR_REF)
check("the stamp is the event's url, carrying our id",
      w.stamp == .url("anticipy://act/\(OUR_REF)"))

// The permission string the owner already read says "She never reads the notes
// or the invitees". An undo that searched notes would read the notes of every
// event in its window.
if case .url(let value) = w.stamp {
    check("the stamp is a url and nothing else", value.hasPrefix("anticipy://"))
}
check("Stamp offers no notes case at all",
      CalendarHandPolicy.Stamp.url("x") == .url("x"))

// The undo's search window is computed NOW, from values that all resolve NOW.
check("the undo window opens a day before the event",
      w.undoWindow.from == CalendarHandPolicy.instant(START)!
        .addingTimeInterval(-86400))
check("the undo window closes a day after it",
      w.undoWindow.to == CalendarHandPolicy.instant(END)!
        .addingTimeInterval(86400))

guard let u = undone(decide(row(params: params(
    actType: CalendarHandPolicy.undoActType)))) else {
    check("an approved undo runs", false)
    print("\(failures) FAILED"); exit(1)
}
check("an approved undo runs", true)
check("the undo searches for the SAME id the write minted", u.ourRef == OUR_REF)
check("the undo looks for it under the same stamp",
      u.stamp == .url("anticipy://act/\(OUR_REF)"))
check("the undo searches the window the write recorded",
      u.searchWindow == w.undoWindow)

// ================================================== 9. unreadable is refused

check("params that are not JSON at all are refused",
      refusal(decide(row(params: "{not json"))) == .malformedParams)
check("params with no workflow blob are refused",
      refusal(decide(row(params: "{\"source\":\"hi\"}"))) == .malformedParams)
check("an empty params column is refused",
      refusal(decide(row(params: ""))) == .malformedParams)
check("a JSON array is not a plan", refusal(decide(row(params: "[1,2]")))
        == .malformedParams)

// ============================================ 10. every refusal is countable
// §11: reasons are enumerated causes, not free text — a shelf that refuses in
// prose cannot be widened on evidence, because nobody can count what it
// refused. A shared code is a refusal nobody can tell from another one.

let everyRefusal: [CalendarHandPolicy.Refusal] = [
    .malformedParams, .actTypeNotAdmitted("a"), .reachDisagrees("a"),
    .executorDisagrees("a"), .actAndTellNotAdmitted("a"), .rowDisagreesWithPlan,
    .noApproval, .approvalUnbound, .actTargetUnbound, .noUndoPlan,
    .undoAddressesAnotherAct, .unknownProvenance("a"), .unresolvedReference("a"),
    .undoBindsNothing, .undoMissesTheTarget, .factsIncomplete(["a"]),
    .unreadableFact("a"), .endsBeforeItStarts, .startAlreadyPast,
    .noWritableCalendar,
]
let codes = everyRefusal.map(\.code)
check("every refusal cause has its own code",
      Set(codes).count == everyRefusal.count)
check("every code is namespaced to this hand",
      codes.allSatisfy { $0.hasPrefix("calhand.") })

print(failures == 0 ? "all calendar hand checks passed" : "\(failures) FAILED")
exit(failures == 0 ? 0 : 1)
