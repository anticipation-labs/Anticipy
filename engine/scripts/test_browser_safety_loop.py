"""Browser agent IN-LOOP guardrail contract — proven through the real WebVoyagerAgent.run().

The agent-level "refusals" (don't click a final-purchase control, don't type a credential, don't
act on a checkout page) are NOT always-on product behaviour. They are a SAFETY/DEMO mode gated by
ANTICIPY_BROWSER_UNLOCKED (default ON = the brain decides, the hands act). Real-world spend is
gated ask-first at the spine, not by a blanket refusal in the hands. This drives the actual loop
with a FakeLink + a scripted gateway and pins BOTH sides of the flag:
  1. UNLOCKED (default): a click on a purchase control IS dispatched (no safety stop) — the agent
     is free to complete real flows;
  2. LOCKED (ANTICIPY_BROWSER_UNLOCKED=0): the SAME click is stopped BEFORE the browser sees it
     (stopped_for_safety, honest hand-back, money not spent).
The SSRF / private-IP security boundary is separate and ALWAYS on (test_navwall.py).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_browser_safety_loop.py
"""
import asyncio
import json

import anticipy_engine.agent.webvoyager as wv
from anticipy_engine.agent.webvoyager import PURCHASE_GUARD, WebVoyagerAgent

# A review page whose only actionable controls are a FINAL-PURCHASE button and a benign nav link.
PURCHASE_PAGE = {
    "url": "https://shop.test/review",
    "title": "Review order",
    "text": "Review your order before continuing.",
    "elements": [
        {"idx": 0, "role": "button", "name": "Place your order", "inView": True},
        {"idx": 1, "role": "a", "name": "Continue shopping", "inView": True},
    ],
}


class FakeLink:
    """Serves the review page on observe; records every act actually dispatched to the browser."""

    def __init__(self):
        self.actions = []

    async def send_browse(self, job_id, intent, args, timeout):
        if intent == "observe":
            return {"type": "result", "job_id": job_id, "status": "success",
                    "output": dict(PURCHASE_PAGE),
                    "proof": {"screenshot": "data:image/png;base64,xx", "id": "p1"}}
        self.actions.append(args or {})  # an act reached the browser
        return {"type": "result", "job_id": job_id, "status": "success",
                "output": dict(PURCHASE_PAGE),
                "proof": {"screenshot": "data:image/png;base64,xx", "id": "p1"}}


class ClickGateway:
    """A scripted 'model': plan, then click a fixed element idx, then (if asked again) answer."""

    def __init__(self, click_idx):
        self.click_idx = click_idx
        self.acted = False

    async def think(self, task, tier=None, caller=None, image=None, json_mode=False,
                    temperature=None, max_tokens=None):
        if "PLAN_SYS" in task or task.startswith("Break the task"):
            return json.dumps({"subgoals": ["review the page", "finish"]})
        if not self.acted:
            self.acted = True
            return json.dumps({"action": "click", "index": self.click_idx})
        return json.dumps({"action": "answer", "answer": "done looking"})


async def test_unlocked_dispatches_purchase_click():
    # DEFAULT (unlocked): the brain decides; the hands carry out a purchase click — no refusal.
    assert wv.BROWSER_UNLOCKED is True, "default posture must be UNLOCKED (the brain decides)"
    link = FakeLink()
    agent = WebVoyagerAgent(link, ClickGateway(click_idx=0), max_steps=4, per_subgoal=3)
    result = await agent.run(task="Place the order on this page.", start_url="https://shop.test/review")
    assert not result.get("stopped_for_safety"), result
    assert any(a.get("action") == "click" for a in link.actions), (
        "UNLOCKED: the purchase click must reach the browser (the agent completes the flow)", link.actions)
    print("PASS unlocked: agent.run() dispatched 'Place your order' (the brain decides, hands act)")


async def test_locked_stops_purchase_click():
    # SAFETY MODE (locked): the SAME click is refused before the browser sees it.
    assert PURCHASE_GUARD.search("Place your order"), "fixture purchase control must match the guard"
    saved = wv.BROWSER_UNLOCKED
    wv.BROWSER_UNLOCKED = False
    try:
        link = FakeLink()
        agent = WebVoyagerAgent(link, ClickGateway(click_idx=0), max_steps=4, per_subgoal=3)
        result = await agent.run(task="Tell me what this page shows.", start_url="https://shop.test/review")
        assert result.get("stopped_for_safety") is True, result
        assert "STOPPED before a purchase control" in (result.get("answer") or ""), result
        assert link.actions == [], ("a purchase click was dispatched in safety mode (money path!)", link.actions)
    finally:
        wv.BROWSER_UNLOCKED = saved
    print("PASS locked: ANTICIPY_BROWSER_UNLOCKED=0 stops 'Place your order' before the browser sees it")


async def test_normal_click_not_overblocked():
    link = FakeLink()
    agent = WebVoyagerAgent(link, ClickGateway(click_idx=1), max_steps=4, per_subgoal=3)
    result = await agent.run(task="Tell me what this page shows.", start_url="https://shop.test/review")
    assert not result.get("stopped_for_safety"), result
    assert any(a.get("action") == "click" for a in link.actions), ("benign click was wrongly blocked", link.actions)
    print("PASS scope: a 'Continue shopping' click is dispatched normally (no false safety stop)")


async def main():
    await test_unlocked_dispatches_purchase_click()
    await test_locked_stops_purchase_click()
    await test_normal_click_not_overblocked()


if __name__ == "__main__":
    asyncio.run(main())
