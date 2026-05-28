"""HTTP API for the V7 universal action dispatcher (no-decline path).

Endpoints under `/api/action/*` expose `ActionDispatcher` to product
callers (`/api/act`, proactive engine, surfaces). The dispatcher is
imported lazily so this module loads even before it is built.

Contract: NEVER returns `declined`. Allowed statuses are
`in_progress | success | ask_user | notify_user | timed_out`. The
dispatcher's internal `notify` is promoted to `notify_user`; any
`declined` shape is rewritten to `notify_user`. Execute is bounded
by a 60 second wall clock.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


router = APIRouter()

_ALLOWED = {"in_progress", "success", "ask_user", "notify_user", "timed_out"}
_TIMEOUT_S = 60.0
_TASKS_LOCK = threading.Lock()
_TASKS: dict[str, dict[str, Any]] = {}
_EXEC = ThreadPoolExecutor(max_workers=4, thread_name_prefix="anticipy-action")


class ExecuteBody(BaseModel):
    intent: str = Field(..., description="Natural language instruction")
    account_id: str
    device_id: str
    context: dict[str, Any] = Field(default_factory=dict)


class ConfirmBody(BaseModel):
    task_id: str
    user_choice: str  # "yes" | "no"


class CancelBody(BaseModel):
    task_id: str


def _load_dispatcher() -> Optional[Any]:
    """Return the ActionDispatcher class or None. Tests override this."""
    try:
        from app.product.action_dispatcher import ActionDispatcher  # type: ignore
    except Exception:
        return None
    return ActionDispatcher


def _norm(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if s == "notify":
        return "notify_user"
    return s if s in _ALLOWED else "notify_user"


def _shape(raw: Any) -> dict[str, Any]:
    if hasattr(raw, "to_dict") and callable(raw.to_dict):
        try:
            raw = raw.to_dict()
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        raw = {"value": raw}
    result = raw.get("result")
    if not isinstance(result, dict):
        carry = {k: raw[k] for k in
                 ("question", "options", "message", "proof", "error",
                  "steps", "intent") if k in raw}
        if result is not None and "value" not in carry:
            carry["value"] = result
        result = carry
    hist = raw.get("history") or []
    if not isinstance(hist, list):
        hist = [hist]
    return {
        "task_id": str(raw.get("task_id") or "").strip(),
        "status": _norm(raw.get("status")),
        "result": result,
        "history": hist,
    }


def _resolve(cls: Any) -> Any:
    if cls is None:
        return None
    if isinstance(cls, type):
        try:
            return cls()
        except Exception:
            return None
    if callable(cls) and not hasattr(cls, "execute"):
        try:
            return _resolve(cls())
        except Exception:
            return None
    return cls


def _invoke(cls, intent, account_id, device_id, context):
    inst = _resolve(cls)
    fn = getattr(inst, "execute", None)
    if fn is None:
        return {"status": "notify_user",
                "result": {"error": "dispatcher_unavailable"},
                "history": []}
    out = None
    last: Optional[Exception] = None
    for kw in (
        {"account_id": account_id, "device_id": device_id,
         "memory_context": context},
        {"account_id": account_id, "device_id": device_id, "context": context},
        {"account_id": account_id, "device_id": device_id},
    ):
        try:
            out = fn(intent, **kw); last = None; break
        except TypeError as exc:
            last = exc
        except Exception as exc:
            return {"status": "notify_user",
                    "result": {"error": str(exc)}, "history": []}
    if out is None and last is not None:
        try:
            out = fn(intent, account_id, device_id)
        except Exception as exc:
            return {"status": "notify_user",
                    "result": {"error": str(exc)}, "history": []}
    if asyncio.iscoroutine(out):
        try:
            out = asyncio.get_event_loop().run_until_complete(out)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                out = loop.run_until_complete(out)
            finally:
                loop.close()
    return out


def _get(task_id: str) -> Optional[dict[str, Any]]:
    with _TASKS_LOCK:
        return _TASKS.get(task_id)


def _err_unknown(task_id: str) -> JSONResponse:
    return JSONResponse({
        "task_id": task_id, "status": "notify_user",
        "result": {"error": "unknown task_id"}, "history": [],
    }, status_code=404)


@router.post("/api/action/execute")
def execute(body: ExecuteBody) -> JSONResponse:
    cls = _load_dispatcher()
    if cls is None:
        return JSONResponse({
            "task_id": "", "status": "notify_user",
            "result": {"error": "action_dispatcher_not_available",
                       "message": ("ActionDispatcher is not yet wired. "
                                   "Build engine/app/product/"
                                   "action_dispatcher.py.")},
            "history": [],
        }, status_code=503)
    if not body.intent.strip():
        raise HTTPException(status_code=400, detail="intent is required")
    if not body.account_id or not body.device_id:
        raise HTTPException(status_code=400,
                            detail="account_id and device_id are required")

    task_id = str(uuid.uuid4())
    state: dict[str, Any] = {
        "task_id": task_id, "status": "in_progress", "result": {},
        "history": [], "started_at": time.time(),
        "confirm_event": threading.Event(),
        "user_choice": None, "cancel": False,
    }
    with _TASKS_LOCK:
        _TASKS[task_id] = state
    future = _EXEC.submit(_invoke, cls, body.intent, body.account_id,
                          body.device_id, body.context)
    try:
        raw = future.result(timeout=_TIMEOUT_S)
        shaped = _shape(raw)
        if not shaped["task_id"]:
            shaped["task_id"] = task_id
        with _TASKS_LOCK:
            state.update(shaped)
        return JSONResponse(shaped)
    except FuturesTimeout:
        with _TASKS_LOCK:
            state["status"] = "timed_out"
        return JSONResponse({
            "task_id": task_id, "status": "timed_out",
            "result": {"error": "dispatcher exceeded 60s budget"},
            "history": state.get("history", []),
        })


@router.get("/api/action/status")
def status(task_id: str = Query(...)) -> JSONResponse:
    state = _get(task_id)
    if state is None:
        return _err_unknown(task_id)
    return JSONResponse({
        "task_id": task_id,
        "status": _norm(state.get("status")),
        "result": state.get("result") or {},
        "history": state.get("history") or [],
    })


@router.post("/api/action/confirm")
def confirm(body: ConfirmBody) -> JSONResponse:
    state = _get(body.task_id)
    if state is None:
        return _err_unknown(body.task_id)
    choice = (body.user_choice or "").strip().lower()
    if choice not in {"yes", "no"}:
        raise HTTPException(status_code=400,
                            detail="user_choice must be 'yes' or 'no'")
    with _TASKS_LOCK:
        state["user_choice"] = choice
        state["status"] = "in_progress" if choice == "yes" else "notify_user"
    try:
        state["confirm_event"].set()
    except Exception:
        pass
    return JSONResponse({
        "task_id": body.task_id,
        "status": _norm(state.get("status")),
        "result": {"user_choice": choice},
        "history": state.get("history") or [],
    })


@router.post("/api/action/cancel")
def cancel(body: CancelBody) -> JSONResponse:
    state = _get(body.task_id)
    if state is None:
        return _err_unknown(body.task_id)
    with _TASKS_LOCK:
        state["cancel"] = True
        state["status"] = "notify_user"
        state["result"] = {"cancelled": True}
        try:
            state["confirm_event"].set()
        except Exception:
            pass
        _TASKS.pop(body.task_id, None)
    return JSONResponse({
        "task_id": body.task_id, "status": "notify_user",
        "result": {"cancelled": True},
        "history": state.get("history") or [],
    })
