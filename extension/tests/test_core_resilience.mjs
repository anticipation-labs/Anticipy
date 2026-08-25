import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  completionContradiction,
  completionEvidenceGap,
  completionRecoveryReversal,
  completionShapeGap,
  externalControlSemantics,
  evidenceStateUrlKey,
  extractVerifierVerdict,
  goalMatchingElements,
  loopbackTarget,
  missingCompletionEvidence,
  nonAuthoritativeCompletionEvidence,
  normalizedResult,
  officialRecordEvidenceGap,
  outputOnlyCompletionGap,
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
assert.equal(completionContradiction("SFU returned 0 results. I will now try BCIT."), true);
assert.equal(completionShapeGap("Find three active listings.", JSON.stringify([{ id: 1 }])),
  "the goal requests 3 records but the result contains 1");
assert.equal(completionShapeGap("Find three active listings.", JSON.stringify([{ id: 1 }, { id: 2 }, { id: 3 }])), "");
assert.equal(completionShapeGap("Find three active listings.", "OPTION 1: A\nOPTION 2: B\nOPTION 3: C"), "");
assert.equal(completionShapeGap("Find three active listings.", "Option 1: A. Option 2: B. Option 3: C."), "");
assert.match(completionShapeGap(
  "Compare plans for Alpha, Beta, and Gamma. Provide direct URLs.",
  "Alpha https://alpha.test Beta https://beta.test Gamma"), /3 direct URLs.*2/);
assert.equal(outputOnlyCompletionGap("the goal requests 3 records but the result contains 1"), true);
assert.equal(outputOnlyCompletionGap("The claimed result fails to provide the requested direct URLs"), true);
assert.equal(outputOnlyCompletionGap("the live page does not support the claimed price"), false);
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
assert.equal(missingCompletionEvidence("the requested price does not appear in the evidence"), true);
assert.equal(missingCompletionEvidence("all requested values are present"), false);
assert.equal(nonAuthoritativeCompletionEvidence(
  "the claim came from a search result snippet rather than the vendor's official page"), true);
assert.equal(nonAuthoritativeCompletionEvidence("the official vendor page supports the claim"), false);
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
assert.match(completionShapeGap(
  "[AUDIT:opaque-metadata] Compare paid plans on the official pages for Alpha, Beta Business, and Gamma Workplace.",
  { Alpha: { price: 1 } }), /Beta Business, Gamma Workplace/);
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
assert.equal(officialRecordEvidenceGap(
  "Compare several plans and summarize them.", officialPricingResult,
  { url: "https://search.test", text: "$14.16 USD" }, []), "");
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

const ranked = goalMatchingElements(
  "Choose a cordless drill kit with battery and charger under CAD 300.",
  [
    "[1] <link> Burnaby store location @(20,20)",
    "[2] <link> Cordless drill/driver kit with battery and charger @(20,40)",
    "[3] <button> Account settings @(20,60)",
  ].join("\n"));
assert.match(ranked, /^\[2\]/);
assert.doesNotMatch(ranked, /Burnaby store location/);
console.log("PASS 3: goal-relevant live elements outrank unrelated page chrome generically");

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
assert.match(loopSource, /coverage > bestCompletionCoverage/);
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
