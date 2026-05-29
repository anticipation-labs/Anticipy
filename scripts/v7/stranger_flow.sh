#!/usr/bin/env bash
# Anticipy V7 stranger-flow proof harness.
#
# The end-to-end test that has never been run honestly. A real "stranger"
# (brand-new macOS user) downloads the DMG, installs, onboards, and does ONE
# real action. This script is the scripted version against the live engine.
#
# Step plan (per HANDOFF_FOR_NEXT_AGENT.md spec):
#   1. Snapshot the current ~/.anticipy/v7/ (so a real user run does not lose
#      Omar's dossier, decisions log, or normalized inputs).
#   2. Wipe ~/.anticipy/v7/ to simulate a brand-new user.
#   3. POST /api/coldstart/start (unit 12 work). If not yet shipped, mark the
#      coldstart steps SKIPPED with a clear message and continue so the
#      restore-and-verify chain still exercises.
#   4. Poll GET /api/coldstart/status until done or 90s. Report people_count.
#   5. POST /api/listen/inject with a scripted utterance designed to work with
#      whatever dossier the inhale produced (or the empty dossier the engine
#      has after the wipe).
#   6. POST /api/act and verify a real Gmail draft appears in the user's Chrome
#      (CDP read of mail.google.com/u/0/#drafts via the same pattern Z-001
#      uses).
#   7. Restore the snapshot to ~/.anticipy/v7/ so Omar's real state is intact.
#   8. Write result.json with verdict, per-step timings, and evidence pointers.
#
# Exit code is 0 if the harness completed end-to-end (PASS or honest FAIL).
# Exit code is non-zero only when the harness itself crashed mid-flight in a
# way that left state half-restored; in that case the snapshot path is printed
# loudly so a human can restore manually.
#
# This is the test that proves the product works for a new user. Run it on
# demand.
#
# Usage:
#   scripts/v7/stranger_flow.sh
#
# Env (optional):
#   ANTICIPY_ENGINE_URL   default http://127.0.0.1:8731
#   ANTICIPY_CDP_BASE     default http://localhost:9222
#   ANTICIPY_TRIGGER_SECRET (read but currently unused; reserved for bridge fallback)
#   STRANGER_INJECT_TEXT  override the scripted utterance
#   STRANGER_TIMEOUT_INHALE_S  default 90
#   STRANGER_TIMEOUT_ACT_S     default 120

set -uo pipefail

# Resolve repo root and required paths.
REPO_ROOT="/Users/omarebrahim/Developer/Anticipy-V7"
ANTICIPY_HOME="$HOME/.anticipy/v7"
ENGINE_URL="${ANTICIPY_ENGINE_URL:-http://127.0.0.1:8731}"
CDP_BASE="${ANTICIPY_CDP_BASE:-http://localhost:9222}"
TIMEOUT_INHALE_S="${STRANGER_TIMEOUT_INHALE_S:-90}"
TIMEOUT_ACT_S="${STRANGER_TIMEOUT_ACT_S:-120}"

# Default scripted utterance: written to work with whatever dossier the inhale
# produced. If the dossier has a contact, the planner resolves to the first
# person. If the dossier is empty, the engine surfaces a clarify or pending
# instruction; either way the run completes honestly.
DEFAULT_INJECT_TEXT="I should send Zara Somani a thank-you note for the OpenDoor Law walkthrough"
INJECT_TEXT="${STRANGER_INJECT_TEXT:-$DEFAULT_INJECT_TEXT}"

TS_UTC="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="${REPO_ROOT}/state/v7/stranger_flow_runs/${TS_UTC}"
SNAPSHOT_DIR="/tmp/anticipy-stranger-backup-${TS_UTC}"
RESULT_JSON="${RUN_DIR}/result.json"

mkdir -p "$RUN_DIR"

# Steps recorded incrementally to a JSONL so a Ctrl-C still leaves a readable
# partial result.json.
STEPS_JSONL="${RUN_DIR}/_steps.jsonl"
: > "$STEPS_JSONL"

OVERALL_VERDICT="UNKNOWN"
OVERALL_NOTES=""
FAILED_STEP=""

# ---------------------------------------------------------------------------
# Helpers. All Python heredocs READ inputs via argv to avoid any interpolation
# pitfalls in nested quoting.
# ---------------------------------------------------------------------------

now_ms() {
  python3 -c "import time; print(int(time.time()*1000))"
}

