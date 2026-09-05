#!/usr/bin/env python3
"""Read-only production acceptance plus a non-persisting signed-SMS probe.

The signed SMS uses an unregistered +1 555 sender. The webhook validates it and
returns TwiML, but owner resolution fails closed so no event is created.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import uuid

import requests


# 2026-09-05: this file died on os.environ["ANTICIPY_SERVICE_TOKEN"] before it
# checked anything, because nothing loaded .env.local — the defect
# capture_day.py had, in the one script that is supposed to run right after a
# deploy. Explicit environment still wins over the file.
import sys  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "overnight"))
import _env  # noqa: E402

_env.load_and_announce(str(Path(__file__).resolve().parents[1]))
BASE = os.getenv(
    "ANTICIPY_PRODUCTION_URL",
    "https://api.anticipy.ai",
).rstrip("/")
ROOT = Path(__file__).resolve().parents[1]


def require(response: requests.Response, status: int, label: str) -> requests.Response:
    if response.status_code != status:
        raise RuntimeError(f"{label}: HTTP {response.status_code}: {response.text[:160]}")
    print(f"PASS {label}: HTTP {status}")
    return response


def twilio_signature(url: str, body: dict[str, str], token: str) -> str:
    signed = url + "".join(k + body[k] for k in sorted(body))
    digest = hmac.new(token.encode(), signed.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def main() -> None:
    service_token = os.environ["ANTICIPY_SERVICE_TOKEN"]
    auth_token = os.environ["TWILIO_AUTH_TOKEN"]
    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    to_number = os.environ["TWILIO_PHONE_NUMBER"]
    webhook_url = os.environ.get(
        "ANTICIPY_TWILIO_WEBHOOK_URL", f"{BASE}/sms/inbound")

    require(requests.get(f"{BASE}/api/health", timeout=20), 200, "PocketBase health")
    setup = require(requests.get(f"{BASE}/setup.html", timeout=20), 200, "browser setup")
    # The name the setup page and is_it_live.py agree on; the two other zips
    # are aliases of the same bytes. Until 2026-09-05 this pinned the old
    # "Codex" branding and could not pass against any page since the rename.
    expected_download = "/anticipy-claude-version-extension.zip"
    if not re.search(
        r'href=["\']' + re.escape(expected_download) + r'["\']', setup.text
    ) or "Download Anticipy" not in setup.text:
        raise RuntimeError("browser setup: branded download action missing")

    privacy = require(requests.get(f"{BASE}/privacy.html", timeout=20), 200, "privacy policy")
    # Sendblue carries the texts from 2026-09-05; the policy must say so. Twilio
    # stays named until it is retired, and its absence later is not a failure.
    for phrase in ("OpenRouter", "Sendblue", "Apple speech recognition", "delete"):
        if phrase not in privacy.text:
            raise RuntimeError(f"privacy policy: missing disclosure {phrase!r}")

    package = require(
        requests.get(f"{BASE}{expected_download}", timeout=30),
        200, "extension package")
    local_digest = hashlib.sha256(
        (ROOT / "backend/pb_public/anticipy-claude-version-extension.zip").read_bytes()).hexdigest()
    remote_digest = hashlib.sha256(package.content).hexdigest()
    if remote_digest != local_digest:
        raise RuntimeError(
            f"extension package: deployed SHA-256 {remote_digest} != release {local_digest}")
    print(f"PASS extension package identity: sha256:{remote_digest}")

    owners = require(
        requests.get(f"{BASE}/worker/owners", headers={"X-Anticipy-Token": service_token},
                     timeout=20),
        200, "owner discovery")
    total = int(owners.json().get("totalItems", 0))
    if total < 1:
        raise RuntimeError("owner discovery: production contains no owner")
    print(f"PASS owner discovery: {total} account(s), identifiers suppressed")

    sms_body = {
        "AccountSid": account_sid,
        "Body": "Anticipy signed production acceptance probe",
        "From": "+15550000000",
        "MessageSid": "SM" + uuid.uuid4().hex,
        "To": to_number,
    }
    require(requests.post(webhook_url, data=sms_body,
                          headers={"X-Twilio-Signature": "forged"}, timeout=20),
            403, "forged inbound SMS rejected")
    signature = twilio_signature(webhook_url, sms_body, auth_token)
    signed = require(requests.post(
        webhook_url, data=sms_body,
        headers={"X-Twilio-Signature": signature}, timeout=20),
        200, "valid inbound SMS accepted")
    if "<Response" not in signed.text:
        raise RuntimeError("valid inbound SMS: TwiML response missing")

    print(json.dumps({
        "ok": True,
        "backend": BASE,
        "extension_sha256": remote_digest,
        "owner_count": total,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
