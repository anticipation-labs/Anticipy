"""Piece 3 (unit) test: the browser hand edge-cases against a FakeLink.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_browser_hand.py
"""
import asyncio

from anticipy_engine.core.envelopes import Job, JobStatus
from anticipy_engine.agent.webvoyager import AGENT_MAX_TOKENS
from anticipy_engine.hands.browser_hand import BrowserHand, MODE_MOCK


class FakeLink:
    def __init__(self, connected=True, behavior="success"):
        self.connected = connected
        self.behavior = behavior
        self.last_args = None

    async def send_browse(self, job_id, intent, args, timeout):
        self.last_args = args
        if self.behavior == "timeout":
            raise asyncio.TimeoutError()
        if self.behavior == "disconnect":
            raise ConnectionError()
        if self.behavior == "login_wall":
            return {"type": "result", "job_id": job_id, "status": "needs_human",
                    "output": {"reason": "please sign in"}, "proof": None}
        if self.behavior == "no_proof":
            return {"type": "result", "job_id": job_id, "status": "success", "proof": {}, "output": {}}
        if self.behavior == "fail":
            return {"type": "result", "job_id": job_id, "status": "failed", "output": {"reason": "nav error"}}
        return {"type": "result", "job_id": job_id, "status": "success",
                "proof": {"screenshot": "data:image/png;base64,xx", "id": "page-1"},
                "output": {"title": "Example"}}


async def main():
    assert AGENT_MAX_TOKENS >= 64, "browser planner JSON replies need room to parse"
    # browse_task/read_page are the read arm; prepare_form is the safe write arm
    # (fill-to-submit-screen then hand off, covered by test_form_prepare.py).
    assert {"browse_task", "read_page"} <= set(BrowserHand(FakeLink()).handles())
    assert "prepare_form" in BrowserHand(FakeLink()).handles()

    r = await BrowserHand(FakeLink(behavior="success")).handle(Job(intent="browse_task", args={"task": "x"}))
    assert r.status == JobStatus.success and r.proof.get("screenshot")

    r = await BrowserHand(FakeLink(connected=False)).handle(Job(intent="browse_task"))
    assert r.status == JobStatus.needs_human and "isn't connected" in r.output["reason"]

    r = await BrowserHand(FakeLink(behavior="timeout")).handle(Job(intent="browse_task"))
    assert r.status == JobStatus.failed and "timed out" in r.error

    r = await BrowserHand(FakeLink(behavior="disconnect")).handle(Job(intent="browse_task"))
    assert r.status == JobStatus.needs_human

    r = await BrowserHand(FakeLink(behavior="login_wall")).handle(Job(intent="browse_task"))
    assert r.status == JobStatus.needs_human and "sign in" in str(r.output)

    r = await BrowserHand(FakeLink(behavior="no_proof")).handle(Job(intent="browse_task"))
    assert r.status == JobStatus.failed  # success without a screenshot is NOT done

    # search-fallback: URL-less read/info tasks may become real search navigation.
    link = FakeLink(behavior="success")
    await BrowserHand(link).handle(Job(intent="browse_task", args={"task": "current USD to EUR exchange rate"}))
    assert link.last_args.get("url", "").startswith("https://duckduckgo.com/?q="), link.last_args
    assert "exchange" in link.last_args["url"]
    # action-shaped tasks must not dump the whole instruction into search. The
    # planner/memory layer must resolve a real site first.
    link_action = FakeLink(behavior="success")
    r = await BrowserHand(link_action).handle(Job(
        intent="browse_task",
        args={"task": "grab that thing I looked at earlier and add it to the cart"},
    ))
    assert r.status == JobStatus.failed and "resolved real site" in r.error, r
    assert link_action.last_args is None, link_action.last_args
    # an explicit URL is left untouched (no clobber)
    link2 = FakeLink(behavior="success")
    await BrowserHand(link2).handle(Job(intent="browse_task", args={"url": "https://example.com", "task": "read it"}))
    assert link2.last_args["url"] == "https://example.com", link2.last_args
    # a task that already contains a URL is left for the extension to extract
    link3 = FakeLink(behavior="success")
    await BrowserHand(link3).handle(Job(intent="browse_task", args={"task": "open https://anticipy.ai now"}))
    assert "url" not in link3.last_args, link3.last_args

    # In live mode, a memory-resolved browser ACTION still needs the browser
    # planner. A read-only observe proof is not proof that a cart/action happened.
    live_no_planner = FakeLink(behavior="success")
    r = await BrowserHand(live_no_planner).handle(Job(intent="browse_task", args={
        "task": "On https://store.test, find wide shoes and add to the cart. Do not checkout.",
        "url": "https://store.test",
        "resolved_from_memory": True,
    }))
    assert r.status == JobStatus.needs_human and "live browser planner" in r.output["reason"], r
    assert live_no_planner.last_args is None, "must not fake-complete an action through observe"

    # ---- MOCK mode (ANTICIPY_HANDS_MODE=mock via ControlCore; default stays LIVE) ----
    # navigable job -> loudly-labeled mock artifact, the link NEVER touched
    mock_link = FakeLink(connected=False)
    hand = BrowserHand(mock_link, mode=MODE_MOCK)
    r = await hand.handle(Job(intent="browse_task", args={"task": "open the page"}))
    assert r.status == JobStatus.success, r
    assert r.proof["mock"] is True and r.proof["id"].startswith("mock-"), r.proof
    assert r.proof.get("screenshot") and r.proof.get("url"), r.proof
    assert mock_link.last_args is None, "mock mode must never touch the browser link"
    # the live refusal still rules: an action-shaped task with no resolved real
    # site FAILS exactly like live — mock must not complete what live refuses
    r = await hand.handle(Job(
        intent="browse_task",
        args={"task": "get the ones I picked out, the wide ones, put them in the cart"},
    ))
    assert r.status == JobStatus.failed and "resolved real site" in r.error, r
    # a memory-resolved cart job (site + item from the planner pre-pass) succeeds
    r = await hand.handle(Job(intent="browse_task", args={
        "task": "On https://store.test, find wide shoes and add to the cart. Do not checkout.",
        "url": "https://store.test", "resolved_from_memory": True}))
    assert r.status == JobStatus.success and r.proof["url"] == "https://store.test", r
    # nothing to navigate to -> failed, never a proof-carrying success
    r = await hand.handle(Job(intent="read_page", args={}))
    assert r.status == JobStatus.failed and not r.proof, r
    # default construction is LIVE: not-connected still hands back to the human
    r = await BrowserHand(FakeLink(connected=False)).handle(Job(intent="browse_task", args={"task": "open the page"}))
    assert r.status == JobStatus.needs_human, r

    print("PASS piece 3 (unit): browser hand — success/proof, not-connected, timeout, disconnect, "
          "login-wall, no-proof, search-fallback for info, no search-dump for actions, explicit url "
          "preserved, mock tier (labeled artifact, live refusals intact, link untouched, default live)")


if __name__ == "__main__":
    asyncio.run(main())
