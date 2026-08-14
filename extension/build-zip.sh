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
OUT="$SRC/../backend/pb_public/anticipy-claude-version-extension.zip"
# Every filename ever handed to a customer keeps serving the SAME bytes:
# the codex-era name and the original name are aliases, never stale copies.
LEGACY_OUT="$SRC/../backend/pb_public/anticipy-extension.zip"
LEGACY_OUT2="$SRC/../backend/pb_public/anticipy-codex-version-extension.zip"

# Exactly what the extension needs at runtime — no tests, no store metadata,
# no build scripts. Keep this list in step with what Chrome actually loads.
FILES="manifest.json background.js agent_loop.js page_map.js workflow_state.js \
popup.html popup.js onboarding.html onboarding.js icons"

VERSION=$(python3 -c "import json;print(json.load(open('$SRC/manifest.json'))['version'])")

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/pkg"
for f in $FILES; do
  [ -e "$SRC/$f" ] || { echo "build-zip: missing $f" >&2; exit 1; }
  cp -R "$SRC/$f" "$TMP/pkg/"
done

# A release artifact must be identifiable by its bytes, not by the minute the
# build happened. Normalize archive timestamps and entry order so identical
# source always produces the same SHA-256 (including on a fresh checkout).
find "$TMP/pkg" -exec touch -t 198001010000 {} +

rm -f "$OUT" "$LEGACY_OUT" "$LEGACY_OUT2"
(cd "$TMP/pkg" && find . -type f | LC_ALL=C sort | zip -X -q "$OUT" -@)
cp "$OUT" "$LEGACY_OUT"
cp "$OUT" "$LEGACY_OUT2"

# Prove the artifact matches the source rather than assuming it.
PACKED=$(unzip -p "$OUT" manifest.json | python3 -c "import json,sys;print(json.load(sys.stdin)['version'])")
[ "$PACKED" = "$VERSION" ] || { echo "build-zip: packed $PACKED != source $VERSION" >&2; exit 1; }

# Prove the module graph is complete. On 2026-08-13 the zip shipped WITHOUT
# workflow_state.js — background.js imports it, so the MV3 service worker died
# at load and every fresh install sat forever with no pair code and no error
# anywhere. The version check above passed the whole time: a package can match
# its version and still be missing a limb. So resolve every relative import in
# every packaged .js file and refuse to emit a zip whose imports point at
# files the package does not contain.
python3 - "$TMP/pkg" <<'PYEOF'
import re, sys
from pathlib import Path
pkg = Path(sys.argv[1])
packaged = {p.name for p in pkg.iterdir()}
missing = []
for js in pkg.glob("*.js"):
    for m in re.finditer(r'''(?:^|\n)\s*(?:import[^"']*|export[^"']*from\s*)["'](\./[^"']+)["']''', js.read_text()):
        target = m.group(1)[2:]
        if target not in packaged:
            missing.append(f"{js.name} imports {m.group(1)} but the package has no {target}")
if missing:
    for line in missing:
        print(f"build-zip: BROKEN MODULE GRAPH: {line}", file=sys.stderr)
    sys.exit(1)
PYEOF

echo "built $OUT  version $PACKED  ($(wc -c < "$OUT" | tr -d ' ') bytes)"
echo "legacy aliases $LEGACY_OUT and $LEGACY_OUT2 carry the same bytes"
echo "now: commit it, then deploy the backend so users actually get it."
