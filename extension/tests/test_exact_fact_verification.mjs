// Completion is not "a green banner appeared". The exact approved facts
// must be visible on the receipt/current page or in the final pre-effect form
// snapshot, and an unselected option is never evidence.

import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";

const here = dirname(fileURLToPath(import.meta.url));
globalThis.chrome = globalThis.chrome || {
  tabs: { query: async () => [], create: async () => ({ id: 1 }), remove: async () => {} },
  storage: { local: { get: async () => ({}), set: async () => {} } },
  runtime: {}, debugger: {}, tabGroups: {}, notifications: {}, alarms: {},
};

const { completionContradiction, groundedFormCorrections,
        normalizedAuthorityText, schemaBoundaryCorrections,
        terminalReceiptEvidence, unsupportedApprovedFacts,
        unsupportedScopeFields } =
  await import(join(here, "..", "agent_loop.js"));
const source = readFileSync(join(here, "..", "agent_loop.js"), "utf8");

let failed = 0;
const check = (condition, label) => {
  if (condition) console.log(`PASS: ${label}`);
  else { failed += 1; console.error(`FAIL: ${label}`); }
};

const invoiceFacts = { invoice: "INV-8842", request: "Corrected invoice" };
const wrongReceipt = { text: "Submitted successfully. invoice: INV-8842 · request: Explanation", elements: "" };
const wrongForm = {
  elements: '[4] <combobox> Resolution (options: "Explanation"*, "Corrected invoice")',
  fields: [{ name: "invoice", label: "Invoice number", value: "INV-8842" },
           { name: "request", label: "Resolution requested", value: "Explanation" }],
};
check(unsupportedApprovedFacts(invoiceFacts, wrongReceipt, wrongForm).includes("request"),
  "a success page cannot hide a wrong default option");

const rightReceipt = { text: "Submitted successfully. invoice: INV-8842 · request: Corrected invoice", elements: "" };
check(unsupportedApprovedFacts(invoiceFacts, rightReceipt, null).length === 0,
  "the exact receipt supports the approved facts");

const terseReceipt = { text: "Submitted successfully. Confirmation #A42", elements: "" };
const rightForm = {
  elements: '[4] <combobox> Resolution (options: "Explanation", "Corrected invoice"*)\n[2] <textbox> Invoice [contains "INV-8842"]',
  fields: [{ name: "invoice", label: "Invoice number", value: "INV-8842" },
           { name: "request", label: "Resolution requested", value: "Corrected invoice" }],
};
check(unsupportedApprovedFacts(invoiceFacts, terseReceipt, rightForm).length === 0,
  "the exact pre-effect form plus a terminal receipt is evidence");

check(unsupportedApprovedFacts({ education: true },
  { text: "Submitted successfully. education: true", elements: "" }, null).length === 0,
  "boolean facts are bound to their field name");
check(unsupportedApprovedFacts({ education: true },
  { text: "Submitted successfully. consent: true", elements: "" }, null).includes("education"),
  "an unrelated true value cannot satisfy a boolean fact");
const longValue = "A privacy-first assistant that helps people complete everyday digital paperwork.";
check(unsupportedApprovedFacts({ summary: longValue }, terseReceipt,
  { fields: [{ name: "summary", label: "Project summary", value: longValue }],
    elements: '[2] <textbox> Project summary [contains "A privacy-first assistant that helps pe"]' }).length === 0,
  "structured form state preserves long approved values beyond the model map truncation");
const hostileDefaults = { fields: [
  { name: "account", label: "Account number", value: "NG-96999" },
  { name: "charged", label: "Amount charged", value: "OLD-2" },
  { name: "usual", label: "Usual amount", value: "OLD-3" },
  { name: "resolution", label: "Requested resolution", value: "OLD-4" },
] };
const disputeScope = "Dispute account NG-96999: charged $353.32, usual $79.95; request a corrected bill";
check(JSON.stringify(unsupportedScopeFields(disputeScope, hostileDefaults)) ===
      JSON.stringify(["charged", "usual", "resolution"]),
  "visible hostile defaults are outside the approved words");
check(unsupportedScopeFields(disputeScope, { fields: [
  { name: "account", value: "NG-96999" }, { name: "charged", value: "353.32" },
  { name: "usual", value: "79.95" }, { name: "resolution", value: "Corrected bill" },
] }).length === 0, "exact submitted values are supported without oracle facts");
check(unsupportedScopeFields("Open a mail-in warranty repair", { fields: [
  { name: "service", label: "Service", value: "Mail-in repair" },
] }).length === 0, "short categorical values may remove redundant page context");
check(unsupportedScopeFields(
  "Cancel at the end of the current billing period", { fields: [
    { name: "effective", label: "When", value: "End of current billing period" },
  ] }).length === 0,
  "text-rendered choices may omit surrounding determiners without leaving scope");
