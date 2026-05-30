"""
Anticipy cost-efficient LLM router (Phase 7).

Every LLM call in Anticipy flows through ``route()`` which picks the cheapest
model that meets the quality bar for the task type. Target $0.002/task average,
$0.005/call hard cap. See planning/00-handoff/RESEARCH/llm-cost-routing.md
for the full spec.

Public API:

    from app.llm_router import route, BudgetExceeded, RouteError

    response = await route(
        task_type="planner",
        messages=[{"role": "user", "content": "plan a trip"}],
        user_id="u-123",
    )
    # response = {content, model_used, cost_usd, latency_ms, cache_hit}

Task types supported (per spec):
    - intent_classify, planner, web_action, draft_email -> DeepSeek V4 Flash
    - vision_dom -> Gemini 2.5 Flash
    - trivia_lookup -> Perplexity Sonar via OpenRouter
    - escalation -> Gemini 2.5 Pro
"""

from app.llm_router.router import route, RouteError, RouteResponse
from app.llm_router.budget import BudgetExceeded, check_budget
from app.llm_router.cache import cache_stats

__all__ = [
    "route",
    "RouteError",
    "RouteResponse",
    "BudgetExceeded",
    "check_budget",
    "cache_stats",
]
