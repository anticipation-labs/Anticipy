#!/usr/bin/env bash
set -euo pipefail

: "${CYCLE:?}"
: "${CYCLE_DIR:?}"

REPO="${REPO:-$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)}"
cd "$REPO"
. scripts/v6/dispatch_common.sh

PROMPT="Read ANTICIPY_V7.md from disk. First restate PART 0 in your own words.
You are the Planner per roles/planner.md and the V7 target.
Cycle: $CYCLE.
Cycle dir: $CYCLE_DIR.

Do not write code. Read state/STATUS.md if present, state/decisions/queue.md if present, state/check_done_v7.json if present, state/cycle-$((CYCLE - 1))/judge_verdict.json if present, git status, focused git log, and the output of bash scripts/regression.sh. Then write $CYCLE_DIR/tasks.json with 1 to 3 tasks. Each task must have id, title, scope, out_of_scope, success_test, and principle_link.

Choose the next task from the first actionable red V7 gate, not from a stale fixed instruction. If a red gate is blocked only by an Omar-only decision or missing hardware already recorded in state/decisions/queue.md, keep that gate red, mention it in the rationale, execute its default, and plan the next red gate that can be advanced by code or verifier work. Do not repeat the external_microphone proof task while /api/audio/devices has no non-builtin, non-virtual input device; that proof cannot be made true in code without faking it.

Current input-mode priority: fix MP3 transcript_path/timeouts if red, fix transcript/computer-mic product bugs if red, and require a real external input device for external_microphone. Any success_test that probes 127.0.0.1:8731 must start with python3 scripts/v7/assert_installed_engine.py so source uvicorn or stale dev servers cannot pass as product proof. If V7 is mechanically green, do not guess: run bash scripts/v7/check_done.sh and let it write state/COMPLETE.md."

PROMPT="$PROMPT

Chrome surface correction: direct remote-debugging CDP on the user's actual default Chrome profile is a proven dead end on Chrome 136+ / Chrome 148. Cycle 27 recorded Chrome's exact restriction: DevTools remote debugging requires a non-default data directory. Do not plan another direct_browser_cdp task that requires --remote-debugging-port against the default real profile, and do not fall back to ~/.anticipy/chrome-real-clone. The next real-surface plan must use the installed Anticipy Chrome extension / chrome.debugger / native-messaging bridge, or macOS Chrome Apple Events plus screenshot, on the user's actual visible Chrome. V7.10 may be proven by extension/chrome.debugger/native-messaging or real_chrome_applescript_visible_surface receipts; it must not require direct_browser_cdp."

run_codex_prompt "$PROMPT"
