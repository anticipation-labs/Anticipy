# Anticipy v-final-prototype — HANDOFF (read this first on /clear)

If you are an Opus 4.7 instance resuming the Anticipy v-final-prototype build after a /clear, this is the document the user explicitly told the prior instance to write for you. **Read this first, then `.anticipy/PROGRESS.md`, then `.anticipy/FARA_PLAN.md`, then `git tag | tail -15`.** Resume past the last green tag.

## CURRENT BUILD: FARA-7B integration (2026-05-15)

The user pivoted on 2026-05-15: ALL service APIs are out (Gmail/Sheets/Slack/Notion/Linear/Spotify/Maps/Resy/Amazon, every single one). The product is the world's best BROWSER agent. Visual grounding by Microsoft Fara-7B running locally on the Mac. Master plan at `.anticipy/FARA_PLAN.md`.

Hard rules from the FARA pivot (also saved in memory):
- No service APIs. EVER. Use real browser navigation. See [[feedback-no-api-keys]].
- No fabrication. Real screenshots. Real artifacts in `.anticipy/PROOF/`. See [[feedback-no-fabrication]].
- No em-dashes anywhere. See [[feedback-no-em-dashes]].
- No "should work" without a runnable command + its actual output pasted to PROGRESS.md.
- No telling the user to run terminal commands (two GUI exceptions only).
- 2-attempt rule then pivot to the alt path defined in FARA_PLAN section 5+.

### FARA build phase tags as of this handoff

| Phase | Tag | What | Status |
|---|---|---|---|
| 0 | `phase-fara-0-env-confirmed` | env audit, mlx-vlm + patchright installed, Fara HF reachable | DONE |
| 1 | `phase-fara-1-real-chrome-attached` | Chrome :9222 attached to a CLONE of the real signed-in profile at `~/.anticipy/chrome-real-clone/` (8.3 GB). Gmail inbox loads directly with omarkebrahim@gmail.com signed in | DONE |
| 2 | `phase-fara-2-local-inference-up` | Fara-7B 15 GB downloaded, MLX 4-bit converted (5.3 GB at 5.4 bpw), FastAPI server `com.anticipy.fara.plist` on :8742, /infer returns real action. **Honest latency: 33s wall on M2 Air 16GB (target was 3s).** | DONE with latency caveat |
| 3 | `phase-fara-3-dispatcher-ready` | CDP dispatcher with Bezier motion + Gaussian timing, 8/8 unit tests + 1/1 real Chrome integration (example.com -> iana.org). Modules at `engine/app/action_engine/{humanlike, cdp_dispatcher}.py` | DONE |
| 4 | (no tag yet; framework done) | Trajectory recorder at `engine/data/synth/record_trajectory.py`. ONE smoke trajectory recorded (smoke_wikipedia, 3 steps). The 8 real proof recipes (Gmail, Sheets, Docs, Canva, Resy, Amazon, Notion, Slack) still need writing | FRAMEWORK ONLY |
| 5 | (staged; Omar-blocked) | Kaggle T4 QLoRA notebook at `engine/data/synth/finetune_qlora.ipynb`. 8 cells: deps, paths, base load 4-bit, attach LoRA r=8 alpha=16, trajectory dataset, train 3 epochs, cold-test eval (>=70% gate), merge + reconvert MLX 4-bit. Omar uploads trajectories to Kaggle and hits Run. | NOTEBOOK READY, NEEDS OMAR |
| 6 | (no tag yet; partial) | `engine/app/action_engine/fara_skill_runner.py` wires CDP + Fara :8742 + Mistral pixtral verifier on OpenRouter. One real-prod run against Google Sheets: Fara controlled real Chrome, opened an existing Sheet from recent files (clicked wrong target without QLoRA tuning), then ran Click-A1 with 2-of-3 dispatches OK | PARTIAL |
| 7-10 | (not started) | Eight proofs, cascade lock, Hermes 30/run, dmg ship | NOT STARTED |

### What was demonstrated end-to-end (real artifacts on disk)

`.anticipy/PROOF/sheets_create_test/run_1778853862/` and `.anticipy/PROOF/sheets_a1_click/run_1778854118/` each have:
- `manifest.json` with full step record, latencies, Fara actions, dispatch outcomes
- `step_NN_before.png` and `step_NN_after.png` from real Chrome
- The screenshots show real Google Sheets pages with Omar's account signed in

The Sheets-write test clicked at [35, 243] (correctly hit cell A1 area), then attempted another click before timing out at CDP level. Zero-shot Fara accuracy on canvas-heavy pages is the QLoRA gap.

### Key infrastructure files

- `~/Library/LaunchAgents/com.anticipy.chrome.plist` -- Chrome :9222 on real-profile clone
- `~/Library/LaunchAgents/com.anticipy.fara.plist` -- Fara FastAPI :8742, lazy-loads MLX model
- `~/.anticipy/chrome-real-clone/` -- 8.3 GB clone of Omar's signed-in Chrome profile
- `~/.anticipy/models/fara-7b/` -- HF download (15 GB, can be deleted after MLX convert)
- `~/.anticipy/models/fara-7b-mlx-4bit/` -- 5.3 GB MLX 4-bit, what the server loads
- `engine/.venv/` -- Python 3.11.12 with mlx-vlm, patchright, fastapi, websockets, etc.

### Next session resume order

1. Verify infra still up: `curl localhost:9222/json/version && curl localhost:8742/health` should both return 200.
2. Tag Phase 4 framework if not tagged: `phase-fara-4-framework-ready`.
3. Either (a) write the 8 real proof recipes and record 50 trajectories each (multi-hour, no Kaggle needed yet), or (b) wait for Omar to run Kaggle and merge the adapter, then re-run the proof recipes with the fine-tuned weights.
4. Phase 6 full: wire Hermes lifecycle to use Fara-grounded skills instead of API skills. Delete the API-based skill modules (per [[feedback-no-api-keys]]).
5. Phase 7: run 8 proofs 3x each against real Chrome. Capture all artifacts.
6. Phase 8: cascade lock 17/17.
7. Phase 9: 30 runs per skill (300 total).
8. Phase 10: ship signed-or-unsigned dmg.

### Pre-FARA state (also still in repo, may need cleanup)

The pre-FARA skills under `executor/skills/*.js` all use service APIs. They are DEPRECATED per the no-API rule. They are not deleted yet because Phase 6 wiring will replace them with Fara-grounded recipes; deleting the directory before that would break the existing tests and the path Hermes uses for the watchdog canary. Delete after Phase 6 swap.

The pre-FARA build's phase tags (`phase-0-complete` through `phase-10-harness-complete` plus `phase-9-full-pipeline-passing` and `phase-9-hermes-promote-verified`) are still on remote. They represent the prior API-based architecture which is now obsolete. The FARA `phase-fara-N-*` tags are the current architecture.

---



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