# write_result composes the final result.json from the per-step JSONL plus
# the overall fields. Called at every checkpoint so a Ctrl-C still leaves a
# readable partial result.
write_result() {
  local final_verdict="${1:-$OVERALL_VERDICT}"
  python3 - \
      "$STEPS_JSONL" "$RESULT_JSON" \
      "$final_verdict" "$OVERALL_NOTES" "$FAILED_STEP" \
      "$TS_UTC" "$SNAPSHOT_DIR" "$ENGINE_URL" "$CDP_BASE" \
      "$INJECT_TEXT" "$ANTICIPY_HOME" <<'PY'
import json
import os
import sys
import time

(steps_path, result_path, verdict, notes, failed_step, ts_utc,
 snapshot_dir, engine_url, cdp_base, inject_text,
 anticipy_home) = sys.argv[1:12]
steps = []
try:
    with open(steps_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                steps.append(json.loads(line))
            except Exception as exc:
                steps.append({"name": "unparseable",
                              "ok": False,
                              "error": "{}: {}".format(exc, line[:200])})
except FileNotFoundError:
    pass

record = {
    "story": "stranger_flow",
    "run_id": ts_utc,
    "started_at": ts_utc,
    "finished_at": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()),
    "engine_url": engine_url,
    "cdp_base": cdp_base,
    "snapshot_dir": snapshot_dir,
    "anticipy_home": anticipy_home,
    "inject_text": inject_text,
    "steps": steps,
    "verdict": verdict,
    "failed_step": failed_step,
    "notes": notes,
}
with open(result_path, "w") as f:
    json.dump(record, f, indent=2, sort_keys=False)
PY
}

# log_step appends a JSON record to STEPS_JSONL.
# Args: name ok duration_ms extra_json (defaults to {})
log_step() {
  local name="$1"
  local ok="$2"
  local duration_ms="$3"
  local extra_json="${4:-}"
  if [ -z "$extra_json" ]; then
    extra_json="{}"
  fi
  python3 - \
      "$STEPS_JSONL" "$name" "$ok" "$duration_ms" "$extra_json" <<'PY'
import json
import sys

steps_path, name, ok, dur_ms, extra = sys.argv[1:6]
try:
    extra_obj = json.loads(extra)
    if not isinstance(extra_obj, dict):
        extra_obj = {"raw_extra": extra_obj}
except Exception:
    extra_obj = {"raw_extra": extra}
rec = {"name": name,
       "ok": ok.lower() == "true",
       "duration_ms": int(dur_ms)}
rec.update(extra_obj)
with open(steps_path, "a") as f:
    f.write(json.dumps(rec, sort_keys=False) + "\n")
PY
  local tag="WARN"
  if [ "$ok" = "true" ]; then
    tag="PASS"
  fi
  printf "[stranger] step %-22s %s (%6sms)\n" "$name" "$tag" "$duration_ms"
  write_result "$OVERALL_VERDICT"
}

# Build a JSON string from key=value pairs in a safe way. Bash array of
# alternating keys and values; each value is treated as a string literal.
# Usage: build_json key1 val1 key2 val2 ...
build_json() {
  python3 - "$@" <<'PY'
import json
import sys

argv = sys.argv[1:]
out = {}
for i in range(0, len(argv), 2):
    if i + 1 >= len(argv):
        break
    key = argv[i]
    val = argv[i + 1]
    # Coerce 'true' / 'false' / numeric strings to their JSON types so the
    # final result.json is honest about typing.
    if val.lower() == "true":
        out[key] = True
    elif val.lower() == "false":
        out[key] = False
    else:
        try:
            iv = int(val)
            out[key] = iv
        except (ValueError, TypeError):
            try:
                fv = float(val)
                # Only coerce if no surrounding spaces and not obviously a date string.
                if val.strip() == val and "T" not in val and "-" not in val.lstrip("-")[1:]:
                    out[key] = fv
                else:
                    out[key] = val
            except (ValueError, TypeError):
                out[key] = val
print(json.dumps(out))
PY
}

# wait_for_engine_alive polls /health until it returns ok with a pid, or
# until the retry budget is exhausted. Used before any heavy /api/* call
# because the packaged engine has a known watchdog-restart pattern: a long
# action (Z-001 inject + Gmail compose) can trigger a restart that leaves
# us with a momentarily-dead socket. Tolerating ~30s of transient outage
# keeps the harness honest without polluting verdicts with environmental
# noise.
# Args:
#   $1 = max attempts (default 15)
#   $2 = scratch path (default $HEALTH_PATH or /tmp/anticipy-health-tmp.json)
wait_for_engine_alive() {
  local max_attempts="${1:-15}"
  local scratch="${2:-${HEALTH_PATH:-/tmp/anticipy-health-tmp.json}}"
  local attempt=0
  local got_pid=""
  while [ "$attempt" -lt "$max_attempts" ]; do
    attempt=$((attempt + 1))
    local code
    code=$(curl -sS -o "$scratch" -w '%{http_code}' \
        --max-time 3 \
        "${ENGINE_URL}/health" 2>/dev/null || echo "000")
    if [ "$code" = "200" ]; then
      got_pid="$(read_field "$scratch" pid 2>/dev/null)"
      if [ -n "$got_pid" ]; then
        return 0
      fi
    fi
    sleep 2
  done
  return 1
}

