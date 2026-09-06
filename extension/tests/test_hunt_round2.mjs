// Findings from the 244-agent adversarial hunt that survived two independent
// refuters. Each is a way the browser arm goes silent or writes to the wrong
// place — the same family of symptom the owner hit all week.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const bg = readFileSync(join(here, "../background.js"), "utf8");
const map = readFileSync(join(here, "../page_map.js"), "utf8");

// --- the research-lane 403 that silenced the whole queue ---------------------
// Research runs in the WORKER on a 120s never-heartbeated lease. Two minutes
// in, the extension's stale sweep saw an expired lease on a row it is
// forbidden to write, PATCHed it, got 403, and that throw escaped the poll
// cycle BEFORE claimJob() — so nothing was claimed for the whole research run
// while the heartbeat kept the phone showing "Chrome ready".
//
// The invariant is that the two agree, so assert THAT, not two copies of a
// string. This used to slice 900 characters out of claimJob and grep them,
// which broke the first time the function grew — the filter was still right
// and the test could simply no longer see it. One definition, and both
// callers named against it.
// lane!="api" joined 2026-09-06: the API hand's rows are the worker's, and a
// browser that listed them claimed them (test_api_lane_is_not_browser_work.mjs).
assert.ok(/const BROWSER_LANE = 'workflow_id!="" && lane!="research" && lane!="api"';/.test(bg),
  "one definition of the lanes this browser may take work from");
for (const [what, fn] of [["sweep", "requeueStaleJobs"], ["claim", "claimJob"]]) {
  const body = bg.match(new RegExp(`async function ${fn}\\(\\)[\\s\\S]*?\\n\\}`))[0];
  assert.ok(/ownerLaneFilter\(/.test(body),
    `the ${what} must take its lanes from the shared definition, not a second copy`);
  assert.ok(!/lane\s*!=\s*"research"/.test(body),
    `a hand-written lane clause inside ${fn} is exactly the drift that silenced the queue`);
}
assert.ok(/requeueStaleJobs\(\)\.catch\(/.test(bg),
  "housekeeping must never decide whether real work gets claimed");
assert.ok(/could not recover stale job/.test(bg),
  "one poisoned row must not cost the others their recovery");

// --- writes must never land in a password box -------------------------------
// Writes resolve to the ACTIVE element when a synthetic click could not move
// focus, while the guards run against the MAPPED index. A sign-in dialog that
// autofocuses its password field could take the owner's email or phone.
const active = map.match(/function activeEditable\(\)[\s\S]{0,900}/)[0];
assert.ok(/"password"/.test(active),
  "an autofocused password field must never be a write target");
for (const t of ["submit", "button", "checkbox", "radio", "hidden", "file"]) {
  assert.ok(active.includes(`"${t}"`), `${t} must stay excluded`);
}

console.log("test_hunt_round2: all passed");
