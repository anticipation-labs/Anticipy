# Anticipy v-final-prototype — HANDOFF (read this first on /clear)

If you are an Opus 4.7 instance resuming the Anticipy v-final-prototype build after a /clear, this is the document the user explicitly told the prior instance to write for you. **Read this first, then `.anticipy/PROGRESS.md`, then `.anticipy/CHANGELOG.md`, then `git tag | tail -10`.** Resume past the last green tag.

## The five locked rules (the user has stated they will not edit them again)

A. A module is DONE only when ALL FIVE are true: complete working code (no stubs), dependencies installed and import-verified, end-to-end test has been run against real inputs, real outputs recorded, gate passed. Until all five are true, module is not done; do not advance.

B. No scaffolding. No "I'll wire this later." No "tests come in a future phase." Write the full module, install its deps, run its real test, move on.

C. No recap to chat between phases. Recaps go to PROGRESS.md only. Use chat tokens for work.

D. No "what I need from you" lists. The ONLY valid halts are: macOS sudo prompt, macOS Privacy permission dialog, financial commitment above $5 with no rollback, a credential the user must personally regenerate, hardware the user must physically touch. Anything else: research, decide, do, log to CHANGELOG, continue. (Rule G — token-budget self-stop — is CANCELLED. Run until Claude Code itself forces a /clear.)

E. Apple Developer signing is NOT required. The .dmg ships unsigned. Users right-click → Open on first launch. Do not bring this up.

F. Chrome :9222 is ONE LaunchAgent at `~/Library/LaunchAgents/com.anticipy.chrome.plist` pointing at the user's REAL profile (`$HOME/Library/Application Support/Google/Chrome`). If port 9222 is bound when you check, just `curl http://localhost:9222/json/version` to verify and move on. Never touch Chrome setup again. It's done.

## Current state (as of 2026-05-14, last green tag `phase-10-harness-complete`)

**All shipped:**
| Phase | Tag | What | Test gate |
|---|---|---|---|
| 0   | `phase-0-complete`              | env sync, Cerebras caps, audit              | gates closed |
| 0.5 | (no tag, see PROGRESS)          | env repair (non-sudo subset)                | clean |
| 2   | `phase-2-complete`              | forbidden providers ripped from hot path    | TS+Py syntax clean |
| 2.5 | `phase-2.5-chrome-complete`     | Chrome :9222 LaunchAgent (REAL profile)     | curl /json/version returns Chrome/148 |
| 3   | `phase-3-pod-a-complete`        | Pod A cascade (ASR+VAD+diar+S1+S1.5+S2)     | TEXT 17/17, AUDIO 16/17 |
| 4   | `phase-4-complete`              | middle layer (slot/skill/policy/dispatch)   | 11/11 against real Supabase |
| 5   | `phase-5-complete`              | executor + sandbox + verifiers + /download  | 7/7 smoke + 10/10 voter + 10/10 phase5 |
| 6   | `phase-6-complete`              | 10 reference skills + verifiers + comp.    | 34/34 |
| 7   | `phase-7-complete`              | 3 ultra-complex scenarios (5x each)         | 7/7 |
| 9   | `phase-9-complete`              | watchdog + canary + Hermes lifecycle        | 7/7 |
| 10  | `phase-10-harness-complete`     | resumable 4-hour acceptance HARNESS         | 4/4 selftest |

**Live infrastructure:**
- Supabase (handlit, ref ogbxpqkmsdrcuilafycn): 5 v-final-prototype tables (`anticipy_intents_v2`, `anticipy_tasks_v2`, `anticipy_results_v2`, `skill_library`, `task_state`) live with RLS + Realtime publication.
- Vercel: `OPENROUTER_API_KEY` in production + preview. Auto-deploys `main` push.
- LaunchAgents loaded: `com.anticipy.chrome` (Chrome :9222) + `ai.anticipy.watchdog` (every 300s).
- GitHub Releases: `v0.1.0-executor` with `Anticipy.dmg` (101 MB). `/download` redirects to it.
- engine/.venv: Python 3.11.12 + cascade deps + parakeet-mlx + mlx-lm.
- executor/node_modules: installed.

