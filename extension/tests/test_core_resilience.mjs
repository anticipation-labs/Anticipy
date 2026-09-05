import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  completionEvidenceGap,
  completionRecoveryReversal,
  externalControlSemantics,
  evidenceStateUrlKey,
  extractVerifierVerdict,
  loopbackTarget,
  internalNetworkTarget,
  taskAllowsInternalNetwork,
  COMPLETION_GAPS,
  completionGap,
  normalizedResult,
  officialRecordEvidenceGap,
  prioritizeClaimedEvidence,
  protectedInput,
  repeatedResearchHref,
  repeatedResearchLanding,
  rememberEvidenceEntry,
  replacementShapeCompatible,
  researchUrlKey,
  unapprovedCalendarClick,
} from "../agent_loop.js";

assert.equal(normalizedResult({ named: { fee: "$350" }, numbered: { fee: "$350" } }),
  '{"named":{"fee":"$350"},"numbered":{"fee":"$350"}}');
assert.equal(normalizedResult("  finished  "), "finished");
// AUDIT #74 (2026-09-05): how many records the goal asks for, and how many the
// result delivers, is the auditor's question and is no longer read here. Until
// then the first of these returned "the goal requests 3 records but the result
// contains 1", and prose passed only when it happened to be numbered. The
// behavioural pins — the auditor is asked, in both directions, and the run
// finishes — are test_record_count_is_not_a_regex_match.mjs.
// F06 (2026-09-05): the last two branches went the same way as the count, and
// the function with them. `comparisonNames` read "Compare … for A, B and C"
// off the owner's first sentence and refused a claim that named the carrier as
// its source does ("Bell" for "Bell Canada"); the direct-URL branch refused
// three correct prices sourced from one comparison page. Both returned false
// from verifyDone before mapPage and before the auditor. Nothing may take
// their place: what stands between a done claim and the auditor now reads the
// RESULT's own shape and the pages this run opened, never the goal's wording.
// The behavioural pins are test_completion_shape_is_a_model_verdict.mjs.
const loopExports = await import("../agent_loop.js");
const loopFile = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "agent_loop.js"), "utf8");
assert.ok(!("completionShapeGap" in loopExports),
  "completionShapeGap is deleted, not re-exported");
assert.ok(!/function comparisonNames|completionShapeGap\(/.test(
  loopFile.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "")),
  "neither the comparison-name parse nor its caller survives in the code");
// F24 (2026-09-05): which recovery a rejected done claim gets is chosen from a
// token the verifier returns, not from regexes over its prose. These asserted
// the three deleted predicates; they now assert the token reader, whose whole
// job is to refuse anything outside the closed set — the floor that keeps a
// mis-typed or invented category from pressing Escape on the owner's page.
assert.equal(completionGap("result_omits"), "result_omits");
assert.equal(completionGap("still_loading"), "still_loading");
assert.equal(completionGap("missing_on_page"), "missing_on_page");
assert.equal(completionGap("source_unvisited"), "source_unvisited");
assert.equal(completionGap("non_authoritative"), "non_authoritative");
assert.equal(completionGap("contradiction"), "contradiction");
assert.equal(completionGap("the goal requests 3 records but the result contains 1"), "");
assert.equal(completionGap("MISSING_ON_PAGE"), "", "the token is exact, not case-folded");
assert.equal(completionGap("missing_on_page and still_loading"), "");
assert.equal(completionGap(undefined), "");
assert.equal(completionGap(null), "");
assert.equal(completionGap(""), "");
assert.equal(COMPLETION_GAPS.size, 6);
assert.equal(completionRecoveryReversal(
  { action: "scroll", dy: -900 }, "https://vendor.test/pricing", 1, "price missing"), true);
assert.equal(completionRecoveryReversal(
  { action: "navigate", url: "https://vendor.test/pricing" },
  "https://vendor.test/pricing", 2, "price missing"), true);
assert.equal(completionRecoveryReversal(
  { action: "navigate", url: "https://search.test/?q=official+price" },
  "https://vendor.test/pricing", 2, "price missing"), false);
assert.equal(completionRecoveryReversal(
  { action: "scroll", dy: -900 }, "https://vendor.test/pricing", 0, "price missing"), false);
