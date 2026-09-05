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
  "test_recovery_reads_a_gap_token.mjs",
  "test_row_is_a_model_verdict.mjs",
  "test_financial_errand_is_a_verdict.mjs",
  "test_model_fetch_retries_transients.mjs",
  "test_model_reply_floor.mjs",
  "test_planner.mjs",
  "test_resume_tab.mjs",
  "test_code_guard.mjs",
  "test_protected_input.mjs",
  "test_takeover_list.mjs",
  "test_evidence_capture.mjs",
  "test_done_is_not_a_word_match.mjs",
  "test_done_is_not_a_sentence_match.mjs",
  "test_verification_fail_closed.mjs",
  "test_exact_fact_verification.mjs",
  "test_field_kind_is_not_a_word_match.mjs",
  "test_record_count_is_not_a_regex_match.mjs",
  "test_suggestions_keep_every_option.mjs",
  "test_placeholder_is_a_verdict.mjs",
  "test_research_query_hygiene.mjs",
  "test_search_provider.mjs",
  "test_workflow_state.mjs",
  "test_poll_deadlock.mjs",
  "test_attach_diagnosis.mjs",
  "test_hunt_round2.mjs",
  "test_hunt_round3.mjs",
  "test_commit_integrity.mjs",
  "test_commit_once.mjs",
  "test_effect_intent_survives_crash.mjs",
  "test_reconcile_after_crash.mjs",
  "test_form_retry_after_rejection.mjs",
  "test_captcha_solving.mjs",
  "test_challenge_is_a_verdict.mjs",
  "test_no_domain_hardcoding.mjs",
  "test_stop_before_submit.mjs",
  "test_park_not_burn.mjs",
  "test_live_progress.mjs",
  "test_side_trip.mjs",
  "test_supervised_read.mjs",
  "test_narration_is_not_a_word_match.mjs",
  "test_background_recovery.mjs",
  "test_offline_completion_honesty.mjs",
  "test_guard_superuser_dashboard.mjs",
  "test_claim_legacy_binding.mjs",
  "test_backup_volume_footprint.mjs",
  "test_log_db_footprint.mjs",
  "test_memory_context.mjs",
  "test_memory_in_the_prompt.mjs",
  "test_config_base.mjs",
  "test_learn_before_doing.mjs",
  "test_server_procedure_reaches_the_hands.mjs",
  "test_recall_is_not_gated.mjs",
  "test_recall_is_confirmed.mjs",
  "test_otp_wall.mjs",
  "test_inbox_consent.mjs",
  "test_code_sent_is_not_a_word_match.mjs",
  "test_code_read_is_not_a_word_match.mjs",
  "test_private_places.mjs",
  "test_authored_draft.mjs",
  "test_question_reaches_him.mjs",
  "test_calendar_date.mjs",
  "test_box_verdict.mjs",
  "test_scope_temporal_value.mjs",
  "test_vision_cost.mjs",
  "test_walled_source.mjs",
  "test_carried_values.mjs",
  "test_wall_is_not_a_word_match.mjs",
  "test_recipes.mjs",
  "test_claim_evidence.mjs",
  "test_agent_integration.mjs",
  "test_theme_contract.mjs",
  "test_watch_lease.mjs",
  "test_device_lane.mjs",
  "test_owner_profile_needs_owner.mjs",
  "test_account_delete_flow.mjs",
  "test_hook_scope_trap.mjs",
  "test_guard_agent_credential.mjs",
  "test_config_backend_base.mjs",
  "test_one_submission_two_keys.mjs",
  "test_pair_code_throttle.mjs",
  "test_pair_code_collision.mjs",
  "test_hosted_setup_bridge.mjs",
  "test_spawned_tab_uses_one_gate.mjs",
  "test_commit_beats_reversible_prefix.mjs",
  "test_name_completeness_is_not_a_word_list.mjs",
  "test_completion_shape_is_a_model_verdict.mjs",
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
