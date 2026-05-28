# Anticipy Action Engine — Problem Map

**Goal**: A browser agent that operates on the user's real Chrome, runs millions of tasks per year for ≤$99 total, completes every task end-to-end, beats Anthropic Computer Use / OpenAI Operator / Adept on the user's task distribution.

This document maps every binding constraint we've hit, what success looks like on each axis, and where we need to do research.

---

## A. Cost

**Today**: $0.005–$0.06 per task on paid models. Free tiers cap at 30–500k tokens/day per provider.

**Target**: $99/year for 1M tasks → **$0.0001 per task** (1/100 of a cent).

**Math gap**:
- Browser Use sends ~12–18k tokens per LLM call (DOM + screenshot + prompt + history)
- Tasks need 5–20 LLM calls
- Per-task tokens: ~60k–360k
- Even at DeepSeek's $0.14/MTok input, 1M tasks × 100k tokens = **$14,000/year**. ≥140× too expensive.
- At gpt-4.1-mini ($0.40/MTok input): ~$40,000/year. ≥400× too expensive.

**What has to change for the math to work**:
- Compress per-task tokens to ~500–1500 (10–30× reduction)
- Cache trajectory patterns so 95%+ of tasks bypass the LLM after the first one of its kind
- Pool free-tier daily quotas across 5–10 providers

---

## B. Browser

**Today**: Two paths, both broken for production.

1. **Extension path** (what user actually wants): agent.js shipped with hardcoded Cerebras-first, 2s spacing, 30 RPM ceiling. Locked code → can't change without reload. User authorized one reload last night, said "no more."
2. **Codespace path** (what I demoed today): server-side Patchright Chromium with virtual display. Works but doesn't run on user's machine, so it's fake from his POV.

**Target**: User's real Chrome, real cookies, real account state, no extension reloads, no on-screen takeover that disrupts what user is doing.

**Specific browser-layer problems**:
- Cookie/session reuse without leaking credentials to server
- Stealth (DataDome, Akamai, Cloudflare detection)
- Captcha solving without a paid CAPTCHA service
- Canvas-heavy apps (Sheets, Figma, Gmail rich compose)
- Multi-tab orchestration
- Recovery from "page changed under me"

---

## C. Quality

**Today**: Best server-side run we got was 3/5 real PASSes today (Wikipedia, DDG, books.toscrape) on the codespace path before Groq TPD cap hit. Extension path: 0/35 last night.

**Target**: 100% on user's hard tasks (canvases, multi-step click flows, web geos, cross-site research). Better than the SOTA academic benchmarks (Online-Mind2Web, WebArena).

**Quality failure modes we've seen**:
- Agent hallucinates "I found the answer" without quoting verbatim values
- Can't recover when first plan fails (the loop hits MAX_FAILS without trying a different angle)
- Vision-less models (Cerebras Qwen) can't navigate even simple search flows
- Verifier too strict (used to fire critic on every step)
- Verifier too lax (accepts a generic "completed" message as success)

---

## D. Reliability

**Today**: Inconsistent. Same task can pass or fail depending on Cerebras RPM at the moment, Gemini cap status, Groq TPD remaining. Run-to-run variance is huge.

**Target**: Same task → same outcome 99%+ of the time. Provider hiccups are absorbed silently.

**Reliability failure modes**:
- Single-provider failure cascades to whole task failure
- Hard timeouts (240s per task) catch slow-but-correct runs as fails
- Extension agent gives up after 2 attempts per tier; no graceful degradation
- No memoization: same task pattern, same failure 100 times in a row

---

## E. RPM (rate per minute)

**Today**: Cerebras free 30 RPM, Groq free 30 RPM. Bursty patterns (benchmark fires 25 tasks back-to-back) saturate immediately.

**Target**: No effective RPM ceiling. Either via cache (most calls don't happen), provider pool (5+ providers × 30 RPM = 150 RPM), or self-host (no RPM).

**RPM failure modes**:
- Agent.js's 2000ms spacing + Cerebras-first = exactly the 30 RPM cap; first 429 cascades to ai_unavailable
- Test harness's pre-flight + verification calls double-count against the same RPM bucket as the agent

---

## F. Quotas

**Today**: Tokens-per-day caps are the real constraint, worse than RPM.

| Provider | Model | Daily token cap (free) |
|---|---|---|
| Cerebras | Qwen3-235B | 1M tok/day |
| Groq | llama-4-scout | 500k tok/day |
| Groq | llama-3.3-70b-versatile | ~30k tok/min × 14400 RPD |
| Gemini | 2.5 Flash | project spending cap (hit) |
| Kimi | moonshot-v1-128k | balance-based ($0 = dead) |
| DeepSeek | V3 | balance-based ($0 = dead) |

Browser Use sends ~12k tokens per call. **Groq llama-4-scout dies after 4 tasks. Cerebras after 8 tasks (text-only).**

**Target**: Effective infinite per-day capacity via (1) cache hit ratio >95%, (2) provider rotation pool, (3) drastically smaller per-call token footprint.

---

## Cross-cutting: What "billion-dollar companies" haven't solved

- **OpenAI Operator**: $200/mo, runs in their cloud, not user's Chrome
- **Anthropic Computer Use**: paid API, single provider, screenshot-heavy ($$$)
- **Adept ACT-1**: pivoted, probably dead
- **Browser Company / Dia**: macOS only, closed, expensive
- **Multi-On**: gone

**Their gap = our wedge**: they all assume server-side compute and ignore the cost ceiling. None of them are designed for $99/yr with millions of tasks.

---

## Research targets (what to study, where to piggyback)

For each axis we should figure out which open-source project or small startup has already solved it, and what we can copy / fork / wrap.

- **A. Cost**: Firecrawl (cheap page→markdown), Reader-LM (Jina), DeepSeek-V3 batch pricing, OpenRouter free tier rotation, Cerebras paid vision options, self-hosted Qwen3-VL on cheap GPU
- **B. Browser**: Browser Use 0.12 internals, Stagehand (Browserbase), LaVague, Skyvern, browserbase.com, Anchor Browser, Hyperbrowser, Patchright stealth tricks
- **C. Quality**: Online-Mind2Web SOTA papers, ABP (adversarial best-of-N), SeeAct, Reflexion variants, multi-agent verifier+critic patterns
- **D. Reliability**: Production agent retry patterns from Stagehand, Browser Use, Operator (leaked tactics), circuit breakers, idempotency keys
- **E. RPM**: Provider rotation patterns (LiteLLM, OpenRouter), self-host on Cerebras Inference Cloud or DeepInfra Serverless
- **F. Quotas**: Trajectory caching patterns (RAG over past wins), task-pattern memoization, hindsight relabeling, Reflexion lesson distillation

---

## Honest current state

- 0/35 on user's extension last night (Cerebras RPM ceiling locked in shipped agent.js)
- 3/5 on codespace path today (Wiki Python, DDG search, books.toscrape — then Groq TPD cap killed it)
- Architecture (Browser Use + Patchright + LLM cascade) works when the LLM is alive
- $99/year for 1M tasks is achievable ONLY with compression + caching + pool — not with provider swaps

---

## Next step

Pick which axes to research first (likely all in parallel via subagents). Goal of research pass: name 3 specific tools/projects/startups per axis we should consider piggybacking on. After research → architecture decision → build.