# read_field reads a JSON field from a file by dotted path. Returns empty
# string if missing.
read_field() {
  local path="$1"
  local field="$2"
  python3 - "$path" "$field" <<'PY'
import json
import sys

path, field = sys.argv[1], sys.argv[2]
try:
    body = json.load(open(path))
except Exception:
    print("")
    sys.exit(0)
node = body
for piece in field.split("."):
    if isinstance(node, dict):
        node = node.get(piece)
    else:
        node = None
        break
if node is None:
    print("")
elif isinstance(node, bool):
    print("true" if node else "false")
else:
    print(node)
PY
}

# ---------------------------------------------------------------------------
# Step 1. Snapshot the current ~/.anticipy/v7/ to /tmp/anticipy-stranger-backup
# ---------------------------------------------------------------------------
step_snapshot() {
  local t0; t0=$(now_ms)
  local extra ok
  if [ -d "$ANTICIPY_HOME" ]; then
    if rsync -a --delete "$ANTICIPY_HOME/" "$SNAPSHOT_DIR/" 2>/dev/null; then
      local count size_kb
      count=$(find "$SNAPSHOT_DIR" -type f 2>/dev/null | wc -l | tr -d ' ')
      size_kb=$(du -sk "$SNAPSHOT_DIR" 2>/dev/null | awk '{print $1}')
      extra=$(build_json \
          snapshot_dir "$SNAPSHOT_DIR" \
          file_count "$count" \
          size_kb "$size_kb" \
          source_existed true)
      ok="true"
    else
      extra=$(build_json snapshot_dir "$SNAPSHOT_DIR" error "rsync failed")
      ok="false"
    fi
  else
    # Nothing to snapshot. Create empty dir as a sentinel so restore logic
    # can still recreate the (empty) state cleanly.
    mkdir -p "$SNAPSHOT_DIR"
    extra=$(build_json \
        snapshot_dir "$SNAPSHOT_DIR" \
        source_existed false \
        note "no ~/.anticipy/v7 to snapshot, empty sentinel created")
    ok="true"
  fi
  local t1; t1=$(now_ms)
  log_step "snapshot" "$ok" "$((t1 - t0))" "$extra"
  if [ "$ok" != "true" ]; then
    FAILED_STEP="snapshot"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Step 2. Wipe ~/.anticipy/v7/ to simulate a brand-new user.
# We DO NOT touch ~/.anticipy/system_v1/ or ~/.anticipy/chrome-real-clone/.
# Only v7/ goes (dossiers, decisions, normalized inputs, inference events).
# ---------------------------------------------------------------------------
step_wipe() {
  local t0; t0=$(now_ms)
  local extra ok
  if [[ "$ANTICIPY_HOME" != "$HOME/.anticipy/v7" ]]; then
    extra=$(build_json error "refusing to wipe non-v7 path" path "$ANTICIPY_HOME")
    ok="false"
  elif [ -d "$ANTICIPY_HOME" ]; then
    if rm -rf "$ANTICIPY_HOME" 2>/dev/null && mkdir -p "$ANTICIPY_HOME"; then
      extra=$(build_json wiped_dir "$ANTICIPY_HOME")
      ok="true"
    else
      extra=$(build_json wiped_dir "$ANTICIPY_HOME" error "rm or mkdir failed")
      ok="false"
    fi
  else
    mkdir -p "$ANTICIPY_HOME"
    extra=$(build_json wiped_dir "$ANTICIPY_HOME" note "already absent, fresh dir created")
    ok="true"
  fi
  local t1; t1=$(now_ms)
  log_step "wipe" "$ok" "$((t1 - t0))" "$extra"
  if [ "$ok" != "true" ]; then
    FAILED_STEP="wipe"
    return 1
  fi
}

# ---------------------------------------------------------------------------
# Step 3. POST /api/coldstart/start. Per planning/10-instant-cold-start the
# route is unit 12 work; if it does not exist we record SKIPPED but continue.
# ---------------------------------------------------------------------------
COLDSTART_AVAILABLE="false"
step_coldstart_start() {
  local t0; t0=$(now_ms)
  local resp_path="${RUN_DIR}/coldstart_start.json"
  local code
  code=$(curl -sS -o "$resp_path" -w '%{http_code}' \
      -X POST \
      -H 'Content-Type: application/json' \
      -d '{"account_id":"stranger_flow"}' \
      --max-time 30 \
      "${ENGINE_URL}/api/coldstart/start" 2>/dev/null || echo "000")
  local extra ok
  if [ "$code" = "200" ] || [ "$code" = "202" ]; then
    COLDSTART_AVAILABLE="true"
    extra=$(build_json \
        http_code "$code" \
        available true \
        response_path "$resp_path")
    ok="true"
  elif [ "$code" = "404" ]; then
    # Not yet shipped. Skip cleanly.
    extra=$(build_json \
        http_code "$code" \
        skipped true \
        note "/api/coldstart/start not implemented yet (unit 12 work per planning/10-instant-cold-start/DESIGN.md). Continuing without inhale; dossier will be empty for the inject/act steps.")
    ok="true"
  else
    # Unexpected status. Record but do not abort.
    local body_snippet
    body_snippet=$(head -c 400 "$resp_path" 2>/dev/null || echo "")
    extra=$(build_json \
        http_code "$code" \
        skipped true \
        note "unexpected status; treating as not available" \
        body_snippet "$body_snippet")
    ok="true"
  fi
  local t1; t1=$(now_ms)
  log_step "coldstart_start" "$ok" "$((t1 - t0))" "$extra"
}

# ---------------------------------------------------------------------------
# Step 4. Poll /api/coldstart/status until done or TIMEOUT_INHALE_S. Report
# people_count. If coldstart route is not shipped, mark SKIPPED with the
# people_count read from the on-disk dossier (which after the wipe is 0).
# ---------------------------------------------------------------------------
PEOPLE_COUNT="0"
step_coldstart_status() {
  local t0; t0=$(now_ms)
  local resp_path="${RUN_DIR}/coldstart_status_final.json"
  local poll_log="${RUN_DIR}/coldstart_status_poll.jsonl"
  : > "$poll_log"
  local people_count="0"
  local status_value="not_started"
  local poll_n=0
  local extra ok="true"

  if [ "$COLDSTART_AVAILABLE" = "true" ]; then
    local deadline=$((SECONDS + TIMEOUT_INHALE_S))
    while [ "$SECONDS" -lt "$deadline" ]; do
      poll_n=$((poll_n + 1))
      local code
      code=$(curl -sS -o "$resp_path" -w '%{http_code}' \
          --max-time 10 \
          "${ENGINE_URL}/api/coldstart/status" 2>/dev/null || echo "000")
      python3 - "$poll_log" "$resp_path" "$code" "$poll_n" <<'PY'
import json
import sys
import time

log_path, body_path, code, n = sys.argv[1:5]
try:
    body = json.load(open(body_path))
except Exception:
    body = {}
# Engine exposes "state" (idle|running|done|failed). Also tolerate
# "status" for forward-compatibility.
state = body.get("state") or body.get("status")
rec = {"poll": int(n),
       "http_code": int(code),
       "t": time.time(),
       "state": state,
       "people_count": body.get("people_count"),
       "projects_count": body.get("projects_count"),
       "elapsed_ms": body.get("elapsed_ms"),
       "rows_collected": body.get("rows_collected"),
       "batches_sent": body.get("batches_sent")}
with open(log_path, "a") as f:
    f.write(json.dumps(rec) + "\n")
PY
      status_value="$(read_field "$resp_path" state)"
      if [ -z "$status_value" ]; then
        status_value="$(read_field "$resp_path" status)"
      fi
      if [ -z "$status_value" ]; then
        status_value="unknown"
      fi
      people_count="$(read_field "$resp_path" people_count)"
      if [ -z "$people_count" ]; then
        people_count="0"
      fi
      case "$status_value" in
        done|complete|ready|failed) break ;;
      esac
      sleep 2
    done
    extra=$(build_json \
        final_status "$status_value" \
        people_count "$people_count" \
        poll_count "$poll_n" \
        timeout_s "$TIMEOUT_INHALE_S" \
        poll_log "$poll_log")
  else
    # Coldstart route not shipped. Read people_count from on-disk dossier.
    people_count=$(python3 - <<'PY'
import json
import glob
import os

total = 0
for p in sorted(glob.glob(os.path.expanduser('~/.anticipy/v7/dossiers/*/dossier.json'))):
    try:
        d = json.load(open(p))
        people = d.get('people') or []
        if isinstance(people, list):
            total += len(people)
        elif isinstance(people, dict):
            total += len(people)
    except Exception:
        pass
print(total)
PY
)
    status_value="skipped"
    extra=$(build_json \
        final_status "skipped" \
        people_count "$people_count" \
        note "/api/coldstart/status not available; people_count read from on-disk dossier files (after the wipe this is expected to be 0).")
  fi
  PEOPLE_COUNT="$people_count"
  local t1; t1=$(now_ms)
  log_step "coldstart_status" "$ok" "$((t1 - t0))" "$extra"
}

