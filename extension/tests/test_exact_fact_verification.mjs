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

const { unsupportedApprovedFacts } = await import(join(here, "..", "agent_loop.js"));
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
check(/if \(externalClick\)[\s\S]*unsupportedApprovedFacts\(facts, state, state\)[\s\S]*PRE-SUBMIT BLOCK[\s\S]*trustedClick/.test(source),
  "the exact-fact guard runs before a final click");
check(/if \(!authorized\)[\s\S]*owner has not approved its external effect/.test(source),
  "an unapproved final control is mechanically stopped");

if (failed) process.exit(1);
console.log("test_exact_fact_verification: all passed");
