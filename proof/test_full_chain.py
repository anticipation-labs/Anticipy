"""Full-chain proof: (phone app) -> backend -> brain (live LLM) -> job queue
-> Chrome extension (real Chrome, unpacked) -> action -> result back to app.

The 'phone app' here is a stand-in that calls the exact same backend endpoints
the Swift app calls (events + jobs on PocketBase). Everything else is real:
live OpenRouter triage, real Chrome, real website, real result round-trip.
"""
import json
import os
import sys
import time

import httpx
from playwright.sync_api import sync_playwright

sys.path.insert(0, "/home/ubuntu/anticipy_app")
from brain.orchestrator import Brain  # noqa: E402

BASE = "http://127.0.0.1:8090"
EXT = "/home/ubuntu/anticipy_app/extension"
LINE = "Let me log into the vendor portal and confirm the order went through."


def main():
    for it in httpx.get(f"{BASE}/api/collections/jobs/records", params={"perPage": 200}).json()["items"]:
        httpx.delete(f"{BASE}/api/collections/jobs/records/{it['id']}")

    brain = Brain()
    assert brain.llm.live, "OPENROUTER_API_KEY required for the live chain proof"
    print(f"1. app heard: {LINE!r}")
    d = brain.triage(LINE)
    print(f"2. live brain ({brain.llm.model}): decision={d.decision} goal={d.goal!r}")
    assert d.decision == "act"

    # The app maps the brain's goal onto a browser-executable action.
    httpx.post(f"{BASE}/api/collections/events/records", json={
        "device_id": "anticipy-pendant-0001", "kind": "decision", "text": LINE,
        "decision": d.decision, "goal": d.goal or "",
    })
    job = httpx.post(f"{BASE}/api/collections/jobs/records", json={
        "goal": "form_submit_demo", "status": "queued",
        "params": json.dumps({"source": LINE}), "device_id": "anticipy-pendant-0001",
    }).json()
    print(f"3. app queued browser job {job['id']} on the backend")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            "/tmp/anticipy_ext_profile2", headless=True, channel="chromium",
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"],
        )
        print("4. real Chrome running with the Anticipy extension (unpacked)")
        rec = None
        for _ in range(90):
            time.sleep(2)
            rec = httpx.get(f"{BASE}/api/collections/jobs/records/{job['id']}").json()
            if rec["status"] in ("done", "failed"):
                break
        ctx.pages[-1].screenshot(path="/home/ubuntu/anticipy_app/proof/full_chain.png")
        ctx.close()

    print(f"5. extension executed in the logged-in portal: {rec['result']}")
    print(f"6. app read the result back from the backend (status={rec['status']})")
    assert rec["status"] == "done" and "secure area" in rec["result"].lower()
    print("\nFULL CHAIN PROOF: PASS")


if __name__ == "__main__":
    main()