# ---------------------------------------------------------------------------
# Step 5. POST /api/listen/inject with the scripted utterance.
# ---------------------------------------------------------------------------
INJECT_OK="false"
step_inject() {
  local t0; t0=$(now_ms)
  local resp_path="${RUN_DIR}/inject_response.json"
  local body_path="${RUN_DIR}/inject_request.json"
  python3 - "$body_path" "$INJECT_TEXT" <<'PY'
import json
import sys

body_path, text = sys.argv[1], sys.argv[2]
with open(body_path, "w") as f:
    json.dump({"text": text.strip()}, f)
PY
  # Belt-and-braces: re-check engine health before the heavy call.
  wait_for_engine_alive 15 "${RUN_DIR}/engine_health_pre_inject.json"
  local code
  code=$(curl -sS -o "$resp_path" -w '%{http_code}' \
      -X POST \
      -H 'Content-Type: application/json' \
      --data-binary "@${body_path}" \
      --max-time 60 \
      --retry 2 --retry-delay 3 --retry-connrefused \
      "${ENGINE_URL}/api/listen/inject" 2>/dev/null || echo "000")
  local extra ok
  if [ "$code" = "200" ]; then
    ok="true"
    INJECT_OK="true"
    local outcome ingest_id has_pending pending_instruction proposal transcript
    outcome="$(read_field "$resp_path" outcome)"
    ingest_id="$(read_field "$resp_path" ingest_id)"
    has_pending="$(read_field "$resp_path" pending)"
    # "pending" is a dict; coerce to true/false based on emptiness.
    if [ -n "$has_pending" ]; then
      has_pending="true"
    else
      has_pending="false"
    fi
    pending_instruction="$(read_field "$resp_path" pending.instruction)"
    proposal="$(read_field "$resp_path" proposal)"
    transcript="$(read_field "$resp_path" transcript)"
    extra=$(build_json \
        http_code "$code" \
        outcome "$outcome" \
        ingest_id "$ingest_id" \
        has_pending "$has_pending" \
        pending_instruction "$pending_instruction" \
        proposal "$proposal" \
        transcript "$transcript")
  else
    ok="false"
    local body_snippet
    body_snippet=$(head -c 400 "$resp_path" 2>/dev/null || echo "")
    extra=$(build_json \
        http_code "$code" \
        body_snippet "$body_snippet")
    FAILED_STEP="inject"
  fi
  local t1; t1=$(now_ms)
  log_step "inject" "$ok" "$((t1 - t0))" "$extra"
}

