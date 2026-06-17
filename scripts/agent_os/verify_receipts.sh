#!/usr/bin/env bash
# verify_receipts.sh — sanity gate before claiming progress / committing. Checks the Memory Dock is
# intact, no secrets are staged, and (optionally) that the suite + cardinal-sin floor pass.
# Usage: bash scripts/agent_os/verify_receipts.sh [--full]
#   --full also runs scripts/run_suite.sh (slow). Default is fast doc/secret checks only.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"
FAIL=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad() { printf '  \033[31m✗\033[0m %s\n' "$1"; FAIL=1; }

echo "=== verify_receipts ==="
# 1. Dock intact
for f in CONSTITUTION DEFINITION_OF_DONE CURRENT_TRUTH RECEIPTS FAILURES DECISIONS NEXT_GATE RESEARCH_LEDGER HANDOFF_NOW; do
  [ -s "docs/agent_os/$f.md" ] && ok "$f.md" || bad "missing/empty docs/agent_os/$f.md"
done
# 2. No secrets staged or tracked
if git diff --cached --name-only | grep -E '(^|/)\.env' | grep -qvE '\.(example|sample|template)$'; then bad "STAGED .env file — refuse"; else ok "no staged .env (templates ok)"; fi
if git ls-files | grep -E '(^|/)\.env' | grep -qvE '\.(example|sample|template)$'; then bad "TRACKED .env file present"; else ok "no tracked .env (templates ok)"; fi
# 3. No lock
[ -e factory/.lock ] && bad "factory/.lock present — do not commit" || ok "no factory/.lock"

if [ "${1:-}" = "--full" ]; then
  echo "--- running suite (run_suite.sh) ---"
  if bash scripts/run_suite.sh; then ok "suite passed"; else bad "suite FAILED"; fi
fi

echo "=== verify_receipts: $([ $FAIL -eq 0 ] && echo OK || echo FAIL) ==="
exit $FAIL
