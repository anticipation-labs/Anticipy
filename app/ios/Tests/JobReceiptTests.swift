// What the SERVER verified is what the done card shows.
//
// The backend refuses to move any job to `done` without a receipt carrying
// `verified: true` and a non-empty `evidence` array (workflow_guard.pb.js:662).
// The app decoded none of it and fed the card `result` — free text the browser
// composed about its own success — so the one screen whose entire job is to be
// a receipt showed a sentence. Moment 31: "Done without proof doesn't exist."
//
// Run: sh app/ios/Tests/run_job_receipt_tests.sh
import Foundation

// Compiled by run_job_receipt_tests.sh against the REAL production sources.
var failures = 0
func check(_ name: String, _ ok: Bool) {
    print("\(ok ? "PASS" : "FAIL"): \(name)")
    if !ok { failures += 1 }
}

// A receipt exactly as `extension/workflow_state.js:122` writes one.
let realReceipt = """
{"effect_key":"book:earls-west-van:2026-08-28T19:30",
 "summary":"Booked: Earls West Van, Thu 7:30pm, 4 people, conf #R7K2",
 "evidence":["evidence:rec8813kk20","url:https://www.opentable.com/booking/confirm?id=R7K2",
             "title:Reservation confirmed | OpenTable","page:a91f0c",
             "facts:party_size,date,time,name","proof:page",
             "shot:verified-done@https://www.opentable.com/booking/confirm"],
 "verified":true,"recorded_at":"2026-08-25T02:11:04Z"}
"""

// ------------------------------------------------------- reading the column
if let r = JobReceipt.parse(realReceipt) {
    check("the effect the receipt is bound to survives",
          r.effectKey == "book:earls-west-van:2026-08-28T19:30")
    check("the server's own verified flag is carried, not assumed", r.verified)
    check("every evidence entry is kept", r.items.count == 7)
    check("a verified receipt with evidence is proof", r.isProof)
    check("the deposited photograph is noticed", r.photographed)
    check("the page it was checked on is readable",
          r.url == "https://www.opentable.com/booking/confirm?id=R7K2")
    check("the page title is readable",
          r.title == "Reservation confirmed | OpenTable")
    check("when it was recorded survives", r.recordedAt == "2026-08-25T02:11:04Z")
    // The whole point: a url is full of colons and the tag is the FIRST one.
    check("a url entry is not cut at https:",
          r.items.first { $0.kind == .url }?.value.hasPrefix("https://") == true)
    check("entries keep their original order and text",
          r.items.first?.raw == "evidence:rec8813kk20")
} else {
    check("a real receipt parses at all", false)
}

// ------------------------------------------------- nothing readable is nil
check("nil column is nil", JobReceipt.parse(nil) == nil)
check("the empty string the app writes on approve/cancel is nil",
      JobReceipt.parse("") == nil)
check("whitespace is nil", JobReceipt.parse("   \n ") == nil)
check("unparseable JSON is nil, not a half-receipt",
      JobReceipt.parse("{\"verified\":tru") == nil)
check("a JSON array is not a receipt", JobReceipt.parse("[1,2,3]") == nil)
check("free text is not a receipt", JobReceipt.parse("Booked it!") == nil)

// ------------------------------------- what must NOT read as verified proof
if let r = JobReceipt.parse("{\"verified\":true,\"evidence\":[]}") {
    check("verified with no evidence is not proof — the server would refuse it",
          !r.isProof)
} else {
    check("an empty-evidence receipt still parses", false)
}
if let r = JobReceipt.parse("{\"verified\":false,\"evidence\":[\"url:https://x.com\"]}") {
    check("evidence without verification is not proof", !r.isProof)
} else {
    check("an unverified receipt still parses", false)
}
if let r = JobReceipt.parse("{\"evidence\":[\"url:https://x.com\"]}") {
    check("a missing verified flag is not a verification", !r.verified)
    check("and therefore not proof", !r.isProof)
} else {
    check("a receipt with no verified key still parses", false)
}
// A hand-written row is not a verification. Only a real JSON true counts.
if let r = JobReceipt.parse("{\"verified\":\"true\",\"evidence\":[\"url:https://x.com\"]}") {
    check("the string \"true\" is not a verification", !r.verified && !r.isProof)
} else {
    check("a string-typed verified flag still parses", false)
}

