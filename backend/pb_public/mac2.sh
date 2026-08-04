set -e

# Makes a separate "build keychain" that holds ONLY the app-signing
# certificate, with its own random password kept on this Mac. Remote builds
# unlock that one small keychain — never your login keychain.

LOGIN=~/Library/Keychains/login.keychain-db
BK=~/Library/Keychains/anticipy-build.keychain-db

# You'll be asked for your Mac password here (stays on this Mac).
security unlock-keychain "$LOGIN"

mkdir -p ~/.anticipy
PW=$(openssl rand -hex 24)
echo "$PW" > ~/.anticipy/build_keychain_pw
chmod 600 ~/.anticipy/build_keychain_pw

security delete-keychain "$BK" 2>/dev/null || true
security create-keychain -p "$PW" "$BK"
security set-keychain-settings "$BK"
security unlock-keychain -p "$PW" "$BK"

# Copy the signing identity across. macOS may pop up a window asking to
# allow the export — click Allow (or Always Allow) and enter your Mac
# password there.
TMP=$(mktemp -d)
security export -k "$LOGIN" -t identities -f pkcs12 -P "$PW" -o "$TMP/ids.p12"
security import "$TMP/ids.p12" -k "$BK" -P "$PW" -T /usr/bin/codesign -T /usr/bin/security
rm -rf "$TMP"

security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$PW" "$BK" >/dev/null

# Put the build keychain on the search list alongside the login keychain.
security list-keychains -d user -s "$LOGIN" "$BK"

security find-identity -v -p codesigning "$BK" | tail -2
echo "ANTICIPY_BUILD_KEYCHAIN_READY"
