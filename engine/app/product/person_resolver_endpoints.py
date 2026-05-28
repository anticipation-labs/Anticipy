"""FastAPI router for the V7 person/alias resolver.

Endpoints:
  POST /api/person/resolve       -> {person, confidence, alternatives, reason}
  POST /api/person/disambiguate  -> records user choice, learns alias
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.product.person_resolver import PersonResolver

router = APIRouter()


class ResolveBody(BaseModel):
    reference: str
    context_text: Optional[str] = ""
    account_id: str
    device_id: Optional[str] = "default"


class DisambiguateBody(BaseModel):
    reference: str
    person_id: str
    account_id: str
    device_id: Optional[str] = "default"


def _resolver(account_id: str, device_id: str) -> PersonResolver:
    if not account_id:
        raise HTTPException(status_code=400, detail="account_id is required")
    return PersonResolver(account_id=account_id,
                          device_id=device_id or "default")


@router.post("/api/person/resolve")
def person_resolve(body: ResolveBody) -> JSONResponse:
    pr = _resolver(body.account_id, body.device_id or "default")
    res = pr.resolve(body.reference, body.context_text or "")
    return JSONResponse({"ok": True, "resolution": res.to_dict()})


@router.post("/api/person/disambiguate")
def person_disambiguate(body: DisambiguateBody) -> JSONResponse:
    pr = _resolver(body.account_id, body.device_id or "default")
    res = pr.disambiguate(body.reference, body.person_id)
    return JSONResponse({"ok": True, "resolution": res.to_dict()})
