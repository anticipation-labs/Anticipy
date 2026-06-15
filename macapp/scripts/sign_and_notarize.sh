#!/usr/bin/env bash
# sign_and_notarize.sh — the ONE command to ship a signed, notarized "Anticipy Execute"
# that anyone can download and open with a double-click (no right-click → Open).
#
# This is the ONLY remaining step that genuinely needs you, because Apple requires it:
# a Developer ID certificate + Apple's notary service. An agent cannot create that for
# you — it needs your Apple ID login and the $99 enrollment. One-time setup (~15 min):
#
#   1. Enroll in the Apple Developer Program ($99/yr): https://developer.apple.com/programs/
#   2. Create + install a "Developer ID Application" certificate (Xcode > Settings >
#      Accounts > Manage Certificates > +, or developer.apple.com). It lands in your
#      login keychain automatically.
#   3. Store notary credentials once (app-specific password from appleid.apple.com):
#        xcrun notarytool store-credentials anticipy-notary \
#          --apple-id "<your-apple-id>" --team-id "<TEAMID>" --password "<app-specific-pw>"
#
# Then ship it any time with:   bash macapp/scripts/sign_and_notarize.sh
set -euo pipefail
MACAPP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="$MACAPP/dist/Anticipy.app"
PROFILE="${ANTICIPY_NOTARY_PROFILE:-anticipy-notary}"
test -d "$APP" || { echo "build first: bash macapp/scripts/build_app.sh" >&2; exit 1; }

ID="$(security find-identity -v -p codesigning | grep 'Developer ID Application' | head -1 | sed -E 's/.*"(.*)"/\1/' || true)"
if [ -z "${ID:-}" ]; then
  echo "No 'Developer ID Application' certificate in the keychain yet." >&2
  echo "Do the one-time setup in the header of this script, then re-run." >&2
  exit 1
fi
echo "== signing with: $ID =="
codesign --force --deep --options runtime --timestamp --sign "$ID" "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"

ZIP="$MACAPP/dist/AnticipyExecute.zip"
rm -f "$ZIP"; ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
echo "== submitting to Apple notary (profile: $PROFILE) — this can take a few minutes =="
xcrun notarytool submit "$ZIP" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$APP"
rm -f "$ZIP"; ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
echo "== verifying Gatekeeper acceptance =="
spctl -a -t open --context context:primary-signature -v "$APP" || true
echo "DONE: signed + notarized + stapled -> $ZIP  (double-click-openable by anyone)."
