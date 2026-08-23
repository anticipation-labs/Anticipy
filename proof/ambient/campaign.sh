#!/bin/bash
# THE 10K VOICE CAMPAIGN. Eight rounds of the same thousand utterances.
#
#   sh proof/ambient/campaign.sh 8
#
# WHY EIGHT ROUNDS OF ONE CORPUS, rather than eight thousand different lines.
# "Run them repeatedly, not once" is the requirement, and repetition is the only
# thing that separates a capability boundary from a coin flip. Measured
# 2026-08-21: of fourteen lines that missed in one round, five were caught on a
# re-run and twelve produced a goal in the clean room. A single pass cannot tell
# those apart, and a single pass is what every previous scorecard was.
#
# Each round writes its own directory, so score.py can be run per round and the
# spread across rounds IS the stability number.
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
RIG="${ANTICIPY_RIG_DIR:-$HOME/.anticipy-rig}"
ROUNDS="${1:-8}"
CORPUS="${CORPUS:-$REPO/proof/ambient/corpus.big.json}"
cd "$REPO"

# Loopback only, and pinned rather than inherited: .env.local carries a
# production ANTICIPY_PB and anything that inherits this shell inherits it.
export ANTICIPY_PB=http://127.0.0.1:8090
export ANTICIPY_MODEL="${ANTICIPY_MODEL:-google/gemini-2.5-flash}"
export ANTICIPY_AUX_MODEL="${ANTICIPY_AUX_MODEL:-google/gemini-2.5-flash-lite}"

echo "corpus  $(python3 -c "import json;print(len(json.load(open('$CORPUS'))))") utterances"
echo "rounds  $ROUNDS"
echo "model   $ANTICIPY_MODEL  (aux $ANTICIPY_AUX_MODEL)"

for i in $(seq 1 "$ROUNDS"); do
  echo ""
  echo "================ ROUND $i of $ROUNDS ================"
  # Every round starts from a clean set of workers. A worker left over from the
  # previous round holds accumulated memory for its owner, so round 8 would be
  # answering with facts learned in rounds 1-7 and the rounds would stop being
  # comparable.
  pkill -f "brain.worker" 2>/dev/null
  sleep 3
  "$RIG/venv/bin/python" -u proof/ambient/fanout.py \
      --corpus "$CORPUS" --label "k$i" --gap 0.2 2>&1 \
    | grep -E "utterances across|merged" || true
  "$RIG/venv/bin/python" proof/ambient/score.py \
      --corpus "$CORPUS" \
      --results "proof/ambient/rounds/k$i/results.jsonl" \
      --json "proof/ambient/rounds/k$i/scorecard.json" 2>&1 \
    | sed -n '2p;6,9p;17,19p'
done

pkill -f "brain.worker" 2>/dev/null
echo ""
echo "all $ROUNDS rounds done. Combined:"
cat proof/ambient/rounds/k*/results.jsonl 2>/dev/null | wc -l | sed 's/^/  decisions: /'