// The two prose predicates these lines pinned are gone with F24; the same two
// findings are `missing_on_page` and `non_authoritative`, and the sentence a
// verifier happens to write about either decides nothing at all now.
assert.equal(completionGap("missing_on_page"), "missing_on_page");
assert.equal(completionGap("the requested price does not appear in the evidence"), "");
assert.equal(completionGap("the claim came from a search result snippet"), "");
assert.equal(repeatedResearchHref(
  "https://vendor.test/pricing", new Set(["https://vendor.test/pricing"]), 1,
  "price missing"), true);
assert.equal(repeatedResearchHref(
  "https://vendor.test/products/pro", new Set(["https://vendor.test/pricing"]), 1,
  "price missing"), false);
assert.equal(repeatedResearchHref(
  "https://vendor.test/pricing", new Set(["https://vendor.test/pricing"]), 0,
  "price missing"), false);
assert.equal(repeatedResearchHref(
  "https://search.test/search?q=second", new Set(["https://search.test/search?q=first"]),
  1, "price missing"), false);
assert.equal(repeatedResearchHref(
  "https://search.test/search?q=first", new Set(["https://search.test/search?q=first"]),
  1, "price missing"), true);
assert.notEqual(researchUrlKey("https://search.test/search?q=first"),
  researchUrlKey("https://search.test/search?q=second"));
const scrollEvidence = [];
rememberEvidenceEntry(scrollEvidence,
  { url: "https://vendor.test/pricing", text: "Business Pro", elements: "" });
rememberEvidenceEntry(scrollEvidence,
  { url: "https://vendor.test/pricing", text: "$14.16 USD", elements: "" });
assert.equal(scrollEvidence.length, 2,
  "distinct scroll states at one research URL retain complementary evidence");
rememberEvidenceEntry(scrollEvidence,
  { url: "https://vendor.test/pricing", text: "$14.16 USD", elements: "" });
assert.equal(scrollEvidence.length, 2,
  "an unchanged same-URL state is deduplicated");
rememberEvidenceEntry(scrollEvidence,
  { url: "https://vendor.test/pricing", text: "Annual commitment", elements: "" });
rememberEvidenceEntry(scrollEvidence,
  { url: "https://vendor.test/pricing", text: "Collaboration features", elements: "" });
assert.deepEqual(scrollEvidence.map((entry) => entry.text),
  ["$14.16 USD", "Annual commitment", "Collaboration features"],
  "same-page evidence remains bounded to the newest three distinct views");
assert.equal(repeatedResearchLanding({
  sourceUrl: "https://search.test/?q=price",
  visitedKeys: new Set(["vendor.test/pricing"]),
}, "https://vendor.test/pricing"), true);
assert.equal(repeatedResearchLanding({
  sourceUrl: "https://search.test/?q=price",
  visitedKeys: new Set(["vendor.test/pricing"]),
}, "https://vendor.test/products/pro"), false);
assert.equal(replacementShapeCompatible('"price":"19.16","currency":"CAD"',
  "Education Healthcare Frontline Developer"), false);
assert.equal(replacementShapeCompatible('"price":"19.16","currency":"CAD"',
  "$15.99 monthly"), false);
assert.equal(replacementShapeCompatible('"price":"19.16","currency":"CAD"',
  "$15.99 monthly USD"), true);
assert.deepEqual(extractVerifierVerdict(
  'I checked {this prose is not JSON}. Final: {"verified":false,"reason":"missing exact hour"}'),
  { verified: false, reason: "missing exact hour" });
assert.deepEqual(extractVerifierVerdict(
  '```json\n{"verified":true}\n```'), { verified: true });
assert.equal(evidenceStateUrlKey("https://www.example.test/search?b=2&utm_source=x&a=1#selected"),
  "example.test/search?a=1&b=2#selected");
assert.notEqual(evidenceStateUrlKey("https://example.test/search?trip=outbound"),
  evidenceStateUrlKey("https://example.test/search?trip=return"));
