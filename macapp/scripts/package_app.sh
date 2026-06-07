#!/usr/bin/env bash
# Build, sign, package, and report on the local M1 Mac app artifact.
set -euo pipefail

MACAPP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$MACAPP/.." && pwd)"
LAP="${AUTOPILOT_LAP:-manual}"
APP_NAME=Anticipy
APP="$MACAPP/dist/$APP_NAME.app"
OUT_DIR="${1:-$REPO/.anticipy-data/m1_${LAP}/release}"
ZIP="$OUT_DIR/${APP_NAME}_${LAP}_aarch64.zip"
REPORT="$OUT_DIR/package_report.txt"
INDEX="$OUT_DIR/index.html"

mkdir -p "$OUT_DIR"

bash "$MACAPP/scripts/build_app.sh"

rm -f "$ZIP" "$REPORT" "$INDEX"
ditto -c -k --keepParent "$APP" "$ZIP"

set +e
CODESIGN_OUTPUT="$(codesign --verify --strict --verbose=2 "$APP" 2>&1)"
CODESIGN_CODE=$?
SPCTL_OUTPUT="$(spctl --assess --type execute --verbose=4 "$APP" 2>&1)"
SPCTL_CODE=$?
IDENTITY_OUTPUT="$(security find-identity -v -p codesigning 2>&1)"
set -e

if [ "$CODESIGN_CODE" -eq 0 ]; then
  CODESIGN_STATUS=PASS
else
  CODESIGN_STATUS=FAIL
fi

if [ "$SPCTL_CODE" -eq 0 ]; then
  SPCTL_STATUS=PASS
else
  SPCTL_STATUS=FAIL
fi

SIZE_BYTES="$(stat -f%z "$ZIP")"
SHA256="$(shasum -a 256 "$ZIP" | awk '{print $1}')"
CREATED_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

{
  printf 'Anticipy M1 package report\n'
  printf 'lap=%s\n' "$LAP"
  printf 'created_utc=%s\n' "$CREATED_UTC"
  printf 'app=%s\n' "$APP"
  printf 'artifact=%s\n' "$ZIP"
  printf 'artifact_size_bytes=%s\n' "$SIZE_BYTES"
  printf 'artifact_sha256=%s\n' "$SHA256"
  printf 'codesign_status=%s\n' "$CODESIGN_STATUS"
  printf 'codesign_exit=%s\n' "$CODESIGN_CODE"
  printf 'codesign_output=%s\n' "$CODESIGN_OUTPUT"
  printf 'spctl_status=%s\n' "$SPCTL_STATUS"
  printf 'spctl_exit=%s\n' "$SPCTL_CODE"
  printf 'spctl_output=%s\n' "$SPCTL_OUTPUT"
  printf 'developer_id_gate=%s\n' "Developer ID signing and notarization are required for clean public launch if spctl_status is FAIL."
  printf '\ncode_signing_identities:\n%s\n' "$IDENTITY_OUTPUT"
} > "$REPORT"

cat > "$INDEX" <<EOF
<!doctype html>
<meta charset="utf-8">
<title>Anticipy M1 package ${LAP}</title>
<main style="font: 16px -apple-system, BlinkMacSystemFont, sans-serif; max-width: 760px; margin: 48px auto; line-height: 1.5;">
  <p style="font-size: 12px; letter-spacing: .18em; text-transform: uppercase; color: #8a6a26;">Anticipy M1 local package</p>
  <h1>Download Anticipy for Mac</h1>
  <p>This local page verifies the package path for lap ${LAP}. It is build evidence, not production proof.</p>
  <p><a href="./$(basename "$ZIP")" download>Download Anticipy for Mac</a></p>
  <pre style="white-space: pre-wrap; background: #f4f4f4; padding: 16px; border-radius: 6px;">Artifact: $(basename "$ZIP")
SHA-256: ${SHA256}
Size bytes: ${SIZE_BYTES}
codesign: ${CODESIGN_STATUS}
spctl: ${SPCTL_STATUS}</pre>
</main>
EOF

printf '%s\n' "$REPORT"
printf '%s\n' "$INDEX"

if [ "${ANTICIPY_REQUIRE_GATEKEEPER:-0}" = "1" ] && [ "$SPCTL_STATUS" != "PASS" ]; then
  echo "FAIL: Gatekeeper assessment failed. See $REPORT" >&2
  exit 2
fi
