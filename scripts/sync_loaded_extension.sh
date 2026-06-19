#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${ANTICIPY_EXTENSION_SOURCE:-$ROOT/extension}"
TARGET="${ANTICIPY_LOADED_EXTENSION:-$HOME/Desktop/★ LOAD THIS — Anticipy extension (Jun14)}"
ENGINE_URL="${ANTICIPY_ENGINE_URL:-http://127.0.0.1:8787}"
ZIP_OUT="${ANTICIPY_EXTENSION_ZIP:-$HOME/Desktop/anticipy-hands-extension-dev.zip}"
CHROME_BIN="${ANTICIPY_CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
BACKUP=1

if [[ "${1:-}" == "--no-backup" ]]; then
  BACKUP=0
fi

if [[ ! -f "$SOURCE/manifest.json" ]]; then
  echo "source extension missing manifest: $SOURCE" >&2
  exit 1
fi

if [[ ! -d "$TARGET" ]]; then
  echo "loaded extension folder missing: $TARGET" >&2
  exit 1
fi

if [[ "$BACKUP" == "1" ]]; then
  stamp="$(date +%Y%m%dT%H%M%S)"
  backup="$TARGET.backup-$stamp"
  ditto "$TARGET" "$backup"
  echo "backup=$backup"
fi

rsync -a --delete "$SOURCE/" "$TARGET/"
echo "synced=$TARGET"

node "$TARGET/test/connect_test.js" "$ENGINE_URL"

reload_json="$(curl -fsS -X POST "$ENGINE_URL/ws/reload")"
echo "reload=$reload_json"
sleep 2

state_json="$(curl -fsS "$ENGINE_URL/ws/state")"
echo "state=$state_json"
if ! /usr/bin/python3 - "$state_json" <<'PY'
import json, sys
data = json.loads(sys.argv[1])
raise SystemExit(0 if data.get("connected") is True else 1)
PY
then
  echo "extension did not reconnect after reload" >&2
  exit 1
fi

rm -f "$ZIP_OUT"
(cd "$TARGET" && zip -qr "$ZIP_OUT" .)
echo "zip=$ZIP_OUT"

if [[ -x "$CHROME_BIN" ]]; then
  parent="$(dirname "$TARGET")"
  base="$(basename "$TARGET")"
  crx="$parent/$base.crx"
  pem="$parent/$base.pem"
  if [[ -f "$pem" ]]; then
    "$CHROME_BIN" --pack-extension="$TARGET" --pack-extension-key="$pem" >/tmp/anticipy-extension-pack.log 2>&1 || {
      cat /tmp/anticipy-extension-pack.log >&2
      exit 1
    }
  else
    "$CHROME_BIN" --pack-extension="$TARGET" >/tmp/anticipy-extension-pack.log 2>&1 || {
      cat /tmp/anticipy-extension-pack.log >&2
      exit 1
    }
  fi
  echo "crx=$crx"
  echo "pem=$pem"
else
  echo "chrome_pack=skipped; Chrome binary not found at $CHROME_BIN"
fi
