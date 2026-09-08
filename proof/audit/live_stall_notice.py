"""Live phone-less browser-blocker proof; cleans up its own synthetic account."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlencode

from brain.workflow import Consequence, new_plan, put_in_params
from proof.audit.live_api_release import request
from proof.audit.model_gateway import atomic_json

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://api.anticipy.ai"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    public = ROOT / "work/audit" / (args.label + ".json")
    private = public.with_name(args.label + "-private.json")
    if public.exists() or private.exists():
        raise RuntimeError("Use a fresh label to preserve evidence")
    budget_path = ROOT / "work/audit/overnight-live-browser-budget.json"
    lock = str(budget_path) + ".lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        budget = json.loads(budget_path.read_text())
        if budget["reserved_upper_bound_usd"] + 0.5 > budget["limit_usd"]:
            raise RuntimeError("Native audit ceiling reached")
        budget["reserved_upper_bound_usd"] += 0.5
        budget["calls"].append({"label": args.label,
            "at": datetime.now(timezone.utc).isoformat(), "reserved_usd": 0.5,
            "purpose": "one live worker blocker notice, no phone"})
        atomic_json(budget_path, budget)
    finally:
        os.close(fd)
        os.unlink(lock)
    service = json.loads((ROOT / "work/audit/secrets.json").read_text())["ANTICIPY_SERVICE_TOKEN"]
    fixture = {"created_by": "anticipy-browser-audit", "base": BASE,
               "email": "stall-" + secrets.token_hex(12) + "@anticipy-test.invalid",
               "password": secrets.token_urlsafe(32)}
    atomic_json(private, fixture)
    evidence = {"scope": "live worker persists an unavailable-browser notice for a fresh queued task",
                "phone": "absent", "browser": "unpaired", "messages_sent": 0}
    try:
        status, owner, _ = request(BASE, "POST", "/api/collections/owners/records", {
            "email": fixture["email"], "password": fixture["password"],
            "passwordConfirm": fixture["password"]})
        assert status == 200 and owner.get("id"), f"signup HTTP {status}"
        fixture["ownerId"] = owner["id"]
        atomic_json(private, fixture)
        status, auth, _ = request(BASE, "POST", "/api/collections/owners/auth-with-password", {
            "identity": fixture["email"], "password": fixture["password"]})
        assert status == 200 and auth.get("token"), f"login HTTP {status}"
        token = fixture["ownerToken"] = auth["token"]
        atomic_json(private, fixture)
        status, _, _ = request(BASE, "POST", "/me/profile/upsert", {
            "name": "Casey Blocker Fixture", "timezone": "America/Vancouver"}, token)
        assert status == 200, f"profile HTTP {status}"
        goal = "Open the appointment page in my browser so I can review it. Do not submit or book."
        status, ev, _ = request(BASE, "POST", "/api/collections/events/records", {
            "owner_ref": owner["id"], "kind": "app_reply", "source": "typed",
            "device_id": "isolated-stall-audit", "text": goal, "decision": "ignore"}, token)
        assert status == 200 and ev.get("id"), f"event HTTP {status}"
        plan = new_plan(owner_ref=owner["id"], lineage_key="audit-" + secrets.token_hex(10),
            goal=goal, consequence=Consequence.READ_ONLY, source_event_id=ev["id"], authority_text=goal)
        params = put_in_params({"task": goal, "source": goal,
                               "start_url": "https://appointment.audit.invalid/"}, plan)
        status, job, _ = request(BASE, "POST", "/api/collections/jobs/records", {
            "owner_ref": owner["id"], "owner": owner["id"], "goal": goal,
            "params": json.dumps(params), "device_id": "isolated-stall-audit",
            "lane": "", **plan.job_fields()},
            extra_headers={"X-Anticipy-Token": service, "X-Anticipy-Worker": "1"})
        assert status == 200 and job.get("id"), f"job HTTP {status}"
        fixture["jobId"] = job["id"]
        atomic_json(private, fixture)
        started = time.monotonic()
        query = urlencode({"filter": f'owner_ref="{owner["id"]}" && external_event_id="job-stalled:{job["id"]}:queued"'})
        notices = []
        while time.monotonic() - started < 120:
            status, body, _ = request(BASE, "GET", "/api/collections/events/records?" + query, token=token)
            assert status == 200, f"notice read HTTP {status}"
            notices = body.get("items", [])
            if notices:
                break
            time.sleep(3)
        assert len(notices) == 1, "The actual worker did not publish one app notice"
        status, saved, _ = request(BASE, "GET", "/api/collections/jobs/records/" + job["id"], token=token)
        assert status == 200 and saved["status"] == "queued", "Notice must not execute or complete the task"
        evidence.update(passed=True, elapsed_seconds=round(time.monotonic() - started, 2),
                        notice=notices[0]["text"], notice_count=1, job_status=saved["status"])
    except Exception as error:
        evidence.update(passed=False, error=str(error))
        raise
    finally:
        if fixture.get("ownerToken"):
            status, body, _ = request(BASE, "POST", "/me/delete", {"confirm": "delete"}, fixture["ownerToken"])
            evidence["cleaned_up"] = status == 200 and body.get("account_deleted") is True
            fixture["accountDeleted"] = evidence["cleaned_up"]
            atomic_json(private, fixture)
        atomic_json(public, evidence)
        print(json.dumps(evidence))


if __name__ == "__main__":
    main()