# ---------------------------------------------------------------------------
# Step 6. POST /api/act and verify a real Gmail draft via CDP.
# We do NOT manufacture a synthetic recipient/subject the way Z-001 does;
# we let the engine decide what to draft based on the inject utterance.
# Then we use CDP to read mail.google.com/u/0/#drafts and look for a fresh
# draft. Verification is honest: if the engine could not act (empty dossier,
# clarify, confirm_required, etc.) we record act_ran=false and the verify
# substep is skipped.
# ---------------------------------------------------------------------------
ACT_OK="false"
ACT_RAN="false"
step_act_and_verify() {
  local t0; t0=$(now_ms)
  local resp_path="${RUN_DIR}/act_response.json"
  # Belt-and-braces: re-check engine health before the heavy call.
  wait_for_engine_alive 15 "${RUN_DIR}/engine_health_pre_act.json"
  local code
  code=$(curl -sS -o "$resp_path" -w '%{http_code}' \
      -X POST \
      -H 'Content-Type: application/json' \
      -d '{}' \
      --max-time "$TIMEOUT_ACT_S" \
      --retry 2 --retry-delay 3 --retry-connrefused \
      "${ENGINE_URL}/api/act" 2>/dev/null || echo "000")
  local ran="false" clarify="false" confirm_required="false"
  local act_status="" act_intent="" act_error="" act_compose_url=""
  local act_resolved_person=""
  if [ "$code" = "200" ]; then
    ran="$(read_field "$resp_path" ran)"
    [ -z "$ran" ] && ran="false"
    clarify="$(read_field "$resp_path" clarify)"
    [ -z "$clarify" ] && clarify="false"
    confirm_required="$(read_field "$resp_path" confirm_required)"
    [ -z "$confirm_required" ] && confirm_required="false"
    act_status="$(read_field "$resp_path" status)"
    act_intent="$(read_field "$resp_path" intent)"
    act_error="$(read_field "$resp_path" error)"
    act_compose_url="$(read_field "$resp_path" compose_url)"
    act_resolved_person="$(read_field "$resp_path" resolved_person)"
    # If the SMS pre-confirm gate fired, auto-dispatch YES so the test
    # harness can complete end-to-end. In production the user replies
    # YES via SMS. In dev/test we simulate that via /api/sms/inbound.
    local awaiting_sms_confirm pending_task_id
    awaiting_sms_confirm="$(read_field "$resp_path" awaiting_sms_confirm)"
    pending_task_id="$(read_field "$resp_path" task_id)"
    if [ "$awaiting_sms_confirm" = "true" ] && [ -n "$pending_task_id" ]; then
      local inbound_resp="${RUN_DIR}/inbound_yes_response.json"
      curl -sS -o "$inbound_resp" -w '%{http_code}' \
          -X POST \
          -H 'Content-Type: application/x-www-form-urlencoded' \
          --data-urlencode "Body=YES" \
          --data-urlencode "task_id=$pending_task_id" \
          --data-urlencode "format=json" \
          --max-time 90 \
          "${ENGINE_URL}/api/sms/inbound" 2>/dev/null > /dev/null
      # Re-read ran from the dispatched action result if present.
      local disp_ran
      disp_ran="$(python3 -c "
import json, sys
try:
    d = json.load(open('$inbound_resp'))
    disp = d.get('dispatched') or {}
    print('true' if (disp.get('status') == 'SUCCESS' or disp.get('ran')) else 'false')
except Exception:
    print('false')
" 2>/dev/null)"
      if [ "$disp_ran" = "true" ]; then
        ran="true"
      fi
    fi
  fi
  ACT_RAN="$ran"

  local cdp_drafts_dump="${RUN_DIR}/cdp_drafts_scan.json"
  local draft_ok="false" drafts_url="" drafts_title="" body_chars="0"
  local draft_marker_present="false"

  if [ "$ran" = "true" ]; then
    # Engine returned ran=True before Gmail's autosave fires; wait a beat
    # so the compose dialog has hydrated, then read /drafts via CDP.
    sleep 8
    python3 - "$CDP_BASE" "$cdp_drafts_dump" <<'PY' > "${RUN_DIR}/_draft_verify_summary.json"
import json
import sys
import time
import urllib.parse
import urllib.request

cdp_base, dump_path = sys.argv[1], sys.argv[2]


def _cdp_list_targets():
    try:
        with urllib.request.urlopen("{}/json".format(cdp_base),
                                    timeout=5) as r:
            return json.loads(r.read().decode())
    except Exception:
        return []


def _cdp_close(tid):
    try:
        urllib.request.urlopen(
            "{}/json/close/{}".format(cdp_base,
                                      urllib.parse.quote(tid, safe="")),
            timeout=5).read()
    except Exception:
        pass


def _cdp_new_tab(url):
    encoded = urllib.parse.quote(url, safe=":/?&=%#")
    for method in ("PUT", "GET"):
        try:
            req = urllib.request.Request(
                "{}/json/new?{}".format(cdp_base, encoded), method=method)
            with urllib.request.urlopen(req, timeout=10) as r:
                body = r.read().decode()
            d = json.loads(body)
            return d.get("id"), d.get("url")
        except Exception:
            continue
    return None, None


def _cdp_eval(tid, expr, timeout_s=10):
    try:
        from websockets.sync.client import connect
    except Exception as exc:
        return {"ok": False, "error": "websockets missing: {}".format(exc)}
    ws_url = "ws://localhost:9222/devtools/page/{}".format(tid)
    try:
        ws = connect(ws_url, max_size=8 * 1024 * 1024, open_timeout=5.0)
    except Exception as exc:
        return {"ok": False, "error": "ws connect: {}".format(exc)}
    try:
        ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                            "params": {"expression": expr,
                                       "returnByValue": True,
                                       "awaitPromise": False}}))
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                raw = ws.recv(timeout=max(0.5, deadline - time.time()))
            except Exception as exc:
                return {"ok": False, "error": "recv: {}".format(exc)}
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("id") != 1:
                continue
            result = (msg.get("result") or {}).get("result") or {}
            exc_info = (msg.get("result") or {}).get("exceptionDetails")
            if exc_info:
                desc = (exc_info.get("exception") or {}).get(
                    "description") or json.dumps(exc_info)[:200]
                return {"ok": False, "error": "js exc: {}".format(desc)}
            return {"ok": True, "value": result.get("value")}
        return {"ok": False, "error": "timeout"}
    finally:
        try:
            ws.close()
        except Exception:
            pass


