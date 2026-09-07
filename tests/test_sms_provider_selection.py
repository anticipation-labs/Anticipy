"""One live provider across the conversational and direct notification paths.
Retired Twilio settings cannot select a sender or rewrite a webhook. Missing
SendBlue configuration remains an explicit non-delivery rather than fallback.
"""
from __future__ import annotations

import inspect
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from brain import sendblue_arm as sb        # noqa: E402
import brain.worker as worker               # noqa: E402

TWILIO = {"TWILIO_ACCOUNT_SID": "AC" + "1" * 32, "TWILIO_AUTH_TOKEN": "tok",
          "TWILIO_PHONE_NUMBER": "+15550001111"}
SENDBLUE = {"SENDBLUE_API_KEY_ID": "sbkey-" + "0" * 8 + "4321",
            "SENDBLUE_API_SECRET_KEY": "secret-value", "SENDBLUE_FROM_NUMBER": "+15550002222"}
NAMES = tuple(TWILIO) + tuple(SENDBLUE) + (
    "TWILIO_FROM", "TWILIO_API_KEY_SID", "TWILIO_API_KEY_SECRET", "TWILIO_MOCK",
    "ANTICIPY_SMS_MOCK", "ANTICIPY_SMS_PROVIDER", "ANTICIPY_TWILIO_WEBHOOK_URL")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def setenv(monkeypatch, *groups, **extra):
    for group in groups:
        for k, v in group.items():
            monkeypatch.setenv(k, v)
    for k, v in extra.items():
        monkeypatch.setenv(k, v)


# ------------------------------------------------------------- the provider

def test_nothing_configured_is_mock():
    assert sb.choose_provider() == "mock"


def test_sendblue_is_the_default_when_its_three_variables_are_set(clean_env):
    setenv(clean_env, SENDBLUE)
    assert sb.choose_provider() == "sendblue"
    setenv(clean_env, TWILIO)
    assert sb.choose_provider() == "sendblue", "Sendblue wins over Twilio when both are set"


def test_retired_twilio_credentials_cannot_select_a_sender(clean_env):
    setenv(clean_env, TWILIO)
    assert sb.choose_provider() == "mock"
    # A key pair alone is a Twilio credential too (voice_arm.rest_credential).
    clean_env.delenv("TWILIO_AUTH_TOKEN")
    setenv(clean_env, TWILIO_API_KEY_SID="SK" + "2" * 32, TWILIO_API_KEY_SECRET="s")
    assert sb.choose_provider() == "mock"


def test_two_of_three_sendblue_variables_is_not_sendblue(clean_env):
    partial = dict(SENDBLUE)
    del partial["SENDBLUE_FROM_NUMBER"]
    setenv(clean_env, partial)
    assert sb.choose_provider() == "mock"
    setenv(clean_env, TWILIO)
    assert sb.choose_provider() == "mock"


def test_a_named_provider_that_is_not_configured_is_mock_not_the_other_vendor(clean_env):
    setenv(clean_env, TWILIO, ANTICIPY_SMS_PROVIDER="sendblue")
    assert sb.choose_provider() == "mock", "asked for Sendblue, must not text via Twilio"
    clean_env.undo() if False else None
    for name in TWILIO:
        clean_env.delenv(name)
    setenv(clean_env, SENDBLUE, ANTICIPY_SMS_PROVIDER="twilio")
    assert sb.choose_provider() == "mock", "asked for Twilio, must not text via Sendblue"


def test_a_named_provider_that_is_configured_is_honoured_over_the_default(clean_env):
    setenv(clean_env, TWILIO, SENDBLUE, ANTICIPY_SMS_PROVIDER="twilio")
    assert sb.choose_provider() == "mock"
    setenv(clean_env, ANTICIPY_SMS_PROVIDER="Sendblue")
    assert sb.choose_provider() == "sendblue", "case-insensitive"


def test_an_unknown_provider_name_is_mock(clean_env):
    setenv(clean_env, TWILIO, SENDBLUE, ANTICIPY_SMS_PROVIDER="imessage")
    assert sb.choose_provider() == "mock"


def test_a_muzzle_makes_every_provider_mock(clean_env):
    setenv(clean_env, TWILIO, SENDBLUE, ANTICIPY_SMS_MOCK="1")
    assert sb.choose_provider() == "mock"
    clean_env.delenv("ANTICIPY_SMS_MOCK")
    setenv(clean_env, TWILIO_MOCK="true")
    assert sb.choose_provider() == "mock"
    setenv(clean_env, TWILIO_MOCK="false")
    assert sb.choose_provider() == "sendblue"


# ---------------------------------------------------------------- the banner

def test_the_banner_names_the_vendor_and_the_key_tail_never_the_secret(clean_env):
    setenv(clean_env, SENDBLUE)
    arm = sb.SendblueArm(journal=lambda _l: None)
    assert worker.sms_banner("sendblue", arm) == "sendblue:…4321"
    assert "secret-value" not in worker.sms_banner("sendblue", arm)
    assert worker.sms_banner("twilio", object()) == "mock"
    assert worker.sms_banner("mock", None) == "mock"


