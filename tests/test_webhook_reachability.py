"""A local worker must not be able to break his real phone number.

Live, 2026-08-19: a laptop worker started with the production TWILIO_* vars
inherited from a shell's exports and ANTICIPY_PB=http://127.0.0.1:8090.
`ensure_inbound_webhook` compared the live binding against its own idea of
"ours", decided the production URL was a hijack, and wrote
http://127.0.0.1:8090/sms/inbound onto +1 619 658 4447. Twilio cannot reach a
loopback address, so from that moment every text he sent would have been
dropped, and the only evidence was one line of stdout on the laptop.

The function's whole justification is that it repairs a binding somebody else
broke. A URL Twilio cannot reach is not a repair, so it must refuse.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import brain.worker as worker  # noqa: E402


class _Recorder:
    """Stands in for `requests`. Records whether a WRITE ever happened."""

    def __init__(self, current_sms_url="https://real.example.com/sms/inbound"):
        self.current = current_sms_url
        self.gets = 0
        self.posts = []

    def get(self, url, **kw):
        self.gets += 1
        return _Resp({"incoming_phone_numbers": [
            {"phone_number": "+15550001111", "sid": "PN1",
             "sms_url": self.current, "sms_application_sid": ""},
        ]})

    def post(self, url, **kw):
        self.posts.append(kw.get("data") or {})
        return _Resp({})


class _Resp:
    def __init__(self, payload):
        self._payload = payload
        self.ok = True
        self.status_code = 200

    def json(self):
        return self._payload


def _run(target_url, monkeypatch, current="https://real.example.com/sms/inbound"):
    rec = _Recorder(current)
    monkeypatch.setattr(worker, "requests", rec)
    monkeypatch.setattr(worker, "PB", "http://unused.invalid")
    for k, v in (("TWILIO_ACCOUNT_SID", "AC1"),
                 ("TWILIO_AUTH_TOKEN", "tok"),
                 ("TWILIO_PHONE_NUMBER", "+15550001111"),
                 ("ANTICIPY_TWILIO_WEBHOOK_URL", target_url)):
        monkeypatch.setenv(k, v)
    worker.ensure_inbound_webhook()
    return rec


UNREACHABLE = [
    "http://127.0.0.1:8090/sms/inbound",       # the exact URL that was written
    "http://localhost:8090/sms/inbound",
    "https://localhost:8090/sms/inbound",      # https does not make it routable
    "http://[::1]:8090/sms/inbound",
    "http://0.0.0.0:8090/sms/inbound",
    "https://mac-mini.local/sms/inbound",
    "https://10.0.0.4/sms/inbound",
    "https://192.168.1.20/sms/inbound",
    "https://169.254.10.10/sms/inbound",
    "https://172.16.0.9/sms/inbound",          # bottom of the RFC1918 /12
    "https://172.31.255.254/sms/inbound",      # top of the RFC1918 /12
    "http://public.example.com/sms/inbound",   # plain http: signature is over
                                               # the exact URL, so never
]


def test_an_unreachable_target_writes_nothing(monkeypatch):
    for url in UNREACHABLE:
        rec = _run(url, monkeypatch)
        assert rec.posts == [], f"{url} must not be written to Twilio"


def test_a_public_https_target_is_still_repaired(monkeypatch):
    """The guard must not disable the feature it protects.

    Without this, "refuse the bad ones" could be satisfied by refusing
    everything, and the hijack this function exists to fix would silently stop
    being fixed.
    """
    rec = _run("https://backend.example.com/sms/inbound?token=abc", monkeypatch)
    assert len(rec.posts) == 1, "a reachable URL must still be repointed"
    assert rec.posts[0]["SmsUrl"] == "https://backend.example.com/sms/inbound?token=abc"
    assert rec.posts[0]["SmsMethod"] == "POST"
    # An application SID silently overrides every sms_* URL, so clearing it is
    # part of a working repair.
    assert rec.posts[0]["SmsApplicationSid"] == ""


def test_a_correct_binding_is_left_alone(monkeypatch):
    same = "https://backend.example.com/sms/inbound?token=abc"
    rec = _run(same, monkeypatch, current=same)
    assert rec.posts == [], "an already-correct binding must not be rewritten"


def test_172_addresses_outside_rfc1918_are_not_treated_as_private(monkeypatch):
    """172.15.x and 172.32.x are PUBLIC. A sloppy `startswith("172.")` would
    refuse real hosts and quietly stop repairing a genuine hijack."""
    for url in ("https://172.15.0.1/sms/inbound", "https://172.32.0.1/sms/inbound"):
        rec = _run(url, monkeypatch)
        assert len(rec.posts) == 1, f"{url} is public and must still be written"


def test_no_credentials_means_no_calls_at_all(monkeypatch):
    """The pre-existing contract: without all three vars this is not our job."""
    rec = _Recorder()
    monkeypatch.setattr(worker, "requests", rec)
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWILIO_PHONE_NUMBER", raising=False)
    monkeypatch.delenv("TWILIO_FROM", raising=False)
    worker.ensure_inbound_webhook()
    assert rec.gets == 0 and rec.posts == []