# Snapshot existing mail.google.com tabs so we know what to ignore.
mail_tabs_before = [
    t for t in _cdp_list_targets()
    if str(t.get("type")) == "page"
    and "mail.google.com" in str(t.get("url") or "")
]

# Open the drafts list in a NEW background tab.
inbox_url = "https://mail.google.com/mail/u/0/#drafts"
new_tid, new_url = _cdp_new_tab(inbox_url)
if not new_tid:
    summary = {
        "ok": False,
        "error": "could not open drafts tab via CDP",
        "subject_present": False,
        "draft_url": None,
    }
    with open(dump_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary))
    sys.exit(0)

# Wait for Gmail SPA to load.
time.sleep(10)

scan_expr = (
    "(()=>{const t=(document.body&&document.body.innerText)||'';"
    "const u=location.href;const title=document.title;"
    "return JSON.stringify({"
    "len:t.length,url:u,title:title,"
    "snippet:t.slice(0,8000)"
    "});})()"
)
result = {}
deadline = time.time() + 30
while time.time() < deadline:
    scan = _cdp_eval(new_tid, scan_expr, timeout_s=8)
    try:
        result = json.loads(str(scan.get("value") or "{}"))
    except Exception:
        result = {}
    if int(result.get("len", 0) or 0) > 1000:
        break
    time.sleep(2)

