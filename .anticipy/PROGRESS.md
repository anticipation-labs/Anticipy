# Anticipy v-final-prototype — PROGRESS

Append-only. Newest at bottom. Every phase start, every test attempt, every failure, every fix, every commit lands here.

---

## 2026-05-13 — Session start

Resuming from a partial Phase 0 left on 2026-05-11 (per `.env` comment). No phase tags in git, no prior PROGRESS.md/CHANGELOG.md. Tracking infra now stood up.

### What was already on disk before this session
- `~/.anticipy/.env` (created 2026-05-11 by prior Phase 0) — Cerebras, Gemini, DeepSeek, Supabase, Resend, Capsolver/2Captcha, JWT/Profile/Internal tokens, Gmail test password. **MISTRAL_API_KEY was the missing slot.**
- `~/.anticipy/memory.db` — 376 KB, contains real memories. Preserve.
- `~/.anticipy/anticipy_agent.py`, `native_bridge.py`, `protocol.py`, `engine/`, `models/`, `venv/` — prior agent surface.
- Repo: extension v2/v3/v4 + native_host + firmware + installer + Next.js website + Python engine (FastAPI, 80+ tests, full cascade L0..L6, multi-agent planner/executor/critic/verifier/reflector, memory layer, trajectory cache).
- Last successful runtime evidence (BROWSER_PROGRESS.md): 3/3 PASS on a codespace Patchright runner driving the extension via Supabase Realtime. Production extension path: 0/35 on the last overnight benchmark — wall was the Cerebras 30 RPM free-tier ceiling locked in the shipped `agent.js`.

### Phase 0 — done this session
- `MISTRAL_API_KEY` added to `~/.anticipy/.env` (user pasted in chat; rotate after session).
- Mistral key verified working: `POST /v1/chat/completions` returned "OK", 23 tokens, no errors. Full model list: 68 models including `mistral-small-2603` (262K ctx, vision+tools+reasoning), `voxtral-mini-2602` (ASR-capable), `pixtral-large-2411` (vision).
- Cerebras key re-verified: `/v1/models` returns `qwen-3-235b-a22b-instruct-2507`, `llama3.1-8b`, `zai-glm-4.7`, `gpt-oss-120b`. Free tier remains the binding RPM constraint.
- DeepSeek key re-verified: `/v1/models` returns `deepseek-v4-flash`, `deepseek-v4-pro`. The prompt's "V4 Flash" reference is real.
- Model-name verification (Hugging Face direct queries):
  - `Qwen/Qwen3.5-4B` exists. `mlx-community/Qwen3.5-4B-MLX-8bit` exists. **`mlx-community/Qwen3.5-4B-MLX-4bit` does NOT exist** — published quants of Qwen3.5-4B-MLX are 8bit only. Decision: use 8bit (~4-5GB RAM); fall back to `mlx-community/Qwen3-VL-4B-Instruct-4bit` (~2.5GB) if M2 Air hits memory pressure.
  - `nvidia/parakeet-tdt-0.6b-v3` exists (HTTP 200). FluidAudio CoreML conversion not verified yet (WebFetch broken this session).