// --------------------------------------------- entries are never rewritten
if let r = JobReceipt.parse(
    "{\"verified\":true,\"evidence\":[\"weathervane:42\",\"no-tag-at-all\",\"url:\"]}") {
    check("an unknown tag is kept, not dropped", r.items.count == 3)
    check("an unknown tag degrades to other, never to a wrong label",
          r.items[0].kind == .other && r.items[0].raw == "weathervane:42")
    check("an entry with no tag is kept verbatim",
          r.items[1].kind == .other && r.items[1].value == "no-tag-at-all")
    // An empty url must not be offered as "the page it was checked on".
    check("an empty tagged value is not passed off as a value", r.url == nil)
} else {
    check("odd entries still parse", false)
}
if let r = JobReceipt.parse("{\"verified\":true,\"evidence\":[\"url:https://x\",7,null,\"\"]}") {
    check("non-string entries are dropped rather than coerced into evidence",
          r.items.count == 1)
} else {
    check("a mixed-type evidence array still parses", false)
}
if let r = JobReceipt.parse(
    "{\"verified\":true,\"evidence\":[\"shot:verified-done(none)@https://x.com\"]}") {
    check("a milestone that took no picture is still an entry",
          r.items[0].kind == .shot)
    check("and it is not counted as a photograph", !r.photographed)
} else {
    check("a shot-only receipt still parses", false)
}

// ================================================================ the card
let goal = "Book a table for four at Earls West Van"
let result = "Booked: Earls West Van, Thu 7:30pm, 4 people, conf #R7K2"

// ----------------------------------------------- a done row with real proof
let proven = JobReceiptPolicy.doneCard(goal: goal, result: result,
                                       receipt: realReceipt)
check("the engine's words still lead — ex 77, and ex 126 forbids editing them",
      proven.lead == result)
check("the goal stays underneath so the errand is identifiable",
      proven.context == goal)
check("a server-verified receipt reads as a receipt", proven.hasReceipt)
check("and the proof itself reaches the card", proven.proof != nil)
check("nothing is called unproven when it was proven", proven.unproven == nil)
check("the card can say where it was checked",
      proven.proof?.url == "https://www.opentable.com/booking/confirm?id=R7K2")
check("the card can say there is a photograph", proven.proof?.photographed == true)
check("every evidence line reaches the card verbatim",
      proven.proof?.items.count == 7
        && proven.proof?.items.first == "evidence:rec8813kk20")
check("and when it was checked", proven.proof?.recordedAt == "2026-08-25T02:11:04Z")

// ------------------------------------------ THE DEFECT THIS LEG IS ABOUT
// A confident sentence with nothing behind it must not wear a receipt's
// clothes. This is the whole difference between a receipt and a claim.
let claimOnly = JobReceiptPolicy.doneCard(goal: goal, result: result, receipt: nil)
check("a done row with no receipt does not read as proven", !claimOnly.hasReceipt)
check("the sentence is still shown — it is what the engine said",
      claimOnly.lead == result)
check("and the card says out loud that nothing backs it",
      (claimOnly.unproven ?? "").isEmpty == false)
check("no proof block is invented for it", claimOnly.proof == nil)

let unverified = JobReceiptPolicy.doneCard(
    goal: goal, result: result,
    receipt: "{\"verified\":false,\"evidence\":[\"url:https://x.com\"]}")
check("an unverified receipt is not a receipt", !unverified.hasReceipt)
check("an unverified receipt shows no proof block", unverified.proof == nil)

let noEvidence = JobReceiptPolicy.doneCard(
    goal: goal, result: result, receipt: "{\"verified\":true,\"evidence\":[]}")
check("verified with nothing to show is not a receipt", !noEvidence.hasReceipt)

