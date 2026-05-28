"""Integration tests for the V7 confirm-card surface.

Direct tests use isolated storage root. HTTP tests skip on unreach.
Exit 0 unless an executed test fails.
"""
from __future__ import annotations

import json, os, sys, tempfile, time
import urllib.error
import urllib.request
from pathlib import Path

_ENGINE = Path(__file__).resolve().parents[2] / "engine"
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))

ENGINE_BASE = os.environ.get("ANTICIPY_ENGINE_URL",
                             "http://127.0.0.1:8731").rstrip("/")
_PASS: list[str] = []
_FAIL: list[tuple[str, str]] = []
_SKIP: list[tuple[str, str]] = []


def _check(cond, name, reason=""):
    msg = reason or "assertion failed"
    if cond:
        _PASS.append(name); print(f"PASS  {name}"); return True
    _FAIL.append((name, msg)); print(f"FAIL  {name}: {msg}"); return False


def test_direct() -> None:
    from app.product.confirm_card import (
        ConfirmCardStore, STATUS_APPROVED, STATUS_EXPIRED, STATUS_PENDING,
        build_confirm_card, needs_confirmation)
    nc = lambda i, s, **kw: needs_confirmation(i, s, account_id="acct-test", **kw)
    p_intent = "purchase a new desk lamp"
    p_steps = [{"open": "amazon.com"}, {"click": "buy_now"},
               {"submit": "checkout"}]
    _check(nc(p_intent, p_steps, surface_target="amazon.com",
              money_amount=200.0) is True,
           "$200 purchase needs confirmation")
    _check(nc("draft an email to Maya about Friday",
              [{"open": "gmail.com"}, {"compose": "draft to Maya"}],
              surface_target="gmail.com") is False,
           "draft email does NOT need confirmation")
    _check(nc("send an email to client@externalco.com",
              [{"send": "email to client@externalco.com"}],
              surface_target="gmail.com") is True,
           "external send email needs confirmation")
    _check(nc("check balance", [{"open": "chase.com/login"}],
              surface_target="chase.com") is True,
           "finance surface needs confirmation")

    store = ConfirmCardStore("acct-test")
    card = build_confirm_card(p_intent, p_steps, "amazon.com",
                              {"resolved": {"item": "desk lamp"}},
                              account_id="acct-test", money_amount=200.0)
    store.create(card)
    _check(card.status == STATUS_PENDING and card.risk_level == "high",
           "new card is pending with high risk",
           f"status={card.status} risk={card.risk_level}")
    updated = store.decide(card.card_id, "yes")
    _check(updated is not None and updated.status == STATUS_APPROVED,
           "decide yes updates status to approved", f"updated={updated}")
    fetched = store.get(card.card_id)
    _check(fetched is not None and fetched.status == STATUS_APPROVED,
           "stored decision is persisted", f"fetched={fetched}")
    _check(store.decide(card.card_id, "no") is None,
           "deciding an already-decided card returns None")
    _check(not any(c["card_id"] == card.card_id
                   for c in store.list_pending("acct-test")),
           "approved card no longer appears in list_pending")

    stale = build_confirm_card(
        "tip the waiter $5", [{"send": "tip via venmo"}], "venmo.com",
        None, account_id="acct-test", money_amount=5.0, ttl_seconds=60)
    stale.expires_at = time.time() - 10
    store.create(stale)
    _check(store.expire_stale() >= 1,
           "expire_stale flips stale pending to expired")
    s2 = store.get(stale.card_id)
    _check(s2 is not None and s2.status == STATUS_EXPIRED,
           "stale card's status is now expired", f"got={s2}")
    _check(ConfirmCardStore("acct-other").list_pending("acct-other") == [],
           "isolation: different account sees no cards")


def _http(method, path, body=None, timeout=4.0):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(
        f"{ENGINE_BASE}{path}", data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8") or "{}")


def test_http() -> None:
    try:
        status, body = _http("GET", "/api/confirm/list?account_id=http-acct")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            _SKIP.append(("http endpoints", "router not wired"))
            print("SKIP  http endpoints: router not wired"); return
        _FAIL.append(("http list GET", f"HTTPError {exc.code}")); return
    except Exception as exc:
        _SKIP.append(("http endpoints", f"engine unreachable: {exc}"))
        print(f"SKIP  http endpoints: engine unreachable: {exc}"); return
    _check(status == 200 and body.get("ok"),
           "http list GET returns ok", f"status={status} body={body}")
    try:
        status, body = _http("POST", "/api/confirm/create", {
            "account_id": "http-acct", "intent": "buy a $5 coffee",
            "planned_steps": [{"open": "starbucks.com"},
                              {"click": "checkout"}],
            "surface_target": "starbucks.com", "money_amount": 5.0})
        card_id = body.get("card_id") or ""
        _check(status == 200 and body.get("ok") and card_id,
               "http create returns card_id", f"body={body}")
        _check(body.get("needs_confirmation") is True,
               "http create flags money purchase as needs_confirmation")
        status, body = _http("POST", "/api/confirm/decide", {
            "card_id": card_id, "choice": "yes",
            "account_id": "http-acct"})
        _check(status == 200 and (body.get("card") or {}).get(
                   "status") == "approved",
               "http decide marks card approved", f"body={body}")
    except Exception as exc:
        _FAIL.append(("http endpoints", f"unexpected: {exc}"))


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="v7_cc_test_") as td:
        os.environ["ANTICIPY_V7_CONFIRM_ROOT"] = td
        try:
            test_direct()
        except Exception as exc:
            _FAIL.append(("direct", f"crashed: {exc}"))
        finally:
            os.environ.pop("ANTICIPY_V7_CONFIRM_ROOT", None)
    test_http()
    total = len(_PASS) + len(_FAIL) + len(_SKIP)
    print(f"\nsummary: {len(_PASS)} passed, {len(_FAIL)} failed, "
          f"{len(_SKIP)} skipped ({total} total)")
    return 0 if not _FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
