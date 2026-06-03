"""LIVE proof (section 8): a REAL Gmail send to a TEST address through the real
API hand. The single live action this chunk performs. Run:

    PYTHONPATH=engine engine/.venv/bin/python engine/scripts/live_gmail_send.py [test@addr]

If Gmail isn't connected yet, it prints the connect URL (approve once, re-run).
Idempotent: re-running with the same args won't send twice (proof is cached).
"""
import asyncio
import os
import sys

from anticipy_engine.core.env import load_local_env

load_local_env()

from anticipy_engine.core.envelopes import Job, JobStatus, Risk
from anticipy_engine.hands.api_hand import ApiHand, MODE_LIVE


async def main():
    to = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("TEST_USER_EMAIL", "omar@anticipy.ai")
    # Arcade user_id must match the signed-in Arcade.dev account
    user_id = os.environ.get("ARCADE_USER_ID") or os.environ.get("ADMIN_EMAIL", "omar@anticipy.ai")
    hand = ApiHand(user_id=user_id, mode=MODE_LIVE)
    job = Job(intent="send_email", risk=Risk.needs_confirm, goal_id="live-proof",
              args={"approved": True, "recipient": to,
                    "subject": "Anticipy — live hand proof",
                    "body": "This is the single LIVE proof send from the API hand."})
    r = await hand.handle(job)
    if r.status == JobStatus.needs_human and (r.output or {}).get("connect_url"):
        print("CONNECT GMAIL FIRST — open this URL, approve, then re-run:")
        print(r.output["connect_url"])
        return
    print("status:", r.status.value)
    print("proof:", r.proof)
    if r.status == JobStatus.success and r.proof and r.proof.get("id"):
        print("LIVE PASS: real Gmail message id:", r.proof["id"])
    else:
        print("LIVE not complete:", r.error or r.output)


if __name__ == "__main__":
    asyncio.run(main())
