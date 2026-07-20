"""Prove the unpacked Chrome extension end to end in a real Chrome.

Loads extension/ unpacked into a real Chromium, queues a job on the live
backend, and verifies the extension claims it, opens the page, fills the form,
submits, reads the site's response, and reports 'done' back to the backend.
"""
import json
import time

import httpx
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8090"
EXT = "/home/ubuntu/anticipy_app/extension"


def main():
    # clear old jobs
    for it in httpx.get(f"{BASE}/api/collections/jobs/records", params={"perPage": 200}).json()["items"]:
        httpx.delete(f"{BASE}/api/collections/jobs/records/{it['id']}")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            "/tmp/anticipy_ext_profile",
            headless=True,
            channel="chromium",
            args=[f"--disable-extensions-except={EXT}", f"--load-extension={EXT}"],
        )
        print("1. Chrome launched with Anticipy extension loaded (unpacked)")

        job = httpx.post(f"{BASE}/api/collections/jobs/records", json={
            "goal": "form_submit_demo", "status": "queued",
            "params": json.dumps({}), "device_id": "anticipy-pendant-0001",
        }).json()
        print("2. queued job:", job["goal"], job["id"])

        status = None
        for _ in range(90):
            time.sleep(2)
            rec = httpx.get(f"{BASE}/api/collections/jobs/records/{job['id']}").json()
            status = rec["status"]
            if status in ("done", "failed"):
                break
        print("3. job status:", status)
        print("4. job result:", rec.get("result"))
        shot = "/home/ubuntu/anticipy_app/proof/extension_last.png"
        try:
            pages = ctx.pages
            pages[-1].screenshot(path=shot)
            print("5. screenshot of the tab the extension drove:", shot)
        except Exception as e:
            print("screenshot failed:", e)
        ctx.close()

    assert status == "done" and "logged into a secure area" in rec.get("result", "").lower()
    print("\nEXTENSION PROOF: PASS")


if __name__ == "__main__":
    main()
