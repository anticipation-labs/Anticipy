"""Functional checker for task (B) — grader-owned deterministic form.

This is the strongest of the three: the independent re-read hits the *backend's*
own record (``GET /last``), so we confirm exactly what the server received rather
than anything the agent narrates. A hand that fakes a submit, or fills the DOM
without a real trusted-input POST, leaves ``/last`` empty and fails.

setup(ctx)  starts the embedded server and stashes the handle on ctx.
start_url(ctx) returns the URL the agent should be pointed at (public tunnel in a
live run, else the loopback server).
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

_SERVER_PATH = Path(__file__).with_name("server.py")


def _load_server_module():
    spec = importlib.util.spec_from_file_location("local_form_server", _SERVER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def setup(ctx: dict) -> None:
    mod = _load_server_module()
    handle = mod.start(port=0)          # free loopback port
    handle.reset()
    ctx["server"] = handle
    ctx["server_last_url"] = handle.url.rstrip("/") + "/last"


def teardown(ctx: dict) -> None:
    h = ctx.get("server")
    if h is not None:
        h.stop()


def start_url(ctx: dict) -> str:
    """Live lane points the agent at a public tunnel that forwards to our server
    (the SSRF gate refuses loopback); the selftest lane uses the loopback URL."""
    return os.environ.get("ANTICIPY_LOCALFORM_URL") or ctx["server"].url


def check(result: dict, ctx: dict) -> tuple[bool, str]:
    nonce = ctx["nonce"]
    # INDEPENDENT re-read: ask the backend what it actually stored.
    try:
        raw = ctx["http_get"](ctx["server_last_url"])
        import json
        last = json.loads(raw or "{}")
    except Exception as e:
        return False, f"could not read /last off the grader backend: {e}"
    if not last:
        return False, "backend recorded no submission (/last is empty — no real submit landed)"
    want = {
        "fullname": f"Grader {nonce}",
        "order_code": f"ORD-{nonce}",
        "speed": "express",
    }
    for k, v in want.items():
        got = last.get(k)
        if got != v:
            return False, f"backend recorded {k}={got!r}, expected {v!r}"
    return True, f"backend stored the exact submission (order ORD-{nonce}, express)"


def _submit(ctx: dict, fields: dict) -> None:
    """Helper used only by the selftest to emulate a real trusted submit."""
    import urllib.parse
    import urllib.request
    body = urllib.parse.urlencode(fields).encode()
    url = ctx["server"].url.rstrip("/") + "/submit"
    urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=5).read()


def synth_pass(ctx: dict) -> dict:
    nonce = ctx["nonce"]
    # Emulate the agent having actually submitted: the backend now has a record.
    _submit(ctx, {"fullname": f"Grader {nonce}", "order_code": f"ORD-{nonce}",
                  "address": "500 Test Ave", "speed": "express", "notes": "handle-with-care"})
    return {
        "answer": f"Submitted the shipping form for order ORD-{nonce}.",
        "final_url": ctx["server"].url,
        "final_text": "<h1>Order received</h1>",
        "metrics": {"steps": 8, "est_cost_usd": 0.0143, "frontier_pct": 22.0,
                    "vision_pct": 50.0, "region_pct": 80.0, "replayed": False},
        "task_succeeded": True,
    }


def synth_fail(ctx: dict) -> dict:
    # No _submit() call -> the backend has no record even though the agent claims
    # success. The checker must catch this via the empty /last.
    nonce = ctx["nonce"]
    ctx["server"].reset()
    return {
        "answer": f"All done, I submitted order ORD-{nonce}.",
        "final_url": ctx["server"].url,
        "final_text": "<h1>Shipping details</h1>",
        "metrics": {"steps": 2, "est_cost_usd": 0.003, "frontier_pct": 0.0,
                    "vision_pct": 0.0, "region_pct": 0.0, "replayed": False},
        "task_succeeded": True,
    }