check(unsupportedScopeFields("sink leaking under the cabinet", { fields: [
  { name: "issue", label: "Issue", value: "sink leaking under cabinet" },
] }).includes("issue"), "long descriptions may not silently lose the owner's words");
const aligned = groundedFormCorrections({ corrections: [
  { index: 1, value: "Anticipy" },
  { index: 2, value: "At renewal" },
  { index: 3, value: "invented enterprise plan" },
] }, [
  { index: 1, name: "workspace", value: "NorthGrid" },
  { index: 2, name: "effective", value: "renewal" },
  { index: 3, name: "plan", value: "Pro" },
], "Reduce the Anticipy workspace on NorthGrid at renewal and keep the Pro plan");
check(aligned.length === 2 && aligned[0].value === "Anticipy"
      && aligned[1].value === "At renewal",
  "the semantic auditor may reshape owner words but cannot invent a value");
const reconstructed = groundedFormCorrections({ values: [
  { index: 1, value: "Arrived damaged" },
  { index: 2, value: "Mail-in repair" },
] }, [
  { index: 1, name: "problem", value: "it arrived damaged" },
  { index: 2, name: "service", value: "mail-in warranty repair" },
], "Request a replacement because it arrived damaged; open a mail-in warranty repair");
check(reconstructed.length === 2
      && reconstructed[0].value === "Arrived damaged"
      && reconstructed[1].value === "Mail-in repair",
  "a full field reconstruction may remove sentence and task context");
const bounded = groundedFormCorrections({ values: [
  { index: 1, value: "bedroom outlet sparking; allow entry if nobody is home" },
] }, [
  { index: 1, name: "issue", label: "Problem", type: "textarea",
    value: "bedroom outlet sparking" },
], "Submit an urgent request: bedroom outlet sparking; allow entry if nobody is home", [
  { index: 1, name: "issue", label: "Problem", type: "textarea",
    value: "bedroom outlet sparking" },
  { index: 2, name: "entry", label: "Allow entry", type: "checkbox", value: true },
]);
check(bounded.length === 0,
  "a text correction cannot absorb the answer to another visible field");
check(JSON.stringify(unsupportedScopeFields(
  "Submit an urgent request and allow entry if nobody is home", { fields: [
    { name: "urgent", label: "Urgent", value: false },
    { name: "entry", label: "Allow entry", value: false },
  ] })) === JSON.stringify(["urgent", "entry"]),
  "an unchanged false checkbox cannot contradict a positive approved request");
