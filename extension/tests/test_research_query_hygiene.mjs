// Search queries may never carry rejection prose, quoted owner speech, phone
// numbers, or emails. Both leaks happened live on 2026-08-14: a stuck run
// searched "unparseable verifier response Give permission for Maya Ebrahim …
// +1 604 555 0142", and a resumed run searched the owner's own "Skip it, I do
// not need the batteries anymore" verbatim.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { sanitizedResearchTerms } from "../agent_loop.js";

const here = dirname(fileURLToPath(import.meta.url));

const goal = 'Give permission for Maya Ebrahim to attend the Science World field trip. ' +
  'Emergency contact is Omar Ebrahim at +1 604 555 0142, reach me at omar@example.com. ' +
  'You stopped and asked: "what plate?". They answered: "Skip it, I do not need it anymore".';
const terms = sanitizedResearchTerms(goal);
assert.ok(!/\d{3}.*\d{4}/.test(terms), "phone digits leaked into search terms");
assert.ok(!terms.includes("@"), "email leaked into search terms");
assert.ok(!terms.toLowerCase().includes("skip it"), "quoted owner speech leaked");
assert.ok(terms.includes("Science World"), "legitimate goal terms were destroyed");
console.log("  ok    quoted speech, phones, and emails never reach a search query");

const source = readFileSync(join(here, "..", "agent_loop.js"), "utf8");
const researchBlock = source.split("RESEARCH after rejected completion")[0].slice(-3000);
assert.ok(!/focus\s*=[\s\S]{0,120}compact\.slice/.test(researchBlock),
  "rejection prose is back in the research query focus");
assert.ok(source.includes("sanitizedResearchTerms(goal)"),
  "research queries no longer pass through the sanitizer");
console.log("  ok    rejection prose cannot become the research focus");

console.log("test_research_query_hygiene: all passed");
