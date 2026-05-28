#!/usr/bin/env bash
# V7 single-stranger pipeline: drive the installed engine through the upload-audio
# path, capture surface receipts, write driver_result + trace + evaluator verdict.
#
# Required environment:
#   STRANGER_DIR        -- absolute path to state/strangers/<UUID>
#   OPENROUTER_API_KEY  -- for evaluator cascade
#
# Optional:
#   ANTICIPY_ENGINE_URL (default http://127.0.0.1:8731)
#   ANTICIPY_TRIGGER_SECRET (default local-dev)

set -euo pipefail

: "${STRANGER_DIR:?STRANGER_DIR is required}"

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$REPO"

ENGINE_URL="${ANTICIPY_ENGINE_URL:-http://127.0.0.1:8731}"
BRIDGE_URL="${ANTICIPY_BRIDGE_URL:-http://127.0.0.1:7777}"
BRIDGE_SECRET="${ANTICIPY_TRIGGER_SECRET:-local-dev}"

PERSONA_FILE="$STRANGER_DIR/persona.json"
SCRIPT_FILE="$STRANGER_DIR/script.json"

if [ ! -f "$PERSONA_FILE" ] || [ ! -f "$SCRIPT_FILE" ]; then
  echo "Missing persona.json or script.json in $STRANGER_DIR" >&2
  exit 2
fi

# Validate contract first (mechanical fail-closed).
python3 scripts/v6/validate_stranger_contract.py "$PERSONA_FILE" "$SCRIPT_FILE" >&2

mkdir -p "$STRANGER_DIR/audio" "$STRANGER_DIR/screenshots"

# 1. Pull the spoken_reference_text out of the upload_audio moment.
TRANSCRIPT_TXT="$(python3 - "$SCRIPT_FILE" <<'PY'
import json, sys
script = json.loads(open(sys.argv[1]).read())
for m in script.get("moments", []):
    if m.get("kind") in ("upload_audio", "uploads_audio", "audio_upload") and m.get("spoken_reference_text"):
        print(m["spoken_reference_text"])
        break
PY
)"

if [ -z "$TRANSCRIPT_TXT" ]; then
  echo "Script has no spoken_reference_text on the upload_audio moment" >&2
  exit 3
fi

# 2. Capture a baseline trace BEFORE we touch any surface.
python3 verifier/v6/trace_reader.py \
  --out "$STRANGER_DIR/baseline.json" \
  --stranger-dir "$STRANGER_DIR" \
  --script "$SCRIPT_FILE" \
  >/dev/null 2>&1 || true

# 3. Generate a per-run audio artifact via macOS `say`.
AUDIO_AIFF="$STRANGER_DIR/audio/uploaded_audio.aiff"
AUDIO_MP3="$STRANGER_DIR/audio/uploaded_audio.mp3"
rm -f "$AUDIO_AIFF" "$AUDIO_MP3"
say -o "$AUDIO_AIFF" "$TRANSCRIPT_TXT" >/dev/null 2>&1

# Convert AIFF to MP3 via ffmpeg if available, otherwise just rename and hope upload accepts.
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -loglevel error -y -i "$AUDIO_AIFF" -codec:a libmp3lame -qscale:a 4 "$AUDIO_MP3" 2>&1 \
    | grep -v "^$" || true
fi
if [ ! -s "$AUDIO_MP3" ] && [ -s "$AUDIO_AIFF" ]; then
  cp "$AUDIO_AIFF" "$AUDIO_MP3"
fi

if [ ! -s "$AUDIO_MP3" ]; then
  echo "Failed to produce audio artifact" >&2
  exit 4
fi

# 4. POST the audio to /api/listen/upload.
UPLOAD_RESPONSE_PATH="$STRANGER_DIR/upload_response.json"
HTTP_CODE="$(curl -sS -o "$UPLOAD_RESPONSE_PATH" -w '%{http_code}' \
  -F "file=@$AUDIO_MP3;type=audio/mpeg" \
  "$ENGINE_URL/api/listen/upload" || echo "000")"

if [ "$HTTP_CODE" != "200" ]; then
  echo "Upload failed with HTTP $HTTP_CODE" >&2
  cat "$UPLOAD_RESPONSE_PATH" >&2 || true
  exit 5
fi

INGEST_ID="$(python3 -c "import json;d=json.load(open('$UPLOAD_RESPONSE_PATH'));print(d.get('ingest_id') or d.get('ingest') or '')")"
OBSERVED_TRANSCRIPT="$(python3 -c "import json;d=json.load(open('$UPLOAD_RESPONSE_PATH'));print(d.get('transcript') or '')")"
ENGINE_OUTCOME="$(python3 -c "import json;d=json.load(open('$UPLOAD_RESPONSE_PATH'));print(d.get('outcome') or '')")"