check(unsupportedScopeFields("Do not request a refund", { fields: [
  { name: "refund", label: "Request refund", value: false },
] }).length === 0, "an explicitly negated checkbox stays false");
check(unsupportedScopeFields("Do not request a refund", { fields: [
  { name: "refund", label: "Request refund", value: true },
] }).includes("refund"), "a checked box cannot reverse an explicit negation");
const tomorrow = new Date();
tomorrow.setDate(tomorrow.getDate() + 1);
const localTomorrow = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, "0")}-${String(tomorrow.getDate()).padStart(2, "0")}`;
check(unsupportedScopeFields("Book tomorrow at 10:30 AM", { fields: [
  { name: "day", value: localTomorrow },
  { name: "time", value: "10:30" },
] }).length === 0, "native date and time values preserve relative approved meaning");
check(unsupportedScopeFields("Book on September 4 at 2:40 PM", { fields: [
  { name: "time", value: "14:40" },
] }).length === 0, "24-hour native time preserves an approved 12-hour time");
check(unsupportedScopeFields("Renew the license for one year", { fields: [
  { name: "term", value: "1 year" },
] }).length === 0, "number words authorize the same native numeric value");
check(unsupportedScopeFields("Renew the license for two years", { fields: [
  { name: "term", value: "1 year" },
] }).includes("term"), "a different number remains outside scope");
check(normalizedAuthorityText(
  "highway stone caused a 20 … then: yeah, agreed — cm crack")
  === "highway stone caused a 20 cm crack",
"the recognizer join marker is removed only for contiguous authorization");
check(unsupportedScopeFields(
  "highway stone caused a 20 … then: yeah, agreed — cm crack", { fields: [
    { name: "damage", label: "Damage", value: "highway stone caused a 20 cm crack" },
  ] }).length === 0,
"an exact value spanning a recognizer join remains authorized");
check(unsupportedScopeFields(
  "Schedule Jordan Chen at West Coast Dental", { fields: [
    { name: "clinic", label: "Clinic", value: "Coast Dental" },
  ] }).includes("clinic"),
"a named field cannot silently drop a leading proper-name word");
check(unsupportedScopeFields(
  "Cancel membership MBR-80189 at StudioBox", { fields: [
    { name: "member", label: "Membership", value: "MBR-80189 at StudioBox" },
  ] }).includes("member"),
"an identifier field cannot absorb its service or location");
const schoolScope = "Emergency contact Jordan Kim at +1 604 555 4798";
const schoolFields = { fields: [
  { index: 1, name: "contact", label: "Emergency contact", value: "Jordan Kim at +1 604 555 4798" },
  { index: 2, name: "phone", label: "Phone", value: "+16045550142" },
] };
check(JSON.stringify(unsupportedScopeFields(schoolScope, schoolFields,
  { phone: "+16045550142" })) === JSON.stringify(["contact", "phone"]),
"task contact data cannot bleed across fields or lose to a saved profile phone");
const boundaryFixes = schemaBoundaryCorrections(schoolFields.fields, schoolScope,
  schoolFields.fields);
check(boundaryFixes.some((row) => row.index === 1 && row.value === "Jordan Kim")
      && boundaryFixes.some((row) => row.index === 2
        && row.value === "+1 604 555 4798"),
"schema boundaries reconstruct separate contact and task-phone values");
const indexedBoundaryFixes = schemaBoundaryCorrections([
  { index: 1, name: "member", label: "Membership", value: "MBR-80189 at StudioBox" },
], "Cancel membership MBR-80189 at StudioBox", [
  { index: 1, name: "member", label: "Membership", value: "MBR-80189 at StudioBox" },
]);
check(indexedBoundaryFixes.length === 1 && indexedBoundaryFixes[0].value === "MBR-80189",
"schema boundaries repair an identifier contaminated by portal context");
const windowFixes = schemaBoundaryCorrections([
  { index: 2, name: "window", label: "Window", value: "OLD-3" },
], "Register the guest from 6 PM to 11 PM", [
  { index: 2, name: "window", label: "Window", value: "OLD-3" },
]);
check(windowFixes.length === 1 && windowFixes[0].value === "6 PM to 11 PM",
"schema boundaries reconstruct a complete approved time window");
check(terminalReceiptEvidence({
  text: "Submitted successfully. Confirmation #A42", title: "Request Portal",
}), "a success statement plus a receipt identifier is terminal evidence");
check(!terminalReceiptEvidence({
  text: "Click Submit to receive Confirmation #A42", title: "Request Portal",
}), "a page promising future confirmation is not terminal evidence");
check(!terminalReceiptEvidence({
  text: "Submitted successfully.", title: "Request Portal",
}), "success prose without a receipt identifier is not terminal evidence");
check(completionContradiction("Permission has NOT been submitted and was not granted."),
  "an explicit non-completion can never become done");
check(completionContradiction("The amounts were not correctly reflected."),
  "an admitted incorrect submission can never become done");
check(!completionContradiction("Replacement, not a refund, was submitted successfully."),
  "a negated alternative does not erase a successful action");
check(/if \(externalClick\)[\s\S]*unsupportedApprovedFacts\(facts, controlState, controlState\)[\s\S]*PRE-SUBMIT BLOCK[\s\S]*trustedClick/.test(source),
  "the exact-fact guard runs before a final click");
check(/if \(!authorized\)[\s\S]*owner has not approved its external effect/.test(source),
  "an unapproved final control is mechanically stopped");
check(/cleared unapproved optional defaults/.test(source),
  "unsupported optional defaults are cleared before the final control");
check(/PRE-SUBMIT ALIGNMENT corrected exact field values/.test(source)
      && /await auditFormAlignment/.test(source),
  "label-sized authority alignment runs before the final control");
check(source.includes("if (decision.enter === true)"),
  "typing cannot submit a form unless Enter was explicit");
check(!source.includes("if (decision.enter !== false)"),
  "an omitted Enter flag fails closed");
check(source.includes("copy the owner's relative wording exactly"),
  "ordinary text dates stay in the owner's words");

if (failed) process.exit(1);
console.log("test_exact_fact_verification: all passed");