// ------------------------------------------------- the effect must match
// The guard binds the receipt to the exact effect. A receipt for a DIFFERENT
// effect on this row is the one shape that would let a photograph of one
// action vouch for another.
let mismatched = JobReceiptPolicy.doneCard(
    goal: goal, result: result, receipt: realReceipt, effectKey: "book:somewhere-else")
check("a receipt for a different effect does not vouch for this one",
      !mismatched.hasReceipt && mismatched.proof == nil)
check("and the card says why rather than going quiet",
      (mismatched.unproven ?? "").isEmpty == false)
let matched = JobReceiptPolicy.doneCard(
    goal: goal, result: result, receipt: realReceipt,
    effectKey: "book:earls-west-van:2026-08-28T19:30")
check("the matching effect is accepted", matched.hasReceipt)
// Rows predate the effect_key column; an absent one cannot be a mismatch.
let unknownEffect = JobReceiptPolicy.doneCard(
    goal: goal, result: result, receipt: realReceipt, effectKey: nil)
check("no effect on the row is not treated as a mismatch", unknownEffect.hasReceipt)
let blankEffect = JobReceiptPolicy.doneCard(
    goal: goal, result: result, receipt: realReceipt, effectKey: "")
check("an empty effect on the row is not treated as a mismatch",
      blankEffect.hasReceipt)

// ---------------------------------------------------- done with no words
let silent = JobReceiptPolicy.doneCard(goal: goal, result: "", receipt: nil)
check("done with nothing at all is named plainly, not shown as success",
      !silent.hasReceipt && silent.lead.contains("nothing came back"))
check("and the goal survives so the person knows which errand it was",
      silent.context == goal)
check("whitespace is nothing", JobReceiptPolicy
        .doneCard(goal: goal, result: "   \n", receipt: nil).lead == silent.lead)

// A receipt whose row lost its result text still has the summary the SERVER
// stored. Falling back to "nothing came back to show for it" beside a verified
// receipt would be the card calling its own proof nothing.
let summaryOnly = JobReceiptPolicy.doneCard(goal: goal, result: nil,
                                            receipt: realReceipt)
check("the receipt's own summary is used when the result column is empty",
      summaryOnly.lead == "Booked: Earls West Van, Thu 7:30pm, 4 people, conf #R7K2")
check("and it still reads as proven", summaryOnly.hasReceipt)

let noWords = JobReceiptPolicy.doneCard(
    goal: goal, result: nil,
    receipt: "{\"verified\":true,\"evidence\":[\"url:https://x.com\"]}")
check("a receipt with no words at all still reads as proven", noWords.hasReceipt)
check("and the lead does not claim nothing came back when proof exists",
      !noWords.lead.contains("nothing came back"))
check("its proof still reaches the card", noWords.proof?.items.count == 1)

// ------------------------------------------------------- the safety line
check("an uncertain effect warns about the duplicate booking",
      JobReceiptPolicy.safetyLine(effectUncertain: true).contains("two"))
check("a certain one promises nothing was lost",
      JobReceiptPolicy.safetyLine(effectUncertain: false).contains("lost"))

// ----------------------------------------- the three production wire dialects
for evidence in ["[\"vendor-log:good\",null]", "[\"vendor-log:good\",1]",
                 "[\"vendor-log:good\",{}]", "[\"vendor-log:good\",\"\"]",
                 "[\"vendor-log:good\",\"  \"]", "null", "{}", "\"vendor-log:good\""] {
    let raw = "{\"verified\":true,\"evidence\":\(evidence)}"
    check("malformed evidence preserves the wire verification flag: \(evidence)",
          JobReceipt.parse(raw)?.verified == true)
    check("a partially malformed array cannot certify a receipt: \(evidence)",
          JobReceipt.parse(raw)?.isProof == false)
    check("a partially malformed array cannot create a proof card: \(evidence)",
          JobReceiptPolicy.doneCard(goal: "Read", result: "Result", receipt: raw).proof == nil)
}
// JSONSerialization bridges NSNumber(1) to Bool; it is not JSON `true`.
for flag in ["1", "1.0", "0", "null", "\"true\"", "\"false\"", "{}", "[]"] {
    let raw = "{\"verified\":\(flag),\"evidence\":[\"vendor-log:run-123\"]}"
    check("verified \(flag) cannot certify a receipt",
          JobReceipt.parse(raw)?.isProof == false)
    check("verified \(flag) cannot give a card a proof block",
          JobReceiptPolicy.doneCard(goal: "Read a test record", result: "A result",
                                    receipt: raw).proof == nil)
}

