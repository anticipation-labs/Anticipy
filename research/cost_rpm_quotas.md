# Browser Agent Cost / RPM / Quota Research — May 2026

**Goal:** $99/year for 1M tasks = $0.0001/task. Currently $0.005-$0.06/task with paid LLMs.

**The math we're up against:** Browser Use sends 12-18k tokens per LLM call, 5-20 calls/task = 60k-360k tokens/task. 1M tasks * 100k tokens = 100B tokens/year. Even at DeepSeek's $0.14/MTok input, that's $14k/year — 140x over budget.

**The escape hatch:** the per-task token count is the real lever, not the per-token price. Cutting to 1k-3k tokens/task changes the math from impossible to plausible.

---

## TL;DR — Best Stack to Hit $99/year

The path is **route-by-task-class + token-shrinking observation layer + multi-provider free tier with quota-aware router**:

1. **First: classify the task.** ~60-70% of "tasks" are read-only ("summarize this Reddit thread", "find cheapest USB-C cable on Amazon"). These do NOT need a browser agent loop — route them to **Jina Reader (free, r.jina.ai prefix)** + a small text LLM. Cost: ~$0.00002/task.
2. **For action tasks: replace the perception layer.** Drop Browser Use's full DOM+screenshot model in favor of an accessibility-tree snapshot (a la Vercel **agent-browser** / Microsoft **Playwright CLI**) — 200-400 tokens/page vs 12-18k. Tasks shrink from 100k tokens to 5-15k tokens.
3. **Cache successful trajectories.** Stagehand-style action caching: hash (URL + DOM fingerprint + intent), reuse selector without LLM. ~80% cost reduction on repeat workflows. Build this in-house in ~200 LOC because the open-source one is locked to Browserbase.
4. **Multi-provider free-tier router.** **LiteLLM** as the gateway, **FreeLLMAPI**'s pattern (RPM/RPD/TPM/TPD-aware round robin) across: Gemini 2.5 Flash (vision, free), Cerebras Qwen3-235B (1M tok/day, no vision), Groq Llama 4 Scout (vision, free), Mistral Pixtral 12B (1B tok/MONTH free), Cloudflare Workers AI (10k neurons/day, vision). Stack 5+ providers, never pay.
5. **Paid spillover floor:** Llama 3.2 11B Vision @ $0.049/MTok (Meta's own API or Together) for the bottom 5% of traffic that exhausts every free tier.

**Per-task target with this stack:**
- Read-only tasks (~70%): Jina Reader + Cerebras Qwen3 → ~3k tokens, free
- Action tasks (~25%): accessibility-tree + Gemini 2.5 Flash free → ~10k tokens, mostly free
- Repeat workflows (~5%): cache hit, ~0 tokens, free
- Annual blended cost: **~$50-150/yr at 1M tasks** if free tiers hold; ~$2k-5k if all paid. The free tier stack is the only realistic path to $99.

---

## A. COST — Top 3 Tools/Services

### A1. Jina Reader API (`r.jina.ai`)
- **Link:** https://jina.ai/reader/ , https://github.com/jina-ai/reader
- **What it solves:** Read-only "fetch + summarize" tasks bypass the full agent loop. Prepend `r.jina.ai/` to any URL → get clean LLM-ready Markdown.
- **Pricing:**
  - Free without API key: **20 RPM**
  - Free with API key: **500 RPM** + 10M onboarding tokens
  - Paid: token-based, ~$0.02/M output tokens (very cheap)
- **Self-hostable alternative:** ReaderLM-v2 (1.5B params, Apache 2.0, runs on a T4 — 67 tok/s input). Self-host for zero per-call cost.
- **Anticipy integration:** Add a router layer. If task classifier returns `read_only` (regex: "summarize", "what does X say", "find on page", "search for"), hit `r.jina.ai/{url}` → small text LLM. Skip browser agent entirely. Would absorb ~60-70% of tasks at near-zero cost.

### A2. Vercel agent-browser / Microsoft Playwright CLI (accessibility-tree observation)
- **Links:** https://github.com/vercel-labs/agent-browser (Apache 2.0, Rust CLI), https://github.com/microsoft/playwright-mcp
- **What it solves:** The biggest cost driver isn't the LLM price — it's that Browser Use ships 12-18k tokens of DOM+screenshot per step. Accessibility-tree snapshots are **200-400 tokens/page**.
- **Measured savings:**
  - Playwright CLI vs Playwright MCP: ~27k vs ~114k tokens for same 10-step task = **4x reduction** (Microsoft benchmark)
  - agent-browser vs Playwright MCP on 7-step workflow: ~105k-175k vs ~350k tokens = **~2-3x reduction**, ~$0.52-0.88 vs $1.75/run on GPT-4o
  - Format example: `- button "Submit" [ref=e2]` — agent says `click @e2` instead of parsing HTML
- **Caveat:** agent-browser is CLI-only (no library API); Playwright MCP is a library you can import. For Anticipy's Python wrapper we'd shell out to one or wrap Playwright's `accessibility.snapshot()` directly — that's a few-hundred-LOC change to `engine/app/agent.py`.
- **Anticipy integration:** Replace Browser Use's `browser_state` with a Playwright accessibility-tree snapshot. Drop screenshots from default path, only attach when an action returns `unable_to_locate`. This single change is the highest-leverage cost cut available — turns 100k-token tasks into 5-15k-token tasks.

### A3. Stagehand-style trajectory cache (in-house build)
- **Reference link:** https://www.browserbase.com/blog/stagehand-caching , https://docs.stagehand.dev/v3/best-practices/cost-optimization
- **What it solves:** Repeat tasks (same site, same intent) re-run the LLM unnecessarily. Cache the LLM-resolved selector + page-fingerprint, replay without LLM call.
- **Measured savings:** ~**80% speedup on second run**, ~**30% cost reduction across mixed repeat workflows** (Browserbase data).
- **Cache key:** SHA256 of (method, normalized URL, DOM hash, intent text). On hit, execute with cached selector. On miss (DOM drifted), fall through to LLM, store new entry. 48h TTL.
- **Why build vs adopt:** Browserbase's implementation is server-side on their managed service. Open-source Stagehand can replay but the real cache infra is paid. The whole pattern is ~150-300 LOC in Python — just need Redis or SQLite.
- **Anticipy integration:** Add `engine/app/trajectory_cache.py`. Hash `(host, normalized_url, dom_fingerprint, intent_embedding)` → cached `(action, selector)`. Hit before LLM call. For Anticipy's likely workload (users repeating "book a usual table at X", "buy my usual coffee from Y"), expected hit rate **40-60%** — translates to ~50% LLM call reduction.

### Honorable mentions (cost):
- **DeepSeek V3:** $0.14 input / $0.28 output per MTok. Cheapest non-vision capable LLM; useful for the planner/critic side. NO native vision.
- **Pixtral 12B (paid Mistral):** $0.10/$0.10 per MTok — cheapest paid vision LLM with healthy throughput.
- **Llama 3.2 11B Vision (Meta direct):** $0.049/$0.049 per MTok — actually the cheapest paid vision model. But shaky uptime.
- **Self-hosted Qwen2.5-VL 7B on RunPod L40S serverless:** $1.90/sec ≈ $0.000079/sec. At 5 tok/sec/req with batching, breaks even with paid APIs around ~10-50M tok/day.
- **Firecrawl:** Hobby = $9/mo for 5k credits. **Too expensive** at scale ($1.80/1k pages even after volume discount); Jina dominates.

---

## E. RPM — Top 3 Tools/Services

### E1. LiteLLM Router + Proxy
- **Link:** https://docs.litellm.ai/docs/routing
- **What it solves:** Single OpenAI-compatible endpoint that load-balances across N provider keys. Round-robin, weighted, latency-based, and ordered fallback chains. Redis-tracked TPM/RPM across deployments.
- **Pricing:** Open-source / self-hosted (free). Hosted SaaS available.
- **Production behavior:** Handles cooldowns on 429s, exponential backoff retries, model aliases. Can chain `gemini-flash → groq-scout → cerebras-qwen → openai`.
- **Anticipy integration:** Replace `engine/app/models.py` direct provider calls with a `litellm.Router` client pointing at `model_list = [...]` (one entry per provider×model×api_key). Set `routing_strategy='usage-based-routing-v2'` and a Redis store. Free tier of 5 providers × 30 RPM each = ~150 sustained RPM.

### E2. FreeLLMAPI (quota-aware free-tier aggregator)
- **Link:** https://github.com/tashfeenahmed/freellmapi (Apache 2.0)
- **What it solves:** Aggregates ~14 free-tier providers behind one OpenAI endpoint. Tracks RPM/RPD/TPM/TPD per (platform, model, key) and routes to whichever has remaining headroom — not just round-robin. Combined claimed throughput **~1.3B tokens/month free**.
- **Pricing:** Self-hosted free. AES-256-GCM key encryption built in.
- **Caveat from author:** Personal experimentation only — terms-of-service tension with several providers if used commercially at scale. Use the *pattern*, don't run *their server* against your real users.
- **Anticipy integration:** Either run as a sidecar or steal the quota-tracking logic. The key idea — RPD/TPD bookkeeping per key — should live in `engine/app/llm_router.py`. When Cerebras hits its 1M token/day cap, demote to cooldown for 24h, route to Gemini, etc.

### E3. Self-hosted vLLM (no rate limit)
- **Link:** https://docs.vllm.ai/
- **What it solves:** Eliminates RPM cap entirely; cost becomes pure GPU $/hr.
- **Specific numbers:**
  - Llama-3 8B on a $1.05/hr A100: ~3,300 tok/sec → **~$0.09/MTok**
  - Llama-3 8B on RTX 4090: 120 tok/sec → ~10M tokens/day per card
  - Break-even point vs. paid APIs: **~600M tok/month** (after that, self-hosting wins)
- **Vision option:** vLLM supports Qwen2.5-VL 7B on a single L40S ($1.90/hr on RunPod serverless = $0.000079/sec).
- **Anticipy integration:** Phase 3 only. Don't self-host until volume actually demands it. At 1M tasks/yr * 10k tokens/task = 10B tokens/yr ≈ 27M tok/day, single A10/L40S can serve it. ~$1.5k-2k/yr GPU cost for the entire vision workload IF traffic warrants always-on instance.

### Honorable mentions (RPM):
- **GPTCache** (https://github.com/zilliztech/GPTCache): Semantic-cache layer in front of any LLM. Reduces calls by **61-69%** on repeat queries. Worth wiring in for chat/Q&A side, not great for action tasks where state matters.
- **OpenRouter:** Free models pool (~28 models, including Gemma 4 31B vision). 20 RPM / 200 RPD on free tier — too restrictive to be primary, OK as failover.
- **Redis prompt cache:** trivial to add for static system prompts; pairs well with Anthropic's 90%-discount cache reads ($0.10x base input).

---

## F. QUOTAS — Top 3 Free Vision Providers (May 2026)

### F1. Gemini 2.5 Flash (free tier on Google AI Studio) — **highest free vision throughput**
- **Link:** https://ai.google.dev/gemini-api/docs/rate-limits
- **Free limits (May 2026):** 15 RPM, **1M TPM**, **500-1500 RPD** (per project — varies; some sources show 500, some 1500 — check AI Studio for your project)
- **Vision:** Yes — full multimodal, no surcharge
- **Catch:** Anticipy already hit a project spending cap on Gemini. Workaround: spin up multiple Google Cloud projects (each gets its own free quota), aggregate via LiteLLM. 5 projects = effectively 5x quota, free.
- **Anticipy integration:** Already wired as primary in `engine/app/models.py`. Add multi-project rotation — same model, different `GOOGLE_API_KEY` per project.

### F2. Mistral La Plateforme — Pixtral 12B free (highest monthly token cap)
- **Link:** https://mistral.ai/news/september-24-release , https://docs.mistral.ai/deployment/ai-studio/tier
- **Free limits:** 1 RPS (~60 RPM), 500k TPM, **1 BILLION tokens/MONTH** total
- **Vision:** Yes — Pixtral 12B accepts images, 128k context
- **Anticipy integration:** Plug into LiteLLM router as the heaviest free-tier slot. 1B tokens/month at 10k tokens/task = 100k tasks/month free. That alone is 1.2M tasks/year of capacity from one provider.

### F3. Cerebras Free Tier (Qwen3-235B, GLM-4.7) — fast text-only fallback
- **Link:** https://www.cerebras.ai/pricing , https://inference-docs.cerebras.ai
- **Free limits:** 30 RPM, **1M tokens/day**, 8k context
- **Paid (Cerebras Code Pro):** $50/month for 24M tokens/day, 300k TPM. Code Max: $200/mo for 120M tok/day. **Massive value** if you need volume.
- **Vision:** **Currently text-only** (April-May 2026). For Anticipy's reading/planning side this is fine; vision must come from another provider.
- **Anticipy integration:** Already in stack. Use for the planner/critic role — non-vision LLM calls. With Cerebras Code Pro at $50/mo, you get ~720M tokens/month — enough alone to handle the entire planner side for $600/yr.

### Other notable free vision tiers:
| Provider | Vision Model | Free Daily Cap | RPM | Notes |
|---|---|---|---|---|
| Groq | Llama 4 Scout (vision) | ~1,000 RPD | 30 RPM | Half-rate vs text models |
| Cloudflare Workers AI | Llama 3.2 11B Vision | 10k neurons/day | — | Neurons → ~227M input tokens (4410 neurons/MTok in) |
| OpenRouter free | Gemma 4 31B (vision) | 200 RPD | 20 RPM | Pool restrictive but free |
| GitHub Models | Llama 3.2 11B Vision | Tied to Copilot tier | — | Useful only if user has Copilot |
| NVIDIA NIM | Various vision | ~1000 credits | 40 RPM | Trial-style |
| Hyperbolic | Qwen2.5-VL, Llama 3.2 Vision | 50 RPD | 20 RPM | Too small for primary |
| SambaNova | Llama 3.3 70B + others | persistent free, 10-30 RPM | — | Vision availability shaky |

### Token-compression tactics (specific to Anticipy's stack):
1. **Drop screenshots in default path** — Browser Use's `use_vision=False` saves ~70% of input tokens per step. Re-enable on `unable_to_locate` errors only.
2. **Accessibility-tree snapshot replaces DOM** — see A2 above. Single biggest lever.
3. **Cap `max_history_items`** — 3-5 last steps only, not full history. Saves 30-50% on long tasks.
4. **Structured outputs (JSON schema)** — forces tight output, often <100 tokens vs 500+ for free-form.
5. **Split observation LLM from action LLM** — small text-only model (Cerebras Qwen) parses page content; vision LLM only invoked when an action requires visual confirmation. Browser Use already supports `page_extraction_llm` separately — set it to a free Cerebras model.
6. **Initial-actions to skip predictable nav** — e.g., "for amazon search, always start at amazon.com/s?k=..." rather than letting LLM navigate from homepage.

---

## SPECIFIC PRICING — Vision-Capable Models, Cheapest First (May 2026)

| Model | Provider | $/MTok input | $/MTok output | Vision | Notes |
|---|---|---|---|---|---|
| Llama 3.2 11B Vision | Meta API | $0.049 | $0.049 | Yes | Cheapest paid vision; uptime varies |
| Pixtral 12B | Mistral La Plateforme | $0.10 | $0.10 | Yes | Apache 2.0; **1B tok/mo free** |
| Gemini 2.5 Flash-Lite | Google | $0.10 | $0.40 | Yes | Batch mode: $0.05/$0.20 |
| Cloudflare Llama 3.2 11B Vision | Cloudflare AI | $0.049 | $0.676 | Yes | 10k neurons/day free |
| Gemini 2.5 Flash | Google | (free tier sufficient) | — | Yes | 1M TPM free per project |
| Qwen2.5-VL 7B | OpenRouter providers | $0.20-0.36 | $0.20-0.40 | Yes | Self-hostable (Apache 2.0) |
| GPT-5.4 nano | OpenAI | $0.20 | $1.25 | Yes | Multimodal; expensive output |
| GPT-4.1 nano | OpenAI | $0.10 | $0.40 | Yes | Multimodal, 1M context |
| Llama 4 Maverick | Together | $0.27 | $0.85 | Yes | |
| Qwen2.5-VL 72B | OpenRouter providers | $0.25 | $0.75 | Yes | |

**Cheapest non-vision (for planner/critic):** DeepSeek V3 at $0.14/$0.28; Cerebras free Qwen3 235B; Groq paid Llama 3.3 70B at $0.05/MTok blended.

---

## CONCRETE ROADMAP FOR ANTICIPY

**Phase 1 (cost wins available this week, ~5 days work):**
1. Add task classifier in `engine/app/router.py` to detect read-only ("summarize", "find on", "what does"). Route those to Jina Reader (`https://r.jina.ai/{url}`) + Cerebras Qwen3 for parsing. This removes ~60-70% of traffic from the agent loop entirely.
2. Add `use_vision=False` as default in `engine/app/agent.py`. Re-enable only on `unable_to_locate` retry.
3. Drop `max_history_items` from default to 3.
4. Add multi-project Gemini rotation — 3-5 GCP projects share load via LiteLLM.

**Estimated impact:** Per-task tokens 100k → 25k. Cost: $0.06 → $0.0075/task. **8x improvement, still 75x over budget but progress.**

**Phase 2 (~2 weeks work):**
5. Replace Browser Use's DOM observation with Playwright accessibility-tree snapshot (200-400 tokens/page). Keep Browser Use for the planning loop, swap out the perception step.
6. Add LiteLLM router with quota tracking. Stack: Gemini 2.5 Flash (free, 5 projects) → Mistral Pixtral 12B (1B/mo free) → Groq Llama 4 Scout (free) → Cerebras (text-only, free) → Cloudflare AI (free) → paid spillover Llama 3.2 11B Vision @ $0.049/MTok.
7. Add `engine/app/trajectory_cache.py` (Stagehand-style). Hash + cached selectors. Redis-backed.

**Estimated impact:** Per-task tokens 25k → 3-5k. Cache hit on repeats removes ~30% of LLM calls. Cost: $0.0075 → ~$0.0001-0.0005/task. **Within striking distance of budget.**

**Phase 3 (only at scale, ~1B+ tokens/month):**
8. Self-host Qwen2.5-VL 7B on a dedicated A10/L40S — ~$0.09/MTok ceiling, no rate limits. Worth it past ~600M tok/month.

---

## SOURCES

- [Firecrawl pricing](https://www.firecrawl.dev/pricing)
- [Jina Reader](https://jina.ai/reader/) / [Reader-LM v2](https://huggingface.co/jinaai/ReaderLM-v2) / [github.com/jina-ai/reader](https://github.com/jina-ai/reader)
- [ScrapingBee pricing](https://www.scrapingbee.com/pricing/)
- [Browserless pricing](https://www.browserless.io/pricing)
- [DeepSeek API pricing](https://api-docs.deepseek.com/quick_start/pricing)
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Gemini API rate limits](https://ai.google.dev/gemini-api/docs/rate-limits)
- [Cerebras pricing](https://www.cerebras.ai/pricing) / [Cerebras Inference docs](https://inference-docs.cerebras.ai/support/rate-limits)
- [Groq pricing](https://groq.com/pricing) / [Groq rate limits](https://console.groq.com/docs/rate-limits)
- [OpenRouter free models](https://openrouter.ai/collections/free-models) / [Vision models](https://openrouter.ai/collections/vision-models)
- [Together AI pricing](https://www.together.ai/pricing)
- [Mistral La Plateforme tiers](https://docs.mistral.ai/deployment/ai-studio/tier) / [Mistral AI in abundance](https://mistral.ai/news/september-24-release)
- [Cloudflare Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)
- [SambaNova rate limits](https://docs.sambanova.ai/docs/en/models/rate-limits)
- [free-llm-api-resources (cheahjs)](https://github.com/cheahjs/free-llm-api-resources)
- [FreeLLMAPI gateway](https://github.com/tashfeenahmed/freellmapi)
- [LiteLLM routing docs](https://docs.litellm.ai/docs/routing)
- [GPTCache](https://github.com/zilliztech/GPTCache)
- [vLLM docs](https://docs.vllm.ai/)
- [RunPod pricing](https://www.runpod.io/pricing) / [Modal pricing](https://costbench.com/software/ai-gpu-cloud/modal/)
- [Stagehand caching](https://www.browserbase.com/blog/stagehand-caching) / [Stagehand cost docs](https://docs.stagehand.dev/v3/best-practices/cost-optimization)
- [Skyvern](https://github.com/Skyvern-AI/skyvern)
- [Vercel agent-browser](https://github.com/vercel-labs/agent-browser)
- [Microsoft playwright-mcp](https://github.com/microsoft/playwright-mcp)
- [Playwright CLI 4x token reduction](https://www.morphllm.com/playwright-mcp) / [agent-browser vs MCP benchmark](https://www.ytyng.com/en/blog/ai-browser-automation-tools-comparison-2026)
- [Browser-Use cost reduction discussion](https://github.com/browser-use/browser-use/discussions/878)
- [Llama 3.2 11B Vision pricing](https://pricepertoken.com/pricing-page/model/meta-llama-llama-3.2-11b-vision-instruct)
- [Pixtral 12B pricing](https://pricepertoken.com/pricing-page/model/mistral-ai-pixtral-12b)
- [Self-hosted LLM cost analysis](https://www.digitalapplied.com/blog/self-host-frontier-models-tco-analysis-2026)
- [Cerebras Code Pro $50/mo](https://www.cerebras.ai/blog/introducing-cerebras-code)
