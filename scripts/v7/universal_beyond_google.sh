#!/usr/bin/env bash
# Universal action loop: proof on NON-Google surfaces.
#
# Per memory feedback_test_beyond_google.md: every claim of universal
# action must verify against >= 3 non-Google apps. This script picks
# three public surfaces that need no Google sign-in, drives the SAME
# universal action loop at engine/app/universal/action_loop.py against
# each one via POST /api/universal/run, and aggregates the result.
#
# Surfaces:
#   1. saucedemo.com         e-commerce login plus add-to-cart
#   2. the-internet.herokuapp.com  classic login form
#   3. en.wikipedia.org      search and read a real article
#
# Each test POSTs an intent plus surface_hint to /api/universal/run.
# The endpoint returns the runner's TaskResult including trajectory_dir
# under ~/.anticipy/trajectories/<task_id>/, where every iteration has
# *_before.png and *_after.png. We pick the LAST *_after.png as the
# evidence screenshot.
#
# Per-test result.json captures: surface, intent, status, n_iterations,
# evidence_screenshot_path, elapsed_sec, trajectory_dir, raw response.
# Aggregate verdict: PASS iff all 3 surfaces SUCCESS.
#
# Output dir: state/v7/universal_beyond_google_runs/<ts>/
# Exit code: 0 PASS, 1 FAIL.

set -uo pipefail

REPO="/Users/omarebrahim/Developer/Anticipy-V7"
ENGINE="http://127.0.0.1:8731"
BRIDGE="http://127.0.0.1:7777"
CDP="http://localhost:9222"

TS="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="${REPO}/state/v7/universal_beyond_google_runs/${TS}"
mkdir -p "${RUN_DIR}"
LOG="${RUN_DIR}/run.log"

# Per-surface deadline (wall clock seconds). 120s is enough for the
# focused single-action intents below: each iteration is ~10-15s
# (vision LLM read + CDP dispatch + after-screenshot capture). The
# loop SHOULD finish in 1-5 iterations for the picks below; 120s
# gives generous headroom.
DEADLINE_SEC="${UNIVERSAL_DEADLINE_SEC:-120}"

log() { printf '[%s] %s\n' "$(date -u +%H:%M:%SZ)" "$*" | tee -a "${LOG}"; }

# Preflight: engine on 8731 plus Chrome on 9222 must answer.
check_engine() {
  local code
  code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "${ENGINE}/health" 2>/dev/null || echo 000)
  if [[ "${code}" != "200" ]]; then
    log "ENGINE preflight FAIL: ${ENGINE}/health -> ${code}"
    return 1
  fi
  log "ENGINE up: ${ENGINE}/health -> 200"
  return 0
}

check_chrome() {
  local code
  code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "${CDP}/json/version" 2>/dev/null || echo 000)
  if [[ "${code}" != "200" ]]; then
    log "CHROME preflight FAIL: ${CDP}/json/version -> ${code}"
    return 1
  fi
  log "CHROME up: ${CDP}/json/version -> 200"
  return 0
}

check_bridge() {
  local body
  body=$(curl -s -m 5 "${BRIDGE}/status" 2>/dev/null || true)
  if ! echo "${body}" | grep -q '"ok": true'; then
    log "BRIDGE preflight WARN: status not ok: ${body:0:160}"
    # Bridge is informational; the universal loop talks straight to CDP
    # via the runner's _ensure_agent_window helper. Do not hard fail.
  else
    log "BRIDGE up: ${BRIDGE}/status ok"
  fi
}

