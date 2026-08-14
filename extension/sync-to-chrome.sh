#!/bin/sh
# Push the repo's extension into the folder Chrome is ACTUALLY reading.
#
# Chrome does not load unpacked extensions from where you think. When an
# extension arrives as a downloaded zip, Chrome copies it into its own profile
# directory and loads THAT copy forever:
#
#   ~/Library/Application Support/Google/Chrome/Default/UnpackedExtensions/…
#
# The Reload button on chrome://extensions re-reads that copy. So editing the
# repo and pressing Reload does nothing at all, quietly — which on 2026-08-05
# had Omar pressing Reload five times on 0.2.6 while 0.2.8 sat in the repo,
# and judging today's work by yesterday's code.
#
# Re-pointing Chrome at the repo folder instead would be the tidier fix, but an
# unpacked extension's ID is derived from its path: a new folder means a new
# ID, which means the pairing with the phone breaks and has to be redone. Not
# worth it. Syncing is one command.
#
# Run:  sh extension/sync-to-chrome.sh     then press Reload in chrome://extensions
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
PROFILE="$HOME/Library/Application Support/Google/Chrome/Default"
ID=niikpkdfnafpdnfgblglkaemmkkhjbba

DEST=$(python3 - "$PROFILE/Secure Preferences" "$ID" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
e = ((d.get("extensions") or {}).get("settings") or {}).get(sys.argv[2])
print((e or {}).get("path", ""))
PY
) || { echo "Could not read Chrome's profile — is Chrome installed for this user?"; exit 1; }

if [ -z "$DEST" ]; then
  echo "Anticipy Claude Version is not loaded as an unpacked extension in the Default profile."
  echo "Load it once via chrome://extensions -> Load unpacked, then re-run this."
  exit 1
fi

echo "repo   : $SRC"
echo "chrome : $DEST"

# Tests, the store bundle and package.json are development-only; shipping them
# is harmless but they are not part of the extension.
rsync -a --delete \
  --exclude 'tests/' --exclude 'store/' --exclude 'node_modules/' \
  --exclude 'package.json' --exclude 'sync-to-chrome.sh' \
  "$SRC"/ "$DEST"/

REPO_V=$(python3 -c "import json;print(json.load(open('$SRC/manifest.json'))['version'])")
LIVE_V=$(python3 -c "import json;print(json.load(open('$DEST/manifest.json'))['version'])")
echo
echo "synced $REPO_V -> Chrome now has $LIVE_V"
[ "$REPO_V" = "$LIVE_V" ] || { echo "MISMATCH — the copy did not take"; exit 1; }
echo "Now press Reload on the Anticipy Claude Version card in chrome://extensions."
