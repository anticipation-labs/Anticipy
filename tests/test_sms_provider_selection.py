"""Which arm the worker texts through, and what only Twilio may touch.

`brain/sendblue_arm.py choose_provider` is the ONE rule: Sendblue when its
three variables are set, else Twilio when its credentials are, else mock —
and ANTICIPY_SMS_PROVIDER names one outright. It is read by the worker's
transport build, the `worker up` banner and overnight/does_she_reach_them.py,
so a gate can never measure a different vendor than the one texting.

The polarity pinned here: a provider that is NAMED but NOT CONFIGURED is
mock, never the other vendor. An operator who wrote `sendblue` and forgot the
secret asked for one channel and must not be answered on another.

And the Twilio-only startup work — reading and rewriting a Twilio number's
inbound binding — runs ONLY for the Twilio provider. A deployment texting
through Sendblue with TWILIO_* still in its environment must not touch the
retired number.
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


def test_twilio_when_only_twilio_is_configured(clean_env):
    setenv(clean_env, TWILIO)
    assert sb.choose_provider() == "twilio"
    # A key pair alone is a Twilio credential too (voice_arm.rest_credential).
    clean_env.delenv("TWILIO_AUTH_TOKEN")
    setenv(clean_env, TWILIO_API_KEY_SID="SK" + "2" * 32, TWILIO_API_KEY_SECRET="s")
    assert sb.choose_provider() == "twilio"


def test_two_of_three_sendblue_variables_is_not_sendblue(clean_env):
    partial = dict(SENDBLUE)
    del partial["SENDBLUE_FROM_NUMBER"]
    setenv(clean_env, partial)
    assert sb.choose_provider() == "mock"
    setenv(clean_env, TWILIO)
    assert sb.choose_provider() == "twilio"


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
    assert sb.choose_provider() == "twilio"
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
    assert worker.sms_banner("twilio", object()) == "twilio"
    assert worker.sms_banner("mock", None) == "mock"


def test_the_worker_builds_the_transport_over_the_chosen_arm():
    """The build site reads the one rule, hands the chosen arm to the
    provider-neutral transport, and prints the banner and the ear line."""
    src = inspect.getsource(worker.main)
    assert "sendblue_arm.choose_provider()" in src
    assert "sendblue_arm.SendblueArm()" in src
    assert "MessageTransport(" in src
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


def test_the_twilio_ear_check_runs_for_the_twilio_provider(clean_env):
    setenv(clean_env, TWILIO, SENDBLUE, ANTICIPY_SMS_PROVIDER="twilio")
    reads = _Reads()
    clean_env.setattr(worker, "requests", reads)
    clean_env.setattr(worker, "PB", "https://backend.example.com")
    clean_env.setattr("builtins.print", lambda *a, **k: None)
    worker.ensure_inbound_webhook()
    assert reads.gets and "IncomingPhoneNumbers" in reads.gets[0]


def test_the_twilio_ear_check_stays_quiet_with_no_provider(clean_env):
    clean_env.setattr(worker, "requests", _MustNotBeAsked())
    worker.ensure_inbound_webhook()


def test_the_supervisor_watchdog_goes_through_the_same_gate():
    """The supervisor calls the same function, so the fleet's watchdog is
    gated by the same provider rule without a second switch to forget."""
    import brain.supervisor as supervisor
    assert "worker.ensure_inbound_webhook()" in inspect.getsource(supervisor.main)


def test_the_sendblue_startup_line_names_the_dashboard_and_the_derived_url(clean_env):
    clean_env.setattr(worker, "PB", "https://api.anticipy.example/")
    line = worker.inbound_ear_note("sendblue")
    assert "Developer → Webhooks" in line
    assert "https://api.anticipy.example/sms/sendblue" in line
    assert "every beat" in worker.inbound_ear_note("twilio")
    assert "nothing to point" in worker.inbound_ear_note("mock")
