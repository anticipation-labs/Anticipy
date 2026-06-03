"""Wall-handler (S6) unit test: a wall PAUSES + texts the user, never fakes done.

Deterministic — no real browser, no real model. Proves the general seam:
classify (captcha/login/block), the human-facing ask (with the no-auto-auth
promise), the paused/needs_human result + resume token, and that the notifier is
actually called. NO site-specific logic.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_handoff.py
"""
import asyncio

from anticipy_engine.agent.handoff import ask_message, classify_wall
from anticipy_engine.agent.webvoyager import WebVoyagerAgent


class FakeGateway:
    async def think(self, prompt, tier=None, caller=None, image=None, json_mode=False, temperature=None):
        return '{"subgoals":["reach the page"]}'  # only the plan call is hit before the wall


class FakeLink:
    def __init__(self, text):
        self._text = text

    async def send_browse(self, job_id, intent, args, timeout):
        return {"output": {"url": "https://example.test/x", "title": "X", "text": self._text, "elements": []},
                "proof": {"screenshot": None}}


async def main():
    # 1) classifier — general, from page text only
    assert classify_wall("Please complete the CAPTCHA to continue") == "captcha"
    assert classify_wall("Sign in to your account") == "login"
    assert classify_wall("A perfectly ordinary page") == "block"

    # 2) the ask carries the hard line (no auto-auth / no captcha-solving / not watching)
    msg = ask_message("login", "https://example.test/login")
    assert "log in" in msg.lower() and "type your password" in msg and "not watching" in msg

    # 3) a captcha page -> PAUSE: needs_human + paused + resume token, and the user is texted
    captured = []

    async def notifier(m):
        captured.append(m)

    agent = WebVoyagerAgent(FakeLink("Please verify you are human"), FakeGateway(), max_steps=4, notifier=notifier)
    res = await agent.run("do the task", "https://example.test/x")
    assert res.get("needs_human") and res.get("paused"), res
    assert res.get("wall_kind") == "captcha" and res.get("resume_token"), res
    assert res.get("answer") == ""  # never a fake answer
    assert captured and "type your password" in captured[0]  # the text actually went out

    # 4) notifier is optional + failures are swallowed (a notify error never crashes a run)
    await WebVoyagerAgent(FakeLink(""), FakeGateway(), notifier=None)._notify("x")

    async def boom(m):
        raise RuntimeError("channel down")

    await WebVoyagerAgent(FakeLink(""), FakeGateway(), notifier=boom)._notify("x")

    print("PASS wall-handler (S6): classify, ask-with-no-auto-auth, pause+text+resume-token, safe notifier")


if __name__ == "__main__":
    asyncio.run(main())