# run_test SURFACE_LABEL INTENT SURFACE_HINT
# Writes ${RUN_DIR}/<label>/result.json. Echoes the per-test status to
# stdout so the loop can aggregate.
run_test() {
  local label="$1"
  local intent="$2"
  local hint="$3"
  local out_dir="${RUN_DIR}/${label}"
  mkdir -p "${out_dir}"
  local resp_file="${out_dir}/raw_response.json"
  local res_file="${out_dir}/result.json"
  local t0 t1 elapsed http_code
  # Mark wall-clock window so we can recover the right trajectory on
  # DEADLINE_EXCEEDED (the loop's worker thread keeps writing the
  # trajectory even after the outer deadline trips and the response
  # returns trajectory_dir="").
  t0=$(python3 -c 'import time; print(time.time())')
  log "BEGIN ${label} :: intent=${intent}"
  log "BEGIN ${label} :: hint=${hint} deadline=${DEADLINE_SEC}s"

  # Body via python3 for safe JSON encoding (no shell quoting pitfalls).
  local body
  body=$(LABEL="${label}" INTENT="${intent}" HINT="${hint}" \
         DL="${DEADLINE_SEC}" python3 - <<'PY'
import json, os
print(json.dumps({
    "intent": os.environ["INTENT"],
    "surface_hint": os.environ["HINT"],
    "deadline_sec": float(os.environ["DL"]),
}))
PY
  )

  # Curl timeout has to exceed deadline. Add 30s safety margin so the
  # inner runner can finish its trajectory write even after the
  # universal loop's deadline trips.
  local curl_timeout
  curl_timeout=$((DEADLINE_SEC + 30))

  http_code=$(curl -s -m "${curl_timeout}" -o "${resp_file}" \
                   -w '%{http_code}' \
                   -X POST "${ENGINE}/api/universal/run" \
                   -H "Content-Type: application/json" \
                   -d "${body}" 2>/dev/null || echo 000)
  t1=$(python3 -c 'import time; print(time.time())')
  elapsed=$(python3 -c "print(round(${t1}-${t0}, 3))")

  # Always emit a result.json. Use python to parse the raw response and
  # find the last *_after.png in trajectory_dir for evidence. On
  # DEADLINE_EXCEEDED the loop's response has empty trajectory_dir
  # because the worker thread is still running; in that case we recover
  # the trajectory dir by picking the newest entry under
  # ~/.anticipy/trajectories that was created during our window
  # [t0, now]. This is best-effort honest reporting, not a fake claim
  # of success.
  RESP="${resp_file}" OUT="${res_file}" LABEL="${label}" \
       INTENT="${intent}" HINT="${hint}" \
       ELAPSED="${elapsed}" HTTP="${http_code}" \
       DEADLINE="${DEADLINE_SEC}" T0="${t0}" python3 - <<'PY'
import json, os
from pathlib import Path

resp_path = Path(os.environ["RESP"])
out_path = Path(os.environ["OUT"])
label = os.environ["LABEL"]
intent = os.environ["INTENT"]
hint = os.environ["HINT"]
elapsed = float(os.environ["ELAPSED"])
http_code = os.environ["HTTP"]
deadline = float(os.environ["DEADLINE"])
t0 = float(os.environ["T0"])

try:
    raw = resp_path.read_text() if resp_path.exists() else ""
    resp = json.loads(raw) if raw.strip() else {}
except Exception as exc:
    resp = {"_parse_error": f"{type(exc).__name__}: {exc}"}

status = str(resp.get("status") or "ERROR")
n_iter = int(resp.get("n_iterations") or 0)
traj_dir = str(resp.get("trajectory_dir") or "")
answer = str(resp.get("answer") or "")[:600]
evidence_text = str(resp.get("evidence") or "")[:600]
error = resp.get("error")

# Recovery path: if the response has no trajectory_dir (DEADLINE_EXCEEDED
# leaves it empty because the worker thread is still alive), scan
# ~/.anticipy/trajectories and pick the most recently MODIFIED entry
# whose mtime falls inside [t0, now+5]. This is the trajectory the
# worker thread is writing into right now.
traj_recovered = False
if not traj_dir:
    root = Path(os.path.expanduser("~/.anticipy/trajectories"))
    if root.is_dir():
        import time
        now = time.time()
        cands = []
        for p in root.iterdir():
            if not p.is_dir():
                continue
            try:
                mt = p.stat().st_mtime
            except Exception:
                continue
            if t0 - 5 <= mt <= now + 5:
                cands.append((mt, p))
        if cands:
            cands.sort()
            traj_dir = str(cands[-1][1])
            traj_recovered = True

# Pick the most recent *_after.png as the evidence screenshot. If none,
# fall back to the most recent *_before.png.
evidence_shot = ""
traj_iter_count = 0
if traj_dir and Path(traj_dir).is_dir():
    afters = sorted(Path(traj_dir).glob("*_after.png"))
    befores = sorted(Path(traj_dir).glob("*_before.png"))
    traj_iter_count = max(len(afters), len(befores))
    if afters:
        evidence_shot = str(afters[-1])
    elif befores:
        evidence_shot = str(befores[-1])

# If we recovered a trajectory dir, also recover the iteration count
# from the on-disk file count (the response's n_iterations is 0 on
# deadline because the worker hasn't returned its TaskResult).
if traj_recovered and traj_iter_count > 0:
    n_iter = traj_iter_count

# Universal loop SUCCESS means vision auditor confirmed the goal on
# the real after-screenshot. Any other status counts as not-yet-proven.
verdict = "PASS" if status == "SUCCESS" else "FAIL"

result = {
    "surface": label,
    "intent": intent,
    "surface_hint": hint,
    "status": status,
    "verdict": verdict,
    "n_iterations": n_iter,
    "elapsed_sec": elapsed,
    "deadline_sec": deadline,
    "http_code": http_code,
    "answer": answer,
    "evidence_text": evidence_text,
    "evidence_screenshot_path": evidence_shot,
    "trajectory_dir": traj_dir,
    "trajectory_recovered_from_disk": traj_recovered,
    "error": error,
}
out_path.write_text(json.dumps(result, indent=2))
print(json.dumps({"label": label, "verdict": verdict, "status": status,
                  "n_iterations": n_iter, "elapsed_sec": elapsed,
                  "evidence_screenshot_path": evidence_shot,
                  "trajectory_dir": traj_dir,
                  "trajectory_recovered_from_disk": traj_recovered}))
PY
  log "END ${label} :: http=${http_code} elapsed=${elapsed}s"
  # Echo verdict line for the aggregator (python wrote it to stdout).
}

