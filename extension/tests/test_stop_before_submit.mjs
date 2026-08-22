// Stop must be honoured BEFORE the irreversible action, not after it.
//
// The bug: runAgentGoal checked stillLive() exactly once, at the top of each
// step — before a mapPage (up to 20s), an LLM call, and the action. The popup
// said "stopped" the instant he tapped it. Everything already in flight still
// ran, so Stop could be honoured after the submit it existed to prevent.
//
// This is a CONTRACT test, not a scenario: it asserts that every consequential
// -action gate re-asks whether the job is still live. A future third submit
// path that forgets the check fails here rather than in front of an investor.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "..", "agent_loop.js"), "utf8");
let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

check("a late liveness helper exists", /const stoppedNow = async \(\)/.test(src));

check("the helper keeps working when liveness cannot be determined",
  /catch \(_\) \{ return false; \}/.test(src));

// Every external-effect gate must re-check liveness BEFORE it persists
// uncertainty and before it acts.
//
// THE INVARIANT IS THE ORDER, NOT THE DISTANCE. This used to scan a fixed
// eight-line window above each gate, which made it a proximity test wearing a
// safety test's clothes: adding five correct lines between the liveness check
// and the gate (the submission digest, 2026-08-22) turned it red while the
// ordering it exists to protect was still perfect —
//     stoppedNow()  ->  effectState = ...  ->  onBeforeExternalEffect(...)
// A test that fails when nothing it cares about changed teaches people to edit
// the test, which is how the real property eventually gets lost. So: look back
// as far as the enclosing block plausibly runs, and assert the sequence.
const lines = src.split("\n");
const gates = [];
lines.forEach((line, i) => {
  if (line.includes("onBeforeExternalEffect(decision")) gates.push(i);
});
check("both external-effect gates were found", gates.length >= 2);
for (const at of gates) {
  const window = lines.slice(Math.max(0, at - 40), at).join("\n");
  check(`gate at line ${at + 1} re-checks liveness before acting`,
    /stoppedNow\(\)/.test(window));
  // The check must come before the uncertainty write, or a stop leaves a
  // phantom "might have submitted" for recovery to reason about.
  const guardAt = window.lastIndexOf("stoppedNow()");
  const effectAt = window.lastIndexOf("effectState =");
  check(`gate at line ${at + 1} checks before persisting uncertainty`,
    guardAt >= 0 && effectAt >= 0 && guardAt < effectAt);
}

check("a stopped run says it stopped before submitting",
  /stopped before submitting/.test(src));

if (failures) { console.error(`test_stop_before_submit: ${failures} failed`); process.exit(1); }
console.log("test_stop_before_submit: all passed");
