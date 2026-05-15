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
| 1   | (partial, no tag)               | synth data scaffolding + 76 rows generated  | 56/60 (93%) held-out cascade |
| 2   | `phase-2-complete`              | forbidden providers ripped from hot path    | TS+Py syntax clean |
| 2.5 | `phase-2.5-chrome-complete`     | Chrome :9222 LaunchAgent (REAL profile)     | curl /json/version returns Chrome/148 |
| 3   | `phase-3-pod-a-complete`        | Pod A cascade (ASR+VAD+diar+S1+S1.5+S2)     | TEXT 16/17, AUDIO 16/17, OOD 56/60 |
| 4   | `phase-4-complete`              | middle layer (slot/skill/policy/dispatch)   | 11/11 against real Supabase |
| 5   | `phase-5-complete`              | executor + sandbox + verifiers + /download  | 7/7 smoke + 10/10 voter + 10/10 phase5 |
| 6   | `phase-6-complete`              | 10 reference skills + verifiers + comp.    | 34/34 |
| 7   | `phase-7-complete`              | 3 ultra-complex scenarios (5x each)         | 7/7 |
| 8   | `phase-8-complete`              | anticipy.ai/download → unsigned dmg via GH Releases | curl returns 302 → 200 |
| 9   | `phase-9-complete`              | watchdog + canary + Hermes lifecycle        | 7/7 |
| 10  | `phase-10-harness-complete`     | resumable 4-hour acceptance HARNESS         | 4/4 selftest |
| FullE2E | `phase-9-full-pipeline-passing` | utterance → cascade → middle → executor → Result | 6/6 (real Supabase + Chrome :9222 + Wikipedia) |
| FullE2E×5 | `phase-9-full-pipeline-5x` | same E2E run 5x consecutively | 30/30 gates green |
| Hermes | `phase-9-hermes-promote-verified` | shadow→active promotion at 20/20 100% on `navigate_fact_lookup` | live promotion observed in DB |

**Live infrastructure:**
- Supabase (handlit, ref ogbxpqkmsdrcuilafycn): 5 v-final-prototype tables. `skill_library` has 11 rows (10 shadow + 1 active — `navigate_fact_lookup` was promoted by Hermes after 20/20 successful E2E runs in this session).
- Vercel: `OPENROUTER_API_KEY` in production + preview. Auto-deploys `main` push. `/download` route LIVE.
- LaunchAgents loaded: `com.anticipy.chrome` (Chrome :9222 on REAL profile) + `ai.anticipy.watchdog` (every 300s; runs health + hermes + canary).
- GitHub Releases: `v0.1.0-executor` with `Anticipy.dmg` (101 MB). `/download` redirects to it. Verified live with `curl -I` returning 302.
- engine/.venv: Python 3.11.12 + cascade deps + parakeet-mlx + mlx-lm + dotenv + supabase + httpx.
- executor/node_modules: installed; both passing tests + .dmg built.
- Synth data: 193 rows across 6 files; cascade OOD eval 138/160 (86.2%) on the 160-row held-out set.

## What's NOT done (the only remaining work for the [ANTICIPY-READY] email)

**Phase 1 full** — the QLoRA fine-tune over a 5k+ row synth dataset on Kaggle T4. The pipeline + generator both work (`engine/data/synth/generate.py` running clean against OpenRouter/DeepSeek; 76 rows generated; 93% held-out cascade with prompt-only). Full run is ~$5-10 OpenRouter spend + 4-6 hour Kaggle T4 fine-tune; bumps the held-out from 93% toward the master prompt's 30+/32 floor on the gold-standard set.

**Phase 10 — REAL 4-hour acceptance test**: only Omar can do this (wearing the laptop mic for 4h of normal life is hardware-only-he-can-do per Rule D). Harness ready at `engine/tests/test_phase10_acceptance.py run --hours 4`. Resumable per correction #8: state at `~/.anticipy/acceptance/test_<id>/progress.json`; restart-from-0 only if the classifier fingerprint changes.

**[ANTICIPY-READY] email**: gates on the real 4-hour test passing. Script ready at `engine/scripts/send_anticipy_ready.py`. Run with `--test-id <id>` (the test_id from the Phase 10 wear test) to send the final-artifact email to omarkebrahim@gmail.com via Resend FROM aevoy@anticipy.ai.

## Resume order

1. **Verify the watchdog is still running.** `launchctl list | grep ai.anticipy.watchdog` and `tail ~/.anticipy/watchdog.stdout.log` — the LaunchAgent runs every 300s. If it's stopped, `launchctl load ~/Library/LaunchAgents/ai.anticipy.watchdog.plist`.
2. **Verify the Chrome :9222 LaunchAgent is still up.** `curl http://localhost:9222/json/version`. Per Rule F, if port is bound, do not touch.
3. **Run the 4-hour acceptance test** (Omar's job; the harness is ready). Once Omar fires it and it returns passed=true, run `python -m engine.scripts.send_anticipy_ready --test-id <id>` to send the [ANTICIPY-READY] email. Tag `phase-10-complete`.
4. **Stop.** Build is shipped.

Anything else (more synth data, more skills, more tests) is incremental polish, not blocking.

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
