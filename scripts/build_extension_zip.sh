#!/usr/bin/env bash
# Regenerate public/anticipy-chrome-extension.zip from the LIVE extension/ folder.
# The Setup screen (app/phase-zero/PhaseZeroApp.js) serves this zip as "Download the browser helper".
# Run this whenever extension/ changes so a download is never a stale/broken build.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="public/anticipy-chrome-extension.zip"
rm -f "$OUT"
zip -rq "$OUT" extension -x 'extension/test/*' 'extension/scripts/*' 'extension/README.md' '*/.DS_Store' '*/__MACOSX/*'
echo "built $OUT from live extension/"
unzip -l "$OUT"
