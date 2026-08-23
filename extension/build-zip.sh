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
# The product is now just Anticipy, so all three of these names are historical:
# two carry a product suffix that no longer exists anywhere in the UI, one is
# the original. They are aliases of the same bytes, never stale copies — a URL
# handed to a customer in any era still downloads the current build, which is
# exactly why these paths outlive the name. Rename none of them.
LEGACY_OUT="$SRC/../backend/pb_public/anticipy-extension.zip"
LEGACY_OUT2="$SRC/../backend/pb_public/anticipy-codex-version-extension.zip"

VERSION=$(python3 -c "import json;print(json.load(open('$SRC/manifest.json'))['version'])")

# WHAT GOES IN THE ZIP IS DERIVED, NOT REMEMBERED.
#
# This was a hand-written list, and keeping a list in step with an import graph
# is a job nobody can do reliably: workflow_state.js, config.js, side_trip.js,
# learn.js, and then recipes.js and login_wall.js on 2026-08-19 were all
# imported by shipped modules while missing from the list. The first of those
# shipped — the MV3 worker died at load and every fresh install sat forever
# with no pair code and no error anywhere.
#
# So: start where CHROME starts (the manifest's service worker, its popup, and
# whatever <script> those pages load), follow every relative import to a fixed
# point, and package exactly that. A new module is packaged the moment
# something reaches it. The graph check further down stays as the belt: it now
# proves the derivation, rather than being the only thing standing between an
# edit and a dead install.
# The script goes to a file rather than straight into $( <<heredoc ): the bash
# that ships with macOS (3.2) scans a command substitution for balanced quotes
# INCLUDING the heredoc body, so a python regex containing ["'] makes the whole
# file a syntax error at a line nowhere near the cause.
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/derive.py" <<'PYEOF'
import json, re, sys
from pathlib import Path

src = Path(sys.argv[1])
manifest = json.loads((src / "manifest.json").read_text())

# Chrome's own entry points, read off the manifest so this cannot disagree
# with what the browser will actually load.
pages, scripts = [], []
worker = (manifest.get("background") or {}).get("service_worker")
if worker:
    scripts.append(worker)
popup = (manifest.get("action") or {}).get("default_popup")
if popup:
    pages.append(popup)
# Not referenced by the manifest: the first-run page background.js opens with
# chrome.runtime.getURL. A file only reachable through getURL cannot be found
# by following imports, so it is named here — and, being HTML, its own
# <script> tags are still followed below.
pages.append("onboarding.html")

SCRIPT_SRC = re.compile(r'''<script[^>]+src=["']([^"']+)["']''')
for page in pages:
    for hit in SCRIPT_SRC.finditer((src / page).read_text()):
        scripts.append(hit.group(1).lstrip("./"))

IMPORT = re.compile(r'''(?:^|\n)\s*(?:import[^"']*|export[^"']*from\s*)["']\./([^"']+)["']''')
# An INJECTED file is an entry point too, and it is invisible to the import
# graph: page_map.js is never imported, it is pushed into the page with
# chrome.scripting.executeScript({ files: [...] }). Deriving from imports alone
# dropped it — which would ship a package whose page mapping fails at the first
# step, the same shape of dead install this whole check exists to prevent.
INJECTED = re.compile(r'''files:\s*\[([^\]]*)\]''')
NAME = re.compile(r'''["']([^"']+)["']''')
out, queue, seen = [], list(scripts), set()
while queue:
    name = queue.pop(0)
    if name in seen:
        continue
    seen.add(name)
    path = src / name
    if not path.is_file():
        sys.exit(f"build-zip: {name} is referenced but not on disk")
    out.append(name)
    text = path.read_text()
    for hit in IMPORT.finditer(text):
        queue.append(hit.group(1))
    for hit in INJECTED.finditer(text):
        for ref in NAME.findall(hit.group(1)):
            queue.append(ref.lstrip("./"))

# The static half: everything Chrome loads that is not code.
print(" ".join(["manifest.json", *pages, *out, "icons"]))
PYEOF
FILES=$(python3 "$TMP/derive.py" "$SRC")
[ -n "$FILES" ] || { echo "build-zip: could not work out what to package" >&2; exit 1; }

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
