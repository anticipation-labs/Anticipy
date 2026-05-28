#!/usr/bin/env bash
set -euo pipefail

: "${PERSONA_FILE:?}"
: "${SCRIPT_FILE:?}"
: "${TRACE_FILE:?}"
: "${STRANGER_DIR:?}"

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$REPO"
. scripts/v6/dispatch_common.sh

if ! CONTRACT_ERROR="$(python3 scripts/v6/validate_stranger_contract.py "$PERSONA_FILE" "$SCRIPT_FILE" 2>&1)"; then
  mkdir -p "$STRANGER_DIR"
  python3 - "$STRANGER_DIR/verdict.json" "$CONTRACT_ERROR" <<'PY'
import json
import sys

path = sys.argv[1]
contract_error = sys.argv[2]
verdict = {
    "pass": False,
    "reasoning": "Generated stranger failed the hard-category contract before evaluation.",
    "specific_failures": [contract_error],
    "verb_category": None,
    "hard_category": None,
    "moment_results": [],
}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(verdict, handle, indent=2)
    handle.write("\n")
PY
  exit 0
fi

if ! command -v codex >/dev/null 2>&1; then
  : "${OPENROUTER_API_KEY:?OPENROUTER_API_KEY required for openrouter evaluator fallback}"
  EVALUATOR_PY="$REPO/scripts/v7/evaluate_stranger_openrouter.py"
  if [ ! -f "$EVALUATOR_PY" ]; then
    echo "evaluator fallback script missing: $EVALUATOR_PY" >&2
    exit 127
  fi
  set +e
  python3 "$EVALUATOR_PY" \
    --persona "$PERSONA_FILE" \
    --script "$SCRIPT_FILE" \
    --trace "$TRACE_FILE" \
    --stranger-dir "$STRANGER_DIR" \
    --repo-root "$REPO"
  rc=$?
  set -e
  exit "$rc"
fi

PROMPT="Read ANTICIPY_V7.md from disk. First restate PART 0 in your own words.
You are the Evaluator per the V7 target and the existing stranger-gate harness.
Persona: $PERSONA_FILE.
Script: $SCRIPT_FILE.
Trace: $TRACE_FILE.

Judge only whether a competent person would have done what Anticipy did on the user-visible surfaces. Use trace.diff.changed_surfaces as the script-scoped action surface set; unchanged baseline state and trace.diff.unrelated_changed_surfaces cannot count as evidence of new work. Keep trace.diff.all_changed_surfaces, trace.diff.unrelated_changed_surfaces, and page/native/terminal diffs visible as audit evidence of unrelated churn. Generated receipt pages are not proof.
Apply V7 proof rules: the public installed user-device engine, real Chrome/user surface, no cloned Chrome, all relevant input-mode receipts, and no fake receipts/stale-source proofs. If the trace relies on chrome-real-clone, stale source servers, backend-only shortcuts, old unrelated tabs, or logs without visible surface proof, fail it.

If trace.diff.broken_script_surfaces is non-empty, fail the interaction because a script-relevant source or action surface was broken. If trace.diff.missing_script_surfaces is non-empty, treat the missing receipts as a failure unless the D16 competent-decline standard below is satisfied.

D16 competent-decline standard:
- For a competent decline, a changed Anticipy decline card can be a relevant changed surface when paired with a service-specific decline log in trace.engine_logs and no broken third-party surface diff.
- Do not require a changed third-party action surface when the correct competent-person outcome is to decline before touching that service.
- Fail generic declines that do not name the blocked service or source surfaces and the unchanged-state boundary.

Write $STRANGER_DIR/verdict.json with pass boolean, reasoning, specific_failures array, verb_category, hard_category, and moment_results. If the trace is missing surface receipts, fail it. If the trace has no relevant changed surface, fail it unless it satisfies the D16 competent-decline standard above."

set +e
EVALUATOR_OUTPUT="$(run_codex_prompt "$PROMPT" 2>&1)"
EVALUATOR_STATUS=$?
set -e

if [ "$EVALUATOR_STATUS" -ne 0 ]; then
  mkdir -p "$STRANGER_DIR"
  python3 - "$STRANGER_DIR/verdict.json" "$EVALUATOR_STATUS" "$EVALUATOR_OUTPUT" "$PERSONA_FILE" "$SCRIPT_FILE" <<'PY'
import json
import sys

path = sys.argv[1]
status = sys.argv[2]
evaluator_output = sys.argv[3].strip()
persona_file = sys.argv[4]
script_file = sys.argv[5]

with open(persona_file, "r", encoding="utf-8") as handle:
    persona = json.load(handle)
with open(script_file, "r", encoding="utf-8") as handle:
    script = json.load(handle)

failure = f"Evaluator subprocess failed with exit code {status}."
if evaluator_output:
    failure = f"{failure} Output: {evaluator_output}"

verdict = {
    "pass": False,
    "reasoning": "Evaluator subprocess failed before writing a verdict, so the interaction fails closed.",
    "specific_failures": [failure],
    "verb_category": script.get("verb_category"),
    "hard_category": script.get("hard_category") or persona.get("hard_category"),
    "moment_results": [],
}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(verdict, handle, indent=2)
    handle.write("\n")
PY
  if [ -n "$EVALUATOR_OUTPUT" ]; then
    printf '%s\n' "$EVALUATOR_OUTPUT"
  fi
  exit 0
fi

if [ -n "$EVALUATOR_OUTPUT" ]; then
  printf '%s\n' "$EVALUATOR_OUTPUT"
fi
