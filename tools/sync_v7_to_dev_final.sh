#!/usr/bin/env bash
# Sync curated paths from Anticipy-V7 into Anticipy-DEV-FINAL.
#
# Default is --dry-run. Pass --apply to actually rsync.
# Never commits, never pushes. Leaves DEV-FINAL with unstaged changes the
# owner reviews with `git diff` and commits manually.
#
# Manifest: tools/sync_manifest.txt (one path per line, # comments allowed).
# Both repos must be on disk. macOS default rsync + git only, no extras.

set -euo pipefail

SRC_ROOT="/Users/omarebrahim/Developer/Anticipy-V7"
DST_ROOT="/Users/omarebrahim/Developer/Anticipy-DEV-FINAL"
MANIFEST="${SRC_ROOT}/tools/sync_manifest.txt"

MODE="dry-run"
if [ "${1:-}" = "--apply" ]; then
  MODE="apply"
elif [ "${1:-}" = "--dry-run" ] || [ -z "${1:-}" ]; then
  MODE="dry-run"
else
  echo "usage: $0 [--dry-run|--apply]" >&2
  exit 2
fi

if [ ! -d "$SRC_ROOT" ]; then
  echo "fatal: source repo missing: $SRC_ROOT" >&2
  exit 1
fi
if [ ! -d "$DST_ROOT" ]; then
  echo "fatal: destination repo missing: $DST_ROOT" >&2
  exit 1
fi
if [ ! -f "$MANIFEST" ]; then
  echo "fatal: manifest missing: $MANIFEST" >&2
  exit 1
fi

# rsync flags:
#   -a archive (perms, times, recursion)
#   -v verbose
#   --delete so DST mirrors SRC for the subtree we sync (catches removals)
#   --exclude common build noise we never want to copy
RSYNC_FLAGS=(-a -v --delete \
  --exclude '.git/' \
  --exclude '__pycache__/' \
  --exclude '.venv/' \
  --exclude 'node_modules/' \
  --exclude '.next/' \
  --exclude 'dist/' \
  --exclude 'build/' \
  --exclude 'target/' \
  --exclude '.DS_Store')

if [ "$MODE" = "dry-run" ]; then
  RSYNC_FLAGS+=(--dry-run)
fi

echo "=== sync_v7_to_dev_final.sh ==="
echo "mode:   $MODE"
echo "src:    $SRC_ROOT"
echo "dst:    $DST_ROOT"
echo "manifest: $MANIFEST"
echo

# Strip comments + blank lines from manifest, take the first whitespace-delimited token.
PATHS_FILE="$(mktemp -t sync_manifest.XXXXXX)"
trap 'rm -f "$PATHS_FILE"' EXIT
grep -vE '^[[:space:]]*(#|$)' "$MANIFEST" | awk '{print $1}' > "$PATHS_FILE"

if [ ! -s "$PATHS_FILE" ]; then
  echo "fatal: manifest contains zero sync paths" >&2
  exit 1
fi

while IFS= read -r REL_PATH; do
  if [ -z "$REL_PATH" ]; then
    continue
  fi

  SRC_PATH="${SRC_ROOT}/${REL_PATH}"
  DST_PATH="${DST_ROOT}/${REL_PATH}"

  if [ ! -e "$SRC_PATH" ]; then
    echo "skip: source not present: $REL_PATH"
    continue
  fi

  echo "--- syncing: $REL_PATH ---"

  # If syncing a directory, rsync needs trailing slash on src so contents land
  # inside DST_PATH instead of nesting. If a file, sync the file itself.
  if [ -d "$SRC_PATH" ]; then
    if [ "$MODE" = "apply" ]; then
      mkdir -p "$DST_PATH"
    fi
    rsync "${RSYNC_FLAGS[@]}" "${SRC_PATH%/}/" "${DST_PATH%/}/"
  else
    if [ "$MODE" = "apply" ]; then
      mkdir -p "$(dirname "$DST_PATH")"
    fi
    rsync "${RSYNC_FLAGS[@]}" "$SRC_PATH" "$DST_PATH"
  fi
  echo
done < "$PATHS_FILE"

if [ "$MODE" = "apply" ]; then
  echo "=== git status in DEV-FINAL ==="
  git -C "$DST_ROOT" status --short
  echo
  echo "Sync staged on disk. Review with: git -C $DST_ROOT diff"
  echo "Owner commits manually. Script does not commit or push."
else
  echo "=== dry-run complete ==="
  echo "Re-run with --apply to write changes. Nothing was modified."
fi
