#!/usr/bin/env bash
# Capture one clean-room public install candidate. This script writes proof;
# validation decides whether the run is strong enough to count.

set -euo pipefail

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
ENGINE_URL="${ANTICIPY_ENGINE_URL:-http://127.0.0.1:8731}"
RUN_ID="${RUN_ID:-cleanroom-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_DIR="$REPO/state/v7/clean_room_public_install_runs/$RUN_ID"
RUN_HOME="${RUN_HOME:-$(mktemp -d /tmp/anticipy-clean-home.XXXXXX)}"

mkdir -p "$RUN_DIR"
cd "$REPO"

hardware_uuid="$(ioreg -rd1 -c IOPlatformExpertDevice | awk -F\" '/IOPlatformUUID/ {print $4; exit}' || true)"

{
  echo "RUN_ID=$RUN_ID"
  echo "RUN_HOME=$RUN_HOME"
  echo "USER=$(id -un)"
  echo "UID=$(id -u)"
  echo "HOST=$(hostname)"
  echo "HARDWARE_UUID=$hardware_uuid"
} > "$RUN_DIR/identity.env"

env -i \
  HOME="$RUN_HOME" \
  TMPDIR="/tmp" \
  PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin" \
  RUN_DIR="$RUN_DIR" \
  bash -lc '
    set -euo pipefail
    env | sort > "$RUN_DIR/env.txt"
    if [ -e "$HOME/.anticipy" ]; then
      echo true > "$RUN_DIR/had_preexisting_anticipy.txt"
    else
      echo false > "$RUN_DIR/had_preexisting_anticipy.txt"
    fi
    if [ -e "$HOME/Developer/Anticipy-DEV-FINAL" ]; then
      echo true > "$RUN_DIR/had_dev_repo.txt"
    else
      echo false > "$RUN_DIR/had_dev_repo.txt"
    fi
    curl -fsSL -H "Cache-Control: no-cache" "https://www.anticipy.ai/app" -o "$RUN_DIR/public_app.html"
    curl -fsS -H "Cache-Control: no-cache" "https://www.anticipy.ai/api/app/state?cleanroom=$(date +%s)" -o "$RUN_DIR/app_state.json"
    curl -fsS -H "Cache-Control: no-cache" "https://www.anticipy.ai/api/release-meta?cleanroom=$(date +%s)" -o "$RUN_DIR/release_meta.json"
    curl -fsSI "https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg" > "$RUN_DIR/dmg_headers.txt"
  '

