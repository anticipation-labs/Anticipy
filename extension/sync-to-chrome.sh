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
CHROME_DIR="$HOME/Library/Application Support/Google/Chrome"

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
#
# Still true on Chrome 151 (verified on this Mac, 151.0.7922.138): the records
# live in each profile's `Secure Preferences` under extensions.settings — the
# plain `Preferences` file carries none of them. Three things this now handles
# that it did not:
#
#   * A RELATIVE path. Chrome stores its own private copies relative to the
#     profile directory, and os.path.isdir() on a bare "abcdef/1.0_0" is False,
#     so those installs reported "not loaded" and were silently skipped.
#   * MORE THAN ONE profile. It used to stop at the first hit; this Mac has
#     eight profiles, so "synced" could easily mean "synced the one you don't
#     use". Every match is written.
#   * Chrome reading the REPO folder itself, which is what Load unpacked does
#     when you point it here. There is nothing to copy in that case, and
#     rsyncing a folder onto itself is a bad way to find that out.
FOUND=$(python3 - "$CHROME_DIR" <<'PY'
import json, os, sys, glob
base = sys.argv[1]
names = {}
try:
    state = json.load(open(os.path.join(base, "Local State")))
    for key, info in ((state.get("profile") or {}).get("info_cache") or {}).items():
        names[key] = (info or {}).get("name") or ""
except Exception:
    pass
seen = set()
for prefs in sorted(glob.glob(os.path.join(base, "*", "Secure Preferences"))):
    profile_dir = os.path.dirname(prefs)
    profile = os.path.basename(profile_dir)
    try:
        d = json.load(open(prefs))
    except Exception:
        continue
    for ext_id, e in (((d.get("extensions") or {}).get("settings")) or {}).items():
        if not isinstance(e, dict):
            continue
        name = ((e.get("manifest") or {}).get("name") or "")
        path = e.get("path") or ""
        # A removed unpacked extension leaves a path-only tombstone in Secure
        # Preferences. It does not appear on chrome://extensions and Chrome
        # cannot run it. Require the stored manifest, which a real card has.
        if "anticipy" not in name.lower():
            continue
        # Chrome writes an absolute path for a folder you picked yourself and a
        # profile-relative one for a copy it made. Resolve both.
        full = path if os.path.isabs(path) else os.path.join(profile_dir, path)
        if not os.path.isfile(os.path.join(full, "manifest.json")):
            continue
        if full in seen:
            continue
        seen.add(full)
        label = f"{profile} ({names.get(profile)})" if names.get(profile) else profile
        status = "disabled" if e.get("disable_reasons") else "enabled"
        print("\t".join([full, label, ext_id, status]))
PY
)

if [ -z "$FOUND" ]; then
  cat <<EOF
Anticipy is not loaded in any Chrome profile on this Mac.

Chrome's stable channel blocks command-line extension loading. Use Chrome's
own Load unpacked screen once:

  1. Open Chrome, go to    chrome://extensions
  2. Turn ON "Developer mode"  — the switch at the TOP RIGHT of that page
  3. Click "Load unpacked"     — the button at the TOP LEFT
  4. Choose this exact folder:

       $SRC

     (In the file picker press Shift-Cmd-G, paste that path, Enter, then
     click "Select". Pick the folder itself — do not open it first.)
  5. A card appears: "Anticipy". A setup tab opens with a
     6-digit code; type that code into Anticipy on your iPhone.

If you use more than one Chrome profile, do it in the profile you actually
browse in — the avatar at the top right is the one you are in now.

Then re-run this script each time the repo changes:  sh extension/sync-to-chrome.sh
EOF
  exit 1
fi

echo "repo   : $SRC"

TAB=$(printf '\t')
REPO_V=$(python3 -c "import json;print(json.load(open('$SRC/manifest.json'))['version'])")

# A temp file, not a pipe: a `while` on the right of a pipe runs in a subshell,
# where an `exit 1` on a failed copy exits nothing but the subshell and the
# script goes on to print its cheerful closing line.
LIST=$(mktemp)
trap 'rm -f "$LIST"' EXIT
printf '%s\n' "$FOUND" > "$LIST"

while IFS="$TAB" read -r DEST LABEL EXT_ID STATUS; do
  [ -n "$DEST" ] || continue
  echo "chrome : $DEST"
  echo "         profile $LABEL, extension id $EXT_ID, $STATUS"
  if [ "$DEST" = "$SRC" ]; then
    # The good case, and the one that used to end in rsync copying a folder
    # over itself: Chrome is reading this checkout directly, so the code on
    # disk IS the code it will load. Nothing to copy.
    echo "         Chrome reads this repo folder directly — nothing to copy."
    echo "         Press Reload on that card in chrome://extensions to pick up your edits."
    continue
  fi
  # Tests, the store bundle and package.json are development-only; shipping
  # them is harmless but they are not part of the extension. Excluded files are
  # also protected from --delete, which is what keeps this safe to run against
  # a folder that is not a pristine copy.
  rsync -a --delete \
    --exclude 'tests/' --exclude 'store/' --exclude 'node_modules/' \
    --exclude 'package.json' --exclude 'sync-to-chrome.sh' \
    "$SRC"/ "$DEST"/
  LIVE_V=$(python3 -c "import json;print(json.load(open('$DEST/manifest.json'))['version'])")
  if [ "$REPO_V" = "$LIVE_V" ]; then
    echo "         synced $REPO_V"
  else
    echo "         MISMATCH — copied $REPO_V but that folder still reads $LIVE_V."
    echo "         Something else owns that folder; load unpacked from $SRC instead."
    exit 1
  fi
done < "$LIST"

echo
echo "Now press Reload on the Anticipy card in chrome://extensions (in that"
echo "profile), then check the version on the card reads $REPO_V. An unpacked"
echo "extension never auto-updates, and a stale worker graph is the single most"
echo "common reason the browser arm looks dead."
