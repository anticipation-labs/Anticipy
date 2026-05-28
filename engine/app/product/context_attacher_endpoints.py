"""FastAPI router for the V7 context attacher.

Single endpoint `POST /api/context/attach` returns the planner context
bundle that `ActionPlanner.plan_next_primitive` consumes before each
planning step. Useful for the proactive engine and external callers
who want to inspect what the planner sees without invoking the LLM.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


router = APIRouter()


class AttachBody(BaseModel):
    intent: Any = Field(..., description="String or dict with summary/refs")
    current_surface: Optional[dict[str, Any]] = Field(
        default_factory=dict,
        description="Current surface read: url, title, dom_text, etc.",
    )
    history: Optional[list[dict[str, Any]]] = Field(
        default_factory=list,
        description="Prior primitive results from this task",
    )
    account_id: str = Field(..., description="Account scope id")
    device_id: str = Field(..., description="Device scope id")
    max_chars: Optional[int] = Field(
        default=3000,
        description="Cap on prompt block size",
    )


@router.post("/api/context/attach")
def attach_context(body: AttachBody) -> JSONResponse:
    if not body.account_id or not body.device_id:
        raise HTTPException(
            status_code=400,
            detail="account_id and device_id are required",
        )
    # Deferred import so this module loads cleanly even if context_attacher
    # imports break (mirrors the no-decline contract in action_engine_api).
    try:
        from app.product.context_attacher import ContextAttacher
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "error": "context_attacher_unavailable",
                "detail": str(exc),
            },
            status_code=503,
        )

    attacher = ContextAttacher(body.account_id, body.device_id)
    context = attacher.attach(
        body.intent,
        body.current_surface or {},
        body.history or [],
    )
    # Serialize learned_recipes (they may be Recipe dataclasses).
    serialised_recipes: list[Any] = []
    for r in context.get("learned_recipes") or []:
        if hasattr(r, "to_dict") and callable(getattr(r, "to_dict")):
            try:
                serialised_recipes.append(r.to_dict())
                continue
            except Exception:
                pass
        serialised_recipes.append(r)
    context["learned_recipes"] = serialised_recipes

    prompt_block = ContextAttacher.as_planner_prompt_block(
        context, max_chars=int(body.max_chars or 3000),
    )
    return JSONResponse({
        "ok": True,
        "account_id": body.account_id,
        "device_id": body.device_id,
        "context": context,
        "prompt_block": prompt_block,
        "prompt_block_chars": len(prompt_block),
    })


__all__ = ["router"]
