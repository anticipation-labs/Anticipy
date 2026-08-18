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

# FIND WHERE CHROME IS ACTUALLY READING IT, rather than assuming.
#
# This used to hard-code the Default profile and one extension ID. Both were
# wrong for a real install: an unpacked extension's ID is derived from its
# PATH, so loading it from a different folder gives a different ID, and Chrome
# had it in Profile 13 as well as Default. The script then reported "not
# loaded" and quietly did nothing — while he pressed Reload on old code.
#
# So: search every profile for an extension whose name or path says Anticipy,
# and sync into whichever folder Chrome actually points at. Some installs read
# straight from a folder on the Desktop; others read Chrome's own private copy.
# Both work, because we write to the path Chrome itself recorded.
DEST=$(python3 - <<'PY'
import json, os, glob
base = os.path.expanduser("~/Library/Application Support/Google/Chrome")
best = ""
for prefs in glob.glob(os.path.join(base, "*", "Secure Preferences")):
    try:
        d = json.load(open(prefs))
    except Exception:
        continue
    for ext_id, e in (((d.get("extensions") or {}).get("settings")) or {}).items():
        if not isinstance(e, dict):
            continue
        name = ((e.get("manifest") or {}).get("name") or "")
        path = e.get("path") or ""
        if "anticipy" in (name + path).lower() and os.path.isdir(path):
            best = path
            break
    if best:
        break
print(best)
PY
)

if [ -z "$DEST" ]; then
  echo "Anticipy is not loaded as an unpacked extension in any Chrome profile."
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
