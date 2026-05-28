"""Unit tests for the V7 action binder. Exit 0 if every test passes.

Covers: email-with-resolved-person, money-requires-confirm,
unknown-person-asks-not-declines, recipe-seeds-planner, router
exposes both /api/action/bind and /api/action/bind_and_execute.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ENGINE = _ROOT / "engine"
if str(_ENGINE) not in sys.path:
    sys.path.insert(0, str(_ENGINE))


_PASS: list[str] = []
_FAIL: list[tuple[str, str]] = []


def _ok(name: str) -> None:
    _PASS.append(name)
    print(f"PASS  {name}")


def _bad(name: str, reason: str) -> None:
    _FAIL.append((name, reason))
    print(f"FAIL  {name}: {reason}")


def _assert(cond: bool, name: str, reason: str = "") -> bool:
    if cond:
        _ok(name)
        return True
    _bad(name, reason or "assertion failed")
    return False


def test_email_with_resolved_person() -> None:
    from app.product.action_binder import bind
    intent = {"intent_id": "i1", "text": "Draft email to Maya about Friday"}
    context = {"resolved_people": {
        "Maya": {"email": "maya@example.com", "display_name": "Maya R."}}}
    b = bind(intent, context, account_id="a1", device_id="d1")
    _assert(b.surface_target == "gmail", "email.surface_target=gmail",
            f"got {b.surface_target}")
    _assert(b.prefilled_slots.get("recipient_email") == "maya@example.com",
            "email.recipient_email_prefilled", f"got {b.prefilled_slots}")
    _assert(b.confirm_required is False,
            "email.draft_confirm_required_false", f"got {b.confirm_required}")
    _assert(not any(p.get("primitive") == "ask_user"
                     for p in b.planned_primitives),
            "email.no_ask_user_when_resolved", f"got {b.planned_primitives}")
    _assert(b.binding_id.startswith("bind-"), "email.binding_id_shape",
            f"got {b.binding_id}")


def test_money_requires_confirm() -> None:
    from app.product.action_binder import bind
    intent = {"intent_id": "i2", "text": "Pay $50 to Marcus for dinner"}
    context = {"resolved_people": {"Marcus": {"display_name": "Marcus L."}}}
    b = bind(intent, context, account_id="a1", device_id="d1")
    _assert(b.confirm_required is True, "money.confirm_required_true",
            f"got {b.confirm_required}")
    _assert(b.risk_reason in {"money_transfer", "transactional_surface"},
            "money.risk_reason_money", f"got {b.risk_reason}")
    _assert(b.prefilled_slots.get("amount") == 50.0,
            "money.amount_prefilled", f"got {b.prefilled_slots}")


def test_unknown_person_asks_not_declines() -> None:
    from app.product.action_binder import bind, execute_binding
    intent = {"intent_id": "i3", "text": "Draft email to Cassandra"}
    b = bind(intent, {"resolved_people": {}}, account_id="a1", device_id="d1")
    _assert(bool(b.planned_primitives), "unknown.has_planned_primitives",
            f"got {b.planned_primitives}")
    _assert(any(p.get("primitive") == "ask_user"
                 for p in b.planned_primitives),
            "unknown.first_primitive_is_ask_user",
            f"got {b.planned_primitives}")
    _assert("recipient_email" in b.missing_slots,
            "unknown.recipient_email_missing", f"got {b.missing_slots}")
    result = execute_binding(b)
    _assert(result.get("status") == "ask_user",
            "unknown.execute_returns_ask_user", f"got {result}")
    _assert(str(result.get("status") or "").lower() != "declined",
            "unknown.execute_never_declined", f"got {result}")


def test_recipe_seeds_planner() -> None:
    from app.product.action_binder import bind
    intent = {"intent_id": "i4", "text": "Draft email to Maya about launch"}
    context = {
        "resolved_people": {"Maya": {"email": "maya@example.com"}},
        "learned_recipes": [{
            "recipe_id": "rec-1", "surface_target": "gmail",
            "intent_summary": "draft email to teammate about launch",
            "primitives": [{"primitive": "open", "args": {
                "url": "https://mail.google.com/"}}]}]}
    b = bind(intent, context, account_id="a1", device_id="d1")
    _assert(b.recipe_id == "rec-1", "recipe.id_selected", f"got {b.recipe_id}")
    _assert(len(b.planned_primitives) >= 1, "recipe.primitives_seeded",
            f"got {b.planned_primitives}")


def test_endpoints_register() -> None:
    from fastapi import FastAPI
    from app.product.action_binder_endpoints import router
    app = FastAPI()
    app.include_router(router)
    paths = {getattr(r, "path", None) for r in app.routes}
    _assert("/api/action/bind" in paths, "router.bind_path", str(paths))
    _assert("/api/action/bind_and_execute" in paths,
            "router.bind_and_execute_path", str(paths))


def main() -> int:
    test_email_with_resolved_person()
    test_money_requires_confirm()
    test_unknown_person_asks_not_declines()
    test_recipe_seeds_planner()
    test_endpoints_register()
    print(f"\nPASSED {len(_PASS)}  FAILED {len(_FAIL)}")
    if _FAIL:
        for name, reason in _FAIL:
            print(f"  - {name}: {reason}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
