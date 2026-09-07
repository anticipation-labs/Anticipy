"""Prepare a disposable local account for real simulator interaction. No live effects."""
import json
import plistlib
import secrets
import subprocess
from pathlib import Path

from live_api_release import request

BASE = "http://localhost:8787"
STATE = Path("work/audit/overnight-visual-account.json")
APP = Path("work/audit/quiet-build/Build/Products/Debug-iphonesimulator/Anticipy.app")


def main():
    if STATE.exists():
        account = json.loads(STATE.read_text())
    else:
        email = "ui-" + secrets.token_hex(8) + "@anticipy-test.invalid"
        password = secrets.token_urlsafe(24)
        status, owner, _ = request(BASE, "POST", "/api/collections/owners/records", {
            "email": email, "password": password, "passwordConfirm": password})
        assert status == 200, status
        status, auth, _ = request(BASE, "POST", "/api/collections/owners/auth-with-password", {
            "identity": email, "password": password})
        assert status == 200, status
        account = {"id": owner["id"], "token": auth["token"], "email": email, "password": password}
        STATE.write_text(json.dumps(account))
        STATE.chmod(0o600)
    token, owner = account["token"], account["id"]
    request(BASE, "POST", "/me/profile/upsert", {"name": "Casey Test", "timezone": "America/Vancouver"}, token)
    if "job_id" not in account:
        status, event, _ = request(BASE, "POST", "/api/collections/events/records", {
            "owner_ref": owner, "device_id": "overnight-ui-fixture", "kind": "transcript", "source": "phone_mic",
            "text": "Could you prepare a calendar event for the family appointment?",
            "goal": "Prepare the family appointment", "decision": "act"}, extra_headers={"X-Anticipy-Token": "overnight-local-service-only"})
        assert status == 200, (status, event)
        status, job, _ = request(BASE, "POST", "/api/collections/jobs/records", {
            "owner_ref": owner, "device_id": "overnight-ui-fixture", "goal": "Prepare the family appointment", "status": "awaiting_confirm",
            "workflow_state": "draft", "lane": "research", "result": "What time does it end?",
            "params": json.dumps({"source_event_ids": [event["id"]]})}, extra_headers={"X-Anticipy-Token": "overnight-local-service-only"})
        assert status == 200, (status, job)
        account["job_id"] = job["id"]
        STATE.write_text(json.dumps(account))
        for index in range(3):
            status, _, _ = request(BASE, "POST", "/api/collections/events/records", {
                "owner_ref": owner, "device_id": "overnight-ui-fixture", "kind": "anticipy_says", "decision": "done",
                "text": ("A detailed synthetic result with several steps and sources. " * 35)
                + f" End of result {index}."}, extra_headers={"X-Anticipy-Token": "overnight-local-service-only"})
            assert status == 200, status
    bundle = plistlib.loads((APP / "Info.plist").read_bytes())["CFBundleIdentifier"]
    subprocess.run(["xcrun", "simctl", "terminate", "booted", bundle], capture_output=True)
    for key, value in {"backendURL": BASE, "authToken": token, "accountID": owner,
                       "keepListening": False}.items():
        args = ["xcrun", "simctl", "spawn", "booted", "defaults", "write", bundle, key]
        args += ["-bool", "false"] if value is False else ["-string", value]
        subprocess.run(args, check=True, capture_output=True)
    subprocess.run(["xcrun", "simctl", "install", "booted", str(APP)], check=True, capture_output=True)
    subprocess.run(["xcrun", "simctl", "launch", "booted", bundle], check=True, capture_output=True)
    print("Disposable local account and long-response fixture ready in Simulator.")


if __name__ == "__main__":
    main()
