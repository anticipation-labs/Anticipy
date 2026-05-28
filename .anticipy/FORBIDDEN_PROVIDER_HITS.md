# FORBIDDEN_PROVIDER_HITS

Grep `claude|anthropic|kimi|moonshot|openai|gpt-[0-9]|deepgram` across `*.py,ts,tsx,js,mjs,json` (excluding `node_modules`, `.next`, `archive`, `venv`, `.venv`).

**254 total hits across 37 unique files** (2026-05-13).

## Important context from production cost log

Last 4 days of LLM traffic via `engine_cost_log` (322 rows):

| provider | model | calls | spend USD | last call |
|---|---|---|---|---|
| gemini | gemini-2.5-flash | 218 | $0.0276 | 2026-05-11 19:33 |
| groq | llama-3.3-70b-versatile | 85 | $0.0439 | 2026-05-11 19:33 |
| cerebras | qwen-3-235b-a22b-instruct-2507 | 19 | $0.0000 | 2026-05-11 04:16 |
| kimi/moonshot/claude/openai/deepgram | — | **0** | — | — |

**Kimi, Moonshot, Claude, OpenAI, Deepgram were NEVER actually called in this window.** All forbidden-provider hits in code are dead paths. Phase 2 archival is a cleanup, not a runtime change. This significantly lowers the risk of the archival step.

## Hits per file (descending)

| hits | file | category |
|---|---|---|
| 59 | engine/test_cascade_resilience.py | test (stubbed kimi, no live calls) |
| 21 | extension/agent.js | **hot path — real `_callKimi` w/ moonshot URL** |
| 16 | __tests__/claude-routing-bench.ts | test (calls `callClaude`) |
| 14 | src/app/api/engine/analyze/route.ts | **hot path — /engine page POSTs here** |
| 14 | engine/test_models.py | test |
| 14 | engine/app/config.py | **hot path — provider chain definition** |
| 12 | engine/test_torture_browser.py | test (live kimi URL) |
| 10 | src/lib/claude.ts | **hot path — Claude module** |
| 9 | scripts/smoke_cascade_fallover.ts | smoke (calls kimi via cascade) |
| 7 | src/lib/llm-cascade.ts | **hot path — cascade orchestrator** |
| 7 | src/lib/agent-llm.ts | **hot path — agent LLM wrapper** |
| 6 | src/lib/kimi.ts | **hot path — Kimi module** |
| 6 | scripts/smoke_per_provider.ts | smoke |
| 6 | engine/test_prompt_rules_present.py | test (asserts kimi in chain) |
| 5 | src/lib/meta-monitor.ts | **hot path — meta monitor** |
| 5 | src/app/api/extension/llm-proxy/route.ts | **hot path — extension proxy to Claude** |
| 5 | engine/synthetic_trajectory_generator.py | offline batch (kimi teacher) |
| 4 | .claude/settings.local.json | unrelated (Claude Code settings) |
| 3 | src/app/api/extension/auth/route.ts | **hot path — extension auth** |
| 3 | scripts/test_llm_cascade_unit.ts | test |
| 3 | extension/test_provider_quota.mjs | test |
| 2 | src/lib/groq.ts | (Groq, not forbidden — `groq.com/openai/v1` URL false-positive) |
| 2 | src/app/engine/page.tsx | **hot path — /engine UI** |
| 2 | src/app/api/health/route.ts | health check |
| 2 | src/app/api/extension/agent-config/route.ts | **hot path — server-driven config** |
| 2 | src/app/api/engine/deepgram-key/route.ts | **hot path — Deepgram key vending** |
| 2 | src/app/api/crm/integrations/test/route.ts | CRM (separate product) |
| 2 | scripts/probe_planC.ts | smoke |
| 2 | extension/popup.js | **hot path — popup stores kimiApiKey** |
| 2 | engine/app/models.py | **hot path — cascade impl** |
| 1 | src/lib/deepgram.ts | **hot path — Deepgram module** |
| 1 | src/lib/crm/deepgram.ts | CRM Deepgram |
| 1 | src/app/api/engine/transcribe/route.ts | **hot path — audio transcription** |
| 1 | src/app/api/crm/voice/route.ts | CRM |
| 1 | engine/test_prompt_rules.py | test |
| 1 | engine/test_extension_runner.py | test runner |
| 1 | engine/app/llm_judge.py | **hot path — LLM judge** |

## Phase 2 archive list (hot-path only — tests stay until rewritten)

These go into `archive/2026-05-pre-overhaul/` via `git mv`:

```
src/lib/claude.ts
src/lib/kimi.ts
src/lib/deepgram.ts
src/lib/crm/deepgram.ts
src/lib/llm-cascade.ts          # depends on claude/kimi modules
src/lib/agent-llm.ts            # depends on claude/kimi
src/lib/meta-monitor.ts          # depends on claude
src/app/api/engine/analyze/route.ts          # to be replaced by Python-cascade pass-through
src/app/api/engine/deepgram-key/route.ts     # Deepgram retired; replaced by Mistral voxtral or Parakeet local
src/app/api/engine/transcribe/route.ts       # Deepgram-backed
src/app/api/extension/llm-proxy/route.ts     # Claude proxy; new architecture publishes via Realtime
src/app/api/crm/voice/route.ts               # CRM Deepgram (CRM is separate product; archive only if confirmed dead)
```

Engine Python cascade needs in-place rewrite (not archive):
```
engine/app/config.py            # rip MODEL_CHAIN's kimi/deepseek-paid slots; insert Mistral
engine/app/models.py            # rip _call_kimi style helpers; add _call_mistral
engine/app/llm_judge.py         # swap kimi judge to Mistral or Gemini
```

Extension `agent.js` needs a hot-path rewrite to drop Kimi entirely. Cannot be done by server prompt updates — needs an extension reload.

`__tests__/claude-routing-bench.ts`, `scripts/smoke_*.ts`, `engine/test_*` — these are tests that exercise the forbidden paths. They get archived alongside their targets OR rewritten against the new whitelist providers in Phase 8.

`.claude/settings.local.json` — unrelated. It's the Claude Code harness settings. NOT a code reference to the Anthropic API. Skip.

## Decision: defer the extension rewrite

The extension is v4 (per recent commits). Rewriting `agent.js` to drop Kimi entirely requires:
1. New zip build (`anticipy-v6/EXTENSION-LOAD-THIS-IN-CHROME/`)
2. Omar reloads at `chrome://extensions`

Per the prior session log: each extension reload is a real friction point and a real risk. The right time to bundle this rewrite is AFTER the new architecture (cascade rewire + Mistral + Phase 1 local stack) is verified server-side. Until then, the extension still works against the existing server endpoints — the Kimi paths just don't fire (no kimi key in env).
