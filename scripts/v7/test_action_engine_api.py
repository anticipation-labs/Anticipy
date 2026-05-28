"""Tests for V7 action engine HTTP API no-decline contract.
Calls route handlers directly (pinned starlette/httpx breaks TestClient)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ENGINE = Path(__file__).resolve().parents[2] / "engine"
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

_R: list[tuple[str, bool, str]] = []


def _c(cond, name, reason=""):
    _R.append((name, bool(cond), "" if cond else (reason or "fail")))
    print(f"{'PASS' if cond else 'FAIL'}  {name}"
          + ("" if cond else f": {reason}"))


def _b(resp):
    raw = getattr(resp, "body", b"") or b""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except Exception:
        return {}


class _Stub:
    def __init__(self, s="success"): self.s = s

    def execute(self, intent, *, account_id="", device_id="",
                memory_context=None):
        return {"status": self.s,
                "result": {"intent": intent, "account_id": account_id,
                           "device_id": device_id},
                "history": [{"step": "stub", "ok": True}]}


def _with(loader, fn):
    from app.product import action_engine_api as m
    saved, m._load_dispatcher = m._load_dispatcher, loader  # type: ignore
    try:
        return fn(m)
    finally:
        m._load_dispatcher = saved  # type: ignore


def _exec(m, **kw):
    return m.execute(m.ExecuteBody(intent=kw.get("intent", "x"),
                                   account_id=kw.get("account_id", "a"),
                                   device_id=kw.get("device_id", "d"),
                                   context=kw.get("context", {})))


def t_routes():
    from fastapi import FastAPI
    from app.product.action_engine_api import router
    app = FastAPI(); app.include_router(router)
    want = {"/api/action/execute", "/api/action/status",
            "/api/action/confirm", "/api/action/cancel"}
    got = {getattr(r, "path", None) for r in app.routes}
    _c(want.issubset(got), "router_has_all_four_routes",
       f"missing: {want - got}")


def t_no_dispatcher():
    r = _with(lambda: None, lambda m: _exec(m))
    p = _b(r)
    _c(r.status_code == 503, "no_dispatcher_returns_503",
       f"got {r.status_code}")
    _c(p.get("status") != "declined", "no_dispatcher_never_declined",
       f"got {p.get('status')}")
    _c(p.get("status") == "notify_user",
       "no_dispatcher_status_notify_user", f"got {p.get('status')}")


def t_execute_success():
    r = _with(lambda: lambda: _Stub("success"),
              lambda m: _exec(m, intent="draft email", context={"k": "v"}))
    p = _b(r)
    _c(r.status_code == 200, "execute_success_200", f"got {r.status_code}")
    for k in ("task_id", "status", "result", "history"):
        _c(k in p, f"execute_body_has_{k}", str(p))
    _c(p.get("status") == "success", "execute_status_success",
       f"got {p.get('status')}")
    _c(p.get("status") != "declined", "execute_never_declined", "")


def t_decline_rewritten():
    p = _b(_with(lambda: lambda: _Stub("declined"), lambda m: _exec(m)))
    _c(p.get("status") != "declined", "wire_strips_declined",
       f"got {p.get('status')}")
    _c(p.get("status") == "notify_user", "wire_promotes_to_notify_user",
       f"got {p.get('status')}")


def t_notify_promoted():
    p = _b(_with(lambda: lambda: _Stub("notify"), lambda m: _exec(m)))
    _c(p.get("status") == "notify_user",
       "notify_promoted_to_notify_user", str(p))


def t_status_404():
    from app.product.action_engine_api import status as h
    r = h(task_id="nope")
    _c(r.status_code == 404, "status_404_unknown", f"got {r.status_code}")
    _c(_b(r).get("status") == "notify_user",
       "status_unknown_notify_user", str(_b(r)))


def t_confirm_cancel_404():
    from app.product.action_engine_api import (
        cancel as ch, confirm as fh, CancelBody, ConfirmBody)
    r = fh(ConfirmBody(task_id="missing", user_choice="yes"))
    _c(r.status_code == 404, "confirm_404_unknown", f"got {r.status_code}")
    r2 = ch(CancelBody(task_id="missing"))
    _c(r2.status_code == 404, "cancel_404_unknown", f"got {r2.status_code}")


def t_wire_attach():
    lock = f"/tmp/anticipy_product_{os.environ.get('ANTICIPY_PORT','8731')}.lock"
    if os.path.exists(lock):
        print(f"SKIP  attach_returns_true: engine lock held at {lock}"); return
    from app.product.action_engine_api_wire import attach
    _c(bool(attach()), "attach_returns_true", "")


def main() -> int:
    for fn in (t_routes, t_no_dispatcher, t_execute_success,
               t_decline_rewritten, t_notify_promoted, t_status_404,
               t_confirm_cancel_404, t_wire_attach):
        fn()
    f = [(n, r) for n, ok, r in _R if not ok]
    print(f"\nPASSED: {sum(1 for _, ok, _ in _R if ok)}\nFAILED: {len(f)}")
    for n, r in f: print(f"  FAIL {n}: {r}")
    return 0 if not f else 1


if __name__ == "__main__":
    raise SystemExit(main())
