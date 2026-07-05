#!/usr/bin/env bash
# Regenerate public/anticipy-chrome-extension.zip from the LIVE extension/ folder.
# The Setup screen (app/phase-zero/PhaseZeroApp.js) serves this zip as "Download the browser helper".
# Run this whenever extension/ changes so a download is never a stale/broken build.
#
# The packaged background.js is TEMPLATED at build time so the downloaded zip is pre-pointed at a
# deployment. The engine URL comes from $ANTICIPY_ENGINE_HTTP and DEFAULTS to the hosted cloud
# engine, so a fresh download connects out of the box. Override to build a localhost helper, e.g.:
#   ANTICIPY_ENGINE_HTTP=http://127.0.0.1:8787 scripts/build_extension_zip.sh
# The live extension/ source is never mutated (we template a staging copy). The URL stays runtime-
# overridable via chrome.storage `anticipy.engine_http` + the popup's Engine URL field regardless.
set -euo pipefail
cd "$(dirname "$0")/.."

ENGINE_HTTP="${ANTICIPY_ENGINE_HTTP:-https://engine-production-eb43.up.railway.app}"
OUT="public/anticipy-chrome-extension.zip"
OUT_ABS="$PWD/$OUT"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# Stage a copy of the extension (same layout the zip ships: top-level extension/ dir), drop the
# dev-only bits the old -x excludes removed, then template DEFAULT_ENGINE_HTTP in the copy only.
cp -R extension "$STAGE/extension"
rm -rf "$STAGE/extension/test" "$STAGE/extension/scripts" "$STAGE/extension/README.md"
find "$STAGE" \( -name '.DS_Store' -o -name '__MACOSX' \) -exec rm -rf {} +

# Replace the DEFAULT_ENGINE_HTTP string literal (keep any trailing fallback comment on the line).
sed -E "s#(^const DEFAULT_ENGINE_HTTP = )\"[^\"]*\";#\1\"${ENGINE_HTTP}\";#" \
  "$STAGE/extension/background.js" > "$STAGE/extension/background.js.tmpl"
mv "$STAGE/extension/background.js.tmpl" "$STAGE/extension/background.js"

# Fail loud if the templating did not take (protects against a future rename of the constant).
grep -q "const DEFAULT_ENGINE_HTTP = \"${ENGINE_HTTP}\";" "$STAGE/extension/background.js" \
  || { echo "ERROR: failed to template DEFAULT_ENGINE_HTTP into background.js" >&2; exit 1; }

rm -f "$OUT_ABS"
( cd "$STAGE" && zip -rq "$OUT_ABS" extension -x '*/.DS_Store' '*/__MACOSX/*' )
echo "built $OUT from live extension/ (engine=${ENGINE_HTTP})"
unzip -l "$OUT"
