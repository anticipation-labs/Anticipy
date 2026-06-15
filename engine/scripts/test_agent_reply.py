"""The conversational agent reply: the brain answers the owner, GROUNDED in what the engine did,
SAFE (words only), and ALWAYS answers (fallback on a model error). No real model call (fake gateway).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_agent_reply.py
"""
import asyncio

from anticipy_engine.proactive.agent_reply import agent_reply, summarize_actions, _FALLBACK
from anticipy_engine.core.gateway import SMART


class FakeGateway:
    def __init__(self, out="Done — I'll remind you to call the dentist at 3 today.", raise_=False):
        self.out = out
        self.raise_ = raise_
        self.last = None

    async def think(self, task, tier, caller, **k):
        self.last = {"task": task, "tier": tier, "caller": caller}
        if self.raise_:
            raise RuntimeError("brain down")
        return self.out


async def main():
    # grounding: the prompt carries WHAT THE ENGINE DID + the user's message; smart tier; caller=agent
    gw = FakeGateway()
    res = {"cards": [{"disposition": "do", "title": "remind to call the dentist at 3"}]}
    reply = await agent_reply(gw, "remind me to call the dentist at 3", result=res)
    assert reply == gw.out and reply.strip(), reply
    assert gw.last["tier"] == SMART and gw.last["caller"] == "agent", gw.last
    task = gw.last["task"]
    assert "WHAT HAPPENED" in task and "dentist" in task, task[:200]
    assert "DID (prepared" in task, "reply must be grounded in what the engine actually did"
    assert "NEVER claim" in task, "the prompt must forbid claiming an untaken action"

    # an ASK card is described as WAITING (never claimed done); money is BLOCKED
    assert "WAITING FOR YOUR OK" in summarize_actions({"cards": [{"disposition": "ask", "title": "send Sam the deck"}]})
    assert "BLOCKED" in summarize_actions({"cards": [{"disposition": "blocked", "title": "buy the desk"}]})
    # no cards -> chit-chat / question framing (so the brain answers, doesn't invent a task)
    assert "nothing actionable" in summarize_actions({"cards": []})

    # NEVER leaves the owner unanswered: model error / empty / no-gateway -> safe fallback
    assert await agent_reply(FakeGateway(raise_=True), "hey", result={"cards": []}) == _FALLBACK
    assert await agent_reply(FakeGateway(out=""), "hey", result={"cards": []}) == _FALLBACK
    assert await agent_reply(None, "hey") == _FALLBACK

    print("PASS: agent_reply gives a grounded conversational reply (smart tier, caller=agent), never "
          "claims an untaken action, and always answers (fallback on any model error)")


if __name__ == "__main__":
    asyncio.run(main())
