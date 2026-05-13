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