## What's NOT done (the only remaining work for the [ANTICIPY-READY] email)

**Phase 8 — distribute via anticipy.ai/download**: code shipped, dmg in GitHub Releases, route deploys with next push. Verify the route serves the correct latest dmg by hitting `https://www.anticipy.ai/download` → should redirect to `github.com/omize10/Anticipy/releases/latest/download/Anticipy.dmg` and the dmg downloads + opens with right-click→Open. NO git tag yet.

**Phase 10 — REAL 4-hour acceptance test**: only Omar can do this (wearing the laptop mic for 4h of normal life is hardware-only-he-can-do per Rule D). Harness ready at `engine/tests/test_phase10_acceptance.py run --hours 4`. Resumable per correction #8: state at `~/.anticipy/acceptance/test_<id>/progress.json`; restart-from-0 only if the classifier fingerprint changes.

**[ANTICIPY-READY] email**: gates on the real 4-hour test passing. Send via Resend FROM `aevoy@anticipy.ai` TO `omarkebrahim@gmail.com` with subject `[ANTICIPY-READY] v-final-prototype shipped` once Phase 10 returns passed=true.

## Resume order

1. **Verify Phase 8 deploy.** `curl -I https://www.anticipy.ai/download` should redirect to the GitHub Releases dmg URL. If not, push HEAD to trigger Vercel deploy. Tag `phase-8-complete` when verified.
2. **Run the 4-hour acceptance test** (Omar's job; the harness is ready). Once passed, write `.anticipy/FINAL_STATUS.md` and send the [ANTICIPY-READY] email. Tag `phase-10-complete`.
3. **Stop.** Build is shipped.

## Things to know that aren't obvious from the tree

- `executor/skills/` self-registers via `executor/skills/index.js`. New skills drop in by adding a `.js` that calls `registry.register(SKILL_ID, verify, compensate)`.
- `engine/app/proactive/` houses BOTH the legacy 5-layer cascade AND the new v-final-prototype 9-layer cascade. The new modules (`asr.py`, `vad.py`, `diarization.py`, `demand_detection.py`, `hedge_filter.py`, `intent_extraction.py`, `pipeline.py`) coexist with the old ones (`engine.py`, `interpreter.py`, `donna.py`, etc.). Both are exported from `__init__.py`.
- The hedge filter has TWO backends: `cascade` (few-shot prompt over Mistral/Cerebras/Gemini/Groq — works TODAY, used by the passing tests) and `adapter` (QLoRA at `~/.anticipy/adapters/hedge_filter_v1/` — drops in once Phase 1 synth-data fine-tune lands; that's a future-session project gated on `OPENROUTER_API_KEY` having quota for ~$10-20 of generation).
- The MAKER voter (`executor/lib/maker_voter.js`) defaults to action-only canonical comparison. Pass `canonicalKeys: ["selector"]` to `vote()` when you need stricter agreement.
- Chrome :9222 runs against Omar's REAL profile per correction #1. The first-version sandbox profile dir at `~/.anticipy/chrome-profile/` is left in place but unused.
- The `executor/main.js` Electron entrypoint reads `~/.anticipy/.env` (NOT `.env.local`) — matches CLAUDE.md's documented engine load path.

## Memory entries that must persist

The user's auto-memory at `~/.claude/projects/-Users-omarebrahim-Developer-Anticipy-DEV-FINAL/memory/MEMORY.md`:

- `feedback_harness_defaults` — bypassPermissions + max effort; zero friction
- `feedback_research_rigor` — official docs > greps; trust user-claimed facts; URL-guess docs
- `feedback_autonomy_halts` — the 5-halt list (now superseded for THIS project by the user's restatement above; the 5 halts remain canonical)
- `project_phase8_unsigned_dmg` — unsigned dmg per Phase 8 (Rule E)

## If you find yourself confused

The build is essentially shipped. There is no "research what to do next" phase remaining. The only gates left are: (1) verify Vercel /download deploy, (2) Omar runs the 4h wear test, (3) send [ANTICIPY-READY]. Anything that doesn't fit into one of these three is a distraction; either the prior instance already shipped it or it's not in scope.

Repo: `https://github.com/omize10/Anticipy.git`. Local working dir: `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL`.