func receiptJSON(_ entries: [String], verified: Bool = true) -> String {
    let obj: [String: Any] = ["effect_key": "test:read", "verified": verified,
                              "evidence": entries, "summary": "Synthetic result"]
    return String(data: try! JSONSerialization.data(withJSONObject: obj), encoding: .utf8)!
}

// Pin the wire's blank set explicitly; JS trim and Foundation disagree on NEL,
// zero-width space and BOM. Neither side should certify what the other drops.
let wireBlankScalars: [UInt32] = Array(0x9...0xd) + [0x20, 0x85, 0xa0, 0x1680]
    + Array(0x2000...0x200b) + [0x2028, 0x2029, 0x202f, 0x205f, 0x3000, 0xfeff]
for scalar in wireBlankScalars {
    let blank = String(UnicodeScalar(scalar)!)
    check("wire-only blank U+\(String(scalar, radix: 16)) is not evidence",
          JobReceipt.parse(receiptJSON([blank]))?.isProof == false)
    check("mixed blank U+\(String(scalar, radix: 16)) invalidates the whole array",
          JobReceipt.parse(receiptJSON(["vendor-log:good", blank]))?.isProof == false)
}
let paddedReference = "\u{0085}\u{200B}\u{FEFF}vendor-log:good\u{FEFF}\u{0085}"
check("wire padding cannot hide a usable connector reference",
      JobReceipt.parse(receiptJSON([paddedReference]))?.items.first?.kind == .vendorLog)
check("even padded raw evidence remains byte-for-byte available for inspection",
      JobReceiptPolicy.doneCard(goal: "Read", result: "Result", receipt: receiptJSON([paddedReference]))
        .proof?.items.first.map { Data($0.utf8) } == Data(paddedReference.utf8))
let paddedSource = "\u{0085}\u{200B}\u{FEFF}https://www.source.fixture.invalid/page\u{FEFF}\u{0085}"
let paddedSourceCard = JobReceiptPolicy.doneCard(goal: "Research", result: "Answer",
                                               receipt: receiptJSON([paddedSource]))
check("padded bare URLs still produce a cited-source label",
      paddedSourceCard.proof?.notes == ["Cited source: source.fixture.invalid"])
check("a cited-source label never normalizes the stored raw URL",
      paddedSourceCard.proof?.items.first.map { Data($0.utf8) } == Data(paddedSource.utf8))

let connectorEntries = ["vendor-log:log-123", "vendor-run:READ_RECORD@name@example.test"]
let connector = JobReceiptPolicy.doneCard(goal: "Read a test record", result: "Original result",
    receipt: receiptJSON(connectorEntries), effectKey: "test:read")
check("API dialect keeps the engine's original result", connector.lead == "Original result")
check("API dialect explains execution without inventing vendor log readback",
      connector.proof?.checked == "Connector execution recorded")
check("connector references stay opaque, including multiple @ characters",
      connector.proof?.notes == ["Connector execution reference: log-123",
                                "Tool/account reference: READ_RECORD@name@example.test"])
check("API raw evidence is preserved in order", connector.proof?.items == connectorEntries)
check("an API receipt cannot certify a different effect",
      !JobReceiptPolicy.doneCard(goal: "Read", result: "Result", receipt: receiptJSON(connectorEntries),
                                effectKey: "other:effect").hasReceipt)

