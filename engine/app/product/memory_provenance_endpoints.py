"""FastAPI router for V7 memory provenance + active-flag controls.

GET  /api/memory/validation_errors?account_id=  recent invalid writes
POST /api/memory/deactivate                     {memory_id, account_id, device_id}
POST /api/memory/reactivate                     {memory_id, account_id, device_id}

The scoped memory wrapper agent is expected to wrap its read path
through ActiveFlagEnforcer. These endpoints expose direct admin
controls on top of that storage.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.product.memory_provenance import (
    ActiveFlagEnforcer,
    read_validation_errors,
)
from app.product.scoped_memory import ScopedMemory

router = APIRouter()


@router.get("/api/memory/validation_errors")
def memory_validation_errors(
    account_id: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=2000),
) -> JSONResponse:
    errs = read_validation_errors(account_id=account_id, limit=limit)
    return JSONResponse({"ok": True, "count": len(errs), "errors": errs})


class FlagBody(BaseModel):
    memory_id: str
    account_id: str
    device_id: str


def _enforcer(account_id: str, device_id: str) -> ActiveFlagEnforcer:
    if not account_id or not device_id:
        raise HTTPException(
            status_code=400,
            detail="account_id and device_id are required",
        )
    return ActiveFlagEnforcer(
        ScopedMemory(account_id=account_id, device_id=device_id)
    )


@router.post("/api/memory/deactivate")
def memory_deactivate(body: FlagBody) -> JSONResponse:
    enf = _enforcer(body.account_id, body.device_id)
    if not body.memory_id:
        raise HTTPException(status_code=400, detail="memory_id is required")
    ok = enf.deactivate(body.memory_id)
    return JSONResponse({"ok": ok, "memory_id": body.memory_id,
                         "active": False if ok else None})


@router.post("/api/memory/reactivate")
def memory_reactivate(body: FlagBody) -> JSONResponse:
    enf = _enforcer(body.account_id, body.device_id)
    if not body.memory_id:
        raise HTTPException(status_code=400, detail="memory_id is required")
    ok = enf.reactivate(body.memory_id)
    return JSONResponse({"ok": ok, "memory_id": body.memory_id,
                         "active": True if ok else None})


def attach() -> bool:
    """Register this router on the running FastAPI app. FIX (W2O):
    surface the actual exception on failure so a PyInstaller miss is
    diagnosable; the outer ``_safe_attach`` in ``app.product.server``
    re-raises for this critical router.
    """
    import sys
    import traceback as _traceback
    try:
        from app.product.server import app
        existing = {getattr(r, "path", None) for r in app.routes}
        new = {getattr(r, "path", None) for r in router.routes}
        if new and new.issubset(existing):
            return True
        app.include_router(router)
        return True
    except Exception as exc:
        try:
            print(f"[memory_provenance_endpoints] attach failed: "
                  f"{type(exc).__name__}: {exc}\n{_traceback.format_exc()}",
                  file=sys.stderr, flush=True)
        except Exception:
            pass
        return False