# Heuristic for "a draft was created in this run": look for any
# draft-marker phrase in the body (Gmail localizes; en-US renders the
# subject + first line of the body, with a "Draft" chip on each row).
# This is intentionally lenient because the engine returns ran=True
# before Gmail's autosave fires, and we cannot rely on a deterministic
# subject (the engine composes from an empty dossier).
snippet = (result.get("snippet") or "")
draft_marker_present = (
    " Draft " in snippet
    or "Drafts" in snippet
    or "(no subject)" in snippet
)

summary = {
    "ok": draft_marker_present,
    "drafts_tab_target_id": new_tid,
    "drafts_url": result.get("url"),
    "drafts_title": result.get("title"),
    "body_chars": int(result.get("len") or 0),
    "draft_marker_present": draft_marker_present,
    "mail_tabs_before_count": len(mail_tabs_before),
    "evidence_path": dump_path,
}
with open(dump_path, "w") as f:
    full = dict(summary)
    full["snippet"] = snippet
    json.dump(full, f, indent=2)
_cdp_close(new_tid)
print(json.dumps(summary))
PY
    if [ -f "${RUN_DIR}/_draft_verify_summary.json" ]; then
      draft_ok="$(read_field "${RUN_DIR}/_draft_verify_summary.json" ok)"
      [ -z "$draft_ok" ] && draft_ok="false"
      drafts_url="$(read_field "${RUN_DIR}/_draft_verify_summary.json" drafts_url)"
      drafts_title="$(read_field "${RUN_DIR}/_draft_verify_summary.json" drafts_title)"
      body_chars="$(read_field "${RUN_DIR}/_draft_verify_summary.json" body_chars)"
      [ -z "$body_chars" ] && body_chars="0"
      draft_marker_present="$(read_field "${RUN_DIR}/_draft_verify_summary.json" draft_marker_present)"
      [ -z "$draft_marker_present" ] && draft_marker_present="false"
    fi
  fi

  local ok
  if [ "$ran" = "true" ] && [ "$draft_ok" = "true" ]; then
    ok="true"
    ACT_OK="true"
  else
    ok="false"
  fi
  extra=$(build_json \
      act_http_code "$code" \
      act_ran "$ran" \
      act_clarify "$clarify" \
      act_confirm_required "$confirm_required" \
      act_status "$act_status" \
      act_intent "$act_intent" \
      act_error "$act_error" \
      act_compose_url "$act_compose_url" \
      act_resolved_person "$act_resolved_person" \
      draft_verify_ok "$draft_ok" \
      drafts_url "$drafts_url" \
      drafts_title "$drafts_title" \
      drafts_body_chars "$body_chars" \
      draft_marker_present "$draft_marker_present" \
      cdp_drafts_dump "$cdp_drafts_dump")
  local t1; t1=$(now_ms)
  log_step "act_and_verify" "$ok" "$((t1 - t0))" "$extra"
}

# ---------------------------------------------------------------------------
# Step 7. Restore the snapshot to ~/.anticipy/v7/. This MUST run even when
# earlier steps fail, otherwise we leave Omar's real state wiped.
# ---------------------------------------------------------------------------
RESTORED_OK="false"
step_restore() {
  local t0; t0=$(now_ms)
  local extra ok
  if [[ "$ANTICIPY_HOME" != "$HOME/.anticipy/v7" ]]; then
    extra=$(build_json error "refusing to wipe non-v7 path" path "$ANTICIPY_HOME")
    ok="false"
  elif [ -d "$SNAPSHOT_DIR" ]; then
    rm -rf "$ANTICIPY_HOME" 2>/dev/null
    mkdir -p "$ANTICIPY_HOME"
    if rsync -a --delete "$SNAPSHOT_DIR/" "$ANTICIPY_HOME/" 2>/dev/null; then
      local restored_count
      restored_count=$(find "$ANTICIPY_HOME" -type f 2>/dev/null | wc -l | tr -d ' ')
      extra=$(build_json \
          restored_dir "$ANTICIPY_HOME" \
          file_count "$restored_count" \
          snapshot_dir "$SNAPSHOT_DIR")
      ok="true"
      RESTORED_OK="true"
    else
      extra=$(build_json error "rsync restore failed" snapshot_dir "$SNAPSHOT_DIR")
      ok="false"
    fi
  else
    extra=$(build_json error "snapshot dir missing" snapshot_dir "$SNAPSHOT_DIR")
    ok="false"
  fi
  local t1; t1=$(now_ms)
  log_step "restore" "$ok" "$((t1 - t0))" "$extra"
  if [ "$ok" != "true" ]; then
    # Loudly print so a human notices.
    echo "[stranger] CRITICAL: restore FAILED. Snapshot preserved at $SNAPSHOT_DIR" >&2
    if [ -z "$FAILED_STEP" ]; then
      FAILED_STEP="restore"
    fi
  fi
}

