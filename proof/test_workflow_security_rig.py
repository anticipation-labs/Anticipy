#!/usr/bin/env python3
"""Black-box proof for owner isolation and the durable workflow law.

Run against a disposable PocketBase instance with all production migrations
and hooks loaded.  No mocks and no model calls are involved.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import sys
import time
import uuid

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from brain.workflow import (
    Consequence,
    approve,
    claim,
    new_plan,
    put_in_params,
    recover_expired,
    succeed,
)


BASE = os.getenv("PB_BASE", "http://127.0.0.1:18091").rstrip("/")
SERVICE = os.getenv("RIG_SERVICE_TOKEN", "rig-worker-secret")
TWILIO_AUTH = os.getenv("RIG_TWILIO_AUTH_TOKEN", "rig-twilio-auth")
TWILIO_ACCOUNT = os.getenv("RIG_TWILIO_ACCOUNT_SID", "AC" + "1" * 32)
TWILIO_NUMBER = os.getenv("RIG_TWILIO_NUMBER", "+15550001111")
TWILIO_WEBHOOK = os.getenv("RIG_TWILIO_WEBHOOK_URL", f"{BASE}/sms/inbound")


def expect(response: requests.Response, status: int, label: str) -> requests.Response:
    if response.status_code != status:
        raise AssertionError(
            f"{label}: expected {status}, got {response.status_code}: {response.text[:500]}"
        )
    print(f"PASS {label}")
    return response


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": token, "Content-Type": "application/json"}


def agent_headers(agent_id: str, token: str, lease: str = "") -> dict[str, str]:
    out = {
        "X-Anticipy-Agent-ID": agent_id,
        "X-Anticipy-Agent-Token": token,
        "Content-Type": "application/json",
    }
    if lease:
        out["X-Anticipy-Lease"] = lease
    return out


def service_headers() -> dict[str, str]:
    return {"X-Anticipy-Token": SERVICE, "Content-Type": "application/json"}


def twilio_headers(form: dict[str, str]) -> dict[str, str]:
    payload = TWILIO_WEBHOOK + "".join(key + form[key] for key in sorted(form))
    signature = base64.b64encode(hmac.new(
        TWILIO_AUTH.encode(), payload.encode(), hashlib.sha1).digest()).decode()
    return {"X-Twilio-Signature": signature}


def create_owner(label: str) -> tuple[str, str, str]:
    suffix = uuid.uuid4().hex[:10]
    email = f"rig-{label}-{suffix}@example.com"
    password = "Rig-proof-password-42!"
    legacy = f"legacy-{label}-{suffix}"
    expect(requests.post(
        f"{BASE}/api/collections/owners/records",
        json={"email": email, "password": password, "passwordConfirm": password,
              "legacy_uuid": legacy}, timeout=10,
    ), 200, f"owner {label} signs up")
    auth = expect(requests.post(
        f"{BASE}/api/collections/owners/auth-with-password",
        json={"identity": email, "password": password}, timeout=10,
    ), 200, f"owner {label} signs in").json()
    return auth["record"]["id"], auth["token"], legacy


def create_profile(owner_ref: str, auth: str, legacy: str, first_name: str,
                   phone: str = "") -> str:
    response = expect(requests.post(
        f"{BASE}/api/collections/owner_profile/records",
        headers=auth_headers(auth),
        json={"owner_ref": owner_ref, "owner_id": legacy, "phone": phone,
              "first_name": first_name, "email": f"{first_name.lower()}@example.com"},
        timeout=10,
    ), 200, f"{first_name} creates only their profile")
    return response.json()["id"]


def create_agent(label: str, owner_ref: str, auth: str, legacy: str) -> tuple[str, str, str]:
    agent_id = f"agent-{label}-{uuid.uuid4().hex}"
    rec = expect(requests.post(
        f"{BASE}/agent/register",
        json={"agent_id": agent_id, "browser": "rig browser"},
        timeout=10,
    ), 200, f"server issues agent {label}'s hidden credential").json()
    agent_token = rec["agent_token"]
    expect(requests.patch(
        f"{BASE}/api/collections/agents/records/{rec['id']}",
        headers=auth_headers(auth),
        json={"owner": legacy, "owner_ref": owner_ref, "paired": True}, timeout=10,
    ), 200, f"signed-in owner {label} pairs their agent")
    return rec["id"], agent_id, agent_token


def job_body(plan, owner_ref: str, legacy: str) -> dict:
    fields = plan.job_fields()
    fields.update({
        "owner_ref": owner_ref,
        "owner": legacy,
        "goal": plan.goal,
        "lane": "browser",
        "params": json.dumps(put_in_params({
            "task": plan.goal,
            "authorized": plan.approved_for_current_version,
            "approved_scope": plan.goal if plan.approved_for_current_version else "",
        }, plan), sort_keys=True),
        "attempts": plan.attempts,
    })
    if plan.lease:
        fields.update({
            "claimed_by": plan.lease.actor_id,
            "claimed_at": plan.lease.acquired_at.isoformat(),
        })
    else:
        fields.update({"claimed_by": "", "claimed_at": None})
    return fields


def main() -> None:
    expect(requests.get(f"{BASE}/api/health", timeout=5), 200, "local backend is live")
    owner_a, auth_a, legacy_a = create_owner("a")
    owner_b, auth_b, legacy_b = create_owner("b")
    phone_a = "+1555" + str(int(uuid.uuid4().hex[:8], 16)).zfill(10)[-7:]
    profile_a = create_profile(owner_a, auth_a, legacy_a, "Alpha", phone_a)
    profile_b = create_profile(owner_b, auth_b, legacy_b, "Beta")

    sms_sid = "SM" + uuid.uuid4().hex
    sms_form = {"From": phone_a, "To": TWILIO_NUMBER,
                "AccountSid": TWILIO_ACCOUNT,
                "Body": "send the warranty request", "MessageSid": sms_sid}
    expect(requests.post(
        TWILIO_WEBHOOK, data=sms_form,
        headers={"X-Twilio-Signature": "forged"}, timeout=10,
    ), 403, "forged SMS signature is rejected")
    expect(requests.post(
        TWILIO_WEBHOOK, data=sms_form, headers=twilio_headers(sms_form), timeout=10,
    ), 200, "SMS from one canonical owner is accepted")
    sms_list = expect(requests.get(
        f"{BASE}/api/collections/events/records",
        headers=auth_headers(auth_a),
        params={"filter": f'owner_ref="{owner_a}" && external_event_id="{sms_sid}"'},
        timeout=10,
    ), 200, "owner sees their routed SMS").json()["items"]
    assert len(sms_list) == 1 and sms_list[0]["text"] == sms_form["Body"]
    expect(requests.post(
        TWILIO_WEBHOOK, data=sms_form, headers=twilio_headers(sms_form), timeout=10,
    ), 200, "Twilio retry receives an idempotent response")
    sms_list = requests.get(
        f"{BASE}/api/collections/events/records",
        headers=auth_headers(auth_a),
        params={"filter": f'owner_ref="{owner_a}" && external_event_id="{sms_sid}"'},
        timeout=10,
    ).json()["items"]
    assert len(sms_list) == 1
    print("PASS Twilio retry creates exactly one owner command")
    expect(requests.patch(
        f"{BASE}/api/collections/owner_profile/records/{profile_b}",
        headers=auth_headers(auth_b), json={"phone": phone_a}, timeout=10,
    ), 200, "second account can share the routing number")
    ambiguous_sid = "SM" + uuid.uuid4().hex
    ambiguous_form = {"From": phone_a, "To": TWILIO_NUMBER,
                      "AccountSid": TWILIO_ACCOUNT,
                      "Body": "yes", "MessageSid": ambiguous_sid}
    expect(requests.post(
        TWILIO_WEBHOOK, data=ambiguous_form,
        headers=twilio_headers(ambiguous_form),
        timeout=10,
    ), 200, "ambiguous SMS fails closed without leaking account state")
    ambiguous = requests.get(
        f"{BASE}/api/collections/events/records",
        headers=auth_headers(auth_a),
        params={"filter": f'owner_ref="{owner_a}" && external_event_id="{ambiguous_sid}"'},
        timeout=10,
    ).json()["items"]
    assert not ambiguous
    print("PASS shared phone cannot choose an owner's browser")

    expect(requests.get(
        f'{BASE}/api/collections/events/records?filter=owner_ref="{owner_b}"',
        headers=auth_headers(auth_a), timeout=10,
    ), 403, "owner A cannot widen a list to owner B")
    expect(requests.post(
        f"{BASE}/api/collections/events/records", headers=auth_headers(auth_a),
        json={"owner_ref": owner_b, "device_id": "attack", "kind": "transcript",
              "text": "must not cross tenants"}, timeout=10,
    ), 403, "owner A cannot create owner B data")
    expect(requests.get(
        f"{BASE}/api/collections/owner_profile/records/{profile_b}",
        headers=auth_headers(auth_a), timeout=10,
    ), 403, "owner A cannot read owner B profile")

    _, agent_a, secret_a = create_agent("a", owner_a, auth_a, legacy_a)
    _, agent_b, secret_b = create_agent("b", owner_b, auth_b, legacy_b)
    expect(requests.get(
        f"{BASE}/agent/key?agent_id={agent_a}",
        headers=agent_headers(agent_a, "x" * 64), timeout=10,
    ), 403, "wrong agent secret cannot fetch the model bundle")
    bundle = expect(requests.get(
        f"{BASE}/agent/key?agent_id={agent_a}",
        headers=agent_headers(agent_a, secret_a), timeout=10,
    ), 200, "right agent secret receives a tenant-scoped bundle").json()
    assert bundle["owner_ref"] == owner_a and bundle["owner"]["first_name"] == "Alpha"
    assert "service_token" not in bundle
    print("PASS agent bundle contains only its owner and no master token")

    plan = new_plan(
        owner_ref=owner_a, lineage_key="warranty-claim", goal="submit the warranty claim",
        consequence=Consequence.CONSEQUENTIAL, source_event_id="event-a",
        facts={"serial": "ABC-123"}, required=("serial",),
    )
    malformed = job_body(plan, owner_a, legacy_a)
    malformed.update({"status": "queued", "workflow_state": "queued"})
    expect(requests.post(
        f"{BASE}/api/collections/jobs/records", headers=service_headers(),
        json=malformed, timeout=10,
    ), 409, "consequential work cannot queue without bound approval")

    plan = approve(plan, expected_version=1, owner_words="Send it")
    job = expect(requests.post(
        f"{BASE}/api/collections/jobs/records", headers=service_headers(),
        json=job_body(plan, owner_a, legacy_a), timeout=10,
    ), 200, "approved plan is durably queued").json()

    expect(requests.get(
        f'{BASE}/api/collections/jobs/records?filter=owner_ref="{owner_a}"',
        headers=agent_headers(agent_b, secret_b), timeout=10,
    ), 403, "agent B cannot list owner A jobs")
    expect(requests.patch(
        f"{BASE}/api/collections/jobs/records/{job['id']}",
        headers=agent_headers(agent_b, secret_b), json={"result": "tampered"}, timeout=10,
    ), 403, "agent B cannot write owner A job")

    expect(requests.patch(
        f"{BASE}/api/collections/jobs/records/{job['id']}",
        headers=agent_headers(agent_a, secret_a),
        json={"status": "running", "workflow_state": "running"}, timeout=10,
    ), 409, "running cannot be claimed without an actor and lease")

    running = claim(plan, expected_version=1, actor_id=agent_a, lease_seconds=30)
    job = expect(requests.patch(
        f"{BASE}/api/collections/jobs/records/{job['id']}",
        headers=agent_headers(agent_a, secret_a), json=job_body(running, owner_a, legacy_a),
        timeout=10,
    ), 200, "agent A claims with one durable lease").json()
    lease = running.lease.token
    expect(requests.patch(
        f"{BASE}/api/collections/jobs/records/{job['id']}",
        headers=agent_headers(agent_a, secret_a, "wrong-lease"),
        json={"trace": "forged"}, timeout=10,
    ), 409, "wrong lease cannot update running work")

    fake_receipt = {
        "effect_key": "wrong-effect", "summary": "pretend complete",
        "evidence": ["not evidence"], "verified": True,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    expect(requests.patch(
        f"{BASE}/api/collections/jobs/records/{job['id']}",
        headers=agent_headers(agent_a, secret_a, lease),
        json={"status": "done", "workflow_state": "succeeded", "lease_token": "",
              "lease_until": "", "claimed_by": "", "claimed_at": None,
              "receipt": json.dumps(fake_receipt)}, timeout=10,
    ), 409, "fake receipt cannot manufacture completion")

    completed = succeed(
        running, lease_token=lease, summary="claim accepted",
        evidence=("confirmation page #Q41",), verified=True,
    )
    job = expect(requests.patch(
        f"{BASE}/api/collections/jobs/records/{job['id']}",
        headers=agent_headers(agent_a, secret_a, lease),
        json=job_body(completed, owner_a, legacy_a), timeout=10,
    ), 200, "verified evidence completes the exact effect").json()
    expect(requests.patch(
        f"{BASE}/api/collections/jobs/records/{job['id']}",
        headers=agent_headers(agent_a, secret_a),
        json={"status": "queued", "workflow_state": "queued"}, timeout=10,
    ), 409, "completed work cannot be resurrected")

    risky = new_plan(
        owner_ref=owner_a, lineage_key="recall", goal="submit the appliance recall",
        consequence=Consequence.CONSEQUENTIAL, source_event_id="event-risk",
    )
    risky = approve(risky, expected_version=1, owner_words="Send it")
    risky_job = expect(requests.post(
        f"{BASE}/api/collections/jobs/records", headers=service_headers(),
        json=job_body(risky, owner_a, legacy_a), timeout=10,
    ), 200, "second approved effect is queued").json()
    risky_running = claim(risky, expected_version=1, actor_id=agent_a, lease_seconds=5)
    risky_job = expect(requests.patch(
        f"{BASE}/api/collections/jobs/records/{risky_job['id']}",
        headers=agent_headers(agent_a, secret_a),
        json=job_body(risky_running, owner_a, legacy_a), timeout=10,
    ), 200, "short crash-test lease is claimed").json()
    risky_lease = risky_running.lease.token
    expect(requests.patch(
        f"{BASE}/api/collections/jobs/records/{risky_job['id']}",
        headers=agent_headers(agent_a, secret_a, risky_lease),
        json={"effect_uncertain": True}, timeout=10,
    ), 200, "possible external effect is persisted before acting")
    time.sleep(5.2)
    expect(requests.patch(
        f"{BASE}/api/collections/jobs/records/{risky_job['id']}",
        headers=agent_headers(agent_a, secret_a, risky_lease),
        json={"status": "done", "workflow_state": "succeeded", "lease_token": "",
              "lease_until": "", "receipt": json.dumps({
                  "effect_key": risky.effect_key, "summary": "late claim",
                  "evidence": ["late"], "verified": True,
              })}, timeout=10,
    ), 409, "expired executor cannot report success")
    expect(requests.patch(
        f"{BASE}/api/collections/jobs/records/{risky_job['id']}",
        headers=agent_headers(agent_a, secret_a, risky_lease),
        json={"status": "queued", "workflow_state": "queued", "lease_token": "",
              "lease_until": "", "effect_uncertain": False}, timeout=10,
    ), 409, "uncertain effect cannot blindly requeue")

    parked = recover_expired(
        risky_running,
        external_effect_uncertain=True,
        now=risky_running.lease.expires_at + timedelta(milliseconds=1),
    )
    risky_job = expect(requests.patch(
        f"{BASE}/api/collections/jobs/records/{risky_job['id']}",
        headers=agent_headers(agent_a, secret_a, risky_lease),
        json={**job_body(parked, owner_a, legacy_a), "effect_uncertain": True}, timeout=10,
    ), 200, "crashed uncertain effect parks for owner verification").json()
    resumed = approve(parked, expected_version=1,
                      owner_words="I checked the site; the action did not happen. Try again.")
    expect(requests.patch(
        f"{BASE}/api/collections/jobs/records/{risky_job['id']}",
        headers=auth_headers(auth_a),
        json={**job_body(resumed, owner_a, legacy_a), "effect_uncertain": False}, timeout=10,
    ), 409, "owner retry without a reconciliation record is refused")
    reconciliation = {
        "effect_key": risky.effect_key, "conclusion": "not_applied", "verified": True,
        "owner_words": "I checked the site; the action did not happen. Try again.",
        "evidence": ["owner explicitly checked the destination before retry"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    retry_body = {**job_body(resumed, owner_a, legacy_a), "effect_uncertain": False,
                  "reconciliation": json.dumps(reconciliation, sort_keys=True)}
    expect(requests.patch(
        f"{BASE}/api/collections/jobs/records/{risky_job['id']}",
        headers=agent_headers(agent_a, secret_a), json=retry_body, timeout=10,
    ), 409, "browser executor cannot mint owner approval")
    expect(requests.patch(
        f"{BASE}/api/collections/jobs/records/{risky_job['id']}",
        headers=auth_headers(auth_a), json=retry_body, timeout=10,
    ), 200, "explicit checked-not-applied reconciliation permits retry")

    print("\nALL WORKFLOW + TENANT RIG PROOFS PASSED")


if __name__ == "__main__":
    main()
