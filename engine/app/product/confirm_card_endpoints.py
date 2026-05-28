"""FastAPI router for the V7 confirm-card surface.

Routes:

  POST /api/confirm/create
      Body: {"account_id": "...", "intent": "...",
             "planned_steps": [...], "surface_target": "...",
             "money_amount": 0.0|null, "memory_context": {...},
             "ttl_seconds": 86400}
      Builds a card and persists it; returns the card_id and status.

  GET  /api/confirm/list?account_id=
      Pending cards for an account, newest first.

  POST /api/confirm/decide
      Body: {"card_id": "...", "choice": "yes"|"no", "account_id": "..."}
      Records the user's decision.

  GET  /api/confirm/{card_id}?account_id=
      Single card status by id.

All routes return JSON. Missing required fields -> 400. Unknown card
-> 404. Decisions for non-pending cards -> 409.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.product.confirm_card import (
    ConfirmCardStore,
    build_confirm_card,
    needs_confirmation,
)


router = APIRouter()


def _store(account_id: str) -> ConfirmCardStore:
    if not account_id or not str(account_id).strip():
        raise HTTPException(status_code=400, detail="account_id is required")
    return ConfirmCardStore(account_id=str(account_id))


class CreateBody(BaseModel):
    account_id: str
    intent: Any
    planned_steps: Optional[list[Any]] = None
    surface_target: Optional[str] = ""
    money_amount: Optional[float] = None
    memory_context: Optional[dict[str, Any]] = None
    ttl_seconds: Optional[int] = None


@router.post("/api/confirm/create")
def confirm_create(body: CreateBody) -> JSONResponse:
    store = _store(body.account_id)
    store.expire_stale()
    needs = needs_confirmation(
        body.intent, body.planned_steps,
        surface_target=body.surface_target or "",
        money_amount=body.money_amount,
        account_id=body.account_id,
    )
    card = build_confirm_card(
        body.intent, body.planned_steps or [],
        body.surface_target or "",
        body.memory_context,
        account_id=body.account_id,
        money_amount=body.money_amount,
        ttl_seconds=int(body.ttl_seconds) if body.ttl_seconds else 86400,
    )
    store.create(card)
    return JSONResponse({
        "ok": True,
        "card_id": card.card_id,
        "status": card.status,
        "needs_confirmation": bool(needs),
        "risk_level": card.risk_level,
        "expires_at": card.expires_at,
        "card": card.to_dict(),
    })


@router.get("/api/confirm/list")
def confirm_list(account_id: str = Query(...)) -> JSONResponse:
    store = _store(account_id)
    store.expire_stale()
    pending = store.list_pending(account_id=account_id)
    return JSONResponse({
        "ok": True,
        "account_id": account_id,
        "count": len(pending),
        "cards": pending,
    })


class DecideBody(BaseModel):
    card_id: str
    choice: str
    account_id: str


@router.post("/api/confirm/decide")
def confirm_decide(body: DecideBody) -> JSONResponse:
    if not body.card_id:
        raise HTTPException(status_code=400, detail="card_id is required")
    store = _store(body.account_id)
    existing = store.get(body.card_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="card not found")
    if existing.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"card already {existing.status}",
        )
    updated = store.decide(body.card_id, body.choice)
    if updated is None:
        raise HTTPException(
            status_code=400,
            detail="choice must be yes or no",
        )
    return JSONResponse({
        "ok": True,
        "card_id": updated.card_id,
        "status": updated.status,
        "decided_at": updated.decided_at,
        "card": updated.to_dict(),
    })


@router.get("/api/confirm/{card_id}")
def confirm_get(card_id: str, account_id: str = Query(...)) -> JSONResponse:
    store = _store(account_id)
    store.expire_stale()
    card = store.get(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="card not found")
    return JSONResponse({"ok": True, "card": card.to_dict()})