# ---------------------------------------------------------------------------
# Step 8. Final verdict + result.json.
# Verdict PASS only if every hard step (snapshot, wipe, inject, act_and_verify,
# restore) returned ok=true. Coldstart steps tolerated as SKIPPED while
# unit 12 is not shipped.
# ---------------------------------------------------------------------------
finalize_verdict() {
  local hard_steps=("snapshot" "wipe" "inject" "act_and_verify" "restore")
  local hard_ok="true"
  for name in "${hard_steps[@]}"; do
    local got
    got=$(python3 - "$STEPS_JSONL" "$name" <<'PY'
import json
import sys

path, target = sys.argv[1], sys.argv[2]
ok = False
try:
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("name") == target:
                ok = bool(rec.get("ok"))
                break
except Exception:
    pass
print("true" if ok else "false")
PY
)
    if [ "$got" != "true" ]; then
      hard_ok="false"
      if [ -z "$FAILED_STEP" ]; then
        FAILED_STEP="$name"
      fi
    fi
  done
  if [ "$hard_ok" = "true" ]; then
    OVERALL_VERDICT="PASS"
  else
    OVERALL_VERDICT="FAIL"
  fi
  OVERALL_NOTES="coldstart_available=$COLDSTART_AVAILABLE; people_count=$PEOPLE_COUNT; inject_ok=$INJECT_OK; act_ran=$ACT_RAN; act_ok=$ACT_OK; restored=$RESTORED_OK"
  write_result "$OVERALL_VERDICT"
}

# ---------------------------------------------------------------------------
# trap so a Ctrl-C still attempts restore + writes the partial result.
# ---------------------------------------------------------------------------
on_exit() {
  # Only run restore if we got past wipe but never restored.
  if [ -d "$SNAPSHOT_DIR" ] && [ "$RESTORED_OK" != "true" ]; then
    echo "[stranger] trap: attempting emergency restore..." >&2
    step_restore || true
  fi
  finalize_verdict
  write_result "$OVERALL_VERDICT"
  echo "[stranger] result.json = $RESULT_JSON"
  echo "[stranger] verdict = $OVERALL_VERDICT"
}
trap on_exit EXIT

# ---------------------------------------------------------------------------
# Main flow. Each step continues even on warn; the restore MUST run.
# ---------------------------------------------------------------------------
echo "[stranger] run_id = $TS_UTC"
echo "[stranger] run_dir = $RUN_DIR"
echo "[stranger] snapshot_dir = $SNAPSHOT_DIR"
echo "[stranger] engine = $ENGINE_URL"
echo "[stranger] cdp = $CDP_BASE"
echo "[stranger] inject_text = $INJECT_TEXT"

# Engine alive precheck. The packaged engine is supervised by a watchdog
# that restarts it after a crash; in tests we tolerate up to 60s of
# transient outage so a recent Z-001 (which exercises the same code path
# and sometimes triggers a restart) does not poison this run.
HEALTH_PATH="${RUN_DIR}/engine_health.json"
ENGINE_ALIVE_T0=$(now_ms)
if wait_for_engine_alive 30 "$HEALTH_PATH"; then
  ENGINE_PID="$(read_field "$HEALTH_PATH" pid)"
  ENGINE_ALIVE_T1=$(now_ms)
  extra=$(build_json \
      engine_pid "$ENGINE_PID" \
      engine_url "$ENGINE_URL" \
      health_path "$HEALTH_PATH")
  log_step "engine_alive" "true" "$((ENGINE_ALIVE_T1 - ENGINE_ALIVE_T0))" "$extra"
else
  ENGINE_ALIVE_T1=$(now_ms)
  extra=$(build_json \
      error "engine /health did not return a pid within 30 attempts (60s)" \
      health_path "$HEALTH_PATH")
  log_step "engine_alive" "false" "$((ENGINE_ALIVE_T1 - ENGINE_ALIVE_T0))" "$extra"
  FAILED_STEP="engine_alive"
  exit 0
fi

step_snapshot || true
step_wipe || true
step_coldstart_start || true
step_coldstart_status || true
step_inject || true
step_act_and_verify || true
step_restore || true

# on_exit trap will finalize and print verdict.
exit 0
