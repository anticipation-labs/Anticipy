"""Piece 3 (unit) test: the browser hand edge-cases against a FakeLink.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_browser_hand.py
"""
import asyncio

from anticipy_engine.core.envelopes import Job, JobStatus
from anticipy_engine.hands.browser_hand import BrowserHand


class FakeLink:
    def __init__(self, connected=True, behavior="success"):
        self.connected = connected
        self.behavior = behavior

    async def send_browse(self, job_id, intent, args, timeout):
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
    assert set(BrowserHand(FakeLink()).handles()) == {"browse_task", "read_page"}

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

    print("PASS piece 3 (unit): browser hand — success/proof, not-connected, timeout, disconnect, login-wall, no-proof")


if __name__ == "__main__":
    asyncio.run(main())
