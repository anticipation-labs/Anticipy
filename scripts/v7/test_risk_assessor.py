"""V7 risk assessor tests. Exit 0 on pass, 1 on fail.

Load-bearing assertion: no case may emit proceed_mode=="decline".
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ENGINE = _ROOT / "engine"
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))


_PASSED: list[str] = []
_FAILED: list[tuple[str, str]] = []
_ALL_MODES: list[str] = []


def _ok(name: str) -> None:
    _PASSED.append(name)
    print(f"PASS  {name}")


def _fail(name: str, reason: str) -> None:
    _FAILED.append((name, reason))
    print(f"FAIL  {name}: {reason}")


def _assert(cond: bool, name: str, reason: str = "") -> bool:
    if cond:
        _ok(name)
        return True
    _fail(name, reason or "assertion failed")
    return False


def _record(mode: str) -> None:
    _ALL_MODES.append(mode)


def _new_app_with_router():
    from fastapi import FastAPI
    from app.product.risk_assessor_endpoints import router
    app = FastAPI()
    app.include_router(router)
    return app


def test_pay_500_to_marcus():
    from app.product.risk_assessor import assess
    a = assess("Pay $500 to Marcus", {}, {})
    _record(a.proceed_mode)
    _assert(a.level == "high", "pay_500.high", f"got {a.level}")
    _assert(a.proceed_mode == "confirm", "pay_500.confirm",
            f"got {a.proceed_mode}")
    _assert(a.money_amount == 500.0, "pay_500.money=500",
            f"got {a.money_amount}")
    _assert(a.confirm_card_required is True, "pay_500.card_required")


def test_send_external_email():
    from app.product.risk_assessor import assess
    a = assess(
        "Send email to external@example.com about Friday",
        {"recipients": ["external@example.com"],
         "surface_target": "mail.google.com"}, {})
    _record(a.proceed_mode)
    _assert(a.level in ("medium", "high"), "send_external.level",
            f"got {a.level}")
    _assert(a.proceed_mode == "confirm", "send_external.confirm",
            f"got {a.proceed_mode}")
    _assert(a.confirm_card_required is True, "send_external.card_required")


def test_add_note():
    from app.product.risk_assessor import assess
    a = assess("Add note: dentist 3pm", {}, {})
    _record(a.proceed_mode)
    _assert(a.level == "low", "add_note.low", f"got {a.level}")
    _assert(a.proceed_mode == "silent", "add_note.silent",
            f"got {a.proceed_mode}")
    _assert(a.confirm_card_required is False, "add_note.no_card")
    _assert(a.money_amount is None, "add_note.no_money")


def test_delete_payroll_with_do_not_touch():
    from app.product.risk_assessor import assess
    a = assess("Delete payroll spreadsheet",
               {"do_not_touch_warnings": ["never touch payroll"]}, {})
    _record(a.proceed_mode)
    _assert(a.level == "high", "delete_payroll.high", f"got {a.level}")
    _assert(a.proceed_mode == "ask", "delete_payroll.ask",
            f"got {a.proceed_mode}")
    _assert(a.confirm_card_required is True,
            "delete_payroll.card_required")


def test_email_ambiguous_with_missing_slots():
    from app.product.risk_assessor import assess
    a = assess("Email ambiguous_person", {"missing_slots": ["email"]}, {})
    _record(a.proceed_mode)
    _assert(a.level == "medium", "missing_slots.medium",
            f"got {a.level}")
    _assert(a.proceed_mode == "ask", "missing_slots.ask",
            f"got {a.proceed_mode}")


def test_money_word_parsing_variants():
    from app.product.risk_assessor import parse_money_amount, assess

    _assert(parse_money_amount("Pay $50") == 50.0, "money.$50")
    _assert(parse_money_amount("$1,200.50 to vendor") == 1200.50,
            "money.$1,200.50")
    _assert(parse_money_amount("send fifty dollars") == 50.0,
            "money.fifty_dollars")
    _assert(parse_money_amount("one thousand dollars") == 1000.0,
            "money.one_thousand_dollars")
    _assert(parse_money_amount("no money here") is None, "money.none")
    a = assess("Wire one thousand dollars to ops", {}, {})
    _record(a.proceed_mode)
    _assert(a.money_amount == 1000.0, "assess.wire.money=1000")
    _assert(a.proceed_mode == "confirm", "assess.wire.confirm")


def test_never_decline_contract_for_known_cases():
    if "decline" in _ALL_MODES:
        _fail("never_decline_contract", "decline observed")
        return
    _ok("never_decline_contract")


def test_router_registers():
    app = _new_app_with_router()
    paths = {getattr(r, "path", None) for r in app.routes}
    _assert("/api/risk/assess" in paths, "router.registered",
            f"paths={sorted(paths)}")


def test_endpoint_returns_no_decline():
    from fastapi.testclient import TestClient

    client = TestClient(_new_app_with_router())
    bodies = [
        {"intent": "Pay $500 to Marcus"},
        {"intent": "Send email to a@b.com",
         "binding": {"recipients": ["a@b.com"]}},
        {"intent": "Add note dentist"},
        {"intent": "Delete payroll spreadsheet",
         "binding": {"do_not_touch_warnings": ["payroll"]}},
        {"intent": "Email ambiguous_person",
         "binding": {"missing_slots": ["email"]}},
        {"intent": ""},
    ]
    saw_decline = False
    for body in bodies:
        resp = client.post("/api/risk/assess", json=body)
        _assert(resp.status_code == 200,
                f"endpoint.200 {body.get('intent','')[:20]}",
                f"status={resp.status_code}")
        out = resp.json()
        if out.get("proceed_mode") == "decline":
            saw_decline = True
        _assert(out.get("proceed_mode") in
                {"silent", "notify", "confirm", "ask"},
                f"endpoint.mode_valid {body.get('intent','')[:20]}",
                f"got {out.get('proceed_mode')}")
    _assert(saw_decline is False, "endpoint.never_decline")


def main() -> int:
    test_pay_500_to_marcus()
    test_send_external_email()
    test_add_note()
    test_delete_payroll_with_do_not_touch()
    test_email_ambiguous_with_missing_slots()
    test_money_word_parsing_variants()
    test_never_decline_contract_for_known_cases()
    try:
        test_router_registers()
        test_endpoint_returns_no_decline()
    except Exception as exc:
        _fail("http_surface_tests", f"{type(exc).__name__}: {exc}")

    print()
    print(f"PASSED: {len(_PASSED)}")
    print(f"FAILED: {len(_FAILED)}")
    if _FAILED:
        for name, reason in _FAILED:
            print(f"  FAIL {name}: {reason}")
    return 0 if not _FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())