// This used to assert that an [AUDIT:…] transport prefix could not make a
// "Compare … for A, B and C" goal slip past the named-entity gate. F06 deleted
// that gate, and the property survives in a stronger form: the two checks that
// still run in front of the auditor do not read the goal AT ALL, so no prefix,
// phrasing or metadata on it can change what they say.
{
  const opened2 = { url: "https://example.test/plans", title: "plans", text: "", elements: "" };
  const claim = { Alpha: { price: 1, url: "https://example.test/alpha" } };
  const plain = completionEvidenceGap(
    "Compare paid plans for Alpha, Beta Business, and Gamma Workplace.", claim, opened2, []);
  const prefixed = completionEvidenceGap(
    "[AUDIT:opaque-metadata] Compare paid plans for Alpha, Beta Business, and Gamma Workplace.",
    claim, opened2, []);
  assert.equal(plain, prefixed, "provenance is blind to how the goal is worded or prefixed");
  assert.match(plain, /example\.test\/alpha/, "and it still refuses a cited page nobody opened");
}
const opened = {
  url: "https://example.test/listing/one", title: "one", text: "", elements: "",
};
const openedJournal = [{ url: "https://example.test/listing/two" }];
assert.match(completionEvidenceGap(
  "Find three records. Open each actual listing and report the direct URL.",
  [
    { url: "https://example.test/listing/one" },
    { url: "https://example.test/listing/two" },
    { url: "https://example.test/listing/three" },
  ], opened, openedJournal), /listing\/three/);
assert.equal(completionEvidenceGap(
  "Find two records. Open each actual listing and report the direct URL.",
  [
    { url: "https://example.test/listing/one?tracking=1" },
    { url: "https://example.test/listing/two" },
  ], opened, openedJournal), "");
const officialPricingResult = [{
  vendor: "ExampleCo", plan_name: "Business Pro", displayed_price: "14.16",
  currency: "USD", url: "https://example.test/pricing/pro",
}];
assert.equal(officialRecordEvidenceGap(
  "Compare the current plans on each vendor's official pricing page.",
  officialPricingResult,
  { url: "https://example.test/pricing/pro", title: "Business Pro", text: "Business Pro — $14.16 USD per user", elements: "" },
  []), "");
assert.equal(officialRecordEvidenceGap(
  "Compare the current plans on each vendor's official pricing page.",
  officialPricingResult,
  { url: "https://example.test/pricing/pro", title: "Price", text: "$14.16 USD per user", elements: "" },
  [{ url: "https://example.test/pricing/pro", title: "Plan", text: "Business Pro", elements: "" }]), "",
  "complementary live scroll states on the same official document form one proof");
assert.equal(officialRecordEvidenceGap(
  "Compare the current plans on each vendor's official pricing page.",
  [{ ...officialPricingResult[0], displayed_price: "8.75" }],
  { url: "https://example.test/pricing/pro", title: "Business Pro", text: "Business Pro $8.75$4.38 USD per user", elements: "" }, []), "",
  "a leading currency symbol remains a complete money token beside another promotional price");
assert.match(officialRecordEvidenceGap(
  "Compare the current plans on each vendor's official pricing page.",
  officialPricingResult,
  { url: "https://search.test/?q=example", title: "Search", text: "ExampleCo Business Pro $14.16 USD", elements: "" },
  [{ url: "https://example.test/pricing/pro", title: "Business Pro", text: "Contact sales", elements: "" }]),
  /does not contain claimed displayed_price "14\.16"/);
assert.match(officialRecordEvidenceGap(
  "Compare the current plans on each vendor's official pricing page.",
  [{ ...officialPricingResult[0], displayed_price: "141" }],
  { url: "https://example.test/pricing/pro", title: "Business Pro", text: "Business Pro $1416/month/user USD", elements: "" }, []),
  /does not contain claimed displayed_price "141"/,
  "a substring of a larger money token cannot prove a claimed price");
// F06 (2026-09-05): this used to assert the OPPOSITE — that a goal without the
// word "official" was not checked at all. One word of the owner's sentence
// decided whether a claimed price was checked against the page it cites, and
// "from the vendor itself" or "the airline's own site" switched nothing on.
// The check no longer reads the goal; it reads the RESULT's own shape, so the
// same fabricated citation is refused however the errand was phrased. This is
// a stronger pin than the one it replaces, not a softer one.
assert.match(officialRecordEvidenceGap(
  "Compare several plans and summarize them.", officialPricingResult,
  { url: "https://search.test", text: "$14.16 USD" }, []),
  /was not observed as a live page: https:\/\/example\.test\/pricing\/pro/,
  "a record citing a page this run never opened is refused whatever the goal says");