def test_the_worker_builds_the_transport_over_the_chosen_arm():
    """The build site reads the one rule, hands the chosen arm to the
    provider-neutral transport, and prints the banner and the ear line."""
    src = inspect.getsource(worker.main)
    assert "sendblue_arm.choose_provider()" in src
    assert "configure_message_transport(anticipy, sms_provider)" in src
    binding = inspect.getsource(worker.configure_message_transport)
    assert "sendblue_arm.SendblueArm()" in binding
    assert "MessageTransport(" in binding
    assert "ensure_inbound_webhook()" not in src
    assert "sms_banner(sms_provider, arm)" in src
    assert "inbound_ear_note(sms_provider)" in src
    assert "sms={'live'" not in src, "the field names the vendor or says mock"


# ------------------------------------------------ what only Twilio may touch

class _MustNotBeAsked:
    """Stands in for `requests` in the worker: any call is a failure."""

    def get(self, *_a, **_k):
        pytest.fail("the Twilio ear check ran for a non-Twilio provider")

    post = get


class _Reads:
    def __init__(self):
        self.gets: list[str] = []

    def get(self, url, **_k):
        self.gets.append(url)
        return type("R", (), {"ok": False, "status_code": 401})()

    def post(self, *_a, **_k):
        pytest.fail("nothing here should write")


def test_the_twilio_ear_check_is_skipped_for_the_sendblue_provider(clean_env):
    setenv(clean_env, TWILIO, SENDBLUE)                  # Sendblue by default
    clean_env.setattr(worker, "requests", _MustNotBeAsked())
    clean_env.setattr(worker, "PB", "https://backend.example.com")
    printed: list[str] = []
    clean_env.setattr("builtins.print", lambda *a, **k: printed.append(" ".join(map(str, a))))
    worker.ensure_inbound_webhook()
    assert printed == [], "silent every beat; the one line is printed at startup"


def test_retired_provider_setting_cannot_rebind_a_twilio_number(clean_env):
    setenv(clean_env, TWILIO, SENDBLUE, ANTICIPY_SMS_PROVIDER="twilio")
    reads = _Reads()
    clean_env.setattr(worker, "requests", reads)
    clean_env.setattr(worker, "PB", "https://backend.example.com")
    clean_env.setattr("builtins.print", lambda *a, **k: None)
    worker.ensure_inbound_webhook()
    assert reads.gets == []


def test_the_twilio_ear_check_stays_quiet_with_no_provider(clean_env):
    clean_env.setattr(worker, "requests", _MustNotBeAsked())
    worker.ensure_inbound_webhook()


def test_missing_sendblue_clears_the_retired_direct_send_arm(clean_env):
    from types import SimpleNamespace
    from brain.anticipy_core import Anticipy
    class RetiredArm:
        def text(self, *args, **kwargs):
            raise AssertionError("retired arm reached a phone")
    setenv(clean_env, TWILIO, ANTICIPY_SMS_PROVIDER="sendblue")
    owner = SimpleNamespace(voice=RetiredArm(), conversation=None, owner_phone="+12025550123")
    arm, transport = worker.configure_message_transport(owner, sb.choose_provider())
    assert arm is None and owner.voice is None
    assert transport.send(owner.owner_phone, "test only")["mock"] is True
    assert Anticipy.notify_owner(owner, "test only") == {"skipped": "no transport"}


def test_sendblue_binds_both_surfaces_and_preserves_destination_guard(clean_env):
    from types import SimpleNamespace
    calls = []
    class SelectedArm:
        def text(self, to, text, **kwargs):
            calls.append((to, text))
            return {"message_handle": "synthetic", "status": "SENT"}
    selected = SelectedArm()
    clean_env.setattr(sb, "SendblueArm", lambda: selected)
    clean_env.setattr(worker, "canonical_phone_allows_effect", lambda owner, to: to == owner.owner_phone)
    owner = SimpleNamespace(voice=None, owner_phone="+12025550123")
    arm, transport = worker.configure_message_transport(owner, "sendblue")
    assert arm is selected and owner.voice is selected
    transport.send(owner.owner_phone, "synthetic message")
    assert transport.send("+12025550124", "wrong owner") is None
    assert calls == [(owner.owner_phone, "synthetic message")]


def test_startup_uses_the_shared_transport_binding():
    assert "configure_message_transport(anticipy, sms_provider)" in inspect.getsource(worker.main)
    assert "VoiceArm()" not in inspect.getsource(worker.main).split("sms_provider =", 1)[1]


def test_the_sendblue_startup_line_names_the_dashboard_and_the_derived_url(clean_env):
    clean_env.setattr(worker, "PB", "https://api.anticipy.example/")
    line = worker.inbound_ear_note("sendblue")
    assert "Developer → Webhooks" in line
    assert "https://api.anticipy.example/sms/sendblue" in line
    assert "nothing to point" in worker.inbound_ear_note("twilio")
    assert "nothing to point" in worker.inbound_ear_note("mock")
