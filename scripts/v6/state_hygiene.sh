#!/usr/bin/env bash
# Prepare a stranger run by clearing V6 working state and snapshotting surfaces.

set -euo pipefail

if GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  REPO="$GIT_ROOT"
else
  REPO="${REPO:-$(pwd -P)}"
fi
UUID="${1:-$(date -u +%Y%m%dT%H%M%SZ)}"
if [[ -n "${STRANGER_DIR:-}" ]]; then
  if [[ "$STRANGER_DIR" = /* ]]; then
    STRANGER_BASELINE_DIR="$STRANGER_DIR"
  else
    STRANGER_BASELINE_DIR="$REPO/$STRANGER_DIR"
  fi
else
  STRANGER_BASELINE_DIR="$REPO/state/strangers/$UUID"
fi
OUT="$STRANGER_BASELINE_DIR/baseline.json"
mkdir -p "$STRANGER_BASELINE_DIR"

python3 - <<'PY' || true
import json
import os
import urllib.parse
import urllib.request

port = int(os.environ.get("ANTICIPY_CDP_PORT", "9222"))

try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as resp:
        targets = json.loads(resp.read() or b"[]")
except Exception:
    targets = []

for target in targets:
    haystack = f"{target.get('url') or ''}\n{target.get('title') or ''}".lower()
    if target.get("type") == "page" and "anticipy" in haystack:
        target_id = urllib.parse.quote(str(target.get("id") or ""), safe="")
        if target_id:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/json/close/{target_id}", timeout=2).read()
            except Exception:
                pass
PY

pkill -f "$REPO.*[a]nticipy.*engine" >/dev/null 2>&1 || true
pkill -f "$REPO.*engine.*[a]nticipy" >/dev/null 2>&1 || true
rm -rf "$HOME/.anticipy/working"
mkdir -p "$HOME/.anticipy/working"
mkdir -p "$HOME/.anticipy/declined_actions"
rm -f "$HOME/.anticipy/declined_actions/latest.jsonl"

if [ -f "$REPO/scripts/v6/run_with_timeout.py" ]; then
  python3 "$REPO/scripts/v6/run_with_timeout.py" "${STATE_HYGIENE_TRACE_TIMEOUT_SECONDS:-45}" \
    python3 "$REPO/verifier/v6/trace_reader.py" --out "$OUT" --stranger-dir "$STRANGER_BASELINE_DIR" \
    >/dev/null 2>&1 || true
else
  python3 "$REPO/verifier/v6/trace_reader.py" --out "$OUT" --stranger-dir "$STRANGER_BASELINE_DIR" \
    >/dev/null 2>&1 || true
fi
echo "$OUT"