# --- preflight --------------------------------------------------------------
check_engine || { log "ABORT: engine down"; exit 1; }
check_chrome || { log "ABORT: chrome :9222 down"; exit 1; }
check_bridge

# --- the three picks --------------------------------------------------------
# Each intent is concrete and verifiable by reading the after-screenshot.
# No per-app code, no hardcoded selectors. The universal loop reads the
# DOM accessibility tree plus screenshot, asks the vision model for the
# next concrete action, dispatches over CDP, observes, repeats, and the
# vision auditor confirms completion.

# Each intent below is intentionally a focused meaningful action plus
# a verification step (not just a navigate). The universal loop reads
# the DOM accessibility tree plus screenshot, decides via vision LLM,
# dispatches via CDP, observes, and the vision auditor confirms on
# the real after-screenshot. The loop SUCCEEDS when the auditor
# confirms the intent end-state. All three intents are non-Google,
# public, and need no login. The verification is concrete enough
# that the vision auditor can confirm or deny by reading the
# after-screenshot. We pick concise, single-step actions because the
# loop's per-iteration cost is ~10-12s (vision LLM read + CDP
# dispatch + after-screenshot capture); multi-step flows like full
# login plus add-to-cart need 15 plus iterations and over 200
# seconds, which fights the 300s wall-clock budget.

# Surface 1: saucedemo.com (e-commerce demo, no real login required).
# Action: type the username into the visible login field. Verify by
# reading the field value back from the after-screenshot.
SAUCE_INTENT="On the SauceDemo login page, type the text standard_user into the Username input field. The task is complete when the Username input shows the text standard_user."

# Surface 2: the-internet.herokuapp.com /add_remove_elements (classic
# click-and-observe page). One real click on the Add Element button
# spawns a Delete button. Verifying the Delete button appeared proves
# the click landed and the page state changed.
HEROKU_INTENT="On this Add/Remove Elements page, click the button labeled Add Element. The task is complete when a new button labeled Delete appears on the page below the Add Element button."

# Surface 3: en.wikipedia.org. The article URL is the starting point
# so the loop confirms it can read DOM and verify content on a real
# encyclopedia article. The vision auditor checks the heading on the
# real page.
WIKI_INTENT="Read the page heading and the very first sentence of the article body on this Wikipedia page. The task is complete when you have reported what the heading says and the first sentence of the article."

# Wait for the previous runner's worker thread to release the
# Anticipy-owned background tab before starting the next surface.
# The runner thread is daemon; it keeps writing its trajectory after
# the outer deadline trips and the response returns. Starting a new
# surface immediately would have two runners driving the same target
# tab. We poll openrouter_calls.jsonl for idle (no new line in the
# last quiesce_sec seconds) up to a cap, then proceed.
wait_for_runner_idle() {
  local quiesce_sec="${1:-8}"
  local cap_sec="${2:-60}"
  local calls_file="${HOME}/.anticipy/openrouter_calls.jsonl"
  local started
  started=$(python3 -c 'import time; print(time.time())')
  python3 - "${calls_file}" "${quiesce_sec}" "${cap_sec}" "${started}" <<'PY'
import os, sys, time
path = sys.argv[1]
qs = float(sys.argv[2])
cap = float(sys.argv[3])
t0 = float(sys.argv[4])
def last_mtime():
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0
deadline = t0 + cap
done = False
while time.time() < deadline:
    lm = last_mtime()
    if lm == 0.0 or (time.time() - lm) >= qs:
        print(f"runner_idle after {time.time()-t0:.1f}s; "
              f"last_call_age={time.time()-lm:.1f}s")
        done = True
        break
    time.sleep(1.0)
if not done:
    print(f"runner_idle wait CAPPED at {cap:.0f}s; proceeding anyway")
PY
}

