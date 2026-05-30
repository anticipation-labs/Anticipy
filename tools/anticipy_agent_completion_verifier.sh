#!/usr/bin/env bash
# Helper run after each parallel agent claims completion.
#
# Args:
#   $1 agent_id              short identifier for the agent (e.g. "agent-04")
#   $2 claimed_commit_sha    the commit SHA the agent claims to have shipped
#   $3 claimed_verify_command verify command the agent says proves their work
#
# Steps:
#   1. Resolve the claimed commit (fail BROKEN if missing from git log).
#   2. Run the claimed verify command. Non-zero -> BROKEN.
#   3. Run ONE sentinel iteration. Non-zero -> BROKEN with sentinel evidence.
#   4. Print VERIFIED or BROKEN with details and write the audit record
#      to state/orchestrator/agent_completions/<ts>_<agent>.json.
#
# Read-only with respect to engine state; never restarts services.
# Exit code: 0 VERIFIED, 1 BROKEN, 2 usage error.

set -u

if [ $# -lt 3 ]; then
  echo "usage: $0 <agent_id> <claimed_commit_sha> <claimed_verify_command>" >&2
  exit 2
fi

AGENT_ID="$1"
CLAIMED_COMMIT="$2"
CLAIMED_VERIFY="$3"

REPO_ROOT="${ANTICIPY_REPO_ROOT:-/Users/omarebrahim/Developer/Anticipy-V7}"
SENTINEL="${REPO_ROOT}/tools/anticipy_loop_sentinel.sh"
AUDIT_DIR="${REPO_ROOT}/state/orchestrator/agent_completions"
mkdir -p "${AUDIT_DIR}"

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
TS=$(ts)
AUDIT_FILE="${AUDIT_DIR}/${TS//:/}_${AGENT_ID//[^A-Za-z0-9_-]/_}.json"

write_audit() {
  # write_audit <verdict> <reason> <commit_resolved> <verify_rc> <sentinel_verdict>
  local verdict="$1" reason="$2" commit_resolved="$3" verify_rc="$4" sentinel_verdict="$5"
  python3 - "$AUDIT_FILE" "$AGENT_ID" "$CLAIMED_COMMIT" "$CLAIMED_VERIFY" \
    "$verdict" "$reason" "$commit_resolved" "$verify_rc" "$sentinel_verdict" "$TS" <<'PY'
import json, sys
(path, agent, commit_claim, verify_claim, verdict, reason,
 commit_resolved, verify_rc, sentinel_verdict, ts) = sys.argv[1:11]
payload = {
    "ts": ts,
    "agent_id": agent,
    "claimed_commit_sha": commit_claim,
    "claimed_verify_command": verify_claim,
    "verdict": verdict,
    "reason": reason,
    "commit_resolved": commit_resolved,
    "verify_exit_code": int(verify_rc) if verify_rc.lstrip("-").isdigit() else verify_rc,
    "sentinel_verdict": sentinel_verdict,
}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2, sort_keys=True)
PY
}

# ----- step 1: resolve the claimed commit -----
COMMIT_RESOLVED=$(git -C "${REPO_ROOT}" rev-parse --verify "${CLAIMED_COMMIT}^{commit}" 2>/dev/null || true)
if [ -z "${COMMIT_RESOLVED}" ]; then
  REASON="commit ${CLAIMED_COMMIT} not found in repo"
  write_audit "BROKEN" "${REASON}" "" "" "skipped"
  echo "BROKEN agent=${AGENT_ID} reason=${REASON} audit=${AUDIT_FILE}"
  exit 1
fi

# ----- step 2: run the claimed verify command -----
VERIFY_OUT_FILE="${AUDIT_DIR}/${TS//:/}_${AGENT_ID//[^A-Za-z0-9_-]/_}.verify.out"
( cd "${REPO_ROOT}" && bash -c "${CLAIMED_VERIFY}" ) > "${VERIFY_OUT_FILE}" 2>&1
VERIFY_RC=$?
if [ "${VERIFY_RC}" -ne 0 ]; then
  REASON="verify command exited ${VERIFY_RC}; see ${VERIFY_OUT_FILE}"
  write_audit "BROKEN" "${REASON}" "${COMMIT_RESOLVED}" "${VERIFY_RC}" "skipped"
  echo "BROKEN agent=${AGENT_ID} commit=${COMMIT_RESOLVED} verify_rc=${VERIFY_RC} log=${VERIFY_OUT_FILE} audit=${AUDIT_FILE}"
  exit 1
fi

# ----- step 3: run ONE sentinel iteration -----
SENTINEL_OUT_FILE="${AUDIT_DIR}/${TS//:/}_${AGENT_ID//[^A-Za-z0-9_-]/_}.sentinel.out"
SENTINEL_SKIP_Z001=1 SENTINEL_FORCE_DEEP=0 bash "${SENTINEL}" > "${SENTINEL_OUT_FILE}" 2>&1
SENTINEL_RC=$?
SENTINEL_VERDICT="GREEN"
if [ "${SENTINEL_RC}" -ne 0 ]; then
  SENTINEL_VERDICT="RED"
fi

if [ "${SENTINEL_VERDICT}" = "RED" ]; then
  REASON="sentinel iteration RED after agent commit; see ${SENTINEL_OUT_FILE} and state/orchestrator/SENTINEL_ALERT.json"
  write_audit "BROKEN" "${REASON}" "${COMMIT_RESOLVED}" "${VERIFY_RC}" "${SENTINEL_VERDICT}"
  echo "BROKEN agent=${AGENT_ID} commit=${COMMIT_RESOLVED} verify_rc=${VERIFY_RC} sentinel=RED audit=${AUDIT_FILE}"
  exit 1
fi

write_audit "VERIFIED" "verify ok and sentinel GREEN" "${COMMIT_RESOLVED}" "${VERIFY_RC}" "${SENTINEL_VERDICT}"
echo "VERIFIED agent=${AGENT_ID} commit=${COMMIT_RESOLVED} verify_rc=${VERIFY_RC} sentinel=GREEN audit=${AUDIT_FILE}"
exit 0
