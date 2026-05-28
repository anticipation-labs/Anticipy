#!/usr/bin/env bash
# test_dispatch.sh — verify `codex exec` is wired and can produce file output non-interactively.
#
# Run once during BOOTSTRAP. If this fails, write state/SETUP_BROKEN.md and stop.

set -uo pipefail

if [ -z "${REPO:-}" ]; then
  REPO="$(git rev-parse --show-toplevel 2>/dev/null || (cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P))"
fi
cd "$REPO"

mkdir -p state

if ! command -v codex >/dev/null 2>&1; then
  cat > state/SETUP_BROKEN.md <<EOF
# SETUP_BROKEN

\`codex\` CLI not found in PATH.

Install with: \`npm install -g @openai/codex\`
Or: \`brew install openai/codex/codex\`

Then re-run BOOTSTRAP.
EOF
  exit 1
fi

VERSION=$(codex --version 2>&1 | head -1)
echo "Found codex: $VERSION"

# Need 0.128.0+ for /goal feature, but we use codex exec which is older.
# Verify codex exec works non-interactively.
TEST_OUT=$(mktemp)
codex exec --sandbox danger-full-access --dangerously-bypass-approvals-and-sandbox "Write the literal string 'DISPATCH_OK' to $TEST_OUT and exit. Do not write anything else." > /tmp/codex-test.log 2>&1 || true

if grep -q "DISPATCH_OK" "$TEST_OUT" 2>/dev/null; then
  echo "codex exec dispatch verified."
  rm -f "$TEST_OUT"
  exit 0
fi

# Fallback: maybe the flags differ. Try alternative invocations.
codex exec "Write the literal string 'DISPATCH_OK' to $TEST_OUT and exit." > /tmp/codex-test.log 2>&1 || true
if grep -q "DISPATCH_OK" "$TEST_OUT" 2>/dev/null; then
  echo "codex exec dispatch verified (alt invocation)."
  rm -f "$TEST_OUT"
  # Patch dispatch scripts to use this invocation
  perl -0pi.bak -e 's/codex exec --sandbox danger-full-access --dangerously-bypass-approvals-and-sandbox "\\$PROMPT"/codex exec "\\$PROMPT"/g' scripts/dispatch_*.sh
  exit 0
fi

cat > state/SETUP_BROKEN.md <<EOF
# SETUP_BROKEN

\`codex exec\` did not produce expected output in non-interactive mode.

Diagnostic:
\`\`\`
$(cat /tmp/codex-test.log | head -50)
\`\`\`

Possible fixes:
1. Update Codex CLI: \`npm update -g @openai/codex\`
2. Check Codex auth: \`codex auth status\`
3. Check the exact invocation syntax for your Codex version: \`codex exec --help\`

Then update scripts/dispatch_*.sh with the correct invocation and re-run BOOTSTRAP.
EOF
exit 1
