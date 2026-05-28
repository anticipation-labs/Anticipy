"""FastAPI router for the V7 unified intent extractor.

Two endpoints:
  POST /api/intent/extract       -> single normalized_input -> Intent dict
  POST /api/intent/extract_batch -> list of normalized inputs -> list[Intent]

This router is the canonical HTTP surface for intent extraction; the action
planner, /api/listen/inject, and /api/engine/analyze all go through here
(or import `extract` directly) instead of running their own ad-hoc intent
classifiers.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.product.intent_extractor import (
    extract,
    extract_batch,
    is_actionable,
)

router = APIRouter()


class ExtractBody(BaseModel):
    normalized_input: dict[str, Any]
    surface_context: Optional[dict[str, Any]] = None
    memory_context: Optional[str] = ""
    timeout: Optional[float] = None
    cascade: Optional[list[str]] = None


class ExtractBatchBody(BaseModel):
    inputs: list[dict[str, Any]]
    surface_context: Optional[dict[str, Any]] = None
    memory_context: Optional[str] = ""
    timeout: Optional[float] = None
    cascade: Optional[list[str]] = None


def _intent_payload(intent: Any) -> dict[str, Any]:
    data = intent.to_dict() if hasattr(intent, "to_dict") else dict(intent)
    data["is_actionable"] = is_actionable(intent)
    return data


@router.post("/api/intent/extract")
def intent_extract(body: ExtractBody) -> JSONResponse:
    if not isinstance(body.normalized_input, dict):
        raise HTTPException(
            status_code=400,
            detail="normalized_input must be an object",
        )
    kwargs: dict[str, Any] = {}
    if body.timeout is not None:
        kwargs["timeout"] = float(body.timeout)
    if body.cascade:
        kwargs["cascade"] = list(body.cascade)
    intent = extract(
        body.normalized_input,
        body.surface_context or {},
        body.memory_context or "",
        **kwargs,
    )
    return JSONResponse({"ok": True, "intent": _intent_payload(intent)})


@router.post("/api/intent/extract_batch")
def intent_extract_batch(body: ExtractBatchBody) -> JSONResponse:
    if not isinstance(body.inputs, list):
        raise HTTPException(
            status_code=400, detail="inputs must be an array")
    kwargs: dict[str, Any] = {}
    if body.timeout is not None:
        kwargs["timeout"] = float(body.timeout)
    if body.cascade:
        kwargs["cascade"] = list(body.cascade)
    intents = extract_batch(
        body.inputs,
        body.surface_context or {},
        body.memory_context or "",
        **kwargs,
    )
    return JSONResponse({
        "ok": True,
        "count": len(intents),
        "intents": [_intent_payload(i) for i in intents],
    })
