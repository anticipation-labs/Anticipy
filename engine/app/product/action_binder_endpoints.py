"""FastAPI router for the V7 action binder.

Endpoints:
  POST /api/action/bind             -> returns a Binding dict
  POST /api/action/bind_and_execute -> binds then dispatches in one call

No-decline contract: a missing slot returns a Binding whose
planned_primitives is [{type: "ask_user", ...}] rather than a decline.
Dispatcher errors collapse to status="notify_user".
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


router = APIRouter()


class _BindBody(BaseModel):
    intent_id: str = Field(...)
    context: dict[str, Any] = Field(default_factory=dict)
    account_id: str = Field("")
    device_id: str = Field("")
    intent: Optional[dict[str, Any]] = Field(default=None)
    risk_assessment: Optional[dict[str, Any]] = Field(default=None)


def _coerce_intent(body: _BindBody) -> dict[str, Any]:
    if isinstance(body.intent, dict) and body.intent:
        merged = dict(body.intent)
        merged.setdefault("intent_id", body.intent_id)
        return merged
    return {"intent_id": body.intent_id,
            "text": str(body.context.get("intent_text")
                         or body.context.get("text") or body.intent_id)}


@router.post("/api/action/bind")
def bind_endpoint(body: _BindBody) -> JSONResponse:
    if not body.intent_id.strip():
        raise HTTPException(status_code=400, detail="intent_id is required")
    try:
        from app.product.action_binder import bind as _bind
    except Exception as exc:
        return JSONResponse(
            {"error": "action_binder_not_available", "detail": str(exc)},
            status_code=503)
    binding = _bind(_coerce_intent(body), body.context or {},
                    body.risk_assessment, account_id=body.account_id,
                    device_id=body.device_id)
    return JSONResponse(binding.to_dict())


@router.post("/api/action/bind_and_execute")
def bind_and_execute_endpoint(body: _BindBody) -> JSONResponse:
    if not body.intent_id.strip():
        raise HTTPException(status_code=400, detail="intent_id is required")
    try:
        from app.product.action_binder import (  # type: ignore
            bind as _bind, execute_binding as _exec,
        )
    except Exception as exc:
        return JSONResponse(
            {"status": "notify_user", "binding": None,
             "result": {"error": "action_binder_not_available",
                         "detail": str(exc)}}, status_code=503)
    binding = _bind(_coerce_intent(body), body.context or {},
                    body.risk_assessment, account_id=body.account_id,
                    device_id=body.device_id)
    try:
        result = _exec(binding)
    except Exception as exc:
        result = {"status": "notify_user", "intent": binding.intent_text,
                  "result": {"error": "execute_binding_failed",
                              "detail": str(exc)},
                  "binding_id": binding.binding_id}
    if str(result.get("status") or "").lower() == "declined":
        result["status"] = "notify_user"
    return JSONResponse({"binding": binding.to_dict(), "result": result,
                          "status": result.get("status", "notify_user")})


__all__ = ["router"]
