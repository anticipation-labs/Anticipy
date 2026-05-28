#!/usr/bin/env bash
set -euo pipefail

: "${CYCLE:?}"
: "${CYCLE_DIR:?}"
: "${JUDGE_INPUT:?}"

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$REPO"
. scripts/v6/dispatch_common.sh

PROMPT="Read ANTICIPY_V7.md from disk. First restate PART 0 in your own words.
You are the Judge per roles/judge.md and the V7 target.
Manifest: $JUDGE_INPUT.

Read only ANTICIPY_V7.md, roles/judge.md, and the manifest. Apply the mechanical rules. Reject any task whose success_test probes 127.0.0.1:8731 without python3 scripts/v7/assert_installed_engine.py, because source uvicorn or stale dev servers cannot count as public product proof. Write $CYCLE_DIR/judge_verdict.json. Do not run tests and do not read worker logs."

run_codex_prompt "$PROMPT"
