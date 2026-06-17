#!/usr/bin/env bash
# commit_and_push.sh — safe commit for the foreman. Refuses to commit under factory/.lock or with
# staged .env/secrets. Push is OPT-IN (PUSH=1) and never targets the Omar-owned DEV-FINAL repo.
#
# Usage:
#   bash scripts/agent_os/commit_and_push.sh "Gate X: specific proven message" [file ...]
#   PUSH=1 bash scripts/agent_os/commit_and_push.sh "..."   # also push to origin current-branch
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"
MSG="${1:?commit message required}"; shift || true

# Guard: lock
[ -e factory/.lock ] && { echo "factory/.lock present — refusing to commit"; exit 1; }
# Guard: not the hands-off repo
ORIGIN="$(git remote get-url origin 2>/dev/null || true)"
case "$ORIGIN" in
  *Anticipy.git) echo "origin is $ORIGIN (Omar-owned anticipy.ai) — refusing autonomous commit/push here"; exit 1;;
esac

# Stage
if [ "$#" -gt 0 ]; then git add -- "$@"; else git add -A; fi
# Guard: no secrets staged
if git diff --cached --name-only | grep -E '(^|/)\.env' | grep -qvE '\.(example|sample|template)$'; then echo "staged .env detected — aborting"; git reset -q; exit 1; fi
# Run the fast receipts sanity check
bash scripts/agent_os/verify_receipts.sh || { echo "verify_receipts failed — aborting"; exit 1; }

git diff --cached --name-only | sed 's/^/  staged: /'
git commit -m "$MSG

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"

if [ "${PUSH:-0}" = "1" ]; then
  BR="$(git branch --show-current)"
  echo "pushing origin $BR ..."
  git push origin "$BR"
else
  echo "committed locally (set PUSH=1 to push)."
fi
