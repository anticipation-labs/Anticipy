"""Inbound SMS is authenticated cryptographically, not by a URL secret."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "backend" / "pb_hooks" / "twilio_signature.js"


def js_signature(token: str, url: str, params: dict) -> str:
    program = (
        f"const v=require({json.dumps(str(HELPER))});"
        f"process.stdout.write(v.expectedSignature({json.dumps(token)},"
        f"{json.dumps(url)},{json.dumps(params)}));"
    )
    return subprocess.check_output(["node", "-e", program], text=True)


def test_matches_twilios_published_reference_vector():
    params = {
        "Digits": "1234",
        "To": "+18005551212",
        "From": "+14158675310",
        "Caller": "+14158675310",
        "CallSid": "CA1234567890ABCDE",
    }
    assert js_signature("12345", "https://example.com/myapp.php?foo=1&bar=2", params) \
        == "L/OH5YylLD5NRKLltdqwSvS0BnU="


def test_matches_standard_hmac_for_unicode_and_future_parameters():
    token = "pässphrase"
    url = "https://backend.example/sms/inbound"
    params = {
        "AccountSid": "AC" + "1" * 32,
        "Body": "Meet at café ☕",
        "From": "+16045550111",
        "FutureTwilioField": "kept",
        "MessageSid": "SM" + "a" * 32,
        "To": "+16045550222",
    }
    payload = url + "".join(key + params[key] for key in sorted(params))
    expected = base64.b64encode(hmac.new(
        token.encode(), payload.encode(), hashlib.sha1).digest()).decode()
    assert js_signature(token, url, params) == expected


def test_sms_hook_requires_signature_and_worker_configures_a_clean_url():
    hook = (ROOT / "backend" / "pb_hooks" / "sms.pb.js").read_text()
    worker = (ROOT / "brain" / "worker.py").read_text()
    assert "X-Twilio-Signature" in hook
    assert "TWILIO_AUTH_TOKEN" in hook
    assert "ANTICIPY_TWILIO_WEBHOOK_URL" in hook
    assert "ANTICIPY_SMS_TOKEN" not in hook
    assert "/sms/inbound?token=" not in worker
