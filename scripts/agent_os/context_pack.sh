#!/usr/bin/env bash
# context_pack.sh — the mission context every spawned agent (Claude subagent / Codex worker) MUST
# receive before its task. Prints CONSTITUTION + CURRENT_TRUTH + NEXT_GATE + FAILURES.
# Usage: bash scripts/agent_os/context_pack.sh   (prints to stdout)
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
D="$REPO/docs/agent_os"

emit() { # $1 = file, $2 = banner
  if [ -f "$1" ]; then
    printf '\n================ %s ================\n\n' "$2"
    cat "$1"
  else
    printf '\n[context_pack] MISSING: %s\n' "$1" >&2
  fi
}

cat <<'HDR'
================ ANTICIPY AGENT BRIEF — READ BEFORE YOUR TASK ================

You are building Anticipy: Donna from Suits for real life. Do NOT shrink the mission, call mock proof
product proof, or grade your own work. Prepare harmless work, park the final press-go, ask only at the
irreversible step. NEVER act on vents/jokes/sarcasm. Money/payment is a hard stop. No self-attestation:
real-artifact read-back or it is NOT done. Your output must include: changed files, commands run, the
receipt produced, what could still break, and whether you touched any forbidden area.

Forbidden without an explicit "eval owner" task: hidden holdout content, scoring thresholds, receipt
ledger history, failure ledger history, production secrets, user tokens, payment functions. Never commit
.env*. Never commit while factory/.lock exists. ~/Developer/Anticipy-DEV-FINAL is HANDS-OFF.
HDR

emit "$D/CONSTITUTION.md"  "CONSTITUTION (supreme law)"
emit "$D/CURRENT_TRUTH.md" "CURRENT TRUTH (what is proven vs not)"
emit "$D/NEXT_GATE.md"     "NEXT GATE (your objective + receipts)"
emit "$D/FAILURES.md"      "FAILURES (tripwires — do not repeat)"

printf '\n================ END BRIEF ================\n'
