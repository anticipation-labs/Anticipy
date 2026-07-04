"""S3 — the OpenRouter tier ladder (ACT / GROUND / ESCALATE) + the per-task frontier cap.

Proves, with zero network (httpx.MockTransport echoes back the model each request carried):
  - ACT   routes to act_model   (env ANTICIPY_MODEL_ACT, else the cheap model — a SAFE default).
  - GROUND routes to ground_model (env ANTICIPY_MODEL_GROUND, else the cheap model).
  - ESCALATE routes to escalate_model (claude-opus-4-8 by default) — but only while budget remains.
  - The per-task cap (ANTICIPY_ESCALATE_CAP / escalate_cap) HARD-CAPS ESCALATE: beyond it, the
    call degrades to the SMART model and the ledger records tier=smart + requested_tier=escalate.
  - reset_escalations() re-arms the budget (the actor calls it once per task in run()).
  - Frontier tiers (SMART, ESCALATE) are refused from a caller outside SMART_CALLERS; the cheap
    ACT/GROUND tiers are allowed from anywhere; caller="actor" (the split-out per-step actor) may
    take the frontier rung.
  - The pre-existing SMART/CHEAP contract is untouched (CHEAP -> cheap model, SMART -> smart model).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_gateway_tiers.py
"""
import asyncio
import json
import os

# Deterministic + offline: dummy key (MockTransport intercepts every request), unroutable base URL.
os.environ["ANTICIPY_MODEL_PROVIDER"] = "stub"
os.environ["ANTICIPY_MODEL_API_KEY"] = "test-key-not-real"
os.environ["ANTICIPY_OPENAI_BASE_URL"] = "https://mock.invalid/chat/completions"
# Keep the cap env out of the way; tests set escalate_cap via the constructor.
os.environ.pop("ANTICIPY_ESCALATE_CAP", None)
os.environ.pop("ANTICIPY_MODEL_ACT", None)
os.environ.pop("ANTICIPY_MODEL_GROUND", None)
os.environ.pop("ANTICIPY_MODEL_ESCALATE", None)

import httpx

from anticipy_engine.core.gateway import (
    ACT,
    CHEAP,
    ESCALATE,
    GROUND,
    SMART,
    ModelGateway,
)

fails = []


def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f" :: {detail}"))
    if not cond:
        fails.append(name)


def _echo_transport(seen):
    """MockTransport that records the model each request carried and echoes it back as content."""
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        seen.append(body["model"])
        return httpx.Response(200, json={"choices": [{"message": {"content": body["model"]}}]})
    return httpx.MockTransport(handler)


def _gw(seen, **kw):
    return ModelGateway(provider="openrouter", transport=_echo_transport(seen),
                        cheap_model="cheap/model", smart_model="smart/model", **kw)


async def test_act_ground_default_to_cheap():
    seen = []
    gw = _gw(seen)  # no ACT/GROUND overrides -> SAFE default = the cheap model
    act = await gw.think("do a step", tier=ACT, caller="actor")
    ground = await gw.think("ground it", tier=GROUND, caller="actor")
    check("ACT default -> cheap model (safe default)", act == "cheap/model", act)
    check("GROUND default -> cheap model (safe default)", ground == "cheap/model", ground)


async def test_act_ground_env_override():
    seen = []
    gw = _gw(seen, act_model="qwen/qwen-vl", ground_model="ui/tars")
    act = await gw.think("do a step", tier=ACT, caller="actor")
    ground = await gw.think("ground it", tier=GROUND, caller="actor")
    check("ACT -> configured cheap VLM", act == "qwen/qwen-vl", act)
    check("GROUND -> configured grounder", ground == "ui/tars", ground)


async def test_smart_cheap_unchanged():
    seen = []
    gw = _gw(seen)
    cheap = await gw.think("x", tier=CHEAP, caller="anyone")
    smart = await gw.think("y", tier=SMART, caller="plan")
    check("CHEAP -> cheap model (unchanged)", cheap == "cheap/model", cheap)
    check("SMART -> smart model (unchanged)", smart == "smart/model", smart)


async def test_escalate_routes_to_opus_then_caps():
    seen = []
    gw = _gw(seen, escalate_model="anthropic/claude-opus-4-8", escalate_cap=2)
    a = await gw.think("hard 1", tier=ESCALATE, caller="actor")
    b = await gw.think("hard 2", tier=ESCALATE, caller="actor")
    c = await gw.think("hard 3", tier=ESCALATE, caller="actor")  # over cap -> degrade to SMART
    check("ESCALATE within cap -> opus (call 1)", a == "anthropic/claude-opus-4-8", a)
    check("ESCALATE within cap -> opus (call 2)", b == "anthropic/claude-opus-4-8", b)
    check("ESCALATE over cap -> degrades to smart model", c == "smart/model", c)
    # Ledger: two escalate-priced calls, then a smart-priced call carrying the requested_tier trail.
    capped = [x for x in gw.calls if x.get("requested_tier") == ESCALATE]
    check("capped call is logged tier=smart", bool(capped) and capped[0]["tier"] == SMART, gw.calls)
    esc_calls = [x for x in gw.calls if x["tier"] == ESCALATE]
    check("exactly 2 real ESCALATE calls (the cap)", len(esc_calls) == 2, gw.calls)


async def test_reset_escalations_rearms():
    seen = []
    gw = _gw(seen, escalate_model="anthropic/claude-opus-4-8", escalate_cap=1)
    first = await gw.think("h1", tier=ESCALATE, caller="actor")
    over = await gw.think("h2", tier=ESCALATE, caller="actor")  # over cap
    gw.reset_escalations()
    after = await gw.think("h3", tier=ESCALATE, caller="actor")  # budget re-armed
    check("cap=1: first escalate -> opus", first == "anthropic/claude-opus-4-8", first)
    check("cap=1: second escalate degrades", over == "smart/model", over)
    check("reset_escalations re-arms -> opus again", after == "anthropic/claude-opus-4-8", after)


async def test_frontier_gate():
    seen = []
    gw = _gw(seen)
    # ESCALATE + SMART refused from an untrusted caller; ACT/GROUND allowed from anywhere.
    for tier in (SMART, ESCALATE):
        refused = False
        try:
            await gw.think("sneak", tier=tier, caller="some_worker")
        except PermissionError:
            refused = True
        check(f"{tier} refused from untrusted caller", refused, tier)
    ok = True
    try:
        await gw.think("cheap step", tier=ACT, caller="some_worker")
        await gw.think("cheap ground", tier=GROUND, caller="some_worker")
    except PermissionError:
        ok = False
    check("ACT/GROUND allowed from any caller", ok)
    check("'actor' is a trusted (frontier-capable) caller", "actor" in gw.SMART_CALLERS)


async def main():
    await test_act_ground_default_to_cheap()
    await test_act_ground_env_override()
    await test_smart_cheap_unchanged()
    await test_escalate_routes_to_opus_then_caps()
    await test_reset_escalations_rearms()
    await test_frontier_gate()
    if fails:
        print(f"\nFAILED: {fails}")
        raise SystemExit(1)
    print("\nALL PASS: gateway ACT/GROUND/ESCALATE tiers + per-task frontier cap")


if __name__ == "__main__":
    asyncio.run(main())
