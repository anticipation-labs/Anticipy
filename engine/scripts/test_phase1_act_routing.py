"""Phase 1 (THE SPINE) routing test — UNATTENDED, no real Chrome.

Proves _run_browser_and_confirm drives the CONNECTED real-Chrome hand (WebVoyagerAgent over
browser_link) when the extension is attached, falls back to the throwaway browse_act when it is not,
normalizes both result shapes onto the card, and NEVER claims success when the connected agent hands
back (needs_human). The live "acts in real Gmail" proof is BLOCKED-ON-OMAR; this verifies the routing
+ adapter logic with mocks (so the ratchet can protect it).
"""
import asyncio
import os
import tempfile
import types
from pathlib import Path

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")
os.environ.setdefault("ANTICIPY_TICK_SECONDS", "0")
os.environ.setdefault("ANTICIPY_INBOUND_POLL_SECONDS", "0")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402
import anticipy_engine.agent.webvoyager as wv  # noqa: E402
import anticipy_engine.hands.browser_use_link as bul  # noqa: E402

fails = []
def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f" :: {detail}"))
    if not cond:
        fails.append(name)

with tempfile.TemporaryDirectory() as d:
    core = ControlCore(data_dir=Path(d))
    # Isolate routing from card I/O: capture what would be landed on the card.
    landed = {}
    core._land_browser_result_on_card = (
        lambda ask_id, *, success, answer, url, screenshot, screenshot_path=None:
        landed.update({"ask_id": ask_id, "success": success, "answer": answer,
                       "url": url, "screenshot": screenshot}))

    used = {"agent": False, "browse_act": False}

    class FakeAgent:
        def __init__(self, link, gateway, max_steps=16):
            pass
        async def run(self, task, start_url):
            used["agent"] = True
            return {"answer": "Found the dentist number: 555-0100",
                    "final_url": "https://ex.com/done", "final_shot": "<imgdata>", "steps": 3}

    def fake_browse_act(*a, **k):
        used["browse_act"] = True
        return types.SimpleNamespace(success=True, result="THROWAWAY RESULT",
                                     url="https://throwaway", screenshot=False, screenshot_path=None)

    wv.WebVoyagerAgent = FakeAgent
    bul.browse_act = fake_browse_act

    # --- A: extension CONNECTED -> the real-Chrome hand, NOT the throwaway ---
    core.browser_link.connected = True
    landed.clear(); used.update(agent=False, browse_act=False)
    asyncio.run(core._run_browser_and_confirm("call the dentist", "https://ex.com", "ask1"))
    check("connected -> used WebVoyagerAgent (real Chrome), not browse_act",
          used["agent"] and not used["browse_act"], str(used))
    check("connected -> agent answer normalized onto card",
          landed.get("answer") == "Found the dentist number: 555-0100", str(landed))
    check("connected -> agent final_url normalized onto card",
          landed.get("url") == "https://ex.com/done", str(landed))
    check("connected -> final_shot normalized to screenshot=True",
          landed.get("screenshot") is True, str(landed))
    check("connected -> clean answer = success True", landed.get("success") is True, str(landed))

    # --- B: NOT connected -> throwaway browse_act fallback (unchanged behavior) ---
    core.browser_link.connected = False
    landed.clear(); used.update(agent=False, browse_act=False)
    asyncio.run(core._run_browser_and_confirm("call the dentist", "https://ex.com", "ask2"))
    check("not-connected -> used browse_act fallback, not the agent",
          used["browse_act"] and not used["agent"], str(used))
    check("not-connected -> throwaway result landed", landed.get("answer") == "THROWAWAY RESULT", str(landed))

    # --- C: connected but agent hands back (needs_human) -> NEVER fake success ---
    class FakeAgentWall:
        def __init__(self, link, gateway, max_steps=16):
            pass
        async def run(self, task, start_url):
            used["agent"] = True
            return {"answer": "", "final_url": "https://login", "needs_human": True, "steps": 1}
    wv.WebVoyagerAgent = FakeAgentWall
    core.browser_link.connected = True
    landed.clear(); used.update(agent=False, browse_act=False)
    asyncio.run(core._run_browser_and_confirm("log into the bank", "https://login", "ask3"))
    check("connected wall (needs_human) -> success FALSE (handed back, not faked)",
          landed.get("success") is False, str(landed))

print("PHASE1 ROUTING:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
import sys
sys.exit(1 if fails else 0)