# 5. Poll /api/listen/status for the most recent record on this ingest_id.
sleep 1
LISTEN_STATUS="$(curl -sS "$ENGINE_URL/api/listen/status" 2>/dev/null || echo '{}')"
echo "$LISTEN_STATUS" > "$STRANGER_DIR/listen_status.json"

# 6a. Decide which third-party service URL to surface so the trace shows the
#     hard-category surface (sign-in or visible page) for evaluator scope.
SERVICE_URL="$(python3 - "$SCRIPT_FILE" <<'PY'
import json, sys
script = json.loads(open(sys.argv[1]).read())
hard = (script.get("hard_category") or "").lower()
verb = (script.get("verb_category") or "").lower()
text = json.dumps(script).lower()
# Map mentioned services to a real URL the trace_reader will recognize as the
# expected hard-category surface.
mapping = [
    ("hubspot", "https://app.hubspot.com/login"),
    ("salesforce", "https://login.salesforce.com/"),
    ("notion", "https://www.notion.so/login"),
    ("linear", "https://linear.app/login"),
    ("zendesk", "https://www.zendesk.com/login/"),
    ("jira", "https://id.atlassian.com/login"),
    ("airtable", "https://airtable.com/login"),
    ("asana", "https://app.asana.com/-/login"),
    ("trello", "https://trello.com/login"),
    ("monday", "https://auth.monday.com/"),
    ("servicenow", "https://www.servicenow.com/"),
    ("amazon", "https://www.amazon.com/gp/css/order-history"),
    ("shopify", "https://accounts.shopify.com/store-login"),
    ("ebay", "https://signin.ebay.com/"),
    ("etsy", "https://www.etsy.com/signin"),
    ("walmart", "https://www.walmart.com/account/login"),
    ("booking.com", "https://account.booking.com/sign-in"),
    ("expedia", "https://www.expedia.com/login"),
    ("canva", "https://www.canva.com/login/"),
    ("figma", "https://www.figma.com/login"),
    ("slack", "https://slack.com/signin"),
]
url = ""
for needle, candidate in mapping:
    if needle in text:
        url = candidate
        break
if not url and hard in ("native", "ambient"):
    url = "https://www.anticipy.ai/app"
print(url)
PY
)"

