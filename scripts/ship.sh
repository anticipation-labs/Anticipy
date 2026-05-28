#!/usr/bin/env bash
# ship.sh - package, upload, deploy, verify. Idempotent. Single command.
#
# What it does:
#   1. Build the Mac DMG via the existing desktop/Tauri build path.
#   2. Compute sha256 of the DMG.
#   3. Upload to R2 with content-type application/x-apple-diskimage.
#   4. Update state/builds/manifest.json with the new sha256 and commit hash.
#   5. Push to main.
#   6. Wait for Vercel deploy to complete by polling /api/app/state.
#   7. Confirm /api/app/state returns the new commit hash.
#   8. Confirm the DMG at the public URL has the new sha256.
#   9. Exit 0 only when all are confirmed.

set -euo pipefail

if [ -z "${REPO:-}" ]; then
  REPO="$(git rev-parse --show-toplevel 2>/dev/null || (cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P))"
fi
cd "$REPO"

if [ "${V6_DEFER_WORKTREE_SHIP:-0}" = "1" ] && printf '%s\n' "$REPO" | grep -q '/\.worktrees/'; then
  echo "[ship] deferred from worker worktree; orchestrator ships after merge to main."
  exit 0
fi

if [ -f scripts/load_env.sh ]; then
  # shellcheck disable=SC1091
  . scripts/load_env.sh
  load_anticipy_env
fi

CURRENT_COMMIT=$(git rev-parse HEAD)
SHORT=$(git rev-parse --short HEAD)

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "[ship] working tree is dirty. Commit, revert, or isolate unrelated changes before shipping."
  git status --short
  exit 1
fi

echo "[ship] Building DMG for $SHORT"
bash scripts/build_dmg.sh > state/ship-build.log 2>&1 || { echo "[ship] build failed"; exit 1; }

DMG_PATH=$(find target -name "Anticipy_*.dmg" -type f | head -1)
[ -f "$DMG_PATH" ] || { echo "[ship] DMG not found"; exit 1; }
DMG_SHA=$(shasum -a 256 "$DMG_PATH" | awk '{print $1}')
echo "[ship] DMG sha256: $DMG_SHA"

: "${R2_ACCOUNT_ID:?R2_ACCOUNT_ID must be set}"
: "${R2_BUCKET:=anticipy-downloads}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-${R2_ACCESS_KEY_ID:-${R2_ACCESS_KEY:-}}}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-${R2_SECRET_ACCESS_KEY:-${R2_SECRET:-}}}"
: "${AWS_ACCESS_KEY_ID:?R2 access key must be set}"
: "${AWS_SECRET_ACCESS_KEY:?R2 secret key must be set}"

if command -v aws >/dev/null 2>&1; then
  AWS=(aws)
else
  AWS=(uvx --from awscli aws)
fi

echo "[ship] Uploading to R2"
"${AWS[@]}" s3 cp "$DMG_PATH" "s3://$R2_BUCKET/Anticipy_1.0.0_aarch64.dmg" \
  --endpoint-url "https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com" \
  --content-type "application/x-apple-diskimage" \
  > state/ship-r2.log 2>&1 || { echo "[ship] R2 upload failed"; exit 1; }

mkdir -p state/builds
jq -n --arg sha "$DMG_SHA" --arg commit "$CURRENT_COMMIT" --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  '{latest_sha256: $sha, latest_commit: $commit, built_at: $ts}' \
  > state/builds/manifest.json

git add state/builds/manifest.json
if ! git diff --cached --quiet; then
  git commit -m "ship: update build manifest for $SHORT"
  CURRENT_COMMIT=$(git rev-parse HEAD)
  SHORT=$(git rev-parse --short HEAD)
fi

echo "[ship] Pushing to main"
git push origin HEAD:main

echo "[ship] Polling /api/app/state until live commit matches $SHORT"
LIVE=""
for i in $(seq 1 60); do
  LIVE=$(curl -s https://www.anticipy.ai/api/app/state | jq -r '.build.commit // .commit // .deployedCommit // empty' || echo "")
  if [ "${LIVE:0:7}" = "$SHORT" ]; then
    echo "[ship] Vercel is live at $SHORT"
    break
  fi
  echo "[ship] live=$LIVE expected=$SHORT (try $i/60)"
  sleep 10
done

if [ "${LIVE:0:7}" != "$SHORT" ]; then
  echo "[ship] Vercel did not deploy $SHORT after 10min. Failing."
  exit 1
fi

echo "[ship] Verifying public DMG sha256 matches"
LIVE_DMG_SHA=""
for i in $(seq 1 6); do
  LIVE_DMG_SHA=$(curl --max-time 900 -fsSL https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg | shasum -a 256 | awk '{print $1}' || echo "")
  if [ "$LIVE_DMG_SHA" = "$DMG_SHA" ]; then
    break
  fi
  echo "[ship] public DMG sha try $i/6: live=${LIVE_DMG_SHA:-unavailable} expected=$DMG_SHA"
  sleep 60
done
if [ "$LIVE_DMG_SHA" != "$DMG_SHA" ]; then
  echo "[ship] Public DMG sha mismatch: live=$LIVE_DMG_SHA expected=$DMG_SHA"
  exit 1
fi

echo "[ship] OK. $SHORT is live, DMG is correct, sha256=$DMG_SHA."