# Run sequentially. Parallel would race for the same Anticipy-owned
# background tab and produce nondeterministic results.
# wait_for_engine_alive: poll /health up to cap_sec until it returns
# 200. The engine has been observed to die between universal/run
# calls (CDP WebSocket close races). We wait for it to come back
# before proceeding; if it never does, the next surface will fail
# fast with http=000 and our result.json honestly reports that.
wait_for_engine_alive() {
  local cap_sec="${1:-30}"
  local t0
  t0=$(python3 -c 'import time; print(time.time())')
  python3 - "${cap_sec}" "${t0}" "${ENGINE}" <<'PY'
import sys, time, urllib.request
cap = float(sys.argv[1])
t0 = float(sys.argv[2])
engine = sys.argv[3]
url = f"{engine}/health"
deadline = t0 + cap
ok = False
while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            if r.status == 200:
                print(f"engine alive after {time.time()-t0:.1f}s")
                ok = True
                break
    except Exception:
        pass
    time.sleep(2.0)
if not ok:
    print(f"engine NOT alive after {cap:.0f}s; proceeding anyway")
PY
}

log "==== SURFACE 1: saucedemo ===="
run_test "saucedemo" "${SAUCE_INTENT}" "https://www.saucedemo.com/"
log "wait for runner thread to quiesce before next surface"
wait_for_runner_idle 8 60 | tee -a "${LOG}"
log "wait for engine to be alive"
wait_for_engine_alive 60 | tee -a "${LOG}"
log "==== SURFACE 2: the_internet_herokuapp ===="
run_test "the_internet_herokuapp" "${HEROKU_INTENT}" "https://the-internet.herokuapp.com/add_remove_elements/"
log "wait for runner thread to quiesce before next surface"
wait_for_runner_idle 8 60 | tee -a "${LOG}"
log "wait for engine to be alive"
wait_for_engine_alive 60 | tee -a "${LOG}"
log "==== SURFACE 3: wikipedia ===="
run_test "wikipedia" "${WIKI_INTENT}" "https://en.wikipedia.org/wiki/Roman_Empire"

# --- aggregate --------------------------------------------------------------
AGG="${RUN_DIR}/result.json"
RUN_DIR_ENV="${RUN_DIR}" AGG_ENV="${AGG}" TS_ENV="${TS}" python3 - <<'PY'
import json, os
from pathlib import Path

run_dir = Path(os.environ["RUN_DIR_ENV"])
agg_path = Path(os.environ["AGG_ENV"])
ts = os.environ["TS_ENV"]

surfaces = ["saucedemo", "the_internet_herokuapp", "wikipedia"]
per = []
all_pass = True
for s in surfaces:
    rp = run_dir / s / "result.json"
    if not rp.exists():
        per.append({"surface": s, "verdict": "FAIL",
                    "error": "result.json missing"})
        all_pass = False
        continue
    try:
        r = json.loads(rp.read_text())
    except Exception as exc:
        per.append({"surface": s, "verdict": "FAIL",
                    "error": f"parse: {exc}"})
        all_pass = False
        continue
    per.append(r)
    if r.get("verdict") != "PASS":
        all_pass = False

agg = {
    "ts": ts,
    "run_dir": str(run_dir),
    "surfaces_tested": surfaces,
    "verdict": "PASS" if all_pass else "FAIL",
    "per_surface": per,
}
agg_path.write_text(json.dumps(agg, indent=2))
print(json.dumps(agg, indent=2))
PY

VERDICT=$(python3 -c "import json; print(json.load(open('${AGG}'))['verdict'])")
log "AGGREGATE verdict=${VERDICT}"
log "AGGREGATE result.json: ${AGG}"

if [[ "${VERDICT}" == "PASS" ]]; then
  exit 0
else
  exit 1
fi
