#!/usr/bin/env bash
# preflight.sh — Gate-0 / start-of-session ground check. READ-ONLY and SAFE: no commits, no sends,
# no engine restarts. Prints the state every session needs before building.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; }

echo "===================== ANTICIPY PREFLIGHT ====================="
echo "repo:   $REPO"
echo "branch: $(git branch --show-current 2>/dev/null)"
echo "head:   $(git log --oneline -1 2>/dev/null)"
echo

echo "--- concurrency ---"
if [ -e factory/.lock ]; then bad "factory/.lock PRESENT — a lap is running; FOREMAN MUST NOT COMMIT"; else ok "no factory/.lock — safe to commit"; fi
if [ -e factory/.halt ]; then warn "factory/.halt present — nightly factory loop is paused"; else ok "no factory/.halt"; fi
echo

echo "--- git cleanliness ---"
DIRTY="$(git status --porcelain | wc -l | tr -d ' ')"
echo "  uncommitted changes: $DIRTY file(s)"
echo

echo "--- secret hygiene (must be NONE tracked) ---"
TRACKED_ENV="$(git ls-files | grep -E '(^|/)\.env' | grep -vE '\.(example|sample|template)$' || true)"
if [ -n "$TRACKED_ENV" ]; then bad "TRACKED .env files: $TRACKED_ENV"; else ok "no tracked .env* files"; fi
echo

echo "--- Memory Dock present ---"
for f in CONSTITUTION DEFINITION_OF_DONE CURRENT_TRUTH RECEIPTS FAILURES DECISIONS NEXT_GATE RESEARCH_LEDGER HANDOFF_NOW; do
  if [ -f "docs/agent_os/$f.md" ]; then ok "docs/agent_os/$f.md"; else bad "MISSING docs/agent_os/$f.md"; fi
done
echo

echo "--- toolchain ---"
command -v codex >/dev/null 2>&1 && ok "codex: $(codex --version 2>/dev/null)" || warn "codex CLI not found"
command -v node  >/dev/null 2>&1 && ok "node: $(node --version)" || warn "node not found"
[ -x engine/.venv/bin/python ] && ok "engine venv present" || warn "engine/.venv/bin/python missing"
echo

echo "--- live engine (read-only) ---"
STATUS="$(curl -s -m 3 http://127.0.0.1:8787/status 2>/dev/null)"
if [ -n "$STATUS" ]; then
  ok "engine :8787 reachable"
  MODE="$(printf '%s' "$STATUS" | grep -o '"mode":"[a-z]*"' | head -1)"
  echo "    channels $MODE"
  printf '%s' "$STATUS" | grep -q '"mode":"live"' && warn "channels=LIVE — do NOT trigger live text/call to Omar (31-text history)"
else
  warn "engine :8787 not reachable (start it read-only if a gate needs it)"
fi
echo
echo "Reminders: verify never assume · receipts only · never act on a vent · money = hard stop."
echo "============================================================="
