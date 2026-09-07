"""Adversarial spend controls. No provider requests or credentials used."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from proof.audit.model_gateway import Budget, Refused, prepare


def ledger(tmp_path, limit=5):
    path = tmp_path / "spend.json"
    path.write_text(json.dumps({"budget_usd": limit, "calls": []}))
    return Budget(path, operating_limit=limit)


def test_racing_requests_cannot_each_spend_the_same_balance(tmp_path):
    budget = ledger(tmp_path)

    def reserve(_):
        try:
            return budget.reserve(3, "test", b"body")
        except Refused:
            return None

    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(reserve, range(20)))
    assert sum(x is not None for x in results) == 1
    assert Budget.committed(json.loads(budget.path.read_text())) == 3


def test_concurrent_people_keep_distinct_cost_attribution(tmp_path):
    budget = ledger(tmp_path, 50)
    with ThreadPoolExecutor(4) as pool:
        calls = list(pool.map(lambda n: budget.reserve(1, "test", b"same input", f"cohort/{n}"), range(4)))
    for i, call in enumerate(reversed(calls)):
        budget.finish(call, {"usage": {"cost": (i + 1) / 10}}, "returned")
    state = json.loads(budget.path.read_text())
    by_person = {c["audit_run"]: c["cost_usd"] for c in state["calls"]}
    assert by_person == {"cohort/0": 0.4, "cohort/1": 0.3, "cohort/2": 0.2, "cohort/3": 0.1}


def test_crash_and_unknown_usage_do_not_release_money(tmp_path):
    budget = ledger(tmp_path)
    first = budget.reserve(3, "test", b"body")
    recovered = Budget(budget.path, operating_limit=5)
    recovered.finish(first, {"id": "provider-generation", "usage": {"tokens": 42}})
    with pytest.raises(Refused):
        recovered.reserve(3, "test", b"body")
    recovered.finish(first, {"usage": {"cost": 0.25}}, "returned")
    assert recovered.reserve(3, "test", b"new body")


def test_provider_exceeding_reservation_halts_new_calls(tmp_path):
    budget = ledger(tmp_path, 50)
    call = budget.reserve(1, "test", b"body")
    budget.finish(call, {"usage": {"cost": 1.01}}, "returned")
    with pytest.raises(Refused):
        budget.reserve(1, "test", b"body")


PRICING = {"test/model": {"context_length": 100000, "pricing": {
    "prompt": "0.000001", "completion": "0.000002",
    "overrides": [{"min_prompt_tokens": 10, "prompt": "0.000003"}],
}}}


def test_prices_reserve_entire_context_and_enforce_endpoint_ceiling():
    raw = {"model": "test/model", "messages": [{"role": "user", "content": [
        {"type": "text", "text": "example", "cache_control": {"type": "ephemeral"}},
    ]}], "max_tokens": 999999}
    data, cost = prepare(raw, PRICING)
    assert cost == pytest.approx(0.3 + 4096 * 0.000002)
    assert data["provider"]["max_price"] == {"prompt": 3, "completion": 2, "request": 0}
    assert data["max_tokens"] == 4096
    assert "cache_control" not in data["messages"][0]["content"][0]
    assert "cache_control" in raw["messages"][0]["content"][0]


@pytest.mark.parametrize("extra", [
    {"plugins": [{"id": "web"}]}, {"model": "unpriced/model"},
    {"stream": True}, {"n": 2}, {"provider": {"max_price": {"prompt": 999}}},
    {"tools": [{"type": "web_search"}]},
    {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": "https://example.invalid/image"}}]}]},
])
def test_extra_charges_cannot_bypass_priced_text_path(extra):
    with pytest.raises(Refused):
        prepare({"model": "test/model", "messages": [{"role": "user", "content": "example"}], **extra}, PRICING)
