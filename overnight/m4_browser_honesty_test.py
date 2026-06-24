#!/usr/bin/env python3
"""M4 acceptance — the browser arm NEVER fakes done. A finished-but-WRONG task must return
needs_human, never success. Pure unit test (mocked browse_act + judge, no live browser).
Run: engine/.venv/bin/python overnight/m4_browser_honesty_test.py"""
import asyncio, sys, os, types
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))
import anticipy_engine.main as main
from anticipy_engine.main import AgentActIn

fails = []
def check(name, cond, detail=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {'' if cond else ':: '+str(detail)}")
    if not cond: fails.append(name)

def fake_res(success, result, error=None):
    return types.SimpleNamespace(success=success, result=result, url="https://example.com/done",
        steps=3, actions=[], allowed_domains=["example.com"], error=error)

_verdict = {"success": False, "reason": "stub"}
async def _stub_judge(gw, task, result, image=None):
    return dict(_verdict)
main.judge = _stub_judge
def run(body): return asyncio.run(main.agent_act(body))
body = lambda: AgentActIn(task="buy the blue ceramic mug", start_url="https://example.com", max_steps=4)

# CASE 1 — agent finished but did the WRONG thing (judge says false): NO false success
main.browser_use_link.browse_act = lambda task, url, max_steps, cdp_url=None: fake_res(True, "bought a red mug")
_verdict = {"success": False, "reason": "wrong color"}
r = run(body())
check("finished+wrong -> success is False", r["success"] is False, r)
check("finished+wrong -> task_succeeded False", r["task_succeeded"] is False)
check("finished+wrong -> needs_human True", r["needs_human"] is True)
check("finished+wrong -> agent_finished True (honest self-report)", r["agent_finished"] is True)

# CASE 2 — agent finished AND judge verifies: real success
_verdict = {"success": True, "reason": "correct item in cart"}
r = run(body())
check("finished+verified -> success True", r["success"] is True, r)
check("finished+verified -> task_succeeded True", r["task_succeeded"] is True)
check("finished+verified -> needs_human False", r["needs_human"] is False)

# CASE 3 — hard infra error: a tool failure, NOT a human-clearable wall, NOT success
main.browser_use_link.browse_act = lambda task, url, max_steps, cdp_url=None: fake_res(False, "", error="bridge down")
r = run(body())
check("hard error -> success False", r["success"] is False)
check("hard error -> needs_human False (tool failure, not a wall)", r["needs_human"] is False)
check("hard error -> error surfaced", r["error"] == "bridge down")

print(f"\nM4 BROWSER HONESTY: {'ALL PASS' if not fails else str(len(fails))+' FAILED'}")
sys.exit(1 if fails else 0)
