#!/bin/sh
# Build the zip the backend serves, FROM the extension source.
#
# This exists because the two drifted and nobody noticed. On 2026-08-11 the
# source was 0.3.9 and backend/pb_public/anticipy-extension.zip — the file
# every user downloads, and the file the setup page tells Omar to re-download
# whenever the browser arm misbehaves — was still 0.3.3. Six releases of
# browser fixes (frame-aware mapping, the parked-tab resume, "what does this
# field already contain", the readonly-picker label, never inventing an
# identity) had been written, tested, committed, and reported as shipped
# while the artifact people actually install contained none of them.
#
# Worse than stale: following the documented repair path DOWNGRADED him and
# silently reintroduced every bug he had just been told was fixed.
#
# So the zip is no longer edited by hand. Run this, commit the result, deploy.
#
#   sh extension/build-zip.sh
#
# It refuses to produce a zip whose manifest does not match the source, which
# is the one failure this script exists to make impossible.
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
OUT="$SRC/../backend/pb_public/anticipy-extension.zip"

# Exactly what the extension needs at runtime — no tests, no store metadata,
# no build scripts. Keep this list in step with what Chrome actually loads.
FILES="manifest.json background.js agent_loop.js page_map.js \
popup.html popup.js onboarding.html onboarding.js icons"

VERSION=$(python3 -c "import json;print(json.load(open('$SRC/manifest.json'))['version'])")

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/pkg"
for f in $FILES; do
  [ -e "$SRC/$f" ] || { echo "build-zip: missing $f" >&2; exit 1; }
  cp -R "$SRC/$f" "$TMP/pkg/"
done

rm -f "$OUT"
(cd "$TMP/pkg" && zip -qr "$OUT" .)

# Prove the artifact matches the source rather than assuming it.
PACKED=$(unzip -p "$OUT" manifest.json | python3 -c "import json,sys;print(json.load(sys.stdin)['version'])")
[ "$PACKED" = "$VERSION" ] || { echo "build-zip: packed $PACKED != source $VERSION" >&2; exit 1; }

echo "built $OUT  version $PACKED  ($(wc -c < "$OUT" | tr -d ' ') bytes)"
echo "now: commit it, then deploy the backend so users actually get it."
