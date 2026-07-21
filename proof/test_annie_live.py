"""Live spine: Annie -> real PocketBase job queue -> confirm gate -> loop closed.

Runs against the actual backend at 127.0.0.1:8090 (no mocks). The extension's
role (claiming the job and reporting done) is played by direct API calls so
the proof runs headless; the extension side was already proven live in Chrome.
"""
import sys, time
sys.path.insert(0, "/home/ubuntu/anticipy_app")

import requests
from brain.annie import Annie

BASE = "http://127.0.0.1:8090"


def main():
    assert requests.get(f"{BASE}/api/health", timeout=5).ok
    a = Annie(backend_url=BASE)

    # 1. Annie hears a commitment -> job is created HELD at awaiting_confirm.
    out = a.hear("I'll send Sarah the pitch deck right after this call.")
    assert out["decision"].decision == "act"
    job_id = a.loops[0].job_id
    assert job_id, "job was not created on the real backend"
    job = requests.get(f"{BASE}/api/collections/jobs/records/{job_id}").json()
    assert job["status"] == "awaiting_confirm", job["status"]
    print(f"PASS held for confirmation: job {job_id} awaiting_confirm")
    print(f"     Annie says: {out['annie_says']}")

    # 2. User says yes (same PATCH the app's "Send it" button makes).
    requests.patch(f"{BASE}/api/collections/jobs/records/{job_id}",
                   json={"status": "queued"})
    job = requests.get(f"{BASE}/api/collections/jobs/records/{job_id}").json()
    assert job["status"] == "queued"
    print("PASS in-app confirm released the job (awaiting_confirm -> queued)")

    # 3. The browser agent completes it (extension proven separately).
    requests.patch(f"{BASE}/api/collections/jobs/records/{job_id}",
                   json={"status": "done", "result": "draft sent to Sarah"})

    # 4. Annie reviews her loops: closes the loop AND resolves the memory.
    loops = a.review_loops()
    assert loops[0]["status"] == "done", loops
    assert a.memory.open_loops() == [], "memory commitment should be resolved"
    print("PASS loop closed and memory commitment resolved")

    # 5. Briefing reflects the day.
    print(f"     Briefing: {a.briefing()}")
    print("annie live spine: all steps passed")


if __name__ == "__main__":
    main()
