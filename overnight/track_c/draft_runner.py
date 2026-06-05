"""Track C — Gmail DRAFT runner (the honest auth gate).

Tonight this REFUSES to run (the gmail.compose scope is `pending`) and prints the one-tap connect
URL — it cannot and will not fake a draft. The moment the scope is granted, re-running this
self-proves the judge and runs fresh draft laps proven against the real mailbox, exactly like
Track A. Mirrors Track A: fresh request -> worker -> SEPARATE judge confirms in reality.

Run: PYTHONPATH=engine:overnight/track_c python overnight/track_c/draft_runner.py [n]
"""
from __future__ import annotations

import asyncio
import random
import sys

from anticipy_engine.core.env import load_local_env

load_local_env()

import os

import draft_judge as J
import draft_worker as W
from arcadepy import Arcade

_TOPICS = ["thank the team for shipping on time", "ask Dana to move our sync to Thursday",
           "follow up on the unpaid invoice", "decline the Friday meeting politely",
           "check in with a mentor", "ask the landlord about the parking spot",
           "confirm the dinner reservation details", "intro two colleagues"]


def _auth_status() -> tuple[str, str]:
    c = Arcade(api_key=os.environ["ARCADE_API_KEY"])
    a = c.tools.authorize(tool_name="Gmail.WriteDraftEmail", user_id=os.environ["ARCADE_USER_ID"])
    return getattr(a, "status", None), getattr(a, "url", None)


async def main(n: int):
    status, url = _auth_status()
    if status != "completed":
        print("=== Track C Gmail draft: BLOCKED (honest gate) ===")
        print(f"  Gmail.WriteDraftEmail status = {status!r}  -> cannot create real drafts yet.")
        print("  This will NOT fake anything. Tap to grant the draft scope, then re-run me:")
        print(f"  {url}")
        return
    print("=== Track C Gmail draft: scope granted — self-proving the judge ===")
    if not J.self_prove():
        print("  judge not trustworthy -> refusing to run."); return
    rng = random.Random()
    print(f"\n=== {n} fresh draft laps (proven against the real mailbox) ===")
    for i in range(n):
        ask = f"Draft an email to {rng.choice(_TOPICS)}."
        claim = await W.do(ask)
        verdict = J.confirm(claim)
        print(f"  [{'PASS' if verdict['pass'] else 'FAIL'}] {ask[:50]:<50} id={claim.get('draft_id') or '-'}  {verdict['reason']}")


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 5))