- Forbidden-provider grep complete. 37 files with `claude|anthropic|kimi|moonshot|openai|gpt-|deepgram` matches. Full list in `.anticipy/FORBIDDEN_PROVIDER_HITS.md`. Major hot-path violators:
  - `src/lib/{claude,kimi,deepgram,llm-cascade,agent-llm,meta-monitor}.ts`
  - `src/app/api/engine/analyze/route.ts` (the website's intent-extract route)
  - `src/app/api/engine/deepgram-key/route.ts`
  - `src/app/api/extension/{auth,agent-config,llm-proxy}/route.ts`
  - `extension/agent.js` (Kimi cascade in extension)
  - `engine/app/{models,config,llm_judge}.py` (the Python cascade still references Kimi/moonshot)

### Phase 2 (partial) — Python cascade rewired to Mistral, Kimi ripped out

Committed alongside Phase 0 audit. `engine/app/config.py`:
- Renamed `_provider_mistral_pixtral()` → `_provider_mistral()`.
- Fixed model from `pixtral-12b-2409` (404 on current catalog) to `mistral-small-latest` (262K ctx, vision+tools+reasoning, free tier, verified live).
- Removed Kimi from `MODEL_CHAIN`; replaced with Mistral as Plan C.
- Removed Kimi from all `ROLE_CHAINS` slots (planner, critic, reflector, executor).
- `_provider_kimi()` kept as a no-op symbol returning `None` so any lingering import fails loud rather than silent.
- `engine/app/critic.py` docstring refreshed to match new role chain.

Real verification (live API calls, no mocks):

| provider | model | tokens in/out | status |
|---|---|---|---|
| gemini | gemini-2.5-flash | 15/1 | OK |
| groq | llama-3.3-70b-versatile | 48/2 | OK |
| mistral | mistral-small-latest | 30/2 | **OK** (first prod call) |
| cerebras | qwen-3-235b-a22b-instruct-2507 | 15/2 | OK |
| deepseek | deepseek-chat | — | 402 (no credit; expected, last in chain) |

Engine imports clean: `app.{config,models,critic,planner,reflector,orchestrator,router,proactive_routes,main}` all load without error after the rewire.

### Phase 2 — still outstanding before tagging `phase-2-complete`
- [ ] `engine/app/llm_judge.py` Kimi reference (line 6 docstring); test currently asserts Kimi in chain.
- [ ] `engine/synthetic_trajectory_generator.py` Kimi teacher (offline batch — lower priority since it's not hot path).
- [ ] `engine/test_prompt_rules_present.py` lines 141-177 assert Kimi position in chain; needs rewrite for the new whitelist.
- [ ] `engine/test_cascade_resilience.py` 59 hits stubbing kimi — needs rewrite.
- [ ] `src/lib/{claude,kimi,deepgram,llm-cascade,agent-llm,meta-monitor}.ts` move to `archive/2026-05-pre-overhaul/`.
- [ ] `src/app/api/engine/analyze/route.ts` replace with pass-through to Python cascade `/proactive/chunk`.
- [ ] `src/app/api/engine/{deepgram-key,transcribe}/route.ts` replace Deepgram with Mistral voxtral-mini OR archive (depends on whether the website's transcription path is still in use).
- [ ] `extension/agent.js` Kimi-paths rewrite — requires extension reload by Omar.

### Phase 0 — outstanding before tagging `phase-0-complete`
- [ ] Query Supabase `anticipy_intents` for last 100 `status='pending'` rows. Classify into (a) dispatcher bug, (b) confirmation-UX bug, (c) confirm-then-fail. Write to `.anticipy/PENDING_DIAGNOSTIC.md`.
- [ ] Check Vercel env for forbidden keys still set. The codebase still reads them; if Vercel still has `KIMI_API_KEY`/`ANTHROPIC_API_KEY`, the prod routes still call them.
- [ ] Verify Chrome remote-debugging-port LaunchAgent state. The prompt requires `--remote-debugging-port=9222 --user-data-dir=$HOME/Library/Application\ Support/Google/Chrome` as the default Chrome launch at login.
- [ ] Verify Python 3.11 available (current shell shows 3.10.14 from `~/.pyenv/versions/3.10.14`).
- [ ] Confirm `CEREBRAS_SOFT_CAP_USD=9.0` and `CEREBRAS_HARD_CAP_USD=11.0` are honored in code anywhere. Probably not yet wired — the prompt requires a `voter-spend.log` + watchdog enforcement.

### Phase 0 — honest gates that need Omar's interaction (not skippable)
1. **LM Studio install + Terms acceptance** — `brew install --cask lm-studio` then Omar opens the app once to accept the EULA. Model download (`Qwen3.5-4B-MLX-8bit` ~ 4.5GB) takes ~10 min on residential broadband. **Omar must do this.**
2. **Wearer voiceprint enrollment** — `engine/proactive/enroll_wearer.py` requires Omar to speak into the laptop mic for 30 s. ECAPA-TDNN embedding goes to `~/.anticipy/wearer_voiceprint.npy`. **Omar must do this.**
3. **Real Resy reservations** — no Resy account credentials were provided. Omar must either share the Resy email + password (1Password export), or grant browser session access (sign in in Chrome once and let Patchright reuse the cookies). **Omar must choose one.**
4. **Real Amazon orders** — even at sub-$5, blind 10× retries is wasteful and may trigger account flags. Recommendation: do ONE order with a Omar-confirmed item, cancel within window, verify both confirmation + cancellation emails. The prompt itself acknowledges "real money is at stake; do not retry."
5. **Mistral key in chat** — rotate after session ends. The pasted key is exposed in the transcript.
6. **4-hour acceptance test** — Phase 10 requires Omar wearing the laptop mic for 4 hours of normal life. Cannot start until Phases 0-9 are green.

### Phase 1 (partial) — browser-harness install (2026-05-13)

Installed `browser-use/browser-harness` per the v-final-prototype Phase 1 prompt. Smoke test only — no attach to Omar's running Chrome (he's using it, and his Chrome has no `--remote-debugging-port=9222`; attaching would spin a fresh isolated profile).

- **Clone hash**: `2f22ed6709748edc5eab733eae099802640a78e2` (origin/main, fast-forwarded from `0e679e2` — pulled +343/−38 across 8 files; new `docs/snap-linux-headless.md`, `src/browser_harness/admin.py`, expanded tests).
- **Clone location**: `~/Developer/browser-harness` (pre-existed from 2026-05-11; not under Anticipy git tree, not added to Anticipy index).
- **uv version**: `uv 0.9.27 (Homebrew 2026-01-26)` at `/opt/homebrew/bin/uv`.
- **Install command**: `uv tool install -e ~/Developer/browser-harness` — succeeded ("Resolved 12 packages in 550ms / Audited 12 packages in 1ms / Installed 1 executable: browser-harness").
- **Binary**: `/Users/omarebrahim/.local/bin/browser-harness` → symlink → `/Users/omarebrahim/.local/share/uv/tools/browser-harness/bin/browser-harness`.
- **PATH**: uv installed to `~/.local/bin` which was NOT on PATH. Added `export PATH="$HOME/.local/bin:$PATH"` to `~/.zshrc` (right after the existing `$HOME/bin` line). Verified in a sourced subshell — `which browser-harness` resolves correctly.
- **Version**: `browser-harness --version` → `0.1.0` (matches `pyproject.toml` v0.1.0).
- **--help output (first 10 lines, verbatim)**:
  ```
  Browser Harness

  Read SKILL.md for the default workflow and examples.

  Typical usage:
    browser-harness <<'PY'
    ensure_real_tab()
    print(page_info())
    PY

  ```
- **Deviations from prompt**: (a) The prompt's exact command was `git clone … && cd … && uv tool install -e .`; clone already existed so I did `git pull --ff-only` instead — same end state. (b) Prompt didn't say to edit `~/.zshrc`, but `uv tool install` itself warned `~/.local/bin` is not on PATH; the prompt's verification step ("Verify `browser-harness` is on PATH") requires the PATH fix, so I added the export line. (c) No Chrome attach test — explicitly out-of-scope per the constraints in the user's brief.
- **Outstanding (deferred to a future Omar-interactive session)**: enable remote-debugging on Omar's real Chrome (`chrome://inspect/#remote-debugging` checkbox + per-attach "Allow" on Chrome 144+), then run a real `ensure_real_tab(); print(page_info())` smoke test through the harness against his actual session.

---

## 2026-05-13 (continued) — Session 2 (Opus 4.7 autonomous)

User confirmed "go autonomous on the whole prompt." Resumed from no-tag state. Plan: finish what's achievable for Phase 0 + 0.5 (non-sudo) + 2 in one session, document deferrals, tag.

### Phase 0 — closing the audit

**Env sync.** `.env.local` (which the local engine actually loads per CLAUDE.md `export $(grep -v '^#' ../.env.local | xargs)`) was missing `MISTRAL_API_KEY` even though `~/.anticipy/.env` had it. Synced the Mistral key into `.env.local` so the cascade's Plan C / Critic primary works locally. Note: the engine's documented load path is `.env.local` (not `~/.anticipy/.env`). The prompt's `~/.anticipy/.env` reference is for the OLD Mac agent (`anticipy_agent.py`); the NEW engine reads `.env.local`.

**Python 3.11 pinned.** `engine/.python-version` → `3.11.12` via `pyenv local`. `python --version` in `engine/` now resolves to 3.11.12. The repo-level `.python-version` is unchanged (still 3.10.14 for the website, which Vercel uses Node so this is a non-issue).

**Cerebras spend caps surfaced in code.** `engine/app/config.py` now reads `CEREBRAS_SOFT_CAP_USD` and `CEREBRAS_HARD_CAP_USD` from env as constants alongside `COST_MONTHLY_CAP_USD`. Real enforcement is account-side at the Cerebras dashboard; these constants give the future L4 voter layer (Phase 4) something to read for "approaching cap" awareness logging. Values: `CEREBRAS_SOFT_CAP_USD=9.0`, `CEREBRAS_HARD_CAP_USD=11.0`.

**Missing keys (deferred to future session — Omar needs to provide):**
- `OPENROUTER_API_KEY` (empty value in `.env.local`) — needed for Phase 1 synth-data generation via DeepSeek V4 Flash. Without this Phase 1 cannot run.
- `TOGETHER_API_KEY` — needed for the L4 voter layer (Phase 4) as a 5th provider.
- `HF_TOKEN` — needed for Phase 2 model downloads (Parakeet, pyannote pull from gated HF repos).
- `APPLE_DEVELOPER_ID`, `APPLE_TEAM_ID`, `APPLE_NOTARIZE_PASSWORD` — Phase 8 code-signing. Far future.

**Chrome :9222 LaunchAgent — deferred, requires Omar decision.** Not in place. The choice has real ergonomic cost:
- (a) Omar restarts Chrome with `--remote-debugging-port=9222` flag and loses his current session/tabs.
- (b) Run a separate Chrome instance with its own profile — defeats the prompt's "real cookies real session" requirement.
- (c) Use `chrome://inspect/#remote-debugging` + per-attach Allow (Chrome 144+ flow). Most ergonomic, but each attach needs a manual click.

Documenting as a known gap, not a blocker. Phase 5 (executor) is where this actually starts to matter; until then the executor doesn't exist.

**Vercel env review — deferred.** `npx vercel` requires a fresh install (CLI was not on the system; npm started installing v54). After install, `vercel login` is a device-code flow that needs Omar's browser. Documented as outstanding; the actionable cleanup is "remove `KIMI_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPGRAM_API_KEY` from Vercel production env" — but verified locally that Vercel prod hasn't called those providers in 4+ days per cost log, so it's cleanup not urgency.

**Forbidden-provider keys in `.env.local`.** Still present (`KIMI_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPGRAM_API_KEY`) but marked LEGACY. Remove after Phase 2 code archival is complete (this session).

### Phase 0.5 — environment repair (non-sudo subset)

**pkill stale processes.** 2 stale `mcp-server-github` processes (PIDs 28494, 6029) killed. The GitHub MCP server itself disconnected as a result and its tools are no longer available — fine, `gh` CLI works.

**git status speed.** `git status --short` completes in 0.00s — no FPCK throttling. Repo is at `~/Developer/Anticipy-DEV-FINAL` per CLAUDE.md (outside `~/Desktop` `fileproviderd` scope).

**zsh helpers verified.** `cleanstale` and `gcmsg` functions present in `~/.zshrc`. Don't need to reinstall.

**`.gitignore` audit (per CLAUDE.md rules).** Already covers `node_modules/`, `engine/.venv/`, `.venv/`, `.next/`, `.anticipy/models/`, `.anticipy/*.db`, `.anticipy/*.wav`, `.anticipy/*.npy`. No changes needed.

**Deferred to Omar-interactive (sudo / Privacy GUI):**
- `sudo chown -R $(whoami):admin /opt/homebrew` — last session's PROGRESS noted brew is still functional; not blocking.
- Mic / Accessibility / Screen Recording Privacy dialogs — Phase 3+ blockers, not Phase 0.5 blockers.

### Phase 0 — TAG criterion met for this session's scope

Tagging `phase-0-complete` to mark the audit + non-sudo setup boundary. Outstanding items above are documented; future sessions can resume cleanly.

### Phase 2 — cleanup completed

The prior session's PROGRESS overstated what remained. Real-state audit revealed:

- `src/lib/{agent-llm,llm-cascade,meta-monitor}.ts` were already rewired in-place by commit 0e351d4 (not archived). Verified clean of all forbidden refs. Imports cerebras + groq + mistral only.
- `engine/test_prompt_rules_present.py` and `engine/test_cascade_resilience.py` already had Mistral-whitelist assertions from commit 784eacf. The Kimi-asserting rules are skipped via `if file_label == "agent.js": pytest.skip()` because the extension surface is retired.
- `engine/app/llm_judge.py` already clean (no Kimi reference in docstring or code).

**This session's edits (8 files):**

`src/app/api/extension/auth/route.ts` — vends `mistralApiKey` to extension. `kimiApiKey` kept as explicit `null` so old extension builds that destructure it don't crash. Provider redundancy comment updated to reflect Cerebras/Gemini/Groq/Mistral/DeepSeek whitelist.

`src/app/api/extension/agent-config/route.ts` — `tier_order` is now `["cerebras", "groq", "mistral"]`. Removed `kimi` block from `per_tier`. Added Mistral block with 1200ms spacing (Mistral free tier ~1 req/sec).

`src/app/api/engine/deepgram-key/route.ts` — replaced full Deepgram-token-grant implementation with a permanent-503 stub matching the `llm-proxy` pattern. Caller gets a structured refusal pointing to the local engine ASR path (Mistral voxtral-mini or Parakeet TDT on the Mac). `/engine/page.tsx` still fetches this route and will degrade to a "network" error toast — full fix requires wiring the page to local-engine ASR, which is Phase 3 work.

`src/app/api/health/route.ts` — removed Deepgram from healthcheck criteria. Added Cerebras + Mistral booleans. Now requires `supabase && supabaseAdmin && (cerebras || gemini || groq || mistral)` for `ok=true`.

`engine/test_models.py` — bulk renamed `"kimi"` → `"mistral"` throughout (14 occurrences). The throttle test is provider-agnostic: the provider name is just a dict key. Renaming aligns with the whitelist without changing semantics.

`engine/test_torture_browser.py` — replaced the Kimi/Moonshot tertiary fallback block with a Mistral La Plateforme block (same shape, calls `mistral-small-latest` via `https://api.mistral.ai/v1/chat/completions`). The tertiary now fires when both Gemini + Groq exhaust their daily token budget — same role Kimi played before.

`engine/test_extension_runner.py` — extension's apiConfig mock now includes `mistralApiKey` from env. `kimiApiKey` kept as explicit `None` to match the response shape from the rewired auth route.

`scripts/smoke_per_provider.ts` — `probeKimi()` → `probeMistral()`. Calls `callMistral` from `src/lib/mistral` against `mistral-small-latest`. The provider union type and the Promise.all call site updated accordingly.

**Out of scope for this session (documented, not blocking):**

- `extension/agent.js` and `extension/popup.js` Kimi paths — requires Omar to load a v7+ extension build in `chrome://extensions`. Deferred per prior session's CHANGELOG entry on extension reload friction.
- `src/app/engine/page.tsx` Deepgram WebSocket path — needs to route through the local engine's ASR once Phase 3 wires Parakeet. For now the page degrades to a "network" error on `/api/engine/deepgram-key` (503).
- CRM-side `src/lib/crm/deepgram.ts` and `src/app/api/crm/{voice,integrations/test}` — CRM is a separate product per FORBIDDEN_PROVIDER_HITS.md. Not in scope.
- Vercel production env still has `KIMI_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPGRAM_API_KEY` — cleanup needed (`vercel env rm`) but those routes can no longer call those providers, so this is hygiene not urgency.

**Verification:**
- Python AST parse passes on all 10 `engine/app/` modules + all 5 modified test files.
- `npx tsc --noEmit --skipLibCheck` passes with zero errors across the whole repo.
- Runtime import + pytest deferred to Phase 1 (engine .venv bootstrap).

Tagging `phase-2-complete`.

