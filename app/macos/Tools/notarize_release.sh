#!/bin/sh
# Notarize an already Developer-ID-signed archive without exporting its key.
set -eu
zip=$1
: "${NOTARY_KEY_PATH:?Apple API key path required}"
: "${NOTARY_KEY_ID:?Apple API key ID required}"
: "${NOTARY_ISSUER_ID:?Apple API issuer ID required}"
check=$(mktemp -d)
trap 'rm -rf "$check"' EXIT
ditto -x -k "$zip" "$check"
app="$check/AnticipyMac.app"
codesign --verify --deep --strict --verbose=2 "$app"
codesign -d --verbose=4 "$app" 2> "$check/signature.txt"
grep -q '^Authority=Developer ID Application: Omar Ebrahim (49T86P9XGW)$' "$check/signature.txt"
grep -q '^TeamIdentifier=49T86P9XGW$' "$check/signature.txt"
grep -q 'flags=.*runtime' "$check/signature.txt"
xcrun notarytool submit "$zip" --wait --key "$NOTARY_KEY_PATH" \
    --key-id "$NOTARY_KEY_ID" --issuer "$NOTARY_ISSUER_ID" \
    --output-format json > "$zip.notary.json"
python3 - "$zip.notary.json" <<'PY'
import json,sys
receipt=json.load(open(sys.argv[1]))
assert receipt.get('status') == 'Accepted', receipt
print('Apple notarization accepted:', receipt['id'])
PY
xcrun stapler staple "$app"
xcrun stapler validate "$app"
spctl -a -vvv -t exec "$app"
ditto -c -k --keepParent "$app" "$zip"
shasum -a 256 "$zip"
