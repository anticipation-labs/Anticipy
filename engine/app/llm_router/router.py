"""
Main router function for cost-efficient LLM dispatch.

``route(task_type, messages, **kwargs)`` is the single entry point. It:

  1. Resolves the task_type to a primary model + ordered fallback chain
     per the routing matrix in planning/00-handoff/RESEARCH/llm-cost-routing.md.
  2. Checks the SQLite prompt cache. On hit returns immediately (cache_hit=True).
  3. Estimates the call cost, gates via budget.check_budget.
  4. Dispatches to the right provider client. On ProviderError, tries the
     next model in the fallback chain (max 2 swaps).
  5. Records the actual cost via budget.record_cost.
  6. Stores the response in the cache.
  7. Returns a normalized dict {content, model_used, cost_usd, latency_ms, cache_hit}.

Task types:
    - intent_classify, planner, web_action, draft_email -> DeepSeek V4 Flash
    - vision_dom -> Gemini 2.5 Flash
    - trivia_lookup -> Perplexity Sonar (via OpenRouter)
    - escalation -> Gemini 2.5 Pro
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.llm_router import budget, cache
from app.llm_router.providers import (
    DeepSeekClient,
    GeminiClient,
    OpenAIClient,
    PerplexityClient,
    PRICING,
    ProviderError,
    ProviderResponse,
    get_client_for_model,
)


logger = logging.getLogger("engine.llm_router.router")


# Routing matrix: task_type -> ordered list of models (primary first).
# A call falls through to the next model on provider error. Limit fallthrough
# to 2 swaps so cascade failure surfaces fast (don't burn 5 providers' worth
# of latency on a doomed request).
TASK_ROUTING: dict[str, list[str]] = {
    "intent_classify": ["deepseek-v4-flash", "gpt-4.1-nano", "gemini-2.5-flash"],
    "planner": ["deepseek-v4-flash", "gemini-2.5-flash", "gpt-4.1-nano"],
    "web_action": ["deepseek-v4-flash", "gemini-2.5-flash", "gpt-4.1-nano"],
    "draft_email": ["deepseek-v4-flash", "gemini-2.5-flash", "gpt-4.1-nano"],
    "vision_dom": ["gemini-2.5-flash", "gemini-2.5-pro", "gpt-4.1-nano"],
    "trivia_lookup": ["perplexity/sonar", "gemini-2.5-flash", "deepseek-v4-flash"],
    "escalation": ["gemini-2.5-pro", "gemini-2.5-flash", "deepseek-v4-flash"],
}


MAX_FALLTHROUGH_SWAPS = 2


# Rough token estimates per spec (planning/00-handoff/RESEARCH/llm-cost-routing.md
# section "Concrete $/task projections"). Used by check_budget before dispatch.
# Conservative: actual response may be lower; we want the budget gate to be
# the upper bound.
DEFAULT_EST_TOKENS: dict[str, dict[str, int]] = {
    "intent_classify": {"input": 2000, "output": 100},
    "planner": {"input": 6000, "output": 400},
    "web_action": {"input": 12000, "output": 600},
    "draft_email": {"input": 5000, "output": 800},
    "vision_dom": {"input": 8000, "output": 600},
    "trivia_lookup": {"input": 500, "output": 300},
    "escalation": {"input": 8000, "output": 800},
}


class RouteError(Exception):
    """Raised when every model in the chain failed."""

    def __init__(self, task_type: str, errors: list[str]):
        self.task_type = task_type
        self.errors = errors
        super().__init__(f"route({task_type}) all providers failed: {errors}")


# RouteResponse is the canonical return shape; callers can either use it
# directly or treat the .as_dict() form (preferred: the public API returns dict).
class RouteResponse(dict):
    """Dict-shaped response with attribute access for ergonomics."""

    def __init__(
        self,
        content: str,
        model_used: str,
        cost_usd: float,
        latency_ms: int,
        cache_hit: bool,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
    ):
        super().__init__(
            content=content,
            model_used=model_used,
            cost_usd=float(cost_usd),
            latency_ms=int(latency_ms),
            cache_hit=bool(cache_hit),
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            cached_tokens=int(cached_tokens),
        )


def _estimate_cost(task_type: str, model: str) -> float:
    """Conservative upper-bound cost estimate per spec table.

    We assume input tokens are uncached for the estimate (the worst case), so
    callers can't game the gate by claiming a fully-cached prompt.
    """
    est = DEFAULT_EST_TOKENS.get(task_type, {"input": 2000, "output": 400})
    pricing = PRICING.get(model)
    if not pricing:
        return 0.0
    in_tok = est["input"]
    out_tok = est["output"]
    cost = (
        (in_tok / 1_000_000) * pricing["input"]
        + (out_tok / 1_000_000) * pricing["output"]
    )
    cost += float(pricing.get("request_fee", 0.0))
    return cost


async def _dispatch_one(model: str, messages: list[dict], **kwargs) -> ProviderResponse:
    """Pick the right client and execute one call."""
    client = get_client_for_model(model)
    # Strip kwargs that are router-internal so they don't leak into provider
    # payloads (e.g. user_id, task_type, override_model).
    internal_keys = {"user_id", "task_type", "override_model", "use_cache", "ttl_seconds"}
    clean_kwargs = {k: v for k, v in kwargs.items() if k not in internal_keys}
    return await client.complete(messages, model=model, **clean_kwargs)


async def route(
    task_type: str,
    messages: list[dict],
    user_id: str = "_anon",
    override_model: str | None = None,
    use_cache: bool = True,
    ttl_seconds: int | None = None,
    **kwargs,
) -> dict:
    """Single entry point for all LLM calls.

    Args:
        task_type: One of TASK_ROUTING keys. Anything else raises ValueError.
        messages: OpenAI-style messages list.
        user_id: For budget tracking. Defaults to "_anon".
        override_model: Force a specific model (skips routing matrix lookup).
        use_cache: Default True. Set False for non-deterministic calls.
        ttl_seconds: Override cache TTL.
        **kwargs: max_tokens, temperature, etc., forwarded to the provider.

    Returns:
        Dict shaped like {content, model_used, cost_usd, latency_ms,
        cache_hit, input_tokens, output_tokens, cached_tokens}.

    Raises:
        ValueError: unknown task_type.
        BudgetExceeded: budget cap would be exceeded by this call.
        RouteError: every model in the fallback chain failed.
    """
    start = time.time()

    if task_type not in TASK_ROUTING:
        raise ValueError(
            f"unknown task_type {task_type!r}; valid: {sorted(TASK_ROUTING.keys())}"
        )

    if override_model:
        chain = [override_model]
    else:
        chain = TASK_ROUTING[task_type][:MAX_FALLTHROUGH_SWAPS + 1]

    primary_model = chain[0]

    # Cache lookup uses the primary model in the key so callers asking for a
    # different model don't accidentally share cache entries.
    if use_cache:
        cached = cache.cache_get(task_type, primary_model, messages)
        if cached is not None:
            latency = int((time.time() - start) * 1000)
            return RouteResponse(
                content=cached.get("content", ""),
                model_used=cached.get("model_used", primary_model),
                cost_usd=0.0,  # cache hit is free
                latency_ms=latency,
                cache_hit=True,
                input_tokens=int(cached.get("input_tokens", 0) or 0),
                output_tokens=int(cached.get("output_tokens", 0) or 0),
                cached_tokens=int(cached.get("cached_tokens", 0) or 0),
            )

    # Budget gate is based on the primary model's estimate. Cheaper fallbacks
    # will only get triggered after the primary fails, so worst-case spend is
    # the primary's estimate. Per-call cap stops a single insane request from
    # nuking the daily budget.
    estimated_cost = _estimate_cost(task_type, primary_model)
    # budget.check_budget raises BudgetExceeded if the gate trips. We let it
    # propagate to the caller (Ralph loop can decide pause vs escalate).
    budget.check_budget(task_type, estimated_cost, user_id=user_id)

    errors: list[str] = []
    last_response: ProviderResponse | None = None

    for attempt, model in enumerate(chain):
        try:
            last_response = await _dispatch_one(model, messages, **kwargs)
            break
        except ProviderError as e:
            errors.append(f"{model}: {e}")
            logger.warning("provider error on %s (attempt %d): %s", model, attempt, e)
            continue
        except Exception as e:
            # Defensive: log and move on. Don't let one provider's bug kill
            # the entire call chain.
            errors.append(f"{model}: {type(e).__name__}: {e}")
            logger.exception("unexpected error on %s", model)
            continue

    if last_response is None:
        raise RouteError(task_type=task_type, errors=errors)

    # Record actual cost (post-call) so the next call sees the running total.
    budget.record_cost(
        task_type=task_type,
        model=last_response.model,
        cost_usd=last_response.cost_usd,
        user_id=user_id,
    )

    # Store in cache for next time.
    if use_cache:
        cache.cache_put(
            task_type=task_type,
            model=primary_model,
            messages=messages,
            response={
                "content": last_response.content,
                "model_used": last_response.model,
                "input_tokens": last_response.input_tokens,
                "output_tokens": last_response.output_tokens,
                "cached_tokens": last_response.cached_tokens,
            },
            ttl_seconds=ttl_seconds,
        )

    latency = int((time.time() - start) * 1000)
    return RouteResponse(
        content=last_response.content,
        model_used=last_response.model,
        cost_usd=last_response.cost_usd,
        latency_ms=latency,
        cache_hit=False,
        input_tokens=last_response.input_tokens,
        output_tokens=last_response.output_tokens,
        cached_tokens=last_response.cached_tokens,
    )


__all__ = [
    "route",
    "RouteError",
    "RouteResponse",
    "TASK_ROUTING",
]