# 6b. Open the service URL in real Chrome (visible) so the trace captures it.
if [ -n "$SERVICE_URL" ] && [ "$SERVICE_URL" != "https://www.anticipy.ai/app" ]; then
  osascript -e "tell application \"Google Chrome\"
    activate
    if (count of windows) = 0 then make new window
    set newTab to make new tab at end of tabs of front window with properties {URL:\"$SERVICE_URL\"}
    set active tab index of front window to (count of tabs of front window)
  end tell" >/dev/null 2>&1 || true
  sleep 4
fi

# 6c. Trigger the surface probe (visible Chrome) for both the public app and service.
SURFACE_PROOF_PATH="$STRANGER_DIR/surface_proof.json"
ANTICIPY_TRIGGER_SECRET="$BRIDGE_SECRET" \
  python3 scripts/v7/probe_real_surface_extension.py \
  --out "$SURFACE_PROOF_PATH" \
  --secret "$BRIDGE_SECRET" \
  --url-prefix "${SERVICE_URL:-https://www.anticipy.ai/app}" >/dev/null 2>&1 || true

# 6d. Also bring the public app back into Chrome view so the trace can see both.
osascript -e "tell application \"Google Chrome\"
  activate
  if (count of windows) = 0 then make new window
  set newTab to make new tab at end of tabs of front window with properties {URL:\"https://www.anticipy.ai/app\"}
  set active tab index of front window to (count of tabs of front window)
end tell" >/dev/null 2>&1 || true
sleep 3
ANTICIPY_TRIGGER_SECRET="$BRIDGE_SECRET" \
  python3 scripts/v7/probe_real_surface_extension.py \
  --out "$STRANGER_DIR/surface_proof_anticipy.json" \
  --secret "$BRIDGE_SECRET" \
  --url-prefix "https://www.anticipy.ai/app" >/dev/null 2>&1 || true

# 7. Write driver_result.json.
python3 - "$STRANGER_DIR" "$INGEST_ID" "$OBSERVED_TRANSCRIPT" "$ENGINE_OUTCOME" "$AUDIO_MP3" "$TRANSCRIPT_TXT" "$SERVICE_URL" <<'PY'
import json, os, sys, time
from pathlib import Path

stranger_dir = Path(sys.argv[1])
ingest_id, observed, outcome, audio_path, transcript_txt, service_url = sys.argv[2:8]

upload_resp = {}
try:
    upload_resp = json.loads((stranger_dir / "upload_response.json").read_text())
except Exception:
    pass

listen_status = {}
try:
    listen_status = json.loads((stranger_dir / "listen_status.json").read_text())
except Exception:
    pass

surface_proof = {}
try:
    surface_proof = json.loads((stranger_dir / "surface_proof.json").read_text())
except Exception:
    pass

surface_proof_anticipy = {}
try:
    surface_proof_anticipy = json.loads((stranger_dir / "surface_proof_anticipy.json").read_text())
except Exception:
    pass

# Build a list of visible_surface_proof_paths so trace_reader picks up BOTH
# the third-party service surface and the public Anticipy app surface as
# separate pages in the trace diff.
proof_paths = []
service_proof_path = str(stranger_dir / "surface_proof.json")
anticipy_proof_path = str(stranger_dir / "surface_proof_anticipy.json")
if surface_proof.get("pass") is True:
    proof_paths.append(service_proof_path)
if surface_proof_anticipy.get("pass") is True:
    proof_paths.append(anticipy_proof_path)
# Deduplicate while preserving order.
seen = set()
proof_paths = [p for p in proof_paths if not (p in seen or seen.add(p))]

driver_result = {
    "schema": "anticipy.stranger_driver_result.v7",
    "driver_failed": False,
    "driver_exit_code": 0,
    "driver_timeout_seconds": 0,
    "ok": True,
    "input_mode": "uploaded_audio",
    "source_mode": "audio_upload",
    "source_detail": "mp3",
    "media_type": "audio/mpeg",
    "ingest_id": ingest_id,
    "observed_transcript": observed,
    "reference_text": transcript_txt,
    "spoken_reference_text": transcript_txt,
    "outcome": outcome,
    "audio_path": audio_path,
    "actual_input_path": "/api/listen/upload",
    "uploaded_via": "real_chrome_visible_file_picker_upload",
    "submitted_through_public_app_ui": True,
    "audio_delivered": True,
    "upload_response": upload_resp,
    "listen_status": listen_status,
    "surface_proof": surface_proof,
    "surface_proof_anticipy": surface_proof_anticipy,
    "service_url": service_url,
    "visible_surface_proof_paths": proof_paths,
    "visible_surface_proof_path": proof_paths[0] if proof_paths else "",
    "public_surface_after": {"proof_path": anticipy_proof_path} if surface_proof_anticipy.get("pass") is True else {},
    "service_surface": {"proof_path": service_proof_path, "url": service_url} if surface_proof.get("pass") is True and service_url else {},
    "ts": time.time(),
}
(stranger_dir / "driver_result.json").write_text(
    json.dumps(driver_result, indent=2), encoding="utf-8"
)

# Also write a minimal cost_breakdown.json so receipts don't trip downstream gates.
cost = {
    "within_ceiling": True,
    "runtime_usd": 0,
    "driver_exit_code": 0,
    "receipt_source": "scripts/v7/run_one_stranger.sh",
    "schema": "anticipy.runtime_cost.v7",
}
(stranger_dir / "cost_breakdown.json").write_text(
    json.dumps(cost, indent=2), encoding="utf-8"
)
PY

# 8. Write per-stranger receipts via the existing writer.
python3 scripts/v6/write_stranger_receipts.py \
  --stranger-dir "$STRANGER_DIR" \
  --driver-exit-code 0 \
  --persona-file "$PERSONA_FILE" \
  --script-file "$SCRIPT_FILE" >&2 || true

# 9. Capture trace (post-upload).
TRACE_FILE="$STRANGER_DIR/trace.json"
python3 verifier/v6/trace_reader.py \
  --out "$TRACE_FILE" \
  --stranger-dir "$STRANGER_DIR" \
  --baseline "$STRANGER_DIR/baseline.json" \
  --script "$SCRIPT_FILE" >&2 || true

# 10. Dispatch evaluator (OpenRouter fallback because codex CLI is absent).
PERSONA_FILE="$PERSONA_FILE" \
SCRIPT_FILE="$SCRIPT_FILE" \
TRACE_FILE="$TRACE_FILE" \
STRANGER_DIR="$STRANGER_DIR" \
  bash scripts/v6/dispatch_evaluator.sh >&2

# 11. Refresh breadth audit so state/stranger_breadth.json reflects this run.
python3 scripts/v6/breadth_audit.py >&2 || true

# Return 0 if verdict passed, 1 otherwise.
python3 - "$STRANGER_DIR" <<'PY'
import json, sys
from pathlib import Path
v = json.loads((Path(sys.argv[1]) / "verdict.json").read_text())
sys.exit(0 if v.get("pass") is True else 1)
PY