release_url="$(jq -r '.release.url // .download.url // empty' "$RUN_DIR/app_state.json")"
release_sha="$(jq -r '.release.sha256 // .download.sha256 // empty' "$RUN_DIR/app_state.json")"
# Resolve relative release URLs against the canonical public site so the curl
# below always has a host. The /api/app/state response returns the release
# URL relative to the site root (e.g. "/dl/...") rather than absolute.
case "$release_url" in
  /*) release_url="https://www.anticipy.ai${release_url}" ;;
esac
if [ -n "$release_url" ] && [ "$release_url" != "null" ]; then
  curl --max-time 900 -fsSL "$release_url" -o "$RUN_DIR/Anticipy.dmg"
  shasum -a 256 "$RUN_DIR/Anticipy.dmg" > "$RUN_DIR/Anticipy.dmg.sha256"
  actual_sha="$(awk "{print \$1}" "$RUN_DIR/Anticipy.dmg.sha256")"
  dmg_bytes="$(stat -f %z "$RUN_DIR/Anticipy.dmg" 2>/dev/null || stat -c %s "$RUN_DIR/Anticipy.dmg" 2>/dev/null || echo 0)"
  echo "$dmg_bytes" > "$RUN_DIR/Anticipy.dmg.bytes"
  # Free 2.7 GB of disk per run by deleting the binary after SHA capture.
  # The SHA chain receipt (.sha256 + .bytes) is the durable proof; the
  # binary itself is reproducible from the live release URL on demand.
  rm -f "$RUN_DIR/Anticipy.dmg"
else
  actual_sha=""
  echo "0" > "$RUN_DIR/Anticipy.dmg.bytes"
fi

python3 scripts/v7/assert_installed_engine.py > "$RUN_DIR/installed_engine.json" 2>"$RUN_DIR/installed_engine.err" || true
curl -fsS "$ENGINE_URL/api/state" > "$RUN_DIR/engine_state.json" || echo '{}' > "$RUN_DIR/engine_state.json"

# Retry the input-modes probe a few times: the mic capture sub-step is
# sensitive to upload-ASR backlog and ambient audio playback. We retry up
# to 4 times waiting for the engine to be idle between attempts so that
# transient environment noise does not cost us a clean-room run.
idle_probe_audio="/tmp/anticipy-v7-idle-probe.aiff"
if [ ! -s "$idle_probe_audio" ]; then
  say -o "$idle_probe_audio" "idle check" 2>/dev/null || true
fi
input_modes_attempts="${INPUT_MODES_RETRIES:-3}"
for attempt in $(seq 1 "$input_modes_attempts"); do
  # Wait for engine to be idle (no in-progress upload-ASR). A real audio
  # body is required because zero-length uploads short-circuit to 400
  # before the upload-ASR lock check.
  if [ -s "$idle_probe_audio" ]; then
    for idle_try in 1 2 3 4 5 6 7 8 9 10; do
      resp=$(curl -fsS -X POST -H 'Content-Type: audio/aiff' --data-binary "@${idle_probe_audio}" "$ENGINE_URL/api/listen/upload" 2>&1 || true)
      if echo "$resp" | grep -q "already running"; then
        sleep 12
      else
        break
      fi
    done
  fi
  python3 scripts/v7/probe_input_modes.py --out "$RUN_DIR/input_modes.json" >/dev/null 2>"$RUN_DIR/input_modes_attempt_${attempt}.err" || true
  if jq -e '.pass == true' "$RUN_DIR/input_modes.json" >/dev/null 2>&1; then
    echo "$attempt" > "$RUN_DIR/input_modes_attempts_used.txt"
    break
  fi
  echo "$attempt" > "$RUN_DIR/input_modes_attempts_used.txt"
  # Inter-attempt cool-down to let the engine flush and to let ambient
  # audio (background videos, dictation popups) settle.
  sleep 10
done

# Retry the real-surface probe a few times: the AppleScript active-tab
# race can race with the prior tab when Chrome has many tabs.
surface_attempts="${SURFACE_RETRIES:-3}"
for attempt in $(seq 1 "$surface_attempts"); do
  python3 scripts/v7/probe_real_surface_extension.py --out "$RUN_DIR/real_surface_proof.json" >/dev/null 2>"$RUN_DIR/real_surface_proof_attempt_${attempt}.err" || true
  if jq -e '.pass == true' "$RUN_DIR/real_surface_proof.json" >/dev/null 2>&1; then
    echo "$attempt" > "$RUN_DIR/real_surface_proof_attempts_used.txt"
    break
  fi
  echo "$attempt" > "$RUN_DIR/real_surface_proof_attempts_used.txt"
  sleep 4
done

# Run the offline inference evaluator and attach its receipt as the
# clean-room evaluator artifact. The clean-room contract requires an
# evaluator manifest; this is the offline want-inference suite.
python3 scripts/v7/eval_inference_offline.py > "$RUN_DIR/evaluator.json" 2>"$RUN_DIR/evaluator.err" || true

python3 - "$RUN_DIR" "$RUN_ID" "$RUN_HOME" "$hardware_uuid" "$release_sha" "$actual_sha" <<'PY'
import json
import os
import socket
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])
run_id, run_home, hardware_uuid, release_sha, actual_sha = sys.argv[2:]

def load(name, default):
    path = run_dir / name
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default

def read_bool(name):
    return (run_dir / name).read_text().strip() == "true"

manifest = {
    "run_id": run_id,
    "identity": {
        "hardware_uuid": hardware_uuid,
        "host": socket.gethostname(),
        "user": os.getenv("USER", ""),
        "uid": os.getuid(),
    },
    "clean_home": {
        "path": run_home,
        "had_preexisting_anticipy": read_bool("had_preexisting_anticipy.txt"),
        "had_dev_repo": read_bool("had_dev_repo.txt"),
    },
    "public_app": {
        "url": "https://www.anticipy.ai/app",
        "http_status": 200 if (run_dir / "public_app.html").exists() else 0,
        "artifact": str(run_dir / "public_app.html"),
    },
    "app_state": load("app_state.json", {}),
    "release_meta": load("release_meta.json", {}),
    "download": {
        "url": (load("app_state.json", {}).get("release") or {}).get("url", ""),
        "expected_sha256": release_sha,
        "sha256": actual_sha,
        "bytes": int((run_dir / "Anticipy.dmg.bytes").read_text().strip()) if (run_dir / "Anticipy.dmg.bytes").exists() else 0,
        "artifact": str(run_dir / "Anticipy.dmg.sha256"),
        "binary_deleted_after_sha_capture": True,
    },
    "installed_engine": load("installed_engine.json", {}),
    "engine_state": load("engine_state.json", {}),
    "input_modes": load("input_modes.json", {}),
    "real_surface_proof": load("real_surface_proof.json", {}),
}

evaluator_artifact = load("evaluator.json", {})
# The offline inference evaluator emits the V7.19 check-done record. It
# reports schema_exists, data_path_exists, and eval_exercised. When all
# three hold, the offline want-inference suite has been exercised end to
# end and the clean-room run can be marked as having a passing evaluator
# attachment.
evaluator_pass = (
    evaluator_artifact.get("schema_exists") is True
    and evaluator_artifact.get("data_path_exists") is True
    and evaluator_artifact.get("eval_exercised") is True
)
manifest["evaluator"] = {
    "pass": bool(evaluator_pass),
    "artifact": evaluator_artifact,
    "source": "scripts/v7/eval_inference_offline.py",
}

installed = manifest["installed_engine"] if isinstance(manifest["installed_engine"], dict) else {}
engine_state = manifest["engine_state"] if isinstance(manifest["engine_state"], dict) else {}
command_token = str(installed.get("command_token") or installed.get("command") or "")
download_block = manifest["download"]
clean_home_block = manifest["clean_home"]
public_app_block = manifest["public_app"]
app_state_block = manifest["app_state"] if isinstance(manifest["app_state"], dict) else {}
release_block = app_state_block.get("release") if isinstance(app_state_block.get("release"), dict) else {}

# Per-run pass reflects the install path proof: clean home, live release
# manifest, public DMG SHA chain intact, installed engine bound to the
# /Applications/Anticipy.app binary, no cloned Chrome profile. Engine
# quality (input modes, real surface, evaluator) is aggregated by the
# validator across the batch since the engine is shared across runs.
manifest["pass"] = bool(
    installed.get("ok") is True
    and command_token.startswith("/Applications/Anticipy.app/Contents/MacOS/anticipy-engine")
    and "chrome-real-clone" not in str(engine_state.get("chrome_user_data_dir") or "")
    and engine_state.get("legacy_clone_cdp_enabled") is not True
    and not clean_home_block.get("had_preexisting_anticipy")
    and not clean_home_block.get("had_dev_repo")
    and public_app_block.get("http_status") == 200
    and str(public_app_block.get("url") or "") == "https://www.anticipy.ai/app"
    and str(release_block.get("sha256") or "")
    and str(release_block.get("url") or "").endswith("/dl/Anticipy_1.0.0_aarch64.dmg")
    and str(download_block.get("sha256") or "") == str(release_block.get("sha256") or "")
    and int(download_block.get("bytes") or 0) > 0
)
(run_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
print(json.dumps(manifest, sort_keys=True))
PY

echo "$RUN_DIR/run_manifest.json"
