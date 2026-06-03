"""Piece 1 test: gateway keeps the deterministic stub by default AND can drive a
real model (OpenRouter) with text + vision. Makes a couple of real (cheap) calls.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_gateway_real.py
"""
import asyncio
import base64

from anticipy_engine.core.env import load_local_env

load_local_env()

from anticipy_engine.core.gateway import CHEAP, SMART, PROVIDER_OPENROUTER, ModelGateway


async def main():
    # 1) stub default — deterministic + free, unchanged
    stub = ModelGateway()
    assert stub.provider == "stub"
    assert "send_email" in await stub.think("Plan: send Sarah the deck", tier=SMART, caller="plan")

    # 2) real OpenRouter, text (cheap tier)
    gw = ModelGateway(provider=PROVIDER_OPENROUTER)
    txt = await gw.think("Reply with exactly: OK", tier=CHEAP, caller="agent")
    assert "OK" in txt.upper(), txt

    # 3) real OpenRouter, vision (benign Amazon screenshot)
    img = "data:image/jpeg;base64," + base64.b64encode(open("/tmp/anticipy_hard_proof.jpg", "rb").read()).decode()
    vis = await gw.think("What website is this screenshot from? One word.", tier=CHEAP, caller="agent", image=img)
    assert "amazon" in vis.lower(), vis

    # 4) smart tier still locked to allowed callers
    refused = False
    try:
        await gw.think("x", tier=SMART, caller="random_worker")
    except PermissionError:
        refused = True
    assert refused

    print("PASS piece 1: real model gateway (stub default + OpenRouter text + vision + smart-lock)")
    print("  text:", txt.strip()[:40])
    print("  vision:", vis.strip()[:40])


if __name__ == "__main__":
    asyncio.run(main())
