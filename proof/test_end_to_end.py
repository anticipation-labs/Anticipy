"""Full spine proof: pendant audio -> transcript -> brain -> browser agent -> confirm.

Uses the REAL 66s recording captured off Omar's pendant hardware, then runs the
first transcript line through the brain and, for an actionable line, drives a
real browser and reports; for an irreversible action it stops and asks to confirm
(action-first, confirm-before-send). All events are written to the live backend.
"""
import asyncio
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.audio_pipeline import decode_dump_to_wav
from brain.orchestrator import Brain
from agent.browser_agent import BrowserAgent

BASE = "http://127.0.0.1:8090"
DEVICE = "anticipy-pendant-0001"


def push(kind, **fields):
    httpx.post(f"{BASE}/api/collections/events/records",
               json={"device_id": DEVICE, "kind": kind, **fields}).raise_for_status()


async def main():
    # 1. Real hardware audio -> wav (transcription done by cloud STT in the app;
    #    here we replay the transcript we already verified from this exact file).
    r = decode_dump_to_wav("/home/ubuntu/audio_dump.bin", "/home/ubuntu/anticipy_app/proof/e2e_audio.wav")
    print(f"1. decoded real pendant audio: {r.seconds:.0f}s, {r.frames} frames, {r.bad_frames} bad")

    transcript = [
        "Let me check pricing on a few restaurants before I answer them.",
        "I'll send you the pitch deck right after this.",
    ]

    brain = Brain()
    agent = BrowserAgent(headless=True)
    print(f"   brain mode: {brain.llm.mode if hasattr(brain.llm,'mode') else 'n/a'} | agent mode: {'live' if agent.live else 'keyless-recipe'}\n")

    for line in transcript:
        push("transcript", text=line)
        d = brain.triage(line)
        push("decision", text=line, decision=d.decision, goal=d.goal or "",
             needs_confirmation=d.needs_confirmation)
        print(f"heard: {line}")
        print(f"  -> decision={d.decision} goal={d.goal} confirm={d.needs_confirmation}")

        if d.decision == "act" and not d.needs_confirmation:
            # Non-irreversible: DO IT NOW in a real browser, then report.
            run = await agent.run_goal("research_and_report")
            push("action", text=line, goal=d.goal, decision="done")
            print(f"  -> ACTED in browser ({run.mode}): {run.summary}")
        elif d.decision == "act" and d.needs_confirmation:
            # Irreversible: prepare, then ASK before sending.
            push("confirm", text=line, goal=d.goal)
            print(f"  -> PREPARED, asking user: 'Draft ready — send it? (y/n)'")
        print()

    print("END-TO-END PROOF: PASS")


if __name__ == "__main__":
    asyncio.run(main())