let digest = String(repeating: "a1", count: 32)
let researchEntries = ["text-sha256:\(digest)", "https://www.example.test/path?q=a:b",
                       "future-format:keep:this", "https://www.example.test/path?q=a:b"]
let research = JobReceiptPolicy.doneCard(goal: "Research", result: "Original answer",
                                        receipt: receiptJSON(researchEntries))
check("research fingerprint does not claim successful delivery",
      research.proof?.checked == "Answer fingerprint recorded")
check("research notes label sources without claiming phone-side readback",
      research.proof?.notes == ["Answer fingerprint (SHA-256): a1a1a1a1a1a1…",
                                "Cited source: example.test", "Cited source: example.test"])
check("unknown and duplicate raw research entries survive unchanged",
      research.proof?.items == researchEntries)
check("browser title keeps precedence", proven.proof?.checked == "Checked on Reservation confirmed | OpenTable")
check("HTTP host is normalized, not the whole private query",
      JobReceiptPolicy.host(of: "HTTPS://WWW.Example.test/a?private=example") == "example.test")
for invalidURL in ["javascript:alert(1)", "file:///tmp/example", "data:text/plain,hi", "not-a-url"] {
    check("non-web source is not given a source label: \(invalidURL)",
          JobReceiptPolicy.host(of: invalidURL) == nil)
}

for entry in ["vendor-log:", "vendor-run:   ", "text-sha256:", "text-sha256:not-a-digest"] {
    let r = JobReceipt.parse(receiptJSON([entry]))!
    check("unusable reference cannot generate a positive heading: \(entry)",
          JobReceiptPolicy.checkedLine(r) == nil)
    check("unusable reference cannot generate an explanatory note: \(entry)",
          JobReceiptPolicy.notes(for: r).isEmpty)
    check("unusable reference remains available for inspection: \(entry)",
          r.items.first?.raw == entry)
}
check("empty deposited-photo reference is not a photograph",
      JobReceipt.parse(receiptJSON(["evidence:   "]))?.photographed == false)

// The runner extracts these methods from the actual SwiftUI view. Only their
// surrounding stored properties are fixtures; the row arithmetic is not a copy.
struct DoneCardFixture { let doneCard: JobReceiptPolicy.Card? }
struct ReceiptRevealFixture { let revealed: Int? }
check("a missing proof has no arrival rows", DoneCardFixture(doneCard: claimOnly).proofRows == 0)
check("browser seal/photo/disclosure has three rows", DoneCardFixture(doneCard: proven).proofRows == 3)
check("API notes participate in the actual card's row count", DoneCardFixture(doneCard: connector).proofRows == 4)
check("API notes start after the seal", connector.proof?.notesStartIndex == 1)
check("API disclosure follows both notes", connector.proof?.disclosureRowIndex == 3)
check("research sources count, including repeated references", DoneCardFixture(doneCard: research).proofRows == 5)
let many = JobReceiptPolicy.doneCard(goal: "Research", result: "Answer",
    receipt: receiptJSON(["evidence:photo"] + (0..<24).map { "vendor-log:log-\($0)" }))
check("large receipts retain every visible row", DoneCardFixture(doneCard: many).proofRows == 27)
check("photo shifts note indices once", many.proof?.notesStartIndex == 2)
let manyPlan = DoneCeremonyPolicy.plan(revealSteps: DoneCardFixture(doneCard: many).proofRows)
check("many notes do not extend the ceremony budget", manyPlan.total <= DoneCeremonyPolicy.maximumDelay)
check("the ceremony's hard cap is preserved", manyPlan.revealSteps == DoneCeremonyPolicy.evidenceHardCap)
for index in 0..<27 {
    check("final reveal shows large receipt row \(index)", ReceiptRevealFixture(revealed: nil).landed(index))
    check("in-progress reveal counts row \(index) once",
          ReceiptRevealFixture(revealed: index + 1).landed(index)
            && !ReceiptRevealFixture(revealed: index).landed(index))
}

print(failures == 0 ? "all receipt checks passed" : "\(failures) FAILED")
exit(failures == 0 ? 0 : 1)
