// Offline suite for brief 03 (never-foreground). Run: node extension/tests/run_all.mjs
import { execFileSync } from "node:child_process";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const suites = [
  "check_never_foreground.mjs",
  "test_agent_loop_focus.mjs",
  "test_background_handback.mjs",
  "test_registration_singleflight.mjs",
  "test_background_scheduling.mjs",
  "test_background_tab_fallback.mjs",
  "test_core_resilience.mjs",
  "test_planner.mjs",
  "test_resume_tab.mjs",
  "test_code_guard.mjs",
  "test_protected_input.mjs",
  "test_verification_fail_closed.mjs",
  "test_exact_fact_verification.mjs",
  "test_research_query_hygiene.mjs",
  "test_workflow_state.mjs",
  "test_poll_deadlock.mjs",
  "test_attach_diagnosis.mjs",
  "test_hunt_round2.mjs",
  "test_commit_integrity.mjs",
  "test_captcha_solving.mjs",
  "test_no_domain_hardcoding.mjs",
];
let failed = 0;
for (const s of suites) {
  try {
    const out = execFileSync(process.execPath, [join(here, s)], { stdio: "pipe", timeout: 120000 });
    process.stdout.write(out);
  } catch (e) {
    failed++;
    process.stdout.write(String(e.stdout || ""));
    process.stderr.write(String(e.stderr || e));
    console.error(`FAIL: ${s}`);
  }
}
if (failed) { console.error(`run_all: ${failed}/${suites.length} suites failed`); process.exit(1); }
console.log(`run_all: all ${suites.length} suites passed`);

// EVERY suite in this directory must be listed above.
//
// Twice now a test file was written, passed when run by hand, and was never
// added here — so it protected nothing. The CapSolver checks and the
// no-hard-coding guarantee both sat unregistered until 2026-08-17. A test
// nobody runs is worse than no test: it reads like coverage.
import { readdirSync } from "node:fs";
const onDisk = readdirSync(new URL(".", import.meta.url))
  .filter((f) => f.startsWith("test_") && f.endsWith(".mjs"));
const missing = onDisk.filter((f) => !suites.includes(f));
if (missing.length) {
  console.error(`run_all: ${missing.length} suite(s) exist but are NOT registered: ${missing.join(", ")}`);
  process.exit(1);
}
