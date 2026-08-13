// Offline suite for brief 03 (never-foreground). Run: node extension/tests/run_all.mjs
import { execFileSync } from "node:child_process";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const suites = [
  "check_never_foreground.mjs",
  "test_agent_loop_focus.mjs",
  "test_background_handback.mjs",
  "test_planner.mjs",
  "test_resume_tab.mjs",
  "test_code_guard.mjs",
  "test_verification_fail_closed.mjs",
  "test_workflow_state.mjs",
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
