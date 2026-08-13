// A browser verifier is allowed to withhold success. It is never allowed to
// manufacture success because the page, model, or JSON could not be read.

import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "..", "agent_loop.js"), "utf8");

let failed = 0;
const ok = (condition, name) => {
  if (condition) console.log(`PASS: ${name}`);
  else { failed++; console.error(`FAIL: ${name}`); }
};

ok(!/claim accepted unverified/.test(src),
  "no verifier failure path accepts an unverified completion");
ok(/page unreadable; completion is unverified/.test(src),
  "an unreadable page fails closed");
ok(/unparseable verifier response/.test(src),
  "an unparseable verifier response fails closed");
ok(/verifier error; completion is unverified/.test(src),
  "a verifier error fails closed");
ok(/receipt:\s*\{ verified: true, evidence: verdict\.evidence/.test(src),
  "a done result carries the evidence that justified it");
ok(/onBeforeExternalEffect/.test(src),
  "external-effect uncertainty is persisted before an authorized action");

if (failed) process.exit(1);
console.log("test_verification_fail_closed: all passed");
