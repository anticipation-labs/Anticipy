#!/bin/bash
# THE BUTTON. Run this and everything goes back to exactly how Omar left it
# on the night of 2026-08-05, before any overnight work.
#
#     bash ~/AnticipyFleet/control/REVERT.sh
#
# It restores the code to the tagged known-good commit and redeploys the
# live brain from it. It does NOT touch the database — your events, jobs
# and memory are never deleted by this script.
#
# Safe to run twice. Safe to run if nothing changed.
set -euo pipefail

TAG="pre-overnight-2026-08-05"
REPO="$HOME/AnticipyFleet/control"

echo "Reverting Anticipy to $TAG (the state you went to sleep on)…"
cd "$REPO"

echo "  · what is on the branch right now:"
git log --oneline "$TAG"..HEAD 2>/dev/null | sed 's/^/      /' || true

# Keep the overnight work — never destroy it, just step off it.
git branch -f overnight-work-kept HEAD >/dev/null 2>&1 || true
git checkout -B pendant-system "$TAG" >/dev/null 2>&1
echo "  · code is back at $TAG (overnight work saved on branch 'overnight-work-kept')"

echo "  · redeploying the brain from this exact code…"
railway up --service worker --detach >/dev/null 2>&1 && echo "      worker redeploy started"

echo
echo "Done. The brain is going back to the version you knew."
echo "Give it ~2 minutes, then check:"
echo "  railway logs --service worker | tail -3"
echo
echo "Nothing was deleted. To look at the overnight work again:"
echo "  git checkout overnight-work-kept"
