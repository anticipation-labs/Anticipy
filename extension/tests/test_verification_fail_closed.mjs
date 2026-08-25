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
// A DONE RESULT CARRIES THE EVIDENCE THAT JUSTIFIED IT.
//
// This was `/receipt:\s*\{ verified: true, evidence: verdict\.evidence/` — one
// literal, matching one line's exact punctuation. It went red on 2026-08-25
// because the receipt gained a second source of evidence (the milestone marks,
// card HANDS 3) and the line wrapped. The property never changed; only the
// spelling did. That is the defect `.superpowers/sdd/second-door-criticals.md`
// C2 names: a test pinned to today's implementation shape, which has to be
// rewritten by whoever touches the line and therefore stops being evidence of
// anything.
//
// So it asks the question the file actually cares about, of EVERY done exit
// there is: does this success name the verdict that justified it? A new exit
// that forgets to is caught; a reflow is not. The behavioural half — that the
// verifier's own proof index really does survive into the receipt a job row
// gets — lives in test_evidence_capture.mjs, which runs the loop.
{
  const exits = [...src.matchAll(/return \{ status: "done"[\s\S]{0,400}?\};/g)]
    .map((m) => m[0]);
  ok(exits.length >= 2, `every done exit was found (${exits.length})`);
  ok(exits.length > 0 && exits.every((exit) =>
    /verified: true/.test(exit) && /verdict\.evidence/.test(exit)),
  "a done result carries the evidence that justified it");
}
ok(/onBeforeExternalEffect/.test(src),
  "external-effect uncertainty is persisted before an authorized action");

if (failed) process.exit(1);
console.log("test_verification_fail_closed: all passed");
