"""Live API release proof. Only creates and removes its own phone-less test accounts.

No model calls, messages, real contacts, or secret-bearing output. The optional
Cloudflare check compares the URL's running version with its active deployment.
"""
import argparse
import json
import os
import secrets
import time
import urllib.error
import urllib.request


def request(base, method, path, data=None, token=None, extra_headers=None):
    headers = {"Content-Type": "application/json", "User-Agent": "Anticipy-release-proof/1"}
    if token:
        headers["Authorization"] = "Bearer " + token
    headers.update(extra_headers or {})
    req = urllib.request.Request(base + path, method=method, headers=headers,
                                 data=None if data is None else json.dumps(data).encode())
    try:
        response = urllib.request.urlopen(req, timeout=40)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read()
        try:
            body = json.loads(raw) if raw else {}
        except ValueError:
            body = {}
        return response.status, body, response.headers


def prove(base, verify_deployment=False):
    checks = []
    accounts = []

    def check(condition, name):
        if not condition:
            raise RuntimeError(name + " FAILED")
        checks.append(name)
        print(name + ": PASS", flush=True)

    if verify_deployment:
        status, _, _ = request(base, "POST", "/sms/sendblue", {})
        check(status == 403, "SendBlue webhook is configured and rejects unsigned input")
        status, _, _ = request(base, "POST", "/sms/inbound", {})
        check(status == 410, "Retired texting endpoint cannot accept input")
    status, body, headers = request(base, "GET", "/api/health")
    check(status == 200 and body.get("code") == 200, "API liveness")
    if verify_deployment:
        account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
        status, body, _ = request("https://api.cloudflare.com/client/v4", "GET",
            f"/accounts/{account}/workers/scripts/anticipy-api/deployments",
            token=os.environ["CLOUDFLARE_API_TOKEN"])
        check(status == 200 and body.get("success"), "Cloudflare deployment lookup")
        deployments = body["result"]["deployments"]
        latest = max(deployments, key=lambda d: d["created_on"])
        versions = {v["version_id"] for v in latest["versions"] if v["percentage"] == 100}
        # A rollout may need a few seconds to propagate to the custom domain.
        for _ in range(12):
            if headers.get("x-anticipy-version") in versions:
                break
            time.sleep(5)
            status, _, headers = request(base, "GET", "/api/health")
        check(status == 200 and headers.get("x-anticipy-version") in versions,
              "Live URL serves the active deployment version")
        check(headers.get("x-anticipy-revision") == os.environ["GITHUB_SHA"],
              "Live URL serves this workflow commit")
        print(json.dumps({"active_version": headers.get("x-anticipy-version"),
                          "source_commit": headers.get("x-anticipy-revision")}))

    try:
        for _ in range(2):
            email = "release-" + secrets.token_hex(12) + "@anticipy-test.invalid"
            password = secrets.token_urlsafe(32)
            status, owner, _ = request(base, "POST", "/api/collections/owners/records", {
                "email": email, "password": password, "passwordConfirm": password})
            check(status == 200 and bool(owner.get("id")), "Server-issued signup")
            status, auth, _ = request(base, "POST", "/api/collections/owners/auth-with-password", {
                "identity": email, "password": password})
            check(status == 200 and bool(auth.get("token")), "Password login")
            accounts.append({"id": owner["id"], "token": auth["token"], "email": email,
                             "password": password})
        owner, stranger = accounts
        status, _, _ = request(base, "POST", "/me/profile/upsert", {
            "name": "Release verification", "timezone": "America/Vancouver"}, owner["token"])
        check(status == 200, "Profile saved through the phone route")
        status, policy, _ = request(base, "GET", "/me/notification-policy", token=owner["token"])
        check(status == 200 and policy.get("timeZone") == "America/Vancouver"
              and policy.get("startHour") == 22 and policy.get("endHour") == 8
              and isinstance(policy.get("quietHoursActive"), bool)
              and 0 < policy.get("expiresAt", 0) - policy.get("observedAt", 0) <= 60,
              "Phone receives current account-scoped quiet-hours policy")
        from datetime import datetime
        from zoneinfo import ZoneInfo
        observed_hour = datetime.fromtimestamp(policy["observedAt"], ZoneInfo(policy["timeZone"])).hour
        check(policy["quietHoursActive"] == (observed_hour >= 22 or observed_hour < 8),
              "Live quiet-hours answer agrees with the account clock")
        status, _, _ = request(base, "GET", "/me/notification-policy")
        check(status == 401, "Quiet-hours profile information requires sign-in")
        status, event, _ = request(base, "POST", "/api/collections/events/records", {
            "owner_ref": owner["id"], "kind": "profile", "source": "import",
            "text": "Synthetic API release check", "device_id": "release-proof"}, owner["token"])
        check(status == 200 and bool(event.get("id")), "Owned event persisted")
        status, _, _ = request(base, "POST", "/me/context-request", {
            "eventID": event["id"], "availableSources": ["contacts"]})
        check(status == 401, "Context requests require sign-in")
        status, _, _ = request(base, "POST", "/me/context-request", {
            "eventID": event["id"], "availableSources": ["contacts"]}, stranger["token"])
        check(status == 404, "Context requests cannot read another owner's conversation")
        event_path = "/api/collections/events/records/" + event["id"]
        status, _, _ = request(base, "GET", event_path, token=stranger["token"])
        check(status in (403, 404), "Other account cannot read the event")
        status, _, _ = request(base, "PATCH", event_path, {"text": "unauthorized"}, stranger["token"])
        check(status in (403, 404), "Other account cannot change the event")
        # This owner is excluded from the brain fleet. A research-lane fixture
        # has no browser claimant or provider effect, even for the success case.
        status, task, _ = request(base, "POST", "/api/collections/jobs/records", {
            "owner_ref": owner["id"], "goal": "Synthetic approval race check",
            "device_id": "release-proof", "status": "awaiting_confirm", "lane": "research",
            "params": json.dumps({"lane": "research", "source": "isolated release fixture"}),
        }, owner["token"])
        check(status == 200 and bool(task.get("id")), "Isolated held task created")
        task_path = "/api/collections/jobs/records/" + task["id"]
        status, _, task_headers = request(base, "GET", task_path, token=owner["token"])
        etag = task_headers.get("ETag")
        check(status == 200 and bool(etag), "Live API supplies task approval precondition")
        status, _, _ = request(base, "PATCH", task_path, {"goal": "Changed synthetic scope"}, owner["token"])
        check(status == 200, "Concurrent task amendment saved")
        status, _, _ = request(base, "PATCH", task_path, {"status": "queued"}, owner["token"], {"If-Match": etag})
        check(status == 412, "Stale approval refused by live database")
        status, current, task_headers = request(base, "GET", task_path, token=owner["token"])
        check(status == 200 and current.get("status") == "awaiting_confirm"
              and current.get("goal") == "Changed synthetic scope", "Refused approval preserves held corrected task")
        current_etag = task_headers.get("ETag")
        status, _, _ = request(base, "PATCH", task_path, {"status": "queued"}, owner["token"], {"If-Match": current_etag})
        check(status == 200, "Fresh approval precondition accepted")
        status, _, _ = request(base, "PATCH", task_path, {"status": "queued"}, owner["token"], {"If-Match": current_etag})
        check(status == 412, "Repeated approval cannot win twice")
        status, _, _ = request(base, "DELETE", "/api/collections/owners/records/" + owner["id"], token=owner["token"])
        check(status == 405, "Generic deletion cannot bypass account cleanup")
        status, _, _ = request(base, "POST", "/me/delete", {"confirm": "delete"}, "a.b.%%%%")
        check(status == 401, "Malformed token is refused without a server error")
        status, deleted, _ = request(base, "POST", "/me/delete", {"confirm": "delete"}, owner["token"])
        check(status == 200 and deleted.get("account_deleted") is True, "Account cleanup completed")
        status, _, _ = request(base, "POST", "/api/collections/owners/auth-with-password", {
            "identity": owner["email"], "password": owner["password"]})
        check(status == 400, "Deleted account can no longer log in")
        status, _, _ = request(base, "GET", event_path, token=owner["token"])
        check(status in (401, 403, 404), "Old token cannot read deleted data")
        accounts.remove(owner)
        if os.environ.get("ANTICIPY_INTERNAL_KEY"):
            # This .invalid owner is excluded from the production brain fleet.
            # A fictional profile number is identity data only; no text is sent.
            status, _, _ = request(base, "POST", "/me/profile/upsert", {
                "name": "Operator erasure fixture", "email": stranger["email"],
                "phone": "+12025550199", "timezone": "America/Vancouver"}, stranger["token"])
            check(status == 200, "Operator fixture profile saved")
            payload = {"owner_ref": stranger["id"], "email": stranger["email"],
                       "phone": "+12025550199", "confirm": "DELETE PRODUCT ACCOUNT"}
            header = {"X-Internal-Key": os.environ["ANTICIPY_INTERNAL_KEY"]}
            status, _, _ = request(base, "POST", "/admin/account-reset", payload)
            check(status == 401, "Operator erasure refuses an unauthenticated request")
            status, _, _ = request(base, "POST", "/admin/account-reset",
                                   payload | {"phone": "+12025550198"}, extra_headers=header)
            check(status == 409, "Operator erasure refuses mismatched identity")
            status, body, _ = request(base, "POST", "/admin/account-reset", payload, extra_headers=header)
            check(status == 200 and body.get("account_deleted") is True,
                  "Verified operator erasure completed through the same cleanup path")
            status, _, _ = request(base, "POST", "/api/collections/owners/auth-with-password", {
                "identity": stranger["email"], "password": stranger["password"]})
            check(status == 400, "Operator-erased fixture cannot log in")
            accounts.remove(stranger)
    finally:
        failures = 0
        for owner in accounts:
            status, body, _ = request(base, "POST", "/me/delete", {"confirm": "delete"}, owner["token"])
            failures += status not in (200, 401)
        if failures:
            raise RuntimeError(f"Cleanup failed for {failures} synthetic account(s); investigate before release")
    print(json.dumps({"scope": "live API account and ownership behavior; no provider effects", "checks": len(checks), "passed": True}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--verify-deployment", action="store_true")
    args = parser.parse_args()
    prove(args.base.rstrip("/"), args.verify_deployment)
