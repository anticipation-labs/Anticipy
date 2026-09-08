# Gemini usage ledger repair — 8 September 2026

Local source repair at `cloudflare-backend`; no provider call or deployment.

## Reproduction

`LLM._gemini()` passed native `usageMetadata` directly to `_record()`, whose
keys followed OpenRouter's usage shape. A response reporting 120 prompt tokens
wrote `prompt_tokens: null`. It also checked for response text before recording
usage, so empty or blocked replies disappeared entirely even when the provider
reported tokens. A fallback then made the ledger look cheaper than the calls
that actually happened.

## Stored contract

The adapter follows Google's current [UsageMetadata reference](https://ai.google.dev/api/generate-content#UsageMetadata),
checked on 8 September 2026. Each value is a reported nonnegative integer;
missing or malformed values remain null, while explicit zero stays zero.

| Gemini field | Ledger field |
| --- | --- |
| `promptTokenCount` | `prompt_tokens` |
| `candidatesTokenCount` | `completion_tokens` |
| `cachedContentTokenCount` | `cached_tokens` |
| `thoughtsTokenCount` | `reasoning_tokens` |
| `toolUsePromptTokenCount` | `tool_prompt_tokens` |
| `totalTokenCount` | `total_tokens` |

The prompt count already includes cached content. Gemini's candidate count is
separate from its thinking count. Consumers must use the provider's reported
`total_tokens` aggregate for total usage and retain `mode` when comparing
breakdowns; they must not assume every provider's completion count includes
reasoning. The adapter does not estimate missing counts or dollar costs.
Gemini `cost` stays null. OpenRouter's reported cost and existing counts retain
their meanings, with its reported total now stored too.

Accounting occurs before response-text validation. The existing empty-response
error and fallback behavior remain; each provider response gets its own entry.
The ledger continues storing prompt lengths, not prompt text, replies, keys or
headers. A ledger write error still cannot fail a valid model answer.

## Proof and limits

`tests/test_llm_usage_ledger.py` originally produced ten failing cases and one
passing control. After the repair, its twelve cases pass, including a public
`chat()` call where an empty Gemini response falls through to OpenRouter and
both providers' reported usage remains recorded exactly once.

The new ledger suite plus Gemini, transient retry, gateway fallthrough,
truncated reply and decision-budget suites: **83 tests passed**, exit 0.
`git diff --check` passed for the changed code and tests.

All provider replies were explicit offline fixtures. No model quality,
production spend, live credentials or billed totals were measured. The ledger
remains opt-in via `ANTICIPY_LLM_LEDGER`; this patch does not configure a durable
container sink, change model tiers, or change polling/consolidation cadence.
Deployment and live ledger verification remain separate required evidence.
