"""The product voice — Anticipy talks like a human, never like software.

Omar's law: no real person says "Anticipy: got it, dispatching to your engine," and a due
reminder must never read "Reminder: Remind me to ...". This pins the deterministic floor
(robot-word detector + the no-model fallbacks) and proves the model path can never slip back
into robot-speak (a jargon reply is replaced by the clean deterministic nudge).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_voice.py
"""
import asyncio

from anticipy_engine.core.gateway import SMART
from anticipy_engine.core.voice import (
    PRODUCT_VOICE,
    ask_line,
    deterministic_reminder,
    humanize_reminder,
    reads_like_a_robot,
)


class FakeGateway:
    def __init__(self, provider="openrouter", out="It's time to call the dentist — want me to remind you again later?", raise_=False):
        self.provider = provider
        self.out = out
        self.raise_ = raise_
        self.last = None

    async def think(self, task, tier, caller, **k):
        self.last = {"task": task, "tier": tier, "caller": caller}
        if self.raise_:
            raise RuntimeError("brain down")
        return self.out


async def main():
    # robot detector: catches the exact words a real person never uses
    assert reads_like_a_robot("Got it, dispatching to your engine")
    assert reads_like_a_robot("Reminder: call the dentist")
    assert reads_like_a_robot("I ingested that into the pipeline")
    assert not reads_like_a_robot("Hey, quick nudge — call the dentist about your appointment")

    # deterministic nudge strips the redundant "remind me to" and never reads like a robot
    d = deterministic_reminder("remind me to email the accountant about taxes")
    assert "remind me to" not in d.lower() and not d.lower().startswith("reminder:"), d
    assert not reads_like_a_robot(d), d
    assert "email the accountant about taxes" in d.lower(), d
    # other phrasings too
    for raw in ("don't forget to call the roofer back", "I need to pay the babysitter", "note to self: book the dentist"):
        assert not reads_like_a_robot(deterministic_reminder(raw)), raw

    # stub gateway -> NO model call, deterministic fallback
    stub = FakeGateway(provider="stub")
    r = await humanize_reminder(stub, "remind me to call the dentist at 3")
    assert stub.last is None, "stub provider must not call the model"
    assert not reads_like_a_robot(r) and "call the dentist" in r.lower(), r

    # live gateway -> uses the SMART model with the product voice, returns its line
    live = FakeGateway()
    r2 = await humanize_reminder(live, "remind me to call the dentist at 3")
    assert live.last["tier"] == SMART, live.last
    assert PRODUCT_VOICE[:40] in live.last["task"], "the model must be given the product-voice rules"
    assert r2 == live.out

    # live model error -> clean deterministic fallback (owner still gets a human nudge)
    flaky = FakeGateway(raise_=True)
    assert not reads_like_a_robot(await humanize_reminder(flaky, "remind me to stretch"))

    # a model that slips into robot-speak is REJECTED -> deterministic nudge instead
    robotic = FakeGateway(out="Reminder: dispatching your task to the engine now.")
    r3 = await humanize_reminder(robotic, "remind me to stretch")
    assert not reads_like_a_robot(r3), r3
    assert r3 == deterministic_reminder("remind me to stretch")

    # the yes/no ask: human framing, keeps the reply mechanism, drops the robot labels
    a = ask_line("send Sam the deck", "3f2a1b", category="binding_send")
    assert "Anticipy wants to" not in a and "Why it paused" not in a, a
    assert "send sam the deck" in a.lower(), a
    # BOTH reply forms shown so a yes or a no stays unambiguous when several things pend
    assert "YES 3f2a1b" in a and "NO 3f2a1b" in a, a
    assert "sends something to someone else" in a, "the 'why' must be a human line from the category"
    assert not reads_like_a_robot(a.replace("3f2a1b", "")), a  # (the code is not a word)

    # the raw internal reason (robot notes) is NEVER surfaced — category wins, jargon is dropped
    a2 = ask_line("text Priya the deck", "766a2d", category="binding_send",
                  reason="memory low-confidence on recipient -> fail-safe ask")
    assert "low-confidence" not in a2 and "->" not in a2 and "fail-safe" not in a2, a2
    assert "sends something to someone else" in a2, a2

    print("PASS voice: human reminders (no 'Reminder: Remind me to'), human asks (no 'Anticipy wants to'), "
          "robot-speak rejected even from the model — two-year-old-proof")


if __name__ == "__main__":
    asyncio.run(main())
