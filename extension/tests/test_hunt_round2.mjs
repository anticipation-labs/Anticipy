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
const sweep = bg.match(/async function requeueStaleJobs[\s\S]{0,1400}/)[0];
assert.ok(/lane!="research"/.test(sweep),
  "the sweep must exclude the lane it is forbidden to write");
const claim = bg.match(/async function claimJob[\s\S]{0,900}/)[0];
assert.ok(/lane!="research"/.test(claim),
  "sweep and claim must agree on which lanes belong to the browser");
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