assert.equal(officialRecordEvidenceGap(
  "Compare several plans and summarize them.", officialPricingResult,
  { url: "https://example.test/pricing/pro", title: "Business Pro",
    text: "Business Pro — $14.16 USD per user", elements: "" }, []), "",
  "...and the same record cited off the page the run DID open still passes");
assert.equal(officialRecordEvidenceGap(
  "Compare several plans and summarize them.",
  "Business Pro is $14.16 USD per user on https://example.test/pricing/pro",
  { url: "https://search.test", text: "$14.16 USD" }, []), "",
  "prose is not a record: this check only ever reads a structured url+price pair");
const evidenceOrder = [
  { url: "https://example.test/listing/one" },
  { url: "https://example.test/search" },
  { url: "https://example.test/listing/two" },
];
prioritizeClaimedEvidence(evidenceOrder, [
  { url: "https://example.test/listing/one" },
  { url: "https://example.test/listing/two" },
]);
assert.deepEqual(evidenceOrder.map((item) => item.url), [
  "https://example.test/search",
  "https://example.test/listing/one",
  "https://example.test/listing/two",
]);
console.log("PASS 1: structured completion results retain their facts");

assert.equal(externalControlSemantics({ label: "Accept all cookies", cookieLike: true }), false);
assert.equal(externalControlSemantics({ label: "Confirm choices", cookieLike: true }), false);
assert.equal(externalControlSemantics({ label: "17", explicitSubmit: true, calendarLike: true }), false);
assert.equal(externalControlSemantics({ label: "Search", explicitSubmit: true, searchLike: true }), false);
assert.equal(externalControlSemantics({ label: "See 0 results", explicitSubmit: true }), false);
assert.equal(externalControlSemantics({ label: "See 3,631 results", explicitSubmit: true }), false);
assert.equal(externalControlSemantics({ label: "Business Registry & Name Request", choiceLike: true }), false);
assert.equal(externalControlSemantics({ label: "Name request", disclosureLike: true }), false);
assert.equal(externalControlSemantics({ label: "File forms", disclosureLike: true }), false);
assert.equal(externalControlSemantics({ label: "Request", explicitSubmit: true }), true);
assert.equal(externalControlSemantics({ label: "Apply filters", explicitSubmit: true }), false);
assert.equal(externalControlSemantics({ label: "Stops" }), false);
assert.equal(externalControlSemantics({ label: "Place order" }), true);
assert.equal(externalControlSemantics({ label: "Submit", explicitSubmit: true }), true);
assert.equal(protectedInput(null), null);
assert.equal(loopbackTarget("http://127.0.0.1:18092/_/#/login"), true);
assert.equal(loopbackTarget("http://localhost:8090/_/"), true);
assert.equal(loopbackTarget("https://zoom.us/pricing"), false);
console.log("PASS 2: reversible controls are distinct from external effects");

