// Offline suite for brief 03 (never-foreground). Run: node extension/tests/run_all.mjs
import { execFileSync } from "node:child_process";
import { readdirSync } from "node:fs";
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
  "test_hunt_round3.mjs",
  "test_commit_integrity.mjs",
  "test_commit_once.mjs",
  "test_form_retry_after_rejection.mjs",
  "test_captcha_solving.mjs",
  "test_no_domain_hardcoding.mjs",
  "test_stop_before_submit.mjs",
  "test_park_not_burn.mjs",
  "test_live_progress.mjs",
  "test_side_trip.mjs",
  "test_supervised_read.mjs",
  "test_background_recovery.mjs",
  "test_guard_superuser_dashboard.mjs",
  "test_claim_legacy_binding.mjs",
  "test_backup_volume_footprint.mjs",
  "test_log_db_footprint.mjs",
  "test_memory_context.mjs",
  "test_memory_in_the_prompt.mjs",
  "test_config_base.mjs",
  "test_learn_before_doing.mjs",
  "test_otp_wall.mjs",
  "test_inbox_consent.mjs",
  "test_private_places.mjs",
  "test_authored_draft.mjs",
  "test_question_reaches_him.mjs",
  "test_calendar_date.mjs",
  "test_vision_cost.mjs",
  "test_walled_source.mjs",
  "test_carried_values.mjs",
  "test_login_wall.mjs",
  "test_recipes.mjs",
  "test_claim_evidence.mjs",
  "test_agent_integration.mjs",
  "test_theme_contract.mjs",
  "test_watch_lease.mjs",
  "test_owner_profile_needs_owner.mjs",
  "test_account_delete_flow.mjs",
  "test_hook_scope_trap.mjs",
  "test_guard_agent_credential.mjs",
  "test_config_backend_base.mjs",
  "test_one_submission_two_keys.mjs",
  "test_pair_code_throttle.mjs",
  "test_pair_code_collision.mjs",
];
// A suite listed TWICE runs twice and inflates the number in the pass line —
// and that number is exactly what a person reads to decide whether coverage
// grew. test_side_trip.mjs was registered twice and the run reported 33 suites
// where there were 32. Checked before anything executes: this is a static
// property of the list, and failing fast beats discovering it after 15s.
const dupes = [...new Set(suites.filter((s, i) => suites.indexOf(s) !== i))];
if (dupes.length) {
  console.error(`run_all: registered more than once: ${dupes.join(", ")}`);
  process.exit(1);
}

// EVERY suite in this directory must be listed above.
//
// Twice now a test file was written, passed when run by hand, and was never
// added here — so it protected nothing. The CapSolver checks and the
// no-hard-coding guarantee both sat unregistered until 2026-08-17. A test
// nobody runs is worse than no test: it reads like coverage.
//
// This check used to sit at the very bottom, AFTER the `failed` exit — so the
// one situation where an unregistered file is most likely (somebody mid-change,
// something red) was exactly the situation where it never ran. It asks a static
// question about the directory; ask it first.
const onDisk = readdirSync(new URL(".", import.meta.url))
  .filter((f) => f.startsWith("test_") && f.endsWith(".mjs"));
const missing = onDisk.filter((f) => !suites.includes(f));
if (missing.length) {
  console.error(`run_all: ${missing.length} suite(s) exist but are NOT registered: ${missing.join(", ")}`);
  process.exit(1);
}
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
