"""Browser agent IN-LOOP money hard-stop — proven through the real WebVoyagerAgent.run().

Money is the only hard action stop. PURCHASE_GUARD is unit-tested at the regex/_pick_button
level (test_purchase_guard.py), but the load-bearing guarantee is that the *running agent loop*
refuses to dispatch a click on a final-purchase control: webvoyager.py:2204-2209 returns
stopped_for_safety BEFORE the click is ever sent to the browser. This drives the actual loop
with a FakeLink + a scripted gateway and asserts:
  1. a click targeting a purchase control => result['stopped_for_safety'] is True, an honest
     hand-back answer, and the browser link NEVER received the purchase click (money not spent);
  2. a click on a normal cart/nav control is NOT over-blocked (it IS dispatched, no safety stop).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_browser_safety_loop.py
"""
import asyncio
import json

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


async def test_inloop_purchase_click_is_stopped():
    # sanity: the page's purchase control really is one the guard recognizes
    assert PURCHASE_GUARD.search("Place your order"), "fixture purchase control must match the guard"
    link = FakeLink()
    agent = WebVoyagerAgent(link, ClickGateway(click_idx=0), max_steps=4, per_subgoal=3)
    result = await agent.run(task="Tell me what this page shows.", start_url="https://shop.test/review")
    assert result.get("stopped_for_safety") is True, result
    assert "STOPPED before a purchase control" in (result.get("answer") or ""), result
    # the load-bearing assertion: the purchase click was caught BEFORE the browser saw it.
    assert link.actions == [], ("a purchase click was dispatched to the browser (money path!)", link.actions)
    print("PASS in-loop money stop: agent.run() refused to dispatch 'Place your order' "
          "(stopped_for_safety, no act reached the browser)")


async def test_inloop_normal_click_not_overblocked():
    link = FakeLink()
    agent = WebVoyagerAgent(link, ClickGateway(click_idx=1), max_steps=4, per_subgoal=3)
    result = await agent.run(task="Tell me what this page shows.", start_url="https://shop.test/review")
    assert not result.get("stopped_for_safety"), result
    # a benign nav control IS dispatched (the guard does not over-block cart/navigation)
    assert any(a.get("action") == "click" for a in link.actions), ("benign click was wrongly blocked", link.actions)
    print("PASS in-loop scope: a 'Continue shopping' click is dispatched normally (no false safety stop)")


async def main():
    await test_inloop_purchase_click_is_stopped()
    await test_inloop_normal_click_not_overblocked()


if __name__ == "__main__":
    asyncio.run(main())
