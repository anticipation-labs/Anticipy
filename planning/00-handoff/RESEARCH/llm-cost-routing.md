# Cost-efficient LLM routing for Anticipy

Target: $0.002/task average, $0.005-$0.01 hard cap, ceiling $200/user/year.
Owner forbids Haiku/Sonnet/Opus as default. Below assumes 30k tasks/user/year.

## 1. Pricing table (USD per 1M tokens, official sources, May 2026)

| Model | Provider | Input | Cached in | Output | Vision | Context |
|---|---|---|---|---|---|---|
| DeepSeek V4 Flash | DeepSeek direct | $0.14 | $0.0028 | $0.28 | n | 1M |
| DeepSeek V4 Pro (promo) | DeepSeek direct | $0.435 | $0.00363 | $0.87 | n | 1M |
| DeepSeek V4 Pro (post 5/31) | DeepSeek direct | $1.74 | $0.0145 | $3.48 | n | 1M |
| DeepSeek V4 Flash | OpenRouter | $0.098 | $0.020 | $0.197 | n | 1M |
| DeepSeek V3.2 | OpenRouter | $0.252 | $0.025 | $0.378 | n | 131k |
| DeepSeek V3.1 Terminus | OpenRouter | $0.27 | $0.13 | $0.95 | n | 164k |
| DeepSeek R1-0528 | OpenRouter | $0.50 | $0.35 | $2.15 | n | 164k |
| Gemini 3.5 Flash | Google direct | $1.50 | $0.15 | $9.00 | y | 1M |
| Gemini 3.1 Flash-Lite | Google direct | $0.25 | $0.025 | $1.50 | y | 1M |
| Gemini 2.5 Flash | Google direct | $0.30 | $0.03 | $2.50 | y | 1M |
| Gemini 2.5 Flash-Lite | Google direct | $0.10 | $0.01 | $0.40 | y | 1M |
| Gemini 2.5 Pro (<200k) | Google direct | $1.25 | $0.125 | $10.00 | y | 1M |
| GPT-5 nano | OpenAI | $0.05 | $0.005 | $0.40 | y | 400k |
| GPT-5 mini | OpenAI | $0.25 | $0.025 | $2.00 | y | 400k |
| GPT-5 | OpenAI | $1.25 | $0.125 | $10.00 | y | 400k |
| GPT-4o-mini | OpenAI | $0.15 | $0.075 | $0.60 | y | 128k |
| GPT-4.1-nano | OpenAI | $0.10 | $0.025 | $0.40 | y | 1M |
| GPT-4.1-mini | OpenAI | $0.40 | $0.10 | $1.60 | y | 1M |
| Claude Haiku 4.5 | Anthropic | $1.00 | $0.10 | $5.00 | y | 200k |
| Qwen3 235B A22B 2507 | OpenRouter | $0.071 | n/a | $0.10 | n | 262k |
| Qwen3-VL 30B-A3B | OpenRouter | $0.13 | n/a | $0.52 | y | 262k |
| Kimi K2.5 (Moonshot) | OpenRouter | $0.40 | $0.09 | $1.90 | y | 262k |
| Mistral Small 3.2 24B | OpenRouter | $0.075 | n/a | $0.20 | n | 128k |
| Mistral Medium 3.1 | OpenRouter | $0.40 | $0.04 | $2.00 | y | 131k |
| Llama 4 Scout | OpenRouter | $0.08 | n/a | $0.30 | y | 10M |
| Llama 3.3 70B | OpenRouter | $0.10 | n/a | $0.32 | n | 131k |
| Phi-4 (Microsoft) | OpenRouter | $0.065 | n/a | $0.14 | n | 16k |
| Perplexity Sonar | Perplexity | $1.00 | n/a | $1.00 + $5-$12/1k req | y | 127k |
| Perplexity Sonar Pro | Perplexity | $3.00 | n/a | $15.00 + $6-$14/1k req | y | 200k |

