"""FastAPI router for the V7 local-to-Supabase memory sync outbox.

Endpoints:

- ``GET  /api/memory/sync/status`` returns
  ``{pending_count, last_shipped_at, worker_running}``.
- ``POST /api/memory/sync/flush`` force-flushes the outbox now
  (bypasses the worker backoff schedule) and returns the shipped
  and failed counts plus the new pending count.

The router never raises on missing Supabase config. When SUPABASE_URL
is unset the worker stays no-op and the status endpoint reflects that;
flush returns a sentinel so the caller can tell.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.product.memory_cloud_sync import get_sync


router = APIRouter()


def _status_payload() -> dict[str, Any]:
    sync = get_sync()
    return {
        "pending_count": int(sync.pending_count()),
        "last_shipped_at": sync.last_shipped_at(),
        "worker_running": bool(sync.worker_running()),
        "supabase_url_set": bool(sync._url),
    }


@router.get("/api/memory/sync/status")
def memory_sync_status() -> JSONResponse:
    return JSONResponse({"ok": True, **_status_payload()})


@router.post("/api/memory/sync/flush")
def memory_sync_flush(max_seconds: Optional[float] = 10.0) -> JSONResponse:
    sync = get_sync()
    try:
        deadline = float(max_seconds or 10.0)
    except Exception:
        deadline = 10.0
    deadline = max(0.5, min(deadline, 30.0))
    result = sync.flush(max_seconds=deadline)
    payload = {"ok": True, "result": result, **_status_payload()}
    return JSONResponse(payload)
