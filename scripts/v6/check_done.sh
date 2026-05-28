#!/usr/bin/env bash
# Mechanical V6 D7 done checker.

set -euo pipefail

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
SITE_URL="${SITE_URL:-https://www.anticipy.ai}"
cd "$REPO"

mkdir -p state
OUT="state/check_done_v6.json"

set +e
python3 scripts/v6/breadth_audit.py --min-success 100 --min-verb-categories 20 --min-hard-categories 5 >/tmp/anticipy_breadth_v6.log 2>&1
BREATH_RC=$?
python3 scripts/v6/cost_audit.py >/tmp/anticipy_cost_v6.log 2>&1
COST_RC=$?
python3 scripts/v6/transcript_audit.py >/tmp/anticipy_transcript_v6.log 2>&1
TRANSCRIPT_RC=$?
set -e

LOCAL_HEAD=$(git rev-parse HEAD)
ORIGIN_HEAD=$(git ls-remote origin refs/heads/main | awk '{print $1}')
LIVE_HEAD=$(curl -sS "$SITE_URL/api/app/state" | jq -r '.build.commit // .commit // .deployedCommit // empty' || echo "")

DEPLOY_OK=false
if [ "${LOCAL_HEAD:0:7}" = "${ORIGIN_HEAD:0:7}" ] && [ "${LOCAL_HEAD:0:7}" = "${LIVE_HEAD:0:7}" ]; then
  DEPLOY_OK=true
fi

DMG_OK=false
EXPECTED_SHA=""
LIVE_SHA=""
if [ "$DEPLOY_OK" = true ] && [ -f state/builds/manifest.json ]; then
  EXPECTED_SHA=$(jq -r '.latest_sha256 // empty' state/builds/manifest.json)
  if [ -n "$EXPECTED_SHA" ]; then
    LIVE_SHA=$(curl --max-time 240 -fsSL "$SITE_URL/dl/Anticipy_1.0.0_aarch64.dmg" | shasum -a 256 | awk '{print $1}' || echo "")
    [ "$LIVE_SHA" = "$EXPECTED_SHA" ] && DMG_OK=true
  fi
fi

MP3_OK=$(python3 - <<'PY'
import json
from pathlib import Path
rows = sorted(Path("state/mp3_eval").glob("*/verdict.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:3]
if len(rows) != 3:
    print("false")
    raise SystemExit
for path in rows:
    try:
        data = json.loads(path.read_text())
    except Exception:
        print("false")
        raise SystemExit
    if not (data.get("pass") is True or data.get("verdict") == "pass"):
        print("false")
        raise SystemExit
print("true")
PY
)

LAST20_OK=$(jq -r '(.last20_count >= 20) and ((.last20_failures | length) == 0)' state/stranger_breadth.json 2>/dev/null || echo false)
BREADTH_OK=false
[ "$BREATH_RC" -eq 0 ] && [ "$LAST20_OK" = "true" ] && BREADTH_OK=true

jq -n \
  --arg local "$LOCAL_HEAD" \
  --arg origin "$ORIGIN_HEAD" \
  --arg live "$LIVE_HEAD" \
  --arg expected_sha "$EXPECTED_SHA" \
  --arg live_sha "$LIVE_SHA" \
  --argjson breadth_ok "$BREADTH_OK" \
  --argjson mp3_ok "$MP3_OK" \
  --argjson deploy_ok "$DEPLOY_OK" \
  --argjson dmg_ok "$DMG_OK" \
  --argjson cost_ok "$([ "$COST_RC" -eq 0 ] && echo true || echo false)" \
  --argjson transcript_ok "$([ "$TRANSCRIPT_RC" -eq 0 ] && echo true || echo false)" \
  '{
    breadth_ok: $breadth_ok,
    mp3_ok: $mp3_ok,
    deploy_ok: $deploy_ok,
    dmg_ok: $dmg_ok,
    cost_ok: $cost_ok,
    transcript_ok: $transcript_ok,
    commits: {local: $local, origin_main: $origin, live: $live},
    dmg: {expected_sha256: $expected_sha, live_sha256: $live_sha}
  }' > "$OUT"

ALL_OK=$(jq -r '[.breadth_ok, .mp3_ok, .deploy_ok, .dmg_ok, .cost_ok, .transcript_ok] | all' "$OUT")
if [ "$ALL_OK" = "true" ]; then
  {
    echo "COMPLETE"
    echo "Successful stranger interactions: 100+ across 20+ verb categories"
    echo "Hard categories hit: 5/5"
    echo "Last 20 interactions: all passed"
    echo "MP3 eval: 3 consecutive passes"
    echo "Deploy parity: green"
    echo "Public DMG SHA: matches manifest"
    echo "Runtime cost projection: under $200/user/year"
    echo "Transcript quality: WER under 5 percent"
    echo "Checked at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > state/COMPLETE.md
  cat "$OUT"
  exit 0
fi

cat "$OUT"
exit 1