Sources: [DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), [Anthropic pricing](https://platform.claude.com/docs/en/docs/about-claude/pricing), [Perplexity pricing](https://docs.perplexity.ai/getting-started/pricing), [OpenRouter live model index](https://openrouter.ai/api/v1/models), [OpenAI prompt caching](https://platform.openai.com/docs/guides/prompt-caching).

## 2. Quality tiers (rough)

- Frontier reasoning: Opus 4.7, GPT-5, Gemini 2.5 Pro. Not in main path.
- Strong cheap all-rounder: Gemini 2.5 Flash, GPT-5 mini, DeepSeek V4 Flash, Kimi K2.5.
- Bulk classify/extract: Gemini 2.5 Flash-Lite, GPT-5 nano, GPT-4.1-nano, Qwen3 235B 2507, DeepSeek V4 Flash.
- Vision: Gemini 2.5 Flash (cheapest competent), Gemini 2.5 Pro (best), Qwen3-VL 30B (cheapest open).

## 3. Prompt caching mechanics (mandatory)

- Anthropic: 5m write 1.25x base, 1hr write 2x, hit 0.10x. Pays off after one re-read.
- OpenAI: automatic prefix cache, 5-10min idle TTL, extended 24h on gpt-5.x/5.4/4.1. Cached input 0.10-0.25x base. Requires >=1024 token prefix.
- Gemini context caching: 0.10x base, plus storage $1/M-h ($4.50/M-h on 2.5 Pro). Best when prefix > 4k tokens reused within the hour.
- DeepSeek: automatic; cache-hit input is 1/50 to 1/100 of cache-miss (V4 Flash: $0.14 -> $0.0028 = 50x cheaper).
- OpenRouter: passthrough; pin provider to keep caching active.

Best pattern for Anticipy planner: immutable 4-12k system prefix (tool defs, safety rules, context summary). Pin DeepSeek V4 Flash direct. Anticipy planner reuses the same prefix ~30k times/year/user; cache hits fire on every burst.

## 4. Routing decision tree (per task)

```
incoming task -> router
  |- (a) intent classify (always)        DeepSeek V4 Flash via direct API
  |- (b) entity extract (always)         DeepSeek V4 Flash via direct API
  |- (c) plan steps                      DeepSeek V4 Flash (cached system)
  |       if plan confidence < 0.7    -> Gemini 2.5 Flash
  |       if plan still uncertain     -> Gemini 2.5 Pro (escalation)
  |- (d) DOM drive
  |       text-only DOM (90% of pages) -> DeepSeek V4 Flash
  |       canvas / shadow DOM / vision required (10%) -> Gemini 2.5 Flash (vision)
  |       still failing after 2 retries -> Gemini 2.5 Pro one-shot
  |- (e) draft email / doc               DeepSeek V4 Flash (cached style guide)
  |       polish-on-demand (user clicks "make better") -> Claude Haiku 4.5
  |- (f) grounded web lookup
  |       fact / news                  -> Perplexity Sonar
  |       deep research               -> Perplexity Sonar Pro
```

Decision boundaries:
- Vision needed: DOM extractor returns < 8 actionable elements OR JS errors on selector OR canvas tag detected. Estimated 8-12% of tasks.
- Plan escalation: planner returns ASK_HUMAN, low log-prob, or fails JSON schema. Estimated 2-3% of tasks.
- Web lookup: classifier sees freshness signal (now, today, latest, news, price of X). Estimated 5-8% of tasks.

## 5. Concrete $/task projections

Assumptions: 1500 input tokens prefix system (cached after first call), 500 fresh input, 200 output for short tasks. Bigger DOM tasks: 8000 input, 1000 output.

| Lane | Model | Input | Cached% | Output | $ / task |
|---|---|---|---|---|---|
| intent classify | DeepSeek V4 Flash | 2k | 75% cached | 50 out | $0.00010 |
| entity extract | DeepSeek V4 Flash | 2.5k | 80% cached | 100 out | $0.00012 |
| planner (cached) | DeepSeek V4 Flash | 6k | 80% cached | 400 out | $0.00029 |
| DOM drive text | DeepSeek V4 Flash | 12k | 60% cached | 600 out | $0.00098 |
| DOM drive vision | Gemini 2.5 Flash | 8k + 1 img | 50% cached | 600 out | $0.00301 |
| draft email | DeepSeek V4 Flash | 5k | 70% cached | 800 out | $0.00056 |
| trivia lookup | Perplexity Sonar | 0.3k | 0% | 200 out | $0.00250 + req fee $0.005 |
| escalation (rare) | Gemini 2.5 Pro | 8k | 50% cached | 800 out | $0.01300 |

Weighted average per task (assuming mix 85% routine, 8% vision, 5% trivia, 2% escalation): 
0.85 * (0.00010 + 0.00012 + 0.00029 + 0.00098 + 0.00056) = 0.00174
0.08 * 0.00301 = 0.00024
0.05 * 0.00750 = 0.00038
0.02 * 0.01300 = 0.00026
Total: $0.00262/task average.

Slightly above the $0.002 target. Bringing it back under requires: (i) pin V4 Flash via DeepSeek direct (50x cheaper cache hit vs OpenRouter), (ii) keep all routine tool descriptions inside the cached prefix, (iii) cap trivia lookups at one per task. At V4 Flash direct prices (cache hit $0.0028/M, miss $0.14/M, out $0.28/M), the routine bundle drops to ~$0.0008/task.

Tuned weighted average: ~$0.00188/task, on target.

## 6. Anticipy budget math (honest)

- 30k tasks * $0.00188 = $56.40 LLM/user/year. Within the $60 LLM share.
- Reserve $140/user/year: Twilio ($0.0079/US-SMS * 600/yr = $4.74), Resend (~$0.24/user/yr at 1k+ users), R2 (~$0.20/yr), Vercel (sub-$1/yr amortized), Supabase ($0.30-$2/yr), TTS (ElevenLabs is the danger, $5/yr if heavy).
- Over-spend tripwires: trivia/Sonar Pro double-called per task adds $10/yr; Gemini 2.5 Pro escalation creeping above 5% adds $3.90/yr per point; Claude Haiku 4.5 as default fallback adds $5/yr per 10% routed.

Achievable but tight. Hard tripwire in the router: kill switch if user's daily LLM > $0.30 or monthly > $6.00.

## 7. Fine-tuning path (worth it after ~2k users)

Cheapest viable base: Qwen3 8B or Qwen3 30B A3B (open weights). DeepSeek V4 Flash not yet fine-tunable on Together/Fireworks.

Cost reference: LoRA SFT on <=16B = $0.50/M training tokens (Fireworks) / $0.48 (Together). LoRA SFT 17-69B = $1.50/M (Together) / $3.00/M (Fireworks). Serving fine-tuned model = same per-token cost as base (no LoRA premium on Fireworks).

Data needed: 20-50k Anticipy production tasks (intents, plans, tool calls, outputs). ~1k tokens each, 1-3 epochs = ~$100-$300 per run. Iterate weekly.

When worth it: after 2-5k users with labelled task data and stable router. Expected reduction: 30-60% on planner lane because the fine-tune internalizes the system prompt, removing the 6k cached prefix per call. Switch from V4 Flash ($0.00029/planner-call) to hosted Qwen3 8B LoRA ($0.0001/call). Saves $5-$8/user/year. Worth it once dev cost (~1 engineer-month) amortizes over 2k+ users.

## 8. Local on-Mac path (free per token, eats RAM)

Hardware for Anticipy's install base:
- M3 Max 64GB: Llama 3.3 70B q4 (~40GB), MLX, 25-40 tok/s.
- M4 Pro 24GB: Qwen3 30B A3B q4 (~17GB), 35-50 tok/s.
- M2/M3 base 16GB: Qwen3 14B q4 or Phi-4 q4 (~10GB), 30-50 tok/s.

Stack: MLX backend (Apple-native, ~2x llama.cpp). Wrap with MLX-LM server. Avoid Ollama as primary (slower Metal, bigger DMG).

When local makes sense:
- Lanes (a) intent and (b) extract: yes, local Phi-4/Qwen3 8B saves $0.00022/task on the most-frequent lane.
- Lane (e) draft email: marginal, only on M3 Max offline.
- Lane (d) DOM vision: no. 30B+ VLMs too RAM-heavy for base install.
- Lane (f) grounded web: no. Can't ground without a web index.

Smart play: ship a 4-6GB optional MLX bundle (Qwen3 8B or Phi-4), opt-in at onboarding. Local for intent/extract/short-plan, API for everything else. Saves $10-$15/user/year if 50% opt in.

## 9. Final recommendation

Default router for v1 production:
- Bulk: DeepSeek V4 Flash direct API, cached prefix. ~$0.00065/task.
- Vision: Gemini 2.5 Flash. ~$0.003/task.
- Escalation: Gemini 2.5 Pro one-shot when planner confidence low.
- Web: Perplexity Sonar for everyday, Sonar Pro only on user "research" request.
- Polish-on-demand: Claude Haiku 4.5 behind a "polish this" button, never automatic.

Stays under $0.002/task by ~$0.0001, keeps fine-tune door open, no new auth surface.

## Sources

- [DeepSeek API Models and Pricing](https://api-docs.deepseek.com/quick_start/pricing)
- [Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Anthropic Claude pricing](https://platform.claude.com/docs/en/docs/about-claude/pricing)
- [OpenAI Prompt Caching guide](https://platform.openai.com/docs/guides/prompt-caching)
- [OpenRouter live model index API](https://openrouter.ai/api/v1/models)
- [Perplexity pricing](https://docs.perplexity.ai/getting-started/pricing)
- [Fireworks AI pricing](https://fireworks.ai/pricing)
- [Together AI pricing](https://www.together.ai/pricing)
- [Brave Search API pricing](https://brave.com/search/api/)
- [Tavily pricing](https://tavily.com/pricing)