// THE WHOLE INTERNAL NETWORK, not just this machine — Omi teardown item #04.
// Every row here returned FALSE from loopbackTarget on 2026-09-05, measured
// against WHATWG, and would have let a page steer the agent onto the owner's
// router, NAS, or a cloud metadata service. The IPv4-mapped rows are the ones
// Omi's own guard misses; WHATWG serialises them as hex, so a guard that
// looks for dotted digits inside the brackets sees nothing.
for (const [u, want] of [
  ["http://[::ffff:127.0.0.1]/", true],        // mapped loopback  -> [::ffff:7f00:1]
  ["http://[::ffff:169.254.169.254]/", true],  // mapped metadata  -> [::ffff:a9fe:a9fe]
  ["http://[::ffff:192.168.1.1]/", true],      // mapped RFC 1918
  ["http://[::ffff:8.8.8.8]/", false],         // mapped PUBLIC stays public
  ["http://0.0.0.0/", true], ["http://0.1.2.3/", true],   // 0.0.0.0/8, not just the one address
  ["http://169.254.169.254/", true],           // the credential-handing metadata service
  ["http://10.0.0.1/", true], ["http://172.16.0.1/", true], ["http://192.168.1.1/", true],
  ["http://172.32.0.1/", false],               // one past 172.16/12 — the boundary, not the block
  ["http://100.64.0.1/", true], ["http://100.128.0.1/", false], // CGNAT /10 and one past it
  ["http://198.18.0.1/", true], ["http://224.0.0.1/", true], ["http://255.255.255.255/", true],
  ["http://[fe80::1]/", true], ["http://[fc00::1]/", true], ["http://[fd12::1]/", true],
  ["http://[ff02::1]/", true], ["http://[::]/", true], ["http://[::1]/", true],
  ["https://[2606:4700::1111]/", false],       // a real public v6 stays public
  ["https://8.8.8.8/", false], ["https://zoom.us/pricing", false],
  ["http://localhost/", true],                 // composes loopbackTarget; one definition
  ["not a url", false], ["", false],
]) {
  assert.equal(internalNetworkTarget(u), want, `internalNetworkTarget(${JSON.stringify(u)})`);
}
console.log("PASS 2b: every internal-network address form is refused, every public one is not");

// The owner naming the address in his OWN words is authorisation; a model
// writing it is not, and the caller only ever passes owner text here. A
// public literal authorises nothing, so "go to 8.8.8.8" cannot be laundered
// into permission for 192.168.1.1.
assert.equal(taskAllowsInternalNetwork("check the router at 192.168.1.1", "", ""), true);
assert.equal(taskAllowsInternalNetwork("", "open the NAS on 10.0.0.5 and download the backup", ""), true);
assert.equal(taskAllowsInternalNetwork("", "", "http://[fe80::1]/admin"), true);
assert.equal(taskAllowsInternalNetwork("look up 8.8.8.8 on a DNS site", "", ""), false);
assert.equal(taskAllowsInternalNetwork("book a table for four", "at 7pm", "https://opentable.com"), false);
assert.equal(taskAllowsInternalNetwork("try localhost:3000", "", ""), true); // still composes the loopback allowance
console.log("PASS 2c: only an owner-named internal address opens the internal network, and only that one class");


const state = {
  overlay: true,
  elements: [
    "[8] <button> Monday, August 17 [calendar=August 17] @(10,10)",
    "[9] <button> Thursday, September 17 [calendar=September 17] @(20,10)",
    "[10] <button> Next month @(30,10)",
  ].join("\n"),
};
// AUDIT #69, fixed 2026-08-24: the day is resolved from our own page map and
// the clock (structural), and WHICH day he asked for is read by a model. The
// old arithmetic could not reach "the Tuesday after next" and blocked the cell
// he meant. test_calendar_date.mjs owns that boundary; what is pinned here is
// that the structural half still finds the cell and that non-date controls are
// left alone.
const authority = "Depart September 17, 2026 and return September 21, 2026.";
const onlySept17 = async ({ named }) => (named === "September 17" ? "YES" : "NO");
assert.match((await unapprovedCalendarClick({ action: "click", index: 8 }, state, authority, onlySept17)).reason,
  /August 17/);
assert.equal((await unapprovedCalendarClick({ action: "click", index: 9 }, state, authority, onlySept17)).blocked, false);
assert.equal((await unapprovedCalendarClick({ action: "click", index: 10 }, state, authority, onlySept17)).blocked, false,
  "a month-navigation control carries no date and is never judged");
// FAIL CLOSED, WITHOUT DELETING THE CELL. A guard that cannot tell one day
// from another must not remove them one at a time.
const cannotTell = await unapprovedCalendarClick({ action: "click", index: 9 }, state, authority);
assert.equal(cannotTell.blocked, true, "no model, no click");
assert.equal(cannotTell.undecidable, true, "and the caller is told not to delete the cell");
console.log("PASS 4: picker clicks cannot silently change an explicit date");

const here = dirname(fileURLToPath(import.meta.url));
const mapSource = readFileSync(join(here, "..", "page_map.js"), "utf8");
const overlaySource = mapSource.slice(
  mapSource.indexOf("function activeOverlay"), mapSource.indexOf("function calendarDateOf"));
