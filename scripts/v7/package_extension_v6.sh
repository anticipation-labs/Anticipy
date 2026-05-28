#!/usr/bin/env bash
set -euo pipefail

REPO="${REPO:-$(git rev-parse --show-toplevel)}"
cd "$REPO"

BASE_ZIP="public/anticipy-extension-v6.zip"
ALIAS_ZIP="public/anticipy-extension.zip"

if [ ! -f "$BASE_ZIP" ]; then
  echo "[package-extension-v6] missing $BASE_ZIP" >&2
  exit 1
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

unzip -q "$BASE_ZIP" -d "$tmp"
root="$tmp/anticipy-v6"
if [ ! -d "$root/DAEMON-INSTALLER/engine" ]; then
  echo "[package-extension-v6] unexpected zip layout: missing DAEMON-INSTALLER/engine" >&2
  exit 1
fi

rm -rf "$root/EXTENSION-LOAD-THIS-IN-CHROME"
mkdir -p "$root/EXTENSION-LOAD-THIS-IN-CHROME"
cp -R extension_v4/. "$root/EXTENSION-LOAD-THIS-IN-CHROME/"

rm -rf "$root/DAEMON-INSTALLER/native_host"
mkdir -p "$root/DAEMON-INSTALLER/native_host"
rsync -a \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  native_host/. "$root/DAEMON-INSTALLER/native_host/"

rm -rf "$root/DAEMON-INSTALLER/engine"
mkdir -p "$root/DAEMON-INSTALLER/engine"
rsync -a \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude '*.pyc' \
  engine/app "$root/DAEMON-INSTALLER/engine/"
cp engine/requirements.txt "$root/DAEMON-INSTALLER/engine/requirements.txt"

cp installer/install.sh "$root/DAEMON-INSTALLER/install.sh"
cp installer/install.command "$root/DAEMON-INSTALLER/install.command"
chmod +x "$root/DAEMON-INSTALLER/install.sh" "$root/DAEMON-INSTALLER/install.command"

rm -f "$BASE_ZIP" "$ALIAS_ZIP"
(
  cd "$tmp"
  zip -qr -X "$REPO/$BASE_ZIP" anticipy-v6
)
cp "$BASE_ZIP" "$ALIAS_ZIP"

unzip -t "$BASE_ZIP" >/dev/null
unzip -t "$ALIAS_ZIP" >/dev/null

echo "[package-extension-v6] wrote $BASE_ZIP"
echo "[package-extension-v6] wrote $ALIAS_ZIP"
