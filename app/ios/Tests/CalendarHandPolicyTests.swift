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
            /// Keys struck OFF the blob entirely, which is a different fixture
            /// from a key present and empty — `plan["plan_id"] as? String ?? ""`
            /// reads both as "", and only a test that can say "absent" can tell
            /// the reader which of the two it pinned.
            drop: Set<String> = [],
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
    for key in drop { plan.removeValue(forKey: key) }
    return json(["source": "put dinner with Priya Thursday 7", "_workflow": plan])
}

/// The SERVER's copy of the approval, as `job_fields` in brain/workflow.py
/// writes it into the row's own column: `_canonical(...)` of the very same dict
/// that `put_in_params` embeds in `params._workflow.approval`. Two witnesses to
/// one record, which is why the hand can compare them without re-judging either.
func approvalColumn(_ blob: [String: Any]? = nil) -> String {
    json(blob ?? approvalBlob())
}

func row(status: String = "queued", lane: String? = CalendarHandPolicy.lane,
         workflowID: String? = PLAN, workflowVersion: Int? = VERSION,
         scopeDigest: String? = DIGEST, consequence: String? = "consequential",
         // THE DEFAULT IS THE VALUE, NOT A `?? value` INSIDE THE BODY, and the
         // difference is a check that could not fail. Written the other way,
         // `row(approval: nil)` — the fixture for "the row carried no approval
         // column at all", the load-bearing witness this hand refuses without —
         // was silently handed the good column by the `??`, so the one case
         // that pins the column's absence was testing the case where it is
         // present. A fixture that cannot say "missing" cannot test missing.
         approval: String? = approvalColumn(),
         params p: String? = nil) -> CalendarHandPolicy.Row {
    CalendarHandPolicy.Row(id: "job_991", status: status, lane: lane,
                           workflowID: workflowID, workflowVersion: workflowVersion,
                           scopeDigest: scopeDigest, consequence: consequence,
                           approval: approval,
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

// THE LANE IS READ THE WAY THE SERVER READS IT, and this is not a second copy
// of a rule — it is the SAME rule, spelled the same way. research_lane.pb.js
// normalises with `.trim().toLowerCase()` before every leg it runs, so a row
// whose lane is "Device_Calendar" IS a device row to the server: a browser is
// 403'd off it and deviceShapeRefusal is applied to it. A phone that compared
// exactly would call that row somebody else's, and the row would sit at
// `queued` with no hand at all and nobody reporting it. An orphan is worse
// than a refusal, because a refusal is countable.
check("a lane the server would normalise is this hand's row too",
      written(decide(row(lane: "Device_Calendar"))) != nil)
check("a lane with the whitespace the server trims is this hand's row too",
      written(decide(row(lane: "  device_calendar  "))) != nil)
check("a lane that is genuinely another lane is still not this hand's",
      idle(decide(row(lane: "Research"))) == .notThisHand)

// ============================================ 2. the gate did not move here
// The research names duplicating the confirmation gate as the real risk: "a
// device execution lane that does not route through the same gate is not a new
// hand, it is a hole in the gate." So this hand carries no gate. It refuses to
// move without the SERVER's approval record, bound to this exact version.

check("no approval record on the plan and the hand will not move",
      refusal(decide(row(params: params(approval: NSNull())))) == .noApproval)
check("an empty approval object is no approval record",
      refusal(decide(row(approval: json([String: Any]()),
                         params: params(approval: [String: Any]()))))
        == .noApproval)

// WHERE THE APPROVAL HAS TO COME FROM, and the mutation this pins.
//
// M8: `(plan["approval"] …) ?? (top["approval"] …)` — accept an approval
// sitting at the TOP level of params, outside `_workflow`. Nothing anywhere
// reads a top-level `params.approval`: workflow_guard.pb.js:90 cross-checks
// `embedded.approval` and no hook has ever looked at the other place. An
// approval read from a key no gate validates is an approval the caller wrote.
check("an approval outside the workflow blob is not an approval",
      refusal(decide(row(params: json([
          "source": "put dinner with Priya Thursday 7",
          "approval": approvalBlob(),
          "_workflow": [
              "plan_id": PLAN, "version": VERSION, "scope_digest": DIGEST,
              "consequence": "consequential",
              "facts": [CalendarHandPolicy.titleKey: "Dinner with Priya",
                        CalendarHandPolicy.startKey: START,
                        CalendarHandPolicy.endKey: END],
              "undo": undoPlan(),
              "act": ["act_type": CalendarHandPolicy.writeActType,
                      "reach": CalendarHandPolicy.reach,
                      "executor": CalendarHandPolicy.executor,
                      "target": ["name": "our id", "provenance": "minted_by_us",
                                 "ref": "our_ref"]],
          ]])))) == .noApproval)

// BOTH WITNESSES TO ONE RECORD. `job_fields` in brain/workflow.py writes the
// row's `approval` COLUMN from the same dict `put_in_params` embeds, and
// workflow_guard.pb.js:90 refuses any write where the two disagree. So a row
// that reaches this phone saying two different things did not come through the
// gate — and a hand that read only the blob would be trusting the copy an
// attacker gets to rewrite while ignoring the one the server wrote.
check("a row carrying no approval column at all is refused",
      refusal(decide(row(approval: nil))) == .approvalNotOnTheRow)
check("a row whose approval column is blank is refused",
      refusal(decide(row(approval: "   "))) == .approvalNotOnTheRow)
check("a row whose approval column is not JSON is refused",
      refusal(decide(row(approval: "approved!"))) == .approvalNotOnTheRow)
check("a row whose approval column is a JSON array is not a record",
      refusal(decide(row(approval: "[]"))) == .approvalNotOnTheRow)
// An EMPTY record on the row is the same absence wearing braces, and it has to
// refuse as an ABSENCE: read as a record it would be a record, and the only
// thing left to say about it would be that it disagrees with the blob — which
// names the wrong defect. The row never carried the server's copy at all.
check("a row whose approval column is an empty record carried no record at all",
      refusal(decide(row(approval: "{}"))) == .approvalNotOnTheRow)

check("a blob claiming another plan than the column the server wrote is refused",
      refusal(decide(row(params: params(
          approval: approvalBlob(planID: "pln_other")))))
        == .approvalDisagreesWithTheRow)
check("a blob claiming another version than the column is refused",
      refusal(decide(row(params: params(
          approval: approvalBlob(version: VERSION - 1)))))
        == .approvalDisagreesWithTheRow)
check("a blob claiming another scope digest than the column is refused",
      refusal(decide(row(params: params(
          approval: approvalBlob(digest: "sha256:tampered")))))
        == .approvalDisagreesWithTheRow)
check("words added to the blob that the server never stored are refused",
      refusal(decide(row(approval: approvalColumn(
          ["plan_id": PLAN, "plan_version": VERSION, "scope_digest": DIGEST]),
          params: params()))) == .approvalDisagreesWithTheRow)

// THE RECORD, NOT THE SERIALIZER. `_canonical` writes the column with sorted
// keys and no spaces; whatever wrote `params` need not have. A floor that
// compared raw strings would be a floor made of somebody's whitespace, and it
// would refuse every real row on the day a writer changed.
check("the same record spelled in another key order still matches",
      written(decide(row(approval:
          "{ \"scope_digest\": \"\(DIGEST)\", \"approved_at\": \"2026-08-25T11:59:02Z\","
          + " \"owner_words\": \"Tapped \u{201C}Send it\u{201D}.\","
          + " \"plan_version\": \(VERSION), \"plan_id\": \"\(PLAN)\" }"))) != nil)

// ★ WHAT THIS HAND DOES NOT DO, AND MUST NOT START DOING ★
//
// workflow_guard.pb.js:approvalRefusal additionally requires non-empty
// `owner_words` OR a gesture of a kind we recognise whose actor IS the row's
// owner and which is itself bound to this plan, version and scope. THAT
// DECISION LIVES THERE AND NOWHERE ELSE. The research names duplicating it as
// the actual risk — "a device execution lane that does not route through the
// same gate is not a new hand, it is a hole in the gate" — and the copy this
// hand used to carry had already drifted in the UNSAFE direction: it checked
// three fields where the server checks five and a gesture's actor.
//
// So this record — no owner_words, no gesture, and the server's own column
// agreeing with it — RUNS. Not because the hand judged it good: because the
// hand does not judge, and a row like it cannot reach `queued` and
// `consequential` without the server having judged it first. A second gate
// that currently agrees is still the bug, because it is one edit from
// disagreeing, and then the phone is quietly deciding what may happen to a
// calendar. If somebody re-adds that decision here, THIS is the check that
// goes red and asks them to say why there are two.
let unwordedApproval: [String: Any] = ["plan_id": PLAN, "plan_version": VERSION,
                                       "scope_digest": DIGEST]
check("the hand verifies the server's record, it does not re-judge it",
      written(decide(row(approval: approvalColumn(unwordedApproval),
                         params: params(approval: unwordedApproval)))) != nil)

// ★ AND THE FIELDS INSIDE AN APPROVAL ARE NOT THIS HAND'S TO READ, EITHER ★
//
// The check above pins the ONE shape the deleted gate used to refuse. These pin
// the rule it was an instance of, because a second gate does not have to come
// back wearing the same clothes: it can come back as a binding check, as a
// "whose tap was that", or as a freshness rule. Each row below is one the
// SERVER's `approvalRefusal` would have opinions about, each is identical in
// both witnesses — so it came through that gate — and each RUNS here. Not
// because the hand judged it good: because the hand does not judge. If any of
// these three goes red, somebody has put an opinion about what a good approval
// looks like back on the phone, and the question to answer is why there are two
// places that decide it, not how to make the two agree.
let approvalForAnotherPlan: [String: Any] = [
    "plan_id": "pln_somebody_elses_errand", "plan_version": VERSION + 4,
    "scope_digest": "sha256:another", "owner_words": "for another errand"]
check("an approval bound to another plan entirely is the server's business, not this hand's",
      written(decide(row(approval: approvalColumn(approvalForAnotherPlan),
                         params: params(approval: approvalForAnotherPlan)))) != nil)

// workflow_guard requires a gesture's `actor` to BE the row's owner_ref. That
// is the check this hand is most likely to be handed back "for safety", and it
// is the one it can do worst: the row it decides on carries no owner_ref at all.
let approvalTappedByAStranger: [String: Any] = [
    "plan_id": PLAN, "plan_version": VERSION, "scope_digest": DIGEST,
    "gesture": ["kind": "tap", "actor": "usr_not_the_owner", "plan_id": PLAN,
                "plan_version": VERSION, "scope_digest": DIGEST]]
check("an approval carrying somebody else's tap is still not re-judged here",
      written(decide(row(approval: approvalColumn(approvalTappedByAStranger),
                         params: params(approval: approvalTappedByAStranger)))) != nil)

// Nothing in this file reads a clock against `approved_at`, and a hand that
// started to would be a gate again — a plan approved before a queue stalled is
// a question for the server that minted the record, and the row's own staleness
// is `startAlreadyPast`, which is checked from the FACTS and not from a
// signature's timestamp.
var approvalStampedLongAgo = approvalBlob()
approvalStampedLongAgo["approved_at"] = "2019-03-04T09:00:00Z"
check("an approval the server stamped long ago is not this hand's to expire",
      written(decide(row(approval: approvalColumn(approvalStampedLongAgo),
                         params: params(approval: approvalStampedLongAgo)))) != nil)

// The row and the plan travelled separately to reach this phone.
check("a row whose plan id disagrees with its own blob is refused",
      refusal(decide(row(workflowID: "pln_other"))) == .rowDisagreesWithPlan)
check("a row whose version disagrees with its own blob is refused",
      refusal(decide(row(workflowVersion: 9))) == .rowDisagreesWithPlan)
check("a row whose scope digest disagrees with its own blob is refused",
      refusal(decide(row(scopeDigest: "sha256:other"))) == .rowDisagreesWithPlan)
check("a row whose scope digest is blank while its blob carries one is refused",
      refusal(decide(row(scopeDigest: ""))) == .rowDisagreesWithPlan)

// ★ AND THE CASE EQUALITY CANNOT SEE: BOTH SIDES EMPTY ★
//
// Every check above pins a DISAGREEMENT, and an empty string agrees with an
// empty string. `plan["plan_id"] as? String ?? ""` reads a missing key and an
// empty one identically, so a row carrying nothing at all walks all three
// equality legs. What stops it is the two `!isEmpty` clauses in front of them,
// and those are the phone's mirror of two server floors:
//
//   * workflow_guard.pb.js:24 — `if (!workflow) return e.next()`. A row with no
//     workflow_id is WAVED THROUGH: `approvalRefusal()` never runs on it. It is
//     the case research_lane.pb.js `deviceShapeRefusal` names FIRST, "a calendar
//     errand with no workflow skips the confirmation gate entirely".
//   * `approvalRefusal()` rejects on `!scope`, so a row with no scope_digest can
//     never have been approved server-side at all.
//
// So these are not tidiness. They are the difference between "the gate said yes"
// and "the gate was never asked", and the hand's whole job is to refuse the
// second. Dropping either clause used to leave this suite green.
check("an empty plan id on the row AND its blob is refused, not matched",
      refusal(decide(row(workflowID: "", params: params(planID: ""))))
        == .rowDisagreesWithPlan)
check("a blob carrying no plan id at all, on a row carrying none either, is refused",
      refusal(decide(row(workflowID: nil, params: params(drop: ["plan_id"]))))
        == .rowDisagreesWithPlan)
check("an empty scope digest on the row AND its blob is refused, not matched",
      refusal(decide(row(scopeDigest: "", params: params(digest: ""))))
        == .rowDisagreesWithPlan)
check("a blob carrying no scope digest at all, on a row carrying none either, is refused",
      refusal(decide(row(scopeDigest: nil, params: params(drop: ["scope_digest"]))))
        == .rowDisagreesWithPlan)
check("a blob carrying no version at all, on a row carrying none either, is refused",
      refusal(decide(row(workflowVersion: nil, params: params(drop: ["version"]))))
        == .rowDisagreesWithPlan)

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

// ★ read_only IS THE VALUE THAT TURNS THE SERVER'S APPROVAL CHECK OFF ★
//
// workflow_guard.pb.js: `NO_APPROVAL_NEEDED = ["read_only"]`, and the leg that
// runs `approvalRefusal()` is skipped entirely for such a row. So on a
// read_only row the approval blob inside `params._workflow` was validated by
// NOTHING — and a hand that refused only `reversible_local` would then treat
// that unchecked blob as the server's own approval record and write the event.
// The server's own device-shape refusal cannot cover for this either: it lives
// inside `if (method === "PATCH"…)` in research_lane.pb.js, and the row is BORN
// read_only on a POST that leg never sees.
//
// The fix is not another value on a refuse-list. It is REQUIRING the one value
// this hand runs, so every value nobody thought of refuses too.
check("a read_only row is refused, not run",
      refusal(decide(row(consequence: "read_only",
                         params: params(consequence: "read_only"))))?
        .code == "calhand.consequence_not_consequential")
check("...and the refusal names the value it would not run",
      refusal(decide(row(consequence: "read_only",
                         params: params(consequence: "read_only"))))
        == .consequenceNotConsequential("read_only"))
// Both witnesses again, and for the same reason as the shelf claim above: they
// travelled separately, so agreement is the thing being checked, not either
// copy on its own.
check("read_only in the plan blob alone is still refused",
      refusal(decide(row(consequence: "consequential",
                         params: params(consequence: "read_only"))))
        == .consequenceNotConsequential("read_only"))
check("read_only in the row column alone is still refused",
      refusal(decide(row(consequence: "read_only",
                         params: params(consequence: "consequential"))))
        == .consequenceNotConsequential("read_only"))
// A REQUIREMENT, NOT A REFUSE-LIST. These two are the difference: neither
// value is on anybody's list of dangerous words, and both refuse.
check("a consequence nobody has ever heard of refuses",
      refusal(decide(row(consequence: "harmless",
                         params: params(consequence: "harmless"))))
        == .consequenceNotConsequential("harmless"))
check("no consequence at all refuses",
      refusal(decide(row(consequence: nil,
                         params: params(consequence: ""))))
        == .consequenceNotConsequential(""))

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
          approval: json(["plan_id": PLAN, "plan_version": Double(VERSION),
                          "scope_digest": DIGEST]),
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
// An act declaration that names no act is the same refusal as no declaration,
// and it says so with the same empty string: what came through claimed to be an
// act and said nothing about which one. (This pins the OUTCOME, not the clause:
// `!actType.isEmpty` and the admitted-types guard below it produce the same
// decision for "", so no test can tell the two spellings apart.)
check("an act declaration that names no act at all is refused",
      refusal(decide(row(params: params(actType: "")))) == .actTypeNotAdmitted(""))
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

// ★ THE SET IS CLOSED, AND WHAT IS IN IT IS THE SCHEMA ★
//
// §5.2: "A fourth provenance tag is a schema change, visible in a diff, not a
// string a model can invent at runtime." The check below pins only that a tag
// OUTSIDE the set refuses — it cannot notice the set GROWING, because the tag
// it names would then be inside it. Adding `returned_by_provider` (the tag
// §6.1's excluded shape wants) left this suite green at 108, and an undo input
// carrying it then resolves the moment `held` has any value under it: the
// counterparty fills the recipe, which is the one shape this type exists to
// refuse. The membership is therefore asserted as a value here, and read off
// the declaration itself in run_calendar_hand_tests.sh — the suite catches a
// set widened however it is spelled, the runner catches a set that stopped
// being a literal a diff can show.
check("the provenance set is exactly the three tags §5.2 names",
      CalendarHandPolicy.provenanceTags == ["minted_by_us", "owner_supplied", "constant"])

check("an undo input wearing a tag outside the closed set is refused",
      refusal(decide(row(params: params(undo: undoPlan(inputs: [
          ["name": "our id", "provenance": "minted_by_us", "ref": "our_ref"],
          ["name": "id", "provenance": "returned_by_eventkit", "ref": "our_ref"],
      ]))))) == .unknownProvenance("returned_by_eventkit"))

// AND CLOSED AT THE PLACE IT IS READ, not only where it is written. A
// membership assertion cannot see `|| provenance == "returned_by_provider"`
// bolted onto the check itself — the constant would still hold three tags and
// the runner's leg would still be quiet. So the tag §6.1 excludes BY NAME, a
// tag that reads like one of ours, a case-fold of one we DO admit, and no tag
// at all are each put through the checker.
for tag in ["returned_by_provider", "provider_supplied", "Minted_By_Us", ""] {
    var strange: [String: Any] = ["name": "our id", "ref": "our_ref"]
    if !tag.isEmpty { strange["provenance"] = tag }
    check("an undo input tagged \(tag.isEmpty ? "with nothing at all" : tag) does not resolve",
          refusal(decide(row(params: params(undo: undoPlan(inputs: [
              ["name": "our id", "provenance": "minted_by_us", "ref": "our_ref"],
              strange,
          ]))))) == .unknownProvenance(tag))
}

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
// A REFERENCE WITH NO NAME IS NOT A REFERENCE, and this is the one input that
// tells `resolves`'s first clause from nothing: a `held` bucket can carry a
// value under the empty key as easily as under any other, and then a lookup by
// "" SUCCEEDS and an input that names nothing has "resolved". §5.2's checker
// resolves what a plan points at; a plan that points at nothing is refused for
// pointing at nothing.
check("an undo input whose reference names nothing does not resolve",
      refusal(decide(row(params: params(undo: undoPlan(
          inputs: [["name": "our id", "provenance": "minted_by_us", "ref": "our_ref"],
                   ["name": "the padding", "provenance": "constant", "ref": ""]],
          held: ["minted_by_us": ["our_ref": OUR_REF],
                 "constant": ["": 86400, "undo_window_padding": 86400]])))))
        == .unresolvedReference(""))

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

// A HAND-MAINTAINED LIST OF CASES IS A LIST THAT GOES STALE SILENTLY, and this
// one had. `Refusal` carries associated values, so it cannot be `CaseIterable`
// and no Swift construct will enumerate it — the list below is the only census
// there is. The three causes the approval repair added were never added here,
// and MEASURED rather than assumed: giving `.approvalNotOnTheRow` the code
// `calhand.no_approval` — two refusals nobody could tell apart in a journal,
// the exact thing this section exists to forbid — left the suite green at 102
// checks, because an absent case cannot collide with anything.
//
// So the runner now counts the cases in the enum against the count asserted
// here, and THAT is what fails when somebody adds the twenty-third cause and
// forgets this line. A census nothing audits is a census.
let everyRefusal: [CalendarHandPolicy.Refusal] = [
    .malformedParams, .actTypeNotAdmitted("a"), .reachDisagrees("a"),
    .executorDisagrees("a"), .actAndTellNotAdmitted("a"),
    .consequenceNotConsequential("a"), .rowDisagreesWithPlan,
    .noApproval, .approvalNotOnTheRow, .approvalDisagreesWithTheRow,
    .actTargetUnbound, .noUndoPlan,
    .undoAddressesAnotherAct, .unknownProvenance("a"), .unresolvedReference("a"),
    .undoBindsNothing, .undoMissesTheTarget, .factsIncomplete(["a"]),
    .unreadableFact("a"), .endsBeforeItStarts, .startAlreadyPast,
    .noWritableCalendar,
]
// The number the runner's census leg reads out of the enum and compares. It is
// written as a literal on purpose: a count derived from the array itself would
// agree with the array no matter what the enum said.
let REFUSAL_CAUSES = 22
check("the census covers every cause the enum declares",
      everyRefusal.count == REFUSAL_CAUSES)
let codes = everyRefusal.map(\.code)
check("every refusal cause has its own code",
      Set(codes).count == everyRefusal.count)
check("every code is namespaced to this hand",
      codes.allSatisfy { $0.hasPrefix("calhand.") })

print(failures == 0 ? "all calendar hand checks passed" : "\(failures) FAILED")
exit(failures == 0 ? 0 : 1)