globalThis.window = {};
eval(mapSource);
assert.equal(globalThis.window.__anticipyJoinTypographicMoney("Zoom Pro $14", "16"), "$14.16");
assert.equal(globalThis.window.__anticipyJoinTypographicMoney("Video 1 minute", "41"), "");
delete globalThis.window;
assert.match(mapSource, /url\.host\}\$\{url\.pathname/,
  "link identity exposes no query strings or fragments");
assert.match(mapSource, /calendar=\$\{calendarDate\}/,
  "calendar day map includes inferred month/day context");
assert.match(mapSource, /smallest enclosing dialog/,
  "calendar mapper keeps surrounding month navigation controls");
assert.doesNotMatch(overlaySource, /\[role=application\].*querySelectorAll/,
  "an ordinary video/application cannot hide the surrounding page as an overlay");
assert.doesNotMatch(overlaySource, /\[role=listbox\]/,
  "a permanent navigation listbox cannot hide the surrounding page as an overlay");
assert.match(mapSource, /TYPOGRAPHIC VALUES/,
  "raised cents are exposed as the decimal money value a person sees");
const loopSource = readFileSync(join(here, "..", "agent_loop.js"), "utf8");
const backgroundSource = readFileSync(join(here, "..", "background.js"), "utf8");
// The marker must always MATCH the manifest, not equal a number this test
// hardcodes — a hardcoded pin turned every release into a false red.
const manifestVersion = JSON.parse(
  readFileSync(join(here, "..", "manifest.json"), "utf8")).version;
assert.match(backgroundSource,
  new RegExp(`ENGINE_BUILD = "${manifestVersion.replace(/\./g, "\\.")}"`),
  "ENGINE_BUILD must equal the manifest version so traces identify the build");
assert.match(backgroundSource, /attempt .*\| engine \$\{ENGINE_BUILD\}/,
  "every live trace identifies the exact service-worker engine build");
assert.match(loopSource, /same completion failed verification three times/);
assert.match(loopSource, /a repeated state\/action cycle/);
assert.match(loopSource, /FALLBACK after/);
console.log("PASS 5: completion, cycle, and fallback bounds are wired into the loop");

assert.match(loopSource,
  /max_tokens:\s*4096,[\s\S]{0,180}response_format:\s*\{\s*type:\s*"json_object"\s*\}/,
  "the next-action call leaves enough output room for a multi-record done result");
console.log("PASS 6: final structured results are not capped at one short action");

assert.match(loopSource, /source\.placeholder/,
  "generic search detection includes placeholder semantics");
assert.match(loopSource, /role="search"/,
  "generic search detection includes ARIA search containers");
console.log("PASS 7: read-only search forms stay reversible without site recipes");

assert.match(loopSource, /interpreted select on <\$\{String\(targetKind\.tag\)\.toLowerCase\(\)\}> as a reversible click/,
  "select vocabulary slips on generic tabs/buttons become reversible clicks");
console.log("PASS 8: generic non-native select recovery is wired into the loop");

assert.match(loopSource, /explicitly answer EVERY requested entity, field and quantity/,
  "completion verifier checks all requested research outputs");
assert.match(loopSource, /count them and verify=false/,
  "completion verifier enforces named-item and cardinality completeness");
console.log("PASS 9: partial multi-record research cannot be reported as complete");

