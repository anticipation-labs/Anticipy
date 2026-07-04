"""Functional checker for task (D) — carry_form (multi-step, two-page carry).

The strongest independent postcondition in the set: the checker re-reads BOTH
sides of the server's own memory —

  * ``GET /token`` : the claim token the server actually DISPLAYED on page 1, and
  * ``GET /last``  : the fields the server actually RECEIVED in the submit —

and requires the submitted ``claim_token`` to equal the displayed token. Because
the token is server-generated and appears only on page 1 (never in the task
text), the only way to match is to genuinely read page 1 and carry the value into
the form on page 2 with a real trusted submit. A hand that guesses, skips page 1,
or fakes a submit leaves ``/last`` empty or mismatched and fails.

setup(ctx)     starts the embedded two-page server and stashes the handle on ctx.
start_url(ctx) returns the URL the agent should be pointed at (public tunnel in a
               live run, else the loopback server root).
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

_SERVER_PATH = Path(__file__).with_name("server.py")


def _load_server_module():
    spec = importlib.util.spec_from_file_location("carry_form_server", _SERVER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def setup(ctx: dict) -> None:
    mod = _load_server_module()
    handle = mod.start(port=0)          # free loopback port; mints a fresh token
    ctx["server"] = handle
    base = handle.url.rstrip("/")
    ctx["server_last_url"] = base + "/last"
    ctx["server_token_url"] = base + "/token"


def teardown(ctx: dict) -> None:
    h = ctx.get("server")
    if h is not None:
        h.stop()


def start_url(ctx: dict) -> str:
    """Live lane points the agent at a public tunnel (the SSRF gate refuses
    loopback); the selftest lane uses the loopback root (page 1)."""
    return os.environ.get("ANTICIPY_CARRYFORM_URL") or ctx["server"].url


def check(result: dict, ctx: dict) -> tuple[bool, str]:
    nonce = ctx["nonce"]
    # INDEPENDENT re-read #1: the token the server actually displayed on page 1.
    try:
        tok_raw = ctx["http_get"](ctx["server_token_url"])
        displayed = (json.loads(tok_raw or "{}") or {}).get("token") or ""
    except Exception as e:
        return False, f"could not read /token off the grader backend: {e}"
    if not displayed:
        return False, "grader displayed no token (server not initialised)"

    # INDEPENDENT re-read #2: what the backend actually received in the submit.
    try:
        last_raw = ctx["http_get"](ctx["server_last_url"])
        last = json.loads(last_raw or "{}")
    except Exception as e:
        return False, f"could not read /last off the grader backend: {e}"
    if not last:
        return False, "backend recorded no submission (/last is empty — no real submit landed)"

    # The load-bearing carry assertion: the submitted token must equal the token
    # the server truly displayed on page 1 (proves a genuine cross-page read).
    got_token = last.get("claim_token")
    if got_token != displayed:
        return False, (f"carried token mismatch: submitted {got_token!r} but page 1 showed "
                       f"{displayed!r} (agent did not truly read/carry the token)")

    want = {
        "fullname": f"Analyst {nonce}",
        "department": "operations",
    }
    for k, v in want.items():
        if last.get(k) != v:
            return False, f"backend recorded {k}={last.get(k)!r}, expected {v!r}"
    if last.get("confirm") not in ("yes", ["yes"]):
        return False, "confirm checkbox was not ticked in the submitted form"
    return True, f"carried the page-1 token {displayed!r} into a real submit (department=operations)"


def _submit(ctx: dict, fields: dict) -> None:
    """Helper used only by the selftest to emulate a real trusted submit."""
    import urllib.parse
    import urllib.request
    body = urllib.parse.urlencode(fields).encode()
    url = ctx["server"].url.rstrip("/") + "/submit"
    urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=5).read()


def synth_pass(ctx: dict) -> dict:
    nonce = ctx["nonce"]
    token = ctx["server"].token()       # the agent WOULD have read this off page 1
    _submit(ctx, {"claim_token": token, "fullname": f"Analyst {nonce}",
                  "department": "operations", "notes": "", "confirm": "yes"})
    return {
        "answer": f"Read the claim token {token} and submitted the confirmed claim.",
        "final_url": ctx["server"].url + "submit",
        "final_text": "<h1>Claim received</h1>",
        "metrics": {"steps": 11, "est_cost_usd": 0.0187, "frontier_pct": 25.0,
                    "vision_pct": 55.0, "region_pct": 70.0, "replayed": False},
        "task_succeeded": True,
    }


def synth_fail(ctx: dict) -> dict:
    # The failure mode this task is built to catch: the agent NEVER read page 1
    # and submits a guessed token. The name/department are right, but the carried
    # token is wrong, so the /token-vs-/last comparison rejects it.
    nonce = ctx["nonce"]
    _submit(ctx, {"claim_token": "CLM-GUESSED", "fullname": f"Analyst {nonce}",
                  "department": "operations", "notes": "", "confirm": "yes"})
    return {
        "answer": f"Submitted the claim for Analyst {nonce}.",
        "final_url": ctx["server"].url + "submit",
        "final_text": "<h1>Claim received</h1>",
        "metrics": {"steps": 4, "est_cost_usd": 0.006, "frontier_pct": 0.0,
                    "vision_pct": 0.0, "region_pct": 0.0, "replayed": False},
        "task_succeeded": True,   # deliberately lies; the checker must override this
    }