assert.match(loopSource, /EARLIER LIVE PAGE EVIDENCE FROM THIS SAME RUN/);
assert.match(loopSource, /repeated completion claims failed verification/);
assert.match(loopSource, /source tab was replaced; adopted its only Anticipy child tab/);
assert.match(loopSource, /page stayed unreadable; reloaded it once and will remap/);
assert.match(loopSource, /filterApply/);
assert.match(loopSource, /source\.getAttribute\("data-toggle"\) === "collapse"/);
assert.match(loopSource, /confirm\\s\+choices\?/);
assert.match(loopSource, /words in a guessed URL are not proof/);
assert.match(loopSource, /response_format:\s*\{\s*type:\s*"json_object"\s*\}/);
assert.doesNotMatch(loopSource, /doneRejections\.clear\(\);\s*totalDoneRejections = 0/);
assert.match(loopSource, /RESEARCH after rejected completion/);
// The names survive in the WHAT-WAS-HERE record; what must stay gone is the code.
assert.doesNotMatch(loopSource, /let bestCompletionCoverage|completionCoverageScore\(/,
  "audit #74: the coverage score was written on every done claim and read nowhere; dead state stays gone");
assert.match(loopSource, /DOM scrolled \$\{scrolled\.target\}/);
assert.doesNotMatch(loopSource, /type: "mouseWheel", x: 400, y: 300/);
assert.match(loopSource, /targetKind\?\.tag/);
assert.match(mapSource, /el\.shadowRoot\.querySelector/);
assert.match(loopSource, /BLOCKED DUPLICATE EFFECT/);
assert.match(loopSource, /initialEvidenceJournal/);
assert.match(loopSource, /goal_quote/);
assert.match(loopSource, /stateForControl/);
assert.match(loopSource, /BLOCKED NO-ACTION DONE/);
assert.match(loopSource, /OPENING MISSING EVIDENCE/);
assert.match(mapSource, /slice\(0, 6000\)/);
assert.match(mapSource, /Number\(raw\) >= 0/,
  "negative-tabindex structural containers are not exposed as controls");
assert.match(mapSource, /VISIBLE VIEWPORT/,
  "page text follows the browser viewport instead of remaining pinned to the document header");
assert.match(mapSource, /r\.bottom <= 0 \|\| r\.top >= vh/,
  "viewport evidence is selected by generic DOM geometry");
assert.match(loopSource, /automation session could not be restored after three attempts/);
assert.match(loopSource, /prioritizeClaimedEvidence\(evidenceJournal, claimedResult\)/);
assert.match(loopSource, /evidenceStateUrlKey\(old\?\.url/);
assert.match(loopSource, /pageContentFingerprint\(old\) === content/);
assert.match(loopSource, /setTimeout\(\(\) => ctl\.abort\(\), 80000\)/);
assert.match(loopSource, /parkPointerAfterNavigation/);
assert.match(loopSource, /BLOCKED UNEXPECTED LOCAL TARGET/);
assert.match(loopSource, /tabsBeforeClick\.has\(t\.id\)/);
assert.match(loopSource, /dismissed an unrelated overlay after the verifier found missing evidence/);
assert.match(loopSource, /other installed extensions[\s\S]{0,300}main frame/,
  "a foreign extension iframe cannot abort mapping the actual page");
assert.match(loopSource, /Cannot access a chrome-extension:\\\/\\\/ URL of different extension/);
assert.doesNotMatch(loopSource, /bestCompletionCoverage\) \{[\s\S]{0,120}totalDoneRejections = 0/,
  "better prose never erases the monotonic rejected-completion budget");
console.log("PASS 10: evidence durability, grounded verification, scoped forms, and at-most-once effects are wired in");

assert.match(loopSource, /BLOCKED NO-ACTION DONE/,
  "a rejected completion cannot be rephrased and resubmitted without new browser evidence");
assert.match(loopSource, /VERBATIM OUTPUT CORRECTION/,
  "a grounded verifier contradiction is fed back as an exact output repair");
assert.match(loopSource, /\|\| !!lastDoneCorrection/,
  "a corrected answer may reuse sufficient live evidence without a fake browser action");
assert.match(loopSource, /SCROLLING FOR REJECTED EVIDENCE/,
  "missing evidence below the fold is searched before abandoning the live page");
assert.match(loopSource, /official price per user billed monthly annual/,
  "completion research uses a short named-entity query instead of pasting the whole task");
assert.match(loopSource, /Chrome \$\{method\}/,
  "every low-level Chrome action is bounded by a timeout");
assert.match(loopSource, /browser-action API stopped responding/,
  "a stalled Chrome action ends one run instead of wedging the worker queue");
assert.match(loopSource, /stopped after three completion claims against unchanged evidence/,
  "an exhausted completion-evidence path terminates instead of consuming the global step budget");
console.log("PASS 11: unchanged-evidence completion spam and hung Chrome actions are bounded");

console.log("test_core_resilience: all 11 scenarios passed");
